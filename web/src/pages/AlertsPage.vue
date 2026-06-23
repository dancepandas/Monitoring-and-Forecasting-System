<template>
  <Topbar
    title="告警中心"
    subtitle="值守引擎自动检测的异常事件与推送记录。"
    action-label="系统诊断"
    @primary-action="runDiagnose"
  />

  <section class="command-grid">
    <article class="panel">
      <div class="panel-head">
        <h2>活动告警</h2>
        <span>未解除 {{ activeAlerts.length }} 条</span>
      </div>
      <div class="panel-body">
        <div v-if="loading" class="welcome-msg"><p>加载中...</p></div>
        <div v-else-if="activeAlerts.length === 0" class="welcome-msg">
          <p>当前无活动告警 🎉</p>
        </div>
        <div v-else class="risk-list">
          <div v-for="a in activeAlerts" :key="a.id" :class="['risk-item', levelClass(a.level)]">
            <div class="risk-row">
              <b>{{ a.title }}</b>
              <span :class="['badge', badgeClass(a.level)]">{{ a.level }}</span>
            </div>
            <p>{{ a.message }}</p>
            <div class="alert-meta">
              <span>站点：{{ a.station_code || '—' }}</span>
              <span>触发：{{ fmtTime(a.triggered_at) }}</span>
              <span v-if="a.notify_count > 0">已推送 {{ a.notify_count }} 次</span>
              <span v-else>未推送</span>
            </div>
            <div class="alert-actions">
              <button class="btn" @click="ack(a.id)">确认</button>
              <button class="btn primary" @click="resolve(a.id)">解除</button>
            </div>
          </div>
        </div>
      </div>
    </article>

    <article class="panel">
      <div class="panel-head">
        <h2>历史告警</h2>
        <span>最近 100 条</span>
      </div>
      <div class="panel-body">
        <div v-if="loading" class="welcome-msg"><p>加载中...</p></div>
        <div v-else-if="historyAlerts.length === 0" class="welcome-msg">
          <p>暂无历史告警</p>
        </div>
        <div v-else class="risk-list">
          <div v-for="a in historyAlerts" :key="a.id" class="risk-item">
            <div class="risk-row">
              <b>{{ a.title }}</b>
              <span :class="['badge', badgeClass(a.level)]">{{ a.level }}</span>
            </div>
            <p>{{ a.message }}</p>
            <div class="alert-meta">
              <span>站点：{{ a.station_code || '—' }}</span>
              <span>触发：{{ fmtTime(a.triggered_at) }}</span>
              <span v-if="a.resolved_at">解除：{{ fmtTime(a.resolved_at) }}</span>
            </div>
            <div v-if="a.postmortem" class="postmortem">
              <span class="postmortem-label">AI 复盘</span>
              <p>{{ a.postmortem }}</p>
            </div>
          </div>
        </div>
      </div>
    </article>
  </section>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import Topbar from '../components/Topbar.vue'
import { api } from '../api'

const loading = ref(false)
const activeAlerts = ref([])
const historyAlerts = ref([])

async function load() {
  loading.value = true
  try {
    const [active, history] = await Promise.all([
      api.getActiveAlerts().catch(() => ({ alerts: [] })),
      api.getAlertHistory().catch(() => ({ alerts: [] })),
    ])
    activeAlerts.value = active.alerts || []
    // 历史告警过滤掉仍在活跃的条目
    const activeIds = new Set(activeAlerts.value.map(a => a.id))
    historyAlerts.value = (history.alerts || []).filter(a => !activeIds.has(a.id))
  } catch (e) {
    console.error('[alerts] load failed', e)
  } finally {
    loading.value = false
  }
}

async function ack(id) {
  try {
    await api.acknowledgeAlert(id)
    await load()
  } catch (e) {
    alert('确认失败：' + e.message)
  }
}

async function resolve(id) {
  try {
    await api.resolveAlert(id, '人工解除')
    await load()
  } catch (e) {
    alert('解除失败：' + e.message)
  }
}

function runDiagnose() {
  window.location.href = '/agent?prompt=执行一次系统诊断并汇报结果'
}

function fmtTime(ts) {
  if (!ts) return '—'
  const d = new Date(ts * 1000)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function levelClass(lv) {
  const m = { '红色': 'danger', '橙色': 'warn', '黄色': 'warn', '蓝色预警': 'ok', '蓝色': 'ok', '预报蓝色预警': 'ok', '预报黄色预警': 'warn', '预报橙色预警': 'warn', '预报红色预警': 'danger', '提示': '' }
  return m[lv] || ''
}

function badgeClass(lv) {
  const m = { '红色': 'danger', '橙色': 'warn', '黄色': 'warn', '蓝色预警': 'ok', '蓝色': 'ok', '预报蓝色预警': 'ok', '预报黄色预警': 'warn', '预报橙色预警': 'warn', '预报红色预警': 'danger', '提示': 'ok' }
  return m[lv] || ''
}

onMounted(() => {
  load()
  const timer = setInterval(load, 30000)
  onUnmounted(() => clearInterval(timer))
})
</script>

<style scoped>
.postmortem {
  margin-top: 10px;
  padding: 8px 12px;
  border-radius: 6px;
  background: rgba(104,119,100,.05);
  border-left: 3px solid var(--moss);
}
.postmortem-label {
  font-size: 10px;
  font-weight: 700;
  color: var(--moss);
  text-transform: uppercase;
  letter-spacing: .06em;
}
.postmortem p {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--ink-2);
}
.alert-meta {
  display: flex;
  gap: 12px;
  margin-top: 6px;
  font-size: 11px;
  color: var(--muted);
  flex-wrap: wrap;
}

.alert-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}

.alert-actions .btn {
  min-height: 28px;
  padding: 0 12px;
  font-size: 12px;
}

.risk-item.danger { border-left: 4px solid var(--clay); }
.risk-item.warn { border-left: 4px solid var(--amber); }
.risk-item.ok { border-left: 4px solid var(--ok); }
</style>
