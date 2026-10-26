import asyncio
import json
import random
import re
from urllib.parse import parse_qs, urljoin, urlparse

from .browser import BrowserError, browser
from .collector import Collector, UserAttention, salary_fields
from .platforms import PLATFORMS, belongs_to, is_list_api, job_identity, search_url


def text_value(data, *keys):
    for key in keys:
        value = data.get(key)
        if value is not None and isinstance(value, (str, int, float)) and str(value):
            return str(value)
    return ""


def normalize_job(platform, raw, keyword, city):
    if platform == "liepin":
        item, company, recruiter = raw.get("job") or {}, raw.get("comp") or {}, raw.get("recruiter") or {}
        result = {
            "platform_id": text_value(item, "jobId"), "title": text_value(item, "title"),
            "salary": text_value(item, "salary"), "location": text_value(item, "dq"),
            "experience": text_value(item, "requireWorkYears"), "degree": text_value(item, "requireEduLevel"),
            "company": text_value(company, "compName"), "industry": text_value(company, "compIndustry"),
            "scale": text_value(company, "compScale"), "hr_name": text_value(recruiter, "recruiterName"),
            "hr_title": text_value(recruiter, "recruiterTitle"), "url": text_value(item, "link"),
        }
    elif platform == "job51":
        result = {
            "platform_id": text_value(raw, "jobId"), "title": text_value(raw, "jobName", "jobTitle", "title"),
            "salary": text_value(raw, "provideSalaryString", "salaryDesc", "salary", "salaryText"),
            "location": text_value(raw, "jobAreaString", "cityName"),
            "experience": text_value(raw, "workYearString", "requireWorkYears"),
            "degree": text_value(raw, "degreeString", "requireEduLevel"),
            "company": text_value(raw, "fullCompanyName", "companyName", "ctmName"),
            "industry": text_value(raw, "industryType1Str", "industry"),
            "scale": text_value(raw, "companySizeString", "compScale"),
            "hr_name": text_value(raw, "hrName", "recruiterName"),
            "hr_title": text_value(raw, "hrPosition", "recruiterTitle"),
            "url": text_value(raw, "jobHref"),
        }
        if not result["url"] and result["platform_id"].isdigit():
            result["url"] = "https://we.51job.com/pc/jobdetail?jobId=" + result["platform_id"]
    else:
        result = dict(raw)
        result["platform_id"] = job_identity(platform, raw.get("url", ""))
    result["url"] = urljoin(PLATFORMS[platform]["entry_url"], result.get("url", ""))
    if not result.get("platform_id") or not result.get("title") or not job_identity(platform, result["url"]):
        raise ValueError("岗位缺少名称、标识或有效的详情链接，已跳过")
    if job_identity(platform, result["url"]) != result["platform_id"]:
        raise ValueError("岗位链接和标识不一致，已跳过")
    result.update(source=platform, keyword=keyword, city=city.name, salary_source="page" if platform == "zhilian" else "api",
                  description="", description_source="", detail_status="pending", tags=[])
    for field in ("address", "company_description", "hr_active", "stage", "industry", "scale", "hr_name", "hr_title"):
        result.setdefault(field, "")
    result.update(salary_fields(result["salary"]))
    return result


ZHILIAN_LIST = r"""() => {
    const visible = el => el && el.getClientRects().length;
    const cards = [...document.querySelectorAll('div.joblist-box__item')].filter(visible);
    const jobs = cards.map(card => {
        const text = selector => card.querySelector(selector)?.innerText?.trim() || '';
        return {title: text('a.jobinfo__name'), url: card.querySelector('a.jobinfo__name')?.href || '',
            salary: text('p.jobinfo__salary'), location: text('.jobinfo__other-info-item'),
            experience: text('.jobinfo__other-info-item:nth-child(2)'),
            degree: text('.jobinfo__other-info-item:nth-child(3)'), company: text('.companyinfo__name')};
    });
    const body = document.body?.innerText || '';
    const empty = /暂无相关职位|没有找到相关职位|暂无搜索结果|未找到相关职位/.test(body);
    return {jobs, empty, ready: document.readyState === 'complete', url: location.href};
}"""

DETAIL_SELECTORS = {
    "liepin": {"description": ".job-intro-content, .job-description, [class*='jobIntroContent']", "address": ".job-address, .job-address-text"},
    "job51": {"description": ".job_msg, .job-detail, .jobDetail, .bmsg.job_msg", "address": ".job-address, .bmsg .fp"},
    "zhilian": {"description": ".describtion__detail-content, .job-detail-des, .job-detail-description", "address": ".job-address__content, .job-address"},
}


class PlatformCollector(Collector):
    async def receive_platform_list(self, keyword, city, timeout=35):
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            self.check_stop()
            state = await browser.snapshot()
            if state.get("needs_verification") or state.get("login_required"):
                raise UserAttention("请完成网站登录或验证后继续")
            if self.config.platform == "zhilian":
                data = await self.page.evaluate(ZHILIAN_LIST)
                actual, expected = urlparse(data["url"]), urlparse(self.search_url)
                if (actual.hostname == expected.hostname and actual.path.rstrip('/') == expected.path.rstrip('/')
                        and parse_qs(actual.query).get("kw") == [keyword] and (data["jobs"] or data["empty"])):
                    return data["jobs"]
                await self.delay(0.5)
                continue
            response = await self.page.next_response(timeout=0.5)
            if not response or not is_list_api(self.config.platform, response.get("url", "")):
                continue
            if response.get("status") in (401, 403, 429):
                raise UserAttention("搜索请求被网站限制，请在浏览器处理后继续")
            if response.get("error") or response.get("status") != 200:
                raise ValueError("搜索响应无法读取，请检查当前页面")
            payload = response.get("payload")
            if not isinstance(payload, dict):
                raise ValueError("搜索响应格式已变化，已停止读取")
            message = str(payload.get("message") or payload.get("msg") or "")
            if re.search("登录|验证|频繁|限制", message):
                raise UserAttention(message[:150])
            data = payload.get("data") or {}
            if self.config.platform == "liepin":
                nested = data.get("data", data) if isinstance(data, dict) else {}
                items = nested.get("jobCardList") if isinstance(nested, dict) else None
            else:
                items = None
                for path in (("data", "items"), ("data", "jobList"), ("data", "list"), ("data", "jobs"),
                             ("resultbody", "job", "items"), ("job", "items"), ("resultbody", "items")):
                    node = payload
                    for key in path:
                        node = node.get(key) if isinstance(node, dict) else None
                    if isinstance(node, list):
                        items = node
                        break
            if not isinstance(items, list):
                raise ValueError("未识别到岗位列表字段，请检查平台页面是否改版")
            # 排除其他关键词/城市的后台预加载；仅比较接口实际包含的查询字段。
            actual = parse_qs(urlparse(response.get("request_url", "")).query)
            try:
                posted = json.loads(response.get("request_post_data") or "{}")
                if isinstance(posted, dict):
                    for name in ("data", "dataParams"):
                        if isinstance(posted.get(name), dict):
                            posted = posted[name]
                    actual.update({key: [str(value)] for key, value in posted.items() if isinstance(value, (str, int))})
            except ValueError:
                pass
            if any(actual.get(key) and actual[key][0] != keyword for key in ("key", "keyword")):
                continue
            if any(actual.get(key) and actual[key][0] != city.code for key in ("city", "dq", "jobArea")):
                continue
            return items
        raise ValueError("等待岗位列表超时，请检查网站页面；未将超时当作空结果")

    async def collect_search(self, keyword, city):
        previous_ids = None
        for page_number in range(1, self.config.max_scrolls + 1):
            if self.scanned >= self.config.max_jobs:
                break
            self.search_url = search_url(self.config, keyword, city, page_number)
            await self.progress(current_keyword=keyword, current_city=city.name,
                                message=f"{PLATFORMS[self.config.platform]['name']}：读取第 {page_number} 页")
            while True:
                try:
                    self.page = await self.navigate_search()
                    rows = await self.receive_platform_list(keyword, city)
                    break
                except (UserAttention, BrowserError, ValueError) as exc:
                    await self.attention(str(exc))
            if not rows:
                await self.log("网站明确返回空结果，本次搜索结束")
                break
            ids = set()
            for raw in rows:
                self.check_stop()
                if self.scanned >= self.config.max_jobs:
                    break
                try:
                    job = normalize_job(self.config.platform, raw, keyword, city)
                except (ValueError, TypeError, AttributeError, KeyError) as exc:
                    self.failed += 1
                    await self.log("岗位数据无法识别，已跳过", "warning")
                    continue
                ids.add(job["platform_id"])
                if job["platform_id"] in self.seen:
                    await self.record_keyword(job)
                    continue
                await self.save_job(job)
                self.pending_details.append((job, raw, city))
            await self.progress()
            await self.log(f"第 {page_number} 页读取 {len(rows)} 条，累计保存 {self.scanned} 条")
            if not ids:
                raise RuntimeError("本页岗位格式全部无法识别，请更新平台适配后重试")
            if ids == previous_ids:
                await self.log("网站返回了重复页面，结束翻页；请检查网站是否限制搜索页数", "warning")
                break
            previous_ids = ids
            await self.delay(random.uniform(self.config.delay_min, self.config.delay_max))

    async def read_detail(self, job, raw, city):
        page = await self.wait_for_login(open_page=False)
        await browser.visit_jobs(page, job["url"])
        deadline = asyncio.get_running_loop().time() + 20
        while asyncio.get_running_loop().time() < deadline:
            self.check_stop()
            state = await browser.snapshot()
            if state.get("needs_verification") or state.get("login_required"):
                raise UserAttention("详情需要登录或验证，请完成后继续")
            if job_identity(self.config.platform, page.url) == job["platform_id"] and state.get("logged_in"):
                extracted = await page.evaluate(r"""selectors => {
                    const read = selector => [...document.querySelectorAll(selector)]
                        .filter(el => el.getClientRects().length).map(el => el.innerText.trim())
                        .sort((a,b) => b.length-a.length)[0] || '';
                    return {description: read(selectors.description), address: read(selectors.address),
                        limited: /登录后查看|登录查看完整/.test(document.body?.innerText || '')};
                }""", DETAIL_SELECTORS[self.config.platform])
                if extracted["limited"]:
                    raise UserAttention("职位描述不完整，请完成登录后继续")
                if len(extracted["description"]) >= 30:
                    return {**job, "description": extracted["description"], "address": extracted["address"],
                            "description_source": "page", "detail_status": "complete"}
            await self.delay(0.5)
        raise ValueError("暂未获取完整详情，已保留岗位列表")
