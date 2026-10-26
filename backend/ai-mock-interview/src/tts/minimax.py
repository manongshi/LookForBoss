"""MiniMax cloned speech shared by interview playback and voice previews."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import uuid

import aiohttp


CLONED_VOICE = 'minimax-kobe-clone'
CACHE_DIRECTORY = Path(__file__).resolve().parents[2] / '.local/minimax-speech-cache'
MAX_RESPONSE_BYTES = 32 * 1024 * 1024


class SpeechSynthesisError(RuntimeError):
    """A speech error whose message can safely be shown in the interview UI."""


async def synthesize_minimax(text: str, cancelled=None) -> tuple[bytes, str, str]:
    api_key = os.getenv('MINIMAX_SPEECH_API_KEY', '').strip()
    voice_id = os.getenv('MINIMAX_SPEECH_VOICE_ID', '').strip()
    model = os.getenv('MINIMAX_SPEECH_MODEL', 'speech-2.8-hd').strip()
    if not api_key or not voice_id:
        raise SpeechSynthesisError('尚未配置 MiniMax 复刻音色，请检查后端语音设置。')

    def check_cancelled():
        if cancelled and cancelled():
            raise asyncio.CancelledError

    check_cancelled()
    fingerprint = json.dumps([voice_id, model, text, 'Chinese', 1, 32000], ensure_ascii=False)
    cache_path = CACHE_DIRECTORY / (hashlib.sha256(fingerprint.encode('utf-8')).hexdigest() + '.mp3')
    try:
        cached = cache_path.read_bytes()
        if cached:
            return cached, 'audio/mpeg', ''
    except OSError:
        pass

    async def generate():
        # Leave time for ordinary speech before the interview's 65-second deadline.
        timeout = aiohttp.ClientTimeout(total=20, connect=8)
        payload = {
            'model': model,
            'text': text,
            'stream': False,
            'voice_setting': {'voice_id': voice_id, 'speed': 1, 'vol': 1, 'pitch': 0},
            'audio_setting': {'sample_rate': 32000, 'bitrate': 128000, 'format': 'mp3', 'channel': 1},
            'language_boost': 'Chinese',
            'output_format': 'hex',
        }
        async with aiohttp.ClientSession(timeout=timeout) as client:
            async with client.post('https://api.minimax.cn/v1/t2a_v2',
                                   headers={'Authorization': f'Bearer {api_key}'}, json=payload) as response:
                if response.status in (401, 403):
                    raise SpeechSynthesisError('MiniMax 语音密钥无效或权限不足，请检查后端配置。')
                if response.status == 429:
                    raise SpeechSynthesisError('MiniMax 语音服务限流，请稍后重试。')
                if response.status != 200:
                    raise SpeechSynthesisError('MiniMax 语音服务暂不可用，请稍后重试。')
                raw = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    check_cancelled()
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise SpeechSynthesisError('MiniMax 返回的语音数据过大，请缩短播报内容。')
                value = json.loads(raw)
        if not isinstance(value, dict):
            raise SpeechSynthesisError('MiniMax 返回了无效的语音数据。')
        status = value.get('base_resp') or {}
        code = status.get('status_code')
        if str(code) == '1008':
            raise SpeechSynthesisError('MiniMax 复刻语音账户余额不足，暂时无法使用复刻音色。')
        if code != 0:
            raise SpeechSynthesisError(f"MiniMax 语音合成失败（错误码 {code or '未知'}），请检查账户额度和音色权限。")
        data = value.get('data') or {}
        encoded = data.get('audio')
        if not isinstance(encoded, str) or not encoded:
            raise SpeechSynthesisError('MiniMax 没有返回语音，请重新播报。')
        audio = bytes.fromhex(encoded)
        if not audio:
            raise SpeechSynthesisError('MiniMax 返回了空语音，请重新播报。')
        return audio

    synthesis = asyncio.create_task(generate())
    try:
        while not synthesis.done():
            check_cancelled()
            await asyncio.wait({synthesis}, timeout=0.1)
        audio = await synthesis
        check_cancelled()
    except (aiohttp.ClientError, asyncio.TimeoutError):
        raise SpeechSynthesisError('连接 MiniMax 语音服务超时或失败，请稍后重新播报。') from None
    except (ValueError, TypeError):
        raise SpeechSynthesisError('MiniMax 返回了无效的语音数据，请稍后重新播报。') from None
    finally:
        if not synthesis.done():
            synthesis.cancel()
        await asyncio.gather(synthesis, return_exceptions=True)

    temporary = cache_path.with_suffix(f'.{uuid.uuid4().hex}.tmp')
    try:
        CACHE_DIRECTORY.mkdir(parents=True, exist_ok=True)
        temporary.write_bytes(audio)
        temporary.replace(cache_path)
    except OSError:
        temporary.unlink(missing_ok=True)
    return audio, 'audio/mpeg', ''
