@echo off
chcp 65001 >nul
title FloodMind 水文监测指挥系统

set ROOT=%~dp0

echo.
echo ╔══════════════════════════════════════════╗
echo ║   FloodMind 水文监测指挥核心 — 一键启动  ║
echo ╚══════════════════════════════════════════╝
echo.

:: ── 1. 启动后端网关 ──
echo [1/2] 启动后端网关 (端口 15002)...
start "FloodMind Gateway" cmd /c "cd /d "%ROOT%" && python -m uvicorn gateway.server:app --host 0.0.0.0 --port 15002"

:: 等网关就绪
echo 等待网关启动...
:wait_gateway
timeout /t 2 /nobreak >nul
netstat -ano | findstr ":15002" | findstr "LISTENING" >nul
if %errorlevel% neq 0 goto wait_gateway
echo 网关已就绪 ✓

:: ── 2. 启动前端 ──
echo [2/2] 启动前端 (端口 5173)...
start "FloodMind Frontend" cmd /c "cd /d "%ROOT%web" && npm run dev"

:: 等前端就绪
echo 等待前端启动...
:wait_frontend
timeout /t 2 /nobreak >nul
netstat -ano | findstr ":5173" | findstr "LISTENING" >nul
if %errorlevel% neq 0 goto wait_frontend
echo 前端已就绪 ✓

echo.
echo ╔══════════════════════════════════════════╗
echo ║  ✅ 系统启动完成                          ║
echo ║  后端: http://localhost:15002             ║
echo ║  前端: http://localhost:5173              ║
echo ║  关闭本窗口不会影响服务运行               ║
echo ╚══════════════════════════════════════════╝
echo.

pause
