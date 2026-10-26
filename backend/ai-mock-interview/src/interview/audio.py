"""Decode short browser recordings in memory; never persist microphone audio."""
import base64
import binascii
import io
import wave

MAX_AUDIO_BYTES = 6 * 1024 * 1024
MAX_SECONDS = 120


def normalize_recording(value):
    if not isinstance(value, str) or len(value) > MAX_AUDIO_BYTES * 4 // 3 + 100:
        raise ValueError('录音过大，请将每次录音控制在两分钟内。')
    header, separator, payload = value.partition(',')
    if not separator or header not in {f'data:audio/{kind};base64' for kind in ('webm', 'ogg', 'mp4', 'wav', 'mpeg')}:
        raise ValueError('录音格式无效，请重新录音。')
    try:
        raw = base64.b64decode(payload, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('录音数据无效，请重新录音。') from None
    if not raw or len(raw) > MAX_AUDIO_BYTES:
        raise ValueError('没有收到有效录音，请重新录音。')
    import av
    import numpy as np
    blocks, samples = [], 0
    try:
        with av.open(io.BytesIO(raw)) as source:
            resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
            for frame in source.decode(audio=0):
                for chunk in resampler.resample(frame):
                    samples += chunk.samples
                    if samples > MAX_SECONDS * 16000:
                        raise ValueError('每次录音最长两分钟，请分段回答。')
                    blocks.append(chunk.to_ndarray().reshape(-1))
            for chunk in resampler.resample(None):
                samples += chunk.samples
                blocks.append(chunk.to_ndarray().reshape(-1))
    except ValueError:
        raise
    except Exception:
        raise ValueError('无法读取录音，请检查麦克风后重新录音。') from None
    if samples > MAX_SECONDS * 16000:
        raise ValueError('每次录音最长两分钟，请分段回答。')
    if samples < 1600:
        raise ValueError('录音太短，请说完一句话后再结束。')
    pcm = np.concatenate(blocks)
    if np.sqrt(np.mean(pcm.astype(np.float64) ** 2)) < 12:
        raise ValueError('没有检测到声音，请检查麦克风是否静音或选择了正确设备。')
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(pcm.astype('<i2').tobytes())
    return 'data:audio/wav;base64,' + base64.b64encode(output.getvalue()).decode('ascii')
