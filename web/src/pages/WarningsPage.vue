<template>
  <Topbar title="预警处置" subtitle="预警与告警实时监控，按紧急程度排序。" />
  <div class="sub-tabs">
    <button :class="{ active: subTab === 'current' }" @click="subTab = 'current'">当前预警</button>
    <button :class="{ active: subTab === 'history' }" @click="subTab = 'history'">历史告警</button>
  </div>

  <!-- 当前预警 -->
  <template v-if="subTab === 'current'">
    <div class="command-grid">
      <article class="panel">
        <div class="panel-head"><h2>当前预警与告警</h2><span>{{ totalCount }} 条</span></div>
        <div class="panel-body">
          <div class="risk-list">
            <div v-if="allItems.length === 0" class="empty-state">当前无预警和告警 🎉</div>
            <div class="risk-item" v-for="w in allItems" :key="w.id">
              <div class="risk-row"><b>{{ w.name }}</b><span :class="['badge', levelBadgeClass(w.level)]">{{ levelLabel(w.level) }}</span></div>
              <p>{{ w.message }}</p>
            </div>
          </div>
        </div>
      </article>
      <article class="panel">
        <div class="panel-head"><h2>处置建议</h2><span>FloodMind</span></div>
        <div class="panel-body">
          <div class="suggest-list">
            <div class="suggest-item" v-for="s in suggestions" :key="s.text">
              <span class="suggest-dot" :style="{background:s.color,boxShadow:'0 0 0 0 '+s.color}"></span>
              <span class="suggest-text">{{ s.text }}</span>
            </div>
          </div>
        </div>
      </article>
    </div>
  </template>

  <!-- 历史告警 -->
  <template v-if="subTab === 'history'">
    <section class="command-grid">
      <article class="panel">
        <div class="panel-head">
          <h2>活动告警</h2>
          <span>未解除 {{ activeAlerts.length }} 条</span>
        </div>
        <div class="panel-body">
          <div v-if="alertLoading" class="welcome-msg"><p>加载中...</p></div>
          <div v-else-if="activeAlerts.length === 0" class="welcome-msg">
            <p>当前无活动告警 🎉</p>
          </div>
          <div v-else class="risk-list">
            <div v-for="a in activeAlerts" :key="a.id" :class="['risk-item', levelBadgeClass(a.level)]">
              <div class="risk-row">
                <b>{{ a.title }}</b>
                <span :class="['badge', levelBadgeClass(a.level)]">{{ levelLabel(a.level) }}</span>
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
          <div v-if="alertLoading" class="welcome-msg"><p>加载中...</p></div>
          <div v-else-if="historyAlerts.length === 0" class="welcome-msg">
            <p>暂无历史告警</p>
          </div>
          <div v-else class="risk-list">
            <div v-for="a in historyAlerts" :key="a.id" class="risk-item">
              <div class="risk-row">
                <b>{{ a.title }}</b>
                <span :class="['badge', levelBadgeClass(a.level)]">{{ levelLabel(a.level) }}</span>
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
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import Topbar from '../components/Topbar.vue'
import { api } from '../api'
import { levelLabel, levelBadgeClass, levelSeverity } from '../utils/warningLevel'

const subTab = ref('current')

// ── 当前预警 ──
const allItems = ref([])
const suggestions = ref([])
const totalCount = ref(0)

let pollTimer = null

async function loadWarnings() {
  try {
    const data = await api.getWarnings('00106')
    const warnings = data.warnings || []
    const alerts = data.alerts || []
    allItems.value = [...warnings, ...alerts].sort((a, b) =>
      levelSeverity(a.level) - levelSeverity(b.level)
    )
    totalCount.value = allItems.value.length

    const firstWarn = warnings[0]
    if (firstWarn) {
      try {
        const lv = firstWarn.level
        const lvMap = { '蓝色预警': 'blue', '黄色预警': 'yellow', '橙色预警': 'orange', '红色预警': 'red' }
        const code = lvMap[lv] || 'yellow'
        const isFlow = firstWarn.name?.includes('流量') || firstWarn.unit === 'm³/s'
        const metric = isFlow ? 'flow' : 'level'
        const wl = isFlow ? 0 : (firstWarn.value != null ? firstWarn.value : 0)
        const vf = isFlow ? (firstWarn.value != null ? firstWarn.value : 0) : 0
        let d
        try {
          d = await api.getDisposalAgent(firstWarn.station_code, code, metric, wl, vf)
        } catch {
          d = await api.getDisposal(firstWarn.station_code, code, metric)
        }
        suggestions.value = (d.suggestions || []).map(s => ({
          text: typeof s === 'string' ? s : s.text || s,
          color: 'var(--water)'
        }))
      } catch {
        suggestions.value = [{ text: '处置建议加载失败', color: 'var(--muted)' }]
      }
    } else if (alerts.length > 0) {
      suggestions.value = [{ text: '当前存在系统告警，请检查数据缓存和设备状态。', color: 'var(--accent)' }]
    } else {
      suggestions.value = [{ text: '当前无预警和告警，系统运行正常。', color: 'var(--ok)' }]
    }
  } catch (e) {
    console.error('Failed to load warnings:', e)
    allItems.value = [{ id: 'err', name: '数据加载失败', level: '错误', message: e.message || '未知错误' }]
    totalCount.value = 1
  }
}

// ── 历史告警 ──
const alertLoading = ref(false)
const activeAlerts = ref([])
const historyAlerts = ref([])

async function loadAlerts() {
  alertLoading.value = true
  try {
    const [active, history] = await Promise.all([
      api.getActiveAlerts().catch(() => ({ alerts: [] })),
      api.getAlertHistory().catch(() => ({ alerts: [] })),
    ])
    activeAlerts.value = active.alerts || []
    const activeIds = new Set(activeAlerts.value.map(a => a.id))
    historyAlerts.value = (history.alerts || []).filter(a => !activeIds.has(a.id))
  } catch (e) {
    console.error('[warnings] loadAlerts failed', e)
  } finally {
    alertLoading.value = false
  }
}

async function ack(id) {
  try {
    await api.acknowledgeAlert(id)
    await loadAlerts()
  } catch (e) {
    alert('确认失败：' + e.message)
  }
}

async function resolve(id) {
  try {
    await api.resolveAlert(id, '人工解除')
    await loadAlerts()
  } catch (e) {
    alert('解除失败：' + e.message)
  }
}

function fmtTime(ts) {
  if (!ts) return '—'
  const d = new Date(ts * 1000)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

onMounted(() => {
  loadWarnings()
  pollTimer = setInterval(loadWarnings, 30000)
})
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.sub-tabs {
  display: flex;
  gap: 2px;
  margin-bottom: var(--gap, 10px);
  padding: 4px;
  border: 1px solid var(--edge);
  border-radius: 4px;
  clip-path: var(--clip);
  background: var(--glass);
  backdrop-filter: blur(14px);
  background-attachment: fixed;
}
.sub-tabs button {
  flex: 1;
  min-height: 32px;
  border: 0;
  border-radius: 3px;
  background: transparent;
  color: var(--muted);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: .08em;
  cursor: pointer;
  transition: all .15s;
}
.sub-tabs button:hover { color: #fff; }
.sub-tabs button.active {
  color: #fff;
  background: var(--chip);
  text-shadow: 0 0 10px rgba(30, 144, 255, .5);
}

.suggest-list { display: grid; gap: 14px; }
.suggest-item { display: flex; align-items: flex-start; gap: 12px; }
.suggest-dot {
  flex-shrink: 0; width: 10px; height: 10px; margin-top: 5px;
  border-radius: 50%; opacity: .85;
  animation: pulse-dot 2s ease-in-out infinite;
}
.suggest-text { color: var(--ink); font-size: 16px; line-height: 1.6; }
.empty-state { padding: 40px 0; text-align: center; color: var(--muted); font-size: 13px; }
.welcome-msg { padding: 40px 0; text-align: center; color: var(--muted); font-size: 13px; }
@keyframes pulse-dot {
  0%, 100% { box-shadow: 0 0 0 5px rgba(14,165,233,.18); }
  50% { box-shadow: 0 0 0 10px transparent; }
}

.postmortem {
  margin-top: 10px;
  padding: 8px 12px;
  border-radius: 6px;
  background: var(--chip);
  border-left: 3px solid var(--primary);
  min-width: 0;
  overflow-wrap: break-word;
}
.postmortem-label {
  font-size: 10px;
  font-weight: 700;
  color: #fff;
  text-transform: uppercase;
  letter-spacing: .06em;
}
.postmortem p {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--ink-2);
  overflow-wrap: break-word;
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
  margin-top: 12px;
}
.alert-actions .btn {
  min-height: 28px;
  padding: 0 12px;
  font-size: 12px;
}

.risk-item.danger { border-left: 4px solid var(--danger); }
.risk-item.warn { border-left: 4px solid var(--warn); }
.risk-item.ok { border-left: 4px solid var(--ok); }

.risk-row b {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.risk-row .badge {
  flex-shrink: 0;
  white-space: nowrap;
}
.risk-item > p {
  overflow-wrap: break-word;
}
</style>
