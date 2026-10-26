#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
if [ ! -f backend/.env ]; then
  cp backend/.env.example backend/.env
fi
if [ ! -f backend/static/index.html ]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "缺少内置前端资源，请先安装 Node.js，再重新执行 bash setup.sh。"
    exit 1
  fi
  npm --prefix frontend ci
  npm --prefix frontend run build
fi
echo "安装完成，执行 bash run-backend.sh 后访问 http://127.0.0.1:8000。"
