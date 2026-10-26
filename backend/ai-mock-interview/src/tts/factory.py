"""TTS 工厂类

统一根据字符串类型创建不同的 TTS 引擎实例。
"""

from typing import Type

from .engines import (
    AzureTTS,
    BaseTTS,
    CosyVoiceTTS,
    CosyVoiceAPITTS,
    DoubaoTTS,
    EdgeTTS,
    FishTTS,
    IndexTTS2,
    SovitsTTS,
    TencentTTS,
    XTTS,
)

_ENGINE_MAP: dict[str, Type[BaseTTS]] = {
    "edgetts": EdgeTTS,
    "gpt-sovits": SovitsTTS,
    "xtts": XTTS,
    "cosyvoice": CosyVoiceTTS,
    "cosyvoice_api": CosyVoiceAPITTS,
    "fishtts": FishTTS,
    "tencent": TencentTTS,
    "doubao": DoubaoTTS,
    "indextts2": IndexTTS2,
    "azuretts": AzureTTS,
}


def create_tts_engine(tts_type: str, config, parent) -> BaseTTS:
    """
    根据类型创建 TTS 引擎
    """
    # 统一入口，便于扩展不同 TTS 提供方
    engine_cls = _ENGINE_MAP.get(tts_type)
    if engine_cls is None:
        raise ValueError(f"未知的 TTS 类型: {tts_type!r}")
    return engine_cls(config, parent)
