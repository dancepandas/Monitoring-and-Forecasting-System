# UI 前端改造交接文档

> 生成时间：2026-07-10  
> 当前分支：`feature/3d-terrain-model`  
> 用途：只涉及**前端界面美化**，不包含功能逻辑/后端改动。

---

## 一、技术栈

| 项目 | 技术 |
|------|------|
| 框架 | Vue 3 + `<script setup>` Composition API |
| 路由 | vue-router 4 |
| 构建 | Vite 8 |
| 地图 | CesiumJS 1.142 |
| 3D 模型 | Three.js 0.185.1 |
| 状态管理 | Pinia |
| 报告预览 | docx-preview 0.4.0 |
| 视频流 | flv.js 1.6.2 |
| 样式 | 原生 CSS + CSS 变量 |

---

## 二、当前视觉方向

暗色驾驶舱 / 指挥舱风格：

- 深色背景，Cesium 地图打底
- 玻璃态/半透明面板
- 终端式标题、大圆角、少边框
- 中文界面，前端不展示站点编码

相关记忆：`memory/dark-cockpit-redesign.md`

---

## 三、UI 同事需要修改的文件

### 3.1 全局样式（优先看）

| 文件 | 作用 |
|------|------|
| `web/src/styles/tokens.css` | 颜色、字体、阴影、圆角、状态色变量 |
| `web/src/styles/layout.css` | 布局网格、面板、导航、暗色主题覆盖 |
| `web/src/styles/components.css` | 按钮、卡片、badge、列表、表格 |

### 3.2 页面（重点）

| 文件 | 当前界面 | UI 关注点 |
|------|----------|-----------|
| `web/src/pages/OverviewPage.vue` | 2×2 视频监控墙 | 视频格子、hover、离线态、与四周卡片的层级 |
| `web/src/pages/ReportsPage.vue` | Word 文档阅读器 | 顶部工具栏、加载/空状态、纸张容器、底色 |
| `web/src/pages/WarningsPage.vue` | 告警列表 | 告警级别色块、时间展示、操作按钮 |
| `web/src/pages/AdminSettingsPage.vue` | 系统配置 | 阈值标签、表单间距、卡片排版 |
| `web/src/pages/AppLayout.vue` | 整体布局壳 | 导航、TabBar、全局背景 |

### 3.3 组件

| 文件 | 作用 |
|------|------|
| `web/src/components/CesiumMap.vue` | 地图底图 |
| `web/src/components/StationDrawer.vue` | 站点详情抽屉 |
| `web/src/components/TabBar.vue` | 顶部 Tab 导航 |
| `web/src/components/TrendChart.vue` | 自绘趋势图 |
| `web/src/components/Topbar.vue` | 页面标题栏 |
| `web/src/components/TerrainModel3D.vue` | 3D 地形（当前首页未使用） |

### 3.4 路由

| 文件 | 作用 |
|------|------|
| `web/src/router/index.js` | 页面路由 |

---

## 四、打包给 UI 的最小文件集

```text
web/src/pages/
web/src/components/
web/src/styles/
web/package.json
web/package-lock.json
```

> 不需要后端、不需要脚本、不需要 3D 模型文件、不需要 GeoJSON/地形数据。

---

## 五、本地预览

```bash
cd web
npm install
npm run dev
```

默认地址：`https://localhost:5177/`

报告页面需要后端接口数据才能看到 Word 预览；其他页面基本可以独立预览。

---

## 六、约束条件

1. **前端不显示站点编码**，只显示站点名称。
2. **中文界面**，按钮、标题、标签全部中文。
3. **暗色主题优先**，新增样式适配暗色背景。
4. **滚动条默认隐藏**（`tokens.css`），但内容区域仍需可滚动。
5. **报告预览保持 Word 阅读器风格**，不要厚重边框。

---

## 七、建议优先美化项

1. **OverviewPage 四宫格视频墙**
   - 视频 cell 边框、圆角、hover 效果
   - 离线/加载中的空状态
   - 面板头部站点名 + 状态设计

2. **ReportsPage 报告阅读器**
   - 顶部工具栏图标化
   - 加载动画、空状态
   - 文档纸张阴影与边距

3. **WarningsPage 告警列表**
   - 级别颜色 badge
   - 时间排版
   - 操作按钮样式

4. **全局**
   - Topbar 标题字体
   - panel 卡片圆角/描边/hover
   - 按钮统一为 pill/capsule 风格

---

*本交接只含前端界面相关文件，功能逻辑请勿改动。*
