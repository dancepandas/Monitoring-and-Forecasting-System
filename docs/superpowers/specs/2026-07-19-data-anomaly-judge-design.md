# 数据异常智能裁决（水位↔流量一致性 + 脏数据）— 设计文档

- 日期：2026-07-19
- 分支：feature/3d-terrain-model
- 状态：已 brainstorm 批准，待实现

## 1. 背景与问题

部分站点出现「水位正常、流量本稳定在某一区间，却偶发流量突刺而水位纹丝不动」的现象。这在物理上不通——同一断面水位不变则流量不应突变，说明是**上游 aiflow2 平台的 `virtualFlow` 计算/流量计/数据传输**出了问题，而非真实水情。

现状缺口：
- `MonitorEngine._check_spike()`（`gateway/services/monitor_engine.py:295`）只看 `virtualFlow` 相邻两点 delta，**不看水位↔流量的物理一致性**；突刺只要 delta 没到 danger 阈值就漏判。
- 整条链路没有任何模块对「水位-流量是否自洽」「数据是否冻结/不可能值/缺测伪装稳定」做判断。
- 现有预警只有两类：**预警**（洪水：蓝/黄/橙/红，阈值驱动）与**告警**（系统）。数据质量类异常没有归属，会被当成「正常」展示在地图/卡片/抽屉上，误导值班。

用户硬性要求：**不要人工配阈值**（"写阈值要人设"），要智能体灵活判断；异常要在数据上标注清楚（水位同理），预警信息里也要写清楚。

## 2. 目标 / 非目标

### 目标
1. 新增 `anomaly_judge` 服务：廉价统计预筛 → 命中才调 LLM → 结构化裁决。
2. 裁决**挂到该站最新读数上**（后端注入），`/data/latest`、`/data/flow-raw` 每条最新读数带 `anomaly` 字段；前端零额外请求、多端一致、常驻显示。
3. 新增预警类别「**数据异常**」（紫色徽章，区别于洪水四色），通过 `/data/warnings` 的 `data_anomalies` 数组下发。
4. 前端在 5 个界面渲染标注：左侧水位/流量卡片、地图站点角标与悬浮卡、StationDrawer 详情、底部过程图（标注当前点）、WarningsPage 列表。

### 非目标（本期不做）
- 不修正/重算 `virtualFlow`（绝不编造数值，只标注存疑）。
- 不做历史序列逐点回标（仅标注当前最新读数；历史点标注留作二期）。
- 不做水位-流量 rating curve 反推（gateway 不持水位流量关系曲线；若后续接入 `H_to_Q` 兄弟目录另开 spec）。
- 不接入 floodmind 全量 Agent（用轻量 `quick_ask` 即可，避免起 29 工具的重量级会话）。

## 3. 架构总览

```
MonitorEngine._tick()  每 5 分钟，每站、数据刷新后：
  ┌─ anomaly_judge.judge_station(code) ─────────────────────────┐
  │ 1. 取近 1h 对齐序列（waterLevel + virtualFlow + velocity）   │
  │ 2. 预筛 prefilter(series) → 命中理由 list（固定统计门）       │
  │ 3. 命中 → quick_ask(qwen-plus) 出结构化 JSON 裁决            │
  │    未命中 → 裁决 {flagged:false}                              │
  │ 4. 写 anomaly_verdicts.json[code]（喂 /latest、/flow-raw）    │
  │ 5. flagged → AlertTracker 建事件(category=数据异常,复用去重) │
  │    未 flagged → resolve 该站历史 data_anomaly 事件            │
  └──────────────────────────────────────────────────────────────┘

读取侧（同步给前端）：
  /data/latest      → 每站最新 item 附 anomaly 字段（源：anomaly_verdicts.json）
  /data/flow-raw    → 最新一条 record 附 anomaly 字段（源：anomaly_verdicts.json）
  /data/warnings    → 新增 data_anomalies[]（源：AlertTracker 中 category=数据异常
                      的事件，并从 alerts[] 过滤掉同源事件避免重复计数）
```

降级链：LLM 熔断/超时/解析失败 → 退化为「仅预筛弱标注」（`source:"prefilter"`，文案用预筛理由，不报错不阻塞）。

## 4. 后端组件

### 4.1 `gateway/services/anomaly_judge.py`（新增）

两个函数：

**`prefilter(series) -> list[Reason]`**（纯函数，无 IO，无配置）
对近 1h 序列算 MAD-z（中位绝对偏差，对突刺不敏感），返回命中理由列表。固定门，非配置阈值：

| 理由 key | 触发条件（说明性，非最终实现） |
|---|---|
| `flow_level_inconsistency` | 流量 |z| > 2 且 水位 |z| < 0.5（流量突刺、水位不动） |
| `level_flow_inconsistency` | 水位 |z| > 2 且 流量 |z| < 0.5（水位突刺、流量不动；"水位同理"） |
| `frozen` | 序列 std ≈ 0 但设备心跳在线（数据冻结） |
| `invalid_value` | 出现负值或物理不可能值（水位/流量 < 0 等） |
| `gap_masking` | 实测点占比 < 50% 却被 Chronos 补齐成"稳定"序列 |

MAD-z 计算：`z = 0.6745 * (x - median) / MAD`，`MAD = median(|x_i - median|)`。MAD≈0 时（真冻结）单独走 `frozen` 分支，避免除零。

**`async judge_station(code) -> Verdict`**
1. `data_cache.get_aligned(code, max_age=600)` 取序列，裁到近 1h 实测点。
2. `reasons = prefilter(series)`；若无理由 → 返回 `{flagged:false, source:"none"}`。
3. 命中 → 组装 prompt（站点名、近序列数值表、命中理由），调 `quick_ask`（`max_tokens≈300`，`temperature=0.2`），system 限定"水文数据质量裁判，只输出 JSON"。
4. 解析 JSON；失败 → 退化为 `{flagged:true, source:"prefilter", reason:<预筛理由中文>}`。
5. 返回 Verdict（见 §6 契约）。

### 4.2 MonitorEngine 集成（`gateway/services/monitor_engine.py`）

在 `_check_station()` 末尾、`_check_forecast_thresholds` 之后追加 `await anomaly_judge.judge_station(code)`。裁决落盘后：
- flagged → `tracker.create_or_update(...)` 建一条 `category="数据异常"` 事件（`alert_type="data_anomaly"`），复用现有 30 分钟去重，避免每 tick 刷预警。
- 未 flagged → 若该站存在历史 data_anomaly 事件则 resolve 之（自动清除）。

裁决同时写入 `gateway/data/anomaly_verdicts.json`（`{code: Verdict}`），供读取侧同步。

### 4.3 读取侧注入

- **`/data/latest`**（`routes/data.py:55`）：`results[code] = {"level": item, "anomaly": verdict_for(code)}`。
- **`/data/flow-raw`**（`routes/data.py:44`）：返回前**浅拷贝**响应再把 `anomaly` 挂到 `data[0]`（最新 record）——不得原地改共享缓存对象，避免污染其它读取者。
- **`/data/warnings`**（`routes/data.py:70`）：
  - 新增 `data_anomalies` 数组：从 AlertTracker 活跃事件里筛 `category == "数据异常"`，按 §6.2 契约映射成预警项。
  - 现有 `alerts[]` 合并循环（`routes/data.py:139`）**跳过** `category == "数据异常"` 的事件，避免与 `data_anomalies` 重复计数。
  - 返回体加 `data_anomaly_count`。

`verdict_for(code)` 从 `anomaly_verdicts.json` 读，带 max_age（裁决超过 15 分钟视为过期 → 返回 `{flagged:false}`，防止陈旧误标）。

## 5. 前端组件

### 5.1 `web/src/utils/warningLevel.js`（扩展）
- `levelLabel`：`数据异常` 原样返回。
- `levelBadgeClass`：`if (s === '数据异常') return 'anomaly'`。
- `levelSeverity`：`数据异常` 返回 `3.5`（低于蓝色预警 3、高于提示 4——可见但不压过真实洪水预警）。

### 5.2 徽章样式（`web/src/styles/components.css` 或 OverviewPage 局部）
新增 `.badge.anomaly` 与 `.hud-card-note.anomaly`：紫色（`var(--anomaly, #7c3aed)` 或复用 `--accent` 紫），区别于洪水四色。

### 5.3 `OverviewPage.vue`
- `api.getLatest` 已取到每站数据；扩展解析：读 `it.anomaly` 填入 `stationData[code].anomaly`。
- 当前站卡片：水位/流量卡片若 `flagged` → 卡片 note 显示「⚠ 数据存疑」紫色徽章，`title`/悬浮显示 `reason`。**数值仍显示原值，不修正。**
- 预警面板：`refreshData` 的 `allWarnings` 合并 `warnData.data_anomalies`；列表项按 category 紫色左边框。
- 底部过程图：当前点（实测最后一点）若 flagged → TrendChart 接受 `markLast` 标红/紫圈（TrendChart 增一个可选 prop）。
- `loadStationDetail`：抽屉同步带 `anomaly`，详情区追加「数据质量」行。

### 5.4 `HydroMap.vue`
悬浮卡与角标：站点 `data.anomaly?.flagged` → 角标加紫色 ⚠，悬浮卡多一行「数据存疑：{reason}」。

### 5.5 `StationDrawer.vue`
新增「数据质量」stat 行：flagged 时紫色显示 `数据存疑` + 详情面板写明 `reason`。

### 5.6 `WarningsPage.vue`
列表渲染兼容新类别（`type === '数据异常'`），紫色徽章 + 左边框。

## 6. 数据契约

### 6.1 Verdict（`anomaly_verdicts.json[code]`，内部 + `/data/latest` 的 `anomaly` 字段）
```json
{
  "flagged": true,
  "type": "flow_level_inconsistency",
  "severity": "medium",
  "reason": "近1h流量出现突刺(峰值220 m³/s)而水位波动<2cm，水位正常但流量异常突变，疑似流量计故障或上游virtualFlow计算异常。",
  "source": "llm",
  "confidence": 0.8,
  "evaluated_at": "2026-07-19T14:05:00"
}
```
- `type`: `flow_level_inconsistency | level_flow_inconsistency | frozen | invalid_value | gap_masking`
- `severity`: `low | medium | high`
- `source`: `llm | prefilter | none`（`none` = 未 flagged）

### 6.2 `/data/warnings` 新增 `data_anomalies[]` 项
```json
{
  "id": "DA-00125-flow_level_inconsistency",
  "type": "数据异常",
  "category": "数据质量",
  "name": "流量-水位不一致",
  "level": "数据异常",
  "station_code": "00125",
  "value": 220,
  "unit": "m³/s",
  "message": "近1h流量出现突刺(峰值220 m³/s)而水位波动<2cm，**水位正常但流量异常突变**，疑似流量计故障或上游virtualFlow计算异常。建议核查设备并暂缓采信该流量值。",
  "time": "2026-07-19T14:05:00"
}
```
`message` 前端用现有 `renderMessage` 渲染 `**加粗**`。

## 7. 关键设计决策（已与用户确认）

1. **触发方式**：MonitorEngine 定时巡检 + 廉价预筛 → 仅可疑站调 LLM。
2. **判断范围**：水位↔流量一致性（双向）+ 数据冻结 + 不可能值 + 缺测伪装。
3. **预警归类**：新增「数据异常」类别（紫色），与洪水预警/系统告警并列。
4. **裁决下发**：后端挂到读数（方案 A），常驻、多端一致、前端零额外请求。
5. **数值显示**：被标注时仍显示原始值 + 「⚠ 数据存疑」徽章 + reason，**不修正数值**。
6. **预筛用 MAD-z** 而非 std-z，避免突刺撑大标准差导致自漏判；预筛是固定统计门，非人工配置阈值。

## 8. 错误处理与降级

| 场景 | 行为 |
|---|---|
| LLM 超时/熔断（quick_ask 返回 ""） | 退化为 `source:"prefilter"` 弱标注，用预筛理由文案 |
| LLM 返回非 JSON | 同上退化 |
| 序列不足（<6 实测点） | 不评判，`flagged:false, source:"none"` |
| `anomaly_verdicts.json` 读取失败 | 读取侧按 `flagged:false` 兜底，不阻塞主数据 |
| 裁决陈旧（>15 分钟） | 视为过期，清除标注 |
| AlertTracker 写失败 | 仅日志，不阻塞裁决落盘 |

## 9. 测试策略

- **预筛单元测试**（纯函数，最好测）：构造 5 类序列（正常/流量突刺水位稳/水位突刺流量稳/冻结/含负值/缺测），断言命中理由正确；MAD≈0 不除零。
- **judge_station**：mock `quick_ask` 返回合法 JSON / 非法 JSON / 空串三种，断言裁决与降级路径。
- **读取侧**：mock `anomaly_verdicts.json`，断言 `/data/latest`、`/data/flow-raw`、`/data/warnings` 的字段注入。
- **前端**：`warningLevel` 新分支单测；OverviewPage/Drawer/Map 在 `anomaly.flagged=true` 下渲染徽章的快照/渲染断言。

## 10. 涉及文件清单

**后端（新增/改）**
- 新增 `gateway/services/anomaly_judge.py`
- 新增 `gateway/data/anomaly_verdicts.json`（运行时生成）
- 改 `gateway/services/monitor_engine.py`（_check_station 末尾挂裁决）
- 改 `gateway/routes/data.py`（/latest、/flow-raw、/warnings 注入）
- 新增 `gateway/tests/test_anomaly_judge.py`

**前端（改）**
- `web/src/utils/warningLevel.js`（新类别）
- `web/src/api/index.js`（如有类型补全，可选）
- `web/src/pages/OverviewPage.vue`（卡片/面板/图/抽屉同步）
- `web/src/components/HydroMap.vue`（角标 + 悬浮卡）
- `web/src/components/StationDrawer.vue`（数据质量行）
- `web/src/components/TrendChart.vue`（`markLast` 可选 prop）
- `web/src/pages/WarningsPage.vue`（新类别渲染）
- `web/src/styles/*`（`.badge.anomaly` 紫色）
