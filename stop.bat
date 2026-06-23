@echo off
chcp 65001 >nul
title 关闭 FloodMind

echo 正在关闭 FloodMind 系统...

:: 关闭网关 (端口 15002)
wmic process where "CommandLine like '%%uvicorn gateway.server:app%%'" delete >nul 2>&1
echo 后端网关已关闭

:: 关闭 Vite 前端 (端口 5173)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173" ^| findstr "LISTENING"') do (
    wmic process where "ProcessId=%%a" delete >nul 2>&1
)
echo 前端已关闭

echo 系统已关闭。
pause
