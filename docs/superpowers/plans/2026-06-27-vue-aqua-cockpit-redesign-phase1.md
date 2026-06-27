# Vue 前端「天空蓝驾驶舱」阶段一实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `web/src` 首页 `OverviewPage` 及全局设计令牌系统从暖色编辑风改造为天空蓝浅色玻璃驾驶舱，解决趋势图 SVG 文字畸变问题，并建立可复用的语义化 token 体系。

**Architecture:** 通过重写 `tokens.css` 建立单一事实来源的 CSS 变量；`layout.css` / `components.css` 将硬编码暖色替换为语义令牌；`TrendChart.vue` 改用 `ResizeObserver` + 真实像素笛卡尔坐标；`CesiumMap.vue` 调整场景参数匹配主题；`OverviewPage.vue` 移除地图浮层面板并把 AI 解读融入趋势面板。

**Tech Stack:** Vue 3 (Composition API), Vite, Cesium.js, flv.js, CSS Custom Properties.

## Global Constraints

- 不改业务逻辑、API、数据流。
- 不引入新依赖。
- 不动根目录静态原型 `index.html`。
- 阶段一只改首页 + 全局令牌/样式，其他页面仅扫描并替换明显硬编码暖色。
- 构建必须通过 `npm run build`。
- 所有颜色必须来自 `tokens.css` 或语义等价常量；禁用 `#b96b55`、`#2d2923`、`rgba(37,33,28,…)`、`rgba(200,111,76,…)` 等旧暖色。
- 保持响应式断点 `≤1180px` / `≤720px` 不破版；Cesium 地图始终为背景。

---

## File Structure

| 文件 | 职责 | 变更性质 |
|---|---|---|
| `web/src/styles/tokens.css` | 全局设计令牌：颜色、字体、阴影、半径 | 全量重写 |
| `web/src/styles/layout.css` | App shell、Sidebar、Topbar、按钮、工作区栅格 | 大量替换 |
| `web/src/styles/components.css` | 面板、KPI tile、风险列表、站点、图表、视频、Agent 对话等 | 大量替换 |
| `web/src/components/TrendChart.vue` | 历史/预报过程线 SVG | 重构渲染方式 + 配色 |
| `web/src/components/CesiumMap.vue` | 3D 地球场景与站点标记 | 调参 + pin 颜色 |
| `web/src/pages/AppLayout.vue` | 注入 layout-tuner CSS 变量 | 调整 fr 比例 |
| `web/src/pages/OverviewPage.vue` | 首页模板与数据 | 移除地图浮层面板，AI 解读移至趋势面板 |
| `web/src/components/Topbar.vue` | 顶部标题栏 | 增加等宽分区编号与辉光接缝 |
| `web/src/components/SystemStatus.vue` | 系统状态 pill | 扫描硬编码色 |
| `web/src/components/AgentChatPanel.vue` | 智能体对话面板 | 扫描硬编码色 |
| `web/src/components/ContextMenu.vue` | 右键菜单 | 扫描硬编码色 |

---

## Task 1: 重写 `tokens.css`

**Files:**
- Modify: `web/src/styles/tokens.css:1-78`

**Interfaces:**
- Produces: 全部 CSS 自定义属性，供 `layout.css`、`components.css`、各 Vue 组件使用。

- [ ] **Step 1: 备份原文件并写入新令牌**

```bash
cp web/src/styles/tokens.css web/src/styles/tokens.css.bak
```

用以下内容完全替换 `web/src/styles/tokens.css`:

```css
:root {
  /* 背景 */
  --bg: #EEF4F9;

  /* 玻璃面板 */
  --glass: rgba(255, 255, 255, .40);
  --glass-strong: rgba(255, 255, 255, .60);
  --glass-deep: rgba(255, 255, 255, .82);

  /* 文字层级 */
  --ink: #0F172A;
  --ink-2: #334155;
  --muted: #64748B;
  --faint: #94A3B8;

  /* 线条/描边 */
  --line: rgba(15, 23, 42, .07);
  --line-strong: rgba(15, 23, 42, .14);
  --edge: rgba(255, 255, 255, .65);

  /* 品牌与数据色 */
  --primary: #0284C7;
  --primary-600: #0369A1;
  --primary-soft: rgba(2, 132, 199, .13);
  --accent: #6366F1;
  --accent-soft: rgba(99, 102, 241, .12);
  --water: #0EA5E9;
  --water-soft: rgba(14, 165, 233, .15);

  /* 状态 / 水利四级预警 */
  --danger: #DC2626;
  --danger-soft: rgba(220, 38, 38, .14);
  --orange: #EA580C;
  --orange-soft: rgba(234, 88, 12, .14);
  --warn: #CA8A04;
  --warn-soft: rgba(202, 138, 4, .14);
  --info: #0EA5E9;
  --ok: #10B981;
  --ok-soft: rgba(16, 185, 129, .13);
  --offline: #94A3B8;

  /* 阴影（冷色化） */
  --shadow: 0 18px 50px rgba(30, 64, 124, .08);
  --shadow-soft: 0 8px 24px rgba(30, 64, 124, .06);
  --shadow-panel: 0 6px 20px rgba(30, 64, 124, .05);
  --ring: 0 0 0 3px rgba(2, 132, 199, .20);

  /* 半径 */
  --radius-xl: 28px;
  --radius-lg: 22px;
  --radius-md: 14px;
  --radius-sm: 10px;

  /* 字体栈 */
  --serif: "Cambria", "Times New Roman", "Noto Serif SC", "SimSun", serif;
  --sans: "Inter", "PingFang SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif;
  --mono: "SF Mono", "JetBrains Mono", "Cascadia Code", Consolas, "Courier New", monospace;
}

* { box-sizing: border-box; }

html, body { height: 100%; overflow: hidden; min-height: 100%; }

body {
  margin: 0;
  color: var(--ink);
  font-family: var(--sans);
  background:
    radial-gradient(circle at 18% 0%, rgba(255, 255, 255, .96), transparent 24rem),
    radial-gradient(circle at 82% 12%, rgba(14, 165, 233, .10), transparent 26rem),
    radial-gradient(circle at 50% 100%, rgba(2, 132, 199, .05), transparent 34rem),
    linear-gradient(180deg, #f5fbff 0%, #eaf4fa 46%, #e0eef7 100%);
}

body::before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  background:
    linear-gradient(rgba(15, 23, 42, .018) 1px, transparent 1px),
    linear-gradient(90deg, rgba(15, 23, 42, .014) 1px, transparent 1px);
  background-size: 42px 42px;
  -webkit-mask-image: linear-gradient(to bottom, rgba(0, 0, 0, .36), transparent 72%);
  mask-image: linear-gradient(to bottom, rgba(0, 0, 0, .36), transparent 72%);
  z-index: 0;
}

body::after {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  opacity: .08;
  mix-blend-mode: multiply;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.72' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.55'/%3E%3C/svg%3E");
  z-index: 0;
}

button, input { font: inherit; }
button { color: inherit; }

#app {
  position: relative;
  z-index: 1;
}
```

- [ ] **Step 2: 验证无旧暖色残留**

Run:
```bash
grep -En "#b96b55|#66746b|#6f8f9e|#b58b3f|#2d2923|rgba\(37,33,28|rgba\(200,111,76" web/src/styles/tokens.css || echo "No warm colors found"
```
Expected: 输出 `No warm colors found`。

- [ ] **Step 3: 运行构建检查语法**

Run:
```bash
cd web && npm run build
```
Expected: 构建成功（允许 Cesium 等既有 warning，但无 tokens.css 语法错误）。

- [ ] **Step 4: 提交**

```bash
git add web/src/styles/tokens.css
git commit -m "feat(tokens): sky-blue glass token system

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: 更新 `layout.css`

**Files:**
- Modify: `web/src/styles/layout.css`

**Interfaces:**
- Consumes: `--primary`, `--primary-600`, `--primary-soft`, `--water`, `--water-soft`, `--ok`, `--ok-soft`, `--glass*`, `--line*`, `--edge`, `--shadow*`, `--ring`, `--ink*`, `--muted`, `--faint`, `--mono`, `--serif`, `--sans`。
- Produces: `.app-layout`, `.sidebar`, `.topbar`, `.btn`, `.nav` 等类的最终外观。

- [ ] **Step 1: 替换 Sidebar 与品牌标颜色**

在 `web/src/styles/layout.css` 中执行以下替换：

```css
/* 替换 .sidebar 背景/边框 */
.sidebar {
  ...
  border: 1px solid var(--edge);
  border-radius: var(--radius-xl);
  background: var(--glass);
  box-shadow: var(--shadow-soft);
  -webkit-backdrop-filter: blur(22px);
  backdrop-filter: blur(22px);
  ...
}
```

```css
/* 替换 .mark */
.mark {
  width: 32px;
  height: 32px;
  border-radius: 10px;
  background:
    radial-gradient(circle at 32% 26%, rgba(255, 255, 255, .9) 0 14%, transparent 15%),
    linear-gradient(135deg, var(--primary), var(--water) 85%);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, .3), 0 8px 18px rgba(2, 132, 199, .28);
}
```

```css
/* 替换 .nav a 悬停/激活态 */
.nav a:hover { background: rgba(2, 132, 199, .06); transform: translateX(2px); }
.nav a.router-link-active,
.nav a.active {
  color: var(--primary);
  background: var(--primary-soft);
  font-weight: 700;
}
.nav a.active::before {
  content: "";
  position: absolute;
  left: 0;
  top: 20%;
  bottom: 20%;
  width: 3px;
  border-radius: 3px;
  background: var(--primary);
}
```

```css
/* 替换 .agent-card */
.agent-card {
  border: 1px solid var(--edge);
  border-radius: var(--radius-md);
  padding: 11px;
  background:
    radial-gradient(circle at 88% 0, var(--primary-soft), transparent 9rem),
    var(--glass-strong);
}
.agent-card b { display: block; font-size: 12.5px; margin-bottom: 5px; color: var(--primary); }
```

- [ ] **Step 2: 替换 Topbar 与按钮颜色**

```css
.topbar {
  ...
  border: 1px solid var(--edge);
  border-radius: var(--radius-lg);
  padding: 12px 18px;
  background: var(--glass);
  box-shadow: var(--shadow-panel);
  -webkit-backdrop-filter: blur(22px);
  backdrop-filter: blur(22px);
}
```

```css
.btn {
  min-height: 32px;
  border: 1px solid var(--edge);
  border-radius: 999px;
  padding: 0 14px;
  background: var(--glass-strong);
  color: var(--ink);
  font: 600 12px var(--sans);
  cursor: pointer;
  transition: transform .16s, box-shadow .16s;
}
.btn:hover { transform: translateY(-1px); box-shadow: var(--shadow-soft); }
.btn.primary {
  color: #fff;
  border-color: transparent;
  background: var(--primary);
  box-shadow: 0 8px 20px rgba(2, 132, 199, .28);
}
.btn.primary:hover { background: var(--primary-600); }
.btn.danger { color: var(--danger); border-color: rgba(220, 38, 38, .25); }
```

- [ ] **Step 3: 替换 clock 与其他暖棕描边**

```css
.clock {
  color: var(--ink-2);
  font-family: var(--mono);
  font-size: 12px;
  border: 1px solid var(--edge);
  border-radius: 999px;
  padding: 9px 12px;
  background: var(--glass-strong);
  white-space: nowrap;
}
```

搜索 `rgba(37,33,28` 并全部替换为 `var(--line)` / `var(--line-strong)` / `rgba(15,23,42,.07)` 等冷色等价。

- [ ] **Step 4: 验证残留暖色**

Run:
```bash
grep -En "rgba\(37,33,28|#2d2923|rgba\(200,111,76" web/src/styles/layout.css || echo "clean"
```
Expected: `clean`。

- [ ] **Step 5: 构建与提交**

Run:
```bash
cd web && npm run build
```

```bash
git add web/src/styles/layout.css
git commit -m "feat(layout): sky-blue shell colors and glass panels

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: 更新 `components.css`

**Files:**
- Modify: `web/src/styles/components.css`

**Interfaces:**
- Consumes: 全部 tokens。
- Produces: 组件级样式，包括 `.tile`、`.panel`、`.risk-item`、`.station`、`.video-card`、`.message.ai` 等。

- [ ] **Step 1: 替换 Overview Tiles**

```css
.tile {
  ...
  border: 1px solid var(--edge);
  border-radius: var(--radius-md);
  padding: 11px 14px 11px 18px;
  background: var(--glass);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: var(--shadow-panel);
}
.tile::after { background: var(--primary-soft); }
.tile.river::after { background: var(--water-soft); }
.tile.moss::after { background: var(--ok-soft); }
.tile.amber::after { background: var(--orange-soft); }
.tile-note.danger { color: var(--danger); }
```

- [ ] **Step 2: 替换面板与地图元素**

```css
.panel {
  ...
  border: 1px solid var(--edge);
  border-radius: var(--radius-lg);
  background: var(--glass);
  box-shadow: var(--shadow-panel);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
}
.panel::before, .panel::after {
  content: "";
  position: absolute;
  width: 9px;
  height: 9px;
  border-color: var(--primary);
  pointer-events: none;
  opacity: .28;
}
.panel::before { top: 7px; left: 7px; border-top: 1px solid; border-left: 1px solid; }
.panel::after { bottom: 7px; right: 7px; border-bottom: 1px solid; border-right: 1px solid; }
.panel-head {
  ...
  border-bottom: 1px solid var(--line);
  background: linear-gradient(180deg, rgba(255, 255, 255, .30), rgba(255, 255, 255, .06));
}
```

- [ ] **Step 3: 替换站点与风险列表**

```css
.station {
  ...
  background: var(--ok);
  box-shadow: 0 0 0 5px var(--ok-soft), 0 6px 12px rgba(0, 0, 0, .14);
}
.station.warn {
  background: var(--orange);
  box-shadow: 0 0 0 5px var(--orange-soft), 0 6px 12px rgba(0, 0, 0, .14);
}
.station.danger {
  background: var(--danger);
  box-shadow: 0 0 0 6px var(--danger-soft), 0 6px 14px rgba(0, 0, 0, .18);
  animation: pulse 1.6s infinite;
}
@keyframes pulse {
  0%, 100% { box-shadow: 0 0 0 6px var(--danger-soft), 0 6px 14px rgba(0, 0, 0, .18); }
  50% { box-shadow: 0 0 0 11px rgba(220, 38, 38, .08), 0 6px 14px rgba(0, 0, 0, .18); }
}

.risk-item {
  border: 1px solid var(--edge);
  border-radius: var(--radius-md);
  padding: 9px 11px;
  background: var(--glass-strong);
}
.badge.danger { color: var(--danger); background: var(--danger-soft); }
.badge.warn { color: var(--orange); background: var(--orange-soft); }
.badge.yellow { color: var(--warn); background: var(--warn-soft); }
.badge.ok { color: var(--ok); background: var(--ok-soft); }
.progress { background: var(--line); }
.progress i { background: var(--primary); }
```

- [ ] **Step 4: 替换图表、视频、Agent 对话颜色**

```css
.history-line { stroke: var(--water); }
.forecast-line { stroke: var(--accent); }
.history-dot { fill: var(--water); }
.axis { stroke: rgba(15, 23, 42, .18); }
.grid { stroke: rgba(15, 23, 42, .08); }
.now-line { stroke: var(--accent); opacity: .55; }

.video-card {
  border: 1px solid var(--edge);
  background:
    radial-gradient(circle at 50% 45%, rgba(255, 255, 255, .5), transparent 60%),
    linear-gradient(150deg, #DCEAF3, #C6DCEC 70%, #B4CDE2);
}

.message.ai {
  color: #fff;
  background: var(--primary);
  border-color: transparent;
}

.login-error {
  color: var(--danger);
  background: var(--danger-soft);
}
.login-field input:focus { border-color: var(--primary); box-shadow: var(--ring); }
```

- [ ] **Step 5: 全局替换 `rgba(37,33,28,...)` 与旧色名**

Run and fix until clean:
```bash
grep -En "rgba\(37,33,28|var\(--clay|var\(--moss|var\(--river|var\(--amber|#2d2923" web/src/styles/components.css
```
Expected: 无匹配。

- [ ] **Step 6: 构建与提交**

```bash
cd web && npm run build
```

```bash
git add web/src/styles/components.css
git commit -m "feat(components): sky-blue semantic colors for tiles, panels, stations, charts

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: 重构 `TrendChart.vue`（真实像素 + 跨度感知坐标轴）

**Files:**
- Modify: `web/src/components/TrendChart.vue`

**Interfaces:**
- Consumes: `props.history` (`{time,t,y}`), `props.forecast` (`{time,t,y}`), `props.unit` (String)。
- Produces: 无 viewBox 的真实像素 SVG；`axisTicks(tMin, tMax, pw)` 算法；`fmtLabel(ms, fmt)` 格式化函数。

- [ ] **Step 1: 完全替换 `<template>`**

```vue
<template>
  <div ref="wrap" class="trend-chart-wrap">
    <div ref="canvas" class="chart-canvas">
      <svg ref="svg" aria-hidden="true"></svg>
    </div>
  </div>
</template>
```

- [ ] **Step 2: 完全替换 `<script setup>`**

```vue
<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'

const props = defineProps({
  history: { type: Array, default: () => [] },
  forecast: { type: Array, default: () => [] },
  unit: { type: String, default: '水位(m)' }
})

const wrap = ref(null)
const canvas = ref(null)
const svg = ref(null)

const historyColor = '#0EA5E9'
const forecastColor = '#6366F1'
const HOUR = 3600000

const margin = { top: 12, right: 18, bottom: 26, left: 54 }

function _getTime(d) {
  if (d == null) return null
  if (typeof d.time === 'number') return d.time
  if (d.time instanceof Date) return d.time.getTime()
  if (typeof d.time === 'string') return new Date(d.time).getTime()
  if (typeof d.t === 'number') return d.t
  if (typeof d.t === 'string') {
    const t = new Date(d.t)
    if (!isNaN(t.getTime())) return t.getTime()
  }
  return null
}

const historyPoints = computed(() => props.history.map(d => ({ ...d, _t: _getTime(d) })).filter(d => d._t != null && typeof d.y === 'number'))
const forecastPoints = computed(() => props.forecast.map(d => ({ ...d, _t: _getTime(d) })).filter(d => d._t != null && typeof d.y === 'number'))
const allPoints = computed(() => [...historyPoints.value, ...forecastPoints.value])

const timeDomain = computed(() => {
  const times = allPoints.value.map(d => d._t)
  if (times.length === 0) return [Date.now() - 24 * HOUR, Date.now() + 12 * HOUR]
  let min = Math.min(...times)
  let max = Math.max(...times)
  if (min === max) { min -= HOUR; max += HOUR }
  return [min, max]
})

const yDomain = computed(() => {
  const vals = allPoints.value.map(d => d.y)
  if (!vals.length) return [0, 1]
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const pad = (max - min) * 0.15 || Math.abs(max) * 0.1 || 1
  return [min - pad, max + pad]
})

const nowPoint = computed(() => {
  const h = historyPoints.value
  if (!h.length) return null
  return h[h.length - 1]
})

function pad2(n) { return String(n).padStart(2, '0') }

function fmtLabel(ms, fmt) {
  const d = new Date(ms)
  if (fmt === 'hm') return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`
  if (fmt === 'dhm') return `${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`
  return `${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}

function axisTicks(tMin, tMax, pw) {
  const spanH = (tMax - tMin) / HOUR
  let fmt, steps
  if (spanH <= 12) { fmt = 'hm'; steps = [1, 2, 3] }
  else if (spanH <= 48) { fmt = 'dhm'; steps = [4, 6, 8, 12] }
  else if (spanH <= 24 * 7) { fmt = 'd'; steps = [24] }
  else { fmt = 'd'; steps = [48, 72] }

  let stepH = steps[steps.length - 1]
  for (const s of steps) {
    const n = spanH / s
    if (n >= 3 && n <= 8 && pw / Math.max(1, n) >= 64) { stepH = s; break }
  }
  const stepMs = stepH * HOUR
  const ticks = []
  const start = Math.ceil(tMin / stepMs) * stepMs
  for (let tt = start; tt <= tMax; tt += stepMs) ticks.push(tt)
  return { fmt, ticks }
}

let ro = null
let raf = 0

function render() {
  if (!canvas.value || !svg.value) return
  const rect = canvas.value.getBoundingClientRect()
  const W = Math.max(260, Math.floor(rect.width))
  const H = Math.max(90, Math.floor(rect.height))
  svg.value.setAttribute('width', W)
  svg.value.setAttribute('height', H)
  svg.value.removeAttribute('viewBox')

  const pw = Math.max(40, W - margin.left - margin.right)
  const ph = Math.max(40, H - margin.top - margin.bottom)
  const [tMin, tMax] = timeDomain.value
  const [vMin, vMax] = yDomain.value

  const X = t => margin.left + ((t - tMin) / (tMax - tMin || 1)) * pw
  const Y = v => margin.top + ph - ((v - vMin) / (vMax - vMin || 1)) * ph

  const line = pts => pts.map((p, i) => `${i ? 'L' : 'M'} ${X(p._t).toFixed(1)} ${Y(p.y).toFixed(1)}`).join(' ')
  const area = pts => {
    const cx = X(pts[pts.length - 1]._t)
    return `${line(pts)} L ${cx.toFixed(1)} ${(margin.top + ph).toFixed(1)} L ${X(pts[0]._t).toFixed(1)} ${(margin.top + ph).toFixed(1)} Z`
  }
  const nowX = nowPoint.value ? X(nowPoint.value._t) : null

  // Y grid + labels
  let g = ''
  for (let i = 0; i <= 4; i++) {
    const v = vMin + (vMax - vMin) * (i / 4)
    const y = Y(v)
    g += `<line x1="${margin.left}" y1="${y.toFixed(1)}" x2="${(margin.left + pw).toFixed(1)}" y2="${y.toFixed(1)}" stroke="rgba(15,23,42,.08)" stroke-dasharray="4 7"/>`
    g += `<text x="${margin.left - 8}" y="${(y + 3).toFixed(1)}" font-family="var(--mono)" font-size="10" fill="#64748B" text-anchor="end">${Math.round(v)}</text>`
  }

  // X ticks
  const { fmt, ticks } = axisTicks(tMin, tMax, pw)
  for (const tt of ticks) {
    const x = X(tt)
    g += `<line x1="${x.toFixed(1)}" y1="${margin.top}" x2="${x.toFixed(1)}" y2="${(margin.top + ph).toFixed(1)}" stroke="rgba(15,23,42,.04)"/>`
    g += `<text x="${x.toFixed(1)}" y="${(margin.top + ph + 15).toFixed(1)}" font-family="var(--mono)" font-size="10" fill="#64748B" text-anchor="middle">${fmtLabel(tt, fmt)}</text>`
  }

  const hPts = historyPoints.value
  const fStart = nowPoint.value ? [nowPoint.value, ...forecastPoints.value] : forecastPoints.value

  const hPath = hPts.length ? line(hPts) : ''
  const hArea = hPts.length ? area(hPts) : ''
  const fPath = fStart.length ? line(fStart) : ''
  const fArea = fStart.length ? area(fStart) : ''

  const cy = margin.top + ph / 2
  const nowDot = nowPoint.value
    ? `<circle cx="${nowX.toFixed(1)}" cy="${Y(nowPoint.value.y).toFixed(1)}" r="4" fill="${historyColor}" stroke="#fff" stroke-width="1.5"/>`
    : ''

  svg.value.innerHTML = `
    <defs>
      <linearGradient id="hA" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0" stop-color="${historyColor}" stop-opacity=".28"/>
        <stop offset="1" stop-color="${historyColor}" stop-opacity="0"/>
      </linearGradient>
      <linearGradient id="fA" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0" stop-color="${forecastColor}" stop-opacity=".20"/>
        <stop offset="1" stop-color="${forecastColor}" stop-opacity="0"/>
      </linearGradient>
    </defs>
    ${g}
    <text transform="translate(16 ${cy.toFixed(1)}) rotate(-90)" text-anchor="middle" font-family="var(--mono)" font-size="10" fill="#64748B">${props.unit}</text>
    <line x1="${margin.left}" y1="${(margin.top + ph).toFixed(1)}" x2="${(margin.left + pw).toFixed(1)}" y2="${(margin.top + ph).toFixed(1)}" stroke="rgba(15,23,42,.18)"/>
    <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${(margin.top + ph).toFixed(1)}" stroke="rgba(15,23,42,.18)"/>
    ${nowX != null ? `<line x1="${nowX.toFixed(1)}" y1="${margin.top}" x2="${nowX.toFixed(1)}" y2="${(margin.top + ph).toFixed(1)}" stroke="${forecastColor}" stroke-width="1" stroke-dasharray="5 5" opacity=".55"/>` : ''}
    ${hArea ? `<path d="${hArea}" fill="url(#hA)"/>` : ''}
    ${hPath ? `<path d="${hPath}" fill="none" stroke="${historyColor}" stroke-width="2.5"/>` : ''}
    ${fArea ? `<path d="${fArea}" fill="url(#fA)"/>` : ''}
    ${fPath ? `<path d="${fPath}" fill="none" stroke="${forecastColor}" stroke-width="2.5" stroke-dasharray="6 5"/>` : ''}
    ${nowDot}
  `
}

function schedule() {
  cancelAnimationFrame(raf)
  raf = requestAnimationFrame(render)
}

onMounted(() => {
  nextTick(render)
  if (canvas.value) ro = new ResizeObserver(schedule)
  if (canvas.value) ro.observe(canvas.value)
})

onUnmounted(() => {
  cancelAnimationFrame(raf)
  if (ro && canvas.value) ro.unobserve(canvas.value)
})

watch(() => [props.history, props.forecast, props.unit], schedule, { deep: true })
</script>
```

- [ ] **Step 3: 替换 `<style scoped>`**

```vue
<style scoped>
.trend-chart-wrap {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.chart-canvas {
  position: relative;
  flex: 1;
  min-height: 0;
}
.chart-canvas svg { display: block; }
</style>
```

- [ ] **Step 4: 验证图表渲染**

Run dev server:
```bash
cd web && npm run dev
```
打开浏览器访问首页，检查：
1. 趋势图无字体拉伸；
2. X 轴标签为 `MM-DD hh:mm` 格式；
3. Y 轴左侧显示旋转标题 `流量 (m³/s)`；
4. 历史线为实线天青，预报线为虚线靛蓝。

- [ ] **Step 5: 提交**

```bash
git add web/src/components/TrendChart.vue
git commit -m "feat(trend-chart): real-pixel Cartesian rendering with span-aware axes

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: 更新 `CesiumMap.vue`

**Files:**
- Modify: `web/src/components/CesiumMap.vue`

**Interfaces:**
- Consumes: Cesium Viewer API。
- Produces: 青蓝主题三维场景参数与按状态着色的 pin 工厂函数。

- [ ] **Step 1: 开启柔和大气并调整基色**

在 `onMounted` 内 `scene.globe.enableLighting = true` 之后新增：

```js
scene.skyAtmosphere.show = true
scene.skyAtmosphere.hueShift = 0.0
scene.skyAtmosphere.saturationShift = -0.3
scene.skyAtmosphere.brightnessShift = -0.1

scene.globe.baseColor = Cesium.Color.fromCssColorString('#9bb7c4')
scene.backgroundColor = Cesium.Color.fromCssColorString('#0B2A3A')
```

- [ ] **Step 2: 更新站点标签轮廓色**

```js
outlineColor: Cesium.Color.fromCssColorString('#0284C7'),
```

- [ ] **Step 3: 提取按状态 pin 颜色**

将 `createPin('#e53935')` 替换为 `createPinForStatus('danger')`，并新增函数：

```js
function statusColor(status) {
  const map = {
    normal: '#10B981',
    ok: '#10B981',
    warn: '#EA580C',
    danger: '#DC2626',
    offline: '#94A3B8',
  }
  return map[status] || '#10B981'
}

function createPinForStatus(status) {
  return createPin(statusColor(status))
}
```

- [ ] **Step 4: 构建验证**

```bash
cd web && npm run build
```
Expected: 无新增报错。

- [ ] **Step 5: 提交**

```bash
git add web/src/components/CesiumMap.vue
git commit -m "feat(cesium): sky-blue atmosphere and status-colored pins

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: 调整 `AppLayout.vue` 栅格比例

**Files:**
- Modify: `web/src/pages/AppLayout.vue:18-29`

**Interfaces:**
- Produces: CSS 变量驱动 `workspace[data-page="Overview"]` 的 `grid-template-rows`。

- [ ] **Step 1: 更新 fr 变量**

替换 `onMounted` 中的注入：

```js
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
  root.style.setProperty('--sidebar-w', '220px')
})
```

- [ ] **Step 2: 提交**

```bash
git add web/src/pages/AppLayout.vue
git commit -m "feat(layout): adjust overview grid ratios for sky-blue cockpit

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 7: 调整 `OverviewPage.vue` 布局

**Files:**
- Modify: `web/src/pages/OverviewPage.vue`
- Modify: `web/src/styles/components.css`（为 `.forecast-insight` 添加靛蓝样式，若 Task 3 未覆盖）

**Interfaces:**
- Consumes: `forecastInsight` ref；`Topbar` 新增 `sectionCode` prop。
- Produces: 移除地图浮层面板后的首页结构；AI 解读条位于趋势图下方。

- [ ] **Step 1: 更新 `Topbar` 调用，增加分区编号**

```vue
<Topbar
  title="流域态势"
  subtitle="融合水位、流量、视频巡检与模型预报 · 仙桃站 00106"
  action-label="智能研判"
  section-code="// 01 · OVERVIEW"
  @primary-action="showAgentModal = true"
/>
```

- [ ] **Step 2: 移除地图浮层面板相关 DOM**

当前 `<article class="panel map-panel" />` 保留（Cesium 背景由 `AppLayout` 提供，该元素仅作占位/事件透传），但不再添加任何 `.map-note`、`.map-card` 子元素。检查 `OverviewPage.vue` 模板中无 `<div class="map-note">` 或 `<div class="map-card">`。

- [ ] **Step 3: 把 AI 解读从底部独立块移入趋势面板**

将模板底部 `combined-card` 内结构改为：

```vue
<div class="panel-body combined-card">
  <div class="trend-main">
    <div class="chart-wrap">
      <div class="combined-chart">
        <TrendChart :history="trendHistory" :forecast="trendForecast" unit="流量 (m³/s)" />
      </div>
      <div class="chart-legend">
        <span><i class="legend-hist"></i>实测</span>
        <span><i class="legend-fc"></i>预报</span>
        <span><i class="legend-now"></i>当前</span>
      </div>
    </div>
    <div class="forecast-summary combined-summary">
      <div class="mini-stat"><span>最高流量</span><b>{{ historyMaxFlow }}<small> m³/s</small></b></div>
      <div class="mini-stat"><span>平均流量</span><b>{{ historyAvgFlow }}<small> m³/s</small></b></div>
      <div class="mini-stat peak"><span>预报峰值</span><b>{{ forecastPeak }}<small> m³/s</small></b></div>
      <div class="mini-stat"><span>峰现时间</span><b>{{ forecastPeakTime }}</b></div>
    </div>
  </div>
  <div v-if="forecastInsight" class="forecast-insight">
    <span class="insight-label">AI · 预报解读</span>
    <p>{{ forecastInsight }}</p>
  </div>
</div>
```

- [ ] **Step 4: 更新局部样式**

在 `OverviewPage.vue` 的 `<style scoped>` 中替换 `.forecast-insight`：

```vue
<style scoped>
.forecast-insight {
  margin-top: 0;
  border: 1px solid var(--accent-soft);
  border-left: 3px solid var(--accent);
  border-radius: var(--radius-md);
  padding: 9px 13px;
  background: var(--accent-soft);
  display: flex;
  align-items: center;
  gap: 12px;
}
.insight-label {
  flex: 0 0 auto;
  font-family: var(--mono);
  font-size: 9.5px;
  font-weight: 700;
  color: var(--accent);
  letter-spacing: .08em;
  white-space: nowrap;
}
.forecast-insight p {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--ink);
}

.trend-main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 176px;
  gap: 12px;
  min-height: 0;
}
.chart-wrap {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 0;
}
.chart-legend {
  display: flex;
  align-items: center;
  gap: 14px;
}
.chart-legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  color: var(--ink-2);
}
.chart-legend i {
  width: 14px;
  height: 3px;
  border-radius: 2px;
}
.legend-hist { background: var(--water); }
.legend-fc { background: var(--accent); background-image: repeating-linear-gradient(90deg, var(--accent) 0 5px, transparent 5px 9px); }
.legend-now { background: var(--accent); opacity: .5; }
.mini-stat.peak b { color: var(--accent); }

.agent-modal-card2 {
  width: min(720px, 100%);
  height: min(600px, calc(100vh - 80px));
  display: flex;
  flex-direction: column;
  padding: 20px 22px 22px;
}
.agent-modal-card2 h2 { margin: 0; font-family: var(--serif); font-size: 22px; font-weight: 500; letter-spacing: -.04em; }
.agent-modal-card2 .modal-actions { margin-top: 0; margin-bottom: 12px; }
</style>
```

- [ ] **Step 5: 运行 dev 并检查布局**

```bash
cd web && npm run dev
```
确认：
1. 地图上没有「当前研判 / 倒计时」小面板；
2. 趋势面板下方出现靛蓝 AI 解读条；
3. 四段栅格比例协调。

- [ ] **Step 6: 提交**

```bash
git add web/src/pages/OverviewPage.vue
git commit -m "feat(overview): remove map float panels, move AI insight into trend panel

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 8: 更新 `Topbar.vue`

**Files:**
- Modify: `web/src/components/Topbar.vue`

**Interfaces:**
- Consumes: 新增 `sectionCode` prop。
- Produces: 头部带状标题 DOM。

- [ ] **Step 1: 更新 `<template>`**

```vue
<template>
  <header class="topbar">
    <div class="page-title">
      <span v-if="sectionCode" class="section-code">{{ sectionCode }}</span>
      <h1>{{ title }}</h1>
      <p>{{ subtitle }}</p>
    </div>
    ...
  </header>
</template>
```

- [ ] **Step 2: 新增 prop**

```js
defineProps({
  title: String,
  subtitle: String,
  actionLabel: String,
  sectionCode: String,
})
```

- [ ] **Step 3: 在 `layout.css` 中增加 `.section-code` 样式**

若 Task 2 未添加，在 `web/src/styles/layout.css` 的 `.page-title` 附近新增：

```css
.section-code {
  display: block;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--primary);
  letter-spacing: .08em;
  margin-bottom: 2px;
}
```

- [ ] **Step 4: 提交**

```bash
git add web/src/components/Topbar.vue web/src/styles/layout.css
git commit -m "feat(topbar): add section code header band style

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 9: 扫描并修复剩余组件硬编码色

**Files:**
- Modify: `web/src/components/SystemStatus.vue`
- Modify: `web/src/components/AgentChatPanel.vue`
- Modify: `web/src/components/ContextMenu.vue`

**Interfaces:**
- Consumes: tokens。
- Produces: 无残留暖色的组件样式。

- [ ] **Step 1: 全局扫描**

Run:
```bash
grep -rEn "#b96b55|#66746b|#6f8f9e|#b58b3f|#2d2923|rgba\(37,33,28|rgba\(200,111,76|var\(--clay|var\(--moss|var\(--river|var\(--amber" web/src/components web/src/pages web/src/styles || echo "clean"
```
Expected: 仅可能出现在注释或已确认可保留的静态字符串中；样式值必须 `clean`。

- [ ] **Step 2: 逐个修复匹配项**

对 `SystemStatus.vue`、`AgentChatPanel.vue`、`ContextMenu.vue` 中的匹配项，使用对应 token 替换：
- `#2d2923` / `var(--clay)` → `var(--primary)` 或 `var(--ink)`
- `var(--moss)` → `var(--ok)`
- `var(--river)` → `var(--water)`
- `var(--amber)` → `var(--warn)` 或 `var(--orange)`
- `rgba(37,33,28,...)` → `var(--line)` / `rgba(15,23,42,...)`
- `rgba(200,111,76,...)` → `var(--primary-soft)` / `var(--danger-soft)`

- [ ] **Step 3: 构建验证**

```bash
cd web && npm run build
```

- [ ] **Step 4: 提交**

```bash
git add web/src/components/SystemStatus.vue web/src/components/AgentChatPanel.vue web/src/components/ContextMenu.vue
git commit -m "fix(components): align leftover hardcoded warm colors to tokens

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 10: 构建与回归验证

**Files:**
- 无新增文件；验证整个 `web/src`。

**Interfaces:**
- 验证所有前置任务集成结果。

- [ ] **Step 1: 全量暖色扫描**

```bash
grep -rEn "#b96b55|#66746b|#6f8f9e|#b58b3f|#2d2923|rgba\(37,33,28|rgba\(200,111,76|var\(--clay|var\(--moss|var\(--river|var\(--amber" web/src || echo "clean"
```
Expected: `clean`。

- [ ] **Step 2: 生产构建**

```bash
cd web && npm run build
```
Expected: 构建成功退出。

- [ ] **Step 3: 启动开发服务器进行目视回归**

```bash
cd web && npm run dev
```
检查清单：
1. 左侧 Sidebar 品牌标为天空蓝渐变；
2. 激活导航项有左侧 3px 主色竖条；
3. 4 个 KPI tile 左侧有状态色竖条；
4. 地图无「当前研判 / 倒计时」小面板，保留右上角图层按钮；
5. 趋势图 Y 轴左侧旋转标题、X 轴 `MM-DD hh:mm`、历史天青/预报靛蓝/当前虚线；
6. 趋势图下方有靛蓝 AI 解读条；
7. Cesium 地球背景偏冷调青蓝；
8. 响应式缩窄至 1180px / 720px 不破版。

- [ ] **Step 4: 提交最终验证记录（可选）**

若上述全部通过：

```bash
git add -A
git commit -m "chore(release): phase 1 sky-blue cockpit verified

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Self-Review

### 1. Spec coverage

| Spec 要求 | 对应任务 |
|---|---|
| 天空蓝令牌系统 | Task 1 |
| layout.css 冷色化 | Task 2 |
| components.css 语义化 | Task 3 |
| TrendChart 真实像素 + 跨度感知 | Task 4 |
| Cesium 场景天空蓝 | Task 5 |
| 栅格比例调整 | Task 6 |
| 移除地图浮层面板 + AI 解读移入趋势图 | Task 7 |
| Header Band 分区编号 | Task 8 |
| 全站无残留暖色 | Task 9, Task 10 |
| 构建通过 | Task 10 |

### 2. Placeholder scan

- 无 "TBD" / "TODO" / "implement later"。
- 每个代码步骤给出完整文件片段或替换说明。
- 每个验证步骤给出具体命令与期望输出。

### 3. Type consistency

- `Topbar` 新增 `sectionCode: String` prop，与 `OverviewPage.vue` 中 `<Topbar section-code="..." />` 匹配。
- `TrendChart` props 保持 `history`、`forecast`、`unit` 不变，下游无需修改。
- `AppLayout` 注入的 CSS 变量名与 `layout.css` 中 `--topbar-h` 等一致。

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-27-vue-aqua-cockpit-redesign-phase1.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using `executing-plans`, batch execution with checkpoints for review

**Which approach?**
