"""Local macOS launcher for the bundled workbench."""

import argparse
import fcntl
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import socket
import sys
import threading
import time
import webbrowser


def arguments():
    parser = argparse.ArgumentParser(description="FindBoss 本地工作台")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-dir")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("端口必须在 0 到 65535 之间")
    if args.data_dir:
        os.environ["FINDBOSS_DATA_DIR"] = str(Path(args.data_dir).expanduser().resolve())
    return args


def configure_logging(data_dir):
    logfile = data_dir / "findboss.log"
    handler = RotatingFileHandler(logfile, maxBytes=5 * 1024 * 1024, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    if sys.stdout is None:
        sys.stdout = logfile.open("a", encoding="utf-8", buffering=1)
    if sys.stderr is None:
        sys.stderr = sys.stdout


def acquire_instance(data_dir, no_browser):
    handle = (data_dir / "desktop.lock").open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.seek(0)
        try:
            metadata = json.load(handle)
        except (ValueError, OSError):
            metadata = {}
        handle.close()
        url = metadata.get("url", "")
        if not no_browser and url.startswith("http://127.0.0.1:"):
            webbrowser.open(url)
        return None
    return handle


def bind_socket(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        if not port:
            sock.close()
            raise
        sock.close()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    return sock


def error_alert(message):
    try:
        from AppKit import NSAlert, NSApplication, NSApplicationActivationPolicyAccessory

        application = NSApplication.sharedApplication()
        application.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        application.activateIgnoringOtherApps_(True)
        alert = NSAlert.alloc().init()
        alert.setMessageText_("FindBoss 启动失败")
        alert.setInformativeText_(message)
        alert.addButtonWithTitle_("好")
        alert.runModal()
    except Exception:
        logging.exception("Unable to show startup error")


def run_gui(server, sock, url, data_dir, no_browser):
    from AppKit import (
        NSApplication, NSApplicationActivationPolicyAccessory, NSMenu, NSMenuItem,
        NSObject, NSStatusBar, NSTerminateNow, NSVariableStatusItemLength,
    )

    errors = []

    def serve():
        try:
            server.run(sockets=[sock])
        except BaseException as exc:
            errors.append(exc)
            logging.exception("Local server stopped during startup")

    thread = threading.Thread(target=serve, name="FindBoss server", daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started:
        if not thread.is_alive() or time.monotonic() >= deadline:
            server.should_exit = True
            raise RuntimeError("本地服务未能启动，请查看数据目录中的 findboss.log。") from (errors[0] if errors else None)
        time.sleep(0.1)

    class WorkbenchDelegate(NSObject):
        def openWorkbench_(self, sender):
            webbrowser.open(url)

        def openDataDirectory_(self, sender):
            from AppKit import NSWorkspace

            NSWorkspace.sharedWorkspace().openFile_(str(data_dir))

        def quitWorkbench_(self, sender):
            NSApplication.sharedApplication().terminate_(sender)

        def applicationShouldTerminate_(self, sender):
            server.should_exit = True
            thread.join(timeout=12)
            if thread.is_alive():
                server.force_exit = True
                thread.join(timeout=2)
            return NSTerminateNow

    application = NSApplication.sharedApplication()
    application.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    delegate = WorkbenchDelegate.alloc().init()
    application.setDelegate_(delegate)
    status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
    status_item.button().setTitle_("FB")
    status_item.button().setToolTip_("FindBoss 工作台")
    menu = NSMenu.alloc().init()
    for title, action, shortcut in (
        ("打开工作台", "openWorkbench:", ""),
        ("打开数据目录", "openDataDirectory:", ""),
        ("退出 FindBoss", "quitWorkbench:", "q"),
    ):
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, shortcut)
        item.setTarget_(delegate)
        menu.addItem_(item)
    status_item.setMenu_(menu)
    # Cocoa delegate/target references are weak; retain these for the entire event loop.
    application._findboss_delegate = delegate
    application._findboss_status_item = status_item
    application._findboss_menu = menu
    if not no_browser:
        webbrowser.open(url)
    try:
        application.run()
    finally:
        server.should_exit = True
        thread.join(timeout=12)
        NSStatusBar.systemStatusBar().removeStatusItem_(status_item)


def main():
    args = arguments()
    data_dir = None
    lock = None
    sock = None
    try:
        # Read configuration only after applying the command-line data directory.
        from app.config import DATA_DIR

        data_dir = DATA_DIR
        data_dir.mkdir(parents=True, exist_ok=True)
        configure_logging(data_dir)
        lock = acquire_instance(data_dir, args.no_browser or args.headless)
        if lock is None:
            return 0
        sock = bind_socket(args.port)
        port = sock.getsockname()[1]
        url = f"http://127.0.0.1:{port}/workbench"
        lock.seek(0)
        lock.truncate()
        json.dump({"pid": os.getpid(), "url": url}, lock)
        lock.flush()
        import uvicorn

        from app.main import app

        server = uvicorn.Server(uvicorn.Config(
            app, host="127.0.0.1", port=port, log_config=None,
            access_log=False, timeout_graceful_shutdown=10,
        ))
        logging.info("Starting FindBoss at %s", url)
        if args.headless:
            server.run(sockets=[sock])
            return 0 if server.started else 1
        run_gui(server, sock, url, data_dir, args.no_browser)
        return 0
    except Exception:
        logging.exception("FindBoss startup failed")
        if not args.headless:
            location = str(data_dir / "findboss.log") if data_dir else "本地数据目录"
            error_alert(f"无法启动本地工作台。详细信息请查看：\n{location}")
        return 1
    finally:
        if sock is not None:
            sock.close()
        if lock is not None:
            lock.seek(0)
            lock.truncate()
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
