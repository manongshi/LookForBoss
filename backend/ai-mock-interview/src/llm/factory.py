"""LLM 工厂类"""

from typing import Type

from .engines import BaseLLM, OpenAILLM

_ENGINE_MAP: dict[str, Type[BaseLLM]] = {
    "openai": OpenAILLM,
    "gpt": OpenAILLM,
    "dashscope": OpenAILLM,
    "qwen": OpenAILLM,
    "claude": OpenAILLM,
    "ollama": OpenAILLM,
    "vllm": OpenAILLM,
}


def create_llm_engine(llm_type: str = "openai", config=None, parent=None) -> BaseLLM:
    """根据类型创建 LLM 引擎"""
    engine_cls = _ENGINE_MAP.get(llm_type.lower())
    if engine_cls is None:
        raise ValueError(
            f"未知的 LLM 类型: {llm_type!r}\n"
            f"支持的类型: {', '.join(_ENGINE_MAP.keys())}"
        )
    return engine_cls(config, parent)
