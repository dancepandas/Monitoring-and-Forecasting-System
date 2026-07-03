import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { STATIONS } from '../stations'

// 自动轮播间隔 / 点击钉选时长
const ROTATE_MS = 30000
const PIN_MS = 120000

// 站点轮播：单一数据源，驱动地图高亮与单站数据面板
export const useRotationStore = defineStore('rotation', () => {
  const currentIndex = ref(0)
  const mode = ref('auto')          // 'auto' | 'pinned'
  const pinnedUntil = ref(0)        // 钉选到期时间戳；auto 时为 0

  let rotateTimer = null
  let pinTimer = null

  const current = computed(() => STATIONS[currentIndex.value] || STATIONS[0])
  const isPinned = computed(() => mode.value === 'pinned')

  function clearRotate() { if (rotateTimer) { clearInterval(rotateTimer); rotateTimer = null } }
  function clearPin() { if (pinTimer) { clearTimeout(pinTimer); pinTimer = null } }

  function next() {
    currentIndex.value = (currentIndex.value + 1) % STATIONS.length
  }

  function startRotate() {
    clearRotate()
    rotateTimer = setInterval(() => {
      if (mode.value === 'auto') next()
    }, ROTATE_MS)
  }

  // 用户点击地图某站 → 钉选该站 PIN_MS；到期切回 auto 并前进到下一站
  function pinStation(code) {
    const idx = STATIONS.findIndex(s => s.code === code)
    if (idx < 0) return
    currentIndex.value = idx
    mode.value = 'pinned'
    pinnedUntil.value = Date.now() + PIN_MS
    clearRotate()
    clearPin()
    pinTimer = setTimeout(() => {
      mode.value = 'auto'
      pinnedUntil.value = 0
      next()                 // 从钉选站的下一站恢复轮播
      startRotate()
    }, PIN_MS)
  }

  // Overview 挂载时调用
  function start() {
    clearPin()
    mode.value = 'auto'
    pinnedUntil.value = 0
    currentIndex.value = 0
    startRotate()
  }

  // Overview 卸载时调用
  function stop() {
    clearRotate()
    clearPin()
  }

  // 用户点击地图空白处 → 取消钉选，恢复轮播
  function unpinStation() {
    if (mode.value !== 'pinned') return
    mode.value = 'auto'
    pinnedUntil.value = 0
    clearPin()
    startRotate()
  }

  return { currentIndex, mode, pinnedUntil, current, isPinned, start, stop, next, pinStation, unpinStation }
})
