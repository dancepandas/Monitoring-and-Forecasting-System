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
            <label>模式</label>
            <div class="param-dropdown" @click="toggleDropdown" ref="modeRef">
              <span>{{ params.mode }}</span>
              <i class="arrow">&#9662;</i>
            </div>
          </div>
          <div class="param-action">
            <button class="btn primary run-btn" :disabled="loading" @click="runForecast">
              {{ loading ? '预报运行中...' : '运行预报' }}
            </button>
          </div>
        </div>
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
          <div v-if="forecastInsight" class="forecast-insight">
            <span class="insight-label">AI · 预报解读</span>
            <p>{{ forecastInsight }}</p>
          </div>
          <div class="combined-chart" ref="chartWrap">
            <TrendChart v-show="ran" :history="history" :forecast="forecast" unit="流量(m³/s)" />
          </div>
          <div class="chart-legend">
            <span><i class="legend-hist"></i>实测</span>
            <span><i class="legend-fc"></i>预报</span>
            <span><i class="legend-now"></i>当前</span>
          </div>
          <div class="combined-summary">
            <div class="mini-stat"><span>预报峰值</span><b>{{ resultPeak }}<small> m³/s</small></b></div>
            <div class="mini-stat"><span>峰现时间</span><b>{{ resultTime }}</b></div>
            <div class="mini-stat"><span>最小流量</span><b>{{ resultLow }}<small> m³/s</small></b></div>
            <div class="mini-stat"><span>平均流量</span><b>{{ resultAvg }}<small> m³/s</small></b></div>
          </div>
        </div>
      </div>
    </article>
  </section>

  <Teleport to="body">
    <ul v-if="openDropdown === 'mode'" class="dropdown-menu" :style="ddStyle">
      <li v-for="o in modeOptions" :key="o" @click.stop="selectOption(o)">{{ o }}</li>
    </ul>
  </Teleport>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import Topbar from '../components/Topbar.vue'
import TrendChart from '../components/TrendChart.vue'
import { api } from '../api'

const params = reactive({
  steps: 72,
  context: 72,
  mode: 'univariate'
})

const modeOptions = ['univariate', 'multivariate', 'hybrid', 'ensemble']

const openDropdown = ref(null)
const ddStyle = ref({})
const modeRef = ref(null)
const ran = ref(false)
const loading = ref(false)
const error = ref('')
const resultLabel = ref('未来 72h')
const resultPeak = ref('—')
const resultTime = ref('—')
const resultLow = ref('—')
const resultAvg = ref('—')
const history = ref([])
const forecast = ref([])
const chartWrap = ref(null)
const forecastInsight = ref('')

function toggleDropdown() {
  openDropdown.value = openDropdown.value ? null : 'mode'
  const refEl = modeRef.value
  if (refEl) {
    const r = refEl.getBoundingClientRect()
    ddStyle.value = { position: 'fixed', top: r.bottom + 4 + 'px', left: r.left + 'px', minWidth: r.width + 'px' }
  }
}

function selectOption(val) {
  params.mode = val
  openDropdown.value = null
}

function closeDropdown(e) {
  if (openDropdown.value) {
    const refEl = modeRef.value
    if (refEl && !refEl.contains(e.target)) openDropdown.value = null
  }
}

onMounted(() => document.addEventListener('click', closeDropdown))
onUnmounted(() => document.removeEventListener('click', closeDropdown))

async function runForecast() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.runForecast('00106', params.steps, params.mode, params.context)
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

    ran.value = true

    // 峰值与区间统计（基于真实预报序列，不做人为缩放）
    const vals = forecast.value.map(d => d.y).filter(v => typeof v === 'number' && !isNaN(v))
    if (vals.length) {
      const peak = Math.max(...vals)
      const low = Math.min(...vals)
      const peakIdx = forecast.value.findIndex(d => d.y === peak)
      resultPeak.value = peak.toFixed(2)
      resultTime.value = forecast.value[peakIdx]?.t || '—'
      resultLow.value = low.toFixed(2)
      resultAvg.value = (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2)
    } else {
      resultPeak.value = '—'
      resultTime.value = '—'
      resultLow.value = '—'
      resultAvg.value = '—'
    }

    // AI 预报解读
    api.getForecastInterpret('00106', 'virtualFlow').then(d => {
      forecastInsight.value = d.interpretation || ''
    }).catch(() => { forecastInsight.value = '预报解读暂不可用' })
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
  const fmt = (d) => `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:00`
  return [0, 1, 2, 3].map((i) => ({
    time: now - (3 - i) * 3600000,
    t: fmt(new Date(now - (3 - i) * 3600000)),
    y: 200 + i * 50
  }))
}
</script>

<style scoped>
.forecast-page {
  min-height: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: var(--gap, 10px);
  overflow: hidden;
}

.param-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--gap, 10px);
  align-items: end;
}

.param-item { display: flex; flex-direction: column; gap: 6px; }
.param-item label { font-size: 12px; color: var(--muted); font-weight: 600; }

.param-item input {
  min-height: 36px; padding: 0 12px;
  border: 1px solid var(--line); border-radius: 10px;
  background: rgba(255,255,255,.42);
  backdrop-filter: blur(8px);
  font-family: var(--mono); font-size: 13px; outline: none;
  transition: border-color .15s ease, background .15s ease;
}
.param-item input:focus { border-color: var(--primary); background: rgba(255,255,255,.55); }

.param-dropdown {
  position: relative;
  min-height: 36px; padding: 0 12px;
  border: 1px solid var(--line); border-radius: 10px;
  background: rgba(255,255,255,.42);
  backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: space-between;
  cursor: pointer; font-size: 13px; user-select: none;
  gap: 8px;
  transition: border-color .15s ease, background .15s ease;
}
.param-dropdown .arrow { font-size: 10px; color: var(--muted); }
.param-dropdown:hover { border-color: var(--primary); background: rgba(255,255,255,.55); }

.param-action { display: flex; justify-content: flex-end; }

.dropdown-menu {
  margin: 0; padding: 4px 0; list-style: none; z-index: 2000;
  border: 1px solid var(--line); border-radius: 10px;
  background: rgba(255,255,255,.72); box-shadow: 0 12px 32px rgba(0,0,0,.1);
  backdrop-filter: blur(12px);
}
.dropdown-menu li {
  padding: 8px 12px; font-size: 12px; cursor: pointer;
  transition: background .12s ease;
}
.dropdown-menu li:hover { background: rgba(14,165,233,.12); }

.run-btn { font-size: 13px; min-height: 36px; padding: 0 18px; }
.run-btn:disabled { opacity: .6; cursor: not-allowed; }

.error-msg {
  margin-top: 10px;
  color: var(--danger);
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
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto auto;
  gap: 10px;
}
.forecast-chart-area .forecast-insight {
  width: 100%;
  box-sizing: border-box;
  margin: 0;
  border: 1px solid var(--accent-soft);
  border-left: 3px solid var(--accent);
  border-radius: var(--radius-md);
  padding: 9px 13px;
  background: var(--accent-soft);
  display: flex;
  align-items: center;
  gap: 12px;
}
.forecast-chart-area .forecast-insight .insight-label {
  flex: 0 0 auto;
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 700;
  color: var(--accent);
  letter-spacing: .08em;
  white-space: nowrap;
}
.forecast-chart-area .forecast-insight p {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--ink);
}
.forecast-chart-area .combined-chart {
  min-height: 160px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background:
    linear-gradient(180deg, rgba(255,255,255,.45), rgba(255,255,255,.22)),
    rgba(14,165,233,.04);
  overflow: hidden;
}

.chart-legend {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 0 4px;
}
.chart-legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--ink-2);
}
.chart-legend i {
  width: 14px;
  height: 3px;
  border-radius: 2px;
}
.legend-hist { background: var(--water, #0EA5E9); }
.legend-fc { background: var(--accent, #6366F1); background-image: repeating-linear-gradient(90deg, var(--accent, #6366F1) 0 5px, transparent 5px 9px); }
.legend-now { background: var(--accent, #6366F1); opacity: .5; }

.forecast-chart-area .combined-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  align-items: start;
}
.forecast-chart-area .combined-summary .mini-stat {
  padding: 10px 12px;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.forecast-chart-area .combined-summary .mini-stat span { font-size: 10px; }
.forecast-chart-area .combined-summary .mini-stat b { font-size: 17px; }
.forecast-chart-area .combined-summary .mini-stat b small { font-size: 10px; color: var(--muted); }

@media (max-width: 900px) {
  .param-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .forecast-chart-area .combined-summary { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 540px) {
  .param-grid { grid-template-columns: 1fr; }
  .param-action { justify-content: stretch; }
  .run-btn { width: 100%; }
  .forecast-chart-area .combined-summary { grid-template-columns: 1fr 1fr; }
}
</style>
