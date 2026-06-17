# 水文监测指挥核心

流域水文监测与预报平台。实时采集水位/流量数据，集成 Chronos 时序预报和 FloodMind 智能体，支持预警研判、日报生成和系统自检。

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | Python 3.14, FastAPI, uvicorn, APScheduler |
| 前端 | Vue 3, Vite, marked |
| 数据 | aiflow2 水文平台, SQLite (认证), JSON 文件缓存 |
| 模型 | Chronos-2 时序预报 (Amazon) |
| AI | DashScope (qwen-plus), floodmind SDK |

## 架构

```
aiflow2 (外部) → collector 子进程 (5min)
                    ↓
            hydro_cache.json (三层: raw / aligned / forecast)
                    ↓
    ┌───────────────┼───────────────┐
    ↓               ↓               ↓
  REST API      Agent 工具      定时任务
  (FastAPI)    (24 个工具)    (日报/周报/自检)
    ↓               ↓
  Vue 前端      FloodMind 智能体
```

## 快速启动

### 1. 后端

```bash
cd gateway
pip install -r requirements.txt

# 配置 aiflow_profile.env (aiflow2 账号) 和 .env (DashScope API Key)
cp aiflow_profile.env.example aiflow_profile.env
cp .env.example .env

# 启动
python -m uvicorn gateway.server:app --host 0.0.0.0 --port 15002
```

### 2. 前端

```bash
cd web
npm install
npx vite --host
```

浏览器打开 `http://localhost:5173`，默认账号 `admin / admin123`。

## 页面功能

| 页面 | 功能 |
|------|------|
| 流域总览 | 水位/流量仪表盘、预警列表、历史+预报曲线 |
| 监测站点 | 各站设备状态与数据详情 |
| 预警处置 | 预警+告警列表，按紧急程度排序 |
| 模型预报 | Chronos 时序预报参数配置 |
| 视频巡检 | 视频链路状态 |
| 日报归档 | 查看/预览/导出日报，按日期归档 |
| 智能体对话 | FloodMind 助手，8 个快捷任务 |

## 智能体快捷任务

最新水情 / 趋势分析 / 流量预报 / 预警研判 / 生成日报 / 多站对比 / 设备巡检 / 定时日报

右键任意面板 → "询问智能体" 可直接分析面板数据。

## 配置项 (`gateway/config.py`)

```python
station_codes = "00106,00107,00108"   # 测站列表
default_device_code = "FD000489923695" # 默认设备
collector_interval = 300              # 采集间隔(秒)
cache_ttl = 600                       # 缓存过期(秒)
aligned_context_max = 72              # Chronos 上下文长度
```

## 数据说明

- 数据源：aiflow2，每 5 分钟同步一次
- 缓存：`gateway/data/hydro_cache.json` (raw + aligned 双轨)
- 预报输入：aligned 层等间隔时序，空缺由 Chronos 填充
- 实测值 vs 预报值通过 `source` 字段区分
