"""Speech synthesis with a bounded online request and a macOS offline fallback."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
import re
import sys
import tempfile

import edge_tts
import soundfile as sf

from src.utils.logging import logger
from src.tts.minimax import CLONED_VOICE, SpeechSynthesisError, synthesize_minimax

SPEECH_FALLBACK_NOTICE = '在线语音暂不可用，已改用本机离线语音。'
SPEECH_UNAVAILABLE = '语音合成暂不可用，请稍后点击“重播问题”重试。'
_native_voices: tuple[tuple[str, str], ...] | None = None


def _check_cancelled(cancelled: Callable[[], bool] | None) -> None:
    if cancelled and cancelled():
        raise asyncio.CancelledError


async def _run_command(args, *, timeout: float, cancelled=None) -> bytes:
    """Capture file-only synthesis and terminate it promptly on cancellation."""
    _check_cancelled(cancelled)
    process = await asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    output = asyncio.create_task(process.communicate())
    try:
        async with asyncio.timeout(timeout):
            while not output.done():
                _check_cancelled(cancelled)
                await asyncio.wait({output}, timeout=0.1)
            stdout, _ = await output
        _check_cancelled(cancelled)
        if process.returncode != 0:
            raise RuntimeError(SPEECH_UNAVAILABLE)
        return stdout
    finally:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()
        if not output.done():
            output.cancel()
        await asyncio.gather(output, return_exceptions=True)


async def _native_voice(voice: str, cancelled=None) -> str:
    global _native_voices
    if _native_voices is None:
        listing = await _run_command(['/usr/bin/say', '-v', '?'], timeout=5, cancelled=cancelled)
        installed = []
        for line in listing.decode('utf-8', errors='replace').splitlines():
            match = re.match(r'^(.*?)\s+(zh_[A-Z]{2})\s+#', line)
            if match:
                installed.append((match.group(1).strip(), match.group(2)))
        if not installed:
            raise RuntimeError(SPEECH_UNAVAILABLE)
        _native_voices = tuple(installed)
    preferred_names = ('Eddy', 'Reed') if 'Yun' in voice else ('Tingting', 'Shelley', 'Sandy')
    voices = sorted(_native_voices, key=lambda item: (
        item[1] != 'zh_CN',
        next((index for index, name in enumerate(preferred_names) if item[0].startswith(name)), len(preferred_names)),
    ))
    return voices[0][0]


async def _native_speech(text: str, voice: str, cancelled=None) -> bytes:
    if sys.platform != 'darwin' or not Path('/usr/bin/say').is_file():
        raise RuntimeError(SPEECH_UNAVAILABLE)
    native_voice = await _native_voice(voice, cancelled)
    # -o writes to a private file: nothing is played on the Mac's speakers.
    # -f keeps all text, including a leading hyphen, out of command arguments.
    with tempfile.TemporaryDirectory(prefix='findboss-speech-') as directory:
        text_path = Path(directory) / 'utterance.txt'
        audio_path = Path(directory) / 'utterance.wav'
        text_path.write_text(text, encoding='utf-8')
        await _run_command([
            '/usr/bin/say', '-v', native_voice, '-o', str(audio_path),
            '--file-format=WAVE', '--data-format=LEI16@16000', '--channels=1',
            '-f', str(text_path),
        ], timeout=30, cancelled=cancelled)
        _check_cancelled(cancelled)
        audio = audio_path.read_bytes()
        info = sf.info(BytesIO(audio))
        if not info.frames or info.samplerate != 16000 or info.channels != 1:
            raise RuntimeError(SPEECH_UNAVAILABLE)
        return audio


async def synthesize_speech(
    text: str, voice: str, cancelled: Callable[[], bool] | None = None,
) -> tuple[bytes, str, str]:
    """Return complete audio, its MIME type and an optional playback notice."""
    _check_cancelled(cancelled)
    clone_problem = ''
    if voice == CLONED_VOICE:
        try:
            return await synthesize_minimax(text, cancelled)
        except SpeechSynthesisError as error:
            clone_problem = str(error)
            voice = 'zh-CN-YunxiNeural'
            logger.warning('%s 尝试使用普通音色继续播报。', clone_problem)
    _check_cancelled(cancelled)

    async def online_speech():
        audio = []
        communicate = edge_tts.Communicate(text, voice, connect_timeout=3, receive_timeout=10)
        async for chunk in communicate.stream():
            _check_cancelled(cancelled)
            if chunk['type'] == 'audio':
                audio.append(chunk['data'])
        _check_cancelled(cancelled)
        result = b''.join(audio)
        if not result:
            raise RuntimeError(SPEECH_UNAVAILABLE)
        return result

    async def bounded_online_speech():
        synthesis = asyncio.create_task(online_speech())
        try:
            async with asyncio.timeout(12):
                while not synthesis.done():
                    _check_cancelled(cancelled)
                    await asyncio.wait({synthesis}, timeout=0.1)
                return await synthesis
        finally:
            if not synthesis.done():
                synthesis.cancel()
            await asyncio.gather(synthesis, return_exceptions=True)

    try:
        audio = await bounded_online_speech()
        notice = f'{clone_problem}已改用普通男声播报。' if clone_problem else ''
        return audio, 'audio/mpeg', notice
    except asyncio.CancelledError:
        raise
    except Exception:
        # Do not expose service URLs or reuse a partially received MP3.
        logger.warning('在线语音服务未完成合成，尝试本机离线语音')
    _check_cancelled(cancelled)
    try:
        audio = await _native_speech(text, voice, cancelled)
        notice = f'{clone_problem}已改用本机离线音色播报。' if clone_problem else SPEECH_FALLBACK_NOTICE
        return audio, 'audio/wav', notice
    except asyncio.CancelledError:
        raise
    except Exception:
        if clone_problem:
            raise SpeechSynthesisError(f'{clone_problem}普通音色也暂不可用，请稍后点击“朗读问题”重试。') from None
        raise RuntimeError(SPEECH_UNAVAILABLE) from None
