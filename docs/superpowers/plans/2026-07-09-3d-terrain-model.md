# 3D 流域地形模型 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 Python 把 DEM 高程 + OSM 水系烘焙成一个 3D 地形 GLB 模型，前端 Three.js 加载它铺满 Overview 背景（替换 Cesium），站点光柱可点击联动水文数据。

**Architecture:** Python(`numpy`+`trimesh`) 读 DEM → 600×600 网格 → 顶点着色(高程渐变+河道蓝) → 导出 `terrain.glb`+`terrain_meta.json`。前端 `TerrainModel3D.vue`(`three`) 用 GLTFLoader 加载，动态加青色站点光柱(查 meta 高度数组贴地形)，OrbitControls 旋转 + raycaster 点击联动 `rotation` store。

**Tech Stack:** Python 3.14 + numpy + pillow + trimesh；Vue3 + three(GLTFLoader/OrbitControls/raycaster)。

## Global Constraints

- 数据范围 AOI: `west=112.88, east=113.19, south=25.60, north=25.92`（聚焦郴州四站城区）
- 网格尺寸 600×600；高程夸张 10×
- 配色(写死，勿改): 地形低 `#0f2a38` → 高 `#2d5a6b`；河道顶点 `#3B82F6`；站点光柱 `#22D3EE`；背景 `#06141D`
- 四站坐标来自 `web/src/stations.js`（前后端单一数据源，勿硬编码）
- 站名/编码用真实值，与 `gateway/services/station_names.py` 一致
- Windows + Git Bash 环境，Python 脚本运行需 `PYTHONIOENCODING=utf-8`
- 前端 dev server 在 `web/` 下 `npm run dev`，端口动态（当前 5175）

## File Structure

**新建:**
- `scripts/build_terrain_model.py` — GLB 生成脚本（纯函数 + main，可单测）
- `scripts/test_build_terrain.py` — Python 单元测试（pytest）
- `web/public/models/terrain.glb` — 脚本产物（3D 模型）
- `web/public/models/terrain_meta.json` — 模型元数据（AOI 边界 + 顶点高度数组）
- `web/src/components/TerrainModel3D.vue` — Three.js 组件

**修改:**
- `web/package.json` — 加 `three` 依赖
- `web/src/pages/AppLayout.vue` — `<CesiumMap>` → `<TerrainModel3D>`
- `web/src/components/TerrainPanel.vue` — 精简控制项（移除 Cesium 专属）
- `web/src/router/index.js` — 删除 `/terrain-preview` 路由

**删除:**
- `web/src/pages/TerrainPreviewPage.vue` — Cesium 预览页，不再需要

---

### Task 1: Python — DEM 读取、裁剪 AOI、降采样

**Files:**
- Create: `scripts/build_terrain_model.py`
- Create: `scripts/test_build_terrain.py`

**Interfaces:**
- Produces: `load_dem_mosaic() -> (np.ndarray shape(7200,7200) float32, dict bounds)`；`crop_aoi(mosaic, mosaic_bounds, aoi) -> np.ndarray`；`downsample(arr, size) -> np.ndarray`

- [ ] **Step 1: 装依赖**

Run:
```bash
pip install numpy pillow trimesh pytest
```
Expected: 全部安装成功（trimesh 4.x）

- [ ] **Step 2: 写脚本骨架 + load_dem_mosaic**

Create `scripts/build_terrain_model.py`:
```python
#!/usr/bin/env python3
"""把 DEM + OSM 水系烘焙成 3D 地形 GLB 模型。"""
import json
import numpy as np
from PIL import Image
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEM_DIR = ROOT / 'scripts' / 'data' / 'geospatial' / 'dem'
WATER_GEOJSON = ROOT / 'web' / 'public' / 'geo' / 'water_system.geojson'
OUT_DIR = ROOT / 'web' / 'public' / 'models'
OUT_GLB = OUT_DIR / 'terrain.glb'
OUT_META = OUT_DIR / 'terrain_meta.json'

AOI = {'west': 112.88, 'east': 113.19, 'south': 25.60, 'north': 25.92}
GRID_SIZE = 600
EXAGGERATION = 10.0

COLOR_LOW = np.array([0x0f, 0x2a, 0x38], dtype=np.float32)
COLOR_HIGH = np.array([0x2d, 0x5a, 0x6b], dtype=np.float32)
COLOR_WATER = np.array([0x3b, 0x82, 0xf6], dtype=np.float32)

# Copernicus 瓦片 → (lat, lon) 左下角
TILES = {
    'N25_00_E112_00': (25, 112), 'N25_00_E113_00': (25, 113),
    'N26_00_E112_00': (26, 112), 'N26_00_E113_00': (26, 113),
}


def load_dem_mosaic():
    """读 4 个 1°×1° 瓦片拼成 2°×2° mosaic。
    返回 (array[7200,7200] float32, {'west','east','south','north'})。
    mosaic 行0=北(lat27), 列0=西(lon112)。
    """
    tile_h = tile_w = 3600
    mosaic = np.zeros((tile_h * 2, tile_w * 2), dtype=np.float32)
    mosaic[:] = np.nan
    for fname, (lat, lon) in TILES.items():
        path = DEM_DIR / f'{fname}.tif'
        if not path.exists():
            raise FileNotFoundError(f'缺少 DEM 瓦片: {path}')
        arr = np.array(Image.open(path), dtype=np.float32)
        # lat=26 在上(行0), lat=25 在下(行1); lon=112 在左(列0), lon=113 在右(列1)
        row = 0 if lat == 26 else 1
        col = 0 if lon == 112 else 1
        mosaic[row*tile_h:(row+1)*tile_h, col*tile_w:(col+1)*tile_w] = arr
    bounds = {'west': 112.0, 'east': 114.0, 'south': 25.0, 'north': 27.0}
    return mosaic, bounds


def crop_aoi(mosaic, mosaic_bounds, aoi):
    """从 mosaic 裁出 AOI。mosaic 行0=北。
    返回 array[H,W] float32 (AOI 的高程, 行0=北)。"""
    mb = mosaic_bounds
    h, w = mosaic.shape
    # 经度 → 列
    x0 = int((aoi['west'] - mb['west']) / (mb['east'] - mb['west']) * w)
    x1 = int((aoi['east'] - mb['west']) / (mb['east'] - mb['west']) * w)
    # 纬度 → 行 (行0=北, 即 north)
    y0 = int((mb['north'] - aoi['north']) / (mb['north'] - mb['south']) * h)
    y1 = int((mb['north'] - aoi['south']) / (mb['north'] - mb['south']) * h)
    return mosaic[y0:y1, x0:x1]


def downsample(arr, size):
    """降采样到 size×size (PIL NEAREST 保持精度)。"""
    img = Image.fromarray(arr.astype(np.float32), mode='F')
    img = img.resize((size, size), Image.NEAREST)
    return np.array(img, dtype=np.float32)
```

- [ ] **Step 3: 写失败测试**

Create `scripts/test_build_terrain.py`:
```python
import numpy as np
import pytest
from build_terrain_model import load_dem_mosaic, crop_aoi, downsample, AOI


def test_load_dem_mosaic():
    mosaic, bounds = load_dem_mosaic()
    assert mosaic.shape == (7200, 7200)
    assert bounds == {'west': 112.0, 'east': 114.0, 'south': 25.0, 'north': 27.0}
    assert np.nanmin(mosaic) > 0  # 郴州区域海拔 > 0
    assert np.nanmax(mosaic) < 9000


def test_crop_aoi_shape():
    mosaic, mb = load_dem_mosaic()
    aoi_arr = crop_aoi(mosaic, mb, AOI)
    # AOI 约 0.31°×0.32°, mosaic 2°=7200px → 约 1100×1150
    assert 900 < aoi_arr.shape[0] < 1300
    assert 900 < aoi_arr.shape[1] < 1300


def test_downsample():
    arr = np.random.rand(1100, 1150).astype(np.float32)
    out = downsample(arr, 600)
    assert out.shape == (600, 600)
```

- [ ] **Step 4: 跑测试验证失败→通过**

Run:
```bash
cd scripts && PYTHONIOENCODING=utf-8 python -m pytest test_build_terrain.py -v
```
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/build_terrain_model.py scripts/test_build_terrain.py
git commit -m "feat(terrain): DEM 读取/裁剪AOI/降采样 函数与测试"
```

---

### Task 2: Python — 河道光栅化 + 顶点着色

**Files:**
- Modify: `scripts/build_terrain_model.py`
- Modify: `scripts/test_build_terrain.py`

**Interfaces:**
- Produces: `rasterize_waterways(grid_size, aoi) -> np.ndarray bool[H,W]`；`compute_vertex_colors(heights, water_mask) -> np.ndarray uint8[H,W,3]`

- [ ] **Step 1: 加 rasterize_waterways + compute_vertex_colors 到脚本**

追加到 `scripts/build_terrain_model.py`（`downsample` 之后）:
```python
def _line_cells(x0, y0, x1, y1):
    """Bresenham, 返回 (x0,y0)->(x1,y1) 经过的网格单元列表。"""
    cells = []
    dx = abs(x1 - x0); dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    x, y = x0, y0
    while True:
        cells.append((x, y))
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy; x += sx
        if e2 < dx:
            err += dx; y += sy
    return cells


def rasterize_waterways(grid_size, aoi):
    """OSM 水系 LineString 光栅化到 grid_size×grid_size mask。
    返回 bool[H,W] (行0=北)。河道膨胀 1 邻域防止细河断线。"""
    mask = np.zeros((grid_size, grid_size), dtype=bool)
    with open(WATER_GEOJSON, encoding='utf-8') as f:
        gj = json.load(f)
    lon_span = aoi['east'] - aoi['west']
    lat_span = aoi['north'] - aoi['south']
    for feat in gj.get('features', []):
        geom = feat.get('geometry') or {}
        if geom.get('type') != 'LineString':
            continue
        coords = geom['coordinates']
        prev = None
        for lon, lat in coords:
            if not (aoi['west'] <= lon <= aoi['east'] and aoi['south'] <= lat <= aoi['north']):
                prev = None
                continue
            # 经纬度 → 网格 (行0=北)
            gx = int((lon - aoi['west']) / lon_span * (grid_size - 1))
            gy = int((aoi['north'] - lat) / lat_span * (grid_size - 1))
            if prev is not None:
                for cx, cy in _line_cells(prev[0], prev[1], gx, gy):
                    if 0 <= cx < grid_size and 0 <= cy < grid_size:
                        mask[cy, cx] = True
            prev = (gx, gy)
    # 膨胀 1 像素 (8 邻域)
    dilated = mask.copy()
    dilated[1:, :] |= mask[:-1, :]
    dilated[:-1, :] |= mask[1:, :]
    dilated[:, 1:] |= mask[:, :-1]
    dilated[:, :-1] |= mask[:, 1:]
    return dilated


def compute_vertex_colors(heights, water_mask):
    """高程渐变 + 河道蓝。heights[H,W] 米, water_mask[H,W] bool。
    返回 uint8[H,W,3] RGB。"""
    h_min = float(np.nanmin(heights))
    h_max = float(np.nanmax(heights))
    rng = max(h_max - h_min, 1.0)
    t = np.clip((heights - h_min) / rng, 0, 1)  # [H,W] 0~1
    t = t[..., None]  # [H,W,1]
    colors = COLOR_LOW * (1 - t) + COLOR_HIGH * t  # [H,W,3]
    colors[water_mask] = COLOR_WATER
    return colors.astype(np.uint8)
```

- [ ] **Step 2: 加测试**

追加到 `scripts/test_build_terrain.py`:
```python
from build_terrain_model import rasterize_waterways, compute_vertex_colors, GRID_SIZE


def test_rasterize_waterways_has_hits():
    mask = rasterize_waterways(GRID_SIZE, AOI)
    assert mask.shape == (GRID_SIZE, GRID_SIZE)
    assert mask.dtype == bool
    # 郴州城区有郴江等河道, 必须命中一些顶点
    assert mask.sum() > 50, '河道未命中任何网格, 光栅化可能出错'


def test_compute_vertex_colors():
    heights = np.array([[100, 500], [1000, 1500]], dtype=np.float32)
    water = np.array([[True, False], [False, False]])
    colors = compute_vertex_colors(heights, water)
    assert colors.shape == (2, 2, 3)
    assert colors.dtype == np.uint8
    # 河道顶点 = 蓝色
    assert tuple(colors[0, 0]) == (0x3b, 0x82, 0xf6)
    # 高程顶点在渐变范围内
    assert colors[0, 1, 0] <= 0x2d  # 低处偏暗
```

- [ ] **Step 3: 跑测试**

Run:
```bash
cd scripts && PYTHONIOENCODING=utf-8 python -m pytest test_build_terrain.py -v
```
Expected: 5 passed

- [ ] **Step 4: Commit**

```bash
git add scripts/build_terrain_model.py scripts/test_build_terrain.py
git commit -m "feat(terrain): 河道光栅化 + 顶点着色(高程渐变+河道蓝)"
```

---

### Task 3: Python — 构建 mesh + 导出 GLB + meta

**Files:**
- Modify: `scripts/build_terrain_model.py`

**Interfaces:**
- Produces: `build_mesh(heights, colors, aoi, exaggeration) -> trimesh.Trimesh`；`write_meta(path, ...)`；`main()` 产出 `terrain.glb` + `terrain_meta.json`

- [ ] **Step 1: 加 build_mesh / write_meta / main**

追加到 `scripts/build_terrain_model.py`:
```python
def build_mesh(heights, colors, aoi, exaggeration):
    """构建 trimesh。顶点 (x=经度-中心, y=纬度-中心, z=高程×夸张)。
    行0=北 → 翻转 y 使纬度增大方向为 +y。"""
    import trimesh
    H, W = heights.shape
    cx = (aoi['west'] + aoi['east']) / 2
    cy = (aoi['south'] + aoi['north']) / 2
    lon = np.linspace(aoi['west'], aoi['east'], W) - cx
    lat = np.linspace(aoi['north'], aoi['south'], H) - cy  # 行0=北(lat大), 翻转使 +y=北
    gx, gy = np.meshgrid(lon, lat)  # [H,W]
    z = np.where(np.isfinite(heights), heights, 0.0) * exaggeration
    # 轻度平滑地形 (3×3 均值) 让山势更顺
    from PIL import Image as _I
    z_img = _I.fromarray(z, mode='F').filter(_I.SMOOTH)
    z = np.array(z_img, dtype=np.float32)
    verts = np.stack([gx, gy, z], axis=-1).reshape(-1, 3).astype(np.float32)
    vert_colors = colors.reshape(-1, 3)
    # 面: 每 cell 2 三角形
    faces = []
    for r in range(H - 1):
        base = r * W
        base_next = (r + 1) * W
        c0 = np.arange(W - 1)
        v00 = base + c0
        v01 = base + c0 + 1
        v10 = base_next + c0
        v11 = base_next + c0 + 1
        # 两个三角形 (注意 y 翻转后的绕序)
        t1 = np.stack([v00, v10, v11], axis=1)
        t2 = np.stack([v00, v11, v01], axis=1)
        faces.append(t1); faces.append(t2)
    faces = np.vstack(faces).astype(np.int32)
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, vertex_colors=vert_colors, process=False)
    return mesh


def write_meta(path, aoi, grid_size, exaggeration, heights):
    """写 meta JSON。heights 顶点高度数组(未夸张, 米)供前端查站点贴地高度。"""
    meta = {
        'west': aoi['west'], 'east': aoi['east'],
        'south': aoi['south'], 'north': aoi['north'],
        'center_lon': (aoi['west'] + aoi['east']) / 2,
        'center_lat': (aoi['south'] + aoi['north']) / 2,
        'grid_size': grid_size,
        'exaggeration': exaggeration,
        'heights_meters': np.where(np.isfinite(heights), heights, 0.0).round(2).tolist(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(meta, f)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print('[1/5] 读 DEM mosaic ...')
    mosaic, mb = load_dem_mosaic()
    print('[2/5] 裁剪 AOI ...')
    aoi_arr = crop_aoi(mosaic, mb, AOI)
    heights = downsample(aoi_arr, GRID_SIZE)
    print(f'      高程 {np.nanmin(heights):.0f}~{np.nanmax(heights):.0f} m')
    print('[3/5] 光栅化水系 ...')
    water_mask = rasterize_waterways(GRID_SIZE, AOI)
    print(f'      河道顶点 {water_mask.sum()} 个')
    print('[4/5] 顶点着色 + 构建 mesh ...')
    colors = compute_vertex_colors(heights, water_mask)
    mesh = build_mesh(heights, colors, AOI, EXAGGERATION)
    mesh.export(str(OUT_GLB))
    print(f'      导出 {OUT_GLB} ({OUT_GLB.stat().st_size/1024/1024:.1f} MB)')
    print('[5/5] 写 meta ...')
    write_meta(OUT_META, AOI, GRID_SIZE, EXAGGERATION, heights)
    print(f'      {OUT_META} ({OUT_META.stat().st_size/1024/1024:.1f} MB)')
    print('✅ 完成')


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: 跑脚本生成 GLB**

Run:
```bash
cd scripts && PYTHONIOENCODING=utf-8 python build_terrain_model.py
```
Expected: 输出 `[1/5]...[5/5]`，`terrain.glb` 生成（< 30MB），`terrain_meta.json` 生成

- [ ] **Step 3: 验证 GLB 可被重新加载且含顶点色**

Run:
```bash
cd scripts && PYTHONIOENCODING=utf-8 python -c "import trimesh; m=trimesh.load('../web/public/models/terrain.glb'); print('verts', len(m.vertices), 'faces', len(m.faces), 'has_color', m.visual.kind if hasattr(m.visual,'kind') else 'n/a')"
```
Expected: `verts 360000 faces 719802 has_color vertex`

- [ ] **Step 4: Commit**

```bash
git add scripts/build_terrain_model.py web/public/models/terrain.glb web/public/models/terrain_meta.json
git commit -m "feat(terrain): 构建 mesh + 导出 GLB + meta (含顶点高度数组)"
```

---

### Task 4: 前端 — 装 three + TerrainModel3D 骨架（加载渲染）

**Files:**
- Modify: `web/package.json`
- Create: `web/src/components/TerrainModel3D.vue`

**Interfaces:**
- Produces: `<TerrainModel3D>` 组件，全屏铺满，加载 `/models/terrain.glb` 并渲染（此 task 仅静态展示，站点/交互后续 task 加）

- [ ] **Step 1: 装 three**

Run:
```bash
cd web && npm install three
```
Expected: `three` 加入 dependencies

- [ ] **Step 2: 写 TerrainModel3D.vue 骨架**

Create `web/src/components/TerrainModel3D.vue`:
```vue
<template>
  <div ref="container" class="terrain-bg"></div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

const container = ref(null)
let renderer, scene, camera, controls, model, animateId

onMounted(() => {
  const el = container.value
  const w = el.clientWidth, h = el.clientHeight

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.setSize(w, h)
  el.appendChild(renderer.domElement)

  scene = new THREE.Scene()
  scene.background = new THREE.Color('#06141D')

  camera = new THREE.PerspectiveCamera(45, w / h, 0.01, 1000)
  camera.position.set(0.15, -0.25, 0.18)

  // 暗色光照突出山势
  scene.add(new THREE.AmbientLight(0x335566, 0.7))
  const dir = new THREE.DirectionalLight(0xbbddee, 1.0)
  dir.position.set(0.3, -0.4, 0.5)
  scene.add(dir)

  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.autoRotate = true
  controls.autoRotateSpeed = 0.5

  // 模型经纬度单位是度, 数值小(~0.3), 直接用
  const loader = new GLTFLoader()
  loader.load('/models/terrain.glb',
    (gltf) => {
      model = gltf.scene
      scene.add(model)
      console.log('[Terrain3D] 模型加载成功, 顶点数:', model)
    },
    undefined,
    (err) => console.error('[Terrain3D] 模型加载失败:', err)
  )

  const animate = () => {
    animateId = requestAnimationFrame(animate)
    controls.update()
    renderer.render(scene, camera)
  }
  animate()

  window.addEventListener('resize', onResize)
})

function onResize() {
  if (!container.value || !renderer) return
  const w = container.value.clientWidth, h = container.value.clientHeight
  renderer.setSize(w, h)
  camera.aspect = w / h
  camera.updateProjectionMatrix()
}

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  if (animateId) cancelAnimationFrame(animateId)
  if (controls) controls.dispose()
  if (renderer) { renderer.dispose(); renderer.domElement.remove() }
})
</script>

<style scoped>
.terrain-bg { position: fixed; inset: 0; z-index: 0; }
</style>
```

- [ ] **Step 3: 临时挂到 AppLayout 验证渲染**

Modify `web/src/pages/AppLayout.vue`: 把 `<CesiumMap ... />` 整段替换为 `<TerrainModel3D />`，删除相关 import/props/事件绑定/状态（terrainEnabled/exaggeration/showWater/terrainReady/cesiumRef 等全部删，onMounted 里的 CSS 变量设置保留）。

临时简化版 AppLayout `<script setup>` 顶部 import:
```js
import TerrainModel3D from '../components/TerrainModel3D.vue'
// 删除: import CesiumMap / TerrainPanel
```
template 内 `<CesiumMap .../>` → `<TerrainModel3D />`，删除 `<TerrainPanel .../>`。

- [ ] **Step 4: 运行验证**

Run:
```bash
cd web && npm run dev
```
浏览器打开 dev URL（如 `https://localhost:5175/`，登录后 Overview 页）。
Expected:
- 背景显示深色 3D 地形（能看到起伏的山势，自动缓慢旋转）
- console 有 `[Terrain3D] 模型加载成功`
- 无红色报错

- [ ] **Step 5: Commit**

```bash
git add web/package.json web/package-lock.json web/src/components/TerrainModel3D.vue web/src/pages/AppLayout.vue
git commit -m "feat(terrain): Three.js 加载 GLB 地形模型骨架, 替换 CesiumMap"
```

---

### Task 5: 前端 — 站点光柱贴地形 + 名称标签

**Files:**
- Modify: `web/src/components/TerrainModel3D.vue`

**Interfaces:**
- Consumes: `STATIONS` from `../stations`；`/models/terrain_meta.json`
- Produces: 4 个青色光柱贴在地形表面 + 标签

- [ ] **Step 1: 加 meta 加载 + 站点光柱构建函数**

在 `TerrainModel3D.vue` `<script setup>` 内，`onMounted` 之前加:
```js
import { STATIONS } from '../stations'

let meta = null
const stationGroups = []  // 每站一个 Group(光柱+标签)

function lonlatToModel(lon, lat) {
  // 经纬度 → 模型坐标 (模型已减中心)
  const cx = meta.center_lon, cy = meta.center_lat
  return { x: lon - cx, y: lat - cy }
}

function heightAt(lon, lat) {
  // 查 meta 顶点高度数组 (米), 返回夸张后的模型 Z
  const { grid_size, heights_meters, exaggeration, west, east, north, south } = meta
  const gx = Math.round((lon - west) / (east - west) * (grid_size - 1))
  const gy = Math.round((north - lat) / (north - south) * (grid_size - 1))
  const i = Math.max(0, Math.min(grid_size - 1, gy))
  const j = Math.max(0, Math.min(grid_size - 1, gx))
  return heights_meters[i][j] * exaggeration
}

function makeLabelTexture(text) {
  const c = document.createElement('canvas')
  c.width = 256; c.height = 64
  const ctx = c.getContext('2d')
  ctx.font = 'bold 30px "SF Mono", Consolas, monospace'
  ctx.fillStyle = '#E0FBFC'
  ctx.strokeStyle = '#020D14'; ctx.lineWidth = 5
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
  ctx.strokeText(text, 128, 32); ctx.fillText(text, 128, 32)
  const tex = new THREE.CanvasTexture(c)
  tex.minFilter = THREE.LinearFilter
  return tex
}

function buildStations() {
  STATIONS.forEach((s) => {
    const { x, y } = lonlatToModel(s.lon, s.lat)
    const z = heightAt(s.lon, s.lat)
    const g = new THREE.Group()
    g.position.set(x, y, z)
    g.userData = { code: s.code }

    // 青色光柱
    const pillarH = 0.012
    const pillar = new THREE.Mesh(
      new THREE.CylinderGeometry(0.0008, 0.0008, pillarH, 8),
      new THREE.MeshBasicMaterial({ color: 0x22D3EE, transparent: true, opacity: 0.85 })
    )
    pillar.position.set(0, 0, pillarH / 2)
    // Cylinder 默认沿 Y; 我们要沿 Z(上), 旋转
    pillar.rotation.x = Math.PI / 2
    g.add(pillar)

    // 顶部光点
    const top = new THREE.Mesh(
      new THREE.SphereGeometry(0.002, 12, 12),
      new THREE.MeshBasicMaterial({ color: 0x67E8F9 })
    )
    top.position.set(0, 0, pillarH)
    g.add(top)

    // 标签 sprite
    const label = new THREE.Sprite(new THREE.SpriteMaterial({ map: makeLabelTexture(s.name.split('-').pop()) }))
    label.position.set(0, 0, pillarH + 0.006)
    label.scale.set(0.03, 0.0075, 1)
    g.add(label)

    scene.add(g)
    stationGroups.push(g)
  })
}
```

- [ ] **Step 2: 在模型加载回调里加 meta 加载 + 站点构建**

把 `onMounted` 里的 `loader.load` 回调改为:
```js
  loader.load('/models/terrain.glb',
    async (gltf) => {
      model = gltf.scene
      scene.add(model)
      // 加载 meta 后建站点
      const resp = await fetch('/models/terrain_meta.json')
      meta = await resp.json()
      buildStations()
      console.log('[Terrain3D] 模型+站点就绪, 站点', stationGroups.length)
    },
    undefined,
    (err) => console.error('[Terrain3D] 模型加载失败:', err)
  )
```

- [ ] **Step 3: 运行验证**

刷新 Overview。
Expected:
- 4 个青色光柱立在郴州、坳上、鸡嘴桥下游、燕泉河所在的地形位置
- 光柱顶部有光点 + 名称标签
- 光柱底部贴在山势表面（不是悬空或穿地）

- [ ] **Step 4: Commit**

```bash
git add web/src/components/TerrainModel3D.vue
git commit -m "feat(terrain): 站点青色光柱贴地形 + 名称标签"
```

---

### Task 6: 前端 — 点击站点联动水文数据 + 交互收尾

**Files:**
- Modify: `web/src/components/TerrainModel3D.vue`

**Interfaces:**
- Consumes: `useRotationStore` from `../store/rotation`（`pinStation(code)` 联动 StationDrawer）

- [ ] **Step 1: 加 raycaster 点击 + 联动 store**

在 `<script setup>` 顶部 import:
```js
import { useRotationStore } from '../store/rotation'
const rotation = useRotationStore()
```

在 `onMounted` 内 `animate()` 之前加:
```js
  const raycaster = new THREE.Raycaster()
  const pointer = new THREE.Vector2()
  let resumeTimer = null

  function onClick(e) {
    const rect = renderer.domElement.getBoundingClientRect()
    pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
    pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1
    raycaster.setFromCamera(pointer, camera)
    // 只检测站点光柱(柱+球), 不打地形
    const targets = []
    stationGroups.forEach(g => g.children.forEach(c => targets.push(c)))
    const hits = raycaster.intersectObjects(targets, false)
    if (hits.length > 0) {
      // 向上找到带 userData.code 的 Group
      let obj = hits[0].object
      while (obj && !obj.userData?.code) obj = obj.parent
      if (obj?.userData?.code) {
        rotation.pinStation(obj.userData.code)
        controls.autoRotate = false
        clearTimeout(resumeTimer)
        resumeTimer = setTimeout(() => { controls.autoRotate = true }, 8000)
      }
    }
  }
  renderer.domElement.addEventListener('click', onClick)

  // 拖拽时暂停自转
  controls.addEventListener('start', () => {
    controls.autoRotate = false
    clearTimeout(resumeTimer)
  })
  controls.addEventListener('end', () => {
    resumeTimer = setTimeout(() => { controls.autoRotate = true }, 3000)
  })
```

在 `onUnmounted` 里加（清理用，找到现有 cleanup 块补充）:
```js
  if (renderer?.domElement) renderer.domElement.removeEventListener('click', onClick)
```
> 注: `onClick` 需提升到 onMounted 作用域外或在 onUnmounted 可见；实现时把 `onClick` 定义在 onMounted 内但用一个外层 `let clickHandler` 引用以便卸载。

- [ ] **Step 2: 运行验证**

刷新 Overview。
Expected:
- 点击任一站点光柱 → 右侧/抽屉弹出该站水文数据（复用现有 StationDrawer）
- 自转暂停，~8 秒后恢复
- 拖拽旋转正常，松手后 ~3 秒恢复自转

- [ ] **Step 3: Commit**

```bash
git add web/src/components/TerrainModel3D.vue
git commit -m "feat(terrain): 点击站点联动水文抽屉 + 自转交互"
```

---

### Task 7: 集成收尾 — TerrainPanel 精简 + 删预览页 + 文档

**Files:**
- Modify: `web/src/components/TerrainPanel.vue`
- Modify: `web/src/router/index.js`
- Delete: `web/src/pages/TerrainPreviewPage.vue`

**Interfaces:**
- Produces: Overview 干净集成 3D 模型，无 Cesium 残留引用，无废弃预览页

- [ ] **Step 1: 精简 TerrainPanel（只留夸张滑块 + 站点快飞）**

Rewrite `web/src/components/TerrainPanel.vue` 的 `<template>` 和 `<script>`（保留 `<style>`）。新模板只保留: 标题 + 地形夸张滑块 + 站点快飞芯片 + 状态。props 精简为 `terrainExaggeration`，emit `update:terrainExaggeration` / `flyTo` / `flyToOverview`。

新 `<script setup>`:
```js
import { ref } from 'vue'
import { STATIONS } from '../stations'
defineProps({ terrainExaggeration: { type: Number, default: 10 } })
defineEmits(['update:terrainExaggeration', 'flyTo', 'flyToOverview'])
const collapsed = ref(false)
const stations = STATIONS
```

- [ ] **Step 2: AppLayout 接 TerrainPanel 夸张控制**

Modify `web/src/pages/AppLayout.vue`: 重新引入 `TerrainPanel`，状态精简为 `const exaggeration = ref(10)`，watch 它调 `terrainRef.value?.setExaggeration(v)`。
给 `TerrainModel3D.vue` 加 `defineExpose({ setExaggeration })` 方法（内部调 `model.scale.z = v/10` 或重建；简单方案: 整体 `model.scale.set(1,1,v/10)` 不对——正确做法见下）。

> **正确夸张调整**: 模型 Z 已含 10×。改夸张最简单是 `model.scale.z = newExag / 10`。在 TerrainModel3D 加:
```js
function setExaggeration(v) {
  if (model) model.scale.z = v / 10
}
defineExpose({ setExaggeration, flyToStation, flyToOverview })
```
（`flyToStation`/`flyToOverview` 用 `controls.target` + `camera.position` 动画，可后续完善；此 task 先暴露空壳不报错）

- [ ] **Step 3: 删预览页 + 路由**

Delete `web/src/pages/TerrainPreviewPage.vue`。
Modify `web/src/router/index.js`: 删除 `/terrain-preview` 路由行 + beforeEach 里的 `TerrainPreview` 放行。

- [ ] **Step 4: 端到端验证**

Run:
```bash
cd web && npm run dev
```
Expected:
- Overview 背景 3D 地形 + 4 青光柱 + 蓝河网
- 右上 TerrainPanel 可调夸张滑块（地形随之变高/变矮）
- 站点快飞芯片点击不报错（flyTo 空壳）
- 访问 `/terrain-preview` → 重定向到 `/`（不再 404 或白屏）
- console 无 Cesium / Vue 报错

- [ ] **Step 5: Commit**

```bash
git add web/src/components/TerrainPanel.vue web/src/components/TerrainModel3D.vue web/src/pages/AppLayout.vue web/src/router/index.js
git rm web/src/pages/TerrainPreviewPage.vue
git commit -m "feat(terrain): 集成收尾 - TerrainPanel夸张控制 + 删预览页"
```

---

## 可选清理（本计划之外，单独做）

删 Cesium 残留以减小体积:
- `rm -rf web/public/terrain` (657MB heightmap 瓦片)
- `rm web/src/components/CesiumMap.vue web/src/utils/localTerrainProvider.js`
- `package.json` 移除 `cesium`、`vite-plugin-cesium`；`vite.config.js` 移除 cesium 插件
- `npm install` 重装

---

## Self-Review 记录

- **Spec 覆盖**: GLB生成(T1-3)✓ 前端加载(T4)✓ 站点贴地形(T5)✓ 点击联动(T6)✓ 铺满背景替换Cesium(T4/7)✓ 蓝色水系烘焙(T2)✓ 驾驶舱配色(全局约束)✓
- **占位符**: flyToStation/flyToOverview 在 T7 标注为"空壳不报错"，后续可增强——已显式说明非占位
- **类型一致**: `build_mesh`/`write_meta`/`lonlatToModel`/`heightAt` 命名跨 task 一致；meta 字段(`center_lon/lat`, `heights_meters`, `exaggeration`, `west/east/north/south`, `grid_size`)在 T3 写、T5 读，一致
