"""配置加载器"""
import os
import re
import yaml
from pathlib import Path
from typing import Optional, Dict, Any
from .schema import (
    Config, AppConfig, ModelConfig, TTSConfig, ASRConfig, LLMConfig,
    AudioConfig, VideoConfig, CustomVideoConfig, ERNeRfConfig, TalkingGaussianConfig
)


def _merge_dicts(base: Dict, override: Dict) -> Dict:
    """
    深度合并两个字典
    
    Args:
        base: 基础字典
        override: 覆盖字典
    
    Returns:
        合并后的字典
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def load_yaml_config(config_file: Path) -> Dict:
    """加载 YAML 配置文件，支持环境变量插值"""
    if not config_file.exists():
        return {}
    
    with open(config_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 替换 ${VAR_NAME} 格式的环境变量，只替换存在的环境变量
    def replace_env_var(match):
        var_name = match.group(1)
        value = os.getenv(var_name)
        # 只有环境变量存在时才替换，否则保持原样
        return value if value is not None else match.group(0)
    
    content = re.sub(r'\$\{([^}]+)\}', replace_env_var, content)
    config_dict = yaml.safe_load(content) or {}
    
    return config_dict


def dict_to_config(config_dict: Dict) -> Config:
    """
    将字典转换为 Config 对象
    
    Args:
        config_dict: 配置字典
    
    Returns:
        Config 对象
    """
    app_config = AppConfig(**config_dict.get('app', {}))
    
    # 处理 model 配置
    model_dict = config_dict.get('model', {})
    
    # 如果顶层有 ernerf 配置，合并到 model.ernerf
    if 'ernerf' in config_dict:
        if 'ernerf' not in model_dict:
            model_dict['ernerf'] = {}
        # 顶层 ernerf 优先级更高
        model_dict['ernerf'] = _merge_dicts(model_dict.get('ernerf', {}), config_dict['ernerf'])
    
    # 如果顶层有 talkinggaussian 配置，合并到 model.talkinggaussian
    if 'talkinggaussian' in config_dict:
        if 'talkinggaussian' not in model_dict:
            model_dict['talkinggaussian'] = {}
        # 顶层 talkinggaussian 优先级更高
        model_dict['talkinggaussian'] = _merge_dicts(model_dict.get('talkinggaussian', {}), config_dict['talkinggaussian'])
    
    # 创建 ERNeRfConfig
    ernerf_config = ERNeRfConfig(**model_dict.get('ernerf', {}))
    
    # 创建 TalkingGaussianConfig
    talkinggaussian_config = TalkingGaussianConfig(**model_dict.get('talkinggaussian', {}))
    
    # 创建 ModelConfig
    model_dict_for_init = {k: v for k, v in model_dict.items() if k not in ['ernerf', 'talkinggaussian']}
    model_config = ModelConfig(**model_dict_for_init, ernerf=ernerf_config, talkinggaussian=talkinggaussian_config)
    
    tts_config = TTSConfig(**config_dict.get('tts', {}))
    asr_config = ASRConfig(**config_dict.get('asr', {}))
    llm_config = LLMConfig(**config_dict.get('llm', {}))
    audio_config = AudioConfig(**config_dict.get('audio', {}))
    video_config = VideoConfig(**config_dict.get('video', {}))
    custom_video_config = CustomVideoConfig(**config_dict.get('custom_video', {}))

    return Config(
        app=app_config,
        model=model_config,
        tts=tts_config,
        asr=asr_config,
        llm=llm_config,
        audio=audio_config,
        video=video_config,
        custom_video=custom_video_config,
    )


def load_config(
    config_file: Optional[str] = None,
) -> Config:
    """
    加载配置
    
    Args:
        config_file: 指定配置文件路径
    
    Returns:
        Config: 最终配置对象
    """
    from ..utils.paths import get_project_root, get_config_dir
    
    # 1. 加载默认配置（起始为空，后续逐步合并）
    config_dict = {}
    
    # 2. 加载指定的配置文件（如果有传入 --config）
    if config_file:
        config_path = Path(config_file)
        if not config_path.is_absolute():
            config_path = get_project_root() / config_path
        
        if config_path.exists():
            file_config = load_yaml_config(config_path)
            config_dict = _merge_dicts(config_dict, file_config)
    
    # 3. 如果没有指定配置文件，加载默认 config.yaml
    if not config_file:
        default_config_file = get_config_dir() / "config.yaml"
        if default_config_file.exists():
            default_config = load_yaml_config(default_config_file)
            config_dict = _merge_dicts(config_dict, default_config)
    
    # 4. 转换为 Config 对象
    config = dict_to_config(config_dict)
    
    # 处理 -O 快捷选项
    if config.model.ernerf.O:
        config.model.ernerf.fp16 = True
        config.model.ernerf.cuda_ray = True
        config.model.ernerf.exp_eye = True
    
    return config
