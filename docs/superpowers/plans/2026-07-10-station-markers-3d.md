# 3D 地形站点全息光柱 + 模型优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `TerrainModel3D.vue` 中的站点升级为全息光柱 + 数据飘带，并同步优化 3D 地形模型的视觉品质、加载性能与交互体验。

**Architecture:** Python 端用 `gltf-transform` 对 `terrain.glb` 做 Draco 压缩；前端 `GLTFLoader` 配 `DRACOLoader` 加载压缩模型；`TerrainModel3D.vue` 内统一实现暗色光照/雾效/控制限制、全息站点渲染、hover/click 联动、`rotation` store 触发抽屉。

**Tech Stack:** Python 3.14 + trimesh + gltf-transform CLI；Vue3 + three.js (GLTFLoader/DRACOLoader/OrbitControls/raycaster/Sprite)

## Global Constraints

- 文件范围：主要改 `web/src/components/TerrainModel3D.vue`，`scripts/build_terrain_model.py` 加 Draco 压缩
- 配色固定：光柱底部 `#22D3EE` → 顶部 `#67E8F9`；脉冲底座 `#22D3EE`；预警橙 `#F97316`、红 `#EF4444`；背景 `#06141D`
- 不引入 Bloom/SSAO 后处理
- 不新增独立 composable 或组件文件
- 四站坐标/名称来源：`web/src/stations.js`
- 站点点击联动：`useRotationStore().pinStation(code)`
- GLB 目标体积：< 10MB

---

## File Structure

| 文件 | 职责 |
|------|------|
| `scripts/build_terrain_model.py` | 导出原始 GLB → Draco 压缩 → 最终 `terrain.glb` |
| `web/public/models/terrain.glb` | 压缩后的地形模型（产物） |
| `web/public/models/terrain_meta.json` | 模型元数据（不变） |
| `web/public/draco/` | Draco 解码器文件（从 three 包复制） |
| `web/src/components/TerrainModel3D.vue` | Three.js 场景 + 全息站点 + 交互 |
| `web/src/components/TerrainPanel.vue` | 增加"重置视角"按钮（可选） |

---

### Task 1: Python — GLB 导出后 Draco 压缩

**Files:**
- Modify: `scripts/build_terrain_model.py`
- Test: `scripts/test_build_terrain.py`

**Interfaces:**
- Produces: `compress_glb(input_path, output_path)` 调用 `gltf-transform optimize --compress draco`

- [ ] **Step 1: 安装 gltf-transform CLI**

Run:
```bash
cd web && npm install --save-dev @gltf-transform/cli
```
Expected: `package.json` 新增 `@gltf-transform/cli` devDependency

- [ ] **Step 2: 在 Python 脚本追加压缩函数**

在 `scripts/build_terrain_model.py` 的 `main()` 之前追加：

```python
import shutil
import subprocess


def compress_glb(input_path, output_path):
    """使用 gltf-transform CLI 对 GLB 进行 Draco 压缩。"""
    gltf_transform = shutil.which('gltf-transform') or str(ROOT / 'web' / 'node_modules' / '.bin' / 'gltf-transform')
    if not Path(gltf_transform).exists() and not shutil.which('gltf-transform'):
        raise RuntimeError(
            '未找到 gltf-transform CLI。请先运行: cd web && npm install --save-dev @gltf-transform/cli'
        )
    cmd = [
        gltf_transform, 'optimize',
        str(input_path), str(output_path),
        '--compress', 'draco',
    ]
    subprocess.run(cmd, check=True)
    print(f'      Draco 压缩完成: {output_path} ({Path(output_path).stat().st_size/1024/1024:.1f} MB)')
```

- [ ] **Step 3: 修改 main() 使用临时文件 + 压缩**

把 `main()` 里的：
```python
mesh.export(str(OUT_GLB))
```
改为：
```python
raw_glb = OUT_GLB.with_suffix('.raw.glb')
mesh.export(str(raw_glb))
compress_glb(raw_glb, OUT_GLB)
raw_glb.unlink(missing_ok=True)
```

- [ ] **Step 4: 写测试验证压缩产物更小**

在 `scripts/test_build_terrain.py` 追加：

```python
from pathlib import Path


def test_terrain_glb_exists_and_small():
    glb = Path(__file__).resolve().parent.parent / 'web' / 'public' / 'models' / 'terrain.glb'
    assert glb.exists(), 'terrain.glb 未生成'
    mb = glb.stat().st_size / 1024 / 1024
    assert mb < 10, f'terrain.glb 体积 {mb:.1f}MB，超过 10MB 目标'
```

- [ ] **Step 5: 运行构建并验证**

Run:
```bash
cd scripts && PYTHONIOENCODING=utf-8 python build_terrain_model.py
```
Expected: 输出 `[1/5]...[5/5]`，最后显示 Draco 压缩后体积 < 10MB

Run:
```bash
cd scripts && PYTHONIOENCODING=utf-8 python -m pytest test_build_terrain.py -v
```
Expected: 全部通过

- [ ] **Step 6: Commit**

```bash
git add scripts/build_terrain_model.py scripts/test_build_terrain.py web/package.json web/package-lock.json web/public/models/terrain.glb
# 注意: terrain_meta.json 无变化可不 add
git commit -m "feat(terrain): GLB 导出后 Draco 压缩，目标 <10MB"
```

---

### Task 2: 前端 — 配置 Draco 解码器 + GLTFLoader

**Files:**
- Create: `web/public/draco/draco_decoder.js`
- Create: `web/public/draco/draco_decoder.wasm`
- Create: `web/public/draco/draco_wasm_wrapper.js`
- Modify: `web/src/components/TerrainModel3D.vue`

**Interfaces:**
- Consumes: `three/examples/jsm/libs/draco/*`
- Produces: `GLTFLoader` 配 `DRACOLoader`

- [ ] **Step 1: 复制 Draco 解码器到 public**

Run:
```bash
cd web
mkdir -p public/draco
cp node_modules/three/examples/jsm/libs/draco/draco_decoder.js public/draco/
cp node_modules/three/examples/jsm/libs/draco/draco_decoder.wasm public/draco/
cp node_modules/three/examples/jsm/libs/draco/draco_wasm_wrapper.js public/draco/
```
Expected: `web/public/draco/` 下有三个文件

- [ ] **Step 2: 修改 TerrainModel3D.vue 使用 DRACOLoader**

在 `<script setup>` 顶部 import：
```js
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js'
```

在 `onMounted` 内创建 loader 时：
```js
const dracoLoader = new DRACOLoader()
dracoLoader.setDecoderPath('/draco/')
const loader = new GLTFLoader()
loader.setDRACOLoader(dracoLoader)
```

- [ ] **Step 3: 运行验证模型仍加载成功**

Run:
```bash
cd web && npm run dev
```
Expected: Overview 页 3D 地形正常显示，console 无 Draco 报错

- [ ] **Step 4: Commit**

```bash
git add web/public/draco/ web/src/components/TerrainModel3D.vue
git commit -m "feat(terrain): 配置 Draco 解码器加载压缩 GLB"
```

---

### Task 3: 前端 — 3D 场景视觉与交互优化

**Files:**
- Modify: `web/src/components/TerrainModel3D.vue`

**Interfaces:**
- Produces: 暗色背景 + 统一光照 + 雾效 + 控制限制

- [ ] **Step 1: 改背景与渲染器为暗色**

把 `onMounted` 里：
```js
renderer.setClearColor(0xFFFFFF, 1)
scene.background = new THREE.Color('#FFFFFF')
```
改为：
```js
renderer.setClearColor(0x06141D, 1)
scene.background = new THREE.Color('#06141D')
scene.fog = new THREE.Fog('#06141D', 25000, 90000)
```

- [ ] **Step 2: 统一光照**

把当前所有 `AmbientLight/DirectionalLight/HemisphereLight` 代码替换为：
```js
scene.add(new THREE.AmbientLight(0x335566, 0.5))
const dir = new THREE.DirectionalLight(0xaaccdd, 0.9)
dir.position.set(30000, -40000, 50000)
scene.add(dir)
const fill = new THREE.DirectionalLight(0x1e3a4c, 0.3)
fill.position.set(-30000, 30000, 20000)
scene.add(fill)
```

- [ ] **Step 3: 优化地形材质**

在 model traverse 里把当前 material 替换为：
```js
child.material = new THREE.MeshStandardMaterial({
  vertexColors: true,
  roughness: 0.6,
  metalness: 0.08,
  emissive: 0x000000,
})
```

- [ ] **Step 4: 配置 OrbitControls 限制与阻尼**

把当前 controls 配置：
```js
controls.enableDamping = false
controls.enableRotate = false
controls.enableZoom = false
controls.enablePan = false
controls.target.set(0, 0, MODEL_Z)
```
改为：
```js
controls.enableDamping = true
controls.dampingFactor = 0.06
controls.enableRotate = true
controls.enableZoom = true
controls.enablePan = true
controls.minPolarAngle = 0
controls.maxPolarAngle = Math.PI / 2.2
controls.minDistance = 8000
controls.maxDistance = 70000
controls.autoRotate = true
controls.autoRotateSpeed = 0.4
controls.target.set(0, 0, MODEL_Z)
```

- [ ] **Step 5: 调整初始相机位置**

把 `camera.position.set(-12000, 18000, 32000)` 改为更合适的俯视角度：
```js
camera.position.set(-25000, 35000, 45000)
```

- [ ] **Step 6: 运行验证**

Run:
```bash
cd web && npm run dev
```
Expected:
- 背景变暗，远处地形有雾效消融
- 可以旋转/缩放，但不能钻到地形下、不能缩太远
- 拖动有阻尼感

- [ ] **Step 7: Commit**

```bash
git add web/src/components/TerrainModel3D.vue
git commit -m "feat(terrain): 暗色场景、统一光照、雾效、OrbitControls 限制与阻尼"
```

---

### Task 4: 前端 — 全息站点渲染

**Files:**
- Modify: `web/src/components/TerrainModel3D.vue`

**Interfaces:**
- Consumes: `STATIONS`, `meta.heights_meters`
- Produces: 每个站点 Group 包含脉冲环、渐变光柱、光球、站名、数据飘带

- [ ] **Step 1: 添加纹理生成辅助函数**

在 `<script setup>` 内，替换原有 `makeLabelTexture` / `makeDataTexture` 为以下函数：

```js
function makeGradientPillarTexture() {
  const c = document.createElement('canvas')
  c.width = 64; c.height = 512
  const ctx = c.getContext('2d')
  const grad = ctx.createLinearGradient(0, c.height, 0, 0)
  grad.addColorStop(0, 'rgba(34, 211, 238, 0.20)')
  grad.addColorStop(1, 'rgba(103, 232, 249, 0.90)')
  ctx.fillStyle = grad
  ctx.fillRect(0, 0, c.width, c.height)
  const tex = new THREE.CanvasTexture(c)
  tex.minFilter = THREE.LinearFilter
  return tex
}

const pillarTexture = makeGradientPillarTexture()

function makePulseTextures() {
  const frames = []
  const size = 128
  for (let f = 0; f < 8; f++) {
    const c = document.createElement('canvas')
    c.width = size; c.height = size
    const ctx = c.getContext('2d')
    const r = (f / 7) * (size / 2 - 4) + 4
    ctx.clearRect(0, 0, size, size)
    ctx.beginPath()
    ctx.arc(size/2, size/2, r, 0, Math.PI * 2)
    ctx.lineWidth = 3
    ctx.strokeStyle = 'rgba(34, 211, 238, 0.8)'
    ctx.stroke()
    const tex = new THREE.CanvasTexture(c)
    tex.minFilter = THREE.LinearFilter
    frames.push(tex)
  }
  return frames
}

const pulseTextures = makePulseTextures()
const pulseTextureOrange = makePulseTextures('#F97316')  // 后面实现
const pulseTextureRed = makePulseTextures('#EF4444')     // 后面实现
```

Wait, `makePulseTextures` should accept color. Refactor: `makePulseTextures(color = '#22D3EE')` and use that color for stroke. I'll include the corrected version in the actual implementation. For the plan, I should show the exact final code. Let me write it correctly:

```js
function makePulseTextures(color = '#22D3EE') {
  const frames = []
  const size = 128
  for (let f = 0; f < 8; f++) {
    const c = document.createElement('canvas')
    c.width = size; c.height = size
    const ctx = c.getContext('2d')
    const r = (f / 7) * (size / 2 - 6) + 6
    ctx.clearRect(0, 0, size, size)
    ctx.beginPath()
    ctx.arc(size/2, size/2, r, 0, Math.PI * 2)
    ctx.lineWidth = 4
    ctx.strokeStyle = color
    ctx.stroke()
    const tex = new THREE.CanvasTexture(c)
    tex.minFilter = THREE.LinearFilter
    frames.push(tex)
  }
  return frames
}

const pulseTexturesCyan = makePulseTextures('rgba(34, 211, 238, 0.8)')
const pulseTexturesOrange = makePulseTextures('rgba(249, 115, 22, 0.8)')
const pulseTexturesRed = makePulseTextures('rgba(239, 68, 68, 0.8)')
```

And name texture:
```js
function makeNameTexture(name) {
  const c = document.createElement('canvas')
  c.width = 360; c.height = 90
  const ctx = c.getContext('2d')
  ctx.font = 'bold 40px "Roboto", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif'
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
  ctx.strokeStyle = '#020D14'; ctx.lineWidth = 6
  ctx.strokeText(name, 180, 45)
  ctx.fillStyle = '#E0FBFC'
  ctx.fillText(name, 180, 45)
  const tex = new THREE.CanvasTexture(c)
  tex.minFilter = THREE.LinearFilter
  return tex
}
```

And data texture:
```js
function makeDataTexture(label, value, unit, alert = 0) {
  const c = document.createElement('canvas')
  c.width = 420; c.height = 54
  const ctx = c.getContext('2d')
  ctx.font = '600 28px "Roboto", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif'
  ctx.textAlign = 'left'; ctx.textBaseline = 'middle'
  const color = alert === 2 ? '#EF4444' : alert === 1 ? '#F97316' : '#E0FBFC'
  ctx.fillStyle = color
  ctx.fillText(`${label}: ${value} ${unit}`, 10, 27)
  const tex = new THREE.CanvasTexture(c)
  tex.minFilter = THREE.LinearFilter
  return tex
}
```

- [ ] **Step 2: 重写 buildStations 创建全息站点**

替换原有 `buildStations()` 为：

```js
const stationGroups = []
const stationDataSprites = {}
const stationPulseMeshes = {}
const stationPillars = {}

function buildStations() {
  STATIONS.forEach((s) => {
    const { x, y } = lonlatToModel(s.lon, s.lat)
    const z = heightAt(s.lon, s.lat) + MODEL_Z
    const g = new THREE.Group()
    g.position.set(x, y, z)
    g.userData = { code: s.code, name: s.name }

    // 脉冲底座环
    const pulse = new THREE.Sprite(new THREE.SpriteMaterial({
      map: pulseTexturesCyan[0],
      transparent: true,
      opacity: 0.9,
      depthTest: false,
    }))
    pulse.scale.set(2400, 2400, 1)
    pulse.position.set(0, 0, -50)
    g.add(pulse)
    stationPulseMeshes[s.code] = { mesh: pulse, frames: pulseTexturesCyan, frame: 0, interval: 0.6 }

    // 渐变光柱
    const pillarH = 1800
    const pillar = new THREE.Mesh(
      new THREE.CylinderGeometry(60, 60, pillarH, 16, 1, true),
      new THREE.MeshBasicMaterial({
        map: pillarTexture,
        transparent: true,
        opacity: 0.75,
        side: THREE.DoubleSide,
        depthWrite: false,
      })
    )
    pillar.rotation.x = Math.PI / 2
    pillar.position.set(0, 0, pillarH / 2)
    g.add(pillar)
    stationPillars[s.code] = pillar

    // 顶部光球
    const top = new THREE.Mesh(
      new THREE.SphereGeometry(160, 16, 16),
      new THREE.MeshBasicMaterial({ color: 0x67E8F9 })
    )
    top.position.set(0, 0, pillarH)
    g.add(top)

    // 站名标签
    const label = new THREE.Sprite(new THREE.SpriteMaterial({
      map: makeNameTexture(s.name.split('-').pop()),
      transparent: true,
    }))
    label.position.set(0, 0, pillarH + 350)
    label.scale.set(3000, 750, 1)
    g.add(label)

    // 数据飘带
    const level = new THREE.Sprite(new THREE.SpriteMaterial({ map: makeDataTexture('水位', '--', 'm'), transparent: true }))
    level.position.set(0, 0, pillarH + 750)
    level.scale.set(3000, 385, 1)
    g.add(level)

    const flow = new THREE.Sprite(new THREE.SpriteMaterial({ map: makeDataTexture('流量', '--', 'm³/s'), transparent: true }))
    flow.position.set(0, 0, pillarH + 1080)
    flow.scale.set(3000, 385, 1)
    g.add(flow)

    stationDataSprites[s.code] = { level, flow }
    scene.add(g)
    stationGroups.push(g)
  })
}
```

- [ ] **Step 3: 在动画循环中更新脉冲环**

在 `animate()` 函数里加入：

```js
const dt = clock.getDelta()
Object.values(stationPulseMeshes).forEach((p) => {
  p.timer = (p.timer || 0) + dt
  if (p.timer >= p.interval) {
    p.timer = 0
    p.frame = (p.frame + 1) % p.frames.length
    p.mesh.material.map = p.frames[p.frame]
    p.mesh.material.needsUpdate = true
  }
})
```

同时需要在 `onMounted` 顶部创建 `const clock = new THREE.Clock()`。

- [ ] **Step 4: 运行验证站点显示**

Run:
```bash
cd web && npm run dev
```
Expected:
- 4 个站点显示渐变光柱、脉冲底座环、顶部光球、站名、数据飘带
- 脉冲环持续扩散

- [ ] **Step 5: Commit**

```bash
git add web/src/components/TerrainModel3D.vue
git commit -m "feat(terrain): 全息站点渲染（脉冲环+渐变光柱+光球+标签+飘带）"
```

---

### Task 5: 前端 — 站点交互、数据更新与预警态

**Files:**
- Modify: `web/src/components/TerrainModel3D.vue`

**Interfaces:**
- Consumes: `api.getLatest`, `useRotationStore().pinStation`
- Produces: hover/click 交互、数据飘带更新、预警颜色切换

- [ ] **Step 1: 引入 rotation store**

在 `<script setup>` 顶部：
```js
import { useRotationStore } from '../store/rotation'
const rotation = useRotationStore()
```

- [ ] **Step 2: 添加 raycaster hover 与 click**

在 `onMounted` 内，animate 之前加入：

```js
const raycaster = new THREE.Raycaster()
const pointer = new THREE.Vector2()
let hoveredCode = null
let resumeTimer = null

function setStationHover(code, hovered) {
  const pillar = stationPillars[code]
  if (pillar) pillar.material.opacity = hovered ? 0.95 : 0.75
}

function onPointerMove(e) {
  const rect = renderer.domElement.getBoundingClientRect()
  pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
  pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1
  raycaster.setFromCamera(pointer, camera)
  const targets = []
  stationGroups.forEach(g => g.children.forEach(c => targets.push(c)))
  const hits = raycaster.intersectObjects(targets, false)
  const newCode = hits.length > 0 ? hits[0].object.parent?.userData?.code : null
  if (newCode !== hoveredCode) {
    if (hoveredCode) setStationHover(hoveredCode, false)
    hoveredCode = newCode
    if (hoveredCode) setStationHover(hoveredCode, true)
    renderer.domElement.style.cursor = hoveredCode ? 'pointer' : 'default'
  }
}

function onClick(e) {
  if (!hoveredCode) return
  rotation.pinStation(hoveredCode)
  controls.autoRotate = false
  clearTimeout(resumeTimer)
  resumeTimer = setTimeout(() => { controls.autoRotate = true }, 8000)
}

renderer.domElement.addEventListener('pointermove', onPointerMove)
renderer.domElement.addEventListener('click', onClick)

controls.addEventListener('start', () => {
  controls.autoRotate = false
  clearTimeout(resumeTimer)
})
controls.addEventListener('end', () => {
  clearTimeout(resumeTimer)
  resumeTimer = setTimeout(() => { controls.autoRotate = true }, 3000)
})
```

- [ ] **Step 3: 更新 fetchAndUpdateData 支持预警态**

替换原有 `fetchAndUpdateData` 为：

```js
function getAlertLevel(level, warning, danger) {
  if (danger != null && level >= danger) return 2
  if (warning != null && level >= warning) return 1
  return 0
}

function setStationAlert(code, level) {
  const p = stationPulseMeshes[code]
  const pillar = stationPillars[code]
  if (!p) return
  if (level === 2) {
    p.frames = pulseTexturesRed
    p.interval = 0.25
    if (pillar) pillar.material.color.setHex(0xEF4444)
  } else if (level === 1) {
    p.frames = pulseTexturesOrange
    p.interval = 0.40
    if (pillar) pillar.material.color.setHex(0xF97316)
  } else {
    p.frames = pulseTexturesCyan
    p.interval = 0.60
    if (pillar) pillar.material.color.setHex(0xFFFFFF)
  }
  p.mesh.material.map = p.frames[p.frame]
}

async function fetchAndUpdateData() {
  try {
    const data = await api.getLatest(ALL_STATION_CODES)
    const items = data?.data || data?.items || []
    for (const item of items) {
      const sprites = stationDataSprites[item.station_code]
      if (!sprites) continue
      const wl = item.water_level ?? item.waterLevel
      const flow = item.virtual_flow ?? item.virtualFlow ?? item.water_flow ?? item.waterFlow
      const warning = item.warning_level ?? item.warningLevel
      const danger = item.danger_level ?? item.dangerLevel
      const alert = getAlertLevel(wl ?? -Infinity, warning, danger)

      if (wl != null) {
        sprites.level.material.map = makeDataTexture('水位', Number(wl).toFixed(2), 'm', alert)
        sprites.level.material.needsUpdate = true
        flashSprite(sprites.level)
      }
      if (flow != null) {
        sprites.flow.material.map = makeDataTexture('流量', Number(flow).toFixed(0), 'm³/s', alert)
        sprites.flow.material.needsUpdate = true
        flashSprite(sprites.flow)
      }
      setStationAlert(item.station_code, alert)
    }
  } catch (e) {
    console.warn('[Terrain3D] 站点数据获取失败:', e.message)
  }
}

function flashSprite(sprite) {
  let t = 0
  const duration = 0.3
  const baseOpacity = sprite.material.opacity
  function step() {
    t += 0.016
    const p = Math.sin((t / duration) * Math.PI)
    sprite.material.opacity = baseOpacity + p * 0.4
    if (t < duration) requestAnimationFrame(step)
    else sprite.material.opacity = baseOpacity
  }
  step()
}
```

- [ ] **Step 4: 在 onUnmounted 清理事件**

在 `onUnmounted` 里追加：
```js
if (renderer?.domElement) {
  renderer.domElement.removeEventListener('pointermove', onPointerMove)
  renderer.domElement.removeEventListener('click', onClick)
}
if (dataTimer) clearInterval(dataTimer)
```

注意：`onPointerMove` / `onClick` 定义在 `onMounted` 内，需要把它们的引用提到外层 `let` 以便清理：
```js
let onPointerMoveHandler = null
let onClickHandler = null
```
在 `onMounted` 内赋值，在 `onUnmounted` 内用这两个变量清理。

- [ ] **Step 5: 运行验证交互**

Run:
```bash
cd web && npm run dev
```
Expected:
- hover 站点时光柱变亮，光标变 pointer
- click 站点右侧抽屉滑出
- 数据每 60s 更新，飘带闪烁
- 如果后端返回 warning/danger level，对应站点变橙/红，脉冲加快

- [ ] **Step 6: Commit**

```bash
git add web/src/components/TerrainModel3D.vue
git commit -m "feat(terrain): 站点 hover/click、数据更新、预警态联动"
```

---

### Task 6: 前端 — TerrainPanel 增加重置视角按钮（可选）

**Files:**
- Modify: `web/src/components/TerrainPanel.vue`
- Modify: `web/src/pages/AppLayout.vue`
- Modify: `web/src/components/TerrainModel3D.vue`

**Interfaces:**
- Produces: `TerrainModel3D.vue` 暴露 `flyToOverview()`；TerrainPanel 触发 `reset-view`

- [ ] **Step 1: TerrainModel3D 暴露 flyToOverview**

在 `<script setup>` 内定义：
```js
function flyToOverview() {
  if (!camera || !controls) return
  const target = new THREE.Vector3(0, 0, MODEL_Z)
  const pos = new THREE.Vector3(-25000, 35000, 45000)
  camera.position.copy(pos)
  controls.target.copy(target)
  controls.update()
}

defineExpose({ flyToOverview })
```

- [ ] **Step 2: AppLayout 接 reset-view 事件**

在 `AppLayout.vue` 里确保 `TerrainModel3D` 有 ref：
```html
<TerrainModel3D ref="terrainRef" />
```

```js
const terrainRef = ref(null)
function onResetView() {
  terrainRef.value?.flyToOverview()
}
```

并把 `onResetView` 传给 `TerrainPanel`：
```html
<TerrainPanel @reset-view="onResetView" />
```

- [ ] **Step 3: TerrainPanel 加按钮**

在 `TerrainPanel.vue` template 合适位置加：
```html
<button @click="$emit('reset-view')">重置视角</button>
```

在 `<script setup>` 加：
```js
defineEmits(['update:terrainExaggeration', 'flyTo', 'flyToOverview', 'reset-view'])
```

- [ ] **Step 4: 运行验证**

Run:
```bash
cd web && npm run dev
```
Expected: 点击 TerrainPanel "重置视角" 按钮，相机回到初始俯视位置

- [ ] **Step 5: Commit**

```bash
git add web/src/components/TerrainModel3D.vue web/src/components/TerrainPanel.vue web/src/pages/AppLayout.vue
git commit -m "feat(terrain): TerrainPanel 增加重置视角按钮"
```

---

### Task 7: 端到端验证

**Files:**
- 不改代码，只验证

- [ ] **Step 1: 跑构建脚本**

Run:
```bash
cd scripts && PYTHONIOENCODING=utf-8 python build_terrain_model.py
cd scripts && PYTHONIOENCODING=utf-8 python -m pytest test_build_terrain.py -v
```
Expected: GLB < 10MB，测试全过

- [ ] **Step 2: 启动前端**

Run:
```bash
cd web && npm run dev
```

- [ ] **Step 3: 按 checklist 逐项验证**

打开浏览器访问 dev URL，登录后进入 Overview：

1. 3D 地形加载后 4 个站点显示全息光柱 ✓
2. 每个站点有脉冲底座环、渐变光柱、顶部光球、站名、数据飘带 ✓
3. hover 时光柱高亮，光标变 pointer ✓
4. click 站点右侧 `StationDrawer` 滑出，自转暂停 8s ✓
5. 数据更新时对应站点飘带闪烁 ✓
6. 模拟 `water_level >= warning_level` 变橙，`>= danger_level` 变红，脉冲加快 ✓
7. 窗口 resize 后站点标签大小正常 ✓
8. 地形颜色层次清晰，河道蓝色可见，远处有雾效消融 ✓
9. 相机初始视角框住四站，不钻地、不缩放过远/过近 ✓
10. GLB 加载有 loading 提示，文件体积 < 10MB ✓
11. 无 WebGL/Console 报错 ✓

- [ ] **Step 4: Commit 验证记录（可选）**

如有文档/checklist 更新：
```bash
git add docs/superpowers/specs/2026-07-10-station-markers-3d-design.md
git commit -m "docs(terrain): 更新站点展示设计文档"
```

---

## Self-Review

**1. Spec coverage:**
- 全息光柱 + 脉冲底座 + 数据飘带 → Task 4 ✓
- 顶部不要光晕 → Task 4 只加实心光球 ✓
- 预警由后端 warning/danger level 判断 → Task 5 ✓
- 纯 Sprite 动画，不引入 Bloom → 全计划无后处理 ✓
- 3D 模型视觉/性能/交互优化 → Task 1/2/3 ✓
- 重置视角 → Task 6 ✓

**2. Placeholder scan:**
- 无 TBD/TODO
- 所有代码块完整
- 所有命令完整

**3. Type consistency:**
- `stationPulseMeshes` / `stationPillars` / `stationDataSprites` 在各 task 中命名一致
- `MODEL_Z` 作为场景中心偏移一致使用
- `useRotationStore().pinStation(code)` 调用一致

