"""OpenAI 兼容的 LLM 引擎"""

from __future__ import annotations

import time
from typing import Generator, Optional

from openai import OpenAI, OpenAIError

from src.llm.base import BaseLLM
from src.utils.logging import logger


class OpenAILLM(BaseLLM):
    """OpenAI 兼容的 LLM 引擎，支持 OpenAI/DashScope/vLLM/Ollama 等"""
    
    def __init__(
        self, 
        config=None, 
        parent=None,
        api_key: str = None,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        model: str = "qwen-plus",
        max_history: int = 10  # 最大保存的对话轮次
    ):
        super().__init__(config, parent)
        
        if not api_key:
            raise ValueError("api_key is required")
        
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.max_history = max_history
        self.conversation_history = []  # 对话历史 [{'role': 'user/assistant', 'content': '...'}]
        
        logger.info(f"LLM initialized: model={self.model}, base_url={self.base_url}")
        self._client: Optional[OpenAI] = None
    
    @property
    def client(self) -> OpenAI:
        if self._client is None:
            # 延迟创建客户端，避免无效配置时提前报错
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client
    
    def add_to_history(self, role: str, content: str):
        """添加消息到对话历史"""
        self.conversation_history.append({'role': role, 'content': content})
        
        # 保持历史记录在限制范围内（保留最近的 max_history 轮对话）
        if len(self.conversation_history) > self.max_history * 2:  # *2 因为每轮有 user 和 assistant
            self.conversation_history = self.conversation_history[-self.max_history * 2:]
        
        logger.debug(f"Added to history: {role}, history length: {len(self.conversation_history)}")
    
    def clear_history(self):
        """清空对话历史"""
        self.conversation_history = []
        logger.info("Conversation history cleared")
    
    def chat_stream(
        self,
        message: str,
        system_prompt: Optional[str] = None
    ) -> Generator[str, None, None]:
        start_time = time.perf_counter()
        system_prompt = system_prompt or self.system_prompt
        
        try:
            # 添加用户消息到历史
            self.add_to_history('user', message)
            
            # 构建完整的消息列表：system + 历史对话
            messages = [{'role': 'system', 'content': system_prompt}]
            messages.extend(self.conversation_history)
            
            logger.info(f"Sending {len(messages)} messages to LLM (including system prompt and history)")
            
            # 采用 OpenAI 兼容流式接口，逐块返回内容
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                stream_options={"include_usage": True}
            )
            
            init_time = time.perf_counter()
            logger.info(f"LLM initialization time: {init_time - start_time:.3f}s")
            
            # 收集完整的响应用于添加到历史
            full_response = ""
            for chunk in completion:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    yield content
            
            # 添加助手响应到历史
            self.add_to_history('assistant', full_response)
            
        except OpenAIError as e:
            logger.error(f"LLM API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in LLM: {e}")
            raise
