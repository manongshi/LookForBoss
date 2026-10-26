#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
PYTHON_BIN="$VENV_DIR/bin/python"

if [ ! -x "$PYTHON_BIN" ]; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo "未找到 Python 3，请先安装 Python 3.10 或以上版本。"
    exit 1
  fi
  echo "正在创建 Python 虚拟环境……"
  python3 -m venv "$VENV_DIR"
fi

echo "正在安装后端依赖……"
"$PYTHON_BIN" -m pip install -r "$PROJECT_DIR/backend/requirements.txt"

# 浏览器上下文与运行任务由一个进程持有，不启用多 worker 或自动重载。
exec "$PYTHON_BIN" "$PROJECT_DIR/backend/run.py" "$@"
