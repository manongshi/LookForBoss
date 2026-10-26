"""路径解析工具"""
import os
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()

# 各资源目录
MODELS_DIR = PROJECT_ROOT / "models"
DATA_DIR = PROJECT_ROOT / "data"
ASSETS_DIR = PROJECT_ROOT / "assets"
WEB_DIR = PROJECT_ROOT / "web"
CONFIG_DIR = PROJECT_ROOT / "config"


def get_project_root() -> Path:
    """获取项目根目录"""
    return PROJECT_ROOT


def get_models_dir() -> Path:
    """获取模型目录"""
    return MODELS_DIR


def get_data_dir() -> Path:
    """获取数据目录"""
    return DATA_DIR


def get_assets_dir() -> Path:
    """获取资源目录"""
    return ASSETS_DIR


def get_web_dir() -> Path:
    """获取 Web 资源目录"""
    return WEB_DIR


def get_config_dir() -> Path:
    """获取配置目录"""
    return CONFIG_DIR


def resolve_path(path: str) -> Path:
    """
    解析路径，支持相对路径和绝对路径
    
    Args:
        path: 路径字符串
    
    Returns:
        Path: 解析后的绝对路径
    """
    p = Path(path)
    if p.is_absolute():
        return p
    else:
        return (PROJECT_ROOT / p).resolve()


def ensure_dir(path: Path) -> Path:
    """
    确保目录存在，不存在则创建
    
    Args:
        path: 目录路径
    
    Returns:
        Path: 目录路径
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path
