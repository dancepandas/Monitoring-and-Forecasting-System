"""FloodMind 一键启动脚本"""

import subprocess
import sys
import time
import socket
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def wait_port(port: int, timeout: int = 60):
    """等待端口就绪"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            sock.connect(("127.0.0.1", port))
            sock.close()
            return True
        except (ConnectionRefusedError, OSError):
            time.sleep(1)
    return False


def main():
    print()
    print("╔══════════════════════════════════════════╗")
    print("║   FloodMind 水文监测指挥核心 — 一键启动  ║")
    print("╚══════════════════════════════════════════╝")
    print()

    # ── 1. 后端网关 ──
    print("[1/2] 启动后端网关 (端口 15002)...")
    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "gateway.server:app", "--host", "0.0.0.0", "--port", "15002"],
        cwd=str(ROOT),
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    print("等待网关启动...")
    if wait_port(15002):
        print("网关已就绪 ✓")
    else:
        print("网关启动超时 ✗")
        return

    # ── 2. 前端 ──
    print("[2/2] 启动前端 (端口 5173)...")
    web_dir = ROOT / "web"
    subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=str(web_dir),
        shell=True,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    print("等待前端启动...")
    if wait_port(5173, timeout=90):
        print("前端已就绪 ✓")
    else:
        print("前端启动超时 ✗")
        return

    print()
    print("╔══════════════════════════════════════════╗")
    print("║  ✅ 系统启动完成                          ║")
    print("║  后端: http://localhost:15002             ║")
    print("║  前端: http://localhost:5173              ║")
    print("╚══════════════════════════════════════════╝")
    print()
    input("按 Enter 退出...")


if __name__ == "__main__":
    main()
