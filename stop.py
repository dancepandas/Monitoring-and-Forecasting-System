"""FloodMind 一键关闭脚本"""

import os
import platform
import signal
import subprocess
import sys


def _kill_by_command(pattern: str):
    """跨平台按命令行匹配杀进程。"""
    system = platform.system()
    if system == "Windows":
        subprocess.run(
            ['wmic', 'process', 'where', f"CommandLine like '%{pattern}%'", 'delete'],
            capture_output=True,
        )
    else:
        # POSIX: ps + grep + kill
        try:
            result = subprocess.run(
                ['ps', 'aux'],
                capture_output=True, text=True
            )
            for line in result.stdout.splitlines():
                if pattern in line and 'python' in line.lower():
                    parts = line.split()
                    if len(parts) > 1:
                        try:
                            pid = int(parts[1])
                            os.kill(pid, signal.SIGTERM)
                        except (ValueError, ProcessLookupError):
                            pass
        except Exception:
            pass


def _kill_by_port(port: int):
    """跨平台按端口杀监听进程。"""
    system = platform.system()
    if system == "Windows":
        result = subprocess.run(
            ['netstat', '-ano'], capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                pid = parts[-1]
                subprocess.run(['wmic', 'process', 'where', f'ProcessId={pid}', 'delete'], capture_output=True)
                print(f"端口 {port} 进程已关闭")
                break
    else:
        # POSIX: lsof 或 ss
        for cmd in (
            ['lsof', '-ti', f'tcp:{port}'],
            ['ss', '-ltnp', f'sport = :{port}'],
        ):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0 and result.stdout.strip():
                    for token in result.stdout.split():
                        try:
                            pid = int(token)
                            os.kill(pid, signal.SIGTERM)
                            print(f"端口 {port} 进程 {pid} 已关闭")
                            return
                        except (ValueError, ProcessLookupError):
                            pass
            except Exception:
                pass


print("正在关闭 FloodMind 系统...")

# 关闭网关
_kill_by_command("uvicorn gateway.server:app")
print("后端网关已关闭")

# 关闭 collector 子进程
_kill_by_command("gateway.services.collector")

# 关闭前端 (通过端口找 PID)
_kill_by_port(5173)

print("系统已关闭。")
input("按 Enter 退出...")
