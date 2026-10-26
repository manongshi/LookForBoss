"""全局状态管理"""
from typing import Dict, Set
from src.avatars.base import BaseAvatar
from aiortc import RTCPeerConnection


class ServerState:
    """服务器全局状态管理类"""
    
    def __init__(self):
        # 会话管理
        self.avatar_streams: Dict[int, BaseAvatar] = {}  # sessionid -> BaseAvatar
        
        # WebRTC 连接管理
        self.pcs: Set[RTCPeerConnection] = set()
        self.session_pcs = {}
        
        # 配置和模型
        self.config = None
        self.model = None
        self.avatar = None
        
        # 服务状态
        self.server_ready = False
    
    def add_session(self, sessionid: int, avatar_stream: BaseAvatar = None):
        """添加会话"""
        self.avatar_streams[sessionid] = avatar_stream
    
    def remove_session(self, sessionid: int):
        """移除会话"""
        if sessionid in self.avatar_streams:
            del self.avatar_streams[sessionid]
        self.session_pcs.pop(sessionid, None)
    
    def get_session(self, sessionid: int) -> BaseAvatar:
        """获取会话"""
        return self.avatar_streams.get(sessionid)
    
    def add_peer_connection(self, pc: RTCPeerConnection):
        """添加 WebRTC 连接"""
        self.pcs.add(pc)
    
    def remove_peer_connection(self, pc: RTCPeerConnection):
        """移除 WebRTC 连接"""
        self.pcs.discard(pc)


# 全局状态实例
state = ServerState()
