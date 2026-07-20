<template>
  <Topbar title="视频巡检" subtitle="四站采集快照 · 按站点分类 · 最近10条" />
  <section class="video-page">
    <div v-if="stations.length === 0" class="empty">
      <div class="empty-icon">📡</div>
      <p>暂无视频快照</p>
      <small>等待 collector 采集或检查 gateway 是否已重启</small>
    </div>
    <div v-for="st in stations" :key="st.station_code" class="station-group">
      <h3 class="station-title">{{ st.station_name }}</h3>
      <div class="video-grid">
        <div class="video-card" v-for="(s, i) in st.snapshots" :key="st.station_code + '-' + i" @click="openVideo(s, st.station_name)">
          <video v-if="s.live_address" :ref="el => setRef(st.station_code, i, el)" muted autoplay playsinline class="video-player" poster="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg'/>"></video>
          <div v-else class="video-placeholder">无信号</div>
          <div v-if="s.live_address && errorKeys[st.station_code + '-' + i]" class="video-error" @click.stop>
            <span class="ve-icon">⚠️</span>
            <span class="ve-text">视频流不可用</span>
            <button class="ve-retry" @click.stop="retryCard(st.station_code, i)">重试</button>
          </div>
          <div class="video-label">
            <span class="vl-time">{{ fmtTime(s.time) }}</span>
            <span :class="['vl-status', s.status === 'online' ? 'online' : 'offline']">{{ s.status === 'online' ? '在线' : '离线' }}</span>
          </div>
        </div>
      </div>
    </div>
  </section>

  <Teleport to="body">
    <div v-if="stageVisible" class="stage-modal" @click.self="closeStage">
      <div class="stage-card">
        <div class="stage-head"><h2>{{ stageTitle }}</h2><button class="stage-close" @click="closeStage">关闭</button></div>
        <div class="stage-body" style="padding:0;background:#000;">
          <video ref="stageEl" muted autoplay playsinline controls style="width:100%;max-height:70vh;background:#000;"></video>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import flvjs from 'flv.js'
import Topbar from '../components/Topbar.vue'
import { api } from '../api'

const stations = ref([])
const stageVisible = ref(false)
const stageTitle = ref('')
const stageEl = ref(null)
const videoRefs = {}
const players = new Map()      // key → flv player，便于单卡重试
const errorKeys = ref({})      // key → true，记录网络失败的卡片
let stagePlayer = null
let timer = null

function setRef(code, i, el) {
  if (el) videoRefs[`${code}-${i}`] = el
}

function _makePlayer(el, url, key) {
  const p = flvjs.createPlayer({ type: 'flv', url, isLive: true, hasAudio: false })
  // 仅网络错误（404/不可达）提示用户；音频编码等良性错误静默
  p.on(flvjs.Events.ERROR, (errorType) => {
    if (errorType === flvjs.ErrorTypes.NETWORK_ERROR) {
      errorKeys.value = { ...errorKeys.value, [key]: true }
    }
  })
  p.attachMediaElement(el)
  p.load()
  p.play().catch(() => {})
  return p
}

function retryCard(code, i) {
  const key = `${code}-${i}`
  const old = players.get(key)
  if (old) { try { old.destroy() } catch (e) {} }
  players.delete(key)
  const { [key]: _omit, ...rest } = errorKeys.value
  errorKeys.value = rest
  nextTick(() => {
    const el = videoRefs[key]
    const st = stations.value.find(s => s.station_code === code)
    const snap = st && st.snapshots[i]
    if (!el || !snap || !snap.live_address) return
    try {
      players.set(key, _makePlayer(el, snap.live_address, key))
    } catch (e) { console.warn('flv retry:', e) }
  })
}

function fmtTime(ts) {
  if (!ts) return '—'
  const d = new Date(ts.replace(' ', 'T'))
  if (isNaN(d.getTime())) return ts
  return `${d.getMonth()+1}/${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}`
}

function destroyAll() {
  players.forEach(p => { try { p.destroy() } catch (e) {} })
  players.clear()
}

function initPlayers() {
  destroyAll()
  nextTick(() => {
    for (const st of stations.value) {
      (st.snapshots || []).forEach((s, i) => {
        const key = `${st.station_code}-${i}`
        const el = videoRefs[key]
        if (!el || !s.live_address) return
        try {
          players.set(key, _makePlayer(el, s.live_address, key))
        } catch (e) { console.warn('flv init:', e) }
      })
    }
  })
}

function openVideo(s, stationName) {
  stageTitle.value = `${stationName} · ${s.time}`
  stageVisible.value = true
  nextTick(() => {
    if (stagePlayer) { try { stagePlayer.destroy() } catch (e) {} }
    const el = stageEl.value
    if (!el || !s.live_address) return
    try {
      stagePlayer = flvjs.createPlayer({ type: 'flv', url: s.live_address, isLive: true, hasAudio: false })
      stagePlayer.on(flvjs.Events.ERROR, () => {})  // 大屏弹窗错误不提示，用户可关闭
      stagePlayer.attachMediaElement(el)
      stagePlayer.load()
      stagePlayer.play().catch(() => {})
    } catch(e) { console.warn('stage flv:', e) }
  })
}

function closeStage() {
  if (stagePlayer) { try { stagePlayer.destroy() } catch(e){}; stagePlayer = null }
  stageVisible.value = false
}

async function load() {
  try {
    console.log('[devices] fetching all video snapshots...')
    // 先试新 API（__all__ 分组格式）
    let data = await api.getAllVideoSnapshots(10).catch(() => null)
    if (data && data.stations) {
      console.log('[devices] all-stations format, count:', data.stations.length)
      stations.value = data.stations
      return
    }
    // 回退：逐个站点拉取
    console.log('[devices] falling back to per-station fetch')
    const codes = ['00125', '00230', '00231', '00234']
    const names = { '00125': '郴州', '00230': '郴州-坳上', '00231': '郴州-鸡嘴桥下游', '00234': '郴州-燕泉河' }
    const results = []
    for (const code of codes) {
      try {
        const d = await api.getVideoSnapshots(code, 10)
        if (d.snapshots && d.snapshots.length) {
          results.push({
            station_code: code,
            station_name: names[code] || code,
            snapshots: d.snapshots,
            count: d.snapshots.length,
          })
        }
      } catch(e) { console.warn('[devices] failed for', code, e) }
    }
    stations.value = results
  } catch(e) {
    console.error('[devices] snapshots failed:', e)
  }
}

watch(stations, () => initPlayers(), { deep: true })

onMounted(() => {
  load()
  timer = setInterval(load, 60000)
})

onUnmounted(() => {
  clearInterval(timer)
  destroyAll()
  closeStage()
})
</script>

<style scoped>
.video-page {
  min-height: 0;
  overflow-y: auto;
  padding: 0 16px 20px;
  box-sizing: border-box;
}

.station-group {
  margin-bottom: 24px;
}

.station-title {
  margin: 0 0 8px 4px;
  font-size: 14px;
  font-weight: 600;
  color: var(--ink);
}

/* 显式覆盖 components.css 全局样式 */
.video-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  grid-template-rows: auto;
  height: auto;
  min-height: 0;
  overflow: visible;
  gap: 10px;
  padding: 0;
}

.video-card {
  cursor: pointer;
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg-2);
  border: 1px solid var(--edge);
  transition: border-color .15s;
  position: relative;
  min-height: 0;
}

.video-card:hover { border-color: var(--primary); }

.video-card .video-player {
  width: 100%;
  height: 200px;
  object-fit: cover;
  display: block;
  background: #000;
  position: static;
  border-radius: 0;
}

.video-placeholder {
  color: var(--muted);
  font-size: 13px;
  height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-2);
  position: static;
  border-radius: 0;
}

.video-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 5px 8px;
  background: rgba(0, 0, 0, 0.7);
}

.vl-time {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-2);
}

.vl-status {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 3px;
}

.vl-status.online { color: var(--ok); background: rgba(34,197,94,.12); }
.vl-status.offline { color: var(--muted); background: rgba(148,163,184,.08); }

.empty {
  padding: 80px 16px;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
}
.empty-icon { font-size: 40px; margin-bottom: 12px; }
.empty p { margin: 0; font-size: 16px; color: var(--ink-2); }
.empty small { display: block; margin-top: 6px; font-size: 12px; color: var(--muted); }

/* stage modal */
.stage-modal {
  position: fixed; inset: 0; z-index: 200;
  background: rgba(0, 0, 0, .6);
  backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
  padding: 40px;
}
.stage-card {
  width: min(900px, calc(100vw - 80px));
  background: var(--glass-deep);
  border: 1px solid var(--edge);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 16px 48px rgba(0,0,0,.4);
}
.stage-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid var(--line);
}
.stage-head h2 { margin: 0; font-size: 15px; color: var(--ink); }
.stage-close {
  min-height: 28px; padding: 0 14px;
  border: 1px solid var(--edge); border-radius: 4px;
  background: transparent; color: var(--muted);
  font-size: 12px; cursor: pointer; transition: all .15s;
}
.stage-close:hover { color: var(--ink); border-color: var(--ink-2); }
</style>
