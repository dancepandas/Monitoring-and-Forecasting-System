# 一页化导航重构 + 钉钉反向指令 设计

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除左侧菜单栏,将系统重构为"一页展示 + 顶部 tab"的指挥大屏形态;同时为钉钉机器人搭建反向指令通道(领导在群里 @机器人 → 转发智能体 → 回推群)。

**Architecture:**
- 前端:删 `.sidebar`,顶部横幅下方加 4 个 tab(态势/预警/视频/日报);站点详情改为右侧抽屉;管理员入口改为横幅右侧齿轮。
- 后端:新增 `POST /api/notify/dingtalk/inbox` 回调路由,校验钉钉签名 → 转发 Agent → 回推群;配置项加到 `warning_config.py`。

**Tech Stack:** Vue 3 + Vue Router + FastAPI + 钉钉 OpenAPI

## Global Constraints

- 不改动现有后端推送链路(notifier / dispatcher / monitor_engine),只新增接收回调。
- 钉钉回调路由不走 JWT 鉴权,用钉钉签名校验。
- 前端保留所有现有页面组件,只改导航壳(AppLayout + Sidebar → TabBar)。
- `--glass*` 径向透明、斜切角、冷光亮边等暗色指挥舱视觉变量不动。

---

## 一、前端导航重构

### 现状
- 左侧 `.sidebar` 7 个菜单 + 2 个管理员页,9 个独立路由。
- Overview 是"驾驶舱"雏形(数值卡 + 视频/地图/预警三栏 + 联合图表)。

### 目标布局
```
┌──────────────────────────────────────────────────────┐
│         水文监测预报指挥中心  (横幅,居中)      ⚙admin │
├──────────────────────────────────────────────────────┤
│ [态势] [预警] [视频] [日报]              (tab 条)     │
├──────────────────────────────────────────────────────┤
│                                                      │
│              tab 内容区(router-view)                │
│                                                      │
└──────────────────────────────────────────────────────┘
                                    🤖 (右下角机器人,常驻)
```

### 变更点

**删:**
- `Sidebar.vue` 不再渲染(保留文件,AppLayout 不引入)。
- `.app-layout` 的 `grid-template-columns: var(--sidebar-w) 1fr` → 改为单列。
- `.sidebar` 相关 CSS 保留但不生效(删组件引用即可)。

**加:**
- 新组件 `TabBar.vue`:横幅下方一条 tab 条,4 个 tab。
  - 态势 → `/`(OverviewPage,精简:去掉视频栏,视频挪到视频 tab)
  - 预警 → `/warnings`(WarningsPage + AlertsPage 合并入口,内部用子 tab 或合并列表)
  - 视频 → `/devices`(DevicesPage)
  - 日报 → `/reports`(ReportsPage)
- `AppLayout.vue` 结构:横幅 → TabBar → `<router-view>`(无 sidebar)。
- 管理员齿轮:横幅右侧 `<button class="admin-gear">⚙</button>`,点开下拉菜单(用户管理 / 系统设置),只有 `super_admin` / `admin` 角色可见。

**改:**
- `.app-layout` grid 改单列:`grid-template-rows: auto auto minmax(0, 1fr)`(横幅 / tab / 内容)。
- `.workspace` 不再有 `grid-template-columns`,直接 `minmax(0, 1fr)` 占满。
- OverviewPage 精简:去掉视频巡检面板(挪到视频 tab),中间三栏改为两栏(地图 + 预警),联合图表全宽。
- `StationsPage` 不再作为独立路由 —— 站点详情改为 OverviewPage 内点站标 / 预警条目 → 右侧抽屉 `<StationDrawer>`。

**路由调整:**
- `/stations` → 删除独立路由,改为 OverviewPage 内抽屉。
- `/alerts` → 合并进 `/warnings`(WarningsPage 内加子 tab:当前预警 / 历史告警)。
- 其余路由保留(`/`、`/warnings`、`/devices`、`/reports`、`/agent`、`/admin/*`)。

### 站点详情抽屉 `<StationDrawer>`

- 从右侧滑入(`transform: translateX(100%) → 0`),宽度 380px,半透明玻璃底。
- 内容:站点名 + 状态徽章 + 水位/流量/时间序列迷你图 + 处置记录列表 + "写处置"按钮。
- 触发:OverviewPage 地图站标 click / 预警条目 click。
- 关闭:点遮罩 / 点 × / Esc。

---

## 二、钉钉反向指令通道

### 现状
- 推送链路完整:`monitor_engine`(5 分钟阈值检查)→ `agent_alert_dispatcher`(Agent 分析)→ `notifier.push_alert()`(推钉钉/企微)。
- **无接收回调**:领导在钉钉群里 @机器人,系统收不到。

### 目标
```
钉钉群 — @机器人 → 钉钉服务器 POST /api/notify/dingtalk/inbox
                                    ↓
                         签名校验(timestamp + token)
                                    ↓
                         解析消息内容(text)
                                    ↓
                         调 Agent 流式接口(复用 /api/chat 逻辑)
                                    ↓
                         收集完整回答
                                    ↓
                         notifier.send_dingtalk_markdown() 回推群
```

### 变更点

**新增文件:**
- `gateway/routes/notify_inbox.py`:钉钉回调接收路由。
  - `POST /api/notify/dingtalk/inbox`
    - 校验:`timestamp` + `sign`(HMAC-SHA256,钉钉 outgoing 机器人签名算法)。
    - 解析 body:提取 `text.content`(用户消息)、`senderId`、`conversationId`。
    - 调用 Agent:复用 `agent.py` 里的 chat 逻辑(非 HTTP 转发,直接调内部函数),用独立 session ID `dingtalk-bot-{conversationId}`。
    - 回推:收集完整回答 → `notifier.send_dingtalk_markdown(webhook, secret, title, answer)`。
  - 限流:单 conversation 每分钟 10 条(内存计数器)。

**修改文件:**
- `gateway/services/warning_config.py`:`DEFAULT_STANDARDS` 加 3 个 key:
  - `dingtalk_outgoing_token`(回调校验 token,默认空)
  - `dingtalk_bot_app_key`(企业内部应用 appKey,默认空,Stream 模式用,先留空)
  - `dingtalk_bot_app_secret`(企业内部应用 appSecret,默认空)
- `gateway/server.py`:注册 `notify_inbox.router`。

**不做(等 key):**
- 钉钉 Stream 长连客户端(需 appKey/appSecret 才能测,HTTP 回调先跑通)。
- 企微反向指令(需公网 IP)。
- 前端会话与钉钉会话打通。

### 安全
- 回调路由**排除在 JWT 鉴权之外**(钉钉服务器无登录态)。
- 签名校验失败 → 403。
- 白名单:可选,后续加钉钉 IP 段。
- 限流:内存 dict,`{conversationId: [timestamp,...]}`,超限返回 429。

---

## 三、不做清单(YAGNI)

- ❌ 不改现有推送链路(notifier / dispatcher / monitor_engine)。
- ❌ 不改现有 Overview 数据拉取逻辑(refreshData / cache)。
- ❌ 不做钉钉 Stream 客户端(等 key)。
- ❌ 不做企微反向指令。
- ❌ 不做"未读消息中心"前端界面(钉钉群本身就是消息中心)。
- ❌ 不删 Sidebar.vue 文件(只不引用,保留以备回退)。

---

## 四、测试策略

- **前端**:构建通过(`npm run build`) + 手动验证 4 个 tab 切换、站点抽屉滑入/关闭、管理员齿轮显隐。
- **后端**:钉钉回调路由可用 curl 模拟测试(手动构造签名 body)。
- **集成**:等管理员给出钉钉企业内部应用 key 后,端到端验证群内 @机器人 → 回复。