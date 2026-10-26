"""Avatar 工厂类"""
from typing import Any
from copy import deepcopy
from .base import BaseAvatar


def create_avatar(config: Any, model: Any, avatar: Any, sessionid: int) -> BaseAvatar:
    """
    根据配置创建对应的 Avatar 实例
    
    Args:
        config: 配置对象
        model: 加载的模型
        avatar: avatar 数据(帧列表、坐标等)
        sessionid: 会话 ID
    
    Returns:
        BaseAvatar: Avatar 实例
    """
    model_type = config.model.type
    # 每个 session 使用独立 config，避免并发会话互相污染（sessionid / customopt 等）
    session_config = deepcopy(config)
    session_config.sessionid = sessionid
    
    # 延迟导入，避免启动时加载全部模型依赖
    if model_type == 'wav2lip':
        from .wav2lip.avatar import Wav2LipAvatar
        return Wav2LipAvatar(session_config, model, avatar)
    elif model_type == 'musetalk':
        from .musetalk.avatar import MuseTalkAvatar
        return MuseTalkAvatar(session_config, model, avatar)
    elif model_type == 'ultralight':
        from .ultralight.avatar import UltralightAvatar
        return UltralightAvatar(session_config, model, avatar)
    elif model_type == 'ernerf':
        from .ernerf.avatar import ERNeRFAvatar
        return ERNeRFAvatar(session_config, model, avatar)
    elif model_type == 'talkinggaussian':
        from .talkinggaussian.avatar import TalkingGaussianAvatar
        return TalkingGaussianAvatar(session_config, model, avatar)
    else:
        raise ValueError(f"Unknown model type: {model_type}")


def prepare_avatar_model(config: Any):
    """
    预加载 Avatar 模型
    
    Args:
        config: 配置对象
    
    Returns:
        tuple: (model, avatar) 模型和 avatar 数据
    """
    model_type = config.model.type
    
    if model_type == 'musetalk':
        from .musetalk.avatar import load_model, load_avatar, warm_up
        model = load_model()
        avatar = load_avatar(config.model.avatar_id)
        warm_up(config.model.batch_size, model)
        return model, avatar
    elif model_type == 'wav2lip':
        from .wav2lip.avatar import load_model, load_avatar, warm_up
        model = load_model("./models/wav2lip.pth")
        avatar = load_avatar(config.model.avatar_id)
        warm_up(config.model.batch_size, model, 256)
        return model, avatar
    elif model_type == 'ultralight':
        from .ultralight.avatar import load_model, load_avatar, warm_up
        model = load_model(config)
        avatar = load_avatar(config.model.avatar_id)
        warm_up(config.model.batch_size, avatar, 160)
        return model, avatar
    elif model_type == 'ernerf':
        from .ernerf.avatar import load_model, load_avatar
        model = load_model(config)
        avatar = load_avatar(config)
        return model, avatar
    elif model_type == 'talkinggaussian':
        from .talkinggaussian.avatar import load_model, load_avatar
        model = load_model(config)
        avatar = load_avatar(config)
        return model, avatar
    else:
        raise ValueError(f"Unknown model type: {model_type}")
