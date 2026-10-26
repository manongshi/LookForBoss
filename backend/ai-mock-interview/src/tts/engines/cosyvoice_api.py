from __future__ import annotations

import asyncio
import json
import os
import time
import uuid

import numpy as np
import resampy
import websockets
from src.tts.base import BaseTTS, State
from src.utils.logging import logger


class CosyVoiceAPITTS(BaseTTS):
    def __init__(self, config, parent):
        super().__init__(config, parent)
        self.api_key = os.getenv('DASHSCOPE_API_KEY')
        self.uri = 'wss://dashscope.aliyuncs.com/api-ws/v1/inference/'
        self.model = 'cosyvoice-v3-flash'  # 固定使用 flash 模型
        
    def txt_to_audio(self, msg: tuple[str, dict]):
        text, textevent = msg
        asyncio.new_event_loop().run_until_complete(
            self.stream_tts(
                self.cosy_voice_stream(text),
                msg,
            )
        )

    async def cosy_voice_stream(self, text):
        """使用 WebSocket 进行流式合成"""
        voice = self.config.tts.ref_file  # 从配置获取音色
        task_id = str(uuid.uuid4())
        
        try:
            header = {"Authorization": f"bearer {self.api_key}"}
            
            async with websockets.connect(
                self.uri, extra_headers=header, ping_interval=None
            ) as ws:
                # 发送 run-task 指令
                run_task_cmd = {
                    "header": {
                        "action": "run-task",
                        "task_id": task_id,
                        "streaming": "duplex"
                    },
                    "payload": {
                        "task_group": "audio",
                        "task": "tts",
                        "function": "SpeechSynthesizer",
                        "model": self.model,
                        "parameters": {
                            "text_type": "PlainText",
                            "voice": voice,
                            "format": "pcm",
                            "sample_rate": 22050,
                            "volume": 50,
                            "rate": 1,
                            "pitch": 1,
                        },
                        "input": {}
                    }
                }
                await ws.send(json.dumps(run_task_cmd))
                
                task_started = False
                while True:
                    message = await ws.recv()
                    
                    # 处理 JSON 文本消息
                    if isinstance(message, str):
                        msg_json = json.loads(message)
                        if "header" in msg_json and "event" in msg_json["header"]:
                            event = msg_json["header"]["event"]
                            
                            if event == "task-started":
                                task_started = True
                                # 发送文本
                                continue_cmd = {
                                    "header": {
                                        "action": "continue-task",
                                        "task_id": task_id,
                                        "streaming": "duplex"
                                    },
                                    "payload": {
                                        "input": {"text": text}
                                    }
                                }
                                await ws.send(json.dumps(continue_cmd))
                                
                                # 发送结束指令
                                finish_cmd = {
                                    "header": {
                                        "action": "finish-task",
                                        "task_id": task_id,
                                        "streaming": "duplex"
                                    },
                                    "payload": {"input": {}}
                                }
                                await ws.send(json.dumps(finish_cmd))
                                
                            elif event in ["task-finished", "task-failed"]:
                                break
                    else:
                        # 处理二进制音频数据
                        if self.state == State.RUNNING:
                            yield message
                            
        except Exception:
            logger.exception("cosyvoice_api")

    async def stream_tts(self, audio_stream, msg: tuple[str, dict]):
        """流式处理音频数据"""
        text, textevent = msg
        first = True
        last_stream = np.array([], dtype=np.float32)
        
        async for chunk in audio_stream:
            if chunk is not None and len(chunk) > 0:
                stream = (
                    np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32767
                )
                stream = resampy.resample(
                    x=stream, sr_orig=22050, sr_new=self.sample_rate
                )
                stream = np.concatenate((last_stream, stream))
                streamlen = stream.shape[0]
                idx = 0
                while streamlen >= self.chunk:
                    eventpoint = {}
                    if first:
                        eventpoint = {"status": "start", "text": text}
                        eventpoint.update(**textevent)
                        first = False
                    self.parent.put_audio_frame(stream[idx : idx + self.chunk], eventpoint)
                    streamlen -= self.chunk
                    idx += self.chunk
                last_stream = stream[idx:]
                
        eventpoint = {"status": "end", "text": text}
        eventpoint.update(**textevent)
        self.parent.put_audio_frame(np.zeros(self.chunk, np.float32), eventpoint)