# 水文监测指挥核心

流域水文监测与预报平台。实时采集水位/流量数据，集成 Chronos 时序预报和 FloodMind 智能体，支持 3D 地形可视化、语音助手、预警研判、日报生成和系统自检。

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | Python 3.14, FastAPI, uvicorn, APScheduler |
| 前端 | Vue 3, Vite, Pinia, Three.js, Cesium |
| 数据 | aiflow2 水文平台, SQLite (认证/任务), JSON 文件缓存 |
| 模型 | Chronos-2 时序预报 (Amazon) |
| AI | floodmind SDK (Hydro_Model_Agent), DashScope (qwen-plus) |
| 语音 | 阿里百炼 CosyVoice TTS + Paraformer ASR |
| 3D 地形 | Three.js GLB 渲染 + Draco 压缩 |

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
    ↓
┌───┴──────────────┐
│ 3D 地形 (Three)  │  语音助手 (WebSocket)
│ 站点全息渲染     │  CosyVoice + Paraformer
│ 预警态联动       │
└──────────────────┘
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
| 流域总览 | 水位/流量仪表盘、预警列表、历史+预报曲线，站点交互抽屉 |
| 3D 地形 | Three.js 地形模型，全息站点渲染（脉冲环+渐变光柱+光球+标签），预警态联动，hover/click 交互 |
| 监测站点 | 各站设备状态与数据详情 |
| 预警处置 | 预警+告警列表，按紧急程度排序，水位↔流量一致性智能异常裁决 |
| 模型预报 | Chronos 时序预报参数配置 |
| 视频巡检 | 视频链路状态 |
| 日报归档 | 查看/预览/导出日报（docx-preview 渲染 Word 原样），按日期归档 |
| 智能体对话 | FloodMind 助手，8 个快捷任务 |
| 系统设置 | 用户管理、系统参数配置 |

## 智能体快捷任务

最新水情 / 趋势分析 / 流量预报 / 预警研判 / 生成日报 / 多站对比 / 设备巡检 / 定时日报

右键任意面板 → "询问智能体" 可直接分析面板数据。

## 语音助手

基于阿里百炼语音服务，浏览器端通过 WebSocket 连接：
- **TTS**：CosyVoice v3-flash，语音合成播报
- **ASR**：Paraformer realtime-v2，实时语音转文字
- 复用 `dashscope_api_key`，无需额外密钥

## 配置项 (`gateway/config.py`)

```python
station_codes = "00125,00230,00231,00234"   # 测站列表
default_device_code = "FD000848891909"       # 默认设备
collector_interval = 300                     # 采集间隔(秒)
cache_ttl = 600                              # 缓存过期(秒)
aligned_context_max = 72                     # Chronos 上下文长度
aligned_fill_max = 10                        # 对齐填充上限

# Agent LLM
agent_model_name = "qwen-plus"
agent_temperature = 0.3
agent_max_tokens = 4096

# 语音
tts_model = "cosyvoice-v3-flash"
tts_voice = "longanyang"
asr_model = "paraformer-realtime-v2"
```

## 数据说明

- 数据源：aiflow2，每 5 分钟同步一次
- 缓存：`gateway/data/hydro_cache.json` (raw + aligned 双轨)
- 预报输入：aligned 层等间隔时序，空缺由 Chronos 填充
- 实测值 vs 预报值通过 `source` 字段区分

## 3D 地形模型

- 构建脚本：`scripts/build_terrain_model.py`（处理 DEM → mesh → GLB → Draco 压缩）
- 地理数据处理：`scripts/download_geodata.py`、`scripts/process_dem.py`
- 水系图简化：`scripts/simplify_hydro.py`、`scripts/simplify_admin.py`
- 输出：`web/public/models/terrain.glb` + `terrain_meta.json`
- 前端渲染：`TerrainModel3D.vue` (Three.js) + `localTerrainProvider.js`

