"""TTS 引擎实现集中入口。

对外只需要从这里 import 对应的引擎类即可，例如：

    from src.tts.engines import EdgeTTS, SovitsTTS
"""

from src.tts.base import BaseTTS, State
from .edge import EdgeTTS
from .fish import FishTTS
from .sovits import SovitsTTS
from .cosyvoice import CosyVoiceTTS
from .cosyvoice_api import CosyVoiceAPITTS
from .tencent import TencentTTS
from .doubao import DoubaoTTS
from .indextts2 import IndexTTS2
from .xtts import XTTS
from .azure import AzureTTS

__all__ = [
    "BaseTTS",
    "State",
    "EdgeTTS",
    "FishTTS",
    "SovitsTTS",
    "CosyVoiceTTS",
    "CosyVoiceAPITTS",
    "TencentTTS",
    "DoubaoTTS",
    "IndexTTS2",
    "XTTS",
    "AzureTTS",
]
