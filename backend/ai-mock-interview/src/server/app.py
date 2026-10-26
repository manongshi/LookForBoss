# Linly-Talker-Stream (https://github.com/Kedreamix/Linly-Talker-Stream). Copyright [Linly-talker-stream@kedreamix]. Apache-2.0.
# Based on LiveTalking (C) 2024 LiveTalking@lipku https://github.com/lipku/LiveTalking (Apache-2.0).

"""主启动文件"""
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
import argparse
import torch.multiprocessing as mp

from src.utils.logging import logger
from src.config.loader import load_config
from src.avatars.factory import prepare_avatar_model
from src.server.state import state
from src.server.server import create_app, run_server


def main():
    """主启动函数"""
    # 设置 multiprocessing 启动方式
    try:
        mp.set_start_method('spawn')
    except RuntimeError:
        pass
    
    # 解析命令行参数
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--config', 
        type=str, 
        default="config/config.yaml",
        help="path to config file (e.g., config/config.yaml)"
    )
    args = parser.parse_args()
    
    # 加载配置
    state.config = load_config(config_file=args.config)
    logger.info(f"已加载配置: {state.config}")
    
    # 加载自定义视频配置
    state.config.customopt = []
    if state.config.custom_video.config_path:
        with open(state.config.custom_video.config_path, 'r') as file:
            state.config.customopt = json.load(file)
    
    # 加载模型
    logger.info(f"正在加载模型类型: {state.config.model.type}")
    state.model, state.avatar = prepare_avatar_model(state.config)
    logger.info("模型加载完成")
    
    # 创建并运行应用
    app = create_app()
    run_server(app, state.config)


if __name__ == '__main__':
    main()
