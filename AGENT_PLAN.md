# FloodMind 智能体集成方案（最终版）

## 核心原则
**Agent 不写脚本、不画图。只做三件事：** 理解意图 → 调工具获取结构化数据 → 解释结果。前端负责渲染。

**例外：** 日报生成用固定 Python 脚本，定时任务用独立调度器。

## 工具清单（16 个）

### 数据查询（7 个）
| 工具 | 返回 | 对标前端 |
|------|------|---------|
| `query_water_level` | `[{time, waterLevel}]` | 趋势图 |
| `query_flow` | `[{time, virtualFlow}]` | 流量线 |
| `query_latest` | `[{code, level, flow}]` | 概览卡片 |
| `list_stations` | `[{code, name, lat, lng}]` | 站点列表 |
| `compare_stations` | 多站对比 | 对比图 |
| `query_devices` | `[{id, name, online}]` | 设备统计 |
| `query_video_status` | `[{cam, online, ai}]` | 视频巡检 |

### 预警处置（2 个）
| 工具 | 返回 |
|------|------|
| `list_warnings` | `[{title, level, desc}]` |
| `generate_disposal` | `{steps: [{action, reason}]}` |

### 预报分析（2 个）
| 工具 | 返回 |
|------|------|
| `run_forecast` | `{predictions, peak_time, peak_value}` |
| `analyze_trend` | `{trend, change_rate, anomalies}` |

### 报告生成（2 个）
| 工具 | 实现 |
|------|------|
| `generate_report` | 调 `gateway/scripts/generate_report.py` → Word 文档 |
| `query_reports` | 扫描 output 目录，返回已有报告列表 |

### 文件检索（2 个，从 floodmind SDK 引入）
| 工具 | 用途 |
|------|------|
| `Glob` | 文件匹配搜索 |
| `Grep` | 文件内容搜索 |

### 定时任务（3 个，自建轻量调度器）
| 工具 | 功能 | 典型用法 |
|------|------|---------|
| `CreateScheduledTask` | 创建定时任务 | "每天早上8点生成日报" |
| `ListScheduledTasks` | 列出所有定时任务 | "有哪些定时任务" |
| `CancelScheduledTask` | 取消定时任务 | "取消日报定时任务" |

**调度器实现：** `gateway/services/scheduler.py`
- 基于 `APScheduler`（AsyncIOScheduler）
- 任务存 SQLite（复用现有数据库）
- 支持 cron 表达式：`0 8 * * *`（每天 8 点）、`0 */6 * * *`（每 6 小时）
- 任务类型：`generate_report`、`run_forecast`、`check_warnings`
- 启动时自动恢复未完成的任务

## 报告生成脚本：`gateway/scripts/generate_report.py`
```
输入: --type daily|monthly|event --station 00106 --date 2026-06-15
处理: 调 aiflow 取数据 → 调 chronos 取预报 → python-docx 生成 Word
输出: ./reports/日报_仙桃_20260615.docx
返回: {path, filename, size, summary}
```

## 架构
```
Vue 前端 (:5173)
  │ POST /api/chat (NDJSON stream)
  ▼
FastAPI (:15000)
  ├── routes/agent.py (prefix="/api")
  │     ├── /chat → AgentService.stream()
  │     ├── /init, /sessions, /models, /upload, /files
  │     └── /permission/respond
  │
  ├── services/
  │     ├── agent_service.py   → Agent(llm, tools, bare=True) 包装
  │     ├── agent_tools.py     → 16 个 build_agent_tool
  │     ├── session_store.py   → 内存会话 CRUD
  │     └── scheduler.py       → APScheduler 定时任务
  │
  └── scripts/
        └── generate_report.py → 固定脚本，生成 Word 日报
```

## 实施步骤

### 步骤 1：依赖与配置
- `gateway/.env` 加 DashScope 凭据
- `gateway/config.py` 加 agent 配置字段
- `pip install -e Hydro_Model_Agent python-docx apscheduler`

### 步骤 2：5 个新文件
- `gateway/services/session_store.py`
- `gateway/services/agent_tools.py`（16 个工具）
- `gateway/services/agent_service.py`（AgentService + 事件映射）
- `gateway/services/scheduler.py`（APScheduler + SQLite 持久化）
- `gateway/scripts/generate_report.py`

### 步骤 3：重写路由 + 注册调度器
- `gateway/routes/agent.py` — prefix="/api"，全部端点，启动时初始化 scheduler
- 删 `gateway/services/floodmind_client.py`

### 步骤 4：前端补漏
- `web/src/api/agent.js` 补缺失函数 + 对接 /api/scheduled-tasks

### 步骤 5：验证
- curl `/api/chat` → NDJSON 流
- 前端 AgentPage 完整对话
- 定时任务创建/列出/取消
