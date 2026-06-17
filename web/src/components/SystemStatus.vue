<template>
  <div class="sys-status" :class="statusClass" v-if="status" @click="checkNow" :title="status.summary">
    <span class="ss-dot"></span>
    <span class="ss-text">{{ label }}</span>
    <span class="ss-time" v-if="status.checked_at">{{ fmtTime(status.checked_at) }}</span>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api } from '../api'

const status = ref(null)
let timer = null

const statusClass = computed(() => {
  const d = status.value?.diagnosis
  return d === 'healthy' ? 'ok' : d === 'degraded' || d === 'warning' ? 'warn' : 'crit'
})

const label = computed(() => {
  const d = status.value?.diagnosis
  if (!d) return '检查中...'
  const m = {
    healthy: '系统正常',
    degraded: '部分异常',
    partial_failure: '数据异常',
    global_failure: '系统故障',
    unknown: '状态未知'
  }
  return m[d] || d
})

async function fetchStatus() {
  try {
    status.value = await api.getSystemStatus()
  } catch { /* offline */ }
}

async function checkNow() {
  try {
    await api.triggerSystemCheck()
    await fetchStatus()
  } catch { /* ignore */ }
}

function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

onMounted(() => {
  fetchStatus()
  timer = setInterval(fetchStatus, 60000)
})

onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.sys-status {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 12px; border-radius: 999px;
  font-size: 11px; cursor: pointer;
  user-select: none; transition: all .15s;
  border: 1px solid var(--line);
  background: rgba(255,255,255,.5);
}
.sys-status:hover { border-color: var(--river); }
.sys-status.ok { border-color: var(--moss-soft); color: var(--moss); }
.sys-status.warn { border-color: var(--amber); color: var(--amber); }
.sys-status.crit { border-color: var(--clay); color: var(--clay); }
.ss-dot {
  width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
  background: currentColor;
}
.ok .ss-dot { background: var(--moss); animation: none; }
.warn .ss-dot { background: var(--amber); animation: ssPulse 3s ease-in-out infinite; }
.crit .ss-dot { background: var(--clay); animation: ssPulse 1.5s ease-in-out infinite; }
@keyframes ssPulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.ss-text { font-weight: 600; white-space: nowrap; }
.ss-time { color: var(--muted); font-size: 10px; white-space: nowrap; }
</style>
