<template>
  <div ref="wrap" class="trend-chart-wrap">
    <div ref="canvas" class="chart-canvas">
      <svg ref="svg" aria-hidden="true"></svg>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'

const props = defineProps({
  history: { type: Array, default: () => [] },
  forecast: { type: Array, default: () => [] },
  unit: { type: String, default: '水位(m)' }
})

const wrap = ref(null)
const canvas = ref(null)
const svg = ref(null)

const historyColor = '#0EA5E9'
const forecastColor = '#6366F1'
const HOUR = 3600000

const margin = { top: 12, right: 18, bottom: 26, left: 54 }

function _getTime(d) {
  if (d == null) return null
  if (typeof d.time === 'number') return d.time
  if (d.time instanceof Date) return d.time.getTime()
  if (typeof d.time === 'string') return new Date(d.time).getTime()
  if (typeof d.t === 'number') return d.t
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
  if (times.length === 0) return [Date.now() - 24 * HOUR, Date.now() + 12 * HOUR]
  let min = Math.min(...times)
  let max = Math.max(...times)
  if (min === max) { min -= HOUR; max += HOUR }
  return [min, max]
})

const yDomain = computed(() => {
  const vals = allPoints.value.map(d => d.y).filter(v => typeof v === 'number' && !isNaN(v))
  if (!vals.length) return [0, 1]
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const range = max - min
  // Tighter padding so meaningful variation isn't visually flattened
  const pad = range > 0 ? range * 0.06 : Math.abs(max) * 0.05 || 1
  return [Math.max(0, min - pad), max + pad]
})

const nowPoint = computed(() => {
  const h = historyPoints.value
  if (!h.length) return null
  return h[h.length - 1]
})

function pad2(n) { return String(n).padStart(2, '0') }

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/`/g, '&#96;')
}

function fmtLabel(ms, fmt) {
  const d = new Date(ms)
  if (fmt === 'hm') return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`
  if (fmt === 'dhm') return `${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`
  return `${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}

function axisTicks(tMin, tMax, pw) {
  const spanH = (tMax - tMin) / HOUR
  let fmt, steps
  if (spanH <= 12) { fmt = 'hm'; steps = [1, 2, 3] }
  else if (spanH <= 120) { fmt = 'dhm'; steps = [6, 12, 24] }
  else if (spanH <= 24 * 7) { fmt = 'd'; steps = [24] }
  else { fmt = 'd'; steps = [48, 72] }

  let stepH = steps[steps.length - 1]
  for (const s of steps) {
    const n = spanH / s
    if (n >= 3 && n <= 8 && pw / Math.max(1, n) >= 64) { stepH = s; break }
  }
  const stepMs = stepH * HOUR
  const ticks = []
  const start = Math.ceil(tMin / stepMs) * stepMs
  for (let tt = start; tt <= tMax; tt += stepMs) ticks.push(tt)
  return { fmt, ticks }
}

let ro = null
let raf = 0

function render() {
  if (!canvas.value || !svg.value) return
  const rect = canvas.value.getBoundingClientRect()
  const W = Math.max(260, Math.floor(rect.width))
  const H = Math.max(90, Math.floor(rect.height))
  svg.value.setAttribute('width', W)
  svg.value.setAttribute('height', H)
  svg.value.removeAttribute('viewBox')

  const pw = Math.max(40, W - margin.left - margin.right)
  const ph = Math.max(40, H - margin.top - margin.bottom)
  const [tMin, tMax] = timeDomain.value
  const [vMin, vMax] = yDomain.value

  const X = t => margin.left + ((t - tMin) / (tMax - tMin || 1)) * pw
  const Y = v => margin.top + ph - ((v - vMin) / (vMax - vMin || 1)) * ph

  const line = pts => pts.map((p, i) => `${i ? 'L' : 'M'} ${X(p._t).toFixed(1)} ${Y(p.y).toFixed(1)}`).join(' ')
  const area = pts => {
    const cx = X(pts[pts.length - 1]._t)
    return `${line(pts)} L ${cx.toFixed(1)} ${(margin.top + ph).toFixed(1)} L ${X(pts[0]._t).toFixed(1)} ${(margin.top + ph).toFixed(1)} Z`
  }
  const nowX = nowPoint.value ? X(nowPoint.value._t) : null

  // Y grid + labels
  let g = ''
  for (let i = 0; i <= 4; i++) {
    const v = vMin + (vMax - vMin) * (i / 4)
    const y = Y(v)
    g += `<line x1="${margin.left}" y1="${y.toFixed(1)}" x2="${(margin.left + pw).toFixed(1)}" y2="${y.toFixed(1)}" stroke="rgba(0,0,0,.12)" stroke-dasharray="4 7"/>`
    g += `<text x="${margin.left - 8}" y="${(y + 3).toFixed(1)}" font-family="var(--mono)" font-size="10" fill="#000" text-anchor="end">${Math.round(v)}</text>`
  }

  // X ticks
  const { fmt, ticks } = axisTicks(tMin, tMax, pw)
  for (const tt of ticks) {
    const x = X(tt)
    g += `<line x1="${x.toFixed(1)}" y1="${margin.top}" x2="${x.toFixed(1)}" y2="${(margin.top + ph).toFixed(1)}" stroke="rgba(0,0,0,.08)"/>`
    g += `<text x="${x.toFixed(1)}" y="${(margin.top + ph + 15).toFixed(1)}" font-family="var(--mono)" font-size="10" fill="#000" text-anchor="middle">${fmtLabel(tt, fmt)}</text>`
  }

  const hPts = historyPoints.value
  const fStart = nowPoint.value ? [nowPoint.value, ...forecastPoints.value] : forecastPoints.value

  const hPath = hPts.length ? line(hPts) : ''
  const hArea = hPts.length ? area(hPts) : ''
  const fPath = fStart.length ? line(fStart) : ''
  const fArea = fStart.length ? area(fStart) : ''

  const cy = margin.top + ph / 2
  const nowDot = nowPoint.value
    ? `<circle cx="${nowX.toFixed(1)}" cy="${Y(nowPoint.value.y).toFixed(1)}" r="4" fill="${historyColor}" stroke="#fff" stroke-width="1.5"/>`
    : ''

  // 数据点圆点（始终显示）
  let dots = ''
  for (let i = 0; i < hPts.length; i++) {
    const p = hPts[i]
    dots += `<circle cx="${X(p._t).toFixed(1)}" cy="${Y(p.y).toFixed(1)}" r="2.5" fill="${historyColor}" stroke="#fff" stroke-width="1"/>`
  }

  svg.value.innerHTML = `
    <defs>
      <linearGradient id="hA" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0" stop-color="${historyColor}" stop-opacity=".32"/>
        <stop offset="1" stop-color="${historyColor}" stop-opacity="0"/>
      </linearGradient>
      <linearGradient id="fA" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0" stop-color="${forecastColor}" stop-opacity=".28"/>
        <stop offset="1" stop-color="${forecastColor}" stop-opacity="0"/>
      </linearGradient>
    </defs>
    ${g}
    <text transform="translate(16 ${cy.toFixed(1)}) rotate(-90)" text-anchor="middle" font-family="var(--mono)" font-size="10" fill="#000">${escHtml(props.unit)}</text>
    <line x1="${margin.left}" y1="${(margin.top + ph).toFixed(1)}" x2="${(margin.left + pw).toFixed(1)}" y2="${(margin.top + ph).toFixed(1)}" stroke="rgba(0,0,0,.25)"/>
    <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${(margin.top + ph).toFixed(1)}" stroke="rgba(0,0,0,.25)"/>
    ${nowX != null ? `<line x1="${nowX.toFixed(1)}" y1="${margin.top}" x2="${nowX.toFixed(1)}" y2="${(margin.top + ph).toFixed(1)}" stroke="${forecastColor}" stroke-width="1" stroke-dasharray="5 5" opacity=".55"/>` : ''}
    ${hArea ? `<path d="${hArea}" fill="url(#hA)"/>` : ''}
    ${hPath ? `<path d="${hPath}" fill="none" stroke="${historyColor}" stroke-width="2.5"/>` : ''}
    ${fArea ? `<path d="${fArea}" fill="url(#fA)"/>` : ''}
    ${fPath ? `<path d="${fPath}" fill="none" stroke="${forecastColor}" stroke-width="3" stroke-dasharray="8 6"/>` : ''}
    ${dots}
    ${nowDot}
    <rect id="hit-area" x="${margin.left}" y="${margin.top}" width="${pw}" height="${ph}" fill="transparent" pointer-events="all"/>
    <g id="tooltip" visibility="hidden">
      <rect id="tip-bg" x="0" y="0" width="10" height="32" rx="4" fill="rgba(8,47,73,.94)" stroke="${historyColor}" stroke-width="1"/>
      <text id="tip-val" x="0" y="0" font-family="var(--mono)" font-size="11" font-weight="700" fill="#fff" text-anchor="middle"/>
      <text id="tip-time" x="0" y="0" font-family="var(--mono)" font-size="9" fill="#94A3B8" text-anchor="middle"/>
    </g>
  `

  // 鼠标悬停 tooltip
  const hitArea = svg.value.querySelector('#hit-area')
  const tooltip = svg.value.querySelector('#tooltip')
  const tipBg = svg.value.querySelector('#tip-bg')
  const tipVal = svg.value.querySelector('#tip-val')
  const tipTime = svg.value.querySelector('#tip-time')
  if (hitArea && tooltip && hPts.length) {
    const svgEl = svg.value
    hitArea.onmousemove = (e) => {
      const pt = svgEl.createSVGPoint()
      pt.x = e.clientX; pt.y = e.clientY
      const svgPt = pt.matrixTransform(svgEl.getScreenCTM().inverse())
      let best = null; let bestDist = Infinity
      for (const p of hPts) {
        const dx = X(p._t) - svgPt.x
        const dy = Y(p.y) - svgPt.y
        const dist = Math.sqrt(dx * dx + dy * dy)
        if (dist < bestDist) { bestDist = dist; best = p }
      }
      const threshold = pw / Math.max(1, hPts.length) * 3
      if (best && bestDist < threshold) {
        const val = typeof best.y === 'number' ? (Number.isInteger(best.y) ? best.y : best.y.toFixed(1)) : best.y
        const timeStr = fmtLabel(best._t, 'dhm')
        const valStr = String(val)
        const timeW = timeStr.length * 5.5
        const valW = valStr.length * 7
        const bw = Math.max(valW, timeW) + 16
        const tx = X(best._t)
        const ty = Y(best.y) - 22
        tipVal.textContent = valStr
        tipTime.textContent = timeStr
        tipBg.setAttribute('x', (tx - bw / 2).toFixed(1))
        tipBg.setAttribute('y', (ty - 10).toFixed(1))
        tipBg.setAttribute('width', bw.toFixed(1))
        tipVal.setAttribute('x', tx.toFixed(1))
        tipVal.setAttribute('y', (ty + 2).toFixed(1))
        tipTime.setAttribute('x', tx.toFixed(1))
        tipTime.setAttribute('y', (ty + 15).toFixed(1))
        tooltip.setAttribute('visibility', 'visible')
      } else {
        tooltip.setAttribute('visibility', 'hidden')
      }
    }
    hitArea.onmouseleave = () => { tooltip.setAttribute('visibility', 'hidden') }
  }
}

function schedule() {
  cancelAnimationFrame(raf)
  raf = requestAnimationFrame(render)
}

onMounted(() => {
  nextTick(render)
  if (canvas.value) ro = new ResizeObserver(schedule)
  if (canvas.value) ro.observe(canvas.value)
})

onUnmounted(() => {
  cancelAnimationFrame(raf)
  if (ro) { ro.disconnect(); ro = null }
})

watch(() => [props.history, props.forecast, props.unit], schedule, { deep: true })
</script>

<style scoped>
.trend-chart-wrap {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.chart-canvas {
  position: relative;
  flex: 1;
  min-height: 0;
}
.chart-canvas svg { display: block; }
</style>
