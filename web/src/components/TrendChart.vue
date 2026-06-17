<template>
  <div ref="wrap" class="trend-chart-wrap">
    <svg width="100%" height="100%" :viewBox="`0 0 ${viewW} ${viewH}`" preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <linearGradient id="historyArea" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" :stop-color="historyColor" stop-opacity=".22"/>
          <stop offset="1" :stop-color="historyColor" stop-opacity="0"/>
        </linearGradient>
        <linearGradient id="forecastArea" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" :stop-color="forecastColor" stop-opacity=".16"/>
          <stop offset="1" :stop-color="forecastColor" stop-opacity="0"/>
        </linearGradient>
      </defs>

      <!-- Grid + Y axis labels -->
      <g v-for="(g, i) in yGrids" :key="'yg'+i">
        <line class="grid" :x1="plot.x" :y1="g.y" :x2="plot.x + plot.w" :y2="g.y"/>
        <text class="y-label" :x="plot.x - 6" :y="g.y + 3">{{ g.label }}</text>
      </g>
      <line class="axis" :x1="plot.x" :y1="plot.y + plot.h" :x2="plot.x + plot.w" :y2="plot.y + plot.h"/>
      <line class="axis" :x1="plot.x" :y1="plot.y" :x2="plot.x" :y2="plot.y + plot.h"/>
      <text class="y-unit" :x="plot.x - 28" :y="plot.y - 4">{{ props.unit }}</text>

      <!-- Now line -->
      <line v-if="nowX != null" class="now-line" :x1="nowX" :y1="plot.y" :x2="nowX" :y2="plot.y + plot.h"/>

      <!-- History area + line -->
      <path class="history-area" :d="historyAreaD" fill="url(#historyArea)"/>
      <path class="history-line" :d="historyLineD" fill="none" :stroke="historyColor" stroke-width="2.5" vector-effect="non-scaling-stroke"/>

      <!-- Forecast area + line -->
      <path class="forecast-area" :d="forecastAreaD" fill="url(#forecastArea)"/>
      <path class="forecast-line" :d="forecastLineD" fill="none" :stroke="forecastColor" stroke-width="2.5" stroke-dasharray="6 5" vector-effect="non-scaling-stroke"/>

      <!-- Now dot -->
      <circle v-if="nowX != null" class="history-dot" :cx="nowX" :cy="nowY" r="4" vector-effect="non-scaling-stroke"/>

      <!-- X labels -->
      <text v-for="(l, i) in xLabels" :key="'xl'+i" class="chart-label" :x="l.x" :y="plot.y + plot.h + 14">{{ l.text }}</text>
    </svg>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'

const props = defineProps({
  history: { type: Array, default: () => [] },
  forecast: { type: Array, default: () => [] },
  unit: { type: String, default: '水位(m)' }
})

const wrap = ref(null)
const viewW = ref(840)
const viewH = ref(180)

const historyColor = '#6d929f'
const forecastColor = '#b96b55'

const margin = { top: 10, right: 16, bottom: 30, left: 42 }

const plot = computed(() => ({
  x: margin.left,
  y: margin.top,
  w: Math.max(50, viewW.value - margin.left - margin.right),
  h: Math.max(40, viewH.value - margin.top - margin.bottom)
}))

function _getTime(d) {
  if (d == null) return null
  if (typeof d.time === 'number') return d.time
  if (d.time instanceof Date) return d.time.getTime()
  if (typeof d.time === 'string') return new Date(d.time).getTime()
  if (typeof d.t === 'string') {
    const t = new Date(d.t)
    if (!isNaN(t.getTime())) return t.getTime()
  }
  return null
}

const historyPoints = computed(() => props.history.map(d => ({ ...d, _t: _getTime(d) })).filter(d => d._t != null && typeof d.y === 'number'))
const forecastPoints = computed(() => props.forecast.map(d => ({ ...d, _t: _getTime(d) })).filter(d => d._t != null && typeof d.y === 'number'))
const allPoints = computed(() => [...historyPoints.value, ...forecastPoints.value])

const timeDomain = computed(() => {
  const times = allPoints.value.map(d => d._t)
  if (times.length === 0) return [Date.now() - 86400000, Date.now() + 86400000]
  let min = Math.min(...times)
  let max = Math.max(...times)
  if (min === max) { min -= 3600000; max += 3600000 }
  return [min, max]
})

const yDomain = computed(() => {
  const vals = allPoints.value.map(d => d.y)
  if (!vals.length) return [0, 1]
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const pad = (max - min) * 0.12 || Math.abs(max) * 0.1 || 1
  return [min - pad, max + pad]
})

const xForTime = (t) => {
  const [min, max] = timeDomain.value
  const ratio = max === min ? 0.5 : (t - min) / (max - min)
  return plot.value.x + ratio * plot.value.w
}

const yForValue = (v) => {
  const [min, max] = yDomain.value
  const ratio = max === min ? 0.5 : (v - min) / (max - min)
  return plot.value.y + plot.value.h - ratio * plot.value.h
}

const nowPoint = computed(() => {
  const h = historyPoints.value
  if (!h.length) return null
  return h[h.length - 1]
})

const nowX = computed(() => nowPoint.value ? xForTime(nowPoint.value._t) : null)
const nowY = computed(() => nowPoint.value ? yForValue(nowPoint.value.y) : 0)

function linePath(points) {
  if (!points.length) return ''
  return points.map((d, i) => `${i === 0 ? 'M' : 'L'} ${xForTime(d._t)} ${yForValue(d.y)}`).join(' ')
}

function areaPath(points, endTime) {
  if (!points.length) return ''
  const base = plot.value.y + plot.value.h
  const start = xForTime(points[0]._t)
  const end = xForTime(endTime ?? points[points.length - 1]._t)
  return `${linePath(points)} L ${end} ${base} L ${start} ${base} Z`
}

const historyLineD = computed(() => linePath(historyPoints.value))
const historyAreaD = computed(() => areaPath(historyPoints.value, nowPoint.value ? nowPoint.value._t : null))

const forecastLineD = computed(() => {
  // 预报线从历史最后一个点开始画，保证连续性
  const start = nowPoint.value
  const pts = start ? [start, ...forecastPoints.value] : forecastPoints.value
  return linePath(pts)
})

const forecastAreaD = computed(() => {
  const start = nowPoint.value
  const pts = start ? [start, ...forecastPoints.value] : forecastPoints.value
  if (!pts.length) return ''
  return areaPath(pts, pts[pts.length - 1]._t)
})

const yGrids = computed(() => {
  const [min, max] = yDomain.value
  const steps = 4
  const arr = []
  for (let i = 0; i <= steps; i++) {
    const v = min + (max - min) * (i / steps)
    arr.push({ y: yForValue(v), label: formatValue(v) })
  }
  return arr
})

const xLabels = computed(() => {
  const [min, max] = timeDomain.value
  const span = max - min
  // 根据跨度选择 label 间隔：尽量让标签数量在 5~7 个
  let step = 3600000 // 1h
  const candidates = [3600000, 2 * 3600000, 3 * 3600000, 4 * 3600000, 6 * 3600000, 8 * 3600000, 12 * 3600000, 24 * 3600000, 2 * 24 * 3600000, 3 * 24 * 3600000]
  for (const c of candidates) {
    if (span / c > 7) step = c
    else break
  }
  const labels = []
  const fmt = (d) => `${String(d.getDate()).padStart(2, '0')}日${String(d.getHours()).padStart(2, '0')}时`
  const start = Math.floor(min / step) * step
  for (let t = start; t <= max + step; t += step) {
    if (t < min || t > max) continue
    labels.push({ x: xForTime(t), text: fmt(new Date(t)) })
  }
  return labels
})

function formatValue(v) {
  const abs = Math.abs(v)
  if (abs >= 1000) return (v / 1000).toFixed(1) + 'k'
  if (abs >= 1) return v.toFixed(1)
  return v.toFixed(2)
}

let ro
async function measure() {
  if (!wrap.value) return
  await nextTick()
  const rect = wrap.value.getBoundingClientRect()
  viewW.value = Math.max(100, Math.floor(rect.width))
  viewH.value = Math.max(60, Math.floor(rect.height))
}

onMounted(() => {
  measure()
  ro = new ResizeObserver(measure)
  if (wrap.value) ro.observe(wrap.value)
})

onUnmounted(() => {
  if (ro && wrap.value) ro.unobserve(wrap.value)
})
</script>

<style scoped>
.trend-chart-wrap { width: 100%; height: 100%; }
.axis { stroke: rgba(37,33,28,.12); }
.grid { stroke: rgba(37,33,28,.08); stroke-dasharray: 4 7; }
.y-label { fill: var(--muted); font-size: 9px; text-anchor: end; }
.y-unit { fill: var(--muted); font-size: 9px; text-anchor: start; font-weight: 600; }
.now-line { stroke: rgba(37,33,28,.18); stroke-width: 1; stroke-dasharray: 5 5; }
.history-dot { fill: #6d929f; }
.chart-label { fill: var(--muted); font-size: 10px; text-anchor: middle; }
</style>
