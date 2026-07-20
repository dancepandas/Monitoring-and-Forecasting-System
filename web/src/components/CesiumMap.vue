<template>
  <div ref="container" class="cesium-bg"></div>
</template>

<script setup>
/**
 * CesiumMap.vue — 纯 3D 地形建模底图 (无地图影像)
 * ================================================
 * 这是驾驶舱风格的 3D 地形模型：
 *   - 底图 = 本地 DEM 30m 高程起伏 (无卫星图/街道图)
 *   - 站点 = 直接钉在地形表面 (CLAMP_TO_GROUND)
 *   - 水系 = 叠加在地形上的青色河网
 *   - 地形色 = 驾驶舱深色 + 光照阴影立体感
 */

import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as Cesium from 'cesium'
import 'cesium/Build/Cesium/Widgets/widgets.css'
import { STATIONS } from '../stations'
import { useRotationStore } from '../store/rotation'
import { createLocalTerrainProvider } from '../utils/localTerrainProvider'

const container = ref(null)
let viewer = null
let clickHandler = null
const rotation = useRotationStore()

const props = defineProps({
  useCustomTerrain: { type: Boolean, default: true },
  terrainExaggeration: { type: Number, default: 1.8 },
  showWaterSystem: { type: Boolean, default: true },
  showContours: { type: Boolean, default: false },
  terrainUrl: { type: String, default: '/terrain' },
})

const emit = defineEmits(['ready', 'terrainLoaded', 'waterLoaded'])

// ─── 常量 ────────────────────────────────────────────
const CENTER_LON = 113.02373
const CENTER_LAT = 25.78843
const CYAN = '#22D3EE'
const AQUA = '#67E8F9'
const MONO = '"SF Mono", "JetBrains Mono", Consolas, monospace'

// ─── 传感器节点图标 ──────────────────────────────────
function drawMarker(active) {
  const W = 64, H = 80, c = document.createElement('canvas')
  c.width = W; c.height = H
  const ctx = c.getContext('2d')
  const cx = W / 2, cy = 28, R = active ? 18 : 13

  if (active) {
    const g = ctx.createRadialGradient(cx, cy, R * 0.2, cx, cy, R * 2.8)
    g.addColorStop(0, 'rgba(34,211,238,0.55)')
    g.addColorStop(0.5, 'rgba(34,211,238,0.14)')
    g.addColorStop(1, 'rgba(34,211,238,0)')
    ctx.fillStyle = g
    ctx.beginPath(); ctx.arc(cx, cy, R * 2.8, 0, Math.PI * 2); ctx.fill()
  }

  ctx.beginPath()
  ctx.moveTo(cx - R * 0.5, cy + R * 0.55)
  ctx.lineTo(cx + R * 0.5, cy + R * 0.55)
  ctx.lineTo(cx, H - 6)
  ctx.closePath()
  const pg = ctx.createLinearGradient(0, cy, 0, H)
  pg.addColorStop(0, active ? CYAN : 'rgba(34,211,238,0.45)')
  pg.addColorStop(1, 'rgba(34,211,238,0.04)')
  ctx.fillStyle = pg; ctx.fill()

  ctx.strokeStyle = active ? AQUA : 'rgba(125,211,252,0.45)'; ctx.lineWidth = 1
  for (let i = 0; i < 16; i++) {
    const a = (i / 16) * Math.PI * 2, cardinal = i % 4 === 0
    const r1 = R + 2, r2 = R + (cardinal ? 7 : 4)
    ctx.beginPath()
    ctx.moveTo(cx + Math.cos(a) * r1, cy + Math.sin(a) * r1)
    ctx.lineTo(cx + Math.cos(a) * r2, cy + Math.sin(a) * r2)
    ctx.stroke()
  }

  ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2)
  ctx.fillStyle = active ? 'rgba(8,47,73,0.88)' : 'rgba(8,47,73,0.62)'
  ctx.fill()
  ctx.lineWidth = active ? 2 : 1.2; ctx.strokeStyle = CYAN; ctx.stroke()

  ctx.beginPath(); ctx.arc(cx, cy, R * 0.6, 0, Math.PI * 2)
  ctx.strokeStyle = 'rgba(103,232,249,0.55)'; ctx.lineWidth = 1; ctx.stroke()

  const drawWave = (yoff, amp, ph, color, lw) => {
    ctx.strokeStyle = color; ctx.lineWidth = lw; ctx.lineCap = 'round'
    ctx.beginPath()
    const span = R * 0.44
    for (let x = -span; x <= span; x += 0.8) {
      const yy = cy + yoff + Math.sin((x / span) * Math.PI * 2 + ph) * amp
      x === -span ? ctx.moveTo(cx + x, yy) : ctx.lineTo(cx + x, yy)
    }
    ctx.stroke()
  }
  drawWave(-1, R * 0.15, 0, '#E0FBFC', active ? 2 : 1.5)
  drawWave(3, R * 0.11, Math.PI, 'rgba(103,232,249,0.75)', 1.2)

  if (active) {
    ctx.strokeStyle = AQUA; ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(cx - R * 1.7, cy); ctx.lineTo(cx - R * 1.2, cy)
    ctx.moveTo(cx + R * 1.2, cy); ctx.lineTo(cx + R * 1.7, cy)
    ctx.stroke()
  }
  return c.toDataURL()
}

function circleRing(lon, lat, rMeters) {
  const N = 64
  const dLat = rMeters / 111320
  const dLon = rMeters / (111320 * Math.cos(lat * Math.PI / 180))
  const pts = []
  for (let i = 0; i <= N; i++) {
    const a = (i / N) * Math.PI * 2
    pts.push(Cesium.Cartesian3.fromDegrees(lon + Math.cos(a) * dLon, lat + Math.sin(a) * dLat, 0))
  }
  return pts
}

// ─── 水系 GeoJSON 加载 ────────────────────────────────
let waterDataSources = []

async function loadWaterSystem() {
  if (!viewer) return
  const waterFiles = ['/geo/water_system.geojson', '/geo/chenzhou_waterways.geojson']
  for (const url of waterFiles) {
    try {
      const resp = await fetch(url)
      if (!resp.ok) continue
      const geojson = await resp.json()

      const dataSource = await Cesium.GeoJsonDataSource.load(geojson, {
        stroke: Cesium.Color.fromCssColorString('#4DF0FF'),
        fill: Cesium.Color.fromCssColorString('#0C4A6E').withAlpha(0.35),
        strokeWidth: 2,
        clampToGround: true,
      })

      const entities = dataSource.entities.values
      for (const entity of entities) {
        if (!entity.polyline && !entity.polygon) continue
        const p = entity.properties
        if (!p) continue
        const waterway = p.waterway?.getValue() || ''
        const name = p.name?.getValue() || p['name:zh']?.getValue() || ''

        if (entity.polyline) {
          const isMain = waterway === 'river' || name.length > 0
          entity.polyline.width = isMain ? 3 : 1.5
          entity.polyline.material = new Cesium.PolylineGlowMaterialProperty({
            glowPower: 0.2,
            color: Cesium.Color.fromCssColorString(isMain ? '#4DF0FF' : '#2CB8C8').withAlpha(isMain ? 0.95 : 0.7),
          })
          entity.polyline.clampToGround = true
        }
        if (entity.polygon) {
          entity.polygon.material = Cesium.Color.fromCssColorString('#0EA5E9').withAlpha(0.5)
          entity.polygon.outline = true
          entity.polygon.outlineColor = Cesium.Color.fromCssColorString('#38BDF8')
        }
      }

      viewer.dataSources.add(dataSource)
      waterDataSources.push(dataSource)
      console.log(`[CesiumMap] 水系: ${url} (${entities.length} 要素)`)
      emit('waterLoaded', waterDataSources.length)
      return  // 第一个成功就够了
    } catch (e) {
      console.warn(`[CesiumMap] 水系加载失败 ${url}:`, e.message)
    }
  }
}

// ─── 监听 ────────────────────────────────────────────
watch(() => props.terrainExaggeration, (val) => {
  if (viewer) viewer.scene.verticalExaggeration = val
})
watch(() => props.showWaterSystem, (show) => {
  for (const ds of waterDataSources) ds.show = show
})

// ─── 生命周期 ────────────────────────────────────────
onMounted(() => {
  if (!container.value) return
  Cesium.Ion.defaultAccessToken = import.meta.env.VITE_CESIUM_ION_TOKEN || ''

  viewer = new Cesium.Viewer(container.value, {
    // ★ 关键：不要任何地图影像底图 —— 纯 3D 地形建模
    baseLayer: false,
    animation: false, timeline: false, baseLayerPicker: false, fullscreenButton: false,
    homeButton: false, geocoder: false, sceneModePicker: false, navigationHelpButton: false,
    infoBox: false, selectionIndicator: false, creditContainer: undefined,
  })

  const scene = viewer.scene

  // ★ 地形：自定义 provider 加载本地 30m DEM
  if (props.useCustomTerrain) {
    try {
      const provider = createLocalTerrainProvider(props.terrainUrl, {
        minZoom: 10, maxZoom: 15,
        bounds: [112.0, 25.0, 114.0, 27.0],
      })
      viewer.terrainProvider = provider
      console.log('[CesiumMap] 本地 DEM 地形 provider 已挂载')
      emit('terrainLoaded')
    } catch (e) {
      console.error('[CesiumMap] 地形 provider 失败:', e)
    }
  }

  // 地形夸张 + 光照 (立体感)
  scene.verticalExaggeration = props.terrainExaggeration
  scene.verticalExaggerationRelativeHeight = 0.0
  scene.globe.enableLighting = true
  scene.globe.showGroundAtmosphere = true
  scene.globe.atmosphereLightIntensity = 8.0

  // ★ 关键: 锁定郴州正午时间 (UTC 04:30)，否则 enableLighting 在夜半球会让地形全黑
  viewer.clock.currentTime = Cesium.JulianDate.fromIso8601('2026-06-21T04:30:00Z')
  viewer.clock.shouldAnimate = false

  // 驾驶舱深色地形底色 (无影像时 globe 表面色)
  scene.globe.baseColor = Cesium.Color.fromCssColorString('#14384A')

  // 天空大气
  scene.skyAtmosphere.show = true
  scene.skyAtmosphere.hueShift = 0.0
  scene.skyAtmosphere.saturationShift = -0.3
  scene.skyAtmosphere.brightnessShift = -0.1
  scene.backgroundColor = Cesium.Color.fromCssColorString('#06141D')

  // 抗锯齿 + 提升地形边缘
  if (scene.fxaa) scene.fxaa = true
  scene.globe.maximumScreenSpaceError = 2.0  // 更细的地形细节

  // ── 相机：郴州上空斜视，展示 3D 地形起伏 ──
  viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(CENTER_LON + 0.05, CENTER_LAT - 0.20, 18000),
    orientation: {
      heading: Cesium.Math.toRadians(20),
      pitch: Cesium.Math.toRadians(-48),
      roll: 0,
    },
    duration: 2.5,
  })

  // ── 站点：直接钉在地形表面 ──
  const imgActive = drawMarker(true)
  const imgIdle = drawMarker(false)
  const refs = new Map()

  for (const s of STATIONS) {
    const marker = viewer.entities.add({
      id: s.code,
      position: Cesium.Cartesian3.fromDegrees(s.lon, s.lat, 0),
      billboard: {
        image: imgIdle,
        verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
        heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
        scale: 0.78,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
      label: {
        text: `${s.name}`,
        font: `bold 13px ${MONO}`,
        scale: 1.6,
        fillColor: Cesium.Color.WHITE,
        outlineColor: Cesium.Color.fromCssColorString('#020D14'),
        outlineWidth: 5,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        showBackground: false,
        verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
        pixelOffset: new Cesium.Cartesian2(0, -50),
        eyeOffset: new Cesium.Cartesian3(0, 0, -35),
        heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    })

    const beam = viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(s.lon, s.lat, 0),
      polyline: {
        positions: [
          Cesium.Cartesian3.fromDegrees(s.lon, s.lat, 0),
          Cesium.Cartesian3.fromDegrees(s.lon, s.lat, 950),
        ],
        width: 6,
        material: new Cesium.PolylineGlowMaterialProperty({
          glowPower: 0.32, color: Cesium.Color.fromCssColorString(CYAN),
        }),
      },
      show: false,
    })

    const ringSpecs = [
      { r: 420, w: 4, a: 0.5 },
      { r: 760, w: 3, a: 0.26 },
      { r: 1120, w: 2, a: 0.13 },
    ]
    const rings = ringSpecs.map(spec => viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(s.lon, s.lat, 0),
      polyline: {
        positions: circleRing(s.lon, s.lat, spec.r),
        width: spec.w,
        material: new Cesium.PolylineGlowMaterialProperty({
          glowPower: 0.3,
          color: Cesium.Color.fromCssColorString(CYAN).withAlpha(spec.a),
        }),
        clampToGround: true,
      },
      show: false,
    }))
    refs.set(s.code, { marker, beam, rings })
  }

  function updateHighlight(activeCode) {
    for (const [code, r] of refs) {
      const active = code === activeCode
      r.marker.billboard.image = active ? imgActive : imgIdle
      r.marker.billboard.scale = active ? 0.88 : 0.72
      r.marker.label.font = active ? `bold 15px ${MONO}` : `bold 13px ${MONO}`
      r.marker.label.scale = active ? 2.0 : 1.6
      r.marker.label.fillColor = active
        ? Cesium.Color.fromCssColorString('#E0FBFC')
        : Cesium.Color.WHITE
      r.beam.show = active
      r.rings.forEach(ring => { ring.show = active })
    }
  }
  watch(() => rotation.current.code, (code) => updateHighlight(code), { immediate: true })

  clickHandler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas)
  clickHandler.setInputAction((click) => {
    const picked = viewer.scene.pick(click.position)
    if (Cesium.defined(picked) && picked.id && typeof picked.id.id === 'string') {
      const code = picked.id.id
      if (STATIONS.some(s => s.code === code)) rotation.pinStation(code)
    } else {
      rotation.unpinStation()
    }
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK)

  if (props.showWaterSystem) loadWaterSystem()

  emit('ready', { viewer, scene })
})

onUnmounted(() => {
  if (clickHandler) { clickHandler.destroy(); clickHandler = null }
  if (viewer) { viewer.destroy(); viewer = null }
  waterDataSources = []
})

defineExpose({
  getViewer: () => viewer,
  flyToStation: (code) => {
    const s = STATIONS.find(st => st.code === code)
    if (s && viewer) {
      viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(s.lon, s.lat, 3500),
        orientation: { heading: 0, pitch: Cesium.Math.toRadians(-60), roll: 0 },
        duration: 1.5,
      })
    }
  },
  flyToOverview: () => {
    if (viewer) {
      viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(CENTER_LON + 0.05, CENTER_LAT - 0.20, 18000),
        orientation: {
          heading: Cesium.Math.toRadians(20),
          pitch: Cesium.Math.toRadians(-48),
          roll: 0,
        },
        duration: 2.0,
      })
    }
  },
  reloadWaterSystem: loadWaterSystem,
})
</script>

<style scoped>
.cesium-bg {
  position: fixed;
  inset: 0;
  z-index: 0;
}
:deep(.cesium-viewer .cesium-widget-credits) { display: none !important; }
:deep(.cesium-viewer-bottom) { display: none; }
</style>
