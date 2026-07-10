<template>
  <section class="overview-hud">
    <!-- 中心 3D 模型背景 -->
    <div class="hud-bg">
      <TerrainModel3D ref="terrainRef" />
    </div>

    <!-- 3D 地形控制面板 -->
    <TerrainPanel @reset-view="terrainRef?.flyToOverview()" />

    <!-- 左上：当前站点 / 平台标识 -->
    <div class="hud-corner hud-top-left">
      <div class="hud-id">
        <span class="hud-id-code">STATION // {{ rotation.current.code || 'CHENZHOU' }}</span>
        <h1 class="hud-id-name">{{ rotation.current.name || '郴州水文监测' }}</h1>
        <span class="hud-id-meta">实时监测中 · {{ currentTime }}</span>
      </div>
    </div>

    <!-- 左侧：四张指标卡 -->
    <div class="hud-col hud-left">
      <article class="hud-card river" @click="openMonitor('水位')">
        <i class="hud-card-icon"></i>
        <span class="hud-card-label">LATEST WATER LEVEL</span>
        <div class="hud-card-value">
          <b>{{ waterLevel }}</b>
          <span class="unit">m</span>
        </div>
        <div :class="['hud-card-note', waterLevelNoteClass]">{{ waterLevelNote }}</div>
        <div class="hud-card-bar"><i :style="{ width: waterLevelPct + '%' }"></i></div>
      </article>

      <article class="hud-card" @click="openMonitor('流量')">
        <i class="hud-card-icon flow"></i>
        <span class="hud-card-label">LATEST DISCHARGE</span>
        <div class="hud-card-value">
          <b>{{ waterFlow }}</b>
          <span class="unit">m³/s</span>
        </div>
        <div class="hud-card-note">{{ flowChangeNote }}</div>
        <div class="hud-card-bar flow-bar"><i :style="{ width: flowPct + '%' }"></i></div>
      </article>

      <article class="hud-card moss" @click="openStage('模型可信度', 'tile')">
        <i class="hud-card-icon model"></i>
        <span class="hud-card-label">MODEL CONFIDENCE</span>
        <div class="hud-card-value">
          <b>{{ modelConfidence }}</b>
        </div>
        <div class="hud-card-note ok">Chronos 时序预测</div>
        <div class="hud-card-bar conf-bar"><i :style="{ width: (Number(modelConfidence) * 100 || 0) + '%' }"></i></div>
      </article>

      <article class="hud-card amber" @click="goWarnings">
        <i class="hud-card-icon alert"></i>
        <span class="hud-card-label">PENDING ALERTS</span>
        <div class="hud-card-value">
          <b>{{ pendingWarnings }}</b>
          <span class="unit">项</span>
        </div>
        <div class="hud-card-note">点击查看详情</div>
        <div class="hud-card-bar alert-bar"><i :style="{ width: Math.min(100, Number(pendingWarnings) * 15) + '%' }"></i></div>
      </article>
    </div>

    <!-- 右侧：预警与告警 -->
    <div class="hud-col hud-right">
      <article class="hud-panel">
        <div class="hud-panel-head">
          <span class="hud-panel-code">WARN // {{ displayWarnings.length }}</span>
          <h2>预警与告警</h2>
          <span class="hud-panel-status">ACTIVE</span>
        </div>
        <div class="hud-panel-body">
          <div v-if="warningInsight" class="hud-insight warning-insight">
            <span class="insight-label">AI · 预警解读</span>
            <p>{{ warningInsight }}</p>
          </div>
          <div class="hud-risk-list">
            <div class="hud-risk-item" v-for="w in displayWarnings" :key="w.id" :class="'level-' + (w.level || 'ok')" @click="openDrawer(w)">
              <div class="risk-row">
                <b>{{ w.name }}</b>
                <span :class="['badge', levelBadgeClass(w.level)]">{{ levelLabel(w.level) }}</span>
              </div>
              <p v-html="renderMessage(w.message)"></p>
            </div>
          </div>
        </div>
      </article>
    </div>

    <!-- 底部：预报图表 -->
    <div class="hud-bottom">
      <article class="hud-panel wide">
        <div class="hud-panel-head">
          <span class="hud-panel-code">FCST // {{ rotation.current.code || 'CHENZHOU' }}</span>
          <h2>历史数据与模型预报联合展示</h2>
          <span class="hud-panel-status">近24h → 未来12h</span>
        </div>
        <div class="hud-panel-body chart-body">
          <div class="chart-main">
            <div v-if="forecastInsight" class="hud-insight insight-above-chart">
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
          <div class="chart-stats">
            <div class="hud-mini-stat">
              <span>最高流量</span>
              <b>{{ historyMaxFlow }}<small> m³/s</small></b>
            </div>
            <div class="hud-mini-stat">
              <span>平均流量</span>
              <b>{{ historyAvgFlow }}<small> m³/s</small></b>
            </div>
            <div class="hud-mini-stat peak">
              <span>预报峰值</span>
              <b>{{ forecastPeak }}<small> m³/s</small></b>
            </div>
            <div class="hud-mini-stat">
              <span>峰现时间</span>
              <b>{{ forecastPeakTime }}</b>
            </div>
          </div>
        </div>
      </article>
    </div>
  </section>

  <!-- 水位/流量监测弹窗 -->
  <Teleport to="body">
    <div v-if="monitorVisible" class="monitor-overlay" @click.self="closeMonitor">
      <div class="monitor-card">
        <div class="monitor-head">
          <div class="monitor-title">
            <span class="monitor-code">MONITOR // {{ rotation.current.code }}</span>
            <h2>{{ rotation.current.name }} · {{ monitorType }}监测</h2>
          </div>
          <button class="monitor-close" @click="closeMonitor">关闭</button>
        </div>
        <div class="monitor-body">
          <div class="monitor-video">
            <video v-if="videoUrl" ref="monitorVideoEl" muted autoplay playsinline class="video-frame"></video>
            <div v-else class="video-placeholder">
              <span>暂无监测视频画面</span>
            </div>
          </div>
          <div class="monitor-charts">
            <div class="monitor-chart-panel">
              <div class="mcp-head">
                <span class="mcp-code">LVL // 10H</span>
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
                <span class="mcp-code">Q // 10H</span>
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
import TerrainModel3D from '../components/TerrainModel3D.vue'
import TerrainPanel from '../components/TerrainPanel.vue'
import { api, ALL_STATION_CODES } from '../api'
import { useRotationStore } from '../store/rotation'
import { levelLabel, levelBadgeClass, levelSeverity } from '../utils/warningLevel'

const router = useRouter()
const rotation = useRotationStore()

const terrainRef = ref(null)

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
const currentTime = ref('')

let clockTimer = null
function updateClock() {
  const d = new Date()
  currentTime.value = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}

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

const waterLevelPct = computed(() => {
  const v = parseFloat(waterLevel.value)
  if (isNaN(v)) return 0
  return Math.min(100, Math.max(0, (v / 200) * 100))
})
const flowPct = computed(() => {
  const v = parseFloat(waterFlow.value)
  if (isNaN(v)) return 0
  return Math.min(100, Math.max(0, (v / 50) * 100))
})

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

const warningLevel = ref(0)
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
  updateClock()
  pollTimer = setInterval(refreshData, 60000)
  clockTimer = setInterval(updateClock, 1000)
  rotation.start()
  watch(() => rotation.current.code, () => refreshData())
})
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (clockTimer) clearInterval(clockTimer)
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
    const feeds = await api.getVideoFeeds(st.code)
    const online = (feeds.feeds || []).find(f => f.status === 'online' && f.live_address)
    videoUrl.value = online?.live_address || ''
    await nextTick()
    if (videoUrl.value && monitorVideoEl.value) {
      if (flvjs.isSupported()) {
        try {
          monitorPlayer = flvjs.createPlayer({ type: 'flv', url: videoUrl.value, isLive: true, hasAudio: false })
          monitorPlayer.on(flvjs.Events.ERROR, () => {})
          monitorPlayer.attachMediaElement(monitorVideoEl.value)
          monitorPlayer.load()
          monitorPlayer.play().catch(() => {})
        } catch (e) { console.warn('monitor flv:', e) }
      }
    }
  } catch { videoUrl.value = '' }

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

function openStage(title, from) {
  // 保持与原逻辑一致：预留扩展
  console.log('[overview] openStage', title, from)
}
</script>

<style scoped>
/* ─────────────────────────────────────────────────────────
   3D 模型仪表盘容器（Material Design 浅色）
   ───────────────────────────────────────────────────────── */
.overview-hud {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-columns: 300px 1fr 340px;
  grid-template-rows: auto 1fr auto;
  grid-template-areas:
    "top    .      right"
    "left   .      right"
    "bottom bottom bottom";
  gap: 16px;
  padding: 16px;
  pointer-events: none;
  overflow: hidden;
}
.overview-hud > * { pointer-events: auto; }

/* ── 3D 模型背景层 ── */
.hud-bg {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: auto;
}
.hud-bg :deep(.terrain-bg) {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

/* ── Material 卡片 / 面板 ── */
.hud-card,
.hud-panel {
  position: relative;
  border: 1px solid var(--line);
  border-radius: var(--radius-xl);
  background: var(--bg-2);
  box-shadow: var(--shadow-1);
  overflow: hidden;
  animation: hud-in .45s ease both;
}
.hud-card::before,
.hud-panel::before {
  content: "";
  position: absolute;
  left: 0; top: 0; right: 0;
  height: 3px;
  background: var(--primary);
}

@keyframes hud-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

/* 顶部站点标识 */
.hud-top-left {
  grid-area: top;
  align-self: start;
}
.hud-id {
  padding: 14px 18px;
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  background: var(--bg-2);
  box-shadow: var(--shadow-1);
  position: relative;
}
.hud-id::before {
  content: "";
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 4px;
  border-radius: var(--radius-lg) 0 0 var(--radius-lg);
  background: var(--primary);
}
.hud-id-code {
  display: block;
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: .04em;
  color: var(--primary);
  margin-bottom: 4px;
}
.hud-id-name {
  margin: 0;
  font-family: var(--display);
  font-size: 20px;
  font-weight: 600;
  color: var(--ink);
}
.hud-id-meta {
  display: block;
  margin-top: 4px;
  font-family: var(--sans);
  font-size: 12px;
  color: var(--muted);
}

/* 左右列布局 */
.hud-col {
  display: grid;
  align-content: center;
  gap: 12px;
  min-height: 0;
}
.hud-left { grid-area: left; }
.hud-right { grid-area: right; align-content: start; }

/* 指标卡 */
.hud-card {
  display: grid;
  grid-template-columns: 1fr auto;
  grid-template-rows: auto auto auto;
  gap: 6px 12px;
  padding: 16px 18px;
  cursor: pointer;
  transition: transform .18s ease, box-shadow .18s ease, background .18s ease;
}
.hud-card:hover {
  transform: translateY(-2px);
  background: var(--bg-3);
  box-shadow: var(--shadow-2);
}
.hud-card-icon {
  grid-column: 2;
  grid-row: 1 / 4;
  align-self: center;
  width: 10px; height: 42px;
  border-radius: var(--radius-sm);
  background: var(--primary);
}
.hud-card-icon.flow { background: var(--water); }
.hud-card-icon.model { background: var(--ok); }
.hud-card-icon.alert { background: var(--orange); }

.hud-card-label {
  grid-column: 1;
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: .02em;
  color: var(--muted);
}
.hud-card-value {
  grid-column: 1;
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.hud-card-value b {
  font-family: var(--display);
  font-size: 32px;
  line-height: 1;
  font-weight: 600;
  color: var(--ink);
}
.hud-card-value .unit {
  font-family: var(--sans);
  font-size: 13px;
  color: var(--muted);
}
.hud-card-note {
  grid-column: 1;
  font-size: 12px;
  color: var(--ink-2);
}
.hud-card-note.danger { color: var(--danger); }
.hud-card-note.ok { color: var(--ok); }

.hud-card-bar {
  grid-column: 1 / -1;
  height: 4px;
  margin-top: 8px;
  border-radius: var(--radius-sm);
  background: var(--bg-4);
  overflow: hidden;
}
.hud-card-bar i {
  display: block;
  height: 100%;
  width: 0%;
  background: var(--primary);
  border-radius: var(--radius-sm);
  transition: width .8s ease;
}
.hud-card-bar.flow-bar i { background: var(--water); }
.hud-card-bar.conf-bar i { background: var(--ok); }
.hud-card-bar.alert-bar i { background: var(--orange); }

/* 右侧面板 */
.hud-panel {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-height: 0;
}
.hud-panel.wide { grid-area: bottom; max-height: 34vh; }
.hud-right .hud-panel { max-height: 86vh; }

.hud-panel-head {
  position: relative;
  min-height: 46px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--line);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  background: var(--bg-3);
}
.hud-panel-head h2 {
  margin: 0;
  font-family: var(--display);
  font-size: 14px;
  font-weight: 600;
  color: var(--ink);
  white-space: nowrap;
}
.hud-panel-code,
.hud-panel-status {
  font-family: var(--sans);
  font-size: 11px;
  color: var(--muted);
}
.hud-panel-status { color: var(--primary); font-weight: 500; }

.hud-panel-body {
  min-height: 0;
  overflow-y: auto;
  padding: 12px;
  background: var(--bg-2);
}

/* 预报解读 */
.hud-insight {
  display: block;
  padding: 12px 14px;
  border-radius: var(--radius-md);
  background: var(--bg-3);
  border-left: 3px solid var(--accent);
  margin-bottom: 10px;
}
.hud-insight.warning-insight { border-left-color: var(--primary); }
.hud-insight .insight-label {
  display: block;
  font-family: var(--sans);
  font-size: 10px;
  font-weight: 600;
  color: var(--accent);
  letter-spacing: .04em;
  text-transform: uppercase;
  margin-bottom: 6px;
}
.hud-insight.warning-insight .insight-label { color: var(--primary); }
.hud-insight p {
  margin: 0;
  font-size: 12px;
  line-height: 1.55;
  color: var(--ink-2);
}
.hud-insight.insight-above-chart { flex-shrink: 0; }

/* 告警列表 */
.hud-risk-list {
  display: grid;
  gap: 8px;
  align-content: start;
}
.hud-risk-item {
  position: relative;
  border: 0;
  border-radius: var(--radius-md);
  padding: 12px 14px;
  background: var(--bg-3);
  cursor: pointer;
  transition: background .15s ease, transform .15s ease;
}
.hud-risk-item::before {
  content: "";
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
  border-radius: var(--radius-md) 0 0 var(--radius-md);
  background: var(--primary);
}
.hud-risk-item:hover {
  background: var(--bg-4);
  transform: translateX(2px);
}
.hud-risk-item.level-danger::before { background: var(--danger); }
.hud-risk-item.level-orange::before { background: var(--orange); }
.hud-risk-item.level-warn::before { background: var(--warn); }
.hud-risk-item.level-ok::before { background: var(--ok); }
.hud-risk-item .risk-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
  gap: 8px;
  min-width: 0;
}
.hud-risk-item .risk-row b {
  font-size: 13px;
  font-weight: 500;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--ink);
}
.hud-risk-item p {
  margin: 0;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.5;
  overflow-wrap: break-word;
}
.badge {
  border-radius: var(--radius-sm);
  padding: 3px 8px;
  font-size: 10px;
  font-weight: 600;
  font-family: var(--sans);
  color: var(--ink-dark);
  background: var(--primary);
  flex-shrink: 0;
  white-space: nowrap;
}
.badge.danger { background: var(--danger); }
.badge.warn { background: var(--orange); }
.badge.yellow { background: var(--warn); }
.badge.ok { background: var(--ok); }

/* 底部图表区 */
.hud-bottom {
  grid-area: bottom;
  min-height: 0;
}
.chart-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 140px;
  gap: 14px;
  min-height: 0;
}
.chart-main {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.chart-main .combined-chart {
  flex: 1;
  min-height: 0;
  border-radius: var(--radius-md);
  background: var(--bg-3);
}
.chart-legend {
  display: flex;
  align-items: center;
  gap: 16px;
  padding-top: 8px;
}
.chart-legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: var(--sans);
  font-size: 11px;
  color: var(--ink-2);
}
.chart-legend i {
  width: 14px;
  height: 3px;
  border-radius: 2px;
}
.legend-hist { background: var(--water); }
.legend-fc {
  background: var(--accent);
  background-image: repeating-linear-gradient(90deg, var(--accent) 0 5px, transparent 5px 9px);
}
.legend-now { background: var(--accent); opacity: .5; }

.chart-stats {
  display: grid;
  gap: 10px;
  align-content: start;
}
.hud-mini-stat {
  border-radius: var(--radius-md);
  padding: 10px 12px;
  background: var(--bg-3);
  transition: background .15s ease, transform .15s ease;
}
.hud-mini-stat:hover { background: var(--bg-4); transform: translateY(-1px); }
.hud-mini-stat span {
  display: block;
  color: var(--muted);
  font-size: 10px;
  font-weight: 500;
  letter-spacing: .02em;
}
.hud-mini-stat b {
  display: block;
  margin-top: 6px;
  font-family: var(--display);
  font-size: 18px;
  font-weight: 600;
  color: var(--ink);
}
.hud-mini-stat b small { color: var(--muted); font-size: 11px; font-weight: 500; }
.hud-mini-stat.peak b { color: var(--accent); }

/* ===== 监测视频弹窗（Material Dialog） ===== */
.monitor-overlay {
  position: fixed; inset: 0; z-index: 150;
  background: rgba(0,0,0,.55);
  backdrop-filter: blur(6px);
  display: flex; align-items: center; justify-content: center;
  padding: 40px;
}
.monitor-card {
  width: min(1040px, calc(100vw - 80px));
  max-height: 92vh;
  background: var(--bg-2);
  border-radius: var(--radius-xl);
  display: flex; flex-direction: column;
  overflow: hidden;
  box-shadow: var(--shadow-4);
}

.monitor-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
  background: var(--bg-3);
}
.monitor-title { display: grid; gap: 4px; }
.monitor-code {
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 500;
  color: var(--primary);
}
.monitor-head h2 { margin: 0; font-family: var(--display); font-size: 16px; font-weight: 600; color: var(--ink); }
.monitor-close {
  min-height: 32px; padding: 0 16px;
  border: 0; border-radius: var(--radius-sm);
  background: var(--bg-4); color: var(--ink);
  font-family: var(--sans); font-size: 13px; font-weight: 500;
  cursor: pointer;
  transition: background .15s;
}
.monitor-close:hover { background: var(--primary); color: #fff; }

.monitor-body {
  flex: 1; overflow-y: auto; min-height: 0;
  display: flex;
  flex-direction: column; gap: 14px;
  padding: 16px 20px;
}
.monitor-video {
  flex-shrink: 0;
  aspect-ratio: 16/9;
  background: #000;
  border-radius: var(--radius-md);
  overflow: hidden;
  display: flex; align-items: center; justify-content: center;
}
.video-frame { width: 100%; height: 100%; object-fit: contain; }
.video-placeholder { color: var(--muted); font-size: 13px; }

.monitor-charts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  min-height: 0;
  flex: 1;
}
.monitor-chart-panel {
  min-height: 0;
  display: flex; flex-direction: column;
  border-radius: var(--radius-md);
  background: var(--bg-3);
  overflow: hidden;
}
.mcp-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
  gap: 8px;
}
.mcp-code {
  font-family: var(--sans); font-size: 11px; font-weight: 500; color: var(--primary);
}
.mcp-head h3 { margin: 0; font-family: var(--display); font-size: 13px; font-weight: 600; color: var(--ink-2); }
.mcp-legend {
  display: inline-flex; align-items: center; gap: 6px;
  font-family: var(--sans); font-size: 11px; color: var(--muted);
}
.mcp-legend i { width: 14px; height: 3px; border-radius: 2px; }
.leg-hist { background: var(--water); }
.mcp-body {
  flex: 1; min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 90px;
  gap: 10px;
  padding: 10px 12px;
}
.mcp-chart { min-height: 0; min-width: 0; }
.mcp-chart :deep(.trend-chart-wrap) { min-height: 140px; }
.mcp-stats {
  display: grid;
  gap: 6px;
  align-content: start;
}
.mcp-stat {
  padding: 7px 9px;
  border-radius: var(--radius-sm);
  background: var(--bg-4);
}
.mcp-stat span { display: block; font-family: var(--sans); font-size: 10px; color: var(--muted); }
.mcp-stat b { font-size: 15px; font-weight: 600; color: var(--ink-2); }
.mcp-stat b small { font-size: 11px; color: var(--muted); margin-left: 2px; }
.mcp-stat.current b { color: var(--primary); }
.mcp-stat.current { background: var(--chip); }

@media (max-width: 1180px) {
  .overview-hud {
    grid-template-columns: 1fr 1fr;
    grid-template-rows: auto auto 1fr auto;
    grid-template-areas:
      "top top"
      "left right"
      "left right"
      "bottom bottom";
  }
  .hud-bg { display: none; }
}
@media (max-width: 900px) {
  .overview-hud {
    grid-template-columns: 1fr;
    grid-template-areas:
      "top"
      "left"
      "right"
      "bottom";
    overflow-y: auto;
  }
  .chart-body { grid-template-columns: 1fr; }
  .chart-stats { grid-template-columns: repeat(2, 1fr); }
  .monitor-charts { grid-template-columns: 1fr; }
}
</style>
