"""Keep Linly's GPU/audio dependencies in their own local Python process."""
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Literal, get_args
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from .config import BACKEND_DIR, DATA_DIR, settings


router = APIRouter(prefix="/api/interviews", tags=["interview media"])
AVATARS = Literal["hr-warm", "hr-calm", "hr-senior"]
VOICES = Literal["minimax-kobe-clone", "zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural", "zh-CN-XiaoyiNeural", "zh-CN-YunjianNeural"]


class InterviewRuntime:
    def __init__(self):
        self.process = None
        self.lock = asyncio.Lock()
        # Loopback traffic must never go through a user's HTTP proxy.
        self.client = build_opener(ProxyHandler({}))

    @property
    def root(self):
        configured = settings.interview_runtime_dir.strip()
        return Path(configured).expanduser().resolve() if configured else BACKEND_DIR / "ai-mock-interview"

    @property
    def python(self):
        if settings.interview_python.strip():
            return Path(settings.interview_python).expanduser().resolve()
        return self.root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

    def request(self, route, body=None, *, timeout=8, binary=False, with_headers=False):
        request = Request(
            "http://127.0.0.1:8010" + route,
            data=None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="GET" if body is None else "POST",
        )
        try:
            with self.client.open(request, timeout=timeout) as response:
                raw = response.read(16 * 1024 * 1024 + 1)
                media_type = response.headers.get_content_type()
                local_speech = response.headers.get('X-Speech-Fallback') == 'local'
                speech_notice = response.headers.get('X-Speech-Notice', '')
            if len(raw) > 16 * 1024 * 1024:
                raise HTTPException(502, "数字人服务返回的数据过大，请重试")
            if binary:
                return (raw, media_type, local_speech, speech_notice) if with_headers else raw
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("Unexpected media response")
            if value.get("code") == -1 or value.get("error"):
                raise HTTPException(409, value.get("error") or "数字人连接已断开，请重新连接")
            return value
        except HTTPError as error:
            try:
                value = json.loads(error.read(8192))
                detail = value.get("error") if isinstance(value, dict) else None
            except (ValueError, OSError):
                detail = None
            if route == "/offer" and error.code in (400, 422, 500):
                detail = "数字人视频协商失败，请断开后重新连接"
            raise HTTPException(error.code if error.code in (400, 403, 409, 413, 415, 503) else 502,
                                detail or "数字人服务未能完成请求，请断开后重新连接") from None
        except (URLError, OSError, TimeoutError):
            raise HTTPException(503, "暂时无法连接数字人服务，请重新连接；文字面试记录仍会保留") from None
        except (ValueError, UnicodeError):
            raise HTTPException(502, "数字人服务返回格式异常，请重新连接") from None

    async def status(self):
        installed = self.python.is_file() and (self.root / "src/interview/app.py").is_file()
        speech_model = self.root / "models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
        speech_installed = all((speech_model / name).is_file() for name in ("model.int8.onnx", "tokens.txt"))
        avatar_assets = (self.root / "models/wav2lip.pth").is_file() and all(
            (self.root / "data/avatars" / name / "coords.pkl").is_file() or (
                (self.root / "assets/avatars" / f"{name}.png").is_file()
                and (self.root / "assets/avatars" / f"{name}.json").is_file()
            )
            for name in get_args(AVATARS)
        )
        try:
            value = await asyncio.to_thread(self.request, "/interview/status", timeout=1.5)
        except HTTPException:
            value = None
        recognized = bool(value and value.get("service") == "findboss-interview-avatar")
        return {
            "installed": installed,
            "running": recognized,
            "ready": bool(recognized and value.get("avatar_ready")),
            "asr_installed": bool(value.get("asr_installed")) if recognized else speech_installed,
            "avatar_assets_installed": avatar_assets,
            "note": value.get("avatar_note", "") if recognized else (
                "连接后启动本机数字人，也可以直接进行文字面试。" if installed else "尚未安装本机数字人运行环境，可先进行文字面试。"
            ),
            "port_in_use": bool(value and not recognized),
        }

    async def start(self, *, require_avatar=True):
        async with self.lock:
            current = await self.status()
            if current["ready"] or (current["running"] and not require_avatar):
                return current
            if current["port_in_use"]:
                raise HTTPException(409, "8010 端口已被其他服务占用，请关闭该服务后重新连接")
            if not current["installed"]:
                raise HTTPException(503, "尚未安装本机数字人运行环境，请先准备数字人环境，或使用文字面试")
            if require_avatar and not current["avatar_assets_installed"]:
                raise HTTPException(503, "本机数字人口型模型或人物素材尚未准备完成，可先进行文字面试或语音输入")
            if not current["running"] and (not self.process or self.process.poll() is not None):
                log_dir = DATA_DIR / "interviews"
                log_dir.mkdir(parents=True, exist_ok=True)
                env = {**os.environ, "PYTORCH_ENABLE_MPS_FALLBACK": "1", "PYTHONUNBUFFERED": "1"}
                env.update({
                    "MINIMAX_SPEECH_API_KEY": settings.minimax_speech_api_key.get_secret_value(),
                    "MINIMAX_SPEECH_VOICE_ID": settings.minimax_speech_voice_id,
                    "MINIMAX_SPEECH_MODEL": settings.minimax_speech_model,
                })
                try:
                    with (log_dir / "avatar-server.log").open("ab") as output:
                        self.process = subprocess.Popen(
                            [str(self.python), "-u", "-m", "src.interview.app", "--port", "8010"],
                            cwd=self.root, env=env, stdin=subprocess.DEVNULL,
                            stdout=output, stderr=subprocess.STDOUT,
                        )
                except OSError:
                    raise HTTPException(503, "数字人环境无法启动，请检查本机运行环境配置") from None
            deadline = time.monotonic() + 65
            while time.monotonic() < deadline:
                current = await self.status()
                if current["ready"] or (current["running"] and not require_avatar):
                    return current
                if self.process and self.process.poll() is not None:
                    raise HTTPException(503, "数字人启动失败，可查看运行目录中的 interviews/avatar-server.log；文字面试仍可使用")
                if require_avatar and current["running"] and "未就绪" in current["note"]:
                    raise HTTPException(503, current["note"])
                await asyncio.sleep(0.6)
            raise HTTPException(503, "数字人模型仍在加载，请稍后再次连接；已生成的面试题不会丢失")

    async def close(self):
        process, self.process = self.process, None
        if process and process.poll() is None:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait)


interview_runtime = InterviewRuntime()


class SessionMediaRequest(BaseModel):
    sessionid: int = Field(gt=0, le=999999999)


class SpeakRequest(SessionMediaRequest):
    text: str = Field(min_length=1, max_length=8000)


class OfferRequest(BaseModel):
    type: Literal["offer"]
    sdp: str = Field(min_length=1, max_length=200000)
    avatar_id: AVATARS = "hr-warm"
    voice_id: VOICES = "zh-CN-XiaoxiaoNeural"


class TranscribeRequest(BaseModel):
    audio: str = Field(min_length=30, max_length=8 * 1024 * 1024 + 100)


class VoiceRequest(BaseModel):
    voice_id: VOICES


@router.get("/avatar/status")
async def avatar_status():
    return await interview_runtime.status()


@router.post("/avatar/start")
async def start_avatar():
    return await interview_runtime.start()


@router.post("/avatar/offer")
async def avatar_offer(body: OfferRequest):
    await interview_runtime.start()
    return await asyncio.to_thread(interview_runtime.request, "/offer", body.model_dump(), timeout=65)


@router.post("/avatar/speak")
async def avatar_speak(body: SpeakRequest):
    return await asyncio.to_thread(interview_runtime.request, "/human", {
        "sessionid": body.sessionid, "text": body.text.strip(), "type": "echo", "interrupt": True,
    })


@router.post("/avatar/interrupt")
async def avatar_interrupt(body: SessionMediaRequest):
    return await asyncio.to_thread(interview_runtime.request, "/interrupt_talk", body.model_dump())


@router.post("/avatar/disconnect")
async def avatar_disconnect(body: SessionMediaRequest):
    return await asyncio.to_thread(interview_runtime.request, "/disconnect", body.model_dump())


@router.get("/avatar/speaking")
async def avatar_speaking(sessionid: int = Query(gt=0, le=999999999)):
    result = await asyncio.to_thread(interview_runtime.request, "/is_speaking", {"sessionid": sessionid})
    return {"speaking": bool(result.get("data")),
            "speech_error": result.get("speech_error", ""),
            "speech_note": result.get("speech_note", ""),
            "speech_pending": bool(result.get("speech_pending"))}


@router.post("/speech/transcribe")
async def transcribe(body: TranscribeRequest):
    current = await interview_runtime.status()
    if not current["running"]:
        # ASR is independent of the avatar model: an audio-only start is enough.
        await interview_runtime.start(require_avatar=False)
    return await asyncio.to_thread(interview_runtime.request, "/interview/transcribe", body.model_dump(), timeout=90)


@router.post("/speech/preview")
async def preview_voice(body: VoiceRequest):
    current = await interview_runtime.status()
    if not current["running"]:
        await interview_runtime.start(require_avatar=False)
    audio, media_type, local_speech, speech_notice = await asyncio.to_thread(
        interview_runtime.request, "/interview/voice-preview", body.model_dump(), timeout=65, binary=True, with_headers=True)
    headers = {"Cache-Control": "no-store"}
    if local_speech:
        headers['X-Speech-Fallback'] = 'local'
    if speech_notice:
        headers['X-Speech-Notice'] = speech_notice
    return Response(content=audio, media_type=media_type, headers=headers)
