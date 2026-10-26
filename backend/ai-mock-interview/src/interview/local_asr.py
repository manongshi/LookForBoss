"""CPU-only SenseVoice inference. No network access or cloud fallback."""
import base64
import io
from pathlib import Path
import threading

MODEL_NAME = 'sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17'
MODEL_DIRECTORY = Path(__file__).resolve().parents[2] / 'models' / MODEL_NAME


def audio_segments(samples, sample_rate=16000):
    """Bound attention memory; prefer a quiet cut between 12 and 20 seconds."""
    import numpy as np
    start = 0
    maximum = sample_rate * 20
    window = sample_rate // 5
    while len(samples) - start > maximum:
        candidates = range(start + sample_rate * 12, start + maximum - window + 1, window)
        quiet = min(candidates, key=lambda pos: float(np.mean(samples[pos:pos + window] ** 2)))
        end = quiet + window // 2
        yield samples[start:end]
        start = end
    if start < len(samples):
        yield samples[start:]


class LocalSpeechRecognizer:
    def __init__(self, model_directory=None):
        self.directory = Path(model_directory or MODEL_DIRECTORY)
        self.recognizer = None
        self.lock = threading.Lock()

    @property
    def installed(self):
        return all((self.directory / name).is_file() for name in ('model.int8.onnx', 'tokens.txt'))

    def recognize(self, normalized_audio):
        # Input is an already validated mono 16kHz WAV from normalize_recording.
        with self.lock:
            if not self.installed:
                raise ValueError('本地语音模型未安装，请运行 scripts/setup-local-asr.ps1 后重试。')
            if self.recognizer is None:
                try:
                    import sherpa_onnx
                    self.recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                        model=str(self.directory / 'model.int8.onnx'),
                        tokens=str(self.directory / 'tokens.txt'),
                        num_threads=2, provider='cpu', language='auto', use_itn=True, debug=False)
                except ImportError:
                    raise ValueError('本地语音识别依赖未安装，请运行 scripts/setup-local-asr.ps1。') from None
            import soundfile as sf
            samples, rate = sf.read(io.BytesIO(base64.b64decode(normalized_audio.split(',', 1)[1])), dtype='float32')
            pieces = []
            for segment in audio_segments(samples, rate):
                stream = self.recognizer.create_stream()
                stream.accept_waveform(rate, segment)
                self.recognizer.decode_stream(stream)
                text = stream.result.text.strip()
                if text:
                    pieces.append(text)
            return ''.join(pieces)
