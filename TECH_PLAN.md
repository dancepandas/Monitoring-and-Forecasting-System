# 水文监测指挥核心 — 完整架构方案 v2.0

> 日期：2026-06-15
> 状态：方案确认后开工

---

## 目录

1. [系统全景](#1-系统全景)
2. [前端架构](#2-前端架构)
3. [后端架构](#3-后端架构)
4. [认证与权限](#4-认证与权限)
5. [数据流与 API 设计](#5-数据流与-api-设计)
6. [Chronos 预报模型接入](#6-chronos-预报模型接入)
7. [FloodMind 智能体接入](#7-floodmind-智能体接入)
8. [实施排期](#8-实施排期)

---

## 1. 系统全景

```
┌─────────────────────────────────────────────────────────────────┐
│  React 前端 (monitoring-dashboard)                              │
│  • 登录页 / 流域总览 / 监测站点 / 预警处置 / 模型预报 /         │
│    视频巡检 / 日报归档 / FloodMind 对话                          │
│  • 复用原型 clay/moss/river 设计 token                           │
│  • 三种角色：普通用户 / 管理员 / 超级管理员                       │
└──────────────┬──────────────────────────────────────────────────┘
               │ HTTP + JWT Token
               │ localhost:15000
┌──────────────▼──────────────────────────────────────────────────┐
│  统一后端 (gateway/server.py)  ←  新建，独立项目                 │
│  Flask / FastAPI                                               │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 认证模块                                                  │   │
│  │ POST /api/auth/login     → 用户名密码 → JWT Token         │   │
│  │ POST /api/auth/register  → 注册（管理员操作）              │   │
│  │ GET  /api/auth/me        → 当前用户信息+角色               │   │
│  │ 用户存储：SQLite（user 表含 role 字段）                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 数据网关（代理 aiflow2 + Token 自动管理）                  │   │
│  │ GET  /api/data/level?station=00106&begin=...&end=...    │   │
│  │ GET  /api/data/flow?station=00106&begin=...&end=...     │   │
│  │ GET  /api/data/station/list    → 站点清单                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 预报编排（调用 Chronos）                                    │   │
│  │ POST /api/forecast/run    → aiflow2取历史 → Chronos预测   │   │
│  │ GET  /api/forecast/result → 取缓存结果                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 智能体代理（转发 FloodMind）                                │   │
│  │ POST /api/agent/chat     → 转发 FloodMind NDJSON          │   │
│  │ GET  /api/agent/sessions  → 会话列表                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 权限中间件                                                  │   │
│  │ • 普通用户：查看所有数据，使用对话                           │   │
│  │ • 管理员：  查看+配置+注册新用户+手动触发预报               │   │
│  │ • 超级管理员：管理员权限+系统配置+删除用户                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 静态文件服务（React 打包后的 dist 目录）                    │   │
│  └─────────────────────────────────────────────────────────┘   │
└──────────────┬──────────────────────────────────────────────────┘
               │
      ┌────────┼────────┬──────────────┐
      │        │        │              │
┌─────▼──┐ ┌──▼───┐ ┌──▼──────┐ ┌────▼──────────┐
│aiflow2 │ │Chronos│ │FloodMind│ │ SQLite (本地)  │
│:9999   │ │FastAPI│ │:13014   │ │ 用户/角色/会话  │
│水位流量│ │:15001 │ │智能对话 │ │                │
└────────┘ └───────┘ └─────────┘ └───────────────┘
```

**不碰的代码仓库：**
- `D:\chengs\9.project\Hydro_Model_Agent` — 只通过 HTTP API 调用
- `D:\chengs\9.project\Chronos` — 只通过 HTTP API 调用

---

## 2. 前端架构

### 2.1 技术选型

| 层级 | 选择 | 原因 |
|------|------|------|
| 框架 | React 18 + TypeScript | 登录态、路由、状态管理必须有框架 |
| 构建 | Vite | 快速，默认支持 React |
| CSS | TailwindCSS 4 + 原型 CSS 变量 | 原型 token 直接映射，不需要重新设计 |
| 路由 | React Router v7 | 6 个页面 + 登录页 |
| 状态 | Zustand | 轻量，用户信息 + 站点数据全局共享 |
| HTTP | fetch + 自定义 hook | 统一处理 loading/error/empty |
| 图表 | 保持原型 SVG / ECharts 按需引入 | 预报过程线用 ECharts，简单图表继续 SVG |
| 地图 | 保持原型 SVG 流域图 | 后续可切 Mapbox GL |

### 2.2 页面与角色权限矩阵

| 页面 | 路径 | 普通用户 | 管理员 | 超级管理员 |
|------|------|---------|--------|-----------|
| 登录 | `/login` | ✅ | ✅ | ✅ |
| 流域总览 | `/` | ✅ | ✅ | ✅ |
| 监测站点 | `/stations` | ✅ | ✅ | ✅ |
| 预警处置 | `/warnings` | ✅ | ✅ | ✅ |
| 模型预报 | `/forecast` | ✅ 查看 | ✅ 手动触发 | ✅ |
| 视频巡检 | `/devices` | ✅ | ✅ | ✅ |
| 日报归档 | `/reports` | ✅ | ✅ | ✅ |
| 智能体对话 | `/agent` | ✅ | ✅ | ✅ |
| 用户管理 | `/admin/users` | ❌ | ❌ | ✅ |
| 系统配置 | `/admin/settings` | ❌ | ✅ | ✅ |

### 2.3 组件树

```
App
├── LoginPage          (/login)
└── ProtectedLayout    (需要登录)
    ├── Sidebar         (复用原型 .sidebar HTML/CSS)
    ├── Topbar          (复用原型 .topbar HTML/CSS)
    └── <Outlet>
        ├── Overview     (/)           — KPI tiles + 地图 + 预警 + 预报 + 视频 + 智能体
        ├── Stations     (/stations)   — 站点列表 + 详情
        ├── Warnings     (/warnings)   — 预警列表
        ├── Forecast     (/forecast)   — 预报图表 + 情景模拟
        ├── Devices      (/devices)    — 视频巡检网格
        ├── Reports      (/reports)    — 日报列表
        ├── Agent        (/agent)      — FloodMind 全屏对话
        ├── AdminUsers   (/admin/users)
        └── AdminSettings(/admin/settings)
```

### 2.4 CSS 策略

不丢弃原型设计，CSS 变量直接迁移：

```css
/* 从 index.html :root 直接复制，一字不改 */
:root {
  --paper: #f5f5f7;
  --paper-soft: #fbfbfd;
  --clay: #b96b55;
  --moss: #66746b;
  --river: #6f8f9e;
  --amber: #b58b3f;
  --danger: #a94f43;
  --ok: #5f7567;
  --serif: Georgia, "Times New Roman", "Songti SC", serif;
  --sans: "Aptos", "Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif;
  --mono: "Cascadia Mono", "SFMono-Regular", Consolas, monospace;
  /* ... 其余全部照搬 */
}
```

加上 Tailwind 做布局辅助（grid/flex/spacing），颜色、字体、圆角、阴影全部用原型 token。

### 2.5 前端项目结构

```
monitoring-dashboard/
├── index.html              # Vite 入口
├── package.json
├── vite.config.ts
├── tailwind.config.ts
├── src/
│   ├── main.tsx
│   ├── App.tsx             # 路由配置
│   ├── styles/
│   │   ├── tokens.css      # 原型 CSS 变量（从 index.html :root 照搬）
│   │   ├── global.css      # body/sidebar/topbar/panel 等全局样式
│   │   └── tailwind.css    # Tailwind 入口
│   ├── store/
│   │   ├── auth.ts         # 登录态 Zustand store
│   │   └── data.ts         # 站点数据 Zustand store
│   ├── api/
│   │   ├── client.ts       # 统一 fetch（baseURL、Token 注入、错误处理）
│   │   ├── auth.ts         # 登录/注册 API
│   │   ├── data.ts         # 水位/流量 API
│   │   ├── forecast.ts     # 预报 API
│   │   └── agent.ts        # FloodMind 聊天 API
│   ├── hooks/
│   │   ├── usePolling.ts   # 轮询 hook
│   │   └── useAuth.ts      # 认证 hook
│   ├── components/
│   │   ├── Sidebar.tsx     # 侧边栏（从原型 HTML 移植）
│   │   ├── Topbar.tsx      # 顶栏
│   │   ├── KpiTile.tsx     # 指标卡片
│   │   ├── MapPanel.tsx    # 流域地图（SVG）
│   │   ├── WarningList.tsx # 预警列表
│   │   ├── ForecastPanel.tsx # 预报图表
│   │   ├── VideoGrid.tsx   # 视频巡检
│   │   ├── AgentPanel.tsx  # 智能体对话
│   │   ├── StageModal.tsx  # 全屏模态
│   │   └── ProtectedRoute.tsx # 登录守卫
│   └── pages/
│       ├── LoginPage.tsx
│       ├── OverviewPage.tsx    # 流域总览
│       ├── StationsPage.tsx    # 监测站点
│       ├── WarningsPage.tsx    # 预警处置
│       ├── ForecastPage.tsx    # 模型预报
│       ├── DevicesPage.tsx     # 视频巡检
│       ├── ReportsPage.tsx     # 日报归档
│       ├── AgentPage.tsx       # 智能体对话
│       ├── AdminUsersPage.tsx  # 用户管理
│       └── AdminSettingsPage.tsx # 系统配置
```

---

## 3. 后端架构

### 3.1 技术选型

| 层级 | 选择 | 原因 |
|------|------|------|
| 框架 | FastAPI (Python) | 异步、自动 OpenAPI 文档、Pydantic 校验 |
| 数据库 | SQLite + SQLAlchemy | 用户/角色 数据量极小，无需单独数据库 |
| 认证 | JWT (PyJWT) | 轻量，无需单独认证服务 |
| 密码 | bcrypt | 标准 |
| 前端服务 | 直接 serve React 打包产物 | 单一端口部署 |

### 3.2 项目结构

```
D:\chengs\9.project\Monitoring-and-Forecasting-System\
│
├── prototype/             # 原 6 个 HTML 原型不动，保留参考
│   ├── index.html
│   ├── stations.html
│   ├── warnings.html
│   ├── forecast.html
│   ├── devices.html
│   └── reports.html
│
├── gateway/               # 新建后端
│   ├── server.py          # FastAPI 主入口
│   ├── config.py          # 配置（端口、密钥、aiflow2 账号）
│   ├── database.py        # SQLite + SQLAlchemy
│   ├── models.py          # User 表 ORM
│   ├── schemas.py         # Pydantic 请求/响应模型
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── jwt.py         # JWT 生成/验证
│   │   └── middleware.py   # 权限中间件
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py        # 登录/注册/用户管理
│   │   ├── data.py        # aiflow2 代理路由
│   │   ├── forecast.py    # Chronos 编排
│   │   └── agent.py       # FloodMind 代理
│   ├── services/
│   │   ├── __init__.py
│   │   ├── aiflow_client.py  # aiflow2 HTTP 客户端
│   │   ├── chronos_client.py # Chronos HTTP 客户端
│   │   └── floodmind_client.py # FloodMind HTTP 客户端
│   ├── .env               # 账号密码等敏感信息
│   ├── requirements.txt
│   └── seed.py            # 初始化管理员账号
│
├── web/                   # 新建前端（Vite + React）
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   └── src/               # 见 §2.5 结构
│
├── TECH_PLAN.md
└── station/               # 站点映射表（已有）
    ├── station_info_view.csv
    └── calibration_fore_config_flow_view.csv
```

### 3.3 后端 API 一览

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| POST | `/api/auth/login` | 公开 | 用户名+密码 → JWT |
| POST | `/api/auth/register` | 管理员 | 创建新用户 |
| GET | `/api/auth/me` | 登录 | 当前用户信息+角色 |
| DELETE | `/api/auth/users/{id}` | 超管 | 删除用户 |
| GET | `/api/auth/users` | 管理员 | 用户列表 |
| GET | `/api/data/stations` | 登录 | 站点清单（含阈值、设备码） |
| GET | `/api/data/level` | 登录 | 站点水位数据 |
| GET | `/api/data/flow` | 登录 | 站点流量数据（含视频URL） |
| GET | `/api/data/latest` | 登录 | 所有站点最新一条数据（用于KPI） |
| POST | `/api/forecast/run` | 管理员 | 触发 Chronos 预测 |
| GET | `/api/forecast/result` | 登录 | 取预测结果缓存 |
| POST | `/api/agent/chat` | 登录 | 代理 FloodMind 流式对话 |
| GET | `/api/agent/sessions` | 登录 | 会话列表 |

---

## 4. 认证与权限

### 4.1 User 表

```sql
CREATE TABLE user (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  display_name TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'user',  -- 'user' | 'admin' | 'super_admin'
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 4.2 角色权限表

| 操作 | user | admin | super_admin |
|------|------|-------|-------------|
| 查看所有页面 | ✅ | ✅ | ✅ |
| 使用智能体对话 | ✅ | ✅ | ✅ |
| 手动触发预报 | ❌ | ✅ | ✅ |
| 创建新用户 | ❌ | ✅ | ✅ |
| 配置系统参数 | ❌ | ✅ | ✅ |
| 删除用户 | ❌ | ❌ | ✅ |
| 修改他人角色 | ❌ | ❌ | ✅ |

### 4.3 预置账号

系统首次启动时自动创建（`seed.py`）：

| 用户名 | 密码 | 角色 | 说明 |
|--------|------|------|------|
| admin | admin123 | super_admin | 超级管理员 |
| operator | operator123 | admin | 管理员 |

普通账号由管理员在用户管理页面创建。

---

## 5. 数据流与 API 设计

### 5.1 最新数据轮询（首页 KPI）

```
前端每 15 秒:
  GET /api/data/latest → 后端并发查所有站点最新水位/流量 → 返回聚合结果

返回:
{
  "stations": [
    { "code": "00106", "name": "湖北-仙桃", "waterLevel": 25.75, "waterFlow": null, "measureTime": "..." },
    ...
  ],
  "warnings": [
    { "code": "00106", "level": "normal", "msg": "距警戒水位 9.35m" }
  ]
}
```

### 5.2 历史过程线（预报页面）

```
GET /api/data/level?stationCode=00106&beginTime=2026-06-08&endTime=2026-06-15
→ 返回时间序列 [{"measureTime": "...", "waterLevel": 25.75}, ...]
```

### 5.3 视频地址获取

```
GET /api/data/flow?stationCode=00106&isMedia=1
→ 返回 videoUrl / videoUrls[]，网关拼接完整的可访问URL
```

---

## 6. Chronos 预报模型接入

### 6.1 现状

```
Chronos FastAPI 服务:
  位置：D:\chengs\9.project\Chronos
  启动：api/main.py (FastAPI + uvicorn)
  端口：默认 8000（可改为 15001）
  
  POST /predict
  {
    "mode": "univariate",           // 或 past_covariates / future_covariates
    "data": [
      {"Time": "2026-06-14 00:00", "Flow": 1840, "Rain": 12},
      ...
    ],
    "prediction_length": 72,        // 预测步长
    "target": "Flow",               // 目标列
    "timestamp_column": "Time",
    "context_length": 72
  }
  
  响应:
  {
    "mode": "univariate",
    "predictions": [1860, 1920, ...],   // 72个中位数预测值
    "quantiles": {
      "q0.1": [1820, ...],
      "q0.5": [1860, ...], 
      "q0.9": [1950, ...]
    },
    "timestamps": ["2026-06-15T01:00:00", ...]
  }
```

### 6.2 集成方式

**不动 Chronos 代码**，只通过 HTTP 调用：

```
后端编排流程:
  1. 前端 POST /api/forecast/run { stationCode: "00106", hours: 72 }
  2. 后端从 aiflow2 取该站最近 72 小时的历史水位/流量
  3. 格式化为 Chronos 要求的 [{Time, Flow}] 格式
  4. 调用 Chronos POST /predict
  5. 拿到 predictions + quantiles + timestamps
  6. 缓存到内存/文件，返回前端
```

### 6.3 前端展示

预测结果绑定到预报页面的 SVG/Canvas 过程线：
- 实线 = 历史实测数据
- 虚线 = Chronos 中位数预测
- 浅色带 = q0.1 ~ q0.9 置信区间

---

## 7. FloodMind 智能体接入

### 7.1 现状

```
FloodMind Flask 服务:
  位置：D:\chengs\9.project\Hydro_Model_Agent
  启动：floodmind web（端口 13014）
  
  POST /api/chat
  { "session_id": "dashboard", "message": "分析仙桃站趋势" }
  → NDJSON 流式响应
```

### 7.2 集成方式

**不动 Hydro_Model_Agent 代码**，后端做代理转发：

```
前端:
  POST /api/agent/chat { session_id, message }
  → ReadableStream 逐行读取 NDJSON

后端 gateway/routes/agent.py:
  → 转发到 http://localhost:13014/api/chat
  → 透传 NDJSON 流
```

---

## 8. 实施排期

### 总时间：4 周

| 阶段 | 任务 | 时间 |
|------|------|------|
| **Week 1** | 后端基础 | |
| | FastAPI 项目骨架 + SQLite + User 模型 | 1天 |
| | JWT 认证 + 角色中间件 + 登录/注册 API | 1.5天 |
| | aiflow2 客户端封装 + 数据代理路由 | 1.5天 |
| | Chronos 客户端封装 + 预报编排 | 1天 |
| **Week 2** | 前端基础 | |
| | Vite + React + Tailwind + 路由 | 1天 |
| | 原型 CSS token 迁移 + Sidebar/Topbar 组件 | 1.5天 |
| | 登录页 + 认证 hook + ProtectedRoute | 1天 |
| | 流域总览页（KPI + 预警列表 接真实数据） | 1.5天 |
| **Week 3** | 前端页面 | |
| | 监测站点 / 预警处置 / 视频巡检 子页面 | 2天 |
| | 模型预报页 + Chronos 过程线图表 | 1.5天 |
| | 智能体对话页 + NDJSON 流式 | 1.5天 |
| **Week 4** | 收尾 | |
| | 日报归档 / 用户管理 / 系统配置 | 1.5天 |
| | 全流程联调 + 边界处理 + 错误状态 | 2天 |
| | 打包部署（构建 + gateway serve 静态文件） | 1.5天 |

---

## 附录：部署方式

### 开发环境

```bash
# 后端
cd gateway
pip install -r requirements.txt
python server.py          # 启动 :15000

# Chronos（如果需要预报功能）
cd D:\chengs\9.project\Chronos
python -m uvicorn api.main:app --port 15001

# FloodMind（如果需要智能体功能）
cd D:\chengs\9.project\Hydro_Model_Agent
floodmind web              # 启动 :13014

# 前端
cd web
npm install
npm run dev                # 启动 :5173
```

### 生产部署

```bash
# 前端构建
cd web && npm run build    # 输出到 web/dist/

# 后端直接 serve 前端 + API
# gateway/server.py 已内置静态文件服务
cd gateway && python server.py --serve-static ../web/dist
# 访问 http://localhost:15000
```
