from __future__ import annotations

import time
from typing import Iterator

import numpy as np
import requests
import resampy

from src.tts.base import BaseTTS, State
from src.utils.logging import logger


class CosyVoiceTTS(BaseTTS):
    def txt_to_audio(self, msg: tuple[str, dict]):
        text, textevent = msg
        self.stream_tts(
            self.cosy_voice(
                text,
                self.config.tts.ref_file,
                self.config.tts.ref_text,
                "zh",
                self.config.tts.tts_server,
            ),
            msg,
        )

    def cosy_voice(
        self, text, reffile, reftext, language, server_url
    ) -> Iterator[bytes]:
        start = time.perf_counter()
        payload = {
            "tts_text": text,
            "prompt_text": reftext,
        }
        try:
            files = [
                (
                    "prompt_wav",
                    ("prompt_wav", open(reffile, "rb"), "application/octet-stream"),
                )
            ]
            res = requests.request(
                "GET",
                f"{server_url}/inference_zero_shot",
                data=payload,
                files=files,
                stream=True,
            )

            end = time.perf_counter()
            logger.info(f"cosy_voice Time to make POST: {end-start}s")

            if res.status_code != 200:
                logger.error("Error:%s", res.text)
                return

            first = True

            for chunk in res.iter_content(chunk_size=9600):  # 24K*20ms*2
                if first:
                    end = time.perf_counter()
                    logger.info(f"cosy_voice Time to first chunk: {end-start}s")
                    first = False
                if chunk and self.state == State.RUNNING:
                    yield chunk
        except Exception:
            logger.exception("cosyvoice")

    def stream_tts(self, audio_stream, msg: tuple[str, dict]):
        text, textevent = msg
        first = True
        for chunk in audio_stream:
            if chunk is not None and len(chunk) > 0:
                stream = (
                    np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32767
                )
                stream = resampy.resample(
                    x=stream, sr_orig=24000, sr_new=self.sample_rate
                )
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
        eventpoint = {"status": "end", "text": text}
        eventpoint.update(**textevent)
        self.parent.put_audio_frame(np.zeros(self.chunk, np.float32), eventpoint)

