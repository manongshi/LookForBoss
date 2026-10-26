#!/bin/bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${FINDBOSS_BUILD_PYTHON:-$PROJECT_ROOT/.venv/bin/python}"
DIST_DIR="$PROJECT_ROOT/outputs/macos"
WORK_DIR="$PROJECT_ROOT/runtime/packaging"
APP_PATH="$DIST_DIR/FindBoss.app"
ZIP_PATH="$PROJECT_ROOT/outputs/FindBoss-macOS-arm64.zip"

if [ "$(uname -m)" != "arm64" ]; then
    echo "请在 Apple 芯片的 Mac 上制作此版本。" >&2
    exit 1
fi
if [ ! -x "$PYTHON_BIN" ]; then
    echo "未找到构建环境：$PYTHON_BIN" >&2
    echo "请先安装 backend/requirements-build.txt 中的依赖。" >&2
    exit 1
fi

BROWSER_APP="${FINDBOSS_BROWSER_APP:-}"
if [ -z "$BROWSER_APP" ]; then
    shopt -s nullglob
    for candidate in "$HOME"/Library/Caches/ms-playwright/chromium-*/chrome-mac-arm64/"Google Chrome for Testing.app"; do
        BROWSER_APP="$candidate"
    done
    shopt -u nullglob
fi
if [ ! -x "$BROWSER_APP/Contents/MacOS/Google Chrome for Testing" ]; then
    echo "未找到可分发浏览器。请设置 FINDBOSS_BROWSER_APP 为 Google Chrome for Testing.app 的路径。" >&2
    exit 1
fi

echo "构建前端并放入后端静态资源目录……"
npm --prefix "$PROJECT_ROOT/frontend" run build
echo "制作 macOS 应用……"
"$PYTHON_BIN" -m PyInstaller --noconfirm --clean \
    --distpath "$DIST_DIR" --workpath "$WORK_DIR" "$PROJECT_ROOT/backend/findboss.spec"

echo "加入独立采集浏览器……"
mkdir -p "$APP_PATH/Contents/Resources/browser"
ditto "$BROWSER_APP" "$APP_PATH/Contents/Resources/browser/Google Chrome for Testing.app"
for notice in ABOUT LICENSE NOTICE; do
    if [ -f "$(dirname "$BROWSER_APP")/$notice" ]; then
        cp "$(dirname "$BROWSER_APP")/$notice" "$APP_PATH/Contents/Resources/browser/$notice"
    fi
done
codesign --force --deep --sign - "$APP_PATH"
echo "生成分发压缩包……"
ditto -c -k --sequesterRsrc --keepParent "$APP_PATH" "$ZIP_PATH"
echo "已生成：$APP_PATH"
echo "可发送文件：$ZIP_PATH"
