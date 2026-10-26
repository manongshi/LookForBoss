from __future__ import annotations

# Modified for FindBoss: bound online synthesis and fall back to local macOS speech.

import asyncio
import time
from io import BytesIO

import numpy as np
import resampy
import soundfile as sf

from src.tts.base import BaseTTS, State
from src.tts.speech import synthesize_speech
from src.utils.logging import logger


class EdgeTTS(BaseTTS):
    def txt_to_audio(self, msg: tuple[str, dict]):
        text, textevent = msg
        started_at = time.monotonic()

        def cancelled():
            quit_event = getattr(self, 'quit_event', None)
            return self.state != State.RUNNING or bool(quit_event and quit_event.is_set())

        try:
            audio, _, notice = asyncio.run(synthesize_speech(text, self.config.tts.ref_file, cancelled))
        except asyncio.CancelledError:
            return
        if cancelled():
            return
        self.last_notice = notice
        stream, sample_rate = sf.read(BytesIO(audio), dtype='float32')
        if stream.ndim > 1:
            stream = stream[:, 0]
        if sample_rate != self.sample_rate and stream.size:
            stream = resampy.resample(stream, sr_orig=sample_rate, sr_new=self.sample_rate)
        if not stream.size:
            raise RuntimeError('语音合成没有返回音频，请点击“重播问题”重试。')
        # Pad the last 20 ms packet instead of truncating the end of the question.
        remainder = stream.size % self.chunk
        if remainder:
            stream = np.pad(stream, (0, self.chunk - remainder))
        logger.info('语音合成耗时 %.3fs%s', time.monotonic() - started_at, '（本机离线）' if notice else '')

        for idx in range(0, stream.size, self.chunk):
            if cancelled():
                return
            eventpoint = {}
            if idx == 0:
                eventpoint = {'status': 'start', 'text': text, **textevent}
            elif idx + self.chunk >= stream.size:
                eventpoint = {'status': 'end', 'text': text, **textevent}
            self.parent.put_audio_frame(stream[idx:idx + self.chunk], eventpoint)
