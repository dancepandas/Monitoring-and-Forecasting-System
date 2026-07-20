# 3D 地形站点全息光柱设计

**日期**: 2026-07-10  
**状态**: 设计已确认，待写实施计划  
**依赖**: `feature/3d-terrain-model` 分支现有实现（`TerrainModel3D.vue` 加载 `terrain.glb` + `terrain_meta.json`）

## 背景

当前 `TerrainModel3D.vue` 已实现基础的青色光柱 + 站名/水位/流量 Sprite。用户希望整体升级中间站点展示：提升科技感、信息密度、辨识度，并与右侧水文抽屉联动更自然。

参考示例图中数字孪生流域大屏的风格，采用**全息光柱 + 数据飘带**方案。

## 决策汇总

| 维度 | 决策 |
|------|------|
| 整体风格 | 全息光柱 + 脉冲底座 + 数据飘带；3D 模型同步优化视觉/性能/交互 |
| 文件范围 | 主要修改 `web/src/components/TerrainModel3D.vue`；Python 脚本加 Draco 压缩 |
| 顶部光晕 | 不要额外的 Sprite 光晕，保留实心光球 |
| 预警来源 | 后端返回 `warning_level`/`danger_level`，前端比较当前水位 |
| 动画实现 | 纯 CPU/Sprite 动画，预渲染脉冲环帧，不引入 Bloom 后处理 |
| 验证方式 | 手动验证 + checklist 文档 |

## 配色规范

| 元素 | 颜色 | 说明 |
|------|------|------|
| 光柱底部 | `#22D3EE` | 青色，半透明 0.2 |
| 光柱顶部 | `#67E8F9` | 亮青色，半透明 0.9 |
| 顶部光球 | `#67E8F9` | 实心发光球 |
| 脉冲底座环 | `#22D3EE` | 正常状态 |
| 预警状态 | `#F97316` / `#EF4444` | 橙色/红色 |
| 站名标签 | `#E0FBFC` 字 + 深色描边 | 始终面向相机 |
| 数据飘带 | `#E0FBFC` | 水位、流量等宽字体 |
| 数据闪烁 | opacity 脉冲 | 更新时高亮 0.3s |

## 一、站点视觉构成

每个站点渲染为一个 `THREE.Group`，包含以下子对象：

```
StationGroup
├── PulseRing       # 地面脉冲环 Sprite，随时间换帧
├── Pillar          # 渐变半透明圆柱 Mesh
├── TopSphere       # 顶部实心光球 Mesh
├── NameLabel       # 站名 Sprite（始终面向相机）
├── LevelRibbon     # 水位数据飘带 Sprite
└── FlowRibbon      # 流量数据飘带 Sprite
```

### 1.1 脉冲底座环

- 使用 `CanvasTexture` 预渲染 8 帧径向渐变环
- 每帧切换 `material.map`，形成 0.6s/次的扩散动画
- 正常状态颜色 `#22D3EE`
- 预警状态颜色 `#F97316`（超警戒）或 `#EF4444`（超危险），频率加快到 0.25s/次

### 1.2 渐变光柱

- `CylinderGeometry`，高度约 1200m（夸张后模型单位）
- 材质使用 CanvasTexture 贴图，实现纵向渐变：底部淡青色（opacity 0.2）→ 顶部亮青色（opacity 0.9）
- 默认开启一条从上往下的扫描亮线，每帧重绘 CanvasTexture
- 默认不遮挡地形，hover 时透明度整体提升到 0.95

### 1.3 顶部光球

- `SphereGeometry`，颜色 `#67E8F9`
- 不使用额外的 Sprite 光晕

### 1.4 站名标签

- `THREE.Sprite` + CanvasTexture
- 显示站点简称（从 `s.name.split('-').pop()` 取最后一个段）
- 字体：等宽/无衬线，白色 `#E0FBFC`，深色描边
- 始终面向相机（Sprite 默认 billboard）
- 位置：光柱顶部上方约 300m

### 1.5 数据飘带

- 每个站点 2 行：`水位: xx.xx m`、`流量: xx m³/s`
- 使用 Sprite + CanvasTexture
- 位置：站名标签上方，两行错开 250m
- 数据更新时，`material.opacity` 正弦脉冲一次（0.3s）

### 1.6 预警态

- 预警判断：
  ```js
  const isWarning = level >= s.warning_level
  const isDanger = level >= s.danger_level
  ```
- `isDanger` → 光柱/底座环变红，脉冲 0.25s/次
- `isWarning` → 光柱/底座环变橙，脉冲 0.4s/次
- 数据飘带文字颜色同步变化：正常青色、预警橙色、危险红色

## 二、组件架构

### 2.1 改动文件

- `web/src/components/TerrainModel3D.vue`：站点全息光柱 + 3D 场景优化
- `scripts/build_terrain_model.py`：导出 GLB 时启用 Draco 压缩
- `web/src/components/TerrainPanel.vue`（可选）：增加"重置视角"按钮

### 2.2 新增/调整函数

| 函数 | 职责 |
|------|------|
| `buildStations()` | 遍历 `STATIONS` 创建所有站点 Group |
| `buildStation(s)` | 构建单个站点的全部子对象 |
| `makePillarTexture()` | 生成渐变光柱 CanvasTexture |
| `makePulseTextures()` | 预渲染 8 帧脉冲环 CanvasTexture |
| `makeNameTexture(name)` | 生成站名标签 CanvasTexture |
| `makeDataTexture(label, value, unit, alert)` | 生成数据飘带 CanvasTexture |
| `updateStationData(code, data)` | 更新某站数据飘带并触发闪烁 |
| `setStationAlert(code, level)` | 切换光柱/底座颜色与脉冲频率 |
| `fetchAndUpdateData()` | 拉取最新数据并分发更新 |

### 2.3 不拆分独立 composable

站点逻辑集中在 `TerrainModel3D.vue` 内，保持改动最小。

## 三、数据流与交互

### 3.1 加载流程

```
GLTFLoader 加载 terrain.glb
  → fetch terrain_meta.json
  → buildStations() 创建 4 个站点 Group
  → fetchAndUpdateData() 拉取最新数据
  → setInterval(fetchAndUpdateData, 60000)
```

### 3.2 交互行为

| 事件 | 行为 |
|------|------|
| hover 站点 | 光标变 `pointer`；光柱透明度提升到 0.95；底座环暂停脉冲并保持高亮 |
| click 站点 | 命中 → `rotation.pinStation(code)` → `StationDrawer` 滑出；暂停自转 8s |
| 拖拽场景 | `start` 事件暂停自转；`end` 事件后 3s 恢复 |
| 数据更新 | 该站飘带闪烁 0.3s |
| 预警切换 | 颜色/脉冲频率实时变化 |

### 3.3 后端数据契约

接口 `api.getLatest(ALL_STATION_CODES)` 返回的每项需包含：

```js
{
  station_code: string,
  water_level: number,
  virtual_flow: number,
  warning_level: number,   // 新增
  danger_level: number     // 新增
}
```

若后端暂未返回 `warning_level`/`danger_level`，前端 fallback 到 `STATIONS` 配置中的硬编码阈值或默认不标红。

## 四、动画实现

- **脉冲底座环**：预渲染 8 帧 CanvasTexture，每帧切换 `material.map`
- **扫描光带**：在光柱 CanvasTexture 上每帧重绘一条从上往下的亮线
- **数据闪烁**：临时修改 Sprite `material.opacity` 做正弦脉冲
- **不引入 Bloom**：避免 WebGL 后处理兼容性风险

## 五、性能与边界处理

### 5.1 性能

- CanvasTexture 创建后复用，数据更新时重绘贴图而非重建 Sprite
- 脉冲环帧图预渲染，运行时只切换引用
- 限制 `devicePixelRatio <= 2`
- 站点标签/飘带大小随相机距离缩放

### 5.2 错误处理

- `terrain.glb` 加载失败：console 报错，显示 2D 错误提示 Sprite
- `terrain_meta.json` 加载失败：站点 fallback 到固定高度 `MODEL_Z`，不阻断页面
- 后端数据失败：保留旧数据或显示 `--`，不触发预警闪烁
- WebGL 不支持：`try/catch` 捕获，显示降级提示

## 六、验收 Checklist

1. Overview 页 3D 地形加载后，4 个站点显示全息光柱
2. 每个站点有脉冲底座环、渐变光柱、顶部光球、站名、数据飘带
3. hover 时光柱高亮，光标变 `pointer`
4. click 站点右侧 `StationDrawer` 滑出，自转暂停 8s
5. 数据更新时对应站点飘带闪烁
6. 模拟 `water_level >= warning_level` 时底座/光柱变橙，`>= danger_level` 变红，脉冲加快
7. 窗口 resize 后站点标签大小正常
8. 地形颜色层次清晰，河道蓝色可见，远处有雾效自然消融
9. 相机初始视角框住四站，不钻地、不缩放过远/过近
10. GLB 加载有 loading 提示，文件体积 < 10MB
11. 无 WebGL/Console 报错

## 七、3D 模型优化

### 7.1 视觉品质优化

| 项 | 当前问题 | 优化方向 |
|----|---------|---------|
| 地形材质 | 当前使用 `MeshStandardMaterial` 且 `emissive` 偏灰，山体显脏 | 改用 `MeshStandardMaterial`：`vertexColors: true, roughness: 0.6, metalness: 0.08, emissive: 0x000000`，靠顶点色和光照呈现层次 |
| 光照 | 多盏方向光叠加过曝，暗部没有层次 | 固定为：环境光 `#335566`(0.5) + 主方向光 `#aaccdd`(0.9，斜上方) + 补光 `#1e3a4c`(0.3)，统一色温 |
| 背景融合 | 模型边缘与 `#06141D` 背景生硬 | 加 `THREE.Fog('#06141D', 25000, 90000)`，让远处地形自然消融 |
| 河道 | 蓝色顶点不够明显，远看混在山体里 | 河道顶点色从 `#3B82F6` 提亮到 `#60A5FA`，并在前端材质里给河道区域保留顶点色亮度 |
| 场景中心感 | 四站区域不在视觉重心 | 模型加载后相机聚焦 AOI 中心，`controls.target` 设为 `(0,0,MODEL_Z)` |

### 7.2 性能优化

| 项 | 当前状态 | 优化方向 |
|----|---------|---------|
| 网格顶点 | 600×600 = 36 万顶点 | 保持 600×600（视觉效果需要），导出后使用 `gltf-transform` 或 `draco` 压缩 GLB，目标文件 < 10MB |
| 加载 | 同步加载 GLB + meta | 并行发起两个 fetch，GLB 加载期间显示 loading spinner |
| 渲染 | 每帧全量渲染 | 开启 `renderer.frustumCulled = true`；站点标签使用 Sprite 层级，减少 overdraw |
| 像素比 | 可能 >2 导致移动端吃力 | 限制 `setPixelRatio(Math.min(window.devicePixelRatio, 2))`（已做，保留） |

### 7.3 交互体验优化

| 项 | 优化方向 |
|----|---------|
| 初始视角 | 相机位于 AOI 中心斜上方 35°，距离刚好框住四站，类似示例2 的俯视角度 |
| 旋转限制 | `OrbitControls.minPolarAngle = 0`，`maxPolarAngle = Math.PI / 2.2`，禁止钻到地形下面 |
| 缩放范围 | `minDistance = 8000`，`maxDistance = 70000`，防止缩得太近/太远 |
| 阻尼 | `enableDamping = true`，`dampingFactor = 0.06`，拖动更顺滑 |
| 自动旋转 | `autoRotate = true`，`autoRotateSpeed = 0.4`，点击/拖拽后暂停 8s |
| 重置视图 | `TerrainPanel` 保留/增加"重置视角"按钮，调用 `flyToOverview()` |

## 非目标（YAGNI）

- 不引入 Bloom/SSAO 等后处理
- 不做站点之间的连线或流域高亮
- 不做点击站点后的相机飞行动画（复用现有自转暂停逻辑）
- 不新增独立 composable 或组件文件
- 不替换 DEM/水系数据源，不做更大范围地形
