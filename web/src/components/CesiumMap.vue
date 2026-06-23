<template>
  <div ref="container" class="cesium-bg"></div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import * as Cesium from 'cesium'
import 'cesium/Build/Cesium/Widgets/widgets.css'

const container = ref(null)
let viewer = null


const XIANTAO_LON = 113.447
const XIANTAO_LAT = 30.3795

onMounted(() => {
  if (!container.value) return

  Cesium.Ion.defaultAccessToken = import.meta.env.VITE_CESIUM_ION_TOKEN || ''
  if (!Cesium.Ion.defaultAccessToken) {
    console.warn('[CesiumMap] VITE_CESIUM_ION_TOKEN not set')
  }

  viewer = new Cesium.Viewer(container.value, {
    animation: false,
    timeline: false,
    baseLayerPicker: false,
    fullscreenButton: false,
    homeButton: false,
    geocoder: false,
    sceneModePicker: false,
    navigationHelpButton: false,
    infoBox: false,
    selectionIndicator: false,
    creditContainer: undefined,
  })

  const scene = viewer.scene
  scene.globe.enableLighting = true
  scene.skyAtmosphere.show = false

  // 定位到仙桃站，使其位于画面中心，保持 45° 俯视
  viewer.camera.lookAt(
    Cesium.Cartesian3.fromDegrees(XIANTAO_LON, XIANTAO_LAT, 0),
    new Cesium.HeadingPitchRange(
      Cesium.Math.toRadians(0),
      Cesium.Math.toRadians(-45),
      18000
    )
  )

  // 仙桃站标记
  viewer.entities.add({
    position: Cesium.Cartesian3.fromDegrees(XIANTAO_LON, XIANTAO_LAT, 0),
    billboard: {
      image: createPin('#e53935'),
      verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
      heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
      scale: 0.5,
    },
    label: {
      text: '仙桃站 00106',
      font: '14px sans-serif',
      fillColor: Cesium.Color.WHITE,
      outlineColor: Cesium.Color.fromCssColorString('#1a5f7a'),
      outlineWidth: 3,
      style: Cesium.LabelStyle.FILL_AND_OUTLINE,
      verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
      pixelOffset: new Cesium.Cartesian2(0, -34),
      heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
    },
  })

})

function createPin(color) {
  const c = document.createElement('canvas')
  c.width = 28; c.height = 36
  const ctx = c.getContext('2d')
  ctx.beginPath(); ctx.arc(14, 13, 9, 0, Math.PI * 2)
  ctx.fillStyle = color; ctx.fill()
  ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.stroke()
  ctx.beginPath(); ctx.moveTo(7, 20); ctx.lineTo(21, 20); ctx.lineTo(14, 34); ctx.closePath()
  ctx.fillStyle = color; ctx.fill()
  ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5; ctx.stroke()
  return c.toDataURL()
}

onUnmounted(() => {
  if (viewer) { viewer.destroy(); viewer = null }
})
</script>

<style scoped>
.cesium-bg {
  position: fixed;
  inset: 0;
  z-index: 0;
}
</style>
