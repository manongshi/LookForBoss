import asyncio
import logging
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from urllib.request import ProxyHandler, build_opener
import time
import re
from urllib.parse import urlparse

from .cdp import BrowserError, RawPage

from .config import settings
from .platforms import PLATFORMS, belongs_to, is_login_url


LOGIN_COOKIES = {"wt2", "zp_at", "geek_zp_token"}
LOGIN_PATHS = ("/web/user/", "/web/user", "/web/passport/login", "/user/login")
VERIFY_PATHS = ("/zp/verify", "/zp/security", "/web/passport/zp/security", "verify-slider", "security-check", "/captcha", "/verify", "/waf")
ENTRY_URL = "https://www.zhipin.com/web/geek/jobs"
LOGIN_URL = "https://www.zhipin.com/web/user/"
logger = logging.getLogger("uvicorn.error")


def is_boss_page(page):
    host = urlparse(page.url).hostname or ""
    return host == "zhipin.com" or host.endswith(".zhipin.com")

LOGIN_STATE_SCRIPT = """() => {
    const visible = element => {
        if (!element || !element.getClientRects().length) return false;
        for (let current = element; current; current = current.parentElement) {
            const style = window.getComputedStyle(current);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        }
        return true;
    };
    const anyVisible = selector => Array.from(document.querySelectorAll(selector)).some(visible);
    const loginForm = anyVisible(
        '.sign-wrap, .sign-wrap-new, .sign-login, .sign-form, .login-dialog, .login-container, '
        + '.login-wrapper, .login-content, .login-scan, .scan-login, .scan-wrap, '
        + 'iframe[src*="/web/user/"], iframe[src*="passport/login"], iframe[src*="qrconnect"]'
    );
    const loginText = /微信扫码\\s*安全登录|请使用微信扫描二维码登录|验证码登录\\s*[/／]\\s*注册/
        .test(document.body?.innerText || '');
    const loginInput = anyVisible(
        'input[placeholder*="手机号"], input[placeholder*="验证码"], input[name="phone"], input[name="mobile"]'
    );
    const loginButton = Array.from(document.querySelectorAll(
        '.btn-sign, .btns a, a[ka*="login"], a[href*="/web/user/"]'
    )).some(element => visible(element) && /^(登录|注册)/.test((element.innerText || '').trim()));
    const accountVisible = anyVisible(
        '.nav-figure img, .nav-figure .label-name, .nav-figure .label-text, .nav-figure .name, .nav-user img, '
        + '.user-nav .avatar'
    );
    return { login_required: loginForm || loginText || loginInput || loginButton,
        account_visible: accountVisible, ready: document.readyState === 'complete' };
}"""


PLATFORM_LOGIN_SCRIPT = r"""config => {
    const visible = el => el && el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
    const any = selector => [...document.querySelectorAll(selector)].some(visible);
    const text = document.body?.innerText || '';
    return {
        login_required: any(config.login) || any('input[type="tel"], input[placeholder*="验证码"], iframe[src*="qrconnect"]'),
        account_visible: any(config.account), ready: document.readyState === 'complete',
        verification: /请完成安全验证|请按住滑块|访问过于频繁|访问验证|拖动滑块/.test(text)
    };
}"""


class BrowserManager:
    def __init__(self):
        self.platform = "boss"
        self.process = None
        self.process_watcher = None
        self.debug_endpoint = None
        self.native_target = None
        self.native_page_open = False
        self.native_url = ""
        self.native_navigation = 0
        self.page = None
        self._attaching_page = None
        self.closed = True
        self.closed_event = asyncio.Event()
        self.closed_event.set()
        self.lock = asyncio.Lock()
        self.login_lock = asyncio.Lock()
        self.page_navigations = {}
        self.page_urls = {}
        self.login_waiting = False
        self.collection_allowed = False
        self.validated_session = None

    def is_open(self):
        return (
            self.process is not None and self.process.poll() is None and not self.closed
            and (self.native_target is None or self.native_page_open)
            and (self.page is None or self.page is self._attaching_page or not self.page.is_closed())
        )

    def executable(self):
        if settings.browser_executable:
            path = Path(settings.browser_executable).expanduser()
            if path.is_file():
                return str(path)
            raise BrowserError("BROWSER_EXECUTABLE 指定的浏览器文件不存在")
        bundled = settings.bundled_browser_path
        if bundled is not None and bundled.is_file():
            return str(bundled)
        edge = settings.browser_channel.startswith("msedge")
        candidates = []
        if sys.platform == "darwin":
            app = "Microsoft Edge" if edge else "Google Chrome"
            candidates = [f"/Applications/{app}.app/Contents/MacOS/{app}",
                          str(Path.home() / f"Applications/{app}.app/Contents/MacOS/{app}")]
        elif os.name == "nt":
            relative = "Microsoft/Edge/Application/msedge.exe" if edge else "Google/Chrome/Application/chrome.exe"
            candidates = [str(Path(os.environ[root]) / relative)
                          for root in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA") if root in os.environ]
        candidates += [shutil.which(name) for name in (
            ("msedge", "microsoft-edge") if edge else ("google-chrome", "chromium", "chromium-browser")
        )]
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                return candidate
        raise BrowserError("未找到浏览器，请安装 Google Chrome，或在 backend/.env 设置 BROWSER_EXECUTABLE")

    def native_pages(self):
        # 登录等待时仅读取本机元数据，既不连接页面，也不执行页面脚本。
        with build_opener(ProxyHandler({})).open(self.debug_endpoint + "/json/list", timeout=2) as response:
            return [target for target in json.load(response) if target.get("type") == "page"]

    def update_native_page(self, targets):
        target = next((item for item in targets if item["id"] == self.native_target), None)
        if target is None and self.native_target is None:
            target = next((item for item in targets if item.get("url", "").startswith(PLATFORMS[self.platform]["login_url"])), None)
            if target is None:
                target = next((item for item in targets if belongs_to(self.platform, item.get("url", ""))), None)
        if target is None:
            self.native_page_open = False
            return False
        self.native_page_open = True
        self.native_target = target["id"]
        url = target.get("url", "")
        if url != self.native_url:
            self.native_url = url
            self.native_navigation = time.monotonic()
            parsed = urlparse(url)
            logger.info("人工登录页面：%s://%s%s（未连接采集控制）", parsed.scheme, parsed.netloc, parsed.path)
        return True

    async def watch_process(self, process):
        while self.process is process and process.poll() is None:
            if self.page is None:
                try:
                    targets = await asyncio.to_thread(self.native_pages)
                    if self.page is None and not self.update_native_page(targets) and self.native_target is not None:
                        self.collection_allowed = False
                        self.closed_event.set()
                except (OSError, ValueError):
                    pass
            await asyncio.sleep(1)
        if self.process is process:
            self.closed = True
            self.collection_allowed = False
            self.closed_event.set()

    def page_closed(self, page):
        self.page_navigations.pop(page, None)
        self.page_urls.pop(page, None)
        if self.page is page and self._attaching_page is not page:
            self.collection_allowed = False
            self.closed_event.set()
            logger.warning("采集标签页已关闭或连接断开")

    def page_navigated(self, page, url, document_changed):
        if page is not self.page:
            return
        previous = urlparse(self.page_urls.get(page, ""))
        current = urlparse(url)
        self.page_urls[page] = url
        if document_changed or (current.scheme, current.netloc, current.path) != (previous.scheme, previous.netloc, previous.path):
            self.page_navigations[page] = time.monotonic()
        if (current.scheme, current.netloc, current.path) != (previous.scheme, previous.netloc, previous.path):
            logger.info("采集页面导航：%s://%s%s", current.scheme, current.netloc, current.path)
        if (
            not belongs_to(self.platform, page.url)
            or is_login_url(self.platform, url)
            or any(path in url for path in VERIFY_PATHS)
        ):
            self.collection_allowed = False

    def begin_login_wait(self):
        self.collection_allowed = False
        self.validated_session = None
        self.login_waiting = True

    def end_login_wait(self):
        self.login_waiting = False

    async def document_state(self, page):
        # 主文档也会检查可见的登录 iframe，避免使用弹窗背后的旧头像确认登录。
        if self.platform == "boss":
            return await page.evaluate(LOGIN_STATE_SCRIPT)
        return await page.evaluate(PLATFORM_LOGIN_SCRIPT, PLATFORMS[self.platform])

    async def ensure(self):
        async with self.lock:
            if self.is_open():
                return self.page
            if self.process is not None and self.process.poll() is None:
                raise BrowserError("登录标签页已关闭，请先关闭采集浏览器，再重新打开")
            executable = self.executable()
            profile = settings.profile_path if self.platform == "boss" else settings.profile_path.with_name("browser-profile-" + self.platform)
            profile.mkdir(parents=True, exist_ok=True)
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            self.debug_endpoint = f"http://127.0.0.1:{port}"
            self.native_target = None
            self.native_page_open = False
            self.native_url = ""
            self.page = None
            self.page_navigations.clear()
            self.page_urls.clear()
            self.closed_event = asyncio.Event()
            self.begin_login_wait()
            self.process = subprocess.Popen([
                executable, f"--user-data-dir={profile}",
                "--remote-debugging-address=127.0.0.1", f"--remote-debugging-port={port}",
                "--no-first-run", "--no-default-browser-check", "--new-window", PLATFORMS[self.platform]["login_url"],
            ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.closed = False
            process = self.process
            self.process_watcher = asyncio.create_task(self.watch_process(process))
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    self.closed = True
                    self.closed_event.set()
                    raise BrowserError("浏览器启动失败，请关闭占用本项目 browser-profile 的浏览器后重试")
                try:
                    targets = await asyncio.to_thread(self.native_pages)
                    if self.update_native_page(targets):
                        return None
                except (OSError, ValueError):
                    pass
                await asyncio.sleep(0.2)
            raise BrowserError("浏览器启动超时，请关闭采集浏览器后重新打开")

    async def open_login(self, platform=None):
        platform = platform or self.platform
        if platform not in PLATFORMS:
            raise ValueError("不支持的招聘平台")
        if platform != self.platform:
            await self.close()
            self.platform = platform
        async with self.login_lock:
            await self.ensure()
            self.begin_login_wait()
            # 已打开时不导航、不新建标签页，也不反复将窗口置顶。
            if self.page is not None:
                await self._disconnect_page()
            return await self.snapshot()

    async def attach_for_collection(self):
        async with self.login_lock:
            if self.page is not None and not self.page.is_closed():
                return
            if not self.is_open():
                raise ValueError("采集浏览器已关闭，请重新创建任务")
            try:
                targets = await asyncio.to_thread(self.native_pages)
            except (OSError, ValueError) as exc:
                raise ValueError("浏览器尚未准备好，请稍后重试") from exc
            if not self.update_native_page(targets):
                raise ValueError("原登录标签页已关闭，请重新打开采集浏览器")
            parsed = urlparse(self.native_url)
            host = parsed.hostname or ""
            if (
                not belongs_to(self.platform, self.native_url)
                or is_login_url(self.platform, self.native_url)
                or any(path in self.native_url for path in VERIFY_PATHS)
                or time.monotonic() - self.native_navigation < 2
            ):
                raise ValueError("请先在当前浏览器完成登录，页面稳定后再点击确认")
            target = next(item for item in targets if item["id"] == self.native_target)
            if not target.get("webSocketDebuggerUrl"):
                raise ValueError("当前登录页尚未准备好，请稍后重新确认")
            page = RawPage(target, self.page_navigated, self.page_closed)
            self._attaching_page = page
            self.page = page
            self.page_navigations[page] = self.native_navigation
            self.page_urls[page] = self.native_url
            try:
                await page.open()
                # Frame metadata may be newer than /json/list; preserve its URL.
                if self.page_urls.get(page) != page.url:
                    self.page_navigated(page, page.url, True)
                if page.is_closed() or self.closed_event.is_set():
                    raise BrowserError("原登录标签页已关闭")
            except (BrowserError, OSError, ValueError) as exc:
                await self._disconnect_page()
                raise ValueError("无法连接当前登录页，请检查浏览器后重试") from exc
            finally:
                self._attaching_page = None

    async def _disconnect_page(self):
        page = self.page
        self.page = None
        if page is not None:
            self.native_url = page.url
            self.native_navigation = self.page_navigations.get(page, self.native_navigation)
        self.page_navigations.clear()
        self.page_urls.clear()
        if page is not None:
            await page.close()

    async def pause_control(self):
        async with self.login_lock:
            self.collection_allowed = False
            await self._disconnect_page()

    async def snapshot(self):
        if not self.is_open():
            return {"platform": self.platform, "open": False, "logged_in": False, "needs_verification": False, "login_required": False, "checking": False}
        if self.login_waiting or self.page is None:
            return {
                "platform": self.platform, "open": self.is_open(), "logged_in": False,
                "needs_verification": any(path in (self.page.url if self.page else self.native_url) for path in VERIFY_PATHS),
                "login_required": True, "checking": False,
            }
        return await self.page_snapshot(self.page)

    async def confirm_login_page(self):
        return await self.page_snapshot(self.page)

    def require_collection(self, page):
        if self.login_waiting or not self.collection_allowed or page is not self.page or not self.is_open():
            raise BrowserError("等待登录确认，当前不允许跳转、刷新或读取岗位")

    async def visit_jobs(self, page, url):
        self.require_collection(page)
        await page.navigate(url)

    async def reload_jobs(self, page):
        self.require_collection(page)
        await page.reload()

    async def page_snapshot(self, page):
        result = {"platform": self.platform, "open": self.is_open() and page is not None and not page.is_closed(), "logged_in": False,
                  "needs_verification": False, "login_required": False, "checking": True}
        if not result["open"]:
            result["checking"] = False
            return result
        try:
            cookies = await page.cookies()
            if self.platform != "boss":
                return await self.platform_snapshot(page, result, cookies)
            session = tuple(sorted((cookie["name"], cookie["value"]) for cookie in cookies
                                   if cookie["name"] in LOGIN_COOKIES and cookie["value"]))
            navigation = self.page_navigations.get(page, time.monotonic())
            result["needs_verification"] = any(path in page.url for path in VERIFY_PATHS)
            parsed = urlparse(page.url)
            if not belongs_to(self.platform, page.url):
                return result
            result["login_required"] = is_login_url(self.platform, page.url)
            if result["login_required"] or result["needs_verification"]:
                result["checking"] = False
                self.validated_session = None
                return result
            state = await asyncio.wait_for(self.document_state(page), timeout=2)
            if not isinstance(state, dict):
                return result
            result["login_required"] = state.get("login_required", False)
            if result["login_required"] or not session:
                self.validated_session = None
            result["logged_in"] = bool(
                session and state.get("ready") and (state.get("account_visible") or session == self.validated_session)
                and not result["login_required"] and not result["needs_verification"]
                and time.monotonic() - navigation >= 2
                and self.page_navigations.get(page) == navigation and not page.is_closed()
            )
            result["checking"] = not (result["logged_in"] or result["login_required"])
            if result["logged_in"]:
                self.validated_session = session
        except BrowserError:
            result["open"] = self.is_open()
        except asyncio.TimeoutError:
            pass
        return result

    async def platform_snapshot(self, page, result, cookies):
        if not belongs_to(self.platform, page.url):
            result["login_required"] = True
            result["checking"] = False
            return result
        navigation = self.page_navigations.get(page, time.monotonic())
        result["needs_verification"] = any(path in page.url for path in VERIFY_PATHS)
        state = await asyncio.wait_for(self.document_state(page), timeout=2)
        result["needs_verification"] = result["needs_verification"] or state.get("verification", False)
        result["login_required"] = is_login_url(self.platform, page.url) or state.get("login_required", False)
        domain = PLATFORMS[self.platform]["domain"]
        session = frozenset((item["name"], item["value"]) for item in cookies
                            if item.get("value") and (item.get("domain", "").lstrip(".") == domain
                            or item.get("domain", "").endswith("." + domain))
                            and re.search(r"token|session|ticket|passport|auth", item["name"], re.I))
        if result["login_required"] or result["needs_verification"]:
            self.validated_session = None
        previously_confirmed = bool(session and self.validated_session and session.intersection(self.validated_session))
        result["logged_in"] = bool((state.get("account_visible") or previously_confirmed) and state.get("ready")
                                   and not result["login_required"] and not result["needs_verification"]
                                   and time.monotonic() - navigation >= 2
                                   and self.page_navigations.get(page) == navigation)
        result["checking"] = not (result["logged_in"] or result["login_required"] or result["needs_verification"])
        if result["logged_in"] and state.get("account_visible"):
            self.validated_session = session
        return result

    async def close(self):
        async with self.login_lock:
            async with self.lock:
                self.closed_event.set()
                self.collection_allowed = False
                await self._disconnect_page()
                if self.process_watcher:
                    self.process_watcher.cancel()
                    await asyncio.gather(self.process_watcher, return_exceptions=True)
                    self.process_watcher = None
                if self.process and self.process.poll() is None:
                    self.process.terminate()
                    try:
                        await asyncio.to_thread(self.process.wait, timeout=5)
                    except subprocess.TimeoutExpired:
                        raise BrowserError("采集浏览器尚未退出，请手动关闭后重试")
                self.process = None
                self.closed = True
                self.end_login_wait()
                self.validated_session = None


browser = BrowserManager()
