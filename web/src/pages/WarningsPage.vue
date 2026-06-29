<template>
  <Topbar title="预警处置" subtitle="预警与告警实时监控，按紧急程度排序。" />
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
<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import Topbar from '../components/Topbar.vue'
import { api } from '../api'
import { levelLabel, levelBadgeClass, levelSeverity } from '../utils/warningLevel'

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

    // 取第一条预警生成处置建议（优先用 Agent 动态生成）
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

onMounted(() => {
  loadWarnings()
  pollTimer = setInterval(loadWarnings, 30000)
})
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>
<style scoped>
.suggest-list { display: grid; gap: 14px; }
.suggest-item { display: flex; align-items: flex-start; gap: 12px; }
.suggest-dot {
  flex-shrink: 0; width: 10px; height: 10px; margin-top: 5px;
  border-radius: 50%; opacity: .85;
  animation: pulse-dot 2s ease-in-out infinite;
}
.suggest-text { color: var(--ink); font-size: 16px; line-height: 1.6; }
.empty-state { padding: 40px 0; text-align: center; color: var(--muted); font-size: 13px; }
@keyframes pulse-dot {
  0%, 100% { box-shadow: 0 0 0 5px rgba(14,165,233,.18); }
  50% { box-shadow: 0 0 0 10px transparent; }
}
</style>
