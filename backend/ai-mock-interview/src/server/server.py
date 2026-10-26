# Linly-Talker-Stream (https://github.com/Kedreamix/Linly-Talker-Stream). Copyright [Linly-talker-stream@kedreamix]. Apache-2.0.
# Based on LiveTalking (C) 2024 LiveTalking@lipku https://github.com/lipku/LiveTalking (Apache-2.0).

"""服务器启动和配置"""
import asyncio
from aiohttp import web
import aiohttp_cors

from src.utils.logging import logger
from src.server.state import state
from src.server import routes


async def on_shutdown(app):
    """服务器关闭时的清理操作"""
    coros = [pc.close() for pc in state.pcs]
    await asyncio.gather(*coros)
    state.pcs.clear()


def create_app():
    """创建并配置 aiohttp 应用"""
    # 单独设置较大的请求体上限，方便上传音视频
    app = web.Application(client_max_size=1024**2*100)
    app.on_shutdown.append(on_shutdown)
    
    # 路由集中注册，避免分散难维护
    app.router.add_post("/offer", routes.offer)
    app.router.add_post("/human", routes.human)
    app.router.add_post("/humanaudio", routes.humanaudio)
    app.router.add_post("/asr", routes.asr)
    app.router.add_post("/set_audiotype", routes.set_audiotype)
    app.router.add_post("/record", routes.record)
    app.router.add_post("/interrupt_talk", routes.interrupt_talk)
    app.router.add_post("/is_speaking", routes.is_speaking)
    app.router.add_post("/clear_history", routes.clear_history)
    app.router.add_get("/health", routes.health_check)
    app.router.add_get("/download/{filename}", routes.download_record)
    # 前端静态资源托管
    app.router.add_static('/', path='web')
    
    # 宽松 CORS 方便本地调试和跨域访问
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
    })
    
    for route in list(app.router.routes()):
        cors.add(route)
    
    return app


def run_server(app, config):
    """运行服务器"""
    # 兼容新旧配置字段
    use_ssl = getattr(config.app, 'ssl', False)
    if not use_ssl:
        use_ssl = hasattr(config.app, 'ssl_cert') and config.app.ssl_cert and \
                  hasattr(config.app, 'ssl_key') and config.app.ssl_key
    
    protocol = 'https' if use_ssl else 'http'
    listen_host = getattr(config.app, 'listenhost', '0.0.0.0')
    listen_port = config.app.listenport
    
    # 启动信息集中打印，便于排查配置问题
    logger.info('┌─────────────────────────────────────────────┐')
    logger.info('│  🚀 Linly-Talker-Stream 后端服务启动中...   │')
    logger.info('├─────────────────────────────────────────────┤')
    logger.info(f'│  协议: {protocol.upper():<37} │')
    logger.info(f'│  监听地址: {listen_host:<30} │')
    logger.info(f'│  监听端口: {listen_port:<30} │')
    
    if protocol == 'http':
        logger.info('│                                             │')
        logger.info('│  ⚠️  HTTP 模式：浏览器录音仅支持 localhost  │')
        logger.info('│  💡 远程访问需要在配置中启用 ssl: true     │')
    else:
        logger.info(f'│  证书文件: {config.app.ssl_cert:<28} │')
    
    logger.info('└─────────────────────────────────────────────┘')
    
    config.app.protocol = protocol
    
    # 标记可用，供健康检查使用
    state.server_ready = True
    logger.info('✅ 服务已就绪，可以接受连接')
    
    def _run():
        # 独立事件循环，避免与外部线程冲突
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = web.AppRunner(app)
        loop.run_until_complete(runner.setup())
        
        if use_ssl:
            import ssl
            # 仅做服务端 TLS，不做客户端校验
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_cert_chain(config.app.ssl_cert, config.app.ssl_key)
            site = web.TCPSite(runner, listen_host, listen_port, ssl_context=ssl_context)
            logger.info(f'✅ HTTPS 服务已启动: https://{listen_host}:{listen_port}')
        else:
            site = web.TCPSite(runner, listen_host, listen_port)
            logger.info(f'✅ HTTP 服务已启动: http://{listen_host}:{listen_port}')
        
        loop.run_until_complete(site.start())
        loop.run_forever()
    
    _run()
