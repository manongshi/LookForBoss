import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from .browser import browser
from .collector import ACTIVE_STATUSES, tasks
from .config import settings
from .database import DatabaseUnavailable, database, now
from .models import CollectionConfig, DeliveryConfig, DeliveryRequest, DeliveryResolution
from .models import CandidateProfile, BlacklistRule, GreetingDraft
from .job_assistant import analyze_job, blacklist_hits, greeting
from .ai_greeting import AIGenerationError, generate_greeting
from .platforms import OPTIONS, PLATFORMS, PlatformId, public_options, job_identity
from .interviews import router as interviews_router
from .interview_media import interview_runtime, router as interview_media_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(database.initialize)
    try:
        yield
    finally:
        await interview_runtime.close()
        await tasks.shutdown()
        await browser.close()


app = FastAPI(title="岗位采集工作台", version="1.0.0", lifespan=lifespan)
app.include_router(interviews_router)
app.include_router(interview_media_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key", "Last-Event-ID"],
    expose_headers=["Content-Disposition", "X-Speech-Fallback", "X-Speech-Notice"],
)


@app.middleware("http")
async def local_origin_guard(request: Request, call_next):
    origin = request.headers.get("origin")
    same_origin = (
        request.url.hostname in ("127.0.0.1", "localhost", "::1")
        and origin == str(request.base_url).rstrip("/")
    )
    if request.method not in ("GET", "HEAD", "OPTIONS") and origin and origin not in settings.allowed_origins and not same_origin:
        return JSONResponse(status_code=403, content={"detail": "该页面来源不允许操作采集服务"})
    return await call_next(request)


@app.exception_handler(DatabaseUnavailable)
async def database_error(request: Request, exc: DatabaseUnavailable):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/api/system")
async def system_status():
    statistics = None
    connected = database.ready
    message = database.message
    if connected:
        try:
            statistics = await asyncio.to_thread(database.stats)
        except DatabaseUnavailable as exc:
            connected = False
            message = str(exc)
    browser_state = await browser.snapshot()
    browser_state["waiting_for_login"] = bool(tasks.active and tasks.collector and tasks.collector.waiting_for_login)
    browser_state["login_ready"] = bool(tasks.active and tasks.collector and tasks.collector.login_ready)
    return {
        "database": {
            "connected": connected, "message": message, "type": "SQLite",
            "name": settings.database_name, "path": str(settings.database_path),
        },
        "browser": browser_state,
        "stats": statistics,
        "active_task_id": tasks.task_id if tasks.active else None,
    }


@app.post("/api/database/reconnect")
async def reconnect_database():
    if tasks.active:
        raise HTTPException(409, "请先停止当前任务，再重新连接数据库")
    return await asyncio.to_thread(database.initialize)


@app.get("/api/platforms")
def platform_options():
    return public_options()


@app.get("/api/cities")
def city_options(platform: PlatformId = "boss"):
    return OPTIONS[platform]["cities"]


@app.post("/api/browser/open")
async def open_browser(platform: PlatformId = "boss"):
    async with tasks.lock:
        if tasks.active:
            if browser.is_open() and browser.platform == platform:
                return await browser.snapshot()
            raise HTTPException(409, "当前采集浏览器已关闭，请先停止任务后重新打开")
        try:
            return await browser.open_login(platform)
        except RuntimeError as exc:
            raise HTTPException(400, str(exc)) from exc


@app.post("/api/browser/close")
async def close_browser():
    if tasks.active:
        raise HTTPException(409, "请先停止任务，再关闭采集浏览器")
    await browser.close()
    return await browser.snapshot()


@app.get("/api/tasks")
def list_tasks():
    return database.list_tasks()


@app.post("/api/tasks", status_code=201)
async def create_task(config: CollectionConfig):
    try:
        return await tasks.start(config)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/tasks/{task_id}")
def task_detail(task_id: str):
    task = database.get_task(task_id)
    if task is None:
        raise HTTPException(404, "采集任务不存在")
    return task


@app.post("/api/tasks/{task_id}/stop")
async def stop_task(task_id: str):
    try:
        await tasks.stop(task_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return await asyncio.to_thread(database.get_task, task_id)


@app.post("/api/tasks/{task_id}/resume")
async def resume_task(task_id: str):
    try:
        await tasks.resume(task_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"message": "已请求确认登录状态并继续采集"}


@app.post("/api/tasks/{task_id}/confirm-login")
async def confirm_login(task_id: str):
    try:
        await tasks.confirm_login(task_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"message": "已确认当前登录页，准备开始采集"}


@app.post("/api/tasks/{task_id}/interrupt")
async def interrupt_task(task_id: str):
    try:
        await tasks.interrupt(task_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return await asyncio.to_thread(database.get_task, task_id)


@app.get("/api/tasks/{task_id}/logs")
def task_logs(task_id: str, after: int = Query(0, ge=0)):
    return database.get_logs(task_id, after)


@app.get("/api/tasks/{task_id}/events")
async def task_events(task_id: str, request: Request):
    task = await asyncio.to_thread(database.get_task, task_id)
    if task is None:
        raise HTTPException(404, "采集任务不存在")
    try:
        last_sequence = max(0, int(request.headers.get("last-event-id", "0")))
    except ValueError:
        last_sequence = 0

    async def stream():
        nonlocal last_sequence
        while not await request.is_disconnected():
            try:
                snapshot = await asyncio.to_thread(database.get_task, task_id)
                logs = await asyncio.to_thread(database.get_logs, task_id, last_sequence)
                if logs:
                    last_sequence = logs[-1]["seq"]
                payload = json.dumps({"task": snapshot, "logs": logs}, ensure_ascii=False)
                yield f"id: {last_sequence}\nevent: snapshot\ndata: {payload}\n\n"
                if snapshot and snapshot["status"] not in ACTIVE_STATUSES and len(logs) < 200:
                    break
            except DatabaseUnavailable as exc:
                yield "event: service-error\ndata: " + json.dumps({"message": str(exc)}, ensure_ascii=False) + "\n\n"
                break
            await asyncio.sleep(2)

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/jobs/export")
def export_jobs(
    q: str = Query("", max_length=100), city: str = Query("", max_length=32),
    task_id: str = Query("", max_length=36),
    platform: str = Query("", pattern=r"^(boss|liepin|job51|zhilian)?$"),
    keyword: str = Query("", max_length=80),
):
    if not database.ready:
        raise DatabaseUnavailable(database.message)
    filename = f"jobs_{now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        database.export_csv(q, city, task_id, platform, keyword), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/analytics/jobs")
def job_distribution(
    q: str = Query("", max_length=100), city: str = Query("", max_length=32),
    platform: str = Query("", pattern=r"^(boss|liepin|job51|zhilian)?$"),
):
    return database.job_distribution(q.strip(), city, platform)


@app.get("/api/jobs/keywords")
def job_keywords(
    q: str = Query("", max_length=100), city: str = Query("", max_length=32),
    task_id: str = Query("", max_length=36),
    platform: str = Query("", pattern=r"^(boss|liepin|job51|zhilian)?$"),
):
    return database.job_keywords(q.strip(), city, task_id, platform)


@app.get("/api/jobs")
def list_jobs(
    q: str = Query("", max_length=100), city: str = Query("", max_length=32),
    task_id: str = Query("", max_length=36), page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    platform: str = Query("", pattern=r"^(boss|liepin|job51|zhilian)?$"),
    keyword: str = Query("", max_length=80),
):
    result = database.list_jobs(q.strip(), city, task_id, page, page_size, platform, keyword)
    rules = database.blacklist()
    for job in result["items"]:
        job["blacklist_hits"] = blacklist_hits(job, rules)
    return result


@app.get("/api/jobs/{job_id}")
def job_detail(job_id: str):
    job = database.get_job(job_id)
    if job is None:
        raise HTTPException(404, "岗位不存在")
    return job


@app.get("/api/messages")
def message_records(
    q: str = Query("", max_length=100),
    status: str = Query("", pattern=r"^(queued|pending|confirmed|failed|unknown|not_sent|skipped)?$"),
    platform: str = Query("", pattern=r"^(boss|liepin|job51|zhilian)?$"),
    job_id: str = Query("", max_length=64), task_id: str = Query("", max_length=36),
    date_from: date | None = None, date_to: date | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(400, "开始日期不能晚于结束日期")
    return database.list_message_records(q.strip(), status, platform, job_id, task_id, date_from, date_to, page, page_size)


@app.post("/api/deliveries", status_code=201)
async def create_delivery(request: DeliveryRequest):
    jobs = []
    for job_id in request.job_ids:
        job = await asyncio.to_thread(database.get_job, job_id)
        if job is None:
            raise HTTPException(404, "部分岗位已不存在，请刷新后重新选择")
        hits = await asyncio.to_thread(database.job_blacklist_hits, job)
        if hits:
            raise HTTPException(409, f"{job['title']} 命中黑名单：{hits[0]['value']}。请取消勾选，或到求职助手修改规则。")
        jobs.append(job)
    platforms = {job.get("source", "boss") for job in jobs}
    if len(platforms) != 1:
        raise HTTPException(400, "每次投递请选择同一平台的岗位")
    platform = platforms.pop()
    if platform not in PLATFORMS:
        raise HTTPException(400, "不支持该岗位来源")
    if request.action == "contact" and platform not in ("boss", "liepin"):
        raise HTTPException(400, "当前平台仅支持简历投递")
    if request.action == "message" and platform != "boss":
        raise HTTPException(400, "发送自定义消息目前支持 BOSS 直聘")
    if any(job_identity(platform, job["url"]) != job["platform_id"] for job in jobs):
        raise HTTPException(400, "岗位原始链接无法核对，已取消投递")
    config = DeliveryConfig(
        platform=platform, name=f"{PLATFORMS[platform]['name']} · {dict(resume='简历投递', contact='发起沟通', message='发送消息')[request.action]} · {len(jobs)} 个岗位",
        keywords=["已选岗位"], cities=[OPTIONS[platform]["cities"][0]], max_jobs=len(jobs),
        job_ids=request.job_ids, delivery_action=request.action, messages=request.messages,
        allow_repeat=request.allow_repeat, delay_min=10, delay_max=20,
    )
    try:
        return await tasks.start(config)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/jobs/{job_id}/delivery/{action}/resolve")
async def resolve_delivery(job_id: str, action: str, resolution: DeliveryResolution):
    if tasks.active:
        raise HTTPException(409, "请等待当前任务结束后再核对投递状态")
    if action not in ("resume", "contact", "message"):
        raise HTTPException(400, "不支持的投递方式")
    try:
        resolved = await asyncio.to_thread(database.resolve_delivery, job_id, action, resolution.status)
        if not resolved:
            raise ValueError("只有结果待核对的投递记录可以人工确认")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return await asyncio.to_thread(database.get_job, job_id)


@app.get("/api/assistant/profile")
def assistant_profile():
    return database.get_assistant("profile", CandidateProfile().model_dump())


@app.post("/api/assistant/profile")
def save_assistant_profile(profile: CandidateProfile):
    return database.save_assistant("profile", profile.model_dump())


@app.get("/api/assistant/blacklist")
def assistant_blacklist():
    return database.blacklist()


@app.post("/api/assistant/blacklist")
async def add_blacklist(rule: BlacklistRule):
    async with tasks.lock:
        if tasks.active:
            raise HTTPException(409, "请先停止当前任务，再修改黑名单")
        data = {**rule.model_dump(), "id": str(uuid.uuid4())}
        return await asyncio.to_thread(database.save_assistant, "blacklist:" + data["id"], data)


@app.post("/api/assistant/blacklist/{rule_id}")
async def edit_blacklist(rule_id: uuid.UUID, rule: BlacklistRule):
    async with tasks.lock:
        if tasks.active:
            raise HTTPException(409, "请先停止当前任务，再修改黑名单")
        key = "blacklist:" + str(rule_id)
        if await asyncio.to_thread(database.get_assistant, key) is None:
            raise HTTPException(404, "规则不存在")
        return await asyncio.to_thread(database.save_assistant, key, {**rule.model_dump(), "id": str(rule_id)})


@app.post("/api/assistant/blacklist/{rule_id}/delete")
async def delete_blacklist(rule_id: uuid.UUID):
    async with tasks.lock:
        if tasks.active:
            raise HTTPException(409, "请先停止当前任务，再修改黑名单")
        await asyncio.to_thread(database.delete_assistant, "blacklist:" + str(rule_id))
        return {"deleted": True}


def require_job(job_id):
    job = database.get_job(job_id)
    if job is None:
        raise HTTPException(404, "岗位不存在")
    return job


@app.get("/api/jobs/{job_id}/assistant")
def job_assistant(job_id: str):
    job = require_job(job_id)
    profile = database.get_assistant("profile", CandidateProfile().model_dump())
    analysis = analyze_job(job, profile)
    return {"analysis": analysis, "generated_text": greeting(job, profile, analysis),
            "draft": database.get_assistant("greeting:" + job_id),
            "ai": {"configured": bool(settings.minimax_api_key.get_secret_value()), "model": settings.minimax_model},
            "blacklist_hits": database.job_blacklist_hits(job)}


@app.post("/api/jobs/{job_id}/greeting/generate")
def generate_job_greeting(job_id: str):
    job = require_job(job_id)
    profile = database.get_assistant("profile", CandidateProfile().model_dump())
    try:
        text = generate_greeting(job, profile, analyze_job(job, profile))
    except AIGenerationError as exc:
        raise HTTPException(502, str(exc)) from None
    return {"text": text, "model": settings.minimax_model, "provider": "MiniMax", "generated_at": now().isoformat() + "+08:00"}


@app.post("/api/jobs/{job_id}/greeting")
def save_greeting(job_id: str, draft: GreetingDraft):
    require_job(job_id)
    return database.save_assistant("greeting:" + job_id, {"text": draft.text, "updated_at": now().isoformat() + "+08:00"})


@app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
def frontend_page(path: str):
    if path == "api" or path.startswith("api/"):
        raise HTTPException(404, "接口不存在")
    root = settings.static_path.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise HTTPException(404, "页面不存在")
    if target.is_file():
        return FileResponse(target, headers={"Cache-Control": "no-cache"} if target.name == "index.html" else None)
    if path.startswith("assets/") or "." in target.name:
        raise HTTPException(404, "资源不存在")
    index = root / "index.html"
    if not index.is_file():
        raise HTTPException(503, "前端资源尚未打包，请在 frontend 目录执行 npm run build 后重新访问")
    return FileResponse(index, headers={"Cache-Control": "no-cache"})
