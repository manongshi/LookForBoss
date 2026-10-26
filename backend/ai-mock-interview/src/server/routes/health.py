"""健康检查路由"""
import json
from aiohttp import web

from src.server.state import state


async def health_check(request):
    """健康检查接口，用于前端判断后端是否完全启动"""
    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {
                "code": 0, 
                "ready": state.server_ready
            }
        ),
    )
