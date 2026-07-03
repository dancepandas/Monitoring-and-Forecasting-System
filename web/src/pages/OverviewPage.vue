<template>
  <section class="overview-layout">
    <!-- 左侧：4 指标卡纵向堆叠 -->
    <div class="tiles-col">
      <article class="tile river" @click="openMonitor('水位')">
        <span class="station-chip">{{ rotation.current.name }}</span>
        <div class="tile-label">最新监测水位</div>
        <div class="tile-value"><b>{{ waterLevel }}</b><span>m</span></div>
        <div :class="['tile-note', waterLevelNoteClass]">{{ waterLevelNote }}</div>
      </article>
      <article class="tile" @click="openMonitor('流量')">
        <span class="station-chip">{{ rotation.current.name }}</span>
        <div class="tile-label">最新监测流量</div>
        <div class="tile-value"><b>{{ waterFlow }}</b><span>m³/s</span></div>
        <div class="tile-note">{{ flowChangeNote }}</div>
      </article>
      <article class="tile moss" @click="openStage('模型可信度', 'tile')">
        <span class="station-chip">{{ rotation.current.name }}</span>
        <div class="tile-label">模型可信度</div>
        <div class="tile-value"><b>{{ modelConfidence }}</b></div>
        <div class="tile-note ok">Chronos 时序预测</div>
      </article>
      <article class="tile amber" @click="goWarnings">
        <span class="station-chip">全部站点</span>
        <div class="tile-label">待处置预警</div>
        <div class="tile-value"><b>{{ pendingWarnings }}</b><span>项</span></div>
        <div class="tile-note">点击查看详情</div>
      </article>
    </div>

    <!-- 中间留空：透出 Cesium 3D 地图 -->
    <div class="map-void"></div>

    <!-- 右侧：预警与告警 -->
    <article class="panel">
      <div class="panel-head"><span class="station-chip">全部站点</span><h2>预警与告警</h2><span>共 {{ displayWarnings.length }} 条</span></div>
      <div class="panel-body">
        <div v-if="warningInsight" class="forecast-insight warning-insight">
          <span class="insight-label">AI · 预警解读</span>
          <p>{{ warningInsight }}</p>
        </div>
        <div class="risk-list">
          <div class="risk-item" v-for="w in displayWarnings" :key="w.id" @click="openDrawer(w)">
            <div class="risk-row"><b>{{ w.name }}</b><span :class="['badge', levelBadgeClass(w.level)]">{{ levelLabel(w.level) }}</span></div>
            <p v-html="renderMessage(w.message)"></p>
          </div>
        </div>
      </div>
    </article>
  </section>

  <!-- 底部：预报图表 -->
  <section class="bottom-grid">
    <article class="panel combined-panel">
      <div class="panel-head"><span class="station-chip">{{ rotation.current.name }}</span><h2>历史数据与模型预报联合展示</h2><span>近 24h → 未来 12h</span></div>
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

  <!-- 水位/流量监测弹窗 -->
  <Teleport to="body">
    <div v-if="monitorVisible" class="monitor-overlay" @click.self="closeMonitor">
      <div class="monitor-card">
        <div class="monitor-head">
          <h2>{{ rotation.current.name }} · {{ monitorType }}监测</h2>
          <button class="monitor-close" @click="closeMonitor">关闭</button>
        </div>
        <div class="monitor-body">
          <!-- 视频区 -->
          <div class="monitor-video">
            <video v-if="videoUrl" ref="monitorVideoEl" muted autoplay playsinline class="video-frame"></video>
            <div v-else class="video-placeholder">
              <span>暂无监测视频画面</span>
            </div>
          </div>
          <!-- 双图：水位 + 流量 10h -->
          <div class="monitor-charts">
            <div class="monitor-chart-panel">
              <div class="mcp-head">
                <h3>近 10 小时水位过程</h3>
                <span class="mcp-legend"><i class="leg-hist"></i>实测</span>
              </div>
              <div class="mcp-body">
                <div class="mcp-chart"><TrendChart :history="levelHistory" :forecast="[]" unit="水位 (m)" /></div>
                <div class="mcp-stats">
                  <div class="mcp-stat"><span>最大值</span><b>{{ levelMax }}<small> m</small></b></div>
                  <div class="mcp-stat"><span>最小值</span><b>{{ levelMin }}<small> m</small></b></div>
                  <div class="mcp-stat current"><span>当前</span><b>{{ waterLevel }}<small> m</small></b></div>
                </div>
              </div>
            </div>
            <div class="monitor-chart-panel">
              <div class="mcp-head">
                <h3>近 10 小时流量过程</h3>
                <span class="mcp-legend"><i class="leg-hist"></i>实测</span>
              </div>
              <div class="mcp-body">
                <div class="mcp-chart"><TrendChart :history="flowHistory" :forecast="[]" unit="流量 (m³/s)" /></div>
                <div class="mcp-stats">
                  <div class="mcp-stat"><span>最大值</span><b>{{ flowMax }}<small> m³/s</small></b></div>
                  <div class="mcp-stat"><span>最小值</span><b>{{ flowMin }}<small> m³/s</small></b></div>
                  <div class="mcp-stat current"><span>当前</span><b>{{ waterFlow }}<small> m³/s</small></b></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>

  <Teleport to="body">
    <StationDrawer :visible="drawerVisible" :station="drawerStation" @close="closeDrawer" />
  </Teleport>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import flvjs from 'flv.js'
import TrendChart from '../components/TrendChart.vue'
import StationDrawer from '../components/StationDrawer.vue'
import { api, ALL_STATION_CODES } from '../api'
import { useRotationStore } from '../store/rotation'
import { levelLabel, levelBadgeClass, levelSeverity } from '../utils/warningLevel'

const router = useRouter()
const rotation = useRotationStore()

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

// ── 监测弹窗 ──
const monitorVisible = ref(false)
const monitorType = ref('')
const videoUrl = ref('')
const monitorVideoEl = ref(null)
let monitorPlayer = null
const levelHistory = ref([])
const flowHistory = ref([])

const levelMax = computed(() => fmtMax(levelHistory.value, 'm'))
const levelMin = computed(() => fmtMin(levelHistory.value, 'm'))
const flowMax = computed(() => fmtMax(flowHistory.value, 'm³/s'))
const flowMin = computed(() => fmtMin(flowHistory.value, 'm³/s'))

function fmtMax(arr, unit) {
  const vals = arr.map(d => d.y).filter(v => typeof v === 'number')
  return vals.length ? Math.max(...vals).toFixed(2) : '—'
}
function fmtMin(arr, unit) {
  const vals = arr.map(d => d.y).filter(v => typeof v === 'number')
  return vals.length ? Math.min(...vals).toFixed(2) : '—'
}

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

function renderMessage(text) {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
}

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

const warningLevel = ref(0)   // 当前站点警戒水位（红色阈值），由 warning-standards 动态获取

let pollTimer = null

async function refreshData() {
  console.log('[overview] refreshData start')
  try {
    const st = rotation.current
    const [flowData, warnData, chartData, stdData] = await Promise.all([
      api.getFlowRaw(st.code, st.device),
      api.getWarnings(ALL_STATION_CODES).catch(() => ({ warnings: [], total: 0 })),
      api.getAlignedChart(st.code, 'virtualFlow').catch(() => ({ history: [], forecast: [] })),
      api.getWarningStandards().catch(() => ({})),
    ])

    // 取当前站点警戒水位（红色阈值），驱动"距/超警戒水位"提示
    const std = stdData?.stations?.[st.code]?.level || stdData?.defaults?.level || {}
    warningLevel.value = std.red || std.orange || 0

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
        const wl = warningLevel.value
        if (wl > 0) {
          const dist = wl - level
          waterLevelNote.value = dist > 0 ? `距警戒水位 ${dist.toFixed(2)}m` : `超警戒水位 ${Math.abs(dist).toFixed(2)}m`
          waterLevelNoteClass.value = dist <= 2 ? 'danger' : ''
        } else {
          waterLevelNote.value = '阈值未配置'
          waterLevelNoteClass.value = ''
        }
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

      api.getForecastInterpret(st.code, 'virtualFlow').then(d => {
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
  rotation.start()
  // 轮播切站时，刷新单站数据（水位/流量/预报图）；汇总数据仍按 60s 轮询
  watch(() => rotation.current.code, () => refreshData())
})
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  rotation.stop()
  closeMonitor()
})

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

function goWarnings() { router.push('/warnings') }

async function openMonitor(type) {
  monitorType.value = type
  monitorVisible.value = true
  const st = rotation.current
  try {
    // 视频源
    const feeds = await api.getVideoFeeds(st.code)
    const online = (feeds.feeds || []).find(f => f.status === 'online' && f.live_address)
    videoUrl.value = online?.live_address || ''
    // 用 flv.js 播放（萤石云返回的是 .flv 实时流，<img>/<video src> 无法直接播放）
    await nextTick()
    if (videoUrl.value && monitorVideoEl.value) {
      if (flvjs.isSupported()) {
        try {
          monitorPlayer = flvjs.createPlayer({ type: 'flv', url: videoUrl.value, isLive: true, hasAudio: false })
          monitorPlayer.on(flvjs.Events.ERROR, () => {})  // 弹窗错误静默，用户可关闭
          monitorPlayer.attachMediaElement(monitorVideoEl.value)
          monitorPlayer.load()
          monitorPlayer.play().catch(() => {})
        } catch (e) { console.warn('monitor flv:', e) }
      }
    }
  } catch { videoUrl.value = '' }

  // 近 10 小时历史数据
  try {
    const end = new Date().toISOString()
    const begin = new Date(Date.now() - 10 * 3600000).toISOString()
    const data = await api.getFlowRaw(st.code, st.device, begin, end)
    const items = data.data || []
    levelHistory.value = []
    flowHistory.value = []
    for (const item of items) {
      const t = item.time ? new Date(item.time).getTime() : Date.now()
      if (isNaN(t)) continue
      if (item.waterLevel != null) levelHistory.value.push({ t, y: item.waterLevel })
      const vf = item.virtualFlow ?? item.waterFlow
      if (vf != null) flowHistory.value.push({ t, y: vf })
    }
  } catch { levelHistory.value = []; flowHistory.value = [] }
}

function closeMonitor() {
  if (monitorPlayer) { try { monitorPlayer.destroy() } catch (e) {}; monitorPlayer = null }
  monitorVisible.value = false
  videoUrl.value = ''
  levelHistory.value = []
  flowHistory.value = []
}
</script>

<style scoped>
/* 站点标签芯片：单站面板显示当前轮播站名，汇总面板显示"全部站点" */
.station-chip {
  position: absolute;
  top: 6px;
  right: 8px;
  z-index: 2;
  padding: 2px 9px;
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: .03em;
  color: var(--ink-2);
  background: var(--chip);
  border: 1px solid var(--edge);
  border-radius: 999px;
  pointer-events: none;
  white-space: nowrap;
}
/* 面板头内的芯片放到左侧（计数 span 在右侧，对称） */
.panel-head .station-chip {
  top: 50%;
  left: 16px;
  right: auto;
  transform: translateY(-50%);
}

.overview-layout {
  min-height: 0;
  display: grid;
  grid-template-columns: auto 1fr minmax(420px, 500px);
  grid-template-rows: minmax(0, 1fr);
  gap: 28px;
}

.tiles-col {
  display: grid;
  grid-template-columns: 302px;
  grid-template-rows: repeat(4, auto);
  gap: 0;
  align-content: space-between;
  min-height: 0;
  height: 100%;
}

.tiles-col .tile {
  min-height: 0;
  /* 左面板：右侧（近中心）透明 → 左侧（远中心）渐变不透明 */
  background: linear-gradient(to left,
    rgba(14, 42, 78, .00) 0%,
    rgba(14, 42, 78, .10) 22%,
    rgba(14, 42, 78, .35) 52%,
    rgba(14, 42, 78, .65) 78%,
    rgba(14, 42, 78, .88) 100%);
}

.map-void {
  min-height: 0;
  /* 透明 — 透出 Cesium 3D 地图 */
}

.overview-layout > .panel {
  height: 100%;
  min-height: 0;
  /* 右面板：左侧（近中心）透明 → 右侧（远中心）渐变不透明 */
  background: linear-gradient(to right,
    rgba(14, 42, 78, .00) 0%,
    rgba(14, 42, 78, .10) 22%,
    rgba(14, 42, 78, .35) 52%,
    rgba(14, 42, 78, .65) 78%,
    rgba(14, 42, 78, .88) 100%);
}

/* 底部预报面板：上侧（近中心）透明 → 下侧（远中心）渐变不透明 */
.bottom-grid .panel {
  background: linear-gradient(to bottom,
    rgba(14, 42, 78, .00) 0%,
    rgba(14, 42, 78, .10) 22%,
    rgba(14, 42, 78, .35) 52%,
    rgba(14, 42, 78, .65) 78%,
    rgba(14, 42, 78, .88) 100%);
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

/* ===== 监测视频弹窗 ===== */
.monitor-overlay {
  position: fixed; inset: 0; z-index: 150;
  background: rgba(0,0,0,.55);
  backdrop-filter: blur(6px);
  display: flex; align-items: center; justify-content: center;
  padding: 40px;
}
.monitor-card {
  width: min(960px, calc(100vw - 80px));
  max-height: 90vh;
  background: var(--glass-deep);
  backdrop-filter: blur(20px);
  border: 1px solid var(--edge);
  border-radius: 8px;
  display: flex; flex-direction: column;
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(0,0,0,.4);
}
.monitor-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
}
.monitor-head h2 { margin: 0; font-size: 16px; color: #fff; }
.monitor-close {
  min-height: 28px; padding: 0 14px;
  border: 1px solid var(--edge); border-radius: 4px;
  background: transparent; color: var(--muted);
  font-size: 12px; cursor: pointer; transition: all .15s;
}
.monitor-close:hover { color: #fff; border-color: var(--ink-2); }

.monitor-body {
  flex: 1; overflow-y: auto; min-height: 0;
  display: flex; flex-direction: column; gap: 12px;
  padding: 16px 20px;
}
.monitor-video {
  flex-shrink: 0;
  aspect-ratio: 16/9;
  background: #000;
  border-radius: 4px;
  overflow: hidden;
  display: flex; align-items: center; justify-content: center;
}
.video-frame { width: 100%; height: 100%; object-fit: contain; }
.video-placeholder {
  color: var(--muted); font-size: 14px;
}
.monitor-charts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  min-height: 0;
  flex: 1;
}
.monitor-chart-panel {
  min-height: 0;
  display: flex; flex-direction: column;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: rgba(0,0,0,.15);
  overflow: hidden;
}
.mcp-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
}
.mcp-head h3 { margin: 0; font-size: 12px; font-weight: 600; color: var(--ink); }
.mcp-legend {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11px; color: var(--ink);
}
.mcp-legend i { width: 14px; height: 3px; border-radius: 2px; }
.leg-hist { background: var(--water); }
.mcp-body {
  flex: 1; min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 86px;
  gap: 8px;
  padding: 8px 10px;
}
.mcp-chart { min-height: 0; min-width: 0; }
.mcp-chart :deep(.trend-chart-wrap) { min-height: 140px; }
.mcp-stats {
  display: grid;
  gap: 4px;
  align-content: start;
}
.mcp-stat {
  padding: 5px 7px;
  border-radius: 3px;
  background: var(--chip);
}
.mcp-stat span { display: block; font-size: 10px; color: var(--muted); }
.mcp-stat b { font-size: 13px; color: var(--ink-2); }
.mcp-stat b small { font-size: 10px; color: var(--muted); margin-left: 2px; }
.mcp-stat.current b { color: #fff; }
.mcp-stat.current { background: var(--chip-strong); }
</style>
