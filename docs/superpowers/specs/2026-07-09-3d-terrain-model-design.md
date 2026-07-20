# 3D 流域地形模型设计（脱离 Cesium）

**日期**: 2026-07-09
**状态**: 设计待审

## 背景与动机

原方案用 Cesium globe 加载 DEM 地形，遇到一系列 Cesium 1.142 集成问题（terrain provider 接口、RequestScheduler、WebGL 兼容）。

用户明确新方向：**基于 DEM 数据生成一个独立的 3D 模型文件，前端像加载"3D 机器人"那样直接加载**，水系烘焙进模型，不用任何地图引擎（Cesium）。

## 决策汇总

| 维度 | 决策 |
|------|------|
| 加载与交互 | Three.js 手写；GLB 只含地形+水系，站点由前端动态加、可点击联动水文数据 |
| 地形范围 | 聚焦四站城区 ~0.3°×0.3°（112.88–113.19°E × 25.60–25.92°N） |
| 视觉风格 | 驾驶舱暗色科技：深色地形 + 高程渐变（低暗→高亮） |
| 水系呈现 | 蓝色 `#3B82F6` 顶点着色，烘焙进 GLB |
| 集成位置 | 铺满 Overview 背景，替换 CesiumMap |

## 配色规范

| 元素 | 颜色 | 说明 |
|------|------|------|
| 地形低处 | `#0f2a38` | 深青蓝，谷地/水体附近 |
| 地形高处 | `#2d5a6b` | 亮青蓝，山脊 |
| 河道（顶点） | `#3B82F6` | 亮蓝，OSM 水系命中的顶点 |
| 站点光柱 | `#22D3EE` | 青色，监测点高亮 |
| 背景 | `#06141D` | 驾驶舱深色底 |

> 蓝色水系（直觉）与青色站点（科技高亮）职责分明，不冲突。

## 整体架构

```
[Python 构建脚本]                     [前端 Vue + Three.js]
scripts/build_terrain_model.py        web/src/components/TerrainModel3D.vue
  ├ 读 DEM GeoTIFF (4瓦片)             ├ GLTFLoader 加载 /models/terrain.glb
  ├ 裁剪 AOI + 降采样 600×600          ├ 暗色光照(环境光+方向光)
  ├ 高程夸张 10×                        ├ 动态加青色站点光柱(贴地形)
  ├ 水系 GeoJSON→标记河道顶点           ├ OrbitControls(旋转/缩放/平移)
  ├ 顶点着色(高程渐变+河道蓝)           ├ 自动缓慢旋转("机器人展示"感)
  └ trimesh 导出 GLB                    └ raycaster 点击站点→联动 rotation store
        ↓                                       ↑
  web/public/models/terrain.glb  ──────────────┘ 静态资源
```

## 一、GLB 模型生成（Python 端）

**脚本**: `scripts/build_terrain_model.py`
**输出**: `web/public/models/terrain.glb`
**依赖**: `numpy`, `trimesh`, `pillow`, `tifffile`（PIL 读 GeoTIFF，已验证可用）

### 算法步骤

1. **读 DEM**：用 PIL 读 4 个 Copernicus 瓦片（`N25_E112/113`, `N26_E112/113`），拼成 2°×2° mosaic（同 `process_dem.py` 已验证的方法）

2. **裁剪 AOI**：从 mosaic 切出 `112.88–113.19°E × 25.60–25.92°N`（约 0.31°×0.32°）

3. **降采样**：用 PIL `resize` 到 **600×600**（原始约 1100×1100，降一半）。记录 AOI 的经纬度边界 → 模型 XY 映射

4. **高程夸张**：每个顶点 Z = `高程 × 10`（米）。郴州海拔 100–1500m，夸张后 1000–15000，相对 33km 水平范围可见起伏

5. **河道标记**：
   - 读 `web/public/geo/water_system.geojson`（1809 要素）
   - 裁剪到 AOI 范围内的水系
   - 对每条 LineString，按其经纬度序列在 600×600 网格上"光栅化"（Bresenham/扫描），标记命中的网格单元
   - 这些单元对应的顶点 → 染河道蓝

6. **顶点着色**：
   - 地形顶点：按归一化高程在 `#0f2a38`(低) → `#2d5a6b`(高) 插值
   - 河道顶点：覆盖为 `#3B82F6`
   - 河道靠蓝色辨识即可，**不做 Z 下凹**（保持网格简单，避免河道两侧三角面撕裂）

7. **构建网格**：
   - 顶点：`(x=经度, y=纬度, z=高程×夸张)`，居中到原点（减去 AOI 中心经纬度）
   - 面：每个 grid cell 两个三角形
   - `trimesh.Trimesh(vertices, faces, vertex_colors=colors)`
   - 导出 `.glb`：`mesh.export('terrain.glb')`（trimesh 自动包含 COLOR_0 attribute）

8. **附元数据**：导出 `web/public/models/terrain_meta.json`，含：AOI 边界（west/east/south/north）、AOI 中心经纬度、网格尺寸（600×600）、夸张倍数、**网格顶点高度数组**（600×600 的 Float32，前端用它查站点处地形高度以贴光柱）

### 关键风险与对策
- **trimesh 导出顶点色**：trimesh 支持 `vertex_colors`，导出 glb 时生成 `COLOR_0`。若实测丢失，回退用 `pygltflib` 手动构建
- **河道光栅化精度**：600×600 网格上细小河道可能只命中 1–2 个顶点，线条不连续。对策：光栅化时给河道加 1–2 像素膨胀（顶点球邻域染色）

## 二、前端 Three.js 模块

**组件**: `web/src/components/TerrainModel3D.vue`
**依赖**: `three`（需 `npm install three`）

### 职责
- 全屏铺满（`position: fixed; inset: 0; z-index: 0`，同原 CesiumMap）
- 加载 `terrain.glb` + `terrain_meta.json`
- 动态渲染 4 个站点（青色光柱 + 标签）
- 交互：旋转/缩放/点击站点
- 暴露方法：`flyToStation(code)`、`flyToOverview()`

### 实现要点
- `Scene` + `PerspectiveCamera` + `WebGLRenderer`（alpha 背景，让 CSS 深色透出）
- 光照：`AmbientLight`(0x335566, 0.6) + `DirectionalLight`(0xaaccdd, 0.8，斜上方)，突出山势阴影
- `GLTFLoader.load('/models/terrain.glb')` → 加到 scene
- **站点贴地形**：读 `terrain_meta.json` 得 AOI 边界、网格尺寸、夸张、顶点高度数组。站点经纬度 → 模型 XY（减 AOI 中心，按 AOI 跨度映射到网格）。地形高度：站点经纬度 → 网格行列索引 → 查顶点高度数组取 Z（直接数组查，比 raycaster 快且准）。光柱从该 Z 向上延伸
- **站点光柱**：`CylinderGeometry`(细高) + 发光材质（`MeshBasicMaterial` 青色 + 顶部 `Sprite` 光点）+ Canvas 文字标签（`CanvasTexture` 贴 `Sprite`）
- **交互**：`OrbitControls`（damping 开启）；点击 → `raycaster` 先打站点光柱（命中则联动），否则不打地形
- **联动水文数据**：命中站点 → 调 `rotation.pinStation(code)`（复用现有 store），触发 `StationDrawer` 水位/流量面板
- **自动旋转**：`controls.autoRotate = true; autoRotateSpeed = 0.5`，点站点或拖拽时暂停 3 秒

### 边界
- glb 加载失败 → 显示深色背景 + 错误提示（不白屏）
- WebGL 不支持 → 降级提示

## 三、集成

### 改动
- `web/src/pages/AppLayout.vue`：`<CesiumMap>` → `<TerrainModel3D>`
- `TerrainPanel.vue`：保留，控制项改为"高程夸张滑块 + 水系(其实已烘焙，此开关隐藏) + 站点快飞"（移除 terrain on/off、等高线等 Cesium 专属项）
- `package.json`：加 `"three": "^0.180.0"`
- `web/public/models/`：新建目录，放 glb + meta

### 清理（可选，后续做）
- 删 `web/src/components/CesiumMap.vue`
- 删 `web/src/utils/localTerrainProvider.js`
- 删 `web/public/terrain/`（657MB heightmap 瓦片，不再需要）
- 从 `package.json` 移除 `cesium` + `vite-plugin-cesium`（清理依赖）
- 移除 `vite.config.js` 的 cesium 插件

> 清理列为后续可选步骤，本设计阶段不动，避免一次性改动过大。

### 路由
- 删除 `/terrain-preview` 路由和 `TerrainPreviewPage.vue`（Overview `/` 即 3D 展示，无需独立预览页）

## 文件清单

**新建**:
- `scripts/build_terrain_model.py` — GLB 生成脚本
- `web/public/models/terrain.glb` — 生成的 3D 模型（脚本产物）
- `web/public/models/terrain_meta.json` — 模型元数据
- `web/src/components/TerrainModel3D.vue` — Three.js 组件

**修改**:
- `web/package.json` — 加 three 依赖
- `web/src/pages/AppLayout.vue` — CesiumMap → TerrainModel3D
- `web/src/components/TerrainPanel.vue` — 精简控制项

**文档**:
- 本文件 `docs/superpowers/specs/2026-07-09-3d-terrain-model-design.md`

## 验收标准

1. 运行 `python scripts/build_terrain_model.py` 生成 `terrain.glb`（< 20MB）+ meta
2. 前端 Overview 背景显示 3D 地形：能看到四站周边山势起伏 + 蓝色河道网络 + 4 个青色站点光柱
3. 鼠标可旋转/缩放；点击站点光柱弹出该站水文数据抽屉
4. 暗色驾驶舱风格，与现有玻璃面板协调
5. 不依赖 Cesium（cesium 相关代码可独立删除而不报错）

## 非目标（YAGNI）

- 不做地形纹理贴图（卫星图/街道图）——用户明确不要地图
- 不做等高线
- 不做水流动画（水系烘焙为静态蓝色顶点）
- 不做多 LOD（600×600 单一网格够用）
- 不做时间/日照变化（静态光照）
