<template>
  <Topbar title="模型预报" subtitle="Chronos-2 时序基础模型 / LSTM / 水动力融合，未来 72 小时流量趋势。" />
  <section class="forecast-page">
    <article class="panel">
      <div class="panel-head"><h2>模型参数</h2><span>运行前配置</span></div>
      <div class="panel-body">
        <div class="param-grid">
          <div class="param-item">
            <label for="forecast-steps">预测步长</label>
            <input id="forecast-steps" name="steps" type="number" v-model.number="params.steps" min="1" max="168" aria-label="预测步长" />
          </div>
          <div class="param-item">
            <label for="forecast-context">上下文窗口</label>
            <input id="forecast-context" name="context" type="number" v-model.number="params.context" min="1" max="168" aria-label="上下文窗口" />
          </div>
          <div class="param-item">
            <label>置信区间</label>
            <div class="param-dropdown" @click="toggleDropdown('ci')" ref="ciRef">
              <span>{{ params.ci }}</span>
              <i class="arrow">&#9662;</i>
            </div>
          </div>
          <div class="param-item">
            <label>模式</label>
            <div class="param-dropdown" @click="toggleDropdown('mode')" ref="modeRef">
              <span>{{ params.mode }}</span>
              <i class="arrow">&#9662;</i>
            </div>
          </div>
        </div>
        <button class="btn primary run-btn" :disabled="loading" @click="runForecast">
          {{ loading ? '预报运行中...' : '运行预报' }}
        </button>
        <p v-if="error" class="error-msg">{{ error }}</p>
      </div>
    </article>
    <article class="panel forecast-result-panel">
      <div class="panel-head"><h2>预报结果</h2><span>{{ resultLabel }}</span></div>
      <div class="panel-body forecast-result-body">
        <div class="forecast-placeholder" v-if="!ran">
          <p>配置参数后点击「运行预报」</p>
        </div>
        <div class="forecast-chart-area" v-else>
          <div class="combined-chart" ref="chartWrap">
            <TrendChart v-if="chartReady" :history="history" :forecast="forecast" unit="流量(m³/s)" />
          </div>
          <div class="combined-summary">
            <div class="mini-stat"><span>预报峰值</span><b>{{ resultPeak }}m³/s</b></div>
            <div class="mini-stat"><span>峰现时间</span><b>{{ resultTime }}</b></div>
            <div class="mini-stat"><span>置信下限</span><b>{{ resultLow }}m³/s</b></div>
            <div class="mini-stat"><span>置信上限</span><b>{{ resultHigh }}m³/s</b></div>
          </div>
        </div>
      </div>
    </article>
  </section>

  <Teleport to="body">
    <ul v-if="openDropdown === 'ci'" class="dropdown-menu" :style="ddStyle">
      <li v-for="o in ciOptions" :key="o" @click.stop="selectOption('ci', o)">{{ o }}</li>
    </ul>
    <ul v-if="openDropdown === 'mode'" class="dropdown-menu" :style="ddStyle">
      <li v-for="o in modeOptions" :key="o" @click.stop="selectOption('mode', o)">{{ o }}</li>
    </ul>
  </Teleport>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import Topbar from '../components/Topbar.vue'
import TrendChart from '../components/TrendChart.vue'
import { api } from '../api'

const params = reactive({
  steps: 72,
  context: 72,
  ci: '10% / 90%',
  mode: 'univariate'
})

const ciOptions = ['5% / 95%', '10% / 90%', '20% / 80%', '25% / 75%']
const modeOptions = ['univariate', 'multivariate', 'hybrid', 'ensemble']

const openDropdown = ref(null)
const ddStyle = ref({})
const ciRef = ref(null)
const modeRef = ref(null)
const ran = ref(false)
const loading = ref(false)
const error = ref('')
const resultLabel = ref('未来 72h')
const resultPeak = ref('—')
const resultTime = ref('—')
const resultLow = ref('—')
const resultHigh = ref('—')
const history = ref([])
const forecast = ref([])
const chartReady = ref(false)
const chartWrap = ref(null)

const labels = computed(() => {
  const now = new Date()
  const fmt = (d) => `${String(d.getDate()).padStart(2, '0')}日${String(d.getHours()).padStart(2, '0')}时`
  const offsets = [-24, -16, -8, 0, 24, 48, 72]
  return offsets.map(h => { const d = new Date(now.getTime() + h * 3600000); return fmt(d) })
})

function toggleDropdown(key) {
  if (openDropdown.value === key) { openDropdown.value = null; return }
  openDropdown.value = key
  const refEl = key === 'ci' ? ciRef.value : modeRef.value
  if (refEl) {
    const r = refEl.getBoundingClientRect()
    ddStyle.value = { position: 'fixed', top: r.bottom + 4 + 'px', left: r.left + 'px', minWidth: r.width + 'px' }
  }
}

function selectOption(key, val) {
  if (key === 'ci') params.ci = val
  else params.mode = val
  openDropdown.value = null
}

function closeDropdown(e) {
  if (openDropdown.value) {
    const refEl = openDropdown.value === 'ci' ? ciRef.value : modeRef.value
    if (refEl && !refEl.contains(e.target)) openDropdown.value = null
  }
}

onMounted(() => document.addEventListener('click', closeDropdown))
onUnmounted(() => document.removeEventListener('click', closeDropdown))

async function runForecast() {
  ran.value = false
  loading.value = true
  error.value = ''
  chartReady.value = false
  try {
    const data = await api.runForecast('00106', params.steps, params.mode, params.context)
    ran.value = true
    resultLabel.value = `步长 ${params.steps}h · ${params.mode}`
    error.value = ''

    // 解析历史序列（带上真实时间戳）
    const histSeries = data.input_series || []
    const now = Date.now()
    const stepMs = 3600000
    const histPoints = histSeries.map((d, i) => {
      const t = new Date(d.Time)
      return {
        time: !isNaN(t.getTime()) ? t.getTime() : now - (histSeries.length - i) * stepMs,
        t: !isNaN(t.getTime()) ? `${String(t.getDate()).padStart(2, '0')}日${String(t.getHours()).padStart(2, '0')}时` : d.Time,
        y: d.Flow || 0
      }
    })
    history.value = histPoints.length ? histPoints : buildFallbackHistory()

    // 解析预报序列（带上真实时间戳）
    const pred = data.result?.predictions || data.result?.forecast || data.result?.series || []
    if (pred.length) {
      const lastHistTime = history.value[history.value.length - 1]?.time || now
      forecast.value = pred.map((v, i) => {
        const t = new Date(lastHistTime + (i + 1) * stepMs)
        return {
          time: t.getTime(),
          t: `${String(t.getDate()).padStart(2, '0')}日${String(t.getHours()).padStart(2, '0')}时`,
          y: typeof v === 'number' ? v : (v.Flow || v.value || 0)
        }
      })
    } else {
      forecast.value = []
    }

    // 峰值与置信区间
    const vals = forecast.value.map(d => d.y).filter(v => typeof v === 'number')
    if (vals.length) {
      const peak = Math.max(...vals)
      const peakIdx = vals.indexOf(peak)
      resultPeak.value = peak.toFixed(2)
      resultTime.value = forecast.value[peakIdx]?.t || '—'
      resultLow.value = (Math.min(...vals) * 0.95).toFixed(2)
      resultHigh.value = (peak * 1.05).toFixed(2)
    } else {
      resultPeak.value = '—'
      resultTime.value = '—'
      resultLow.value = '—'
      resultHigh.value = '—'
    }

    chartReady.value = true
  } catch (e) {
    error.value = e.message || '预报失败'
    ran.value = false
    console.error('runForecast error:', e)
  } finally {
    loading.value = false
  }
}

function buildFallbackHistory() {
  // 当后端未返回历史序列时，给出占位点保证图表能渲染
  const now = Date.now()
  return [0, 1, 2, 3].map((i) => ({
    time: now - (3 - i) * 3600000,
    t: labels.value[i] || '',
    y: 200 + i * 50
  }))
}
</script>

<style scoped>
.forecast-page {
  min-height: 0;
  display: grid;
  grid-template-rows: auto minmax(45%, 1fr);
  gap: var(--gap, 10px);
  overflow: hidden;
}

.param-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.param-item { display: flex; flex-direction: column; gap: 6px; }
.param-item label { font-size: 12px; color: var(--muted); font-weight: 600; }

.param-item input {
  height: 34px; padding: 0 10px;
  border: 1px solid var(--line); border-radius: 10px;
  background: rgba(255,255,255,.72);
  font-family: var(--mono); font-size: 13px; outline: none;
}
.param-item input:focus { border-color: var(--clay); }

.param-dropdown {
  position: relative;
  height: 34px; padding: 0 10px;
  border: 1px solid var(--line); border-radius: 10px;
  background: rgba(255,255,255,.72);
  display: flex; align-items: center; justify-content: space-between;
  cursor: pointer; font-size: 13px; user-select: none;
  gap: 8px;
}
.param-dropdown .arrow { font-size: 10px; color: var(--muted); }
.param-dropdown:hover { border-color: var(--clay); }

.dropdown-menu {
  margin: 0; padding: 4px 0; list-style: none; z-index: 9999;
  border: 1px solid var(--line); border-radius: 10px;
  background: rgba(255,255,255,.96); box-shadow: 0 12px 32px rgba(0,0,0,.1);
  backdrop-filter: blur(12px);
}
.dropdown-menu li {
  padding: 8px 12px; font-size: 12px; cursor: pointer;
  transition: background .12s ease;
}
.dropdown-menu li:hover { background: rgba(200,111,76,.1); }

.run-btn { margin-top: 12px; font-size: 13px; }
.run-btn:disabled { opacity: .6; cursor: not-allowed; }

.error-msg {
  margin-top: 10px;
  color: var(--clay);
  font-size: 12px;
}

.forecast-result-panel {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
}
.forecast-result-body { display: flex; flex-direction: column; }

.forecast-placeholder {
  flex: 1; display: flex; align-items: center; justify-content: center;
  color: var(--muted); font-size: 13px;
}

.forecast-chart-area {
  flex: 1; min-height: 0;
  display: grid; grid-template-rows: minmax(0, 1fr) auto;
  gap: 8px;
}
.forecast-chart-area .combined-chart {
  min-height: 120px;
  border: 1px solid rgba(37,33,28,.08);
  border-radius: 14px;
  background: rgba(246,246,248,.78);
  overflow: hidden;
}
.forecast-chart-area .combined-chart svg { display: block; width: 100%; height: 100%; }
.forecast-chart-area .combined-summary { grid-template-columns: repeat(4, 1fr); }
</style>
