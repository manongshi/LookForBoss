import asyncio
import random

from .browser import browser
from .collector import Collector, ResultPending
from .database import database
from .platforms import job_identity


# Match the selected job before clicking, and require website evidence of success.
# An uncertain click is never retried automatically.
DELIVERY_PAGE = r"""args => {
    const visible = el => {
        if (!el || !el.getClientRects().length) return false;
        for (let node = el; node; node = node.parentElement) {
            const style = getComputedStyle(node);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        }
        return true;
    };
    const text = el => (el?.innerText || '').replace(/[\u200b-\u200d\ufeff]/g, '').replace(/\s+/g, ' ').trim();
    const compact = value => String(value || '').replace(/[\s\u200b-\u200d\ufeff]/g, '');
    const body = text(document.body);
    const expected = new URL(args.url);
    const here = new URL(location.href);
    const sameJobUrl = url => url.hostname.replace(/^www\./, '') === expected.hostname.replace(/^www\./, '')
        && url.pathname === expected.pathname
        && (args.platform !== 'job51' || url.searchParams.get('jobId') === expected.searchParams.get('jobId'));
    const sameJobPage = sameJobUrl(here);
    const containsIdentity = root => {
        const value = compact(text(root));
        return Boolean(compact(args.title)) && value.includes(compact(args.title))
            && (!args.company || value.includes(compact(args.company)));
    };
    const matchesJob = root => containsIdentity(root) || [...root.querySelectorAll('a[href]')].filter(visible).some(el => {
        try { return sameJobUrl(new URL(el.href, location.href)); } catch { return false; }
    });
    const notices = [...document.querySelectorAll('[role="alert"], .el-message, .ant-message, .toast, .successContent, .deliver-dialog, .el-dialog__body')]
        .filter(visible).map(text).join('\n');
    const blocked = body.match(/今日[^。\n]{0,50}(?:上限|用完)|投递[^。\n]{0,30}上限|操作频繁|访问频繁|请完成验证|请按住滑块/);
    if (blocked) return {state: 'blocked', message: `官网提示：${blocked[0]}`};
    const conversations = [...document.querySelectorAll('.chat-conversation, .chat-container, .chat-window, .chat-detail, .chat-detail-container, .chat-im, .im-chat, .__im_basic__window, .__im_basic__container')]
        .filter(visible).filter(el => !el.closest('.chat-list, .conversation-list, .user-list, .friend-list'))
        .filter(el => {
            const headers = [...el.querySelectorAll('.chat-header, .chat-head, .chat-info, .chat-job, .chat-job-info, .chat-job-card, .job-info')].filter(visible);
            return headers.length ? headers.some(matchesJob) : matchesJob(el);
        }).filter((el, index, all) => !all.some(other => other !== el && el.contains(other)));
    const buttons = root => [...root.querySelectorAll('button, a, [role="button"], .btn, .btn-startchat, .btn-resume, .apply-btn, .btn-apply, .p_but, .chat-btn, .talk-btn, .contact-btn')]
        .filter(visible).filter(el => !el.disabled && el.getAttribute('aria-disabled') !== 'true')
        .filter(el => !el.closest('.job-card, .job-card-wrapper, .recommend-list, .recommend-job, .joblist-box__item'))
        .filter((el, index, all) => !all.some(other => other !== el && el.contains(other) && compact(text(el)) === compact(text(other))));
    const contactLabels = ['立即沟通', '聊一聊', '立即聊聊'];
    const existingContactLabels = ['继续沟通', '继续聊天', '已沟通'];
    const resumeLabels = ['投递简历', '立即投递', '申请职位', '立即申请', '发送简历'];
    const existingResumeLabels = ['已投递', '已申请', '已发送简历'];
    const pageButtons = buttons(document);
    const jobVerified = sameJobPage && containsIdentity(document.body);
    const existingLabels = args.action === 'contact' ? existingContactLabels : existingResumeLabels;
    const existing = jobVerified ? pageButtons.filter(el => existingLabels.includes(compact(text(el)))) : [];
    if (args.phase === 'prepare') {
        if (!sameJobPage) return {state: 'loading', message: '页面未停留在所选职位，尚未点击'};
        if (!containsIdentity(document.body)) return {state: 'loading', message: '页面职位名称或公司与所选记录不一致，尚未点击'};
        if (args.action !== 'message' && existing.length === 1) return {state: 'already', message: `官网显示“${text(existing[0])}”，${args.action === 'contact' ? '该职位已建立沟通' : '该职位已投递'}`};
        const labels = args.action === 'message' ? [...contactLabels, ...existingContactLabels] : args.action === 'contact' ? contactLabels : resumeLabels;
        let candidates = pageButtons.filter(el => labels.includes(compact(text(el))));
        let kind = args.action;
        if (!candidates.length && args.action === 'resume' && ['boss', 'liepin'].includes(args.platform)) {
            candidates = pageButtons.filter(el => [...contactLabels, ...existingContactLabels].includes(compact(text(el))));
            kind = 'contact_then_resume';
        }
        if (candidates.length !== 1) {
            const labelsFound = [...new Set(pageButtons.map(el => compact(text(el))).filter(value => [...contactLabels, ...existingContactLabels, ...resumeLabels, ...existingResumeLabels].includes(value)))];
            return {state: 'unavailable', message: candidates.length > 1
                ? `发现 ${candidates.length} 个操作入口，无法唯一核对，尚未点击`
                : `未找到可用的${args.action === 'resume' ? '简历投递' : '沟通'}入口${labelsFound.length ? `（页面显示：${labelsFound.join('、')}）` : ''}，尚未点击`};
        }
        if (args.click) { candidates[0].click(); return {state: 'clicked', kind}; }
        return {state: 'ready', kind};
    }
    if (args.phase === 'result') {
        if (existing.length === 1) return {state: 'success', message: `官网已显示“${text(existing[0])}”`};
        if (args.action === 'contact' && conversations.length === 1)
            return {state: 'success', message: '已打开与所选职位匹配的沟通窗口'};
        if (args.action === 'resume' && (jobVerified || conversations.length === 1)
            && /投递成功|申请成功|简历发送成功|简历已发送/.test(notices) && !/成功\s*0|未投递|失败/.test(notices))
            return {state: 'success', message: notices.slice(0, 200)};
        return {state: 'waiting', message: args.action === 'contact'
            ? '已点击沟通，但尚未识别到该职位的沟通状态或匹配的聊天窗口'
            : '已点击投递，但尚未识别到该职位的简历发送成功提示'};
    }
    if (args.phase === 'send_resume' && conversations.length === 1) {
        const candidates = buttons(conversations[0]).filter(el => ['发送简历', '投递简历'].includes(compact(text(el))));
        if (candidates.length === 1) { candidates[0].click(); return {state: 'clicked'}; }
    }
    if (args.phase === 'confirm') {
        if (!jobVerified && conversations.length !== 1) return {state: 'waiting'};
        const dialogs = [...document.querySelectorAll('[role="dialog"], .dialog-container, .el-dialog, .ant-modal-content')]
            .filter(visible).filter(el => /简历/.test(text(el)) && /发送|投递|申请/.test(text(el))
                && !/完善简历|上传简历|选择简历|选择.*附件/.test(text(el)));
        if (dialogs.length === 1) {
            const choices = buttons(dialogs[0]).filter(el => /^(确定|确认|发送|确认发送|确认投递|立即投递)$/.test(compact(text(el))));
            if (choices.length === 1) { choices[0].click(); return {state: 'clicked'}; }
        }
    }
    return {state: 'waiting'};
}"""


class DeliveryCollector(Collector):
    def completion_status(self):
        if self.failed:
            return "partial" if self.saved else "failed"
        return "completed"

    def completion_message(self):
        action = "沟通" if self.config.delivery_action == "contact" else "投递"
        message = f"{action}任务结束：网站确认 {self.saved}，跳过 {self.duplicates}，未完成 {self.failed}"
        if self.failure_messages:
            message += f"；最近未完成：{self.failure_messages[-1]}"
        elif self.duplicates and not self.saved:
            message += "；跳过原因见任务日志，待核对记录不会自动重发"
        return message[:500]

    async def execute(self):
        self.failure_messages = []
        for index, job_id in enumerate(self.config.job_ids, 1):
            self.check_stop()
            job = await asyncio.to_thread(database.get_job, job_id)
            if not job or job.get("source", "boss") != self.config.platform:
                raise RuntimeError("职位不存在或平台不一致，投递任务已停止")
            hits = await asyncio.to_thread(database.job_blacklist_hits, job)
            if hits:
                self.scanned += 1
                self.duplicates += 1
                await self.log(f"跳过 {job['title']}：命中黑名单「{hits[0]['value']}」", "warning")
                await self.progress()
                continue
            if job_identity(self.config.platform, job["url"]) != job["platform_id"]:
                raise RuntimeError("职位详情链接无法核对，投递任务已停止")
            await self.progress(current_keyword=job["title"], current_city=job["city"],
                                message=f"准备处理 {index}/{len(self.config.job_ids)}：{job['title']} · {job['company']}")
            page = await self.wait_for_login(open_page=False)
            await browser.visit_jobs(page, job["url"])
            args = {"platform": self.config.platform, "title": job["title"], "company": job["company"], "url": job["url"],
                    "action": self.config.delivery_action, "phase": "prepare", "click": False}
            ready = None
            deadline = asyncio.get_running_loop().time() + 25
            while asyncio.get_running_loop().time() < deadline:
                self.check_stop()
                state = await browser.snapshot()
                if state.get("login_required") or state.get("needs_verification"):
                    raise RuntimeError("网站需要重新登录或验证，当前职位尚未发送，请处理后重新创建投递任务")
                if job_identity(self.config.platform, page.url) == job["platform_id"] and state.get("logged_in"):
                    ready = await page.evaluate(DELIVERY_PAGE, args)
                    if ready["state"] in ("ready", "already", "blocked"):
                        break
                await self.delay(0.5)
            self.scanned += 1
            if ready and ready["state"] == "already":
                recorded = await self.write(database.record_delivery_observation, self.task_id, job_id,
                                            self.config.delivery_action, "confirmed", ready["message"])
                if recorded:
                    self.saved += 1
                    await self.log(f"{job['title']}：{ready['message']}，本次无需再次点击", "success")
                else:
                    self.duplicates += 1
                    await self.log(f"跳过 {job['title']}：已有执行中的投递记录", "warning")
                await self.progress()
                if index < len(self.config.job_ids):
                    await self.delay(random.uniform(self.config.delay_min, self.config.delay_max))
                continue
            if not ready or ready["state"] != "ready":
                reason = (ready or {}).get("message") or "页面未完成加载或登录状态无法确认，尚未点击"
                recorded = await self.write(database.record_delivery_observation, self.task_id, job_id,
                                            self.config.delivery_action, "failed", reason)
                if recorded:
                    self.failed += 1
                    self.failure_messages.append(f"{job['title']}：{reason}")
                else:
                    self.duplicates += 1
                    reason += "；已有完成、执行中或待核对记录，保留原状态，本次未再次发送"
                await self.log(f"{job['title']}：{reason}", "warning")
                await self.progress(message=f"{job['title']}：{reason}")
                if ready and ready["state"] == "blocked":
                    raise RuntimeError(reason)
                if index < len(self.config.job_ids):
                    await self.delay(random.uniform(self.config.delay_min, self.config.delay_max))
                continue
            reserved = await self.write(database.reserve_delivery, self.task_id, job_id, self.config.delivery_action)
            if not reserved:
                self.duplicates += 1
                await self.log(f"跳过 {job['title']}：已有完成、执行中或待核对的记录，本次未点击", "warning")
                await self.progress()
                continue
            status, message = "unknown", "投递结果不明，请在官网核对；系统不会自动重试"
            try:
                self.check_stop()
                browser.require_collection(page)
                if job_identity(self.config.platform, page.url) != job["platform_id"]:
                    status, message = "failed", "点击前职位页面发生变化，本次未点击"
                else:
                    clicked = await page.evaluate(DELIVERY_PAGE, {**args, "click": True})
                    if clicked["state"] == "already":
                        status, message = "confirmed", clicked["message"]
                    elif clicked["state"] != "clicked":
                        status, message = "failed", clicked.get("message") or "页面操作入口发生变化，本次未点击"
                    else:
                        resume_clicked = clicked.get("kind") != "contact_then_resume"
                        dialog_confirmed = False
                        deadline = asyncio.get_running_loop().time() + 20
                        while asyncio.get_running_loop().time() < deadline:
                            await self.delay(0.5)
                            state = await browser.snapshot()
                            if state.get("login_required") or state.get("needs_verification"):
                                message = "点击后官网要求登录或验证，结果待核对；系统不会自动重试"
                                break
                            outcome = await page.evaluate(DELIVERY_PAGE, {**args, "phase": "result"})
                            if outcome["state"] == "success":
                                status, message = "confirmed", outcome["message"]
                                break
                            message = outcome.get("message") or message
                            if outcome["state"] == "blocked":
                                message += "；点击结果待核对，系统不会自动重试"
                                break
                            if not resume_clicked:
                                result = await page.evaluate(DELIVERY_PAGE, {**args, "phase": "send_resume"})
                                resume_clicked = result["state"] == "clicked"
                            elif not dialog_confirmed and args["action"] == "resume":
                                result = await page.evaluate(DELIVERY_PAGE, {**args, "phase": "confirm"})
                                dialog_confirmed = result["state"] == "clicked"
            finally:
                await self.write(database.delivery_status, job_id, self.config.delivery_action, status, message)
            if status == "confirmed":
                self.saved += 1
                await self.log(f"{job['title']}：{message}", "success")
            elif status != "unknown":
                self.failed += 1
                self.failure_messages.append(f"{job['title']}：{message}")
                await self.log(f"{job['title']}：{message}", "warning")
            else:
                await self.log(f"{job['title']}：{message}", "warning")
            await self.progress()
            if status == "unknown":
                raise ResultPending(f"{job['title']}：{message}。请在职位详情核对官网结果后确认状态")
            if index < len(self.config.job_ids):
                await self.delay(random.uniform(self.config.delay_min, self.config.delay_max))
