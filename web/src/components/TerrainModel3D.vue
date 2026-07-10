<template>
  <div ref="container" class="terrain-bg"></div>
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
let renderer, scene, camera, controls, model, animateId
let dracoLoader = null
let meta = null
const stationGroups = []
const stationDataSprites = {}
const stationPulseMeshes = {}
const stationPillars = {}
let dataTimer = null
let onPointerMoveHandler = null
let onClickHandler = null
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

function fitCameraToModel(obj) {
  if (!camera || !controls) return
  const box = new THREE.Box3().setFromObject(obj)
  const sphere = new THREE.Sphere()
  box.getBoundingSphere(sphere)
  const target = new THREE.Vector3(0, 0, MODEL_Z)
  const dir = new THREE.Vector3(-25000, 35000, 45000).sub(target).normalize()
  const fovRad = (camera.fov * Math.PI) / 180
  const distance = (sphere.radius / Math.sin(fovRad / 2)) * 1.12
  camera.position.copy(target).add(dir.multiplyScalar(distance))
  controls.target.copy(target)
  controls.update()
}

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

function makePulseTextures(color = 'rgba(34, 211, 238, 0.8)') {
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

  camera = new THREE.PerspectiveCamera(45, w / h, 1, 200000)
  camera.up.set(0, 0, 1)
  camera.position.set(-25000, 35000, 45000)

  scene.add(new THREE.AmbientLight(0x335566, 0.5))
  const dir = new THREE.DirectionalLight(0xaaccdd, 0.9)
  dir.position.set(30000, -40000, 50000)
  scene.add(dir)
  const fill = new THREE.DirectionalLight(0x1e3a4c, 0.3)
  fill.position.set(-30000, 30000, 20000)
  scene.add(fill)

  controls = new OrbitControls(camera, renderer.domElement)
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
  controls.update()

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

  onPointerMoveHandler = onPointerMove
  onClickHandler = onClick
  renderer.domElement.addEventListener('pointermove', onPointerMoveHandler)
  renderer.domElement.addEventListener('click', onClickHandler)

  controls.addEventListener('start', () => {
    controls.autoRotate = false
    clearTimeout(resumeTimer)
  })
  controls.addEventListener('end', () => {
    clearTimeout(resumeTimer)
    resumeTimer = setTimeout(() => { controls.autoRotate = true }, 3000)
  })

  dracoLoader = new DRACOLoader()
  dracoLoader.setDecoderPath('/draco/')
  const loader = new GLTFLoader()
  loader.setDRACOLoader(dracoLoader)
  loader.load('/models/terrain.glb',
    async (gltf) => {
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
    (err) => console.error('[Terrain3D] 模型加载失败:', err)
  )

  const animate = () => {
    animateId = requestAnimationFrame(animate)
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
  if (renderer?.domElement) {
    renderer.domElement.removeEventListener('pointermove', onPointerMoveHandler)
    renderer.domElement.removeEventListener('click', onClickHandler)
  }
  if (dataTimer) clearInterval(dataTimer)
  if (animateId) cancelAnimationFrame(animateId)
  if (controls) controls.dispose()
  if (dracoLoader) dracoLoader.dispose()
  if (renderer) { renderer.dispose(); renderer.domElement.remove() }
})
</script>

<style scoped>
.terrain-bg { width: 100%; height: 100%; }
</style>
