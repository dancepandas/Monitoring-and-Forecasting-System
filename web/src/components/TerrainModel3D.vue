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

  renderer = new THREE.WebGLRenderer({ antialias: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.setSize(w, h)
  renderer.setClearColor(0x06141D, 1)
  el.appendChild(renderer.domElement)

  scene = new THREE.Scene()
  scene.background = new THREE.Color('#06141D')

  camera = new THREE.PerspectiveCamera(45, w / h, 1, 200000)
  camera.position.set(22000, -32000, 30000)

  // 暗色光照突出山势 (PBR 材质需较强光照)
  scene.add(new THREE.AmbientLight(0x88aabb, 1.8))
  const dir = new THREE.DirectionalLight(0xffffff, 2.2)
  dir.position.set(30000, -40000, 50000)
  scene.add(dir)
  scene.add(new THREE.HemisphereLight(0x99aabb, 0x223344, 0.8))

  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.autoRotate = true
  controls.autoRotateSpeed = 0.5
  controls.target.set(0, 0, 6000)
  controls.update()

  // 模型经纬度单位是度, 数值小(~0.3), 直接用
  const loader = new GLTFLoader()
  loader.load('/models/terrain.glb',
    (gltf) => {
      model = gltf.scene
      // 用 Basic 材质让顶点色直接显示 (河道蓝明显), 不依赖光照
      model.traverse((child) => {
        if (child.isMesh) {
          child.material = new THREE.MeshBasicMaterial({ vertexColors: true })
        }
      })
      scene.add(model)
      console.log('[Terrain3D] 模型加载成功')
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
