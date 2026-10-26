"""视频相关路由"""
import os
import json
from aiohttp import web

from src.utils.logging import logger
from src.server.state import state


async def set_audiotype(request):
    """设置音频类型"""
    try:
        params = await request.json()
        sessionid = params.get('sessionid', 0)
        state.avatar_streams[sessionid].set_custom_state(params['audiotype'], params['reinit'])

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


async def record(request):
    """处理录制请求"""
    try:
        params = await request.json()
        logger.info(f'[录制API] 收到请求: {params}')

        sessionid = params.get('sessionid', 0)
        logger.info(f'[录制API] sessionid={sessionid}')
        
        if sessionid not in state.avatar_streams:
            logger.error(f'[录制API] 录制失败: sessionid {sessionid} 不存在')
            logger.error(f'[录制API] 当前可用的 sessionid: {list(state.avatar_streams.keys())}')
            return web.Response(
                content_type="application/json",
                text=json.dumps(
                    {"code": -1, "msg": f"sessionid {sessionid} not found"}
                ),
                status=404
            )
        
        if state.avatar_streams[sessionid] is None:
            logger.error(f'[录制API] 录制失败: sessionid {sessionid} 的 avatar_stream 为 None')
            return web.Response(
                content_type="application/json",
                text=json.dumps(
                    {"code": -1, "msg": "avatar stream not initialized"}
                ),
                status=500
            )
        
        avatar_stream = state.avatar_streams[sessionid]
        logger.info(f'[录制API] 找到 avatar_stream: {type(avatar_stream).__name__}')
        logger.info(f'[录制API] avatar_stream.recording 状态: {avatar_stream.recording}')
        logger.info(f'[录制API] avatar_stream 视频尺寸: width={avatar_stream.width}, height={avatar_stream.height}')
        
        if params['type'] == 'start_record':
            logger.info(f'[录制API] 开始录制 sessionid={sessionid}')
            avatar_stream.start_recording()
            logger.info(f'[录制API] start_recording 调用完成，当前 recording 状态: {avatar_stream.recording}')
            return web.Response(
                content_type="application/json",
                text=json.dumps(
                    {"code": 0, "msg": "ok"}
                ),
            )
        elif params['type'] == 'end_record':
            logger.info(f'[录制API] 停止录制 sessionid={sessionid}')
            avatar_stream.stop_recording()
            logger.info(f'[录制API] stop_recording 调用完成')
            
            response_data = {"code": 0, "msg": "ok"}
            if avatar_stream.current_record_file:
                filename = os.path.basename(avatar_stream.current_record_file)
                response_data['filename'] = filename
                response_data['filepath'] = avatar_stream.current_record_file
                logger.info(f'[录制API] 返回文件信息: {filename}')
            
            return web.Response(
                content_type="application/json",
                text=json.dumps(response_data),
            )
    except Exception as e:
        logger.exception('[录制API] 录制异常:')
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": -1, "msg": str(e)}
            ),
            status=500
        )


async def download_record(request):
    """下载录制的视频文件"""
    try:
        filename = request.match_info.get('filename', '')
        if not filename:
            return web.Response(text='文件名不能为空', status=400)
        
        # 只允许下载 records 目录下的文件
        if '..' in filename or '/' in filename or '\\' in filename:
            return web.Response(text='非法文件名', status=400)
        
        filepath = f'data/records/{filename}'
        
        if not os.path.exists(filepath):
            logger.warning(f'[下载] 文件不存在: {filepath}')
            return web.Response(text='文件不存在', status=404)
        
        logger.info(f'[下载] 开始下载文件: {filepath}')
        
        return web.FileResponse(
            path=filepath,
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"'
            }
        )
    except Exception as e:
        logger.exception('[下载] 下载异常:')
        return web.Response(text=f'下载失败: {str(e)}', status=500)
