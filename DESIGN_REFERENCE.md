# 流量监测预报智能指挥舱设计参考与当前设计思路

## 1. 文档目的

本文档记录本项目当前静态原型阶段的设计参考来源、实际检索并读取过的 GitHub 项目内容、可借鉴的设计模式，以及当前 `index.html` 原型的页面设计思路与后续演进方向。

项目目标是构建一个面向水利/流量监测业务的“流量监测预报智能指挥舱”，核心能力包括：

- 接入监测设备实时视频；
- 展示设备实时输出的流量、水位等监测数据；
- 展示模型预报结果；
- 管理预警信息；
- 生成日报与智能分析结果；
- 中央区域展示 3D 地图或监测站点三维数字孪生画面；
- 融入智能体项目 [FloodMind](https://github.com/dancepandas/FloodMind)；
- 支持自然语言下达任务，如数据分析、模型调用、报告生成、任务编排等。

当前阶段是单文件静态 HTML 原型，文件为：

```text
index.html
```

---

## 2. 实际检索并读取过的 GitHub 项目

> 说明：本节只记录实际通过 GitHub API 获取到 README、目录结构或源码片段的项目。未实际读取内容的项目不作为确定性参考依据。

### 2.1 L-noodle/vue-big-screen

仓库地址：

[https://github.com/L-noodle/vue-big-screen](https://github.com/L-noodle/vue-big-screen)

#### 项目定位

README 中说明该项目是一个基于以下技术的大数据可视化大屏模板：

- Vue
- DataV
- ECharts

README 中明确描述：

- 这是一个“数据大屏项目”；
- 通过 Vue 组件实现数据动态刷新渲染；
- 内部图表可自由替换；
- 部分图表使用 DataV 自带组件；
- 提供了 Gitee 地址，便于国内访问。

#### 实际读取到的目录结构

读取到的主要目录包括：

```text
src/
  App.vue
  assets/
  components/
  main.js
  router/
  store/
  views/
```

其中 `src/views` 下包括：

```text
bottomLeft.vue
bottomRight.vue
center.vue
centreLeft1.vue
centreLeft2.vue
centreRight1.vue
centreRight2.vue
index.vue
```

`src/components` 下有：

```text
echart/
```

#### 实际读取到的页面结构

在 `src/views/index.vue` 中，看到项目使用了 DataV 的全屏容器和装饰组件：

- `dv-full-screen-container`
- `dv-loading`
- `dv-decoration-10`
- `dv-decoration-8`
- `dv-decoration-6`
- `dv-border-box-12`
- `dv-border-box-13`

其页面结构是典型的大屏布局：

1. 顶部标题区；
2. 左右装饰线；
3. 左侧数据模块；
4. 中央主视觉模块；
5. 右侧数据模块；
6. 底部图表模块。

#### 实际读取到的组件模式

在 `src/views/center.vue` 中，看到以下组件模式：

- 顶部数字指标块；
- `dv-digital-flop` 数字翻牌；
- `dv-scroll-ranking-board` 滚动排行榜；
- `dv-water-level-pond` 水位池组件。

在 `src/views/centreRight1.vue` 中，看到：

- `dv-scroll-board` 滚动表格；
- 表格配置包含 `header`、`data`、`rowNum`、`headerBGC`、`oddRowBGC`、`evenRowBGC`、`index`、`align` 等。

#### 对本项目的借鉴点

该项目对本系统的直接借鉴点包括：

- 全屏大屏容器思路；
- 顶部中心标题 + 两侧装饰线；
- 左中右 + 底部的指挥舱布局；
- 数据指标动态化表达；
- 滚动列表/滚动看板；
- 科技风边框组件；
- ECharts 图表区域可替换思想；
- 中央主视觉区域优先级最高。

---

### 2.2 qiyankai/Big-Screen-Vue-Datav-Echarts

仓库地址：

[https://github.com/qiyankai/Big-Screen-Vue-Datav-Echarts](https://github.com/qiyankai/Big-Screen-Vue-Datav-Echarts)

#### 项目定位

README 中说明该项目是一个“政务大屏-前端”，技术栈为：

- Vue
- DataV
- ECharts

它的 README 还说明：

- 项目来源于 DataV 大屏模板；
- 项目需要全屏展示，建议按 F11；
- 拉取项目后，建议按照自己的功能区域重命名文件；
- 使用 Vue 组件实现数据动态刷新渲染；
- 内部图表可自由替换。

#### 实际读取到的目录结构

读取到的主要目录包括：

```text
src/
  App.vue
  assets/
  common/
  components/
  main.js
  router/
  store/
  utils/
  views/
```

其中 `src/views` 下包括：

```text
bottomLeft.vue
bottomRight.vue
center.vue
centerLeft1.vue
centerLeft2.vue
centerRight1.vue
centerRight2.vue
index.vue
```

#### 实际读取到的页面结构

在 `src/views/index.vue` 中，看到它同样使用：

- `dv-full-screen-container`
- `dv-loading`
- `dv-decoration-*`
- `dv-border-box-*`

相比 `L-noodle/vue-big-screen`，它更偏向政务大屏表达，并且在样式上使用了 `rem` 单位，更适合在不同大屏尺寸下进行缩放适配。

#### 对本项目的借鉴点

该项目对本系统的直接借鉴点包括：

- 政务/指挥中心类信息架构；
- 更明确的业务模块命名方式；
- 全屏展示优先；
- rem 或比例缩放适配思路；
- 顶部时间、标题、业务标签分区；
- 左右两侧挂载业务看板，中间承载态势地图。

对于本项目的水利监测场景而言，这类政务大屏的组织方式比较贴合：

- 左侧：视频监测；
- 中央：流域数字孪生；
- 右侧：实时指标、预警、日报；
- 底部：历史/预报趋势与智能体任务。

---

### 2.3 jay86cn/techui-vue2

仓库地址：

[https://github.com/jay86cn/techui-vue2](https://github.com/jay86cn/techui-vue2)

#### 项目定位

README 中说明：

- `TechUI-Vue2` 已废弃；
- 新版本为 `TechUI-Scifi`；
- TechUI 系列定位于动态 SVG UI 组件库；
- 偏科幻风、未来感 UI。

README 中列出的相关库包括：

- TechUI-Scifi
- TechUI-Base
- TechUI-Admin
- TechUI-Prime

#### 注意事项

当前只读取到了 `techui-vue2` README 中对新版组件库的介绍，并没有实际读取新版 `TechUI-Scifi` 的源码。因此，本项目只将其作为“科幻风组件方向”的参考，而不将其作为已深入研究的源码依据。

#### 对本项目的借鉴点

该项目对本系统的启发主要在视觉层面：

- SVG 动态组件；
- 科幻风边框；
- 未来感装饰；
- 动态线条、光效和科技面板；
- 适合深蓝科技风指挥舱。

但当前原型仍以原生 HTML/CSS/SVG 为主，没有引入该组件库。

---

### 2.4 satnaing/shadcn-admin

仓库地址：

[https://github.com/satnaing/shadcn-admin](https://github.com/satnaing/shadcn-admin)

#### 项目定位

README 中说明该项目是一个基于以下技术的 Admin Dashboard UI：

- Shadcn
- Vite

README 中列出的特性包括：

- Light / dark mode；
- Responsive；
- Accessible；
- Built-in Sidebar component；
- Global search command；
- 10+ pages；
- Extra custom components；
- RTL support。

#### 实际读取到的目录结构

读取到的主要目录包括：

```text
src/
  assets/
  components/
  config/
  context/
  features/
  hooks/
  lib/
  routes/
  stores/
  styles/
```

其中 `src/features` 下包括：

```text
apps/
auth/
chats/
dashboard/
errors/
settings/
tasks/
users/
```

`src/components` 下包括：

```text
command-menu.tsx
config-drawer.tsx
confirm-dialog.tsx
data-table/
date-picker.tsx
layout/
profile-dropdown.tsx
search.tsx
theme-switch.tsx
ui/
```

#### 实际读取到的 Dashboard 页面

在 `src/features/dashboard/index.tsx` 中，看到 Dashboard 页面包含：

- `Header`
- `TopNav`
- `Search`
- `ThemeSwitch`
- `ConfigDrawer`
- `ProfileDropdown`
- `Tabs`
- `Card`
- `Overview`
- `Analytics`
- `RecentSales`

页面结构是现代后台系统常见模式：

1. 顶部导航；
2. 搜索入口；
3. 主题切换；
4. 配置抽屉；
5. 用户菜单；
6. 标签页切换；
7. 卡片化指标；
8. 图表与列表组合。

#### 实际读取到的 Sidebar 结构

在 `src/components/layout/app-sidebar.tsx` 中，看到：

- `Sidebar`
- `SidebarHeader`
- `SidebarContent`
- `SidebarFooter`
- `SidebarRail`
- `NavGroup`
- `NavUser`
- `TeamSwitcher`

#### 对本项目的借鉴点

该项目对本系统的启发主要是“从展示大屏走向可操作平台”：

- 全局搜索/命令入口；
- 配置抽屉；
- 任务中心；
- 用户/值班员入口；
- 后续可扩展多页面；
- 可访问性和响应式设计；
- 更现代的 Dashboard 交互逻辑。

当前 `index.html` 已根据这个方向加入了：

- 全局指挥面板；
- `Ctrl + K` 快捷键；
- 系统配置抽屉；
- 快捷操作按钮；
- 智能体指令入口。

---

### 2.5 Kiranism/next-shadcn-dashboard-starter

仓库地址：

[https://github.com/Kiranism/next-shadcn-dashboard-starter](https://github.com/Kiranism/next-shadcn-dashboard-starter)

#### 项目定位

README 中说明它是一个后台 Dashboard Starter，技术栈为：

- Next.js 16
- shadcn/ui
- Tailwind CSS
- TypeScript

实际读取到根目录中包括：

```text
src/
docs/
components.json
CLAUDE.md
AGENTS.md
package.json
next.config.ts
```

#### 对本项目的借鉴点

该项目不是数据大屏，而是现代后台模板。它对当前项目的价值主要在后续工程化阶段：

- 如果后续从单文件 HTML 转为 React / Next.js；
- 如果需要用户系统、任务系统、报表系统；
- 如果需要组件化、路由化、权限管理；
- 如果要接入 FloodMind 智能体后台；
- 如果要把“指挥舱”扩展为“监测预报平台”。

当前静态原型阶段没有直接套用其实现，只参考其现代后台组织方式。

---

## 3. 当前原型的设计定位

当前页面不是传统后台，也不是纯展示大屏，而是介于两者之间：

```text
数据大屏 + 数字孪生 + 监测视频 + 预警调度 + 智能体任务台
```

因此设计上采用了两类参考的组合：

1. **DataV / ECharts 大屏类项目**  
   用于指导视觉布局、全屏展示、装饰边框、图表区域、滚动列表等。

2. **shadcn-admin 类现代 Dashboard**  
   用于指导可操作交互、全局命令、设置抽屉、任务入口、后续平台化扩展等。

---

## 4. 当前页面信息架构

当前 `index.html` 的主体结构如下：

```text
顶部栏
├── 实时接入状态
├── 全局指挥 Ctrl K
├── 系统标题
├── 当前时间
└── 系统配置

主体区域
├── 左侧：设备监测画面
│   ├── 上游闸口视频
│   └── 桥涵断面视频
│
├── 中央：监测设备分布 / 三维数字孪生态势
│   ├── 流域地图示意
│   ├── 站点分布
│   ├── 风险站点
│   ├── 地图模式切换
│   └── 态势摘要
│
└── 右侧：业务状态
    ├── 实时指标
    ├── 预警信息
    └── 日报 / 智能分析

底部区域
├── 历史数据与预报数据
└── 智能体任务

悬浮层
├── 快捷按钮
├── 3D 机器人
├── 智能体对话框
├── 视频放大弹窗
├── 详情弹窗
├── 全局指挥面板
└── 系统配置抽屉
```

---

## 5. 当前核心模块设计说明

### 5.1 顶部栏

顶部栏承担全局状态和全局操作入口：

- 实时接入状态；
- 全局指挥入口；
- 系统标题；
- 当前时间；
- 系统配置入口。

其中“全局指挥”借鉴了 `shadcn-admin` 中全局搜索/Command Menu 的思路，让系统不只是展示数据，而是可以通过命令触发操作。

当前支持：

- 点击打开；
- `Ctrl + K` 打开；
- 搜索过滤；
- 点击指令执行。

---

### 5.2 左侧实时视频监测

左侧展示两个实时监测画面：

- 上游闸口；
- 桥涵断面。

每个视频卡片包含：

- 模拟视频画面；
- 摄像头编号；
- AI 识别状态；
- 实时状态；
- 局部指标条，如流速、雨量、风险等级。

交互能力：

- 鼠标悬停时提示点击放大；
- 点击后打开居中视频放大弹窗；
- 放大弹窗支持上一画面/下一画面切换；
- 显示当前画面序号；
- 显示实时 AI 研判。

这个模块后续可以对接真实视频流，例如：

- RTSP 转 HLS；
- WebRTC；
- 视频截图流；
- AI 视频分析结果接口。

---

### 5.3 中央数字孪生态势

中央区域是整个页面的主视觉，负责表达：

- 流域结构；
- 河道走向；
- 监测站点位置；
- 风险站点；
- 设备链路；
- 预报可信度。

当前使用 SVG 和 CSS 模拟流域数字孪生视图。

已实现交互：

- 站点可点击查看详情；
- 风险站点有高亮/闪烁效果；
- 地图模式按钮可切换高亮：
  - 数字孪生；
  - 风险热力；
  - 设备链路。

当前地图底部有态势摘要：

- 风险站点数量；
- 视频链路在线数量；
- 预报可信度。

后续可以演进为：

- Mapbox / Cesium / Three.js；
- 三维站点模型；
- 地形与河道模型；
- 监测设备数字孪生；
- 风险热力图；
- 站点点击联动视频、指标和预警。

---

### 5.4 右侧实时指标

根据反馈，实时指标已调整为更清晰的紧凑版本，只突出两个核心实时监测值：

```text
实时监测流量
实时监测水位
```

当前设计为两行卡片：

```text
实时监测流量          2,118 m³/s
较 10 分钟前 ↑ 3.2%

实时监测水位          7.84 m
距警戒水位 0.06m
```

这样比之前四宫格指标更适合当前右侧窄面板，避免数字被裁切。

---

### 5.5 预警信息

预警信息区域用于展示当前风险事件。

当前包含：

- 城西站水位超警戒；
- 泵闸站流量突增；
- 下游站通信延迟；
- 南桥站水位回落。

每个预警条目支持点击查看详情。

设计上增加了风险进度条，用于表达风险强度：

- 橙色/红色预警进度更高；
- 黄色预警进度中等；
- 已解除预警进度较低。

后续可以加入：

- 预警确认；
- 派单；
- 处置记录；
- 责任人；
- 预警闭环状态；
- 预警和模型预报联动。

---

### 5.6 日报 / 智能分析

日报区域用于展示智能体或系统定时生成的分析结果，例如：

- 今日流域运行简报；
- 模型预报一致性检查；
- 设备在线率日报；
- 预警处置复盘。

每个日报条目可点击查看详情。

后续可接入 FloodMind 自动生成：

- 日报；
- 周报；
- 风险摘要；
- 模型对比报告；
- 处置复盘报告。

---

### 5.7 历史数据与预报数据

底部左侧为历史和预报趋势图。

当前使用 SVG 模拟：

- 历史监测区；
- 模型预报区；
- 当前时间分割线；
- 流量曲线；
- 水位曲线；
- 预报虚线；
- 鼠标悬停数值提示。

设计目标是让用户直观看到：

- 过去几天的水位/流量变化；
- 当前时刻；
- 未来 24h / 48h / 72h 预报；
- 预报可信度。

后续可以替换为 ECharts：

- 双 Y 轴；
- tooltip；
- dataZoom；
- markLine；
- markArea；
- 预报置信区间；
- 多模型对比。

---

### 5.8 智能体任务

底部右侧为智能体任务区。

当前支持：

- 展示已有任务；
- 点击任务查看详情；
- 新增任务；
- 输入自然语言指令；
- 模拟任务编排结果。

新增任务会打开 FloodMind 智能体对话框，并自动填入：

```text
我要新增一个智能体任务：
```

后续应接入真实 FloodMind 能力：

- 意图识别；
- 数据检索；
- 工具调用；
- 模型调用；
- 报告生成；
- 定时任务保存；
- 任务执行状态追踪。

---

### 5.9 全局指挥面板

当前新增的全局指挥面板是一个重要交互层。

它参考了 `shadcn-admin` 中 Global Search Command 的思路，但改造成适合本项目的“指挥命令入口”。

当前内置指令包括：

- 定位数字孪生地图；
- 查看当前预警；
- 生成今日运行日报；
- 调用预报模型模拟；
- 打开上游闸口视频；
- 打开系统配置。

设计意义：

- 将页面从静态展示变成可操作系统；
- 让智能体入口不仅是聊天框，也可以是命令面板；
- 后续可以根据用户输入动态匹配工具和任务。

---

### 5.10 系统配置抽屉

系统配置抽屉参考了现代后台中的 Config Drawer。

当前包括三组配置：

#### 自动化任务

- 06:00 自动巡检；
- 08:30 流域日报；
- 预警处置复盘。

#### 模型与数据

- LSTM / 水动力融合；
- 视频 AI 摘要入库；
- 异常数据自动剔除。

#### 通知策略

- 橙色预警短信；
- 值班群推送；
- 日报自动归档。

每个开关可以点击切换状态。

后续可以接入真实配置接口。

---

## 6. 视觉设计方向

当前采用的视觉方向为：

```text
深蓝科技风 + 水利数字孪生 + 指挥调度大屏
```

视觉关键词：

- 深蓝背景；
- 青色主光；
- 绿色正常态；
- 黄色关注态；
- 红色预警态；
- 玻璃拟态面板；
- SVG 地图；
- 动态扫描线；
- 发光边框；
- 数据卡片；
- 悬浮机器人；
- 科技感弹窗。

需要避免的问题：

- 过度装饰导致信息不可读；
- 数字太大导致裁切；
- 面板塞入过多信息；
- 科技风控件没有实际交互；
- 只像展示页，不像系统。

因此当前设计正在向两个方向平衡：

1. 保持大屏视觉冲击力；
2. 增强真实系统的可操作性。

---

## 7. 当前交互能力清单

当前静态原型已经实现以下交互：

### 视频相关

- 点击监测画面放大；
- 居中展示视频弹窗；
- 上一画面/下一画面切换；
- 点击背景关闭；
- `Esc` 关闭。

### 地图相关

- 点击站点查看详情；
- 地图模式按钮切换；
- 风险站点闪烁。

### 预警/日报/任务相关

- 点击预警查看详情；
- 点击日报查看详情；
- 点击智能体任务查看详情。

### 智能体相关

- 点击 3D 机器人打开对话；
- 点击新增任务打开智能体对话；
- 输入自然语言指令；
- 模拟智能体响应。

### 全局操作

- `Ctrl + K` 打开全局指挥；
- 搜索指令；
- 执行指令；
- 打开配置抽屉；
- 切换配置项；
- `Esc` 关闭弹窗/抽屉。

---

## 8. 后续工程化建议

当前是单文件 HTML 原型，适合快速确认效果。后续建议按以下阶段推进。

### 阶段一：静态原型完善

- 继续优化视觉层级；
- 调整不同屏幕比例下的布局；
- 增加更多真实业务字段；
- 增加站点详情卡；
- 增加预警处置流程；
- 增加报告预览页面。

### 阶段二：组件化重构

可选技术路线：

#### Vue 路线

适合继续借鉴 DataV / ECharts 大屏生态：

- Vue 3；
- Vite；
- ECharts；
- DataV 或自研装饰组件；
- Pinia；
- Vue Router。

#### React / Next 路线

适合后续做完整平台：

- React / Next.js；
- shadcn/ui；
- Tailwind CSS；
- ECharts 或 AntV；
- Zustand / Redux；
- TanStack Query。

### 阶段三：数据接入

需要接入：

- 实时流量接口；
- 实时水位接口；
- 设备在线状态接口；
- 预警接口；
- 模型预报接口；
- 日报/报告接口；
- 视频流接口。

### 阶段四：FloodMind 智能体集成

建议将 FloodMind 能力包装为后端服务接口，例如：

- `/agent/chat`
- `/agent/task/create`
- `/agent/task/list`
- `/agent/report/generate`
- `/agent/model/run`
- `/agent/warning/analyze`

前端通过自然语言输入触发：

```text
意图识别 → 参数抽取 → 数据检索 → 工具调用 → 结果解释 → 报告生成/任务保存
```

### 阶段五：数字孪生升级

可选方案：

- SVG 2.5D 示意图；
- Mapbox 地图；
- Cesium 三维地理场景；
- Three.js 站点模型；
- WebGL 河道/地形可视化。

---

## 9. 当前版本：水文监测指挥核心应用界面

当前 `index.html` 已从早期“深蓝科技大屏”原型，迭代为一版更克制、更产品化的 **水文监测指挥核心应用界面**。

### 9.1 设计定位

当前版本不是官网宣传页，也不是传统霓虹数据大屏，而是一个面向值班人员和调度人员的单屏工作台：

```text
Apple 风格高级灰白应用界面 + 水文监测指挥核心 + FloodMind 智能体辅助研判
```

设计目标：

- 默认一个浏览器视口内完整展示核心工作区；
- 用低噪声的灰白背景、半透明白色卡片和中性阴影提升高级感；
- 保持水文业务色彩：河流蓝、苔藓绿、陶土红/预警色；
- 统一数据字号与等宽数字排版，避免指标视觉跳动；
- 让界面看起来像真实应用，而不是一次性展示海报。

### 9.2 当前页面结构

当前应用界面包含：

```text
左侧导航
├── 产品标识
├── 流域总览
├── 监测站点
├── 预警处置
├── 模型预报
├── 视频巡检
└── 日报归档

顶部栏
├── 当前页面标题：流域态势
├── 当前系统时间
├── 生成日报
└── 智能研判

核心指标区
├── 实时监测水位
├── 实时监测流量
├── 模型可信度
└── 待处置预警

主工作区
├── 监测设备分布与流域态势地图
├── 图层切换：流域态势 / 风险热力 / 设备链路 / 调度推演
├── 站点点击详情
├── 预警处置列表
└── 未来 72 小时模型预报

底部辅助区
├── 视频巡检
└── FloodMind 智能体自然语言调度
```

### 9.3 当前交互能力

当前静态原型已实现：

- 实时时钟；
- 左侧导航高亮切换；
- 地图图层按钮切换；
- 站点、预警、视频卡片点击详情弹窗；
- “生成日报”弹窗；
- “智能研判”弹窗；
- FloodMind 智能体输入模拟回复；
- `Esc` 或点击背景关闭弹窗。

### 9.4 视觉规范

当前视觉方向：

- 主背景：Apple 式高级灰白渐变；
- 卡片：白色半透明玻璃质感；
- 阴影：低透明度中性灰阴影；
- 数据字体：等宽数字、统一字号、tabular nums；
- 业务色：
  - 河流蓝：水位、流量、地图水系；
  - 苔藓绿：正常、在线、可信；
  - 陶土红：风险、橙色预警、阈值接近；
  - 琥珀色：黄色预警、关注状态。

---

## 10. 当前文件说明

当前仓库主要文件：

```text
index.html              # 静态原型页面
DESIGN_REFERENCE.md     # 设计参考与当前设计思路文档
```

`index.html` 当前包含：

- 单文件 HTML / CSS / JavaScript；
- 一屏应用布局；
- Apple 高级灰白视觉风格；
- 左侧导航和顶部指挥栏；
- 核心实时指标卡片；
- SVG 流域地图和站点分布；
- 预警处置列表；
- 未来 72 小时模型预报图；
- 视频巡检卡片；
- FloodMind 智能体自然语言调度区域；
- 弹窗详情和模拟交互。

---

## 11. 总结

当前设计不是单纯模仿某一个项目，而是结合了早期读取过的开源项目经验，并根据后续反馈转向更克制的产品应用界面：

1. **DataV / Vue / ECharts 大屏项目**  
   提供大屏布局、装饰组件、数字翻牌、滚动列表、全屏展示等参考。

2. **shadcn-admin 类现代 Dashboard 项目**  
   提供全局搜索、命令菜单、配置抽屉、任务中心、系统化交互等参考。

本项目当前的方向是：

```text
从“水利监测展示大屏”升级为“可操作、可调度、可接入智能体的一屏水文监测指挥核心”。
```

后续如果继续迭代，应优先围绕以下几件事展开：

- 接入真实实时数据；
- 图表组件化；
- 视频流接入；
- FloodMind 智能体后端对接；
- 预警处置闭环；
- 模型预报结果解释；
- 数字孪生地图升级。
