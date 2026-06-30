<template>
  <section class="overview-layout">
    <!-- 左侧：2x2 指标卡 -->
    <div class="tiles-col">
      <article class="tile river" @click="openStage('最新监测水位', 'tile')">
        <div class="tile-label">最新监测水位</div>
        <div class="tile-value"><b>{{ waterLevel }}</b><span>m</span></div>
        <div :class="['tile-note', waterLevelNoteClass]">{{ waterLevelNote }}</div>
      </article>
      <article class="tile" @click="openStage('最新监测流量', 'tile')">
        <div class="tile-label">最新监测流量</div>
        <div class="tile-value"><b>{{ waterFlow }}</b><span>m³/s</span></div>
        <div class="tile-note">{{ flowChangeNote }}</div>
      </article>
      <article class="tile moss" @click="openStage('模型可信度', 'tile')">
        <div class="tile-label">模型可信度</div>
        <div class="tile-value"><b>{{ modelConfidence }}</b></div>
        <div class="tile-note ok">Chronos 时序预测</div>
      </article>
      <article class="tile amber" @click="openStage('待处置预警', 'tile')">
        <div class="tile-label">待处置预警</div>
        <div class="tile-value"><b>{{ pendingWarnings }}</b><span>项</span></div>
        <div class="tile-note">{{ warningNote }}</div>
      </article>
    </div>

    <!-- 右侧：预警与告警 -->
    <article class="panel">
      <div class="panel-head"><h2>预警与告警</h2><span>共 {{ displayWarnings.length }} 条</span></div>
      <div class="panel-body">
        <div v-if="warningInsight" class="forecast-insight warning-insight">
          <span class="insight-label">AI · 预警解读</span>
          <p>{{ warningInsight }}</p>
        </div>
        <div class="risk-list">
          <div class="risk-item" v-for="w in displayWarnings" :key="w.id" @click="openDrawer(w)">
            <div class="risk-row"><b>{{ w.name }}</b><span :class="['badge', levelBadgeClass(w.level)]">{{ levelLabel(w.level) }}</span></div>
            <p>{{ w.message }}</p>
          </div>
        </div>
      </div>
    </article>
  </section>

  <!-- 底部：预报图表 -->
  <section class="bottom-grid">
    <article class="panel combined-panel">
      <div class="panel-head"><h2>历史数据与模型预报联合展示</h2><span>近 24h → 未来 12h</span></div>
      <div class="panel-body combined-card">
        <div class="trend-main">
          <div class="chart-wrap">
            <div v-if="forecastInsight" class="forecast-insight insight-above-chart">
              <span class="insight-label">AI · 预报解读</span>
              <p>{{ forecastInsight }}</p>
            </div>
            <div class="combined-chart">
              <TrendChart :history="trendHistory" :forecast="trendForecast" unit="流量 (m³/s)" />
            </div>
            <div class="chart-legend">
              <span><i class="legend-hist"></i>实测</span>
              <span><i class="legend-fc"></i>预报</span>
              <span><i class="legend-now"></i>当前</span>
            </div>
          </div>
          <div class="forecast-summary combined-summary">
            <div class="mini-stat"><span>最高流量</span><b>{{ historyMaxFlow }}<small> m³/s</small></b></div>
            <div class="mini-stat"><span>平均流量</span><b>{{ historyAvgFlow }}<small> m³/s</small></b></div>
            <div class="mini-stat peak"><span>预报峰值</span><b>{{ forecastPeak }}<small> m³/s</small></b></div>
            <div class="mini-stat"><span>峰现时间</span><b>{{ forecastPeakTime }}</b></div>
          </div>
        </div>
      </div>
    </article>
  </section>

  <Teleport to="body">
    <div v-if="stageVisible" class="stage-modal" @click.self="closeStage">
      <div class="stage-card">
        <div class="stage-head"><h2>{{ stageTitle }}</h2><button class="stage-close" @click="closeStage">关闭</button></div>
        <div class="stage-body"><p style="color:var(--muted);text-align:center;padding:60px 0;">{{ stageTitle }} — 全屏详情（数据接入后展示完整内容）</p></div>
      </div>
    </div>

    <StationDrawer :visible="drawerVisible" :station="drawerStation" @close="closeDrawer" />
  </Teleport>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, computed } from 'vue'
import TrendChart from '../components/TrendChart.vue'
import StationDrawer from '../components/StationDrawer.vue'
import { api } from '../api'
import { levelLabel, levelBadgeClass, levelSeverity } from '../utils/warningLevel'

const waterLevel = ref('—')
const waterFlow = ref('—')
const modelConfidence = ref('—')
const pendingWarnings = ref('—')
const warningNote = ref('加载中...')
const waterLevelNote = ref('加载中...')
const waterLevelNoteClass = ref('')
const flowChangeNote = ref('加载中...')
const forecastPeak = ref('—')
const forecastPeakTime = ref('—')
const forecastInsight = ref('')
const historyMaxFlow = ref('—')
const historyAvgFlow = ref('—')
const stageVisible = ref(false)
const stageTitle = ref('')

const drawerVisible = ref(false)
const drawerStation = ref({})
function openDrawer(w) {
  drawerStation.value = {
    name: w.name,
    code: w.code || w.id || '',
    level: w.level,
    flow: w.flow,
    status: w.level ? levelLabel(w.level) : '—',
    badgeClass: levelBadgeClass(w.level),
    detail: w.message || '',
  }
  drawerVisible.value = true
}
function closeDrawer() { drawerVisible.value = false }

const trendHistory = ref([])
const trendForecast = ref([])

const warnings = ref([
  { id: 'loading', name: '数据加载中...', level: '—', message: '正在获取预警数据' },
])

const displayWarnings = computed(() => {
  const all = [...warnings.value]
  all.sort((a, b) => levelSeverity(a.level) - levelSeverity(b.level))
  return all
})

const warningInsight = computed(() => {
  const items = displayWarnings.value
  if (!items.length) return ''
  const real = items.filter(w => w.id !== 'loading' && w.id !== 'ok')
  if (!real.length) return '当前无 active 预警，各站点运行状态正常，可继续按现有巡检周期执行。'
  const names = [...new Set(real.map(w => w.name))].slice(0, 2).join('、')
  const levels = [...new Set(real.map(w => levelLabel(w.level)))].filter(Boolean)
  const levelText = levels.slice(0, 2).join('、')
  return `当前共有 ${real.length} 条预警，涉及 ${names}${levelText ? '，级别为 ' + levelText : ''}。建议优先复核最近一条并采取预置处置流程。`
})

const WARNING_LEVEL = 35.1

let pollTimer = null

async function refreshData() {
  console.log('[overview] refreshData start')
  try {
    const [flowData, warnData, chartData] = await Promise.all([
      api.getFlowRaw('00106', 'FD000489923695'),
      api.getWarnings('00106').catch(() => ({ warnings: [], total: 0 })),
      api.getAlignedChart('00106', 'virtualFlow').catch(() => ({ history: [], forecast: [] })),
    ])

    pendingWarnings.value = warnData.total || '0'
    const allWarnings = [...(warnData.warnings || []), ...(warnData.alerts || [])]
    if (allWarnings.length > 0) {
      warnings.value = allWarnings.map(w => ({ id: w.id, name: w.name, level: w.level || w.level_name || '', message: w.message }))
      warningNote.value = [...new Set(allWarnings.map(w => w.name))].join('、')
    } else {
      warnings.value = [{ id: 'ok', name: '系统运行正常', level: '正常', message: '所有站点数据正常，无预警信息。' }]
      warningNote.value = '系统运行正常'
    }

    const items = flowData?.data || []
    if (items.length > 0) {
      const latestWL = items.find(i => i.waterLevel != null)
      const level = latestWL?.waterLevel
      if (level !== null && level !== undefined) {
        waterLevel.value = level.toFixed(2)
        const dist = WARNING_LEVEL - level
        waterLevelNote.value = dist > 0 ? `距警戒水位 ${dist.toFixed(2)}m` : `超警戒水位 ${Math.abs(dist).toFixed(2)}m`
        waterLevelNoteClass.value = dist <= 2 ? 'danger' : ''
      } else {
        waterLevel.value = '—'
        waterLevelNote.value = '暂无水位数据'
        modelConfidence.value = '—'
      }

      const latestFlow = items.find(i => i.virtualFlow != null || i.waterFlow != null)
      const wf = latestFlow?.virtualFlow ?? latestFlow?.waterFlow
      if (wf !== null && wf !== undefined) {
        waterFlow.value = wf.toFixed(0)
        flowChangeNote.value = '已更新'
      } else {
        waterFlow.value = '—'
        flowChangeNote.value = '该站无流量数据'
      }

      trendHistory.value = chartData.history || []
      if (trendHistory.value.length) {
        const flowVals = trendHistory.value.map(d => d.y).filter(v => typeof v === 'number')
        historyMaxFlow.value = flowVals.length ? Math.max(...flowVals).toFixed(0) : '—'
        historyAvgFlow.value = flowVals.length ? Math.round(flowVals.reduce((a, b) => a + b, 0) / flowVals.length).toLocaleString() : '—'
      }

      trendForecast.value = chartData.forecast || []
      if (trendForecast.value.length) {
        const peak = Math.max(...trendForecast.value.map(d => d.y).filter(v => typeof v === 'number'))
        forecastPeak.value = peak ? peak.toFixed(0) : '—'
        forecastPeakTime.value = trendForecast.value.find(d => d.y === peak)?.t || '—'
      }
      computeModelConfidence()

      api.getForecastInterpret('00106', 'virtualFlow').then(d => {
        forecastInsight.value = d.interpretation || ''
      }).catch(() => {})

      saveCache()
    }
    console.log('[overview] refreshData done')
  } catch (e) {
    console.error('[overview] Data fetch failed:', e)
    waterLevelNote.value = '数据获取失败'
    flowChangeNote.value = '数据获取失败'
  }
}

const CACHE_KEY = 'overview_data_cache'

function saveCache() {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify({
      waterLevel: waterLevel.value,
      waterFlow: waterFlow.value,
      modelConfidence: modelConfidence.value,
      pendingWarnings: pendingWarnings.value,
      warningNote: warningNote.value,
      waterLevelNote: waterLevelNote.value,
      waterLevelNoteClass: waterLevelNoteClass.value,
      flowChangeNote: flowChangeNote.value,
      forecastPeak: forecastPeak.value,
      forecastPeakTime: forecastPeakTime.value,
      historyMaxFlow: historyMaxFlow.value,
      historyAvgFlow: historyAvgFlow.value,
      trendHistory: trendHistory.value,
      trendForecast: trendForecast.value,
      warnings: warnings.value,
      ts: Date.now()
    }))
  } catch (e) { console.warn('[overview] saveCache failed', e) }
}

function loadCache() {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return false
    const data = JSON.parse(raw)
    if (!data.ts || Date.now() - data.ts > 120000) return false
    waterLevel.value = data.waterLevel ?? waterLevel.value
    waterFlow.value = data.waterFlow ?? waterFlow.value
    modelConfidence.value = data.modelConfidence ?? modelConfidence.value
    pendingWarnings.value = data.pendingWarnings ?? pendingWarnings.value
    warningNote.value = data.warningNote ?? warningNote.value
    waterLevelNote.value = data.waterLevelNote ?? waterLevelNote.value
    waterLevelNoteClass.value = data.waterLevelNoteClass ?? waterLevelNoteClass.value
    flowChangeNote.value = data.flowChangeNote ?? flowChangeNote.value
    forecastPeak.value = data.forecastPeak ?? forecastPeak.value
    forecastPeakTime.value = data.forecastPeakTime ?? forecastPeakTime.value
    historyMaxFlow.value = data.historyMaxFlow ?? historyMaxFlow.value
    historyAvgFlow.value = data.historyAvgFlow ?? historyAvgFlow.value
    if (data.trendHistory) trendHistory.value = data.trendHistory
    if (data.trendForecast) trendForecast.value = data.trendForecast
    if (data.warnings) warnings.value = data.warnings
    console.log('[overview] cache loaded')
    return true
  } catch (e) { console.warn('[overview] loadCache failed', e); return false }
}

onMounted(() => {
  loadCache()
  refreshData()
  pollTimer = setInterval(refreshData, 60000)
})
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer); closeStage() })

function computeModelConfidence() {
  const vals = trendForecast.value.map(d => d.y).filter(v => typeof v === 'number' && !isNaN(v))
  if (vals.length < 2) {
    modelConfidence.value = '—'
    return
  }
  const mean = vals.reduce((a, b) => a + b, 0) / vals.length
  if (mean === 0) {
    modelConfidence.value = '—'
    return
  }
  const range = Math.max(...vals) - Math.min(...vals)
  const conf = 0.95 - (range / mean) * 2
  modelConfidence.value = Math.max(0.5, Math.min(0.99, conf)).toFixed(2)
}

function openStage(title) {
  stageTitle.value = title
  stageVisible.value = true
}

function closeStage() {
  stageVisible.value = false
}
</script>

<style scoped>
.overview-layout {
  min-height: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: var(--gap, 10px);
}

.tiles-col {
  display: grid;
  grid-template-columns: repeat(2, 152px);
  grid-template-rows: 1fr 1fr;
  gap: var(--gap, 10px);
  min-height: 0;
}

.tiles-col .tile {
  min-height: 0;
}

.forecast-insight {
  margin-top: 0;
  border: 0;
  border-left: 3px solid var(--accent);
  border-radius: var(--radius-md);
  padding: 10px 14px;
  background: var(--chip);
  display: block;
}
.insight-label {
  display: block;
  font-family: var(--mono);
  font-size: 10.5px;
  font-weight: 700;
  color: #fff;
  letter-spacing: .08em;
  margin-bottom: 5px;
}
.forecast-insight p {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.55;
  color: var(--ink);
  overflow-wrap: break-word;
}
.forecast-insight.insight-above-chart {
  width: 100%;
  margin-bottom: 6px;
  flex-shrink: 0;
  box-sizing: border-box;
}
.forecast-insight.warning-insight {
  margin-bottom: 8px;
  background: var(--chip);
  border-color: transparent;
  border-left-color: var(--primary);
}
.forecast-insight.warning-insight .insight-label { color: #fff; }

.trend-main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 128px;
  gap: 12px;
  min-height: 0;
}
.trend-main .forecast-summary { grid-template-columns: 1fr; }
.trend-main .mini-stat { padding: 6px 8px; }
.trend-main .mini-stat b { font-size: 15px; }
.chart-wrap {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.chart-wrap .combined-chart {
  flex: 1;
  height: auto;
  min-height: 0;
}
.chart-legend {
  display: flex;
  align-items: center;
  gap: 14px;
  min-height: 0;
  padding-top: 4px;
}
.chart-legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--ink);
}
.chart-legend i {
  width: 14px;
  height: 3px;
  border-radius: 2px;
}
.legend-hist { background: var(--water); }
.legend-fc { background: var(--accent); background-image: repeating-linear-gradient(90deg, var(--accent) 0 5px, transparent 5px 9px); }
.legend-now { background: var(--accent); opacity: .5; }
.mini-stat.peak b { color: #fff; }
</style>
