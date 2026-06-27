<template>
  <Topbar title="视频巡检" subtitle="仙桃站采集快照 · 最近10条" />
  <section class="video-page">
    <div v-if="snapshots.length === 0" class="empty">暂无视频快照，等待 collector 采集...</div>
    <div class="video-grid">
      <div class="video-card" v-for="(s, i) in snapshots" :key="s.time" @click="openVideo(s)">
        <video v-if="s.live_address" :ref="el => setRef(i, el)" muted autoplay playsinline class="video-player"></video>
        <div v-else class="video-placeholder">无信号</div>
        <div class="video-label">{{ fmtTime(s.time) }}</div>
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

const snapshots = ref([])
const stageVisible = ref(false)
const stageTitle = ref('')
const stageEl = ref(null)
const videoRefs = {}
const players = []
let stagePlayer = null
let timer = null

function setRef(i, el) { if (el) videoRefs[i] = el }

function fmtTime(ts) {
  if (!ts) return '—'
  const d = new Date(ts.replace(' ', 'T'))
  if (isNaN(d.getTime())) return ts
  return `${d.getMonth()+1}/${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}`
}

function destroyAll() {
  players.forEach(p => { try { p.destroy() } catch(e){} })
  players.length = 0
}

function initPlayers() {
  destroyAll()
  nextTick(() => {
    snapshots.value.forEach((s, i) => {
      const el = videoRefs[i]
      if (!el || !s.live_address) return
      try {
        const p = flvjs.createPlayer({ type: 'flv', url: s.live_address, isLive: true })
        p.attachMediaElement(el)
        p.load()
        p.play().catch(() => {})
        players.push(p)
      } catch(e) { console.warn('flv init:', e) }
    })
  })
}

watch(snapshots, () => initPlayers(), { deep: true })

function openVideo(s) {
  stageTitle.value = s.time
  stageVisible.value = true
  nextTick(() => {
    if (stagePlayer) { try { stagePlayer.destroy() } catch(e){} }
    const el = stageEl.value
    if (!el || !s.live_address) return
    try {
      stagePlayer = flvjs.createPlayer({ type: 'flv', url: s.live_address, isLive: true })
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
    const data = await api.getVideoSnapshots('00106', 10)
    snapshots.value = data.snapshots || []
  } catch(e) { console.error('snapshots:', e) }
}

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
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow-y: auto;
  padding: 0 16px 20px;
  box-sizing: border-box;
}
.video-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  align-content: start;
}
.video-card {
  cursor: pointer;
  border-radius: 8px;
  overflow: hidden;
  background: #111;
  position: relative;
}
.video-card .video-player {
  width: 100%;
  aspect-ratio: 16 / 10;
  object-fit: contain;
  display: block;
  background: #000;
}
.video-placeholder {
  color: #cbd5e1;
  font-size: 13px;
  aspect-ratio: 16 / 10;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #000;
}
.video-label {
  position: absolute;
  bottom: 8px;
  left: 8px;
  font-size: 11px;
  color: #fff;
  background: rgba(0, 0, 0, 0.6);
  padding: 2px 8px;
  border-radius: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: calc(100% - 16px);
}
.empty {
  padding: 60px 16px;
  text-align: center;
  color: var(--muted, #999);
}
</style>
