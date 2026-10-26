"""路由模块"""
from .webrtc import offer, disconnect
from .chat import human, interrupt_talk, is_speaking, clear_history
from .audio import humanaudio, asr
from .video import set_audiotype, record, download_record
from .health import health_check

__all__ = [
    'offer',
    'human',
    'interrupt_talk', 
    'is_speaking',
    'clear_history',
    'humanaudio',
    'asr',
    'set_audiotype',
    'record',
    'download_record',
    'health_check',
]
