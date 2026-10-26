from __future__ import annotations

import time
from typing import Iterator

import numpy as np
import requests
import resampy

from src.tts.base import BaseTTS
from src.utils.logging import logger


class XTTS(BaseTTS):
    def __init__(self, config, parent):
        super().__init__(config, parent)
        self.speaker = self.get_speaker(config.tts.ref_file, config.tts.tts_server)

    def txt_to_audio(self, msg: tuple[str, dict]):
        text, textevent = msg
        self.stream_tts(
            self.xtts(
                text,
                self.speaker,
                "zh-cn",
                self.config.tts.tts_server,
                "20",
            ),
            msg,
        )

    def get_speaker(self, ref_audio, server_url):
        files = {"wav_file": ("reference.wav", open(ref_audio, "rb"))}
        response = requests.post(f"{server_url}/clone_speaker", files=files)
        return response.json()

    def xtts(
        self, text, speaker, language, server_url, stream_chunk_size
    ) -> Iterator[bytes]:
        start = time.perf_counter()
        speaker["text"] = text
        speaker["language"] = language
        speaker["stream_chunk_size"] = stream_chunk_size
        try:
            res = requests.post(
                f"{server_url}/tts_stream",
                json=speaker,
                stream=True,
            )
            end = time.perf_counter()
            logger.info(f"xtts Time to make POST: {end-start}s")

            if res.status_code != 200:
                print("Error:", res.text)
                return

            first = True

            for chunk in res.iter_content(chunk_size=None):
                if first:
                    end = time.perf_counter()
                    logger.info(f"xtts Time to first chunk: {end-start}s")
                    first = False
                if chunk:
                    yield chunk
        except Exception as e:
            print(e)

    def stream_tts(self, audio_stream, msg: tuple[str, dict]):
        text, textevent = msg
        first = True
        last_stream = np.array([], dtype=np.float32)
        for chunk in audio_stream:
            if chunk is not None and len(chunk) > 0:
                stream = (
                    np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32767
                )
                stream = resampy.resample(
                    x=stream, sr_orig=24000, sr_new=self.sample_rate
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

