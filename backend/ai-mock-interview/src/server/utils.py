"""服务器工具函数"""
import random
import aiohttp
from src.utils.logging import logger


def randN(N: int) -> int:
    """生成长度为 N 的随机数"""
    min_val = pow(10, N - 1)
    max_val = pow(10, N)
    return random.randint(min_val, max_val - 1)


async def post(url: str, data: str):
    """HTTP POST 请求"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as response:
                return await response.text()
    except aiohttp.ClientError as e:
        logger.info(f'Error: {e}')
