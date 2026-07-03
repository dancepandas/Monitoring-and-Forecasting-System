<template>
  <Topbar title="预警处置" subtitle="实时监控 · 按紧急程度排序" />
  <div class="command-grid">
    <!-- 左：未解决 -->
    <article class="panel">
      <div class="panel-head"><h2>未解决</h2><span>{{ unresolved.length }} 条</span></div>
      <div class="panel-body">
        <div class="risk-list">
          <!-- 处置建议（有预警时优先展示） -->
          <div v-if="suggestions.length" class="risk-item suggestion-item">
            <div class="risk-row"><b>FloodMind · 处置建议</b></div>
            <ol class="suggest-inline">
              <li v-for="(s, i) in suggestions" :key="i">{{ s.text }}</li>
            </ol>
          </div>
          <div v-if="unresolved.length === 0" class="empty-state">暂无未解决的预警或告警</div>
          <div v-for="item in unresolved" :key="item._key" :class="['risk-item', levelBadgeClass(item.level)]">
            <div class="risk-row">
              <b>{{ item.name || item.title }}</b>
              <span :class="['badge', levelBadgeClass(item.level)]">{{ levelLabel(item.level) }}</span>
            </div>
            <p v-html="renderMessage(item.message)"></p>
            <div v-if="item._type === 'alert'" class="alert-meta">
              <span>站点 {{ item.station_code || '—' }}</span>
              <span>触发 {{ fmtTime(item.triggered_at) }}</span>
              <span v-if="item.notify_count > 0">已推送 {{ item.notify_count }} 次</span>
            </div>
            <div v-if="item._type === 'alert'" class="alert-actions">
              <template v-if="acknowledgedIds.has(item.id) || item.acknowledged">
                <span class="acked-badge">✓ 已确认</span>
                <button class="btn sm primary" :disabled="processing.has(item.id)" @click="resolve(item.id)">
                  {{ processing.has(item.id) ? '解除中...' : '解除' }}
                </button>
              </template>
              <template v-else>
                <button class="btn sm" :disabled="processing.has(item.id)" @click="askConfirm(item)">
                  确认
                </button>
                <button class="btn sm primary" :disabled="processing.has(item.id)" @click="resolve(item.id)">
                  {{ processing.has(item.id) ? '解除中...' : '解除' }}
                </button>
              </template>
              <span v-if="feedback.id === item.id" class="feedback-flash">{{ feedback.text }}</span>
            </div>
          </div>
        </div>
      </div>
    </article>

    <!-- 右：已解决 -->
    <article class="panel">
      <div class="panel-head"><h2>已解决</h2><span>{{ resolved.length }} 条</span></div>
      <div class="panel-body">
        <div class="risk-list">
          <div v-if="resolved.length === 0" class="empty-state">暂无已解决的告警</div>
          <div v-for="item in resolved" :key="item._key" class="risk-item">
            <div class="risk-row">
              <b>{{ item.title }}</b>
              <span class="risk-meta">{{ fmtTime(item.resolved_at) }}</span>
            </div>
            <p v-html="renderMessage(item.message)"></p>
            <div class="alert-meta">
              <span>站点 {{ item.station_code || '—' }}</span>
              <span>触发 {{ fmtTime(item.triggered_at) }}</span>
            </div>
            <div v-if="item.postmortem" class="postmortem">
              <span class="pm-label">AI 复盘</span>
              <p>{{ item.postmortem }}</p>
            </div>
          </div>
        </div>
      </div>
    </article>
  </div>

  <!-- 确认告警弹窗 -->
  <Teleport to="body">
    <div v-if="confirmTarget" class="modal-overlay" @click.self="confirmTarget = null">
      <div class="confirm-modal">
        <h3>确认告警</h3>
        <p class="confirm-detail"><b>{{ confirmTarget.title }}</b> — {{ confirmTarget.message }}</p>
        <div class="confirm-explain">
          <p>确认后，系统将<em>停止对该告警的重复推送</em>。相同类型的告警在 <strong>30 分钟</strong>内不会再次通知。此操作仅表示您已知悉该告警，不会影响告警的解除流程。</p>
        </div>
        <div class="confirm-actions">
          <button class="btn" @click="confirmTarget = null">取消</button>
          <button class="btn primary" @click="doAck">确认已知悉</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import Topbar from '../components/Topbar.vue'
import { api, ALL_STATION_CODES } from '../api'
import { levelLabel, levelBadgeClass, levelSeverity } from '../utils/warningLevel'

const warnings = ref([])
const suggestions = ref([])
const activeAlerts = ref([])
const historyAlerts = ref([])
const processing = ref(new Set())
const feedback = ref({ id: '', text: '' })
const confirmTarget = ref(null)
const acknowledgedIds = ref(new Set())

let pollTimer = null

const unresolved = computed(() => {
  const w = warnings.value.map(w => ({ ...w, _key: 'w-' + w.id, _type: 'warning' }))
  const a = activeAlerts.value.map(a => ({ ...a, _key: 'a-' + a.id, _type: 'alert' }))
  return [...w, ...a].sort((x, y) => levelSeverity(x.level) - levelSeverity(y.level))
})

const resolved = computed(() => {
  return historyAlerts.value.map(a => ({ ...a, _key: 'h-' + a.id }))
})

async function loadWarnings() {
  try {
    const data = await api.getWarnings(ALL_STATION_CODES)
    warnings.value = (data.warnings || []).sort((a, b) => levelSeverity(a.level) - levelSeverity(b.level))

    const firstWarn = warnings.value[0]
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
        try { d = await api.getDisposalAgent(firstWarn.station_code, code, metric, wl, vf) }
        catch { d = await api.getDisposal(firstWarn.station_code, code, metric) }
        suggestions.value = (d.suggestions || []).map(s => ({
          text: typeof s === 'string' ? s : s.text || s,
        }))
      } catch {
        suggestions.value = []
      }
    } else {
      suggestions.value = []
    }
  } catch (e) {
    console.error('Failed to load warnings:', e)
    warnings.value = [{ id: 'err', name: '数据加载失败', level: '错误', message: e.message || '未知错误' }]
  }
}

async function loadAlerts() {
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
  }
}

async function refreshAll() { await Promise.all([loadWarnings(), loadAlerts()]) }

async function ack(id) {
  processing.value.add(id)
  feedback.value = { id, text: '' }
  try {
    await api.acknowledgeAlert(id)
    acknowledgedIds.value.add(id)
    feedback.value = { id, text: '✓ 已确认' }
    setTimeout(() => { feedback.value = { id: '', text: '' } }, 1500)
    await loadAlerts()
  } catch (e) {
    feedback.value = { id, text: '确认失败' }
    setTimeout(() => { feedback.value = { id: '', text: '' } }, 2000)
  } finally {
    processing.value.delete(id)
  }
}

function askConfirm(item) {
  confirmTarget.value = item
}

async function doAck() {
  const item = confirmTarget.value
  if (!item) return
  confirmTarget.value = null
  await ack(item.id)
}

async function resolve(id) {
  processing.value.add(id)
  feedback.value = { id, text: '' }
  try {
    await api.resolveAlert(id, '人工解除')
    feedback.value = { id, text: '✓ 已解除' }
    setTimeout(() => { feedback.value = { id: '', text: '' } }, 1500)
    await loadAlerts()
  } catch (e) {
    feedback.value = { id, text: '解除失败' }
    setTimeout(() => { feedback.value = { id: '', text: '' } }, 2000)
  } finally {
    processing.value.delete(id)
  }
}

function fmtTime(ts) {
  if (!ts) return '—'
  const d = new Date(ts * 1000)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function renderMessage(text) {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
}

onMounted(() => { refreshAll(); pollTimer = setInterval(refreshAll, 30000) })
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })
</script>

<style scoped>
.command-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--gap, 10px);
  min-height: 0;
}

.risk-meta {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--muted);
  flex-shrink: 0;
}

.empty-state {
  padding: 40px 0;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
}

/* 处置建议（嵌入 risk-item 风格） */
.suggestion-item {
  border-left: 3px solid var(--accent);
}
.suggest-inline {
  margin: 6px 0 0;
  padding: 0 0 0 16px;
  display: grid;
  gap: 4px;
}
.suggest-inline li {
  font-size: 12px;
  color: var(--ink);
  line-height: 1.5;
}
.suggest-inline li::marker {
  color: var(--accent);
  font-weight: 700;
}

/* 告警操作 */
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
  margin-top: 8px;
}
.btn.sm:disabled {
  opacity: .5;
  cursor: not-allowed;
}

.feedback-flash {
  font-size: 11px;
  font-weight: 600;
  color: var(--ok);
  animation: flash-in .25s ease;
}
@keyframes flash-in {
  from { opacity: 0; transform: translateX(-4px); }
  to   { opacity: 1; transform: translateX(0); }
}

/* AI 复盘 */
.postmortem {
  margin-top: 8px;
  padding: 8px 12px;
  border-radius: 4px;
  background: rgba(255, 255, 255, .03);
  border-left: 3px solid var(--primary);
}
.pm-label {
  font-size: 10px;
  font-weight: 700;
  color: var(--primary);
  text-transform: uppercase;
  letter-spacing: .05em;
}
.postmortem p {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--ink-2);
}

/* 已确认标记 */
.acked-badge {
  font-size: 11px;
  font-weight: 600;
  color: var(--ok);
  padding: 2px 0;
}

/* 确认弹窗 */
.modal-overlay {
  position: fixed; inset: 0; z-index: 200;
  background: rgba(0, 0, 0, .5);
  backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
  padding: 40px;
}
.confirm-modal {
  width: 420px;
  background: var(--glass-deep);
  backdrop-filter: blur(18px);
  border: 1px solid var(--edge);
  border-radius: 8px;
  padding: 24px;
  box-shadow: 0 16px 48px rgba(0,0,0,.3);
}
.confirm-modal h3 {
  margin: 0;
  font-size: 16px;
  color: #fff;
}
.confirm-detail {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--ink-2);
  line-height: 1.5;
}
.confirm-explain {
  margin: 14px 0 0;
  padding: 12px;
  border-radius: 4px;
  background: var(--chip);
  font-size: 12px;
  color: var(--ink);
  line-height: 1.7;
}
.confirm-explain em { color: var(--accent); font-style: normal; }
.confirm-explain strong { color: #fff; }
.confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 18px;
}
</style>
