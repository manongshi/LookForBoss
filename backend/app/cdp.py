import asyncio
import base64
import json
from collections import OrderedDict
from urllib.parse import urlparse

from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException
from .platforms import capture_api


class BrowserError(RuntimeError):
    pass


_NO_ARGUMENT = object()
_API_PATHS = {"/wapi/zpgeek/search/joblist.json", "/wapi/zpgeek/job/detail.json"}


class RawPage:
    """One Chrome target, with one reader routing commands and passive responses."""

    def __init__(self, target, on_navigation, on_closed):
        self.target_id = target["id"]
        self.url = target.get("url", "")
        self._websocket_url = target["webSocketDebuggerUrl"]
        self._on_navigation = on_navigation
        self._on_closed = on_closed
        self._socket = None
        self._reader = None
        self._pending = {}
        self._command_id = 0
        self._closed = False
        self._intentional_close = False
        self._main_frame = None
        self._requests = OrderedDict()
        self._responses = asyncio.Queue(maxsize=64)
        self._capture_tasks = set()
        self._generation = 0
        self._overflow = False

    async def open(self):
        endpoint = urlparse(self._websocket_url)
        if endpoint.scheme != "ws" or endpoint.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise BrowserError("浏览器调试地址不是本机地址")
        try:
            self._socket = await connect(
                self._websocket_url, proxy=None, open_timeout=10, close_timeout=2,
                max_size=16 * 1024 * 1024, max_queue=64,
            )
            self._reader = asyncio.create_task(self._read_messages())
            # Never enable Runtime or install scripts on new documents. Commands
            # run only in this existing target after the user's login confirmation.
            await self.command("Page.enable")
            tree = await self.command("Page.getFrameTree")
            frame = tree.get("frameTree", {}).get("frame", {})
            self._main_frame = frame.get("id")
            self.url = frame.get("url", self.url)
            await self.command("Network.enable", {
                "maxTotalBufferSize": 32 * 1024 * 1024,
                "maxResourceBufferSize": 8 * 1024 * 1024,
                "maxPostDataSize": 1024 * 1024,
            })
        except (OSError, WebSocketException, asyncio.TimeoutError) as exc:
            await self.close()
            raise BrowserError("无法连接当前采集标签页") from exc
        except BaseException:
            await self.close()
            raise
        return self

    def is_closed(self):
        return self._closed

    async def command(self, method, params=None, timeout=15):
        if self._closed or self._socket is None:
            raise BrowserError("采集标签页连接已关闭")
        self._command_id += 1
        command_id = self._command_id
        future = asyncio.get_running_loop().create_future()
        self._pending[command_id] = future
        try:
            await self._socket.send(json.dumps({
                "id": command_id, "method": method, "params": params or {},
            }, ensure_ascii=False))
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError as exc:
            raise BrowserError(f"浏览器命令超时（{method}）") from exc
        except (OSError, WebSocketException) as exc:
            raise BrowserError("采集标签页连接已断开") from exc
        finally:
            self._pending.pop(command_id, None)
            if not future.done():
                future.cancel()
            elif not future.cancelled():
                future.exception()

    async def _read_messages(self):
        try:
            async for raw in self._socket:
                message = json.loads(raw)
                # This websocket belongs to one exact target. Never consume
                # messages from separately attached child sessions or other tabs.
                if message.get("sessionId"):
                    continue
                if "id" in message:
                    future = self._pending.get(message["id"])
                    if future is None or future.done():
                        continue
                    if "error" in message:
                        code = message["error"].get("code", "unknown")
                        future.set_exception(BrowserError(f"浏览器拒绝执行命令（CDP {code}）"))
                    else:
                        future.set_result(message.get("result", {}))
                else:
                    self._handle_event(message.get("method"), message.get("params", {}))
                    if self._closed:
                        break
        except (OSError, WebSocketException, ValueError):
            pass
        finally:
            self._closed = True
            for future in tuple(self._pending.values()):
                if not future.done():
                    future.set_exception(BrowserError("采集标签页连接已关闭"))
            for task in tuple(self._capture_tasks):
                task.cancel()
            if not self._intentional_close:
                self._on_closed(self)

    def _publish(self, response):
        if self._responses.full():
            self._responses.get_nowait()
            self._overflow = True
        self._responses.put_nowait(response)

    def _error_response(self, request, error):
        self._publish({
            "url": request.get("url", ""), "request_url": request.get("request_url", ""),
            "request_method": request.get("request_method", "GET"),
            "request_post_data": request.get("request_post_data", ""),
            "payload": None, "status": request.get("status"), "error": error,
        })

    def _handle_event(self, method, params):
        if method == "Inspector.detached":
            self._closed = True
            if not self._intentional_close:
                self._on_closed(self)
            return
        if method == "Page.frameNavigated":
            frame = params.get("frame", {})
            if not frame.get("parentId"):
                self._main_frame = frame.get("id")
                self.url = frame.get("url", self.url)
                self._on_navigation(self, self.url, True)
            return
        if method == "Page.navigatedWithinDocument" and params.get("frameId") == self._main_frame:
            self.url = params.get("url", self.url)
            self._on_navigation(self, self.url, False)
            return
        request_id = params.get("requestId")
        if method == "Network.requestWillBeSent":
            if params.get("type") == "Document" and params.get("frameId") == self._main_frame:
                self._on_navigation(self, self.url, True)
            incoming = params.get("request", {})
            url = incoming.get("url", "")
            parsed = urlparse(url)
            host = parsed.hostname or ""
            if not capture_api(url):
                return
            if len(self._requests) >= 256 and request_id not in self._requests:
                _, old = self._requests.popitem(last=False)
                self._error_response(old, "待处理岗位请求过多，部分响应未能读取，请减少同时操作")
            self._requests[request_id] = {
                "request_url": url, "url": url, "generation": self._generation,
                "request_method": incoming.get("method", "GET"),
                "request_post_data": incoming.get("postData", ""),
                "has_post_data": incoming.get("hasPostData", False),
            }
        elif method == "Network.responseReceived" and request_id in self._requests:
            response = params.get("response", {})
            request = self._requests[request_id]
            request.update(url=response.get("url", request["url"]), status=response.get("status"))
        elif method == "Network.loadingFailed" and request_id in self._requests:
            request = self._requests.pop(request_id)
            self._error_response(request, "岗位接口请求未完成，请检查当前页面或网络连接")
        elif method == "Network.loadingFinished" and request_id in self._requests:
            request = self._requests.pop(request_id)
            if len(self._capture_tasks) >= 16:
                self._error_response(request, "岗位响应读取繁忙，请稍后继续采集")
                return
            task = asyncio.create_task(self._capture_response(request_id, request))
            self._capture_tasks.add(task)
            task.add_done_callback(self._capture_tasks.discard)

    async def _capture_response(self, request_id, request):
        payload = None
        error = None
        try:
            if request.get("has_post_data") and not request.get("request_post_data"):
                try:
                    post_data = await self.command("Network.getRequestPostData", {"requestId": request_id})
                    request["request_post_data"] = post_data.get("postData", "")
                except BrowserError:
                    error = "无法读取岗位请求的搜索条件，请等待页面加载后继续"
            response = await self.command("Network.getResponseBody", {"requestId": request_id})
            body = response.get("body", "")
            if response.get("base64Encoded"):
                body = base64.b64decode(body, validate=True).decode("utf-8")
            payload = json.loads(body)
            if not isinstance(payload, dict):
                payload = None
                error = "岗位接口返回格式异常，未返回 JSON 对象"
            status = request.get("status")
            if status is not None and status >= 400:
                error = f"岗位接口返回 HTTP {int(status)}"
        except (TypeError, ValueError, UnicodeError):
            error = "岗位接口未返回有效 JSON，请检查页面是否要求登录或验证"
        except BrowserError:
            error = "无法读取岗位接口响应，请等待页面加载后继续"
        if request["generation"] != self._generation or self._closed:
            return
        self._publish({
            "url": request["url"], "request_url": request["request_url"],
            "request_method": request.get("request_method", "GET"),
            "request_post_data": request.get("request_post_data", ""),
            "payload": payload, "status": request.get("status"), "error": error,
        })

    async def next_response(self, timeout=1):
        if self._overflow:
            self._overflow = False
            return {"url": "", "request_url": "", "payload": None, "status": None,
                    "error": "岗位响应队列已满，部分响应未能处理，请减少同时操作"}
        if not self._responses.empty():
            return self._responses.get_nowait()
        if self._closed:
            raise BrowserError("采集标签页连接已关闭")
        if timeout <= 0:
            return None
        try:
            return await asyncio.wait_for(self._responses.get(), timeout)
        except asyncio.TimeoutError:
            if self._closed:
                raise BrowserError("采集标签页连接已关闭")
            return None

    def clear_responses(self):
        self._generation += 1
        self._requests.clear()
        self._overflow = False
        while not self._responses.empty():
            self._responses.get_nowait()
        for task in tuple(self._capture_tasks):
            task.cancel()

    async def evaluate(self, script, arg=_NO_ARGUMENT):
        arguments = "" if arg is _NO_ARGUMENT else json.dumps(arg, ensure_ascii=False)
        result = await self.command("Runtime.evaluate", {
            "expression": f"({script})({arguments})", "returnByValue": True, "awaitPromise": True,
        })
        if result.get("exceptionDetails"):
            raise BrowserError("当前页面脚本执行失败，请等待页面加载完成")
        return result.get("result", {}).get("value")

    async def cookies(self):
        result = await self.command("Network.getCookies", {"urls": [self.url]})
        return result.get("cookies", [])

    async def navigate(self, url):
        result = await self.command("Page.navigate", {"url": url}, timeout=35)
        if result.get("errorText") or result.get("isDownload"):
            raise BrowserError("采集页面导航失败，请检查浏览器页面和网络连接")

    async def reload(self):
        await self.command("Page.reload", timeout=30)

    async def bring_to_front(self):
        await self.command("Page.bringToFront")

    async def close(self):
        self._intentional_close = True
        self._closed = True
        self.clear_responses()
        if self._socket is not None:
            try:
                await self._socket.close()
            except (OSError, WebSocketException):
                pass
        if self._reader is not None and self._reader is not asyncio.current_task():
            self._reader.cancel()
            await asyncio.gather(self._reader, return_exceptions=True)
        if self._capture_tasks:
            await asyncio.gather(*tuple(self._capture_tasks), return_exceptions=True)
