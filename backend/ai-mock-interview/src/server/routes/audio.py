"""音频相关路由"""
import json
from aiohttp import web
import asyncio

from src.llm.service import llm_response
from src.utils.logging import logger
from src.server.state import state


async def humanaudio(request):
    """处理音频文件上传"""
    try:
        form = await request.post()
        sessionid = int(form.get('sessionid', 0))
        fileobj = form["file"]
        filename = fileobj.filename
        filebytes = fileobj.file.read()
        state.avatar_streams[sessionid].put_audio_file(filebytes)

        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": 0, "msg": "ok"}
            ),
        )
    except Exception as e:
        logger.exception('exception:')
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": -1, "msg": str(e)}
            ),
        )


async def asr(request):
    """ASR 语音识别接口：将音频转换为文本，然后调用 LLM 进行对话"""
    try:
        form = await request.post()
        sessionid = int(form.get('sessionid', 0))
        fileobj = form["file"]
        filebytes = fileobj.file.read()

        # ASR/LLM 调用在同一流程中，失败时返回可读错误
        from src.asr import get_asr_engine
        
        try:
            asr_config = state.config.asr if state.config else None
            
            asr_engine = get_asr_engine(
                asr_type=asr_config.type if asr_config else "whisper",
                model_size=asr_config.model_size if asr_config else "base",
                device=asr_config.device if asr_config else "auto",
            )
            
            language = asr_config.language if asr_config else "zh"
            asr_engine.set_language(language)
            
            logger.info(f'[ASR] 开始识别音频，sessionid={sessionid}')
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, asr_engine.transcribe, filebytes)
            text = result.get("text", "").strip()
            
            if not text:
                return web.Response(
                    content_type="application/json",
                    text=json.dumps(
                        {"code": -1, "msg": "未识别到语音内容"}
                    ),
                )
            
            logger.info(f'[ASR] 识别结果: {text}')
            
            llm_config = state.config.llm if state.config else None
            logger.info(f'[ASR] LLM 配置: {llm_config}')
            avatar_stream = state.avatar_streams.get(sessionid)
            if avatar_stream is None:
                return web.Response(
                    content_type="application/json",
                    text=json.dumps(
                        {"code": -1, "msg": f"sessionid {sessionid} not found"}
                    ),
                    status=404
                )

            llm_text = await loop.run_in_executor(
                None,
                llm_response,
                text,
                avatar_stream,
                llm_config.api_key if llm_config else None,
                llm_config.base_url if llm_config else "https://dashscope.aliyuncs.com/compatible-mode/v1",
                llm_config.model if llm_config else "qwen-plus",
            )
            logger.info(f'[ASR] LLM 回复: {llm_text}')
            
            avatar_stream.put_msg_txt(llm_text)
            
            return web.Response(
                content_type="application/json",
                text=json.dumps(
                    {"code": 0, "msg": "ok", "text": text, "response": llm_text}
                ),
            )
            
        except Exception as e:
            logger.exception('[ASR] 语音识别失败:')
            return web.Response(
                content_type="application/json",
                text=json.dumps(
                    {"code": -1, "msg": f"语音识别失败: {str(e)}"}
                ),
            )
            
    except Exception as e:
        logger.exception('[ASR] ASR 接口异常:')
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": -1, "msg": str(e)}
            ),
        )
