"""LLM 服务模块"""

from typing import Optional

from src.avatars.base import BaseAvatar
from src.llm.engines import OpenAILLM
from src.utils.logging import logger
import os

_session_llm_instances = {}


def llm_response(
    message: str,
    avatar_stream: BaseAvatar,
    api_key: str = os.getenv("DASHSCOPE_API_KEY"),
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model: str = "qwen-plus"
) -> str:
    """调用 LLM 并将响应流式推送到 avatar"""
    try:
        config = getattr(avatar_stream, 'config', None)
        sessionid = getattr(avatar_stream, 'sessionid', 0)
        
        # 为每个 session 维护独立的 LLM 实例(保留对话历史)
        if sessionid not in _session_llm_instances:
            logger.info(f"Creating new LLM instance for session {sessionid}")
            _session_llm_instances[sessionid] = OpenAILLM(
                config=config,
                parent=avatar_stream,
                api_key=api_key,
                base_url=base_url,
                model=model,
                max_history=10  # 保留最近10轮对话
            )
        
        llm = _session_llm_instances[sessionid]
        return llm.generate_response(message, avatar_stream)
        
    except Exception as e:
        logger.error(f"Error in llm_response: {e}")
        raise


def clear_session_history(sessionid: int):
    """清空指定会话的对话历史"""
    if sessionid in _session_llm_instances:
        _session_llm_instances[sessionid].clear_history()
        logger.info(f"Cleared history for session {sessionid}")


def remove_session(sessionid: int):
    """删除指定会话的 LLM 实例"""
    if sessionid in _session_llm_instances:
        del _session_llm_instances[sessionid]
        logger.info(f"Removed LLM instance for session {sessionid}")


__all__ = ["llm_response", "clear_session_history", "remove_session"]
