import asyncio
import json
import logging
import random
import re
from urllib.parse import parse_qs, quote, urlencode, urlparse

from .browser import BrowserError, ENTRY_URL, VERIFY_PATHS, browser
from .database import DatabaseUnavailable, database, now
from .models import CollectionConfig
from .platforms import PLATFORMS


DETAIL_PATH = "/wapi/zpgeek/job/detail.json"
LIST_PATH = "/wapi/zpgeek/search/joblist.json"
ACTIVE_STATUSES = {"queued", "running", "waiting", "stopping"}
logger = logging.getLogger("uvicorn.error")


class UserAttention(RuntimeError):
    pass


class ResultPending(RuntimeError):
    pass


class StopCollection(Exception):
    pass


def inspect_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("岗位接口没有返回有效数据")
    code = str(payload.get("code", ""))
    message = str(payload.get("message") or payload.get("msg") or "")
    if code in ("31", "37") or any(word in message for word in ("环境存在异常", "访问频繁", "安全校验", "验证", "登录")):
        raise UserAttention(message or "请在采集浏览器中完成登录或安全验证")
    if code != "0":
        raise ValueError(f"岗位接口返回异常（代码 {code}）")
    data = payload.get("zpData")
    if not isinstance(data, dict):
        raise ValueError("岗位接口返回的数据格式不正确")
    return data


def salary_fields(text: str):
    salary = text.replace(" ", "").upper()
    unit = "unknown"
    multiplier = 1.0
    if "元/天" in salary or "元/日" in salary:
        unit = "day"
    elif "元/时" in salary or "元/小时" in salary:
        unit = "hour"
    elif "万/年" in salary:
        unit, multiplier = "year", 10000.0
    elif "K" in salary:
        unit, multiplier = "month", 1000.0
    elif "万" in salary:
        unit, multiplier = "month", 10000.0
    elif "元/月" in salary:
        unit = "month"
    if "面议" in salary:
        unit = "negotiable"
    match = re.search(r"(\d+(?:\.\d+)?)\s*[-–~至]\s*(\d+(?:\.\d+)?)", salary)
    months = re.search(r"(\d{2})薪", salary)
    return {
        "salary_min": round(float(match[1]) * multiplier, 2) if match and unit not in ("unknown", "negotiable") else None,
        "salary_max": round(float(match[2]) * multiplier, 2) if match and unit not in ("unknown", "negotiable") else None,
        "salary_unit": unit,
        "salary_months": int(months[1]) if months else (12 if unit == "month" else None),
    }


def normalize_detail(payload, keyword, city):
    data = inspect_payload(payload)
    job = data.get("jobInfo") or {}
    brand = data.get("brandComInfo") or data.get("brandInfo") or {}
    recruiter = data.get("bossInfo") or {}
    platform_id = str(job.get("encryptId") or job.get("encryptJobId") or "")
    description = str(job.get("postDescription") or "").strip()
    if not platform_id or not job.get("jobName"):
        raise ValueError("详情缺少岗位标识或名称，已跳过")
    if not description or "登录查看完整" in description:
        raise UserAttention("职位描述不完整，请在浏览器中确认登录状态后继续")
    tags = job.get("skills") or job.get("jobLabels") or []
    if not isinstance(tags, list):
        tags = [str(tags)] if tags else []
    tags = list(dict.fromkeys(str(item.get("name") or "") if isinstance(item, dict) else str(item) for item in tags))
    salary = str(job.get("salaryDesc") or "")
    result = {
        "source": "boss", "platform_id": platform_id,
        "title": str(job.get("jobName") or ""),
        "salary": salary, "salary_source": "api",
        "city": str(job.get("cityName") or city["name"]),
        "location": str(job.get("locationName") or city["name"]),
        "address": str(job.get("address") or ""),
        "experience": str(job.get("experienceName") or ""),
        "degree": str(job.get("degreeName") or ""),
        "description": description,
        "company": str(brand.get("brandName") or job.get("brandName") or ""),
        "industry": str(brand.get("industryName") or ""),
        "scale": str(brand.get("scaleName") or ""),
        "stage": str(brand.get("stageName") or ""),
        "company_description": str(brand.get("introduce") or ""),
        "hr_name": str(recruiter.get("name") or ""),
        "hr_title": str(recruiter.get("title") or ""),
        "hr_active": str(recruiter.get("activeTimeDesc") or ""),
        "tags": [tag for tag in tags if tag],
        "url": f"https://www.zhipin.com/job_detail/{platform_id}.html",
        "keyword": keyword,
    }
    result.update(salary_fields(salary))
    return result


def normalize_list_job(raw, keyword, city):
    if not isinstance(raw, dict):
        raise ValueError("列表岗位格式不正确")
    platform_id = str(raw.get("encryptJobId") or "")
    if not platform_id or not raw.get("jobName"):
        raise ValueError("列表岗位缺少标识或名称")
    salary = str(raw.get("salaryDesc") or "")
    tags = raw.get("skills") or raw.get("jobLabels") or []
    tags = tags if isinstance(tags, list) else [tags]
    job = {
        "source": "boss", "platform_id": platform_id, "title": str(raw["jobName"]),
        "salary": salary, "salary_source": "api" if salary else "api_empty",
        "city": str(raw.get("cityName") or city.name),
        "location": " · ".join(str(value) for value in (
            raw.get("cityName") or city.name, raw.get("areaDistrict"), raw.get("businessDistrict")
        ) if value),
        "experience": str(raw.get("jobExperience") or ""), "degree": str(raw.get("jobDegree") or ""),
        "company": str(raw.get("brandName") or ""), "industry": str(raw.get("brandIndustry") or ""),
        "scale": str(raw.get("brandScaleName") or ""), "stage": str(raw.get("brandStageName") or ""),
        "hr_name": str(raw.get("bossName") or ""), "hr_title": str(raw.get("bossTitle") or ""),
        "hr_active": str(raw.get("activeTimeDesc") or ("在线" if raw.get("bossOnline") else "")),
        "tags": list(dict.fromkeys(str(tag.get("name") or "") if isinstance(tag, dict) else str(tag) for tag in tags)),
        "description": "", "description_source": "", "detail_status": "pending",
        "address": "", "company_description": "", "keyword": keyword,
        "url": f"https://www.zhipin.com/job_detail/{quote(platform_id, safe='')}.html",
    }
    job.update(salary_fields(salary))
    return job


DETAIL_TEXT_SCRIPT = """() => {
    const visible = node => node && node.getClientRects().length && getComputedStyle(node).visibility !== 'hidden';
    const sections = [...document.querySelectorAll('.job-detail-section, .job-sec')];
    let description = '';
    for (const section of sections) {
        if (!visible(section) || !(section.innerText || '').includes('职位描述')) continue;
        const body = section.querySelector('.job-sec-text, .text');
        const text = (body?.innerText || section.innerText || '').trim();
        if (text.length > description.length) description = text;
    }
    return {
        description, url: location.href,
        login_required: /登录查看完整|登录后查看/.test(document.body?.innerText || ''),
        address: document.querySelector('.job-location .location-address')?.innerText?.trim() || ''
    };
}"""


class Collector:
    def __init__(self, task_id, config: CollectionConfig, stop_event, resume_event):
        self.task_id = task_id
        self.config = config
        self.stop_event = stop_event
        self.resume_event = resume_event
        self.scanned = self.saved = self.duplicates = self.failed = 0
        self.seen = set()
        self.seen_keywords = set()
        self.restriction = None
        self.pending_details = []
        self.worker = None
        self.finishing = False
        self.interrupt_requested = False
        self.waiting_for_login = True
        self.login_confirmed = False
        self.login_event = asyncio.Event()
        self.login_ready = False
        self.login_generation = 0
        self.confirmed_login = None
        self.page = None
        self.search_url = None
        self.interruption_message = "后端关闭，任务已中断，已采集岗位已保存"

    def interrupt(self, message):
        if self.interrupt_requested or self.finishing:
            return
        self.interrupt_requested = True
        self.interruption_message = message
        self.stop_event.set()
        self.resume_event.set()
        if self.worker and not self.worker.done() and not self.finishing:
            self.worker.cancel()

    async def watch_browser(self, closed_event):
        await closed_event.wait()
        self.interrupt("采集浏览器已关闭，任务已中断，已采集岗位已保存")

    async def write(self, method, *args, **values):
        pending = asyncio.create_task(asyncio.to_thread(method, *args, **values))
        try:
            return await asyncio.shield(pending)
        except asyncio.CancelledError as exc:
            # 取消页面操作时，先等待正在执行的数据库事务结束再写最终状态。
            try:
                await pending
            except Exception:
                pass
            raise exc

    async def save_job(self, job):
        self.check_stop()
        page = await self.wait_for_login(open_page=False)
        browser.require_collection(page)
        pending = asyncio.create_task(asyncio.to_thread(database.save_job, self.task_id, job))
        cancelled = None
        try:
            is_new = await asyncio.shield(pending)
        except asyncio.CancelledError as exc:
            cancelled = exc
            try:
                is_new = await pending
            except Exception:
                raise exc
        self.scanned += 1
        self.seen.add(job["platform_id"])
        self.seen_keywords.add((job["platform_id"], job.get("keyword")))
        self.saved += int(is_new)
        self.duplicates += int(not is_new)
        if cancelled is not None:
            raise cancelled
        return is_new

    async def record_keyword(self, job):
        key = (job["platform_id"], job.get("keyword"))
        if key in self.seen_keywords:
            return
        await self.write(database.record_job_keyword, self.task_id, job)
        self.seen_keywords.add(key)

    async def log(self, message, level="info"):
        await self.write(database.log, self.task_id, message, level)

    def check_stop(self):
        if self.stop_event.is_set():
            raise StopCollection()

    async def delay(self, seconds):
        self.check_stop()
        try:
            await asyncio.wait_for(self.stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return
        raise StopCollection()

    async def progress(self, **values):
        if self.stop_event.is_set() and values.get("status") in ("running", "waiting"):
            self.check_stop()
        await self.write(
            database.update_task, self.task_id,
            scanned=self.scanned, saved=self.saved, duplicates=self.duplicates,
            failed=self.failed, **values,
        )

    async def finish(self, status, message, level=None):
        try:
            if level:
                await self.log(message[:500], level)
            await self.progress(status=status, finished_at=now(), message=message[:500])
        except DatabaseUnavailable:
            # 数据库断开时仍释放浏览器监听；重连时恢复为“已中断”。
            pass

    async def attention(self, message):
        self.check_stop()
        state = await browser.snapshot()
        if state["login_required"] or (not state["logged_in"] and not state["needs_verification"]):
            await self.wait_for_login(message, open_page=False)
            return
        self.resume_event.clear()
        await self.progress(status="waiting", message=message[:500])
        await self.log(message + "；处理完成后点击“继续采集”。", "warning")
        if browser.page and not browser.page.is_closed():
            await browser.page.bring_to_front()
        while not self.resume_event.is_set():
            await self.delay(0.5)
        self.check_stop()
        state = await browser.snapshot()
        if not state["logged_in"] or state["needs_verification"]:
            await self.wait_for_login("请先完成登录或安全验证，再继续采集", open_page=False)
        self.restriction = None
        await self.progress(status="running", message="继续采集")
        await self.log("已继续采集")

    async def pause_collection_page(self):
        self.page = None
        await browser.pause_control()

    def use_collection_page(self, page):
        self.page = page

    async def login_state(self):
        # 页面加载和登录失效是不同状态；等待页面稳定时不刷新、不跳转。
        state = await browser.snapshot()
        if self.login_confirmed:
            deadline = asyncio.get_running_loop().time() + 15
            while state["open"] and state.get("checking") and asyncio.get_running_loop().time() < deadline:
                await self.delay(0.5)
                state = await browser.snapshot()
        return state

    async def wait_for_login(self, message=None, open_page=True):
        message = message or f"请在浏览器中完成{PLATFORMS[self.config.platform]['name']}登录"
        is_delivery = getattr(self.config, "mode", "collect") == "delivery"
        is_message = getattr(self.config, "delivery_action", "") == "message"
        action_label = "发送" if is_message else "投递" if is_delivery else "采集"
        confirm_label = f"我已登录，继续{action_label}"
        self.check_stop()
        state = await self.login_state()
        if self.login_confirmed and browser.collection_allowed and self.page is browser.page and state["logged_in"] and not state["needs_verification"]:
            return self.page
        if self.login_confirmed and state.get("checking"):
            message = "页面尚未就绪，请检查浏览器页面后重新确认；当前没有判定为登录失效"
        self.login_confirmed = False
        self.waiting_for_login = True
        self.login_ready = False
        self.login_generation += 1
        self.confirmed_login = None
        self.login_event.clear()
        browser.begin_login_wait()
        self.resume_event.clear()
        try:
            await self.pause_collection_page()
            await self.progress(status="waiting", message=f"等待登录完成，请登录后点击“{confirm_label}”")
            await self.log(message + f"；点击“{confirm_label}”前保持等待，不自动执行任务。", "warning")
            if open_page:
                await browser.open_login(self.config.platform)
            self.login_ready = True
            while True:
                self.check_stop()
                if not browser.is_open():
                    self.interruption_message = "采集浏览器已关闭，任务已中断，已采集岗位已保存"
                    raise asyncio.CancelledError()
                # Cookie、头像或其他标签页的状态都不能自动放行采集。
                if self.login_event.is_set():
                    self.login_event.clear()
                    confirmed_page, navigation = self.confirmed_login
                    state = await browser.confirm_login_page()
                    if (
                        state["logged_in"] and not state["needs_verification"]
                        and browser.page is confirmed_page
                        and browser.page_navigations.get(confirmed_page) == navigation
                    ):
                        break
                    await browser.pause_control()
                    await self.log(f"登录尚未完成或页面仍在加载，请完成登录后再次点击“{confirm_label}”。", "warning")
                await self.delay(0.5)
            self.check_stop()
            self.use_collection_page(confirmed_page)
            self.login_confirmed = True
            browser.collection_allowed = True
            # 只在人工确认后显示原标签页一次，让官网正常加载；不创建或切换其他标签页。
            await confirmed_page.bring_to_front()
            self.restriction = None
            self.resume_event.clear()
            await self.progress(status="running", message="登录已完成，开始发送已确认的消息" if is_message else "登录已完成，开始投递所选岗位" if is_delivery else "登录已完成，开始采集岗位")
            await self.log("已确认登录完成，继续执行任务", "success")
            return self.page
        finally:
            self.login_ready = False
            self.login_event.clear()
            self.confirmed_login = None
            self.waiting_for_login = False
            browser.end_login_wait()

    async def confirm_login(self):
        if not self.waiting_for_login or not self.login_ready:
            raise ValueError("登录浏览器尚未准备完成，请稍后再确认")
        generation = self.login_generation
        await browser.attach_for_collection()
        page = browser.page
        navigation = browser.page_navigations.get(page)
        state = await browser.confirm_login_page()
        if (
            not state["open"] or not state["logged_in"] or state["needs_verification"]
            or browser.page is not page or browser.page_navigations.get(page) != navigation
        ):
            await browser.pause_control()
            raise ValueError("当前登录页尚未完成登录或仍在跳转，请完成登录后再次确认")
        if self.stop_event.is_set() or self.finishing or not self.login_ready or self.login_generation != generation:
            raise ValueError("任务状态已变化，请刷新工作台后重试")
        self.confirmed_login = (page, navigation)
        self.login_event.set()

    def matches_list_response(self, response):
        request = urlparse(response.get("request_url") or response.get("url") or "")
        if request.hostname != "www.zhipin.com" or request.path != LIST_PATH:
            return False
        actual = parse_qs(request.query)
        post_data = response.get("request_post_data") or ""
        if post_data:
            try:
                posted = json.loads(post_data)
            except (TypeError, ValueError):
                posted = None
            if isinstance(posted, dict):
                actual.update({key: [str(value)] for key, value in posted.items() if value is not None})
            else:
                actual.update(parse_qs(post_data))
        expected = parse_qs(urlparse(self.search_url).query)
        # 接口的 page/ka 等会由官网调整；关键词和城市必须来自本次搜索。
        for key in ("query", "city"):
            if actual.get(key) != expected.get(key):
                return False
        for key in ("salary", "experience", "degree", "scale"):
            if expected.get(key) and actual.get(key) != expected[key]:
                return False
        return True

    @staticmethod
    def response_data(response):
        status = response.get("status", 200)
        if status in (401, 403, 429):
            raise UserAttention(f"岗位接口返回 HTTP {status}，请检查登录状态或完成网站提示的验证")
        if response.get("error") or status != 200:
            raise ValueError(f"职位响应未能读取（HTTP {status}），请检查浏览器中的页面")
        return inspect_payload(response.get("payload"))

    async def receive_list(self, page, timeout=35):
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            self.check_stop()
            if page is not browser.page or page.is_closed():
                raise BrowserError("采集页面连接已变化，请重新确认当前浏览器")
            if any(path in page.url for path in VERIFY_PATHS):
                raise UserAttention("搜索页面要求安全验证，请在采集浏览器中完成验证")
            response = await page.next_response(timeout=0.5)
            if response and response.get("error") and not response.get("url"):
                raise ValueError("岗位响应队列未能完整处理，请减少同时操作后继续")
            if response is None or not self.matches_list_response(response):
                continue
            data = self.response_data(response)
            if not isinstance(data.get("jobList"), list):
                raise ValueError("搜索接口没有返回 jobList 列表，不能作为空结果处理")
            return data
        path = urlparse(page.url).path
        raise ValueError(f"没有收到本次关键词和城市的职位列表响应（当前页面：{path}）")

    async def navigate_search(self):
        page = await self.wait_for_login(open_page=False)
        page.clear_responses()
        await browser.visit_jobs(page, self.search_url)
        return page

    async def collect_search(self, keyword, city):
        params = {"query": keyword, "city": city.code, "page": 1}
        for key in ("salary", "experience", "degree", "scale"):
            value = getattr(self.config, key)
            if value:
                params[key] = value
        self.search_url = ENTRY_URL + "?" + urlencode(params)
        await self.progress(current_keyword=keyword, current_city=city.name, message="等待搜索页面返回职位列表")
        await self.log(f"搜索 {city.name} · {keyword}，等待页面自身的列表响应")
        page = None
        scrolls = 0
        response_count = 0
        repeated = 0
        while self.scanned < self.config.max_jobs:
            self.check_stop()
            try:
                if page is None:
                    page = await self.navigate_search()
                data = await self.receive_list(page)
            except (UserAttention, BrowserError, ValueError) as exc:
                await self.attention(f"{exc}；已保存的数据保留。处理后继续将重新打开本次搜索")
                page = None
                scrolls = 0
                repeated = 0
                continue
            jobs = data["jobList"]
            response_count += 1
            added = 0
            for raw in jobs:
                self.check_stop()
                if self.scanned >= self.config.max_jobs:
                    break
                try:
                    job = normalize_list_job(raw, keyword, city)
                except ValueError as exc:
                    self.failed += 1
                    await self.log(str(exc), "warning")
                    continue
                if job["platform_id"] in self.seen:
                    await self.record_keyword(job)
                    continue
                await self.save_job(job)
                # lid/securityId 只在内存中用于打开对应详情页，不输出到日志或数据库。
                self.pending_details.append((job, raw, city))
                added += 1
            await self.progress(message=f"已保存 {self.scanned} 条岗位列表，稍后补充详情")
            await self.log(f"第 {response_count} 次列表响应：{len(jobs)} 条，本次保存 {added} 条")
            if not jobs or data.get("hasMore") is False or self.scanned >= self.config.max_jobs:
                if not jobs:
                    await self.log("搜索接口明确返回空列表，本次搜索结束")
                break
            repeated = repeated + 1 if added == 0 else 0
            if repeated >= 2:
                await self.log("连续列表响应没有新增岗位，结束本次搜索")
                break
            if scrolls >= self.config.max_scrolls:
                await self.log("已达到设置的最大滚动轮数，开始补充岗位详情")
                break
            await self.delay(random.uniform(self.config.delay_min, self.config.delay_max))
            page = await self.wait_for_login(open_page=False)
            browser.require_collection(page)
            try:
                await page.evaluate("""() => {
                    const root = document.scrollingElement || document.documentElement;
                    root.scrollTo(0, root.scrollHeight);
                    for (const node of document.querySelectorAll('.job-list-box, .job-list-container, .rec-job-list')) {
                        let parent = node;
                        while (parent && parent !== document.body) {
                            const style = getComputedStyle(parent);
                            if (/(auto|scroll)/.test(style.overflowY) && parent.scrollHeight > parent.clientHeight) {
                                parent.scrollTo(0, parent.scrollHeight);
                                break;
                            }
                            parent = parent.parentElement;
                        }
                    }
                }""")
                scrolls += 1
            except BrowserError:
                await self.attention("滚动加载时页面发生变化，请检查后继续")
                page = None
                scrolls = 0

    async def read_detail(self, job, raw, city):
        page = await self.wait_for_login(open_page=False)
        params = {key: str(raw[key]) for key in ("lid", "securityId") if raw.get(key)}
        url = job["url"] + (("?" + urlencode(params)) if params else "")
        page.clear_responses()
        await browser.visit_jobs(page, url)
        deadline = asyncio.get_running_loop().time() + 25
        while asyncio.get_running_loop().time() < deadline:
            self.check_stop()
            if any(path in page.url for path in VERIFY_PATHS):
                raise UserAttention("岗位详情页要求安全验证，请完成后继续")
            response = await page.next_response(timeout=0.5)
            if response and urlparse(response.get("url") or "").path == DETAIL_PATH:
                request_query = parse_qs(urlparse(response.get("request_url") or response.get("url") or "").query)
                requested_id = request_query.get("jobId") or request_query.get("encryptJobId")
                if requested_id and requested_id[0] != job["platform_id"]:
                    continue
                requested_security = request_query.get("securityId")
                if requested_security and raw.get("securityId") and requested_security[0] != str(raw["securityId"]):
                    continue
                data = self.response_data(response)
                detail = data.get("jobInfo") or {}
                if str(detail.get("encryptId") or detail.get("encryptJobId") or "") == job["platform_id"]:
                    if "登录查看完整" in str(detail.get("postDescription") or ""):
                        raise UserAttention("职位描述需要重新登录后才能完整查看")
                    if detail.get("postDescription"):
                        updated = normalize_detail(response["payload"], job["keyword"], city.model_dump())
                        result = {**job, **{key: value for key, value in updated.items() if value not in (None, "", [])}}
                        # 薪资及其结构化值统一保留列表 API 的同一组原始数据。
                        if job["salary"]:
                            for key in ("salary", "salary_source", "salary_min", "salary_max", "salary_unit", "salary_months"):
                                result[key] = job[key]
                        result.update(detail_status="complete", description_source="api")
                        return result
            try:
                state = await browser.snapshot()
                if state["login_required"]:
                    raise UserAttention("岗位详情页要求登录，请完成登录后继续")
                if not state["logged_in"]:
                    continue
                extracted = await page.evaluate(DETAIL_TEXT_SCRIPT)
            except BrowserError:
                await self.delay(0.5)
                continue
            if not isinstance(extracted, dict):
                continue
            if extracted.get("login_required"):
                raise UserAttention("职位描述被登录提示截断，请完成登录后继续")
            if urlparse(extracted.get("url") or "").path != urlparse(job["url"]).path:
                continue
            description = str(extracted.get("description") or "").strip()
            if "职位描述" in description:
                description = description.split("职位描述", 1)[1].strip()
            for marker in ("竞争力分析", "BOSS 安全提示"):
                description = description.split(marker, 1)[0].strip()
            if len(description) >= 40:
                return {**job, "description": description, "description_source": "page",
                        "address": extracted.get("address") or job.get("address", ""), "detail_status": "complete"}
        raise ValueError("详情页未提供完整职位描述，已保留岗位列表信息")

    async def collect_details(self):
        for index, (job, raw, city) in enumerate(self.pending_details, 1):
            self.check_stop()
            await self.progress(current_keyword=job["keyword"], current_city=city.name,
                                message=f"补充第 {index} / {len(self.pending_details)} 条岗位详情")
            while True:
                try:
                    updated = await self.read_detail(job, raw, city)
                    await self.write(database.save_job, self.task_id, updated)
                    await self.log(f"详情已补充 · {job['title']} · {job['company']}")
                    break
                except UserAttention as exc:
                    await self.attention(str(exc))
                except (BrowserError, ValueError):
                    self.failed += 1
                    pending = {**job, "detail_status": "unavailable"}
                    await self.write(database.save_job, self.task_id, pending)
                    await self.log(f"{job['title']}：详情暂未补全，列表数据已保存", "warning")
                    break
            await self.progress()
            if index < len(self.pending_details):
                await self.delay(random.uniform(self.config.delay_min, self.config.delay_max))

    async def execute(self):
        for city in self.config.cities:
            for keyword in self.config.keywords:
                self.check_stop()
                if self.scanned >= self.config.max_jobs:
                    break
                await self.collect_search(keyword, city)
        await self.collect_details()

    def completion_message(self):
        return (f"采集完成：新增 {self.saved}，更新 {self.duplicates}，失败 {self.failed}"
                if self.scanned else "搜索已完成，本次条件没有可保存的岗位。")

    def completion_status(self):
        return "completed"

    async def run(self):
        page = None
        browser_watcher = None
        self.worker = asyncio.current_task()
        try:
            self.check_stop()
            await self.progress(status="waiting", started_at=now(), message="等待登录完成，正在打开登录浏览器")
            await browser.open_login(self.config.platform)
            browser_watcher = asyncio.create_task(self.watch_browser(browser.closed_event))
            if not browser.is_open() or browser.closed_event.is_set():
                self.interruption_message = "采集浏览器已关闭，任务已中断，已采集岗位已保存"
                raise asyncio.CancelledError()
            page = await self.wait_for_login(open_page=False)
            await self.log(f"{PLATFORMS[self.config.platform]['name']}任务已开始")
            await self.execute()
            self.check_stop()
            self.finishing = True
            message = self.completion_message()
            status = self.completion_status()
            level = "error" if status == "failed" else "warning" if status == "partial" or not self.scanned else "success"
            await self.log(message, level)
            await self.progress(status=status, finished_at=now(), message=message)
        except StopCollection:
            self.finishing = True
            await self.finish("stopped", "任务已停止，已采集岗位已保存", "warning")
        except asyncio.CancelledError:
            self.finishing = True
            await self.finish("interrupted", self.interruption_message, "warning")
        except ResultPending as exc:
            self.finishing = True
            await self.finish("unknown", str(exc), "warning")
        except Exception as exc:
            self.finishing = True
            logger.exception("采集任务 %s 异常", self.task_id)
            if not browser.is_open() or browser.closed_event.is_set():
                await self.finish("interrupted", "采集浏览器已关闭，任务已中断，已采集岗位已保存", "warning")
            else:
                message = str(exc) if isinstance(exc, RuntimeError) else f"采集异常（{type(exc).__name__}），具体原因已记录到后端日志。"
                await self.finish("failed", message, "error")
        finally:
            self.finishing = True
            self.login_confirmed = False
            browser.collection_allowed = False
            if getattr(self.config, "mode", "collect") == "delivery":
                try:
                    await self.write(database.finalize_deliveries, self.task_id)
                except DatabaseUnavailable:
                    pass
            if browser_watcher:
                browser_watcher.cancel()
                await asyncio.gather(browser_watcher, return_exceptions=True)
            self.page = None



class TaskManager:
    def __init__(self):
        self.task_id = None
        self.worker = None
        self.stop_event = None
        self.resume_event = None
        self.collector = None
        self.lock = asyncio.Lock()

    @property
    def active(self):
        return self.worker is not None and not self.worker.done()

    async def start(self, config):
        async with self.lock:
            if self.active:
                raise ValueError("已有任务正在采集，请先停止或等待完成")
            task = await asyncio.to_thread(database.create_task, config.model_dump())
            self.task_id = task["id"]
            self.stop_event = asyncio.Event()
            self.resume_event = asyncio.Event()
            if getattr(config, "mode", "collect") == "delivery":
                if config.delivery_action == "message":
                    from .message_delivery import MessageCollector
                    collector_type = MessageCollector
                else:
                    from .delivery import DeliveryCollector
                    collector_type = DeliveryCollector
            elif config.platform != "boss":
                from .platform_collector import PlatformCollector
                collector_type = PlatformCollector
            else:
                collector_type = Collector
            collector = collector_type(self.task_id, config, self.stop_event, self.resume_event)
            self.collector = collector
            self.worker = asyncio.create_task(collector.run())
            collector.worker = self.worker
            return task

    async def stop(self, task_id):
        async with self.lock:
            if not self.active or task_id != self.task_id:
                raise ValueError("该任务当前没有运行")
            try:
                await asyncio.to_thread(database.request_stop, task_id)
            finally:
                self.stop_event.set()
                self.resume_event.set()

    async def interrupt(self, task_id, message="任务已手动中断，已采集岗位已保存"):
        async with self.lock:
            if self.active and task_id == self.task_id:
                self.collector.interrupt(message)
                await asyncio.wait({self.worker}, timeout=3)
                if not self.worker.done():
                    return
            task = await asyncio.to_thread(database.get_task, task_id)
            if task is None:
                raise ValueError("采集任务不存在")
            if task["status"] in ACTIVE_STATUSES:
                await asyncio.to_thread(database.interrupt_task, task_id, message)

    async def resume(self, task_id):
        if not self.active or task_id != self.task_id:
            raise ValueError("该任务当前没有运行")
        task = await asyncio.to_thread(database.get_task, task_id)
        if task["status"] != "waiting":
            raise ValueError("只有等待人工处理的任务可以继续")
        collector = self.collector
        resume_event = self.resume_event
        if collector.waiting_for_login:
            raise ValueError("请使用“我已登录，继续采集”确认登录，普通继续操作不能开始采集")
        state = await browser.snapshot()
        if not state["open"] or not state["logged_in"] or state["needs_verification"]:
            raise ValueError("请先在采集浏览器中完成登录或安全验证")
        if not self.active or self.collector is not collector or collector.stop_event.is_set():
            raise ValueError("该任务当前没有运行")
        resume_event.set()

    async def confirm_login(self, task_id):
        async with self.lock:
            if not self.active or task_id != self.task_id:
                raise ValueError("该任务当前没有运行")
            await self.collector.confirm_login()

    async def shutdown(self):
        if self.active:
            self.collector.interrupt("后端关闭，任务已中断，已采集岗位已保存")
            await asyncio.wait({self.worker}, timeout=5)
            if self.worker.done():
                await asyncio.gather(self.worker, return_exceptions=True)


tasks = TaskManager()
