from __future__ import annotations

import os

import numpy as np
import azure.cognitiveservices.speech as speechsdk

from src.tts.base import BaseTTS, State
from src.utils.logging import logger


class AzureTTS(BaseTTS):
    CHUNK_SIZE = 640  # 16kHz, 20ms, 16-bit Mono PCM size

    def __init__(self, config, parent):
        super().__init__(config, parent)
        self.audio_buffer = b""
        voicename = self.config.tts.ref_file   # 比如"zh-CN-XiaoxiaoMultilingualNeural"
        speech_key = os.getenv("AZURE_SPEECH_KEY")
        tts_region = os.getenv("AZURE_TTS_REGION")
        speech_endpoint = f"wss://{tts_region}.tts.speech.microsoft.com/cognitiveservices/websocket/v2"
        speech_config = speechsdk.SpeechConfig(subscription=speech_key, endpoint=speech_endpoint)
        speech_config.speech_synthesis_voice_name = voicename
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Raw16Khz16BitMonoPcm
        )

        # 获取内存中流形式的结果
        self.speech_synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config, audio_config=None
        )
        self.speech_synthesizer.synthesizing.connect(self._on_synthesizing)

    def txt_to_audio(self, msg: tuple[str, dict]):
        msg_text: str = msg[0]
        result = self.speech_synthesizer.speak_text(msg_text)

        # 延迟指标
        fb_latency = int(
            result.properties.get_property(
                speechsdk.PropertyId.SpeechServiceResponse_SynthesisFirstByteLatencyMs
            )
        )
        fin_latency = int(
            result.properties.get_property(
                speechsdk.PropertyId.SpeechServiceResponse_SynthesisFinishLatencyMs
            )
        )
        logger.info(
            f"azure音频生成相关：首字节延迟: {fb_latency} ms, 完成延迟: {fin_latency} ms, result_id: {result.result_id}"
        )

    # === 回调 ===
    def _on_synthesizing(self, evt: speechsdk.SpeechSynthesisEventArgs):
        if evt.result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            logger.info("SynthesizingAudioCompleted")
        elif evt.result.reason == speechsdk.ResultReason.Canceled:
            cancellation_details = evt.result.cancellation_details
            logger.info(f"Speech synthesis canceled: {cancellation_details.reason}")
            if cancellation_details.reason == speechsdk.CancellationReason.Error:
                if cancellation_details.error_details:
                    logger.info(f"Error details: {cancellation_details.error_details}")

        if self.state != State.RUNNING:
            self.audio_buffer = b""
            return

        # evt.result.audio_data 是刚到的一小段原始 PCM
        self.audio_buffer += evt.result.audio_data
        while len(self.audio_buffer) >= self.CHUNK_SIZE:
            chunk = self.audio_buffer[: self.CHUNK_SIZE]
            self.audio_buffer = self.audio_buffer[self.CHUNK_SIZE :]

            frame = (
                np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32767.0
            )
            self.parent.put_audio_frame(frame)

