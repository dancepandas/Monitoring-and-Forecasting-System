<template>
  <Topbar title="预警处置" subtitle="预警与告警实时监控，按紧急程度排序。" />
  <div class="command-grid">
    <article class="panel">
      <div class="panel-head"><h2>当前预警与告警</h2><span>{{ totalCount }} 条</span></div>
      <div class="panel-body">
        <div class="risk-list">
          <div class="risk-item" v-for="w in allItems" :key="w.id">
            <div class="risk-row"><b>{{ w.name }}</b><span :class="['badge', badgeCls(w)]">{{ w.level }}</span></div>
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
import { ref, computed, onMounted } from 'vue'
import Topbar from '../components/Topbar.vue'
import { api } from '../api'

const allItems = ref([])
const suggestions = ref([])
const totalCount = ref(0)

const levelOrder = { '红色': 0, '橙色': 1, '黄色': 2, '蓝色预警': 3, '提示': 4, '正常': 5 }

function badgeCls(w) {
  const m = { '红色': 'danger', '橙色': 'warn', '黄色': 'warn', '蓝色预警': 'ok', '提示': 'ok', '正常': 'ok' }
  return m[w.level] || ''
}

async function loadWarnings() {
  try {
    const data = await api.getWarnings('00106,00107,00108')
    const warnings = data.warnings || []
    const alerts = data.alerts || []
    allItems.value = [...warnings, ...alerts].sort((a, b) =>
      (levelOrder[a.level] ?? 99) - (levelOrder[b.level] ?? 99)
    )
    totalCount.value = allItems.value.length

    // 取第一条预警生成处置建议
    const firstWarn = warnings[0]
    if (firstWarn) {
      try {
        const lv = firstWarn.level
        const lvMap = { '蓝色预警': 'blue', '黄色预警': 'yellow', '橙色预警': 'orange', '红色预警': 'red' }
        const code = lvMap[lv] || 'yellow'
        const d = await api.getDisposal(firstWarn.station_code, code, 'level')
        suggestions.value = (d.suggestions || []).map(s => ({
          text: typeof s === 'string' ? s : s.text || s,
          color: 'var(--river)'
        }))
      } catch {
        suggestions.value = [{ text: '处置建议加载失败', color: 'var(--muted)' }]
      }
    } else if (alerts.length > 0) {
      suggestions.value = [{ text: '当前存在系统告警，请检查数据缓存和设备状态。', color: 'var(--amber)' }]
    } else {
      suggestions.value = [{ text: '当前无预警和告警，系统运行正常。', color: 'var(--moss)' }]
    }
  } catch (e) {
    console.error('Failed to load warnings:', e)
    allItems.value = [{ id: 'err', name: '数据加载失败', level: '错误', message: e.message || '未知错误' }]
    totalCount.value = 1
  }
}

onMounted(loadWarnings)
</script>
<style scoped>
.suggest-list { display: grid; gap: 14px; }
.suggest-item { display: flex; align-items: flex-start; gap: 12px; }
.suggest-dot {
  flex-shrink: 0; width: 10px; height: 10px; margin-top: 7px;
  border-radius: 50%; opacity: .85;
  animation: pulse-dot 2s ease-in-out infinite;
}
.suggest-text { color: var(--ink); font-size: 16px; line-height: 1.6; }
@keyframes pulse-dot {
  0%, 100% { box-shadow: 0 0 0 5px rgba(200,111,76,.18); }
  50% { box-shadow: 0 0 0 10px transparent; }
}
</style>
