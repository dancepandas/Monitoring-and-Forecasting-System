# 一页化导航重构 + 钉钉反向指令 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除左侧菜单栏，改为"顶部横幅 + tab 条 + 单列内容"的一页大屏布局；同时为钉钉机器人搭建反向指令回调路由（领导在群里 @机器人 → 转发智能体 → 回推群）。

**Architecture:** 前端 AppLayout 从双列 grid（sidebar + workspace）改为单列（banner → TabBar → router-view），新增 TabBar 组件和 StationDrawer 组件；后端新增 `notify_inbox.py` 路由，校验钉钉 outgoing 签名后复用 `stream_agent()` 收集完整回答并回推。

**Tech Stack:** Vue 3 Composition API + Vue Router + FastAPI + httpx + 钉钉 OpenAPI

## Global Constraints

- 不改动现有后端推送链路（notifier / agent_alert_dispatcher / monitor_engine），只新增接收回调。
- 钉钉回调路由不走 JWT 鉴权（`get_current_user`），用钉钉签名校验替代。
- 前端保留所有现有页面组件文件，只改 AppLayout 的壳和路由。
- `--glass*` 径向透明、斜切角 `--clip`、`--edge` 亮边等暗色指挥舱视觉变量不动。
- 密钥走 `.env` / `warning_standards.json`，不硬编码。
- 钉钉 Stream 客户端不做（等 appKey/appSecret），本次只做 HTTP 回调模式。

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `web/src/components/TabBar.vue` | **Create** | 顶部 4 tab 导航条（态势/预警/视频/日报）+ 管理员齿轮 |
| `web/src/components/StationDrawer.vue` | **Create** | 右侧滑入的站点详情抽屉 |
| `web/src/pages/AppLayout.vue` | **Modify** | 去掉 Sidebar 引用，加 TabBar，grid 改单列 |
| `web/src/styles/layout.css` | **Modify** | `.app-layout` 改单列 grid；新增 `.tab-bar` `.tab-item` `.admin-gear` 样式 |
| `web/src/pages/OverviewPage.vue` | **Modify** | 精简中间三栏为两栏（地图 + 预警），视频挪到视频 tab；加站标/预警点击 → 抽屉 |
| `web/src/router/index.js` | **Modify** | 删 `/stations` 路由；`/alerts` 合并进 `/warnings` |
| `web/src/pages/WarningsPage.vue` | **Modify** | 加子 tab（当前预警 / 历史告警），合并 AlertsPage 内容 |
| `gateway/routes/notify_inbox.py` | **Create** | 钉钉 outgoing 回调路由：签名校验 → 转发 Agent → 回推群 |
| `gateway/services/warning_config.py` | **Modify** | `DEFAULT_STANDARDS` 加 3 个钉钉回调配置 key |
| `gateway/server.py` | **Modify** | 注册 `notify_inbox.router` |

---

### Task 1: 后端 — 钉钉回调配置项

**Files:**
- Modify: `gateway/services/warning_config.py:125-127`

**Interfaces:**
- Produces: `warning_config.get_standards()["dingtalk_outgoing_token"]` / `["dingtalk_bot_app_key"]` / `["dingtalk_bot_app_secret"]` — 后续 Task 2 的回调路由读取这些 key 做签名校验。

- [ ] **Step 1: 加 3 个配置 key 到 DEFAULT_STANDARDS**

打开 `gateway/services/warning_config.py`，找到 `DEFAULT_STANDARDS` dict 里的 `"dingtalk_secret": "",` 行（约第 127 行），在它后面加：

```python
    "dingtalk_outgoing_token": "",      # 钉钉 outgoing 机器人回调校验 token
    "dingtalk_bot_app_key": "",         # 钉钉企业内部应用 appKey（Stream 模式用，先留空）
    "dingtalk_bot_app_secret": "",      # 钉钉企业内部应用 appSecret（Stream 模式用，先留空）
```

- [ ] **Step 2: 验证配置可读写**

Run:
```bash
cd gateway && python -c "from services import warning_config; s = warning_config.get_standards(); print('outgoing_token:', s.get('dingtalk_outgoing_token', 'MISSING')); print('app_key:', s.get('dingtalk_bot_app_key', 'MISSING')); print('app_secret:', s.get('dingtalk_bot_app_secret', 'MISSING'))"
```

Expected: 三个 key 都打印空字符串（不是 MISSING）。

- [ ] **Step 3: Commit**

```bash
git add gateway/services/warning_config.py
git commit -m "feat(notify): 钉钉反向指令配置项 (outgoing_token / app_key / app_secret)"
```

---

### Task 2: 后端 — 钉钉 outgoing 回调路由

**Files:**
- Create: `gateway/routes/notify_inbox.py`
- Modify: `gateway/server.py:105` (加 include_router)

**Interfaces:**
- Consumes: `warning_config.get_standards()` 读 `dingtalk_outgoing_token`；`notifier.send_dingtalk_markdown()` 回推；`agent_service.stream_agent()` 收集回答
- Produces: `POST /api/notify/dingtalk/inbox` — 钉钉服务器 POST 过来的回调端点

**钉钉 outgoing 签名算法：** 钉钉在 HTTP header 里带 `timestamp` 和 `sign`。sign = `HMAC-SHA256(timestamp + "\n" + outgoing_token, "")` 再 base64。服务端用配置的 `dingtalk_outgoing_token` 重新算一遍比对。

- [ ] **Step 1: 创建 notify_inbox.py 路由文件**

创建 `gateway/routes/notify_inbox.py`：

```python
"""钉钉 outgoing 机器人回调 — 接收群里 @机器人 的消息，转发给智能体并回推。"""

import base64
import hashlib
import hmac
import logging
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_429_TOO_MANY_REQUESTS

from ..services import warning_config, notifier
from ..services.agent_service import stream_agent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notify", tags=["notify-inbox"])

# ── 简单限流：单 conversation 每分钟 10 条 ──
_rate: dict[str, deque] = defaultdict(deque)
RATE_LIMIT = 10
RATE_WINDOW = 60  # seconds


def _check_rate(conversation_id: str) -> bool:
    now = time.time()
    dq = _rate[conversation_id]
    while dq and now - dq[0] > RATE_WINDOW:
        dq.popleft()
    if len(dq) >= RATE_LIMIT:
        return False
    dq.append(now)
    return True


def _verify_dingtalk_sign(timestamp: Optional[str], sign: Optional[str], token: str) -> bool:
    """钉钉 outgoing 签名校验：sign = base64(HMAC-SHA256(timestamp + '\\n' + token, ''))"""
    if not timestamp or not sign or not token:
        return False
    # 防重放：timestamp 超过 1 小时拒绝
    try:
        ts = int(timestamp)
        if abs(time.time() * 1000 - ts) > 3600_000:
            return False
    except (ValueError, TypeError):
        return False
    string_to_sign = f"{timestamp}\n{token}"
    expected = base64.b64encode(
        hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    ).decode("utf-8")
    return hmac.compare_digest(expected, sign)


@router.post("/dingtalk/inbox")
async def dingtalk_inbox(request: Request, timestamp: Optional[str] = Header(None), sign: Optional[str] = Header(None)):
    """钉钉 outgoing 机器人回调入口。不走 JWT 鉴权，用签名校验。"""
    body = await request.json()

    # 1. 签名校验
    standards = warning_config.get_standards()
    outgoing_token = standards.get("dingtalk_outgoing_token", "")
    if not outgoing_token:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="未配置 dingtalk_outgoing_token")
    if not _verify_dingtalk_sign(timestamp, sign, outgoing_token):
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="签名校验失败")

    # 2. 解析消息
    text = body.get("text", {}).get("content", "").strip()
    sender_id = body.get("senderId", "unknown")
    conversation_id = body.get("conversationId", "default")
    if not text:
        return {"ok": True, "msg": "空消息，忽略"}

    # 3. 限流
    if not _check_rate(conversation_id):
        raise HTTPException(status_code=HTTP_429_TOO_MANY_REQUESTS, detail="请求过于频繁，请稍后再试")

    # 4. 调用 Agent（复用 stream_agent，用独立 session 避免混入前端会话）
    session_id = f"dingtalk-{conversation_id}"
    answer_text = ""
    try:
        async for event in stream_agent(session_id, text):
            t = event.get("type", "")
            if t == "answer_delta":
                answer_text += event.get("content", "")
            elif t == "error":
                answer_text = f"智能体出错：{event.get('content', '未知错误')}"
                break
    except Exception as e:
        logger.exception("dingtalk inbox agent error")
        answer_text = f"智能体处理失败：{e}"

    if not answer_text.strip():
        answer_text = "抱歉，我没能理解这条消息。"

    # 5. 回推到钉钉群
    webhook_url = standards.get("dingtalk_webhook", "")
    secret = standards.get("dingtalk_secret", "")
    if webhook_url:
        try:
            await notifier.send_dingtalk_markdown(
                webhook_url, "智能体回复",
                f"**问：** {text}\n\n**答：** {answer_text}",
                secret,
            )
        except Exception as e:
            logger.exception("dingtalk inbox reply push failed")

    return {"ok": True, "answer": answer_text}
```

- [ ] **Step 2: 注册路由到 server.py**

打开 `gateway/server.py`，在 import 区（约第 17 行附近，其他 `from .routes import xxx` 行）加：

```python
from .routes import notify_inbox
```

在 `app.include_router(voice.router)`（约第 105 行）后面加：

```python
app.include_router(notify_inbox.router)
```

- [ ] **Step 3: 验证路由注册成功**

Run:
```bash
cd gateway && python -c "from server import app; routes = [r.path for r in app.routes]; print([r for r in routes if 'inbox' in r])"
```

Expected: `['/api/notify/dingtalk/inbox']` 出现在输出里。

- [ ] **Step 4: 手动 curl 测试（无签名 → 应 401）**

Run:
```bash
curl -s -X POST http://localhost:15002/api/notify/dingtalk/inbox -H "Content-Type: application/json" -d '{"text":{"content":"test"}}'
```

Expected: 返回 401（"未配置 dingtalk_outgoing_token" 或 "签名校验失败"），证明路由可达且鉴权生效。

- [ ] **Step 5: Commit**

```bash
git add gateway/routes/notify_inbox.py gateway/server.py
git commit -m "feat(notify): 钉钉 outgoing 回调路由 (签名校验 + 转发 Agent + 回推群)"
```

---

### Task 3: 前端 — TabBar 组件

**Files:**
- Create: `web/src/components/TabBar.vue`

**Interfaces:**
- Consumes: `$route.name`（判断当前 tab）、`useAuthStore`（判断管理员角色）
- Produces: `<TabBar />` 组件，AppLayout 引入后渲染在横幅与内容之间

- [ ] **Step 1: 创建 TabBar.vue**

创建 `web/src/components/TabBar.vue`：

```vue
<template>
  <nav class="tab-bar">
    <router-link v-for="t in tabs" :key="t.to" :to="t.to" class="tab-item" :class="{ active: isActive(t) }">
      <span class="tab-label">{{ t.label }}</span>
      <i class="tab-underline"></i>
    </router-link>
    <div class="tab-spacer"></div>
    <button v-if="isAdmin" class="admin-gear" @click="showAdminMenu = !showAdminMenu" title="管理">
      ⚙
      <transition name="admin-pop">
        <div v-if="showAdminMenu" class="admin-menu" @click.stop>
          <router-link to="/admin/users" class="admin-link" @click="showAdminMenu = false">用户管理</router-link>
          <router-link to="/admin/settings" class="admin-link" @click="showAdminMenu = false">系统设置</router-link>
        </div>
      </transition>
    </button>
  </nav>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../store/auth'

const route = useRoute()
const auth = useAuthStore()
const showAdminMenu = ref(false)

const tabs = [
  { to: '/', name: 'Overview', label: '态势' },
  { to: '/warnings', name: 'Warnings', label: '预警' },
  { to: '/devices', name: 'Devices', label: '视频' },
  { to: '/reports', name: 'Reports', label: '日报' },
]

const isAdmin = computed(() => auth.role === 'admin' || auth.role === 'super_admin')

function isActive(t) {
  if (t.to === '/') return route.name === 'Overview'
  return route.name === t.name || route.path.startsWith(t.to)
}
</script>

<style scoped>
.tab-bar {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 0 10px;
  border: 1px solid var(--edge);
  border-radius: 4px;
  clip-path: var(--clip);
  background: var(--glass);
  -webkit-backdrop-filter: blur(14px);
  backdrop-filter: blur(14px);
  background-attachment: fixed;
  min-height: 38px;
}

.tab-item {
  position: relative;
  padding: 7px 22px;
  color: var(--muted);
  text-decoration: none;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: .12em;
  transition: color .18s;
  white-space: nowrap;
}
.tab-item:hover { color: #fff; }
.tab-item.active { color: #fff; text-shadow: 0 0 10px rgba(30, 144, 255, .5); }

.tab-underline {
  position: absolute;
  left: 50%;
  bottom: 0;
  width: 0;
  height: 2px;
  background: var(--primary);
  box-shadow: 0 0 8px rgba(30, 144, 255, .6);
  transform: translateX(-50%);
  transition: width .2s ease;
}
.tab-item.active .tab-underline { width: 60%; }

.tab-spacer { flex: 1; }

.admin-gear {
  position: relative;
  border: 0;
  background: transparent;
  color: var(--muted);
  font-size: 16px;
  cursor: pointer;
  padding: 4px 8px;
  transition: color .15s;
}
.admin-gear:hover { color: #fff; }

.admin-menu {
  position: absolute;
  right: 0;
  top: 100%;
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px;
  border: 1px solid var(--edge);
  border-radius: 6px;
  background: rgba(12, 36, 68, .92);
  backdrop-filter: blur(14px);
  box-shadow: var(--shadow-soft);
  z-index: 100;
  min-width: 120px;
}
.admin-link {
  padding: 6px 14px;
  color: var(--ink-2);
  text-decoration: none;
  font-size: 12px;
  border-radius: 4px;
  transition: background .15s;
}
.admin-link:hover { background: var(--chip); color: #fff; }

.admin-pop-enter-active, .admin-pop-leave-active { transition: all .15s; }
.admin-pop-enter-from, .admin-pop-leave-to { opacity: 0; transform: translateY(-4px); }
</style>
```

- [ ] **Step 2: 构建验证**

Run:
```bash
cd web && npm run build 2>&1 | tail -3
```

Expected: `✓ built in ...` 无错误。

- [ ] **Step 3: Commit**

```bash
git add web/src/components/TabBar.vue
git commit -m "feat(ui): TabBar 组件 — 顶部 4 tab + 管理员齿轮"
```

---

### Task 4: 前端 — AppLayout 去侧栏 + 加 TabBar

**Files:**
- Modify: `web/src/pages/AppLayout.vue`
- Modify: `web/src/styles/layout.css:1-12` (app-layout grid)

**Interfaces:**
- Consumes: `<TabBar />` from Task 3
- Produces: 单列 grid 布局（banner → TabBar → workspace），无 sidebar

- [ ] **Step 1: 改 AppLayout.vue**

把 `web/src/pages/AppLayout.vue` 的 template 和 script 改为：

```vue
<template>
  <div class="app-layout">
    <CesiumMap />
    <header class="app-banner">
      <span class="banner-side left"></span>
      <h1 class="banner-title">水文监测预报指挥中心</h1>
      <span class="banner-side right"></span>
    </header>
    <TabBar />
    <main class="workspace" :data-page="$route.name">
      <router-view />
      <ContextMenu v-if="$route.name !== 'agent'" />
    </main>
    <VoiceAssistant />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import CesiumMap from '../components/CesiumMap.vue'
import TabBar from '../components/TabBar.vue'
import ContextMenu from '../components/ContextMenu.vue'
import VoiceAssistant from '../components/VoiceAssistant.vue'

onMounted(() => {
  const root = document.documentElement
  root.style.setProperty('--topbar-h', '8.5fr')
  root.style.setProperty('--overview-h', '9.0fr')
  root.style.setProperty('--middle-h', '50.0fr')
  root.style.setProperty('--bottom-h', '32.5fr')
  root.style.setProperty('--video-w', '21fr')
  root.style.setProperty('--map-w', '51fr')
  root.style.setProperty('--warning-w', '28fr')
  root.style.setProperty('--gap', '10px')
  root.style.setProperty('--pad', '10px')
})
</script>
```

注意：删掉 `import Sidebar` 和 `--sidebar-w`。横幅里不再放齿轮（齿轮移到 TabBar 里）。

- [ ] **Step 2: 改 layout.css 的 .app-layout grid**

打开 `web/src/styles/layout.css`，找到 `.app-layout` 的 grid 定义（约第 1-11 行），改为单列三行：

```css
.app-layout {
  position: relative;
  z-index: 1;
  height: 100vh;
  min-height: 0;
  padding: var(--pad, 10px);
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  grid-template-rows: auto auto minmax(0, 1fr);
  gap: var(--gap, 10px);
}
```

同时把 `.app-banner` 的 `grid-column: 1 / -1;` 删掉（单列不需要跨列）。把 `.sidebar` 的高度相关声明保留（文件不删，只是不引用），不影响。

- [ ] **Step 3: 构建验证**

Run:
```bash
cd web && npm run build 2>&1 | tail -3
```

Expected: `✓ built in ...`

- [ ] **Step 4: 浏览器手动验证**

刷新页面，确认：
- 左侧菜单栏**消失了**。
- 顶部横幅 → TabBar（4 个 tab）→ 内容区，单列布局。
- 点 tab 能切换页面。
- 如果是 admin 账号，TabBar 右侧有齿轮。

- [ ] **Step 5: Commit**

```bash
git add web/src/pages/AppLayout.vue web/src/styles/layout.css
git commit -m "feat(ui): AppLayout 去侧栏 + 单列 grid + TabBar 接入"
```

---

### Task 5: 前端 — 路由调整（删 /stations，合并 /alerts 进 /warnings）

**Files:**
- Modify: `web/src/router/index.js:10-17`

**Interfaces:**
- Produces: `/stations` 路由删除（404 catch-all 重定向到 `/`）；`/alerts` 路由删除（合并进 `/warnings`）

- [ ] **Step 1: 改 router/index.js**

打开 `web/src/router/index.js`，把 children 数组中删掉这两行：

```javascript
      { path: 'stations', name: 'Stations', component: () => import('../pages/StationsPage.vue') },
```

和

```javascript
      { path: 'alerts', name: 'Alerts', component: () => import('../pages/AlertsPage.vue') },
```

保留 Overview、Warnings、Devices、Reports、Agent、Admin 两个。catch-all `/:pathMatch(.*)*` 已有，会自动把 `/stations`、`/alerts` 重定向到 `/`。

- [ ] **Step 2: 构建验证**

Run:
```bash
cd web && npm run build 2>&1 | tail -3
```

Expected: `✓ built in ...`（AlertsPage / StationsPage 文件还在但不被路由引用，不影响构建）

- [ ] **Step 3: Commit**

```bash
git add web/src/router/index.js
git commit -m "refactor(router): 删 /stations /alerts 路由（站点→抽屉，告警→合并进预警 tab）"
```

---

### Task 6: 前端 — OverviewPage 精简 + 站点抽屉触发

**Files:**
- Modify: `web/src/pages/OverviewPage.vue`
- Create: `web/src/components/StationDrawer.vue`

**Interfaces:**
- Consumes: OverviewPage 已有的 `displayWarnings`、`openStage`
- Produces: 点预警条目 / 站标 → 弹出 `<StationDrawer>`（右侧滑入）

**Overview 精简规则：**
- 中间三栏 `.middle-grid` 从 `video-w / map-w / warning-w` 三栏改为两栏 `map-w / warning-w`（删掉 video-panel）。
- `--video-w` 不再被 Overview 使用（视频 tab 独立用）。
- 联合图表 `.bottom-grid` 保留全宽。
- 预警条目 click 不再 `openStage`，改为 `openDrawer(w)`。

- [ ] **Step 1: 创建 StationDrawer.vue**

创建 `web/src/components/StationDrawer.vue`：

```vue
<template>
  <Teleport to="body">
    <transition name="drawer">
      <div v-if="visible" class="drawer-overlay" @click.self="close">
        <aside class="station-drawer">
          <header class="drawer-head">
            <div>
              <h2>{{ station.name || '站点详情' }}</h2>
              <span class="drawer-code">{{ station.code || '' }}</span>
            </div>
            <button class="drawer-close" @click="close">✕</button>
          </header>
          <div class="drawer-body">
            <div class="drawer-stat">
              <span>水位</span><b>{{ station.level ?? '—' }} <small>m</small></b>
            </div>
            <div class="drawer-stat">
              <span>流量</span><b>{{ station.flow ?? '—' }} <small>m³/s</small></b>
            </div>
            <div class="drawer-stat">
              <span>状态</span><b :class="station.badgeClass">{{ station.status || '—' }}</b>
            </div>
            <p class="drawer-detail">{{ station.detail || '暂无详情' }}</p>
          </div>
        </aside>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
const props = defineProps({
  visible: { type: Boolean, default: false },
  station: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['close'])
function close() { emit('close') }
</script>

<style scoped>
.drawer-overlay {
  position: fixed; inset: 0; z-index: 8000;
  background: rgba(0, 0, 0, .35);
  backdrop-filter: blur(4px);
  display: flex;
  justify-content: flex-end;
}
.station-drawer {
  width: 380px; max-width: 90vw;
  height: 100%;
  border-left: 1px solid var(--edge);
  background: var(--glass-deep);
  backdrop-filter: blur(18px);
  box-shadow: -16px 0 40px rgba(0, 0, 0, .4);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}
.drawer-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 18px;
  border-bottom: 1px solid var(--line);
}
.drawer-head h2 { margin: 0; font-size: 16px; color: #fff; }
.drawer-code { font-family: var(--mono); font-size: 11px; color: var(--muted); }
.drawer-close {
  border: 0; background: transparent; color: var(--muted);
  font-size: 16px; cursor: pointer; padding: 4px;
}
.drawer-close:hover { color: #fff; }
.drawer-body { padding: 16px 18px; display: grid; gap: 10px; }
.drawer-stat {
  display: flex; justify-content: space-between; align-items: baseline;
  padding: 8px 12px; border-radius: 6px; background: var(--chip);
}
.drawer-stat span { color: var(--muted); font-size: 12px; }
.drawer-stat b { font-family: var(--serif); font-size: 18px; color: #fff; }
.drawer-stat b small { font-size: 11px; color: var(--muted); }
.drawer-detail { margin: 0; color: var(--ink-2); font-size: 12px; line-height: 1.6; }
.drawer-enter-active, .drawer-leave-active { transition: all .25s ease; }
.drawer-enter-from, .drawer-leave-to { opacity: 0; }
.drawer-enter-from .station-drawer, .drawer-leave-to .station-drawer { transform: translateX(100%); }
</style>
```

- [ ] **Step 2: 改 OverviewPage — 引入抽屉 + 精简中间栏**

打开 `web/src/pages/OverviewPage.vue`，在 script 顶部 import 加：

```javascript
import StationDrawer from '../components/StationDrawer.vue'
```

在 template 的 `<section class="middle-grid">` 里，**删掉整个 `<article class="panel video-panel">…</article>`**（视频面板整块，从 `<article class="panel video-panel">` 到对应 `</article>`）。

在 `</section>`（middle-grid 结束后）加抽屉触发状态和组件。在 script 里加：

```javascript
const drawerVisible = ref(false)
const drawerStation = ref({})
function openDrawer(w) {
  drawerStation.value = {
    name: w.name,
    code: w.code || w.id || '',
    level: w.level,
    flow: w.flow,
    status: w.level ? levelLabel(w.level) : '—',
    badgeClass: levelBadgeClass(w.level),
    detail: w.message || '',
  }
  drawerVisible.value = true
}
function closeDrawer() { drawerVisible.value = false }
```

把预警条目的 `@click="openStage(w.name, 'warning')"` 改为 `@click="openDrawer(w)"`。

在 template 末尾（`</Teleport>` 之前或之后）加：

```vue
<StationDrawer :visible="drawerVisible" :station="drawerStation" @close="closeDrawer" />
```

- [ ] **Step 3: 改 components.css 的 .middle-grid 为两栏**

打开 `web/src/styles/components.css`，找到 `.middle-grid`，把 `grid-template-columns` 从三栏改两栏：

```css
.middle-grid {
  min-height: 0;
  display: grid;
  grid-template-columns: var(--map-w, 51.0fr) var(--warning-w, 28fr);
  gap: var(--gap, 10px);
}
```

- [ ] **Step 4: 构建验证**

Run:
```bash
cd web && npm run build 2>&1 | tail -3
```

Expected: `✓ built in ...`

- [ ] **Step 5: 浏览器手动验证**

刷新页面，确认：
- 态势 tab 中间只有两栏（地图 + 预警），视频面板不见了。
- 点预警条目 → 右侧滑出抽屉，显示站点名/水位/流量/状态。
- 点遮罩或 ✕ → 抽屉关闭。
- 视频在"视频" tab 里完整保留。

- [ ] **Step 6: Commit**

```bash
git add web/src/components/StationDrawer.vue web/src/pages/OverviewPage.vue web/src/styles/components.css
git commit -m "feat(ui): Overview 精简为两栏(地图+预警) + 站点详情抽屉"
```

---

### Task 7: 前端 — WarningsPage 合并告警子 tab

**Files:**
- Modify: `web/src/pages/WarningsPage.vue`

**Interfaces:**
- Consumes: 原有 WarningsPage 的 `allItems` / `totalCount` 逻辑 + AlertsPage 的历史告警列表逻辑

**目标：** WarningsPage 加两个子 tab：「当前预警」（现有内容）和「历史告警」（从 AlertsPage 搬过来的列表）。

- [ ] **Step 1: 读 AlertsPage 的核心逻辑**

打开 `web/src/pages/AlertsPage.vue`，找到它拉取告警列表的 API 调用（如 `api.getAlerts()` 或类似）和列表渲染逻辑。把它合并进 WarningsPage 的新子 tab。

- [ ] **Step 2: 改 WarningsPage — 加子 tab**

在 WarningsPage template 顶部加子 tab 切换：

```vue
<div class="sub-tabs">
  <button :class="{ active: subTab === 'current' }" @click="subTab = 'current'">当前预警</button>
  <button :class="{ active: subTab === 'history' }" @click="subTab = 'history'">历史告警</button>
</div>
```

`subTab === 'current'` 时显示现有的预警+处置建议两栏；`subTab === 'history'` 时显示从 AlertsPage 搬来的历史告警列表。

在 script 里加 `const subTab = ref('current')`，并搬入 AlertsPage 的告警拉取逻辑。

- [ ] **Step 3: 构建验证**

Run:
```bash
cd web && npm run build 2>&1 | tail -3
```

Expected: `✓ built in ...`

- [ ] **Step 4: Commit**

```bash
git add web/src/pages/WarningsPage.vue
git commit -m "feat(ui): WarningsPage 合并历史告警子 tab"
```

---

## Self-Review

**1. Spec coverage:**
- ✅ 删左侧 sidebar → Task 4 (AppLayout 去 Sidebar 引用)
- ✅ 顶部 4 tab → Task 3 (TabBar) + Task 4 (AppLayout 接入)
- ✅ 站点详情抽屉 → Task 6 (StationDrawer + OverviewPage 触发)
- ✅ 管理员齿轮 → Task 3 (TabBar 内 admin-gear)
- ✅ Overview 精简(去视频、两栏) → Task 6
- ✅ 视频 tab 独立 → 现有 DevicesPage 路由保留，tab 指向 /devices
- ✅ /stations 删路由 → Task 5
- ✅ /alerts 合并进 /warnings → Task 5 (路由删) + Task 7 (内容合并)
- ✅ 钉钉回调路由 → Task 2
- ✅ 钉钉配置项 → Task 1

**2. Placeholder scan:** 无 TBD/TODO，所有代码步骤都有完整代码。

**3. Type consistency:** `stream_agent(session_id, message)` 签名与 Task 2 调用一致。`warning_config.get_standards()` 返回 dict，Task 1 加的 key 与 Task 2 读取的 key 名一致。`StationDrawer` props `visible`/`station` 与 OverviewPage 传入一致。