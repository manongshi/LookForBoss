from __future__ import annotations

import os
import time

import numpy as np
import resampy
import soundfile as sf

from src.tts.base import BaseTTS, State
from src.utils.logging import logger


class IndexTTS2(BaseTTS):
    def __init__(self, config, parent):
        super().__init__(config, parent)
        # IndexTTS2 配置参数
        self.server_url = config.tts.tts_server  # Gradio服务器地址
        self.ref_audio_path = config.tts.ref_file  # 参考音频文件路径
        self.max_tokens = getattr(config.tts, "max_tokens", 120)  # 最大token数

        # 初始化Gradio客户端
        try:
            from gradio_client import Client, handle_file

            self.client = Client(self.server_url)
            self.handle_file = handle_file
            logger.info(f"IndexTTS2 Gradio客户端初始化成功: {self.server_url}")
        except ImportError:
            logger.error("IndexTTS2 需要安装 gradio_client: pip install gradio_client")
            raise
        except Exception as e:
            logger.error(f"IndexTTS2 Gradio客户端初始化失败: {e}")
            raise

    def txt_to_audio(self, msg):
        text, textevent = msg
        try:
            # 先进行文本分割
            segments = self.split_text(text)
            if not segments:
                logger.error("IndexTTS2 文本分割失败")
                return

            logger.info(f"IndexTTS2 文本分割为 {len(segments)} 个片段")

            # 循环生成每个片段的音频
            for i, segment_text in enumerate(segments):
                if self.state != State.RUNNING:
                    break

                logger.info(f"IndexTTS2 正在生成第 {i+1}/{len(segments)} 段音频...")
                audio_file = self.indextts2_generate(segment_text)

                if audio_file:
                    segment_msg = (segment_text, textevent)
                    self.file_to_stream(
                        audio_file,
                        segment_msg,
                        is_first=(i == 0),
                        is_last=(i == len(segments) - 1),
                    )
                else:
                    logger.error(f"IndexTTS2 第 {i+1} 段音频生成失败")

        except Exception as e:
            logger.exception(f"IndexTTS2 txt_to_audio 错误: {e}")

    def split_text(self, text):
        """使用 IndexTTS2 API 分割文本"""
        try:
            logger.info(f"IndexTTS2 开始分割文本，长度: {len(text)}")

            result = self.client.predict(
                text=text,
                max_text_tokens_per_segment=self.max_tokens,
                api_name="/on_input_text_change",
            )

            if "value" in result and "data" in result["value"]:
                data = result["value"]["data"]
                logger.info(f"IndexTTS2 共分割为 {len(data)} 个片段")

                segments = []
                for i, item in enumerate(data):
                    序号 = item[0] + 1
                    分句内容 = item[1]
                    token数 = item[2]
                    logger.info(f"片段 {序号}: {len(分句内容)} 字符, {token数} tokens")
                    segments.append(分句内容)

                return segments
            else:
                logger.error(f"IndexTTS2 文本分割结果格式异常: {result}")
                return [text]

        except Exception as e:
            logger.exception(f"IndexTTS2 文本分割失败: {e}")
            return [text]

    def indextts2_generate(self, text):
        """调用 IndexTTS2 Gradio API 生成语音"""
        start = time.perf_counter()

        try:
            result = self.client.predict(
                emo_control_method="Same as the voice reference",
                prompt=self.handle_file(self.ref_audio_path),
                text=text,
                emo_ref_path=self.handle_file(self.ref_audio_path),
                emo_weight=0.8,
                vec1=0.5,
                vec2=0,
                vec3=0,
                vec4=0,
                vec5=0,
                vec6=0,
                vec7=0,
                vec8=0,
                emo_text="",
                emo_random=False,
                max_text_tokens_per_segment=self.max_tokens,
                param_16=True,
                param_17=0.8,
                param_18=30,
                param_19=0.8,
                param_20=0,
                param_21=3,
                param_22=10,
                param_23=1500,
                api_name="/gen_single",
            )

            end = time.perf_counter()
            logger.info(f"IndexTTS2 片段生成完成，耗时: {end-start:.2f}s")

            if "value" in result:
                audio_file = result["value"]
                return audio_file
            else:
                logger.error(f"IndexTTS2 结果格式异常: {result}")
                return None

        except Exception as e:
            logger.exception(f"IndexTTS2 API调用失败: {e}")
            return None

    def file_to_stream(self, audio_file, msg, is_first=False, is_last=False):
        """将音频文件转换为音频流"""
        text, textevent = msg

        try:
            stream, sample_rate = sf.read(audio_file)
            logger.info(f"IndexTTS2 音频文件 {sample_rate}Hz: {stream.shape}")

            stream = stream.astype(np.float32)

            if stream.ndim > 1:
                logger.info(f"IndexTTS2 音频有 {stream.shape[1]} 个声道，只使用第一个")
                stream = stream[:, 0]

            if sample_rate != self.sample_rate and stream.shape[0] > 0:
                logger.info(f"IndexTTS2 重采样: {sample_rate}Hz -> {self.sample_rate}Hz")
                stream = resampy.resample(
                    x=stream, sr_orig=sample_rate, sr_new=self.sample_rate
                )

            streamlen = stream.shape[0]
            idx = 0
            first_chunk = True

            while streamlen >= self.chunk and self.state == State.RUNNING:
                eventpoint = None

                if is_first and first_chunk:
                    eventpoint = {"status": "start", "text": text, "msgevent": textevent}
                    first_chunk = False

                self.parent.put_audio_frame(stream[idx : idx + self.chunk], eventpoint)
                idx += self.chunk
                streamlen -= self.chunk

            if is_last:
                eventpoint = {"status": "end", "text": text, "msgevent": textevent}
                self.parent.put_audio_frame(np.zeros(self.chunk, np.float32), eventpoint)

            try:
                if os.path.exists(audio_file):
                    os.remove(audio_file)
                    logger.info(f"IndexTTS2 已删除临时文件: {audio_file}")
            except Exception as e:
                logger.warning(f"IndexTTS2 删除临时文件失败: {e}")

        except Exception as e:
            logger.exception(f"IndexTTS2 音频流处理失败: {e}")

