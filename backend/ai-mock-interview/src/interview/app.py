"""Loopback-only interview server; cloud credentials never leave the backend.

Modified for FindBoss: identify the isolated media runtime to its parent process.
"""
import argparse
import asyncio
import json
import os
import time
from pathlib import Path
from urllib.parse import quote, urlparse

from aiohttp import web
from src.interview.service import InterviewService

ROOT = Path(__file__).resolve().parents[2]


def create_app(data_root=None, completion=None, avatar=None, transcriber=None):
    data_root = Path(data_root or ROOT / '.local')
    data_root.mkdir(parents=True, exist_ok=True)
    settings_path = data_root / 'settings.json'

    def settings():
        value = json.loads(settings_path.read_text(encoding='utf-8')) if settings_path.exists() else {}
        return {'api_key': value.get('api_key') or os.getenv('DASHSCOPE_API_KEY', ''),
                'model': value.get('model', 'qwen-plus')}

    async def cloud_complete(messages):
        from openai import AsyncOpenAI, AuthenticationError, RateLimitError, APIConnectionError, APIStatusError
        config = settings()
        if not config['api_key']:
            raise ValueError('请先展开“模型设置”，填写百炼 API Key 并保存。')
        try:
            async with AsyncOpenAI(api_key=config['api_key'],
                                   base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
                                   timeout=60, max_retries=0) as client:
                result = await client.chat.completions.create(model=config['model'],
                    messages=messages, max_tokens=2400, temperature=0.6, stream=False)
                return result.choices[0].message.content or ''
        except AuthenticationError:
            raise ValueError('百炼密钥无效或权限不足，请检查中国内地地域的 API Key。') from None
        except RateLimitError:
            raise ValueError('模型服务限流或额度不足，请检查百炼账户后重试。') from None
        except APIConnectionError:
            raise ValueError('暂时无法连接百炼，请检查网络后重试。') from None
        except APIStatusError:
            raise ValueError('百炼暂未完成请求，请检查模型名称、服务开通状态后重试。') from None

    service = InterviewService(completion or cloud_complete, data_root / 'interviews')

    from src.interview.local_asr import LocalSpeechRecognizer
    local_asr = LocalSpeechRecognizer()

    async def local_transcribe(audio):
        return await asyncio.to_thread(local_asr.recognize, audio)

    transcribing = False
    voice_cache = {}
    voice_preview_lock = asyncio.Lock()

    async def presenters(request):
        from src.interview.presenters import AVATARS, VOICES, DEFAULT_AVATAR, DEFAULT_VOICE
        return web.json_response({'avatars': AVATARS, 'voices': VOICES,
                                  'avatar_id': DEFAULT_AVATAR, 'voice_id': DEFAULT_VOICE})

    async def preview_voice(request):
        from src.interview.presenters import validate_voice
        from src.tts.speech import synthesize_speech
        from src.tts.minimax import SpeechSynthesisError
        params = await request.json()
        voice_id = validate_voice(params.get('voice_id'))
        async with voice_preview_lock:
            cached = voice_cache.get(voice_id)
            # Keep a fallback preview briefly, then give the selected online
            # voice another chance when the network has recovered.
            if cached is None or (cached[2] and time.monotonic() - cached[3] > 60):
                try:
                    audio, media_type, note = await synthesize_speech(
                        '你好，欢迎来到AI模拟面试。准备好后，我们就开始吧。', voice_id)
                    if not audio:
                        raise RuntimeError('No audio')
                    cached = (audio, media_type, note, time.monotonic())
                    voice_cache[voice_id] = cached
                except SpeechSynthesisError as error:
                    raise ValueError(str(error)) from None
                except Exception:
                    raise ValueError('语音合成暂不可用，请稍后重新试听。') from None
        audio, media_type, note, _ = cached
        headers = {'X-Speech-Notice': quote(note, safe='')} if note else {}
        if '本机离线' in note:
            headers['X-Speech-Fallback'] = 'local'
        return web.Response(body=audio, content_type=media_type, headers=headers)

    async def transcribe(request):
        nonlocal transcribing
        if transcribing:
            raise ValueError('正在识别上一段录音，请稍候。')
        transcribing = True
        try:
            from src.interview.audio import normalize_recording
            params = await request.json()
            audio = await asyncio.to_thread(normalize_recording, params.get('audio'))
            text = await (transcriber or local_transcribe)(audio)
            if not isinstance(text, str) or not text.strip():
                raise ValueError('没有识别出文字，请靠近麦克风重新录音。')
            return web.json_response({'text': text.strip()})
        finally:
            transcribing = False

    @web.middleware
    async def local_only(request, handler):
        # No CORS. Reject cross-site forms and fetches, including DNS-rebinding hosts.
        hostname = urlparse('http://' + request.host).hostname
        if hostname not in ('localhost', '127.0.0.1', '::1'):
            return web.json_response({'error': '仅允许本机访问。'}, status=403)
        origin = request.headers.get('Origin')
        if origin and origin not in ('http://' + request.host, 'http://localhost:3000', 'http://127.0.0.1:3000'):
            return web.json_response({'error': '不接受其他网站的请求。'}, status=403)
        if request.method == 'POST' and request.content_type != 'application/json':
            return web.json_response({'error': '请发送 JSON 请求。'}, status=415)
        if request.path != '/interview/transcribe' and request.content_length and request.content_length > 128 * 1024:
            return web.json_response({'error': '请求内容过大。'}, status=413)
        try:
            response = await handler(request)
            if request.path.startswith('/interview'):
                response.headers['Cache-Control'] = 'no-store'
            return response
        except (ValueError, TypeError, KeyError) as error:
            message = str(error) if isinstance(error, ValueError) else '请求内容有误，请检查输入。'
            return web.json_response({'error': message}, status=400)
        except web.HTTPException:
            raise
        except Exception:
            return web.json_response({'error': '请求未完成，请重试；记录不会因失败被覆盖。'}, status=500)

    app = web.Application(middlewares=[local_only], client_max_size=9 * 1024 * 1024)

    async def status(request):
        config = settings()
        return web.json_response({'service': 'findboss-interview-avatar',
                                  'configured': bool(config['api_key']), 'model': config['model'],
                                  'asr_mode': 'local', 'asr_model': 'SenseVoiceSmall INT8 (CPU)', 'asr_installed': local_asr.installed,
                                  'avatar_ready': bool(avatar and avatar.ready),
                                  'avatar_note': avatar.note if avatar else '口型引擎未启动，可先进行文字面试。'})

    async def save_settings(request):
        params = await request.json()
        config = settings()
        key = params.get('api_key', '').strip()
        model = params.get('model', 'qwen-plus').strip()
        if not model or len(model) > 100:
            raise ValueError('请填写有效的模型名称。')
        if len(key) > 1000:
            raise ValueError('密钥长度不正确。')
        if key:
            config['api_key'] = key
        if params.get('clear_key'):
            config['api_key'] = ''
        config['model'] = model
        temp = settings_path.with_suffix('.tmp')
        temp.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
        temp.replace(settings_path)
        return await status(request)

    async def check_model(request):
        text = await (completion or cloud_complete)([{'role': 'user', 'content': '仅回复：连接成功'}])
        return web.json_response({'ok': bool(text.strip())})

    async def start(request):
        params = await request.json()
        result = await service.start(params.get('job'), params.get('level', '中级'), params.get('limit', 6))
        return web.json_response(result)

    async def answer(request):
        params = await request.json()
        return web.json_response(await service.answer(params.get('id'), params.get('answer')))

    async def report(request):
        params = await request.json()
        return web.json_response(await service.report(params.get('id')))

    async def session(request):
        return web.json_response(service.get(request.match_info['id']))

    async def history(request):
        rows = []
        for path in sorted(service.directory.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:30]:
            value = service.get(path.stem)
            rows.append({key: value[key] for key in ('id', 'job', 'answered', 'status', 'created_at')})
        return web.json_response(rows)

    async def health(request):
        return web.json_response({'ready': bool(avatar and avatar.ready), 'interview_ready': True})

    async def legacy(request):
        if not avatar or not avatar.ready:
            return web.json_response({'error': '数字人尚未就绪，可先进行文字面试。'}, status=503)
        from src.server import routes
        route = request.path.lstrip('/')
        if route == 'offer':
            from src.server.state import state
            if avatar.connecting or len(state.avatar_streams) >= 1:
                return web.json_response({'error': '当前只支持一个数字人连接，请先断开其他页面。'}, status=409)
            avatar.connecting = True
            try:
                from src.interview.presenters import prepare_presentation
                from src.avatars.wav2lip.avatar import load_avatar
                params = await request.json()
                config, frames = await asyncio.to_thread(prepare_presentation, params, state.config, load_avatar)
                request['avatar_config'] = config
                request['avatar_data'] = frames
                return await routes.offer(request)
            finally:
                avatar.connecting = False
        if route == 'human':
            # Original chat path uses the same configured provider without logging secrets.
            from src.server.state import state
            params = await request.json()
            target = state.get_session(params.get('sessionid'))
            if not target:
                raise ValueError('数字人连接已断开，请重新连接。')
            target.flush_talk()
            text = params.get('text', '')
            if not isinstance(text, str) or not 1 <= len(text.strip()) <= 8000:
                raise ValueError('请输入有效文本。')
            if params.get('type') == 'chat':
                text = await (completion or cloud_complete)([{'role': 'user', 'content': text}])
            target.put_msg_txt(text)
            return web.json_response({'code': 0, 'response': text})
        return await getattr(routes, route)(request)

    async def index(request):
        path = ROOT / 'web/dist/index.html'
        if not path.exists():
            return web.Response(text='请先构建前端：在 web 目录运行 npm run build。', status=503)
        return web.FileResponse(path)

    app.router.add_get('/interview/status', status)
    app.router.add_get('/interview/presenters', presenters)
    app.router.add_post('/interview/voice-preview', preview_voice)
    app.router.add_post('/interview/settings', save_settings)
    app.router.add_post('/interview/check', check_model)
    app.router.add_post('/interview/transcribe', transcribe)
    app.router.add_post('/interview/start', start)
    app.router.add_post('/interview/answer', answer)
    app.router.add_post('/interview/report', report)
    app.router.add_get('/interview/session/{id}', session)
    app.router.add_get('/interview/history', history)
    app.router.add_get('/health', health)
    for route in ('offer', 'disconnect', 'human', 'interrupt_talk', 'is_speaking', 'clear_history', 'record', 'set_audiotype'):
        app.router.add_post('/' + route, legacy)
    app.router.add_get('/', index)
    if (ROOT / 'web/dist/assets').exists():
        app.router.add_static('/assets', ROOT / 'web/dist/assets')
    if (ROOT / 'web/dist/avatars').exists():
        app.router.add_static('/avatars', ROOT / 'web/dist/avatars')
    return app


class AvatarRuntime:
    def __init__(self):
        self.ready = False
        self.connecting = False
        self.note = '口型引擎正在加载。'

    def load(self):
        try:
            from src.config.loader import load_config
            from src.server.state import state
            from src.avatars.factory import prepare_avatar_model
            state.config = load_config('config/config_local.yaml')
            state.config.customopt = []
            state.model, state.avatar = prepare_avatar_model(state.config)
            state.server_ready = True
            self.ready = True
            self.note = '本地 Wav2Lip 已就绪。'
        except Exception as error:
            self.note = '口型引擎未就绪，请查看 logs/avatar-startup.log；文字面试仍可使用。'
            import traceback
            (ROOT / 'logs').mkdir(exist_ok=True)
            (ROOT / 'logs/avatar-startup.log').write_text(traceback.format_exc(), encoding='utf-8')
            print('Avatar load failed:', type(error).__name__, flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-avatar', action='store_true')
    parser.add_argument('--port', type=int, default=8010)
    args = parser.parse_args()
    os.chdir(ROOT)
    avatar = AvatarRuntime()
    if args.no_avatar:
        avatar.note = '已选择文字模式。'
    app = create_app(avatar=avatar)

    async def runtime(app):
        task = None if args.no_avatar else asyncio.create_task(asyncio.to_thread(avatar.load))
        yield
        if task:
            await task
        if avatar.ready:
            from src.server.state import state
            await asyncio.gather(*(pc.close() for pc in list(state.pcs)))

    app.cleanup_ctx.append(runtime)
    web.run_app(app, host='127.0.0.1', port=args.port, access_log=None)


if __name__ == '__main__':
    main()
