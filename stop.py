"""FloodMind 一键关闭脚本"""

import subprocess
import sys

print("正在关闭 FloodMind 系统...")

# 关闭网关
subprocess.run(
    ['wmic', 'process', 'where',
     "CommandLine like '%uvicorn gateway.server:app%'", 'delete'],
    capture_output=True,
)
print("后端网关已关闭 ✓")

# 关闭前端 (通过端口找 PID)
result = subprocess.run(
    ['netstat', '-ano'], capture_output=True, text=True
)
for line in result.stdout.splitlines():
    if ":5173" in line and "LISTENING" in line:
        parts = line.strip().split()
        pid = parts[-1]
        subprocess.run(['wmic', 'process', 'where', f'ProcessId={pid}', 'delete'], capture_output=True)
        print("前端已关闭 ✓")
        break

print("系统已关闭。")
input("按 Enter 退出...")
