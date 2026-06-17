<template>
  <Topbar
    title="流域态势"
    subtitle="融合水位、流量、雨量雷达、视频巡检与模型预报。"
    action-label="智能研判"
    @primary-action="showAgentModal = true"
  />
  <section class="overview">
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
    </section>

    <section class="middle-grid">
      <article class="panel video-panel">
        <div class="panel-head"><h2>视频巡检</h2><span>关键断面</span></div>
        <div class="panel-body">
          <div class="video-grid">
            <div class="video-card" v-for="v in videoFeeds" :key="v.cam||v.id" @click="openStage(v.title, 'video')">
              <div class="video-meta"><b>{{ v.cam }}</b><span>{{ v.label }}</span></div>
            </div>
          </div>
        </div>
      </article>

      <article class="panel map-panel">
        <div class="panel-head"><h2>监测设备分布与流域态势</h2><span>定期刷新</span></div>
        <div class="panel-body">
          <div class="map-wrap">
            <svg viewBox="0 0 900 560" aria-hidden="true">
              <path class="basin" d="M170 92 L312 56 L484 82 L678 128 L782 252 L730 410 L548 492 L356 470 L160 390 L104 224 Z" />
              <path class="basin" opacity=".65" d="M254 158 L388 126 L542 152 L658 238 L612 364 L480 414 L334 396 L214 314 Z" />
              <path class="river-main" d="M224 118 C254 182 334 190 394 232 C466 282 436 336 510 382 C576 424 580 456 558 500" />
              <path class="river-main" style="stroke-width:11; opacity:.55" d="M138 312 C248 284 330 308 396 356 C458 400 532 382 646 322 C706 290 754 302 806 340" />
              <path class="river-secondary" d="M244 126 C182 194 184 278 222 366" />
              <path class="river-secondary" d="M620 146 C574 220 588 288 676 388" />
            </svg>
            <div class="map-layers">
              <button :class="['layer-btn', { active: mapLayer === 'flow' }]" @click="mapLayer = 'flow'">流域态势</button>
              <button :class="['layer-btn', { active: mapLayer === 'risk' }]" @click="mapLayer = 'risk'">风险热力</button>
              <button :class="['layer-btn', { active: mapLayer === 'links' }]" @click="mapLayer = 'links'">设备链路</button>
              <button :class="['layer-btn', { active: mapLayer === 'plan' }]" @click="mapLayer = 'plan'">调度推演</button>
            </div>
            <button v-for="s in stations" :key="s.code" :class="['station', statusClass(s)]" :style="{ left: s.x + '%', top: s.y + '%' }" :title="s.name">
              <span class="station-label">{{ s.name }}</span>
            </button>
          </div>
        </div>
      </article>

      <article class="panel">
        <div class="panel-head"><h2>预警与告警</h2><span>共 {{ displayWarnings.length }} 条</span></div>
        <div class="panel-body">
          <div class="risk-list">
            <div class="risk-item" v-for="w in displayWarnings" :key="w.id" @click="openStage(w.name, 'warning')">
              <div class="risk-row"><b>{{ w.name }}</b><span :class="['badge', badgeClass(w)]">{{ w.level }}</span></div>
              <p>{{ w.message }}</p>
            </div>
          </div>
        </div>
      </article>
    </section>

    <section class="bottom-grid">
      <article class="panel combined-panel">
        <div class="panel-head"><h2>历史数据与模型预报联合展示</h2><span>近 24h → 未来 12h</span></div>
        <div class="panel-body combined-card">
          <div class="combined-chart">
            <TrendChart :history="trendHistory" :forecast="trendForecast" unit="流量(m³/s)" />
          </div>
          <div class="forecast-summary combined-summary">
            <div class="mini-stat"><span>最高流量</span><b>{{ historyMaxFlow }}m³/s</b></div>
            <div class="mini-stat"><span>平均流量</span><b>{{ historyAvgFlow }}m³/s</b></div>
            <div class="mini-stat"><span>预报峰值</span><b>{{ forecastPeak }}m³/s</b></div>
            <div class="mini-stat"><span>峰现时间</span><b>{{ forecastPeakTime }}</b></div>
          </div>
        </div>
      </article>
    </section>

    <Teleport to="body">
      <div v-if="stageVisible" class="stage-modal" @click.self="stageVisible = false">
        <div class="stage-card">
          <div class="stage-head"><h2>{{ stageTitle }}</h2><button class="stage-close" @click="stageVisible = false">关闭</button></div>
          <div class="stage-body"><p style="color:var(--muted);text-align:center;padding:60px 0;">{{ stageTitle }} — 全屏详情（数据接入后展示完整内容）</p></div>
        </div>
      </div>

      <div v-if="showAgentModal" class="modal" @click.self="showAgentModal = false">
        <div class="modal-card agent-modal-card2">
          <div class="modal-actions" style="justify-content:space-between;align-items:center;">
            <h2>FloodMind 智能体</h2>
            <button class="btn" @click="showAgentModal = false">关闭</button>
          </div>
          <AgentChatPanel :sessionId="overviewAgentSid" />
        </div>
      </div>
    </Teleport>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, nextTick, computed } from 'vue'
import Topbar from '../components/Topbar.vue'
import TrendChart from '../components/TrendChart.vue'
import AgentChatPanel from '../components/AgentChatPanel.vue'
import { api } from '../api'

const overviewAgentSid = 'overview-agent-modal'

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
const historyMaxFlow = ref('—')
const historyAvgFlow = ref('—')
const videoFeeds = ref([])
const deviceCount = ref('—')
const mapLayer = ref('flow')
const stageVisible = ref(false)
const stageTitle = ref('')
const showAgentModal = ref(false)

const trendHistory = ref([])
const trendForecast = ref([])

const stations = [
  { code: '00106', name: '仙桃站', x: 44, y: 43, status: 'normal', shortName: '仙桃' },
]

const warnings = ref([
  { id: 'loading', name: '数据加载中...', level: '—', message: '正在获取预警数据' },
])

const displayWarnings = computed(() => {
  const all = [...warnings.value]
  all.sort((a, b) => {
    const order = { '红色': 0, '橙色': 1, '黄色': 2, '蓝色预警': 3, '提示': 4 }
    return (order[a.level] ?? 5) - (order[b.level] ?? 5)
  })
  return all
})

function badgeClass(w) {
  const m = { '红色': 'danger', '橙色': 'warn', '黄色': 'warn', '蓝色预警': 'ok', '提示': 'ok' }
  return m[w.level] || ''
}


const WARNING_LEVEL = 35.1
const GUARANTEE_LEVEL = 36.2

let pollTimer = null

async function refreshData() {
  console.log('[overview] refreshData start')
  try {
    // 并行拉取水位数据和预警数据
    console.log('[overview] fetching flow-raw + warnings')
    const [flowData, warnData, chartData, deviceData] = await Promise.all([
      api.getFlowRaw('00106', 'FD000489923695'),
      api.getWarnings('00106,00107,00108').catch(() => ({ warnings: [], total: 0 })),
      api.getAlignedChart('00106', 'virtualFlow').catch(() => ({ history: [], forecast: [] })),
      api.getDeviceStats('00106,00107,00108').catch(() => ({ total: 0, online: 0 })),
    ])
    console.log('[overview] flowData', flowData)
    console.log('[overview] warnData', warnData)

    // 更新预警与告警
    deviceCount.value = deviceData.online ? String(deviceData.online) : '—'

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
      const latest = items[0]
      const level = latest.waterLevel
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

      const wf = latest.virtualFlow
      if (wf !== null && wf !== undefined) {
        waterFlow.value = wf.toFixed(0)
        flowChangeNote.value = '已更新'
      } else {
        waterFlow.value = '—'
        flowChangeNote.value = '该站无流量数据'
      }

      // 使用 aligned 层历史数据
      trendHistory.value = chartData.history || []
      if (trendHistory.value.length) {
        const flowVals = trendHistory.value.map(d => d.y).filter(v => typeof v === 'number')
        historyMaxFlow.value = flowVals.length ? Math.max(...flowVals).toFixed(0) : '—'
        historyAvgFlow.value = flowVals.length ? Math.round(flowVals.reduce((a, b) => a + b, 0) / flowVals.length).toLocaleString() : '—'
      }

      // 运行预报模型
      try {
        const fc = await api.runForecast('00106', 12, 'univariate', 72)
        const preds = fc.result?.predictions || fc.result?.forecast || fc.result?.series || []
        if (preds.length) {
          const lastH = trendHistory.value[trendHistory.value.length - 1]
          const stepMs = 3600000
          trendForecast.value = preds.map((v, i) => {
            const t = new Date((lastH?.time || Date.now()) + (i + 1) * stepMs)
            return { time: t.getTime(), t: String(t.getDate()).padStart(2,'0') + '日' + String(t.getHours()).padStart(2,'0') + '时', y: typeof v === 'number' ? v : (v.Flow || v.value || 0), source: 'forecast' }
          })
        } else {
          trendForecast.value = chartData.forecast || []
        }
      } catch {
        trendForecast.value = chartData.forecast || []
      }
      if (trendForecast.value.length) {
        const peak = Math.max(...trendForecast.value.map(d => d.y).filter(v => typeof v === 'number'))
        const peakVal = peak ? peak.toFixed(0) : null
        forecastPeak.value = peakVal || '—'
        forecastPeakTime.value = trendForecast.value.find(d => d.y === peak)?.t || '—'      }
      computeModelConfidence()

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
    if (!data.ts || Date.now() - data.ts > 120000) return false // 10 min TTL
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
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })

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

function statusClass(s) { return s.status === 'warn' ? 'warn' : s.status === 'danger' ? 'danger' : '' }

function openStage(title, type) { stageTitle.value = title; stageVisible.value = true }
</script>

<style scoped>
.agent-modal-card2 {
  width: min(720px, 100%);
  height: min(600px, calc(100vh - 80px));
  display: flex;
  flex-direction: column;
  padding: 20px 22px 22px;
}
.agent-modal-card2 h2 { margin: 0; font-family: var(--serif); font-size: 22px; font-weight: 500; letter-spacing: -.04em; }
.agent-modal-card2 .modal-actions { margin-top: 0; margin-bottom: 12px; }
</style>
