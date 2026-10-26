"""默认配置值"""
from .schema import Config, AppConfig, ModelConfig, TTSConfig, LLMConfig, AudioConfig, VideoConfig, CustomVideoConfig


def get_default_config() -> Config:
    """
    获取默认配置
    
    Returns:
        Config: 默认配置对象
    """
    return Config(
        app=AppConfig(
            listenport=8010,
            max_session=1
        ),
        model=ModelConfig(
            type="musetalk",
            avatar_id="avator_1",
            batch_size=16,
            model_path="./models"
        ),
        tts=TTSConfig(
            type="edgetts",
            ref_file="zh-CN-YunxiaNeural",
            ref_text=None,
            tts_server="http://127.0.0.1:9880"
        ),
        llm=LLMConfig(
            api_key="",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model="qwen-plus"
        ),
        audio=AudioConfig(
            fps=50,
            sample_rate=16000,
            l=10,
            m=8,
            r=10
        ),
        video=VideoConfig(
            width=450,
            height=450,
            fps=25
        ),
        custom_video=CustomVideoConfig(
            config_path=""
        )
    )
