<template>
  <div ref="container" class="terrain-bg">
    <div v-if="isLoading" class="terrain-loading">
      <span class="terrain-loading-spinner"></span>
      <span class="terrain-loading-text">加载 3D 地形模型...</span>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { STATIONS } from '../stations'
import { api, ALL_STATION_CODES } from '../api'
import { useRotationStore } from '../store/rotation'

const rotation = useRotationStore()
const container = ref(null)
const isLoading = ref(true)
let renderer, scene, camera, controls, model, animateId
let dracoLoader = null
let meta = null
const stationGroups = []
const stationDataSprites = {}
let dataTimer = null
let onPointerMoveHandler = null
let onClickHandler = null
const activeFlashes = new Map()
const MODEL_Z = 15500

function lonlatToModel(lon, lat) {
  const cosLat = Math.cos(meta.center_lat * Math.PI / 180)
  const M = 111320
  return { x: (lon - meta.center_lon) * M * cosLat, y: (lat - meta.center_lat) * M }
}

function heightAt(lon, lat) {
  const { grid_size, heights_meters, exaggeration, west, east, north, south } = meta
  const gx = Math.round((lon - west) / (east - west) * (grid_size - 1))
  const gy = Math.round((north - lat) / (north - south) * (grid_size - 1))
  const i = Math.max(0, Math.min(grid_size - 1, gy))
  const j = Math.max(0, Math.min(grid_size - 1, gx))
  return heights_meters[i][j] * exaggeration
}

function flyToOverview() {
  if (!camera || !controls) return
  camera.position.set(0, 0, 80000)
  controls.target.set(0, 0, MODEL_Z)
  // 重置正交相机 zoom 到初始 frustum
  const el = container.value
  if (el) {
    const w = el.clientWidth, h = el.clientHeight
    const aspect = w / h
    const frustumSize = 35000
    camera.left = -frustumSize * aspect / 2
    camera.right = frustumSize * aspect / 2
    camera.top = frustumSize / 2
    camera.bottom = -frustumSize / 2
    camera.updateProjectionMatrix()
  }
  controls.update()
}

defineExpose({ flyToOverview })

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

function buildStations() {
  STATIONS.forEach((s) => {
    const { x, y } = lonlatToModel(s.lon, s.lat)
    const z = heightAt(s.lon, s.lat) + MODEL_Z
    const g = new THREE.Group()
    g.position.set(x, y, z + 80)
    g.userData = { code: s.code, name: s.name }

    // 平面圆环标记
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(500, 900, 32),
      new THREE.MeshBasicMaterial({
        color: 0x22D3EE,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.9,
        depthTest: false,
      })
    )
    ring.rotation.x = 0
    g.add(ring)

    // 中心实心点
    const dot = new THREE.Mesh(
      new THREE.CircleGeometry(350, 32),
      new THREE.MeshBasicMaterial({
        color: 0x67E8F9,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.95,
        depthTest: false,
      })
    )
    g.add(dot)

    // 站名标签
    const label = new THREE.Sprite(new THREE.SpriteMaterial({
      map: makeNameTexture(s.name.split('-').pop()),
      transparent: true,
      depthTest: false,
    }))
    label.position.set(0, 1400, 0)
    label.scale.set(3200, 800, 1)
    g.add(label)

    // 水位数据
    const level = new THREE.Sprite(new THREE.SpriteMaterial({
      map: makeDataTexture('水位', '--', 'm'),
      transparent: true,
      depthTest: false,
    }))
    level.position.set(0, -1400, 0)
    level.scale.set(3200, 420, 1)
    g.add(level)

    stationDataSprites[s.code] = { level }
    scene.add(g)
    stationGroups.push(g)
  })
}

function getAlertLevel(level, warning, danger) {
  if (danger != null && level >= danger) return 2
  if (warning != null && level >= warning) return 1
  return 0
}

function setStationAlert(code, level) {
  // 平面版本暂不做预警颜色变化，后续可在此改标记颜色
}

function flashSprite(sprite) {
  let t = 0
  const duration = 0.3
  const baseOpacity = sprite.material.opacity
  const prev = activeFlashes.get(sprite)
  if (prev) cancelAnimationFrame(prev)
  function step() {
    t += 0.016
    const p = Math.sin((t / duration) * Math.PI)
    sprite.material.opacity = baseOpacity + p * 0.4
    if (t < duration) {
      activeFlashes.set(sprite, requestAnimationFrame(step))
    } else {
      sprite.material.opacity = baseOpacity
      activeFlashes.delete(sprite)
    }
  }
  activeFlashes.set(sprite, requestAnimationFrame(step))
}

async function fetchAndUpdateData() {
  try {
    const data = await api.getLatest(ALL_STATION_CODES)
    const items = data?.data || data?.items || []
    for (const item of items) {
      const sprites = stationDataSprites[item.station_code]
      if (!sprites) continue
      const wl = item.water_level ?? item.waterLevel
      const warning = item.warning_level ?? item.warningLevel
      const danger = item.danger_level ?? item.dangerLevel
      const alert = getAlertLevel(wl ?? -Infinity, warning, danger)

      if (wl != null) {
        sprites.level.material.map = makeDataTexture('水位', Number(wl).toFixed(2), 'm', alert)
        sprites.level.material.needsUpdate = true
        flashSprite(sprites.level)
      }
      setStationAlert(item.station_code, alert)
    }
  } catch (e) {
    console.warn('[Terrain3D] 站点数据获取失败:', e.message)
  }
}

onMounted(() => {
  const clock = new THREE.Clock()
  const el = container.value
  const w = el.clientWidth, h = el.clientHeight

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.setSize(w, h)
  renderer.setClearColor(0x06141D, 1)
  el.appendChild(renderer.domElement)

  scene = new THREE.Scene()
  scene.background = new THREE.Color('#06141D')
  scene.fog = new THREE.Fog('#06141D', 25000, 90000)

  // 正俯视 OrthographicCamera，把 3D 地形当成平面地图看
  const aspect = w / h
  const frustumSize = 35000
  camera = new THREE.OrthographicCamera(
    frustumSize * aspect / -2,
    frustumSize * aspect / 2,
    frustumSize / 2,
    frustumSize / -2,
    1,
    200000
  )
  camera.position.set(0, 0, 80000)
  camera.lookAt(0, 0, MODEL_Z)
  camera.up.set(0, 1, 0)

  scene.add(new THREE.AmbientLight(0x335566, 0.6))
  const dir = new THREE.DirectionalLight(0xaaccdd, 1.0)
  dir.position.set(30000, -40000, 50000)
  scene.add(dir)

  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.06
  controls.enableRotate = false
  controls.enableZoom = true
  controls.enablePan = true
  controls.target.set(0, 0, MODEL_Z)
  controls.update()

  const raycaster = new THREE.Raycaster()
  const pointer = new THREE.Vector2()
  let hoveredCode = null

  function setStationHover(code, hovered) {
    // 平面版本暂只做光标变化，后续可加标记高亮
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
  }

  onPointerMoveHandler = onPointerMove
  onClickHandler = onClick
  renderer.domElement.addEventListener('pointermove', onPointerMoveHandler)
  renderer.domElement.addEventListener('click', onClickHandler)

  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.06
  controls.enableRotate = false
  controls.enableZoom = true
  controls.enablePan = true
  controls.target.set(0, 0, MODEL_Z)
  controls.update()

  dracoLoader = new DRACOLoader()
  dracoLoader.setDecoderPath('/draco/')
  const loader = new GLTFLoader()
  loader.setDRACOLoader(dracoLoader)
  loader.load('/models/terrain.glb',
    async (gltf) => {
      isLoading.value = false
      model = gltf.scene
      model.scale.set(1.15, 1.15, 0.22)
      model.position.z = MODEL_Z
      model.traverse((child) => {
        if (child.isMesh) {
          child.material = new THREE.MeshStandardMaterial({
            vertexColors: true,
            roughness: 0.6,
            metalness: 0.08,
            emissive: 0x000000,
          })
        }
      })
      scene.add(model)
      try {
        const resp = await fetch('/models/terrain_meta.json')
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        meta = await resp.json()
        buildStations()
        fetchAndUpdateData()
        dataTimer = setInterval(fetchAndUpdateData, 60000)
        console.log('[Terrain3D] 模型+站点就绪, 站点', stationGroups.length)
      } catch (e) {
        console.error('[Terrain3D] 元数据加载失败:', e.message)
      }
    },
    undefined,
    (err) => {
      isLoading.value = false
      console.error('[Terrain3D] 模型加载失败:', err)
    }
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
  if (camera.isOrthographicCamera) {
    const aspect = w / h
    const frustumSize = 35000
    camera.left = -frustumSize * aspect / 2
    camera.right = frustumSize * aspect / 2
    camera.top = frustumSize / 2
    camera.bottom = -frustumSize / 2
    camera.updateProjectionMatrix()
  }
}

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  if (renderer?.domElement) {
    renderer.domElement.removeEventListener('pointermove', onPointerMoveHandler)
    renderer.domElement.removeEventListener('click', onClickHandler)
  }
  if (dataTimer) clearInterval(dataTimer)
  activeFlashes.forEach((id) => { if (id) cancelAnimationFrame(id) })
  activeFlashes.clear()
  if (animateId) cancelAnimationFrame(animateId)
  if (controls) { controls.dispose() }
  if (dracoLoader) dracoLoader.dispose()
  if (renderer) { renderer.dispose(); renderer.domElement.remove() }
})
</script>

<style scoped>
.terrain-bg { width: 100%; height: 100%; position: relative; }

.terrain-loading {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: #06141D;
  color: #94A3B8;
  font-family: var(--sans);
  font-size: 13px;
  z-index: 2;
  pointer-events: none;
}

.terrain-loading-spinner {
  width: 28px;
  height: 28px;
  border: 3px solid rgba(148, 163, 184, 0.25);
  border-top-color: #22D3EE;
  border-radius: 50%;
  animation: terrain-spin 0.9s linear infinite;
}

.terrain-loading-text {
  letter-spacing: 0.02em;
}

@keyframes terrain-spin {
  to { transform: rotate(360deg); }
}
</style>
