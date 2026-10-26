"""聊天相关路由"""
import json
from aiohttp import web
import asyncio

from src.llm.service import llm_response
from src.utils.logging import logger
from src.server.state import state


async def human(request):
    """处理文本对话请求"""
    try:
        params = await request.json()
        sessionid = params.get('sessionid', 0)
        
        if params.get('interrupt'):
            state.avatar_streams[sessionid].flush_talk()

        if params['type'] == 'echo':
            state.avatar_streams[sessionid].put_msg_txt(params['text'])
            response_text = params['text']
        elif params['type'] == 'chat':
            # 放到线程池，避免阻塞事件循环
            llm_config = state.config.llm if state.config else None
            logger.info(f'[CHAT] LLM 配置: {llm_config}')
            response_text = await asyncio.get_event_loop().run_in_executor(
                None,
                llm_response,
                params['text'],
                state.avatar_streams[sessionid],
                llm_config.api_key if llm_config else None,
                llm_config.base_url if llm_config else "https://dashscope.aliyuncs.com/compatible-mode/v1",
                llm_config.model if llm_config else "qwen-plus"
            )

        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": 0, "msg": "ok", "response": response_text}
            ),
        )
    except Exception as e:
        logger.exception('exception:')
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": -1, "msg": str(e)}
            ),
        )


async def interrupt_talk(request):
    """中断当前对话"""
    try:
        params = await request.json()
        sessionid = params.get('sessionid', 0)
        state.avatar_streams[sessionid].flush_talk()
        
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": 0, "msg": "ok"}
            ),
        )
    except Exception as e:
        logger.exception('exception:')
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": -1, "msg": str(e)}
            ),
        )


async def is_speaking(request):
    """查询是否正在说话"""
    params = await request.json()
    sessionid = params.get('sessionid', 0)
    avatar = state.avatar_streams.get(sessionid)
    if avatar is None:
        return web.json_response({'code': -1, 'error': '数字人连接已断开，请重新连接。'}, status=409)
    
    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"code": 0, "data": avatar.is_speaking(),
             "speech_error": getattr(avatar.tts, 'last_error', ''),
             "speech_note": getattr(avatar.tts, 'last_notice', ''),
             "speech_pending": bool(getattr(avatar.tts, 'pending', False))}
        ),
    )


async def clear_history(request):
    """清空对话历史"""
    try:
        params = await request.json()
        sessionid = params.get('sessionid', 0)
        
        clear_session_history(sessionid)
        
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": 0, "msg": "对话历史已清空"}
            ),
        )
    except Exception as e:
        logger.exception('清空历史失败:')
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": -1, "msg": str(e)}
            ),
        )
