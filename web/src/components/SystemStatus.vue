<template>
  <div class="sys-status" :class="statusClass" v-if="status" @click="checkNow" :title="status.summary">
    <span class="ss-dot"></span>
    <span class="ss-text">{{ label }}</span>
    <span class="ss-time">{{ clockText }}</span>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api } from '../api'

const status = ref(null)
const now = ref(Date.now())
let statusTimer = null
let clockTimer = null

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

const clockText = computed(() => {
  const d = new Date(now.value)
  const pad = n => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
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

onMounted(() => {
  fetchStatus()
  statusTimer = setInterval(fetchStatus, 60000)
  clockTimer = setInterval(() => { now.value = Date.now() }, 1000)
})

onUnmounted(() => {
  if (statusTimer) clearInterval(statusTimer)
  if (clockTimer) clearInterval(clockTimer)
})
</script>

<style scoped>
.sys-status {
  display: flex; align-items: center; gap: 6px;
  min-height: 32px; padding: 0 12px; border-radius: 999px;
  font-size: 12px; cursor: pointer;
  user-select: none; transition: all .15s;
  border: 1px solid var(--line);
  background: rgba(255,255,255,.5);
  color: var(--ink-2-dark);
}
.sys-status:hover { border-color: var(--water); }
.sys-status.ok { border-color: var(--ok-soft); color: var(--ok); }
.sys-status.warn { border-color: var(--warn); color: var(--warn); }
.sys-status.crit { border-color: var(--danger); color: var(--danger); }
.ss-dot {
  width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
  background: currentColor;
}
.ok .ss-dot { background: var(--ok); animation: none; }
.warn .ss-dot { background: var(--warn); animation: ssPulse 3s ease-in-out infinite; }
.crit .ss-dot { background: var(--danger); animation: ssPulse 1.5s ease-in-out infinite; }
@keyframes ssPulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.ss-text { font-weight: 600; white-space: nowrap; }
.ss-time { color: var(--muted-dark); font-size: 10px; white-space: nowrap; }
</style>
