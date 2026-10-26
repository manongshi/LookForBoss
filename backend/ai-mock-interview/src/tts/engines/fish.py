from __future__ import annotations

import time
from typing import Iterator

import numpy as np
import requests
import resampy

from src.tts.base import BaseTTS, State
from src.utils.logging import logger


class FishTTS(BaseTTS):
    def txt_to_audio(self, msg: tuple[str, dict]):
        text, textevent = msg
        self.stream_tts(
            self.fish_speech(
                text,
                self.config.tts.ref_file,
                self.config.tts.ref_text,
                "zh",
                self.config.tts.tts_server,
            ),
            msg,
        )

    def fish_speech(
        self, text, reffile, reftext, language, server_url
    ) -> Iterator[bytes]:
        start = time.perf_counter()
        req = {
            "text": text,
            "reference_id": reffile,
            "format": "wav",
            "streaming": True,
            "use_memory_cache": "on",
        }
        try:
            res = requests.post(
                f"{server_url}/v1/tts",
                json=req,
                stream=True,
                headers={
                    "content-type": "application/json",
                },
            )
            end = time.perf_counter()
            logger.info(f"fish_speech Time to make POST: {end-start}s")

            if res.status_code != 200:
                logger.error("Error:%s", res.text)
                return

            first = True

            for chunk in res.iter_content(chunk_size=17640):  # 44100*20ms*2
                if first:
                    end = time.perf_counter()
                    logger.info(f"fish_speech Time to first chunk: {end-start}s")
                    first = False
                if chunk and self.state == State.RUNNING:
                    yield chunk
        except Exception:
            logger.exception("fishtts")

    def stream_tts(self, audio_stream, msg: tuple[str, dict]):
        text, textevent = msg
        first = True
        for chunk in audio_stream:
            if chunk is not None and len(chunk) > 0:
                stream = (
                    np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32767
                )
                stream = resampy.resample(
                    x=stream, sr_orig=44100, sr_new=self.sample_rate
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

