<template>
  <section class="overview-hud">
    <!-- 中心：水系地图 -->
    <div class="hud-bg">
      <HydroMap
        :station-level="stationLevel"
        :station-data="stationData"
        :active-code="rotation.current.code"
        @station-click="onMapStationClick"
        @background-click="onMapBackgroundClick"
      />
    </div>

    <!-- 左上：当前站点 / 平台标识 -->
    <div class="hud-corner hud-top-left">
      <div class="hud-id">
        <span class="hud-id-code">当前站点</span>
        <h1 class="hud-id-name">{{ rotation.current.name || '郴州水文监测' }}</h1>
        <span class="hud-id-meta">实时监测中 · {{ currentTime }}</span>
      </div>
    </div>

    <!-- 左侧：四张指标卡 -->
    <div class="hud-col hud-left">
      <article class="hud-card river" @click="openMonitor('水位')">
        <i class="hud-card-icon"></i>
        <span class="hud-card-label">实时水位</span>
        <div class="hud-card-value">
          <b>{{ waterLevel }}</b>
          <span class="unit">m</span>
        </div>
        <div :class="['hud-card-note', levelAnomaly ? 'anomaly' : waterLevelNoteClass]" :title="levelAnomaly ? levelAnomaly.reason : ''">{{ levelAnomaly ? '⚠ 数据存疑' : waterLevelNote }}</div>
        <div class="hud-card-bar"><i :style="{ width: waterLevelPct + '%' }"></i></div>
      </article>

      <article class="hud-card" @click="openMonitor('流量')">
        <i class="hud-card-icon flow"></i>
        <span class="hud-card-label">实时流量</span>
        <div class="hud-card-value">
          <b>{{ waterFlow }}</b>
          <span class="unit">m³/s</span>
        </div>
        <div :class="['hud-card-note', flowAnomaly ? 'anomaly' : '']" :title="flowAnomaly ? flowAnomaly.reason : ''">{{ flowAnomaly ? '⚠ 数据存疑' : flowChangeNote }}</div>
        <div class="hud-card-bar flow-bar"><i :style="{ width: flowPct + '%' }"></i></div>
      </article>

      <article class="hud-card moss" @click="openStage('模型可信度', 'tile')">
        <i class="hud-card-icon model"></i>
        <span class="hud-card-label">模型可信度</span>
        <div class="hud-card-value">
          <b>{{ modelConfidence }}</b>
        </div>
        <div class="hud-card-note ok">Chronos 时序预测</div>
        <div class="hud-card-bar conf-bar"><i :style="{ width: (Number(modelConfidence) * 100 || 0) + '%' }"></i></div>
      </article>

      <article class="hud-card amber" @click="goWarnings">
        <i class="hud-card-icon alert"></i>
        <span class="hud-card-label">待处置预警</span>
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
          <span class="hud-panel-code">预警 {{ displayWarnings.length }} 条</span>
          <h2>预警与告警</h2>
          <span class="hud-panel-status">实时</span>
        </div>
        <div class="hud-panel-body">
          <div v-if="warningInsight" class="hud-insight warning-insight">
            <span class="insight-label">AI · 预警解读</span>
            <p>{{ warningInsight }}</p>
          </div>
          <div class="hud-risk-list">
            <div class="hud-risk-item" v-for="w in displayWarnings" :key="w.id" :class="['level-' + (w.level || 'ok'), w.level === '数据异常' ? 'is-anomaly' : '']" @click="openDrawer(w)">
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
          <span class="hud-panel-code">预报分析</span>
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
              <TrendChart :history="trendHistory" :forecast="trendForecast" :mark-last="!!(currentAnomaly && currentAnomaly.flagged)" unit="流量 (m³/s)" />
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
            <span class="monitor-code">实时监测</span>
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
                <span class="mcp-code">近 10 小时水位</span>
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
                <span class="mcp-code">近 10 小时流量</span>
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
          <div v-if="monitorLoading" class="monitor-loading">
            <span class="m-spinner"></span><span>正在加载监测数据…</span>
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
import HydroMap from '../components/HydroMap.vue'
import { api, ALL_STATION_CODES } from '../api'
import { useRotationStore } from '../store/rotation'
import { levelLabel, levelBadgeClass, levelSeverity } from '../utils/warningLevel'
import { STATIONS } from '../stations'

const router = useRouter()
const rotation = useRotationStore()

// 站点预警级别（供地图着色）：code -> 'ok'|'warn'|'danger'
const stationLevel = ref({})
// 每站实时水位/流量（供地图悬浮卡 + 角标）：code -> {level, flow, time, anomaly}
const stationData = ref({})

// 当前站数据异常裁决（来自 /data/latest 的 anomaly 字段）
const currentAnomaly = computed(() => stationData.value[rotation.current.code]?.anomaly || null)
// 水位是否被标存疑：水位突刺型 + 通用脏数据（冻结/负值/缺测）都影响水位
const levelAnomaly = computed(() => {
  const a = currentAnomaly.value
  if (!a || !a.flagged) return null
  return ['level_flow_inconsistency', 'frozen', 'invalid_value', 'gap_masking'].includes(a.type) ? a : null
})
// 流量是否被标存疑：流量突刺型 + 通用脏数据
const flowAnomaly = computed(() => {
  const a = currentAnomaly.value
  if (!a || !a.flagged) return null
  return ['flow_level_inconsistency', 'frozen', 'invalid_value', 'gap_masking'].includes(a.type) ? a : null
})
function onMapStationClick(s) {
  // 点击地图站点 → pin 到该站、关闭监测弹窗、打开详情抽屉并拉取实时数据
  if (!s?.code) return
  closeMonitor()
  rotation.pinStation(s.code)
  drawerStation.value = {
    name: s.name,
    code: s.code,
    level: '—',
    flow: '—',
    status: '加载中…',
    badgeClass: '',
    detail: '正在获取该站实时数据…',
  }
  drawerVisible.value = true
  loadStationDetail(s.code, s.name)
}

function onMapBackgroundClick() {
  // 点地图空白处 → 取消钉选、关抽屉，恢复轮播
  rotation.unpinStation()
  closeDrawer()
}

// 拉取单站实时水位/流量/预警，填充详情抽屉（点击站点 / 预警项时调用）
async function loadStationDetail(code, nameHint) {
  const st = STATIONS.find(s => s.code === code) || {}
  let level = '—', flow = '—', status = '正常', badgeClass = 'ok', detail = '该站当前运行正常，无活跃预警。'
  let anomaly = null
  try {
    const data = await api.getFlowRaw(code, st.device)
    const items = data?.data || []
    const latestWL = items.find(i => i.waterLevel != null)
    const latestFlow = items.find(i => i.virtualFlow != null || i.waterFlow != null)
    if (latestWL?.waterLevel != null) level = latestWL.waterLevel.toFixed(2)
    const fv = latestFlow?.virtualFlow ?? latestFlow?.waterFlow
    if (fv != null) flow = fv.toFixed(0)
    // 最新一条 record 上挂的数据异常裁决（/flow-raw 注入）
    anomaly = items[0]?.anomaly || null
  } catch (e) {
    detail = '实时数据获取失败：' + (e.message || e)
  }
  try {
    const wd = await api.getWarnings(code)
    const all = [...(wd.warnings || []), ...(wd.alerts || [])]
    if (all.length) {
      const top = all[0]
      const lv = top.level || top.level_name || ''
      status = levelLabel(lv) || '预警'
      badgeClass = levelBadgeClass(lv)
      detail = top.message || detail
    }
  } catch (e) { /* 预警查询失败不阻塞主流程 */ }
  drawerStation.value = {
    ...drawerStation.value,
    name: nameHint || drawerStation.value?.name || st.name,
    code,
    level, flow, status, badgeClass, detail, anomaly,
  }
}

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
const monitorLoading = ref(false)
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
  closeMonitor()
  const code = w.code || w.id || ''
  drawerStation.value = {
    name: w.name,
    code,
    level: '—',
    flow: '—',
    status: w.level ? levelLabel(w.level) : '加载中…',
    badgeClass: levelBadgeClass(w.level),
    detail: w.message || '正在获取该站实时数据…',
  }
  drawerVisible.value = true
  if (code) loadStationDetail(code, w.name)
}
function closeDrawer() { drawerVisible.value = false }

// 注：原 watch(rotation.mode) 会在 pin 后把抽屉数据覆盖成空，已移除。
// 站点点击 / 预警点击均由 onMapStationClick / openDrawer 直接拉取数据填充。

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
    const [flowData, warnData, chartData, stdData, latestAll] = await Promise.all([
      api.getFlowRaw(st.code, st.device),
      api.getWarnings(ALL_STATION_CODES).catch(() => ({ warnings: [], total: 0 })),
      api.getAlignedChart(st.code, 'virtualFlow').catch(() => ({ history: [], forecast: [] })),
      api.getWarningStandards().catch(() => ({})),
      api.getLatest(ALL_STATION_CODES).catch(() => ({ stations: {} })),
    ])

    // 每站实时水位/流量 → 喂给地图悬浮卡与角标
    const sd = {}
    for (const [code, v] of Object.entries(latestAll?.stations || {})) {
      const it = v && v.level
      sd[code] = it ? {
        level: it.waterLevel,
        flow: it.virtualFlow ?? it.waterFlow,
        time: it.time,
        anomaly: v.anomaly,
      } : null
    }
    stationData.value = sd

    const std = stdData?.stations?.[st.code]?.level || stdData?.defaults?.level || {}
    warningLevel.value = std.red || std.orange || 0

    pendingWarnings.value = warnData.total || '0'
    const allWarnings = [...(warnData.warnings || []), ...(warnData.alerts || []), ...(warnData.data_anomalies || [])]
    if (allWarnings.length > 0) {
      warnings.value = allWarnings.map(w => ({ id: w.id, name: w.name, level: w.level || w.level_name || '', message: w.message }))
      warningNote.value = [...new Set(allWarnings.map(w => w.name))].join('、')
    } else {
      warnings.value = [{ id: 'ok', name: '系统运行正常', level: '正常', message: '所有站点数据正常，无预警信息。' }]
      warningNote.value = '系统运行正常'
    }

    // 地图站点着色：按预警级别映射 station_code -> 'ok'|'warn'|'danger'
    // 注意：数据异常（level=数据异常）是数据质量问题，不是洪水险情，不参与红/橙着色，
    // 改由站点角标的紫色 ⚠ 单独表达（见 stationData[code].anomaly）。
    const sevOf = tag => tag === 'danger' ? 3 : tag === 'warn' ? 1 : 0
    const lvlMap = {}
    for (const w of allWarnings) {
      if (w.level === '数据异常' || w.type === '数据异常') continue
      const code = w.station_code || w.code || ''
      if (!code) continue
      const sev = levelSeverity(w.level || w.level_name || '')
      const tag = sev >= 3 ? 'danger' : sev >= 1 ? 'warn' : 'ok'
      if (!lvlMap[code] || sevOf(lvlMap[code]) < sev) lvlMap[code] = tag
    }
    // 默认全 ok
    for (const s of STATIONS) if (!lvlMap[s.code]) lvlMap[s.code] = 'ok'
    stationLevel.value = lvlMap

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
    // 详情抽屉若正打开且就是当前站，顺带同步水位/流量
    if (drawerVisible.value && drawerStation.value?.code === st.code) {
      drawerStation.value = { ...drawerStation.value, level: waterLevel.value, flow: waterFlow.value }
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
  closeDrawer()
  monitorType.value = type
  monitorVisible.value = true
  monitorLoading.value = true
  const st = rotation.current
  try {
    // 直播地址优先取「视频巡检同款 snapshots」（采集器定时缓存，地址稳定可播）；
    // 取不到再回退实时 video-feeds（调 deviceCamera，常返回 offline/空地址）。
    let url = ''
    try {
      const snap = await api.getVideoSnapshots(st.code, 5)
      const list = (snap && snap.snapshots) || []
      const hit = list.find(s => s && s.live_address)
      url = hit ? hit.live_address : ''
    } catch { url = '' }
    if (!url) {
      const feeds = await api.getVideoFeeds(st.code)
      const online = (feeds.feeds || []).find(f => f.status === 'online' && f.live_address)
      url = online ? online.live_address : ''
    }
    videoUrl.value = url
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
  monitorLoading.value = false
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
/* ── Overview 业务布局：地图居中 + 左右信息栏 ── */
.overview-hud {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-columns: 290px 1fr 330px;
  grid-template-rows: auto 1fr auto;
  grid-template-areas:
    "top    center right"
    "left   center right"
    "bottom bottom bottom";
  gap: 14px;
  padding: 14px;
  pointer-events: none;
  overflow: hidden;
}
.overview-hud > * { pointer-events: auto; }

/* ── 中心水系地图容器 ── */
.hud-bg {
  grid-area: center;
  position: relative;
  min-height: 0;
  z-index: 0;
  pointer-events: auto;
  overflow: hidden;
  border-radius: var(--radius-xl);
  border: 1px solid var(--line);
  box-shadow: var(--shadow-panel);
  background: var(--bg-3);
}

/* ── 卡片 / 面板（业务白卡） ── */
.hud-card,
.hud-panel {
  position: relative;
  border: 1px solid var(--line);
  border-radius: var(--radius-xl);
  background: var(--bg-2);
  box-shadow: var(--shadow-panel);
  overflow: hidden;
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
  box-shadow: var(--shadow-panel);
  position: relative;
}
.hud-id::before {
  content: "";
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
  border-radius: var(--radius-lg) 0 0 var(--radius-lg);
  background: var(--primary);
}
.hud-id-code {
  display: block;
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: .06em;
  color: var(--primary);
  margin-bottom: 4px;
  text-transform: uppercase;
}
.hud-id-name {
  margin: 0;
  font-family: var(--display);
  font-size: 20px;
  font-weight: 600;
  color: var(--ink);
  letter-spacing: .01em;
}
.hud-id-meta {
  display: block;
  margin-top: 4px;
  font-family: var(--mono);
  font-size: 11.5px;
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
.hud-right {
  grid-area: right;
  display: grid;
  align-content: stretch;
  gap: 14px;
  min-height: 0;
}

/* 指标卡 —— 收紧内距/行距/字号，确保 4 张卡在左列高度内完整显示 */
.hud-card {
  display: grid;
  grid-template-columns: 1fr auto;
  grid-template-rows: auto auto auto;
  gap: 3px 12px;
  padding: 11px 14px;
  cursor: pointer;
  transition: box-shadow .18s var(--ease-soft), border-color .18s var(--ease-soft);
}
.hud-card:hover {
  border-color: var(--line-strong);
  box-shadow: var(--shadow-2);
}
.hud-card-icon {
  grid-column: 2;
  grid-row: 1 / 4;
  align-self: center;
  width: 4px; height: 30px;
  border-radius: var(--radius-sm);
  background: var(--primary);
}
.hud-card-icon.flow { background: var(--water); }
.hud-card-icon.model { background: var(--ok); }
.hud-card-icon.alert { background: var(--orange); }

.hud-card-label {
  grid-column: 1;
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 500;
  color: var(--muted);
  letter-spacing: 0;
}
.hud-card-value {
  grid-column: 1;
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.hud-card-value b {
  font-family: var(--display);
  font-size: 26px;
  line-height: 1;
  font-weight: 700;
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
.hud-card-note.anomaly { color: var(--anomaly); font-weight: 600; }

.hud-card-bar {
  grid-column: 1 / -1;
  height: 4px;
  margin-top: 6px;
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
  transition: width .6s var(--ease-soft);
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
.hud-panel.wide { grid-area: bottom; max-height: 30vh; }
/* 底部面板不滚动：让 combined-chart 的 flex:1 收缩去给 AI 解读让位，
   这样解读高度被计入，图+图例+解读+统计列在同一高度内全部可见。 */
.hud-panel.wide .hud-panel-body { overflow: hidden; }
.hud-right .hud-panel { height: 100%; max-height: none; }

.hud-panel-head {
  position: relative;
  min-height: 40px;
  padding: 9px 14px;
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
  letter-spacing: .04em;
}
.hud-panel-code,
.hud-panel-status {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--muted);
  letter-spacing: .04em;
  text-transform: uppercase;
}
.hud-panel-status { color: var(--primary); font-weight: 600; }

.hud-panel-body {
  min-height: 0;
  overflow-y: auto;
  padding: 10px;
  background: transparent;
}

/* 预报解读 */
.hud-insight {
  display: block;
  padding: 8px 12px;
  border-radius: var(--radius-md);
  background: var(--accent-soft);
  border: 1px solid var(--line);
  border-left: 3px solid var(--accent);
  margin-bottom: 9px;
}
.hud-insight.warning-insight { border-left-color: var(--primary); background: var(--primary-soft); }
.hud-insight .insight-label {
  display: block;
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 700;
  color: var(--accent);
  letter-spacing: .06em;
  text-transform: uppercase;
  margin-bottom: 6px;
}
.hud-insight.warning-insight .insight-label { color: var(--primary); }
.hud-insight p {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--ink-2);
}
/* 图表上方解读：紧凑横条，最多 2 行，不撑高面板 */
.hud-insight.insight-above-chart {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 5px 12px;
  margin-bottom: 6px;
  flex-shrink: 0;
}
.hud-insight.insight-above-chart .insight-label { margin-bottom: 0; flex-shrink: 0; padding-top: 1px; }
.hud-insight.insight-above-chart p {
  font-size: 11.5px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 告警列表 */
.hud-risk-list {
  display: grid;
  gap: 8px;
  align-content: start;
}
.hud-risk-item {
  position: relative;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  padding: 9px 12px;
  background: var(--bg-2);
  cursor: pointer;
  transition: background .15s var(--ease-soft), border-color .15s var(--ease-soft);
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
  background: var(--bg-3);
  border-color: var(--line-strong);
}
.hud-risk-item.level-danger::before { background: var(--danger); }
.hud-risk-item.level-orange::before { background: var(--orange); }
.hud-risk-item.level-warn::before { background: var(--warn); }
.hud-risk-item.level-ok::before { background: var(--ok); }
.hud-risk-item.is-anomaly::before { background: var(--anomaly); }
.hud-risk-item .risk-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 5px;
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
  line-height: 1.55;
  overflow-wrap: break-word;
}
.badge {
  border-radius: var(--radius-sm);
  padding: 3px 8px;
  font-size: 10px;
  font-weight: 700;
  font-family: var(--mono);
  color: #FFFFFF;
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
  grid-template-columns: minmax(0, 1fr) 128px;
  gap: 12px;
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
  border: 1px solid var(--line);
}
.chart-legend {
  display: flex;
  align-items: center;
  gap: 18px;
  padding-top: 6px;
  flex-shrink: 0;
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
  gap: 8px;
  align-content: start;
}
.hud-mini-stat {
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  padding: 8px 11px;
  background: var(--bg-2);
  transition: background .15s var(--ease-soft), border-color .15s var(--ease-soft);
}
.hud-mini-stat:hover { background: var(--bg-3); border-color: var(--line-strong); }
.hud-mini-stat span {
  display: block;
  color: var(--muted);
  font-size: 10px;
  font-weight: 500;
  letter-spacing: .04em;
}
.hud-mini-stat b {
  display: block;
  margin-top: 3px;
  font-family: var(--display);
  font-size: 16px;
  font-weight: 600;
  color: var(--ink);
}
.hud-mini-stat b small { color: var(--muted); font-size: 11px; font-weight: 500; }
.hud-mini-stat.peak b { color: var(--primary); }

/* ===== 监测视频弹窗（Abyss Dialog） ===== */
.monitor-overlay {
  position: fixed; inset: 0; z-index: 9000;
  background: rgba(15, 23, 42, 0.7);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  display: flex; align-items: center; justify-content: center;
  padding: 40px;
}
.monitor-card {
  width: min(1080px, calc(100vw - 80px));
  max-height: 92vh;
  background: var(--glass-strong);
  border: 1px solid var(--line);
  border-radius: var(--radius-xl);
  display: flex; flex-direction: column;
  overflow: hidden;
  box-shadow: var(--shadow-4), 0 0 40px rgba(14, 165, 233, 0.08);
}

.monitor-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
  background: var(--bg-2);
}
.monitor-title { display: grid; gap: 5px; }
.monitor-code {
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 600;
  color: var(--primary);
  letter-spacing: .06em;
  text-transform: uppercase;
}
.monitor-head h2 { margin: 0; font-family: var(--display); font-size: 17px; font-weight: 600; color: var(--ink); letter-spacing: .03em; }
.monitor-close {
  min-height: 34px; padding: 0 16px;
  border: 1px solid var(--line); border-radius: var(--radius-sm);
  background: var(--bg-3); color: var(--ink);
  font-family: var(--sans); font-size: 13px; font-weight: 500;
  cursor: pointer;
  transition: all .18s ease;
}
.monitor-close:hover { background: var(--primary); color: #FFFFFF; border-color: var(--primary); box-shadow: 0 0 14px var(--primary-glow); }

.monitor-body {
  flex: 1; overflow-y: auto; min-height: 0;
  position: relative;
  display: flex;
  flex-direction: column; gap: 12px;
  padding: 14px 18px;
}
.monitor-video {
  flex-shrink: 0;
  aspect-ratio: 16/9;
  max-height: 40vh;
  background: #000;
  border-radius: var(--radius-md);
  overflow: hidden;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid var(--line);
}
.video-frame { width: 100%; height: 100%; object-fit: contain; }
.video-placeholder { color: var(--muted); font-size: 13px; }

.monitor-loading {
  position: absolute; inset: 0; z-index: 5;
  display: flex; align-items: center; justify-content: center; gap: 10px;
  background: rgba(255, 255, 255, .72);
  -webkit-backdrop-filter: blur(2px);
  backdrop-filter: blur(2px);
  color: var(--ink-2); font-size: 13px;
}
.m-spinner {
  width: 16px; height: 16px;
  border: 2px solid var(--bg-4);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: mspin .6s linear infinite;
}
@keyframes mspin { to { transform: rotate(360deg); } }

.monitor-charts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  min-height: 0;
  flex: 1;
}
.monitor-chart-panel {
  min-height: 0;
  display: flex; flex-direction: column;
  border-radius: var(--radius-md);
  background: var(--bg-2);
  border: 1px solid var(--line);
  overflow: hidden;
}
.mcp-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 9px 14px;
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
  gap: 8px;
}
.mcp-code {
  font-family: var(--mono); font-size: 10px; font-weight: 600; color: var(--primary); letter-spacing: .06em; text-transform: uppercase;
}
.mcp-head h3 { margin: 0; font-family: var(--display); font-size: 13px; font-weight: 600; color: var(--ink-2); letter-spacing: .03em; }
.mcp-legend {
  display: inline-flex; align-items: center; gap: 6px;
  font-family: var(--sans); font-size: 11px; color: var(--muted);
}
.mcp-legend i { width: 14px; height: 3px; border-radius: 2px; }
.leg-hist { background: var(--water); box-shadow: 0 0 6px rgba(14, 165, 233, 0.35); }
.mcp-body {
  flex: 1; min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 95px;
  gap: 10px;
  padding: 10px 12px;
}
.mcp-chart { min-height: 0; min-width: 0; }
.mcp-chart :deep(.trend-chart-wrap) { min-height: 110px; }
.mcp-stats {
  display: grid;
  gap: 8px;
  align-content: start;
}
.mcp-stat {
  padding: 6px 9px;
  border-radius: var(--radius-sm);
  background: rgba(241, 245, 249, 0.5);
  border: 1px solid var(--line);
}
.mcp-stat span { display: block; font-family: var(--sans); font-size: 10px; color: var(--muted); }
.mcp-stat b { font-size: 15px; font-weight: 600; color: var(--ink-2); }
.mcp-stat b small { font-size: 11px; color: var(--muted); margin-left: 2px; }
.mcp-stat.current b { color: var(--primary); }
.mcp-stat.current { background: rgba(14, 165, 233, 0.08); border-color: var(--edge); }

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
  .hud-bg { min-height: 320px; }
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
