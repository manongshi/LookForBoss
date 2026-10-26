import asyncio
import random

from .browser import BrowserError, browser
from .collector import ResultPending
from .database import database
from .delivery import DELIVERY_PAGE, DeliveryCollector
from .platforms import job_identity


# UI selectors referenced from manongshi/get_jobs's Boss.java and Locators.java:
# https://github.com/manongshi/get_jobs/tree/main/src/main/java/com/getjobs/worker/boss
# Keep message sending separate from opening a conversation and sending a resume.
MESSAGE_PAGE = r"""args => {
    const visible = el => {
        if (!el || !el.getClientRects().length) return false;
        for (let current = el; current; current = current.parentElement) {
            const style = current.ownerDocument.defaultView.getComputedStyle(current);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        }
        return true;
    };
    const normalize = value => String(value || '').normalize('NFKC').replace(/[\u200b-\u200f\u2060\ufeff]/g, '').replace(/\s+/g, ' ').trim();
    const text = el => normalize(el?.innerText || el?.textContent || '');
    const compact = value => normalize(value).replace(/\s/g, '');
    const expected = new URL(args.url);
    const sameJob = value => {
        try {
            const url = new URL(value, location.href);
            return url.hostname.replace(/^www\./, '') === expected.hostname.replace(/^www\./, '') && url.pathname === expected.pathname;
        } catch { return false; }
    };
    const identity = root => compact(text(root)).includes(compact(args.title))
        && (!args.company || compact(text(root)).includes(compact(args.company)));
    const documents = [document];
    for (let index = 0; index < documents.length && index < 12; index++) {
        for (const frame of documents[index].querySelectorAll('iframe')) {
            try {
                if (visible(frame) && frame.contentDocument && !documents.includes(frame.contentDocument)) documents.push(frame.contentDocument);
            } catch { /* Only inspect accessible frames in this selected page. */ }
        }
    }
    const block = documents.map(doc => text(doc.body)).join('\n').match(/请完成验证|请按住滑块|操作频繁|访问频繁|今日[^。\n]{0,40}(?:上限|用完)/);
    if (block) return {state: 'blocked', message: `官网提示：${block[0]}`};
    const sessions = window.__findBossMessageChecks instanceof Map ? window.__findBossMessageChecks : (window.__findBossMessageChecks = new Map());
    const previous = sessions.get(args.session);
    const inputSelector = '#chat-input[contenteditable="true"], .chat-input[contenteditable="true"], textarea.input-area';
    const historySelector = '.chat-message .im-list, .chat-record, .dialog-con, .chat-message-list, .message-list';
    const inputs = documents.flatMap(doc => [...doc.querySelectorAll(inputSelector)]).filter(visible);
    const checkingResult = args.phase === 'result';
    if (inputs.length > 1) return {state: 'waiting', message: '出现多个聊天输入框，无法唯一确认接收人'};
    const input = inputs[0] || (checkingResult && previous?.input?.isConnected ? previous.input : null);
    let root = checkingResult && previous?.root?.isConnected && documents.includes(previous.root.ownerDocument) ? previous.root : null;
    if (!root && input) {
        // The input's closest dialog can contain only the editor. Find the
        // nearest shared ancestor that also contains the conversation history.
        for (let node = input.parentElement; node; node = node.parentElement) {
            if ([...node.querySelectorAll(historySelector)].some(visible)) { root = node; break; }
        }
        root ||= input.closest('.dialog-container, .chat-window, .chat-conversation, .chat-detail, .chat-detail-container, .chat-container, .chat-im, .im-chat, .greet-dialog') || input.ownerDocument.body;
    }
    if (!root || (!input && !checkingResult)) return {state: 'waiting', message: '尚未出现可核对的聊天窗口'};
    const doc = root.ownerDocument;
    const headers = [...root.querySelectorAll('.chat-header, .chat-head, .chat-info, .chat-job, .chat-job-info, .chat-job-card, .dialog-title')].filter(visible);
    const links = [...root.querySelectorAll('a[href*="/job_detail/"]')].filter(visible)
        .filter(el => !el.closest('.recommend-list, .recommend-job, .job-card-wrapper, .joblist-box__item'));
    const hasJobLink = links.some(el => sameJob(el.href));
    const verifiedHeader = headers.some(identity) || hasJobLink;
    const openedFromJob = args.opened_from_job && sameJob(location.href) && identity(document.body);
    if ((links.length && !hasJobLink && !openedFromJob) || (!verifiedHeader && !openedFromJob))
        return {state: 'changed', message: '聊天窗口的职位或公司无法与所选职位核对'};
    const fingerprint = [doc.location.pathname, headers.map(text).join('|'), root.getAttribute('data-uid') || '', root.getAttribute('data-to-uid') || ''].join('::');
    if (args.fingerprint && args.fingerprint !== fingerprint)
        return {state: 'changed', message: '聊天接收人或会话发生变化'};
    const editorValue = () => !input?.isConnected ? '' : input.tagName === 'TEXTAREA' ? input.value : input.innerText;
    const ownSelector = '.message-item.item-myself, .item-myself, .message-item.is-self, .message-item.self, [data-direction="outgoing"], [data-from-self="true"]';
    const expectedMessage = compact(args.message);
    const sentLabels = new Set(['已发送', '发送成功']);
    const excludedContent = `${inputSelector}, input, textarea, [contenteditable="true"], .quote-message, .message-quote, .reply-quote`;
    // The job-detail greeting dialog uses a plain bubble beside “已发送”,
    // without the full chat page's outgoing-message classes.
    const simpleRows = [];
    const sentMarkers = [...root.querySelectorAll('*')].filter(el => visible(el)
        && sentLabels.has(text(el)) && !el.closest(excludedContent)
        && ![...el.children].some(child => sentLabels.has(text(child))));
    for (const marker of sentMarkers) {
        for (let row = marker.parentElement, depth = 0; row && root.contains(row) && depth < 4; row = row.parentElement, depth++) {
            if (row.matches('body, html') || (input && row.contains(input))) break;
            const label = compact(text(marker));
            const rowText = compact(text(row));
            if (rowText !== label + expectedMessage && rowText !== expectedMessage + label) continue;
            const bubble = [...row.querySelectorAll('*')].find(el => visible(el)
                && !el.contains(marker) && !marker.contains(el) && !el.closest(excludedContent)
                && compact(text(el)) === expectedMessage);
            if (bubble) {
                simpleRows.push(row);
                break;
            }
        }
    }
    const ownRows = [...new Set([...root.querySelectorAll(ownSelector), ...simpleRows])].filter(visible)
        .filter((row, index, all) => !all.some(other => other !== row && other.contains(row)));
    const hasSentMarker = row => simpleRows.some(simple => row === simple || row.contains(simple));
    const rowKey = row => row.getAttribute('data-mid') || row.getAttribute('data-message-id') || row.getAttribute('data-msg-id') || row.getAttribute('data-id') || row.id || '';
    const ignored = '.message-status, .send-status, .read-status, .read-receipt, .message-time, .time, .timestamp, .avatar, .name, .quote-message, .message-quote, .reply-quote, [role="status"]';
    const cleanText = el => {
        const clone = el.cloneNode(true);
        clone.querySelectorAll(ignored).forEach(node => node.remove());
        return compact(clone.textContent);
    };
    const matching = ownRows.filter(row => {
        if (hasSentMarker(row)) return true;
        const contents = [...row.querySelectorAll('.message-content, .text-content, .message-text, .message-body, .text-box, .text')]
            .filter(el => !el.closest('.quote-message, .message-quote, .reply-quote'));
        return [...contents, row].some(el => cleanText(el) === expectedMessage);
    });
    const signature = row => {
        const time = row.getAttribute('data-time') || row.getAttribute('data-timestamp') || text(row.querySelector('.message-time, time, .timestamp'));
        const value = rowKey(row) + '|' + cleanText(row) + '|' + time;
        let hash = 2166136261;
        for (let index = 0; index < value.length; index++) hash = Math.imul(hash ^ value.charCodeAt(index), 16777619);
        return String(hash >>> 0);
    };
    const state = {fingerprint, count: matching.length, row_ids: ownRows.map(rowKey).filter(Boolean), row_signatures: ownRows.map(signature), own_count: ownRows.length};
    if (args.phase === 'inspect') {
        if (!args.allow_repeat && matching.length) return {...state, state: 'already', message: '聊天记录中已有相同消息，本次未重复发送'};
        return {...state, state: 'ready'};
    }
    if (checkingResult) {
        const baselineIds = new Set(args.baseline_ids || []);
        const baselineSignatures = new Set(args.baseline_signatures || []);
        const newMessages = matching.filter(row => {
            if (baselineSignatures.size) return !baselineSignatures.has(signature(row)) || matching.length > args.baseline_count;
            const id = rowKey(row);
            return id ? !baselineIds.has(id) : matching.length > args.baseline_count;
        });
        const diagnostics = `本人消息 ${ownRows.length} 条，匹配正文 ${matching.length} 条，发送前匹配 ${args.baseline_count} 条`;
        if (!newMessages.length) return {...state, state: 'waiting', message: '等待官网聊天记录确认新消息', diagnostics};
        const last = newMessages[newMessages.length - 1];
        const statusNodes = [...last.querySelectorAll('.message-status, .send-status, .read-status, [role="status"], .send-fail, .message-fail')];
        const statusParts = statusNodes.flatMap(node => [node, ...node.querySelectorAll('*')]);
        const statusText = statusParts.map(el => text(el) + ' ' + (el.getAttribute('title') || '') + ' ' + (el.getAttribute('aria-label') || '')).join(' ');
        const classText = [last, ...statusParts].map(el => typeof el.className === 'string' ? el.className : '').join(' ');
        if (/send-fail|send-error|message-fail|message-error|(?:^|\s)(?:error|failed|fail)(?:\s|$)/.test(classText) || /发送失败|重新发送|点击重试/.test(statusText))
            return {...state, state: 'failed', message: '官网聊天记录显示消息发送失败', diagnostics};
        if (/sending|send-progress/.test(classText) || statusParts.some(el => /loading/.test(el.className || '')) || /发送中/.test(statusText) || normalize(editorValue()))
            return {...state, state: 'waiting', message: '新消息已出现，等待发送状态稳定', diagnostics};
        const simpleConfirmation = hasSentMarker(last);
        return {...state, state: 'sent', confirmation_source: simpleConfirmation ? 'sent_marker' : 'chat_history',
            message: simpleConfirmation ? '官网简化聊天弹窗已显示“已发送”，消息正文一致' : '官网本人聊天记录中已出现本次新消息', diagnostics};
    }
    if (!input) return {...state, state: 'unavailable', message: '聊天输入框已关闭，未点击发送'};
    const sendButtons = [...root.querySelectorAll('div.send-message, button[type="send"], button.btn-send')]
        .filter(visible).filter(el => !el.disabled && el.getAttribute('aria-disabled') !== 'true' && !el.matches('.disabled, .is-disabled'))
        .filter(el => /^(发送|发送消息|立即发送)$/.test(text(el)) || (!text(el) && el.matches('button[type="send"]')))
        .filter((el, index, all) => !all.some(other => other !== el && el.contains(other)));
    if (args.phase === 'fill') {
        if (normalize(editorValue()) && normalize(editorValue()) !== normalize(args.message))
            return {...state, state: 'unavailable', message: '聊天输入框中已有其他草稿，请先在官网处理后重试'};
        if (input.disabled || input.readOnly) return {...state, state: 'unavailable', message: '聊天输入框暂不可编辑'};
        input.focus();
        if (input.tagName === 'TEXTAREA') {
            const setter = Object.getOwnPropertyDescriptor(doc.defaultView.HTMLTextAreaElement.prototype, 'value').set;
            setter.call(input, args.message);
        } else input.innerText = args.message;
        input.dispatchEvent(new doc.defaultView.Event('input', {bubbles: true, composed: true}));
        input.dispatchEvent(new doc.defaultView.Event('change', {bubbles: true}));
        return {...state, state: 'filled'};
    }
    if (args.phase === 'send') {
        if (normalize(editorValue()) !== normalize(args.message)) return {...state, state: 'unavailable', message: '输入框内容与已确认消息不一致，未点击发送'};
        if (sendButtons.length !== 1) return {...state, state: 'unavailable', message: '未找到唯一可用的发送按钮，消息仍保留在输入框中'};
        sessions.set(args.session, {root, input});
        while (sessions.size > 16) sessions.delete(sessions.keys().next().value);
        sendButtons[0].click();
        return {...state, state: 'clicked'};
    }
    return {...state, state: 'waiting'};
}"""


class MessageCollector(DeliveryCollector):
    def completion_message(self):
        message = f"消息任务结束：新发送 {self.saved}，跳过 {self.duplicates}，未完成 {self.failed}"
        if self.failure_messages:
            message += f"；最近未完成：{self.failure_messages[-1]}"
        elif self.duplicates and not self.saved:
            message += "；已有消息或待核对记录不会自动重复发送，具体原因见任务日志"
        return message[:500]

    async def page_state(self, page):
        self.check_stop()
        browser.require_collection(page)
        state = await browser.snapshot()
        if state.get("login_required") or state.get("needs_verification"):
            raise RuntimeError("官网要求登录或验证，请先在浏览器处理")
        if not state.get("logged_in"):
            return False
        return True

    async def send_message(self, page, job, message, attempt):
        args = {
            "session": self.task_id + ":" + job["id"],
            "url": job["url"], "title": job["title"], "company": job.get("company", ""),
            "message": message, "allow_repeat": self.config.allow_repeat, "opened_from_job": False,
        }
        deadline = asyncio.get_running_loop().time() + 25
        last_reason = "等待所选职位加载"
        while asyncio.get_running_loop().time() < deadline:
            if await self.page_state(page) and job_identity("boss", page.url) == job["platform_id"]:
                ready = await page.evaluate(DELIVERY_PAGE, {**args, "platform": "boss", "action": "message", "phase": "prepare", "click": False})
                last_reason = ready.get("message") or last_reason
                if ready["state"] == "blocked":
                    raise RuntimeError(last_reason)
                if ready["state"] == "ready":
                    clicked = await page.evaluate(DELIVERY_PAGE, {**args, "platform": "boss", "action": "message", "phase": "prepare", "click": True})
                    if clicked["state"] != "clicked":
                        return "failed", clicked.get("message") or "沟通入口发生变化，未发送消息", False
                    args["opened_from_job"] = True
                    break
            await self.delay(0.5)
        else:
            return "failed", last_reason + "，未发送消息", False
        deadline = asyncio.get_running_loop().time() + 20
        while asyncio.get_running_loop().time() < deadline:
            if await self.page_state(page):
                ready = await page.evaluate(MESSAGE_PAGE, {**args, "phase": "inspect"})
                last_reason = ready.get("message") or "等待对应会话的输入框"
                if ready["state"] == "already":
                    return "confirmed", last_reason, True
                if ready["state"] == "blocked":
                    raise RuntimeError(last_reason)
                if ready["state"] == "ready":
                    args["fingerprint"] = ready["fingerprint"]
                    break
            await self.delay(0.5)
        else:
            return "failed", last_reason + "，未点击发送", False
        filled = await page.evaluate(MESSAGE_PAGE, {**args, "phase": "fill"})
        if filled["state"] != "filled":
            return "failed", filled.get("message") or "消息输入失败，未点击发送", False
        # Let the website update its input model and button state before sending.
        await self.delay(0.5)
        if not await self.page_state(page):
            return "failed", "登录状态无法确认，未点击发送", False
        # If the browser disconnects during this command, keep the result uncertain.
        attempt["send_attempted"] = True
        sent = await page.evaluate(MESSAGE_PAGE, {**args, "phase": "send"})
        if sent["state"] != "clicked":
            attempt["send_attempted"] = False
            return "failed", sent.get("message") or "发送按钮不可用，未点击发送", False
        args["baseline_count"] = sent["count"]
        args["baseline_ids"] = sent.get("row_ids", [])
        args["baseline_signatures"] = sent.get("row_signatures", [])
        deadline = asyncio.get_running_loop().time() + 45
        stable_since = None
        stable_count = None
        last_diagnostics = ""
        last_reason = "等待官网确认新消息"
        while asyncio.get_running_loop().time() < deadline:
            await self.delay(0.5)
            if not await self.page_state(page):
                stable_since = None
                continue
            result = await page.evaluate(MESSAGE_PAGE, {**args, "phase": "result"})
            last_diagnostics = result.get("diagnostics") or last_diagnostics
            last_reason = result.get("message") or last_reason
            if result["state"] == "failed":
                return "failed", last_reason, False
            if result["state"] in {"blocked", "changed"}:
                return "unknown", last_reason + "；发送结果待核对，不会自动重发", False
            if result["state"] == "sent":
                current = asyncio.get_running_loop().time()
                if stable_since is None or stable_count != result["count"]:
                    stable_since, stable_count = current, result["count"]
                if current - stable_since >= 3:
                    if result.get("confirmation_source") == "sent_marker":
                        return "confirmed", "官网简化聊天弹窗已确认新消息发送完成（已发送标记与正文一致）", False
                    return "confirmed", "官网本人聊天记录已确认新消息发送完成", False
            else:
                stable_since = None
        if last_diagnostics:
            await self.log(f"{job['title']}：发送结果核对超时（{last_diagnostics}）", "warning")
        return "unknown", last_reason + "；发送结果待核对，不会自动重发", False

    async def execute(self):
        self.failure_messages = []
        for index, job_id in enumerate(self.config.job_ids, 1):
            self.check_stop()
            job = await asyncio.to_thread(database.get_job, job_id)
            if not job or job.get("source", "boss") != "boss":
                raise RuntimeError("职位不存在或不是 BOSS 直聘职位，消息任务已停止")
            message = self.config.messages.get(job_id, "").strip()
            if not message or len(message) > 1000:
                raise RuntimeError("消息内容为空或超过 1000 字，任务已停止")
            if job_identity("boss", job["url"]) != job["platform_id"]:
                raise RuntimeError("职位原始链接无法核对，消息任务已停止")
            self.scanned += 1
            hits = await asyncio.to_thread(database.job_blacklist_hits, job)
            if hits:
                self.duplicates += 1
                reason = f"命中黑名单「{hits[0]['value']}」，未发送消息"
                await self.write(database.message_record_status, self.task_id, job_id, "skipped", reason)
                await self.log(f"跳过 {job['title']}：{reason}", "warning")
                await self.progress()
                continue
            reserved = await self.write(database.reserve_delivery, self.task_id, job_id, "message", self.config.allow_repeat)
            if not reserved:
                self.duplicates += 1
                reason = "已有已发送、执行中或待核对记录；再次发送需在确认窗口明确开启"
                await self.write(database.message_record_status, self.task_id, job_id, "skipped", reason)
                await self.log(f"跳过 {job['title']}：{reason}", "warning")
                await self.progress()
                continue
            status, reason, skipped = "failed", "任务在点击发送前中断，本次消息未发送", False
            attempt = {"send_attempted": False}
            stop_reason = None
            try:
                await self.progress(current_keyword=job["title"], current_city=job["city"],
                                    message=f"准备发送消息 {index}/{len(self.config.job_ids)}：{job['title']} · {job['company']}")
                page = await self.wait_for_login(open_page=False)
                await browser.visit_jobs(page, job["url"])
                status, reason, skipped = await self.send_message(page, job, message, attempt)
            except (RuntimeError, BrowserError) as exc:
                stop_reason = str(exc)
                status = "unknown" if attempt["send_attempted"] else "failed"
                reason = stop_reason + ("；已尝试发送，请核对官网记录，不会自动重发" if attempt["send_attempted"] else "；尚未发送消息")
            except BaseException:
                if attempt["send_attempted"]:
                    status, reason = "unknown", "消息发送过程中任务中断，请核对官网记录；系统不会自动重发"
                raise
            finally:
                await self.write(database.delivery_status, job_id, "message", status, reason,
                                 record_status="skipped" if skipped else status)
            if skipped:
                self.duplicates += 1
            elif status == "confirmed":
                self.saved += 1
            elif status != "unknown":
                self.failed += 1
                self.failure_messages.append(f"{job['title']}：{reason}")
            await self.log(f"{job['title']}：{reason}", "success" if status == "confirmed" and not skipped else "warning")
            await self.progress(message=f"{job['title']}：{reason}")
            if status == "unknown":
                raise ResultPending(reason)
            if stop_reason:
                raise RuntimeError(reason)
            if index < len(self.config.job_ids):
                await self.delay(random.uniform(self.config.delay_min, self.config.delay_max))
