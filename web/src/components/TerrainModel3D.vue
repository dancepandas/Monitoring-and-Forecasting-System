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

const container = ref(null)
let renderer, scene, camera, controls, model, animateId
let dracoLoader = null
let meta = null
const stationGroups = []
const stationDataSprites = {}
let dataTimer = null
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

function makeLabelTexture(text) {
  const c = document.createElement('canvas')
  c.width = 360; c.height = 90
  const ctx = c.getContext('2d')
  ctx.font = 'bold 40px "Roboto", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif'
  ctx.fillStyle = '#0F172A'
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
  ctx.fillText(text, 180, 45)
  const tex = new THREE.CanvasTexture(c)
  tex.minFilter = THREE.LinearFilter
  return tex
}

function makeDataTexture(text) {
  const c = document.createElement('canvas')
  c.width = 380; c.height = 54
  const ctx = c.getContext('2d')
  ctx.font = '600 28px "Roboto", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif'
  ctx.fillStyle = '#1E293B'
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
  ctx.fillText(text, 190, 27)
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
    g.userData = { code: s.code }

    const pillarH = 1800
    const pillar = new THREE.Mesh(
      new THREE.CylinderGeometry(70, 70, pillarH, 8),
      new THREE.MeshBasicMaterial({ color: 0x2563EB, transparent: true, opacity: 0.85 })
    )
    pillar.rotation.x = Math.PI / 2
    pillar.position.set(0, 0, pillarH / 2)
    g.add(pillar)

    const top = new THREE.Mesh(
      new THREE.SphereGeometry(180, 12, 12),
      new THREE.MeshBasicMaterial({ color: 0x3B82F6 })
    )
    top.position.set(0, 0, pillarH)
    g.add(top)

    const label = new THREE.Sprite(new THREE.SpriteMaterial({ map: makeLabelTexture(s.name.split('-').pop()) }))
    label.position.set(0, 0, pillarH + 320)
    label.scale.set(3000, 750, 1)
    g.add(label)

    const dataLevel = new THREE.Sprite(new THREE.SpriteMaterial({ map: makeDataTexture('水位: -- m') }))
    dataLevel.position.set(0, 0, pillarH + 800)
    dataLevel.scale.set(3000, 425, 1)
    g.add(dataLevel)

    const dataFlow = new THREE.Sprite(new THREE.SpriteMaterial({ map: makeDataTexture('流量: -- m³/s') }))
    dataFlow.position.set(0, 0, pillarH + 1120)
    dataFlow.scale.set(3000, 425, 1)
    g.add(dataFlow)

    stationDataSprites[s.code] = { level: dataLevel, flow: dataFlow }
    scene.add(g)
    stationGroups.push(g)
  })
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
      if (wl != null) {
        sprites.level.material.map = makeDataTexture(`水位: ${Number(wl).toFixed(2)} m`)
        sprites.level.material.needsUpdate = true
      }
      if (flow != null) {
        sprites.flow.material.map = makeDataTexture(`流量: ${Number(flow).toFixed(0)} m³/s`)
        sprites.flow.material.needsUpdate = true
      }
    }
  } catch (e) {
    console.warn('[Terrain3D] 站点数据获取失败:', e.message)
  }
}

onMounted(() => {
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
