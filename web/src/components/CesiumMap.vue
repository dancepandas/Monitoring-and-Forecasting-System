<template>
  <div ref="container" class="cesium-bg"></div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as Cesium from 'cesium'
import 'cesium/Build/Cesium/Widgets/widgets.css'
import { STATIONS } from '../stations'
import { useRotationStore } from '../store/rotation'

const container = ref(null)
let viewer = null
let clickHandler = null
const rotation = useRotationStore()

// 相机初始定位：燕泉河 00234
const CENTER_LON = 113.02373
const CENTER_LAT = 25.78843

// 水利科技感配色
const CYAN = '#22D3EE'
const AQUA = '#67E8F9'
const DEEP = '#082F49'
const MONO = '"SF Mono", "JetBrains Mono", Consolas, monospace'

// 水文传感器节点图标：表盘刻度 + 同心环 + 中央水波纹 + 指向尖端；active 带光晕与侧十字
function drawMarker(active) {
  const W = 64, H = 80, c = document.createElement('canvas')
  c.width = W; c.height = H
  const ctx = c.getContext('2d')
  const cx = W / 2, cy = 28, R = active ? 18 : 13

  // 1. 光晕（active）
  if (active) {
    const g = ctx.createRadialGradient(cx, cy, R * 0.2, cx, cy, R * 2.8)
    g.addColorStop(0, 'rgba(34,211,238,0.55)')
    g.addColorStop(0.5, 'rgba(34,211,238,0.14)')
    g.addColorStop(1, 'rgba(34,211,238,0)')
    ctx.fillStyle = g
    ctx.beginPath(); ctx.arc(cx, cy, R * 2.8, 0, Math.PI * 2); ctx.fill()
  }

  // 2. 指向地面的尖端（渐变）
  ctx.beginPath()
  ctx.moveTo(cx - R * 0.5, cy + R * 0.55)
  ctx.lineTo(cx + R * 0.5, cy + R * 0.55)
  ctx.lineTo(cx, H - 6)
  ctx.closePath()
  const pg = ctx.createLinearGradient(0, cy, 0, H)
  pg.addColorStop(0, active ? CYAN : 'rgba(34,211,238,0.45)')
  pg.addColorStop(1, 'rgba(34,211,238,0.04)')
  ctx.fillStyle = pg
  ctx.fill()

  // 3. 表盘刻度（16 档，基本方位更长）
  ctx.strokeStyle = active ? AQUA : 'rgba(125,211,252,0.45)'
  ctx.lineWidth = 1
  for (let i = 0; i < 16; i++) {
    const a = (i / 16) * Math.PI * 2
    const cardinal = i % 4 === 0
    const r1 = R + 2, r2 = R + (cardinal ? 7 : 4)
    ctx.beginPath()
    ctx.moveTo(cx + Math.cos(a) * r1, cy + Math.sin(a) * r1)
    ctx.lineTo(cx + Math.cos(a) * r2, cy + Math.sin(a) * r2)
    ctx.stroke()
  }

  // 4. 外环 + 底盘
  ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2)
  ctx.fillStyle = active ? 'rgba(8,47,73,0.88)' : 'rgba(8,47,73,0.62)'
  ctx.fill()
  ctx.lineWidth = active ? 2 : 1.2
  ctx.strokeStyle = CYAN
  ctx.stroke()

  // 5. 内环
  ctx.beginPath(); ctx.arc(cx, cy, R * 0.6, 0, Math.PI * 2)
  ctx.strokeStyle = 'rgba(103,232,249,0.55)'
  ctx.lineWidth = 1
  ctx.stroke()

  // 6. 中央水波纹（两条正弦波）
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

  // 7. 侧十字标线（active）
  if (active) {
    ctx.strokeStyle = AQUA; ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(cx - R * 1.7, cy); ctx.lineTo(cx - R * 1.2, cy)
    ctx.moveTo(cx + R * 1.2, cy); ctx.lineTo(cx + R * 1.7, cy)
    ctx.stroke()
  }
  return c.toDataURL()
}

// 静态圆环点列（地面声呐环，无动画 → 不会触发 ellipse 校验崩溃）
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

onMounted(() => {
  if (!container.value) return
  Cesium.Ion.defaultAccessToken = import.meta.env.VITE_CESIUM_ION_TOKEN || ''
  if (!Cesium.Ion.defaultAccessToken) console.warn('[CesiumMap] VITE_CESIUM_ION_TOKEN not set')

  viewer = new Cesium.Viewer(container.value, {
    animation: false, timeline: false, baseLayerPicker: false, fullscreenButton: false,
    homeButton: false, geocoder: false, sceneModePicker: false, navigationHelpButton: false,
    infoBox: false, selectionIndicator: false, creditContainer: undefined,
  })

  const scene = viewer.scene
  scene.globe.enableLighting = true
  scene.skyAtmosphere.show = true
  scene.skyAtmosphere.hueShift = 0.0
  scene.skyAtmosphere.saturationShift = -0.3
  scene.skyAtmosphere.brightnessShift = -0.1
  scene.globe.baseColor = Cesium.Color.fromCssColorString('#9bb7c4')
  scene.backgroundColor = Cesium.Color.fromCssColorString('#0B2A3A')

  // 相机站在燕泉河南侧约 18km 处，向北俯视，使站点落在画面中央
  viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(CENTER_LON + 0.022, CENTER_LAT - 0.205, 18000),
    orientation: { heading: 0, pitch: Cesium.Math.toRadians(-45), roll: 0 },
    duration: 1.5,
  })

  const imgActive = drawMarker(true)
  const imgIdle = drawMarker(false)

  // 每站：节点标记 + 信号光柱 + 三圈声呐环（仅 active 显示）
  const refs = new Map()   // code -> { marker, beam, rings }
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
    // 信号光柱
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
    // 三圈声呐地面环
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
      },
      show: false,
    }))
    refs.set(s.code, { marker, beam, rings })
  }

  // 高亮当前轮播/钉选站
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
      r.marker.label.outlineColor = active
        ? Cesium.Color.fromCssColorString('#041F2E')
        : Cesium.Color.fromCssColorString('#041F2E')
      r.beam.show = active
      r.rings.forEach(ring => { ring.show = active })
    }
  }
  watch(() => rotation.current.code, (code) => updateHighlight(code), { immediate: true })

  // 点击站点 → 钉选
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
})

onUnmounted(() => {
  if (clickHandler) { clickHandler.destroy(); clickHandler = null }
  if (viewer) { viewer.destroy(); viewer = null }
})
</script>

<style scoped>
.cesium-bg { position: fixed; inset: 0; z-index: 0; }
</style>
