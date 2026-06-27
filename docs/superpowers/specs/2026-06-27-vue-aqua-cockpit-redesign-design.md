# Vue 前端「天空蓝驾驶舱」重构设计方案

> 日期：2026-06-27 ｜ 范围：`web/` Vue 3 应用（Cesium + flv.js）｜ 状态：已确认，进入实施
>
> 配色方向：**天空蓝浅色玻璃（Sky-Blue Glass）** ｜ 布局：**保留原大屏栅格 + 局部精修** ｜ 节奏：**首页 Overview 优先，分阶段推广**
>
> 预览定稿：`preview/aqua-cockpit-overview-v6.html`（含跨度感知过程线）

---

## 1. 背景与目标

当前 Vue 应用沿用了静态原型（`index.html`）的**暖色编辑风**：黏土色 `#b96b55`、苔藓 `#66746b`、河流灰青 `#6f8f9e`、琥珀 `#b58b3f`，以及随处可见的暖棕描边 `rgba(37,33,28,…)`。这套配色对**水利监测指挥**语境不贴切——水利领域主流是冷调蓝青色系 + 强对比预警分级（红/橙/黄/绿）。同时 `tokens.css` 里 `--ink / --ink-2 / --muted` 被全部设为 `#000`，层级失效。

**目标**：
1. 建立一套**水利语义化设计令牌**（design tokens），以青蓝为主、靛蓝为强调，配标准四级预警阶梯。
2. 在保留现有「玻璃质感 + 衬线数字 + 地图作底」签名质感的前提下，把首页重构为更有指挥感的**大屏栅格**。
3. 令牌系统一次建好，首页作为旗舰样板，后续逐页推广（风险可控）。

**非目标**：不改业务逻辑、API、数据流；不动根目录静态原型 HTML（那是另一套）；不引入新依赖。

---

## 2. 设计语言

> 一句话：**浮在实时水文三维地球之上的、冷调青蓝玻璃驾驶舱。**

- **底**：Cesium 三维地图仍是全屏背景（签名特征保留）。地球场景调到**冷调、去饱和、带柔和水汽青光**，与青蓝主题一致。
- **面**：所有信息载体是**半透明白玻 + backdrop-blur** 的浮层卡片，描边/阴影统一冷色化。
- **数**：KPI 大数字保留**衬线**（编辑感签名），但时间戳/表格数字改用真正的**等宽字体**（当前 `--mono` 误设为 Times，时钟会很难看）。
- **色**：以**天空蓝 `#0284C7`** 为品牌主色、**天青 `#0EA5E9`** 为水文数据色、**靛蓝 `#6366F1`** 为预报/强调色；预警严格按 **红→橙→黄→（青=IV级）→绿=正常→灰=离线** 分级。
- **大屏语汇**：增加角标 tick、接缝辉光、等宽分区编号、状态色条等克制装饰，提升指挥临场感，但不喧宾夺主。

---

## 3. 配色令牌系统（核心）

替换 `web/src/styles/tokens.css` 的 `:root`。所有硬编码颜色迁移到语义令牌。

### 3.1 主令牌表

| 令牌 | 值 | 用途 |
|---|---|---|
| `--bg` | `#EEF4F9` | 应用底色（地图未覆盖处） |
| `--glass` | `rgba(255,255,255,.40)` | 普通玻璃面板 |
| `--glass-strong` | `rgba(255,255,255,.60)` | 强玻璃（模态/卡片） |
| `--glass-deep` | `rgba(255,255,255,.82)` | 实底玻璃（浮层/详情） |
| `--ink` | `#0F172A` | 主文字（slate-900） |
| `--ink-2` | `#334155` | 次文字（slate-700） |
| `--muted` | `#64748B` | 辅助文字（slate-500） |
| `--faint` | `#94A3B8` | 禁用/时间戳（slate-400） |
| `--line` | `rgba(15,23,42,.07)` | 分割线 |
| `--line-strong` | `rgba(15,23,42,.14)` | 强描边 |
| `--edge` | `rgba(255,255,255,.65)` | 玻璃面板外描边/内发光 |

### 3.2 品牌与数据色

| 令牌 | 值 | 用途 |
|---|---|---|
| `--primary` | `#0284C7` | 品牌主色（sky-600，天空蓝） |
| `--primary-600` | `#0369A1` | 主色亮一档（sky-700） |
| `--primary-soft` | `rgba(2,132,199,.13)` | 主色淡底（选中态/底纹） |
| `--accent` | `#6366F1` | 强调/预报色（indigo-500，靛蓝） |
| `--accent-soft` | `rgba(99,102,241,.12)` | 强调淡底 |
| `--water` | `#0EA5E9` | 水文数据色（sky-500，天青） |
| `--water-soft` | `rgba(14,165,233,.15)` | 水文淡底 |

### 3.3 状态/预警阶梯（水利四级标准）

| 令牌 | 值 | 语义 |
|---|---|---|
| `--danger` | `#DC2626` | Ⅰ级 红色 / 超保证 / 溃坝 |
| `--danger-soft` | `rgba(220,38,38,.14)` | |
| `--orange` | `#EA580C` | Ⅱ级 橙色 / 超警戒 |
| `--orange-soft` | `rgba(234,88,12,.14)` | |
| `--warn` | `#CA8A04` | Ⅲ级 黄色 / 上涨提醒 |
| `--warn-soft` | `rgba(202,138,4,.14)` | |
| `--info` | `#0EA5E9` | Ⅳ级 蓝色 / 一般提示 |
| `--ok` | `#10B981` | 正常 / 在线 / 数据良好 |
| `--ok-soft` | `rgba(16,185,129,.13)` | |
| `--offline` | `#94A3B8` | 离线 / 无数据 |

### 3.4 阴影与半径（冷色化）

| 令牌 | 值 |
|---|---|
| `--shadow` | `0 18px 50px rgba(30,64,124,.08)` |
| `--shadow-soft` | `0 8px 24px rgba(30,64,124,.06)` |
| `--shadow-panel` | `0 6px 20px rgba(30,64,124,.05)` |
| `--ring` | `0 0 0 3px rgba(2,132,199,.20)` (聚焦环) |
| `--radius-xl/lg/md` | `28 / 20 / 14 px`（保留） |
| `--radius-sm` | `10px`（新增） |

### 3.5 字体（修正 + 保留）

| 令牌 | 现值 | 新值 | 说明 |
|---|---|---|---|
| `--serif` | `"Times New Roman","SimHei"` | `"Cambria","Times New Roman","Noto Serif SC",serif` | 衬线数字保留，栈更稳 |
| `--sans` | Times（误） | `"Inter","PingFang SC","Microsoft YaHei",system-ui,sans-serif` | 正文改回无衬线，CJK 友好 |
| `--mono` | Times（误） | `"SF Mono","JetBrains Mono","Cascadia Code",Consolas,monospace` | 时钟/数字真正等宽 |

> 说明：当前正文与时钟都用 Times，是原型遗留；正文改无衬线、时钟改等宽是**数据可读性刚需**，且与"衬线数字"签名不冲突（数字仍用 `--serif`）。

---

## 4. 布局重构：大屏栅格（首页 Overview）

### 4.1 现状

`AppLayout.vue` = 全屏 Cesium 背景 + 左侧 Sidebar + 右侧 Workspace。`OverviewPage` 当前分区（由 layout-tuner 的 fr 变量驱动）：

```
┌ Sidebar ┬ Topbar (7.9fr) ────────────────────────────┐
│         ├ 4×KPI tiles (10.5fr)                        │
│         ├ middle: 视频 | 地图(透) | 预警 (50fr)        │
│         └ bottom: 趋势图+mini-stats (31.6fr)          │
```

**已是「玻璃浮于地图」的栅格**，所以重构不是推倒重来，而是把它做成**更刻意、更具指挥感的驾驶舱构图**。

### 4.2 目标构图（大屏栅格）

```
┌─ Sidebar ─┬─ HEADER BAND 全宽标题带 ─────────────────────────────┐
│ 品牌      │  流域态势  ·  系统状态pill  ·  时钟  ·  智能研判/退出    │
│ 导航      ├─ KPI STRIP 状态色条 ───────────────────────────────────┤
│ (青蓝)    │  ●水位  ●流量  ●可信度  ●预警   ← 每项带状态色点+趋势   │
│           ├──────────────┬─────────────────────────┬──────────────┤
│ FloodMind │  左翼·视频巡检 │     中央·3D 地图(背景)    │ 右翼·预警告警  │
│ 卡片      │  (2 路浮窗栈)  │   浮层:图层切换按钮        │ (纯风险列表)  │
│           ├──────────────┴─────────────────────────┴──────────────┤
│           │  DATA BAND 全宽趋势带: 历史(天青)→预报(靛蓝)+AI解读+stats│
└───────────┴───────────────────────────────────────────────────────┘
```

### 4.3 关键改动

1. **Header Band**：`Topbar` 升级为全宽带状，加底部 1px 青蓝辉光接缝 `box-shadow: inset 0 -1px 0 var(--primary-soft)`；标题左侧加等宽分区编号（如 `// 01 · OVERVIEW`）作大屏语汇。
2. **KPI Strip**：4 个 `.tile` 改造——左侧**状态色点**（按水位/预警状态着色）、大衬线数字、单位、趋势/距阈值文案；卡片左侧加 2px 状态色竖条。`.tile.river/.moss/.amber` 的暖色 `::after` 改为对应语义色淡光。
3. **中央地图 + 双翼**：地图维持全屏背景；**移除**原地图上的「当前研判」与「38 分钟触达警戒」两个小浮层面板，仅保留右上角**图层切换按钮**；左翼视频、右翼预警作为浮层玻璃栈贴边。
4. **Data Band**：底部趋势带全宽，历史=天青 `--water`、预报=靛蓝 `--accent`，mini-stats 横排内联；**新增 AI 预报解读条**置于图表下方（`--accent-soft` 底 + `--accent` 左边框）。
5. **装饰语汇**：面板四角加 L 形 tick、面板头加等宽小编号、状态徽章统一四级色。
6. **layout-tuner 比例**（`AppLayout.vue` 的 fr 变量）调整为更合理的大屏比例，并保留可调机制。

### 4.4 新栅格比例（建议，可调）

```
--header-h:  8.5fr   (原 topbar 7.9)
--kpi-h:     9.0fr   (原 overview 10.5，更紧凑)
--middle-h:  50fr    (中央带，不变)
--databand-h:32.5fr  (原 bottom 31.6)
--video-w:   21fr    --map-w: 51fr  --warn-w: 28fr
```
> 这些值通过现有 layout-tuner 注入，`workspace[data-page="Overview"]` 的 `grid-template-rows` 同步更新；响应式断点保持。

---

## 5. 组件级改造清单

| 组件/类 | 现状(暖色) | 改为(青蓝) |
|---|---|---|
| `.mark` 品牌标 | `linear-gradient(clay,river)` | `linear-gradient(--primary, --water)` + 青光 |
| `.nav .active` | `rgba(200,111,76,.12)` | `var(--primary-soft)` + 左 2px `--primary` 竖条 |
| `.agent-card` | clay 径向光 | `--primary-soft` 径向光 |
| `.btn.primary` | `#2d2923` 深棕 | `var(--primary)` + hover `--primary-600` |
| `.btn.danger` | `rgba(169,79,67,..)` | `var(--danger)` 语义 |
| `.badge.danger/.warn/.ok` | clay/amber/moss | `--danger/--warn/--ok` + soft 底 |
| `.progress i` | clay 默认 | 按状态：danger/orange/warn/ok |
| `.station` 站点 | moss/amber/clay | ok/warn/danger（normal→`--ok`，warn→`--orange`，danger→`--danger`） |
| `.river-main`(SVG) | warm river 灰青 | `--water` 天青 |
| `.message.ai` | `#2d2923` 深棕 | `var(--primary)` 深青 + 白字 |
| `.login-error` / `input:focus` | clay | `--danger` / `--ring` |
| 所有 `rgba(37,33,28,…)` 暖棕 | — | `var(--line)` / `var(--line-strong)`（或冷色 rgba(15,23,42,..)） |
| `.forecast-insight` | moss 底/边 | `--accent-soft` 底 + `--accent` 边（AI 解读改靛蓝强调） |

---

## 6. 过程线渲染规格（TrendChart.vue）

### 6.1 配色

| 元素 | 现值 | 新值 |
|---|---|---|
| `historyColor` | `#6d929f`（暖灰青） | `#0EA5E9`（`--water`，天青） |
| `forecastColor` | `#b96b55`（黏土） | `#6366F1`（`--accent`，靛蓝） |
| 历史面积渐变 | — | `#0EA5E9` → 透明，上端不透明度 28% |
| 预报面积渐变 | — | `#6366F1` → 透明，上端不透明度 20% |
| `.axis` | `rgba(37,33,28,.28)` | `rgba(15,23,42,.18)` |
| `.grid` | `rgba(37,33,28,.16)` | `rgba(15,23,42,.08)` |
| `.now-line` | warm | `#6366F1` 虚线，不透明度 55% |
| `.history-dot` | `#6d929f` | `#0EA5E9` 实心 + 白边 |

颜色在 `<script>` 中以常量形式与令牌同值（Vue 无 CSS 变量到 JS 的自动桥接）。

### 6.2 核心问题与解决

旧实现使用 SVG `viewBox + preserveAspectRatio="none"` 配合 `ResizeObserver`，导致文字被拉伸畸变。新实现改为**真实像素笛卡尔坐标**：

- 移除 SVG `viewBox`，`width/height` 使用容器测量后的整数像素；
- 1 SVG 用户单位 = 1 设备像素，所有路径/文字按真实 px 计算；
- 通过 `ResizeObserver` 监听 `.chart-canvas` 并在 `requestAnimationFrame` 中重绘；
- 不依赖任何 SVG 坐标缩放，保证字体、虚线、线宽在任何比例下不畸变。

### 6.3 绘图区域与边距

```
m = { l: 54, r: 18, t: 12, b: 26 }
pw = W - m.l - m.r   // 绘图区宽
ph = H - m.t - m.b   // 绘图区高
```

- 左侧 54px：容纳旋转的 Y 轴标题 `流量 (m³/s)` + Y 轴数值标签；
- 底部 26px：容纳 X 轴时间标签；
- 顶部 12px / 右侧 18px：留白，避免边缘压线。

### 6.4 X 轴：跨度感知刻度

根据数据时间跨度自动选择步长与标签格式：

| 跨度 | 格式 | 候选步长 | 选择规则 |
|---|---|---|---|
| `≤ 12h` | `hh:mm` | `[1,2,3]` 小时 | 在 3~8 个刻度之间，且 `pw / n ≥ 64px` |
| `≤ 48h` | `MM-DD hh:mm` | `[4,6,8,12]` 小时 | 同上 |
| `≤ 7天` | `MM-DD` | `[24]` 小时 | 同上 |
| `> 7天` | `MM-DD` | `[48,72]` 小时 | 同上 |

算法：先按跨度选格式与候选步长列表，再遍历步长，优先满足刻度数量 3~8 个且标签间距 ≥64px；若都不满足，使用列表最大步长兜底。

### 6.5 Y 轴

- 固定 5 条水平网格线（含上下边界），等分 `min~max`；
- Y 轴标题：`流量 (m³/s)`，沿 Y 轴左侧垂直旋转 `-90°` 居中；
- 数值标签右对齐，置于绘图区左侧。

### 6.6 数据映射

```
X(t) = m.l + (t - tMin) / (tMax - tMin) * pw
Y(v) = m.t + ph - (v - vMin) / (vMax - vMin) * ph
vMin = min(Y) - (max-min)*0.15
vMax = max(Y) + (max-min)*0.15
```

历史与预报共享同一坐标系；预报线使用虚线 `stroke-dasharray="6 5"`；"当前"时刻使用 `#6366F1` 垂直虚线，并在历史线末端绘制当前点圆点。

### 6.7 交互与响应

- 组件挂载时首次渲染；
- `ResizeObserver` 触发后通过 `requestAnimationFrame` 去抖重绘；
- `window resize` 同样触发重绘；
- （可选）保留跨度切换按钮（12h / 48h / 7天），切换数据集后调用同一 `renderChart`。

---

## 7. Cesium 三维场景配色（CesiumMap.vue）

让背景地球与天空蓝主题统一（仅调参，不动数据/相机逻辑）：

1. `scene.skyAtmosphere`：现为 `show=false` → 改为**开启**并设 `hueSaturationBrightness`，呈柔和天空蓝；或保留关闭、改用 `scene.fog` + `globe` 基色（实现时二选一，默认倾向开启柔光）。
2. `scene.globe.baseColor`：设为冷调去饱和的灰青（`Cesium.Color.fromCssColorString('#9bb7c4')` 级别），使未贴图区域不抢戏。
3. `scene.backgroundColor`（星空底）：`#0B2A3A` 深蓝青（地图边缘/太空处可见时）。
4. 站点标签 `outlineColor` `#1a5f7a` → `--primary` `#0284C7`；`fillColor` 维持白。
5. 站点 pin `createPin(color)`：normal=`--ok`、warn=`--orange`、danger=`--danger`，与 UI 状态色一致。
6. 若有水面/水体实体：填色 `--water` `#0EA5E9` 半透。
7. 保持 `enableLighting=true`（日照真实感）。

---

## 8. 逐页落地（分阶段）

**阶段一（本次重点，旗舰样板）**
- `tokens.css` 全量重写（令牌系统建立）
- `layout.css` / `components.css` 全量冷色化 + 语义化
- `OverviewPage.vue` + `AppLayout.vue` 大屏栅格重构
- `TrendChart.vue` / `CesiumMap.vue` 配色
- `Topbar.vue` / `Sidebar.vue` 随令牌自动生效（少量微调）
- `SystemStatus.vue` / `AgentChatPanel.vue` / `ContextMenu.vue` 对齐令牌（扫一遍硬编码色）

**阶段二（令牌推广，后续单列计划）**
- `StationsPage / WarningsPage / AlertsPage / ForecastPage / DevicesPage / ReportsPage / AgentPage / LoginPage / Admin*` 逐页对齐令牌与大屏语汇；各页表格/表单组件统一。
- 因令牌系统已就位，阶段二多为「替换硬编码色 + 套用新组件类」，工作量与风险递减。

---

## 9. 令牌迁移映射（执行时逐处核对）

| 旧硬编码 | 出现位置 | 新令牌 |
|---|---|---|
| `rgba(37,33,28,.10/.18/.28/…)` | layout/components/TrendChart 全局 | `--line` / `--line-strong` / 冷色 rgba |
| `rgba(200,111,76,..)` (clay) | brand/nav/tile/badge/progress/login | `--primary` / `--primary-soft` / `--danger`(预警语境) |
| `rgba(109,146,159,..)` (river) | map/tile.river/chart | `--water` / `--water-soft` |
| `rgba(104,119,100,..)` (moss) | tile.moss/station/badge.ok | `--ok` / `--ok-soft` |
| `rgba(201,154,66,..)` (amber) | tile.amber/station.warn | `--warn` 或 `--orange` |
| `#2d2923` (深棕按钮/AI气泡) | btn.primary/message.ai | `--primary` |
| `#6d929f` / `#b96b55` (图表) | TrendChart | `#0EA5E9` / `#6366F1` |
| `--primary` `#0E7490` / `--accent` `#2563EB` | 多处 | `#0284C7` / `#6366F1` |
| `--ink/--ink-2/--muted=#000` | tokens | `#0F172A` / `#334155` / `#64748B` |

---

## 10. 验收标准

1. 全站无残留暖色（黏土/苔藓/暖棕/深棕按钮）；`grep` 不到 `#b96b55|#2d2923|rgba(37,33,28|rgba(200,111,76` 在 `web/src`。
2. 文字层级清晰：主/次/辅助/禁用四级对比度达 WCAG AA（玻璃上白字场景对比度 ≥ 4.5:1）。
3. 预警徽章/站点/进度条严格按 红→橙→黄→青→绿→灰 分级。
4. 首页呈大屏栅格构图：Header Band + KPI Strip + 中央地图双翼 + Data Band 四带清晰可读。
5. 趋势图历史(天青)/预报(靛蓝)/当前线 视觉可区分；Cesium 场景冷调与 UI 协调。
6. 响应式：≤1180px / ≤720px 断点不破版；地图始终为背景。
7. 构建通过（`npm run build`），无控制台配色相关报错。

---

## 11. 风险与回退

| 风险 | 应对 |
|---|---|
| 玻璃半透明下冷色文字对比度不足 | 关键文字位加深底（`--glass-strong`）或加文字阴影 |
| Cesium 场景调参后地图辨识度下降 | 仅调 `baseColor/atmosphere`，保留 `enableLighting`；可快速回退单文件 |
| 大屏栅格在中小屏挤压 | 保留现有响应式断点；窄屏自动退回单列 |
| 改动文件多、回归面广 | 阶段一聚焦首页+令牌；阶段二逐页推广，每页可独立验证 |
| 衬线字体在缺字环境回退 | 栈中含 `Noto Serif SC`/`SimHei` 兜底 |

**回退**：所有改动集中在样式与少量模板/场景参数，业务逻辑零改动；必要时 `git revert` 阶段一提交即可完整回退。

---

## 12. 已确认项（不再开放）

1. **Header Band 等宽分区编号**：采用 `// 01 · OVERVIEW` 大屏语汇。
2. **预报色**：采用靛蓝 `--accent` `#6366F1`，与历史天青区分。
3. **主品牌色**：天空蓝 `--primary` `#0284C7`，非深青。
4. **布局**：保留原 4 层栅格（Header / KPI / Middle / DataBand），移除地图上的「当前研判/倒计时」小面板，AI 解读移至趋势图面板底部。
5. **Cesium `skyAtmosphere`**：倾向开启柔和天空蓝大气效果，实现时若性能/辨识度不佳可回退为仅调 `globe.baseColor`。
6. 阶段二各页不在本次 spec 内展开，后续另出计划。

---

> 下一步：本 spec 经用户确认后，调用 **writing-plans** 技能输出阶段一的分步实施计划（含每文件具体改动与顺序），再次确认后方执行。
