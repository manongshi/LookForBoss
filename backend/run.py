import argparse

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="启动 FindBoss 前后端一体服务，自动创建 SQLite 数据库")
    parser.add_argument("--port", type=int, default=8000, help="访问端口，默认 8000")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("端口必须在 1 到 65535 之间")

    print(f"工作台访问地址：http://127.0.0.1:{args.port}", flush=True)
    # 采集浏览器和运行中的任务由同一个进程管理。
    uvicorn.run("app.main:app", host="127.0.0.1", port=args.port, workers=1)


if __name__ == "__main__":
    main()
