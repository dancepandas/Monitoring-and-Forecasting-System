# 水文监测指挥核心 — 技术对接方案

> 版本：v1.0  
> 日期：2026-06-14  
> 状态：待接口确认后开工

---

## 目录

1. [架构概览](#1-架构概览)
2. [数据平台 API](#2-数据平台-api)
3. [FloodMind 智能体](#3-floodmind-智能体)
4. [前端改造方案](#4-前端改造方案)
5. [桌面端方案](#5-桌面端方案)
6. [时间排期](#6-时间排期)
7. [待确认事项](#7-待确认事项)
8. [附录：接口速查](#8-附录接口速查)

---

## 1. 架构概览

```
┌──────────────────────────────────────────────────────────┐
│  浏览器 (index.html + 子页面)                             │
│  • 水位/流量/预警 KPI                                     │
│  • Mapbox 3D 站点地图                                     │
│  • ECharts 过程线                                         │
│  • 视频巡检面板                                           │
│  • FloodMind 对话                                         │
└────────────┬─────────────────────────────────────────────┘
             │ fetch()  所有请求走统一网关
             │ localhost:13014
┌────────────▼─────────────────────────────────────────────┐
│  FloodMind Flask (扩展为统一 API 网关)                    │
│                                                          │
│  /api/gateway/auth           → 登录 aiflow2 获取 Token    │
│  /api/gateway/level          → 转发 水位数据              │
│  /api/gateway/flow           → 转发 流量数据              │
│  /api/gateway/evaporate      → 转发 蒸发数据              │
│  /api/gateway/field          → 转发 流场仪数据            │
│  /api/gateway/video          → 转发 视频地址              │
│  /api/chat                   → 已有，智能体对话           │
│  /api/sessions               → 已有，会话管理             │
│                                                          │
│  职责：                                                   │
│  • 自动管理 JWT Token（登录 + 过期续签）                  │
│  • 解决 CORS 跨域                                         │
│  • 请求参数校验与格式化                                    │
│  • 统一错误处理                                           │
└────────────┬─────────────────────────────────────────────┘
             │ HTTP POST + JSON
             │ Authorization: Bearer <token>
┌────────────▼─────────────────────────────────────────────┐
│  aiflow2.dashuiyun.cn:9999                               │
│                                                          │
│  /prod-api/loginNoVerify         登录获取 Token           │
│  /prod-api/level/reportDataPage  站点水位（表11）         │
│  /prod-api/level/originalDataFilterPage  水位原始（表5）  │
│  /prod-api/flow/reportDataPage    站点流量（表9）         │
│  /prod-api/flow/originalDataFilterPage  流量原始（表3）   │
│  /prod-api/client/monitorEvaporate/page  蒸发站（表1）    │
│  /prod-api/client/monitorField/page  流场仪（表2）        │
│  /prod-api/third/compareMeasureDataPage  第三方水位（表6）│
│  ... 更多接口见附录                                       │
└──────────────────────────────────────────────────────────┘
```

**关键设计决策**：
- 前端**不直连** aiflow2，全部通过 FloodMind Flask 网关中转
- 这样做的好处：Token 集中管理、CORS 零问题、前端零敏感信息
- 网关只需要在 `web_server.py` 中追加 ~150 行路由代码

---

## 2. 数据平台 API

### 2.1 认证

| 项目 | 值 |
|------|-----|
| 地址 | `POST https://aiflow2.dashuiyun.cn:9999/prod-api/loginNoVerify` |
| 参数 | `{"username": "admin", "password": "admin6666"}` |
| 返回 | `{"code": 200, "token": "eyJ..."}` |
| 使用方式 | HTTP Header: `Authorization: Bearer <token>` |

**网关需要做**：
- 应用启动时自动登录获取 Token
- Token 过期（401）时自动重登
- 每次请求自动注入 `Authorization` 头

### 2.2 核心数据接口

#### 站点水位（表 11）

```
POST /prod-api/level/reportDataPage
```

| 入参 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `count` | int | 否 | 每页条数，默认 10 |
| `page` | int | 否 | 页码，默认 1 |
| `request.beginTime` | string | 是 | 开始时间 `yyyy-MM-dd HH:mm:ss.SSS` |
| `request.endTime` | string | 是 | 结束时间 |
| `request.stationCode` | string | 是 | 站码 |
| `request.isMedia` | int | 否 | 是否需要视频地址：0-否, 1-是 |
| `request.measureResult` | int | 否 | 1-成功, 0-失败, 2-全部 |

返回关键字段：`originalWaterLevel`, `reportLevel`, `stationCode`, `stationName`, `measureTime`, `pictureUrl`

#### 站点流量（表 9）

```
POST /prod-api/flow/reportDataPage
```

参数同上。  
返回关键字段：`waterFlow`(m³/s), `waterLevel`(m), `waterVelocity`(m/s), `waterWidth`(m), `videoUrl`, `videoUrls[]`

#### 流量原始数据（表 3）

```
POST /prod-api/flow/originalDataFilterPage
```

| 入参 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `request.beginTime` | string | 是 | 开始时间 |
| `request.endTime` | string | 是 | 结束时间 |
| `request.stationCode` | string | 是 | 站码 |
| `request.deviceCode` | string | 是 | 逻辑设备码 |

返回额外字段：`virtualFlow`, `flowStivSpeedLineVos[]`（测速线）, `deviceVideoInfoVo`, `sectionPointVos[]`（断面图）

#### 水位原始数据（表 5）

```
POST /prod-api/level/originalDataFilterPage
```

返回额外字段：`originalWaterLevel`, `dynamicWaterLevel`, `virtualGaugePoints`(水尺坐标), `rawDataUrl`(原始视频/图片)

#### 流场仪（表 2）

```
POST /prod-api/client/monitorField/page
```

参数：`days`(查询天数), `stationCode`  
返回：`flowFieldDiagram`(流场图), `algorithmResult`, `waterLevel`

#### 蒸发站（表 1）

```
POST /prod-api/client/monitorEvaporate/page
```

返回：`dateEvaporateNum`(时段蒸发量 mm), `dayEvaporateNum`(日蒸发量 mm), `dayRainNum`(日降雨量 mm), `waterLevelBefore/After`

### 2.3 视频获取方式

视频**不是独立流媒体接口**。视频地址嵌入在流量/水位数据返回中：

| 接口 | 视频字段 |
|------|---------|
| 站点流量（表9） | `videoUrl`, `videoUrls[]` (CameraVideoFile 数组) |
| 流量原始（表3） | `videoUrl`, `videoUrlSecond`, `videoUrlThird`, `videoUrls[]`, `deviceVideoInfoVo` |
| 水位原始（表5） | `pictureUrl`, `rawDataUrl` |

**前端处理**：
- 拿到 URL 后直接用 `<video src>` 或 `<img>` 加载
- 需要处理 CORS（由网关统一解决）
- 如果 URL 是相对路径，网关需要拼接完整地址

### 2.4 数据刷新策略

由于接口是 REST（无 WebSocket 推送），前端需要定时轮询：

| 面板 | 轮询间隔 | 理由 |
|------|---------|------|
| 顶部 KPI（水位/流量） | 10–30 秒 | 核心监控指标 |
| 预警列表 | 30 秒 | 预警状态变化 |
| 站点地图 | 60 秒 | 站点状态标记 |
| 模型预报 | 手动/5 分钟 | 预报非实时 |
| 视频巡检 | 手动/按需 | 视频流按需加载 |

**优化方向**（后续）：
- 如果数据平台支持，可改为 SSE 推送
- 或者在后端加一层 Redis 缓存，减少对 aiflow2 的压力

---

## 3. FloodMind 智能体

### 3.1 基本信息

| 项目 | 值 |
|------|-----|
| 位置 | `D:\chengs\9.project\Hydro_Model_Agent` |
| 语言 | Python 3.10+ |
| 框架 | Flask + NDJSON 流式响应 |
| 默认端口 | `13014` |
| 启动命令 | `floodmind web` 或 `python main.py` |
| LLM 后端 | OpenAI 兼容接口（DashScope/DeepSeek 等） |

### 3.2 核心能力

- **Native Agent Runtime**：工具调用循环、流式输出、DAG 工作流
- **Skill 系统**：13 个内置 Skill（水文模型、数据科学、文档生成等）
- **MCP 协议**：FastMCP Server，可连接外部工具
- **双层记忆**：短期对话 + 长期记忆 + LLM 压缩
- **水文模型**：敖江水文模型、Chronos/TSLM 时序预测
- **RAG 知识库**：ChromaDB + BGE Embedding
- **文档生成**：Excel/Word/PDF/PPT
- **定时任务**：每日重复/一次性调度

### 3.3 已有关键 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/chat` | POST | 流式聊天（NDJSON），核心交互接口 |
| `/api/init` | POST | 初始化 Agent 会话 |
| `/api/sessions` | GET | 会话列表 |
| `/api/sessions/<id>` | GET/DELETE | 会话详情/删除 |
| `/api/sessions/<id>/events` | GET | 事件追溯（Cursor 分页） |
| `/api/session/config` | POST | 配置模型/参数 |
| `/api/upload` | POST | 文件上传 |
| `/api/health` | GET | 健康检查 |
| `/api/models` | GET | 可用模型列表 |

### 3.4 `/api/chat` 接口细节

**请求**：
```json
{
  "session_id": "default",
  "message": "分析城西站未来 72 小时水位趋势",
  "enable_reasoning": true
}
```

**响应**：NDJSON 流式，每行一个 JSON 事件
```
{"type":"text","content":"正在读取实时数据..."}
{"type":"tool_call","name":"query_water_level","args":{"station":"00601"}}
{"type":"tool_result","name":"query_water_level","result":{"waterLevel":7.84}}
{"type":"text","content":"城西站当前水位 7.84m..."}
{"type":"done"}
```

**前端对接**：用 `fetch()` + `ReadableStream` 逐行解析 NDJSON。

### 3.5 需要新增的网关路由

在 `web_server.py` 中追加以下路由（约 150 行）：

```
/api/gateway/auth             POST   → aiflow2 loginNoVerify
/api/gateway/level            POST   → aiflow2 level/reportDataPage
/api/gateway/flow             POST   → aiflow2 flow/reportDataPage
/api/gateway/flow/original    POST   → aiflow2 flow/originalDataFilterPage
/api/gateway/level/original   POST   → aiflow2 level/originalDataFilterPage
/api/gateway/field            POST   → aiflow2 client/monitorField/page
/api/gateway/evaporate        POST   → aiflow2 client/monitorEvaporate/page
/api/gateway/third-level      POST   → aiflow2 third/compareMeasureDataPage
/api/gateway/flow/speedline   POST   → aiflow2 flow/reportSpeedLineDataPage (表10)
```

每个路由逻辑相同：校验参数 → 注入 JWT → 转发 aiflow2 → 返回结果。

---

## 4. 前端改造方案

### 4.1 工程化

当前原型是单文件 HTML，需要拆分为工程化项目：

```
monitoring-dashboard/
├── index.html              # 入口
├── package.json
├── vite.config.js
├── src/
│   ├── main.js             # 应用入口
│   ├── App.jsx             # 根组件（路由切换）
│   ├── api/
│   │   ├── client.js       # 统一 fetch 封装（baseURL、错误处理、重试）
│   │   ├── auth.js         # Token 管理
│   │   ├── level.js        # 水位 API
│   │   ├── flow.js         # 流量 API
│   │   └── agent.js        # FloodMind 聊天 API
│   ├── hooks/
│   │   ├── usePolling.js   # 通用轮询 Hook
│   │   ├── useStation.js   # 站点数据 Hook
│   │   └── useAgent.js     # 智能体会话 Hook
│   ├── components/
│   │   ├── Sidebar.jsx     # 左侧导航
│   │   ├── Topbar.jsx      # 顶部栏
│   │   ├── KpiTile.jsx     # 指标卡片
│   │   ├── MapPanel.jsx    # 地图面板（Mapbox）
│   │   ├── WarningList.jsx # 预警列表
│   │   ├── ForecastChart.jsx # 预报图表（ECharts）
│   │   ├── VideoGrid.jsx   # 视频巡检
│   │   ├── AgentPanel.jsx  # 智能体对话
│   │   └── StageModal.jsx  # 全屏查看
│   ├── pages/
│   │   ├── Overview.jsx    # 流域总览（原 index.html）
│   │   ├── Stations.jsx    # 监测站点
│   │   ├── Warnings.jsx    # 预警处置
│   │   ├── Forecast.jsx    # 模型预报
│   │   ├── Devices.jsx     # 视频巡检
│   │   └── Reports.jsx     # 日报归档
│   └── styles/
│       ├── tokens.css      # CSS 变量（从 index.html 提取）
│       └── global.css      # 全局样式
└── electron/               # 桌面端（可选）
    └── main.js             # Electron 主进程
```

### 4.2 每个面板数据绑定

| 面板 | 数据来源 | 核心接口 | 更新方式 |
|------|---------|---------|---------|
| KPI 水位/流量 | 站点水位表11 + 站点流量表9 | `gateway/level` `gateway/flow` | 轮询 15s |
| KPI 模型可信度 | FloodMind Agent 返回 | `/api/chat` | 手动触发 |
| KPI 待处置预警 | 预警逻辑（前端根据水位阈值计算） | — | 同步水位更新 |
| 站点地图 | 表11 最新水位 + 阈值判断 | `gateway/level` | 轮询 60s |
| 预警列表 | 前端水位 vs 阈值 + 流量环比 | — | 同步水位/流量 |
| 模型预报图 | FloodMind 时序预测 | `/api/chat` (触发模型) | 手动 |
| 视频巡检 | 表9 `videoUrl` / 表5 `rawDataUrl` | 随流量/水位数据返回 | 按需 |
| 智能体对话 | FloodMind `/api/chat` NDJSON | `/api/chat` | 实时流式 |

### 4.3 组件状态规范

每个数据驱动组件必须覆盖四种状态：

| 状态 | 表现 |
|------|------|
| `loading` | Skeleton 骨架屏（匹配面板形状） |
| `empty` | 美观空态 + 引导文案 |
| `error` | 错误码 + 重试按钮 + 上次成功数据（如有） |
| `success` | 正常数据渲染 |

### 4.4 站点编码映射

待确认：需要一份数据平台的 `stationCode` → 页面站名映射表。当前原型中的站点：

```
龙门站    → ?
城西站    → ?
泵闸站    → ?
中心站    → ?
南桥站    → ?
```

这些需要对应 aiflow2 中的 `stationCode`（如 `00265`, `00601` 等）。

---

## 5. 桌面端方案

### 5.1 推荐：Electron

| 项目 | 说明 |
|------|------|
| 入口 | `electron/main.js` — 创建 BrowserWindow，加载本地 HTML |
| 打包 | `electron-builder`，输出 `.exe`（Windows） |
| 包体积 | ~120MB（含 Chromium） |
| 额外工作 | 3 天（写 main.js + 配置打包 + 测试） |

### 5.2 备选：Tauri

| 项目 | 说明 |
|------|------|
| 包体积 | ~15MB |
| 额外工作 | 5–8 天（需要 Rust 基础 + Tauri API 学习） |

推荐先用 Electron 快速出桌面版，后续按需迁移 Tauri。

---

## 6. 时间排期

以单人全职（4–6h/天有效产出）计算：

### 第一阶段：基础设施（4 天）

| # | 任务 | 天数 |
|---|------|------|
| 1.1 | 获取站点清单，确认 stationCode ↔ 站名映射 | 0.5 |
| 1.2 | 验证 aiflow2 网络可达性 + 视频 URL 可播放性 | 0.5 |
| 1.3 | FloodMind Flask 新增网关路由（8 条） | 1.5 |
| 1.4 | 前端 Vite 项目搭建 + 拆组件 + CSS 变量提取 | 1.5 |

### 第二阶段：核心面板（7 天）

| # | 任务 | 天数 |
|---|------|------|
| 2.1 | 统一 API 层：fetch 封装、Token、错误、重试 | 1 |
| 2.2 | KPI 面板 + 实时轮询 | 1 |
| 2.3 | 预警列表 + 阈值逻辑 | 1 |
| 2.4 | 站点地图动态化（Mapbox marker 绑定数据） | 1.5 |
| 2.5 | 模型预报图表（ECharts 过程线） | 1.5 |
| 2.6 | 视频面板（URL 绑定 + 懒加载 + 全屏） | 1 |

### 第三阶段：智能体 + 子页面（7 天）

| # | 任务 | 天数 |
|---|------|------|
| 3.1 | 智能体面板对接 `/api/chat` NDJSON 流式 | 2 |
| 3.2 | 监测站点页（stations.html）接数据 | 1.5 |
| 3.3 | 预警处置页 | 1 |
| 3.4 | 模型预报页 | 1 |
| 3.5 | 视频巡检页 | 0.5 |
| 3.6 | 日报归档页 | 1 |

### 第四阶段：联调 & 打磨（3 天）

| # | 任务 | 天数 |
|---|------|------|
| 4.1 | 全流程联调：数据 → 网关 → 前端 | 1.5 |
| 4.2 | 异常处理：断线、超时、空数据、Token 过期 | 1 |
| 4.3 | 性能：轮询间隔优化、视频懒加载、Mapbox 图层优化 | 0.5 |

### 第五阶段：桌面端（3 天，可选）

| # | 任务 | 天数 |
|---|------|------|
| 5.1 | Electron 壳 + 打包配置 | 1.5 |
| 5.2 | 桌面特性：窗口管理、托盘、自启动 | 1 |
| 5.3 | 打包测试 + 安装包验证 | 0.5 |

### 汇总

```
                 Week 1    Week 2    Week 3    Week 4
基础设施  ████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
核心面板  ░░░░████████████████████░░░░░░░░░░░░░
智能体+页 ░░░░░░░░░░░░░░░░░░░░░░███████████████
联调打磨  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░█████
桌面端    ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░█████

网页版可演示: Week 3 末 (~15 天)
网页版稳定:   Week 4 中 (~18 天)
桌面版可用:   Week 4 末 (~21 天)
```

---

## 7. 待确认事项

> 这些需要你和其他方沟通确认后才能精确排期。

### 7.1 高优先级（阻塞开工）

| # | 问题 | 说明 |
|---|------|------|
| 1 | **站点清单** | aiflow2 有哪些 `stationCode`？和页面上的站名如何对应？需要一份映射表 |
| 2 | **网络可达性** | 从开发机能否直连 `aiflow2.dashuiyun.cn:9999`？如果能，ping 延迟大概多少？ |
| 3 | **视频 URL 格式** | `videoUrl` 返回的是完整 `https://...` 还是相对路径？实际格式（mp4/m3u8/其他）？ |
| 4 | **视频 CORS** | aiflow2 的 CORS 策略是什么？如果禁止跨域，必须走网关代理 |

### 7.2 中优先级（影响设计）

| # | 问题 | 说明 |
|---|------|------|
| 5 | **数据更新频率** | 水位/流量数据大概多久写入一次？（决定轮询间隔） |
| 6 | **预报模型接口** | 除了已有的时序数据，FloodMind 的水文模型（敖江/Chronos/TSLM）是否已经能跑？输出格式是什么？ |
| 7 | **LLM API Key** | 智能体的 DashScope/DeepSeek Key 已经有了吗？还是需要申请？ |
| 8 | **部署环境** | 最终运行在哪？内网大屏？值班 PC？公网 SaaS？ |

### 7.3 低优先级（后期优化）

| # | 问题 | 说明 |
|---|------|------|
| 9 | **WebSocket 支持** | 数据平台有没有 WebSocket/SSE 推送能力？没有的话后期是否需要自己加？ |
| 10 | **历史数据范围** | 需要展示多久的历史数据？7 天？30 天？ |
| 11 | **用户权限** | 是否需要多用户登录？目前只有 admin 账号 |

---

## 8. 附录：接口速查

### 8.1 数据平台完整接口清单

| 序号 | 表名 | 地址 | 核心字段 |
|------|------|------|---------|
| 1 | 蒸发站原始 | `/prod-api/client/monitorEvaporate/page` | 蒸发量, 降雨量, 水位 |
| 2 | 流场仪原始 | `/prod-api/client/monitorField/page` | 流场图, 算法结果, 水位 |
| 3 | 流量原始 | `/prod-api/flow/originalDataFilterPage` | 流量, 流速, 视频 URL, 测速线, 断面 |
| 4 | 流量测速线 | `/prod-api/flow/reportSpeedLineDataPage` | 测速线流速, 水深, 面积 |
| 5 | 水位原始 | `/prod-api/level/originalDataFilterPage` | 原始水位, 动态水位, 水尺坐标 |
| 6 | 第三方水位 | `/prod-api/third/compareMeasureDataPage` | 比测水位 |
| 7 | 测流设备示范 | 暂无接口 | — |
| 8 | 图像水位示范 | 暂无接口 | — |
| 9 | 站点流量 | `/prod-api/flow/reportDataPage` | 流量, 水位, 流速, 河宽, 视频 |
| 10 | 站点流量测速线 | `/prod-api/flow/reportSpeedLineFilterPage` | 测速线数据 |
| 11 | 站点水位 | `/prod-api/level/reportDataPage` | 水位, 站名, 图片 |

### 8.2 FloodMind API 清单

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/chat` | POST | 流式聊天（NDJSON） |
| `/api/init` | POST | 初始化会话 |
| `/api/sessions` | GET | 会话列表 |
| `/api/sessions/<id>` | GET | 会话详情 |
| `/api/sessions/<id>` | DELETE | 删除会话 |
| `/api/sessions/<id>/events` | GET | 事件列表（Cursor 分页） |
| `/api/session/config` | POST | 配置模型/参数 |
| `/api/upload` | POST | 文件上传 |
| `/api/health` | GET | 健康检查 |
| `/api/models` | GET | 可用模型 |
| `/api/logs` | GET | 日志 |

### 8.3 三条数据流示例

**获取城西站最新水位**：
```
POST /api/gateway/level
{
  "count": 1,
  "page": 1,
  "request": {
    "stationCode": "00601",
    "beginTime": "2026-06-14 00:00:00",
    "endTime": "2026-06-14 23:59:59"
  }
}
→ { "data": [{ "originalWaterLevel": 7.84, "reportLevel": 7.84, ... }] }
```

**获取龙门站流量（含视频）**：
```
POST /api/gateway/flow
{
  "count": 1,
  "page": 1,
  "request": {
    "stationCode": "00095",
    "beginTime": "2026-06-14 00:00:00",
    "endTime": "2026-06-14 23:59:59",
    "isMedia": 1
  }
}
→ { "data": [{ "waterFlow": 1840, "waterLevel": 6.18, "videoUrl": "https://..." }] }
```

**智能体分析**：
```
POST /api/chat
{ "session_id": "dashboard", "message": "城西站当前水位 7.84m，距阈值 0.06m，分析趋势并给出闸门调度建议" }
→ NDJSON 流: {"type":"text","content":"正在读取实时数据..."} ...
```

---

> **开工前最后确认**：站点清单 + 网络可达性 + 视频 URL 格式。拿到这三项就可以开始第一阶段。
