<template>
  <div class="hydro-map" ref="wrap">
    <svg ref="svg" class="hydro-svg" :viewBox="viewBox" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <defs>
        <radialGradient id="terrainBg" cx="50%" cy="40%" r="75%">
          <stop offset="0%" stop-color="#ECEFF2" />
          <stop offset="60%" stop-color="#DEE3E8" />
          <stop offset="100%" stop-color="#D0D6DC" />
        </radialGradient>
        <linearGradient id="waterFill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stop-color="#BDECFF" />
          <stop offset="100%" stop-color="#A6D2EE" />
        </linearGradient>
        <filter id="waterShadow" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="1" stdDeviation="1.2" flood-color="#0070A8" flood-opacity="0.12" />
        </filter>
        <pattern id="graticule" width="40" height="40" patternUnits="userSpaceOnUse">
          <path d="M40 0H0V40" fill="none" stroke="rgba(30,58,95,.07)" stroke-width="1" />
        </pattern>
      </defs>

      <!-- 地形底 -->
      <rect :x="vbX" :y="vbY" :width="vbW" :height="vbH" fill="url(#terrainBg)" />
      <rect :x="vbX" :y="vbY" :width="vbW" :height="vbH" fill="url(#graticule)" />

      <!-- 行政区划底图（区县填充 + 境界，垫在水系之下） -->
      <g class="layer-admin">
        <path v-for="(d, i) in adminPaths" :key="'ad'+i" :d="d"
              :fill="adminPalette[i % adminPalette.length]" fill-opacity="0.55"
              stroke="rgba(15, 23, 42, .28)" stroke-width="0.8" stroke-linejoin="round" />
      </g>

      <!-- 水体块（多边形） -->
      <g class="layer-water" filter="url(#waterShadow)">
        <path v-for="(d, i) in waterPaths" :key="'w'+i" :d="d" fill="url(#waterFill)" fill-opacity="0.9" stroke="#0070A8" stroke-width="0.7" stroke-opacity="0.7" />
      </g>

      <!-- 河流线 -->
      <g class="layer-river">
        <path v-for="(d, i) in riverPaths.main" :key="'rm'+i" :d="d" fill="none" stroke="#0070A8" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" stroke-opacity="0.95" />
        <path v-for="(d, i) in riverPaths.stream" :key="'rs'+i" :d="d" fill="none" stroke="#4A9DD0" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" stroke-opacity="0.9" />
      </g>

      <!-- 行政区名称（置于水系之上，确保文字不被水体压盖） -->
      <g class="layer-admin-labels">
        <text v-for="(c, i) in adminLabels" :key="'al'+i" class="admin-label"
              :x="c.x" :y="c.y">{{ c.name }}</text>
      </g>

      <!-- 背景点击区：点空白处取消钉选（垫在站点之下，仅站点不命中时接收点击） -->
      <rect class="map-bg-hit" :x="vbX" :y="vbY" :width="vbW" :height="vbH" @click="$emit('background-click')" />

      <!-- 站点 -->
      <g class="layer-station">
        <g v-for="s in projectedStations" :key="s.code" :transform="`translate(${s.x} ${s.y})`">
          <g class="station-g" :class="['st-'+s.level, { active: s.active }]"
             tabindex="0" role="button" :aria-label="`${s.name} 站点，回车查看详情`"
             @click="$emit('station-click', s.raw)"
             @keydown.enter.prevent="$emit('station-click', s.raw)"
             @mouseenter="onStationEnter($event, s)"
             @mouseleave="onStationLeave">
            <circle v-if="s.active" class="st-active-ring" r="21" />
            <g class="st-mark">
              <circle class="st-pulse" r="26" />
              <circle class="st-ring" r="15" />
              <circle class="st-core" r="9" />
              <!-- 实时水位角标（站点正下方，按状态着色） -->
              <g v-if="s.data && s.data.level != null" class="st-level-pill" :class="'lv-'+s.level" :transform="`translate(0 ${s.active ? 32 : 30})`">
                <rect class="pill-bg" :x="-levelPillWidth(s)/2" y="-11" :width="levelPillWidth(s)" height="22" rx="11" />
                <text class="pill-text" x="0" y="4">{{ Number(s.data.level).toFixed(2) }} m</text>
              </g>
            </g>
            <!-- 数据异常角标（紫色 ⚠，挂在站点右上角） -->
            <g v-if="s.data && s.data.anomaly && s.data.anomaly.flagged" class="st-anomaly-flag">
              <circle cx="12" cy="-12" r="7.5" fill="#7C3AED" stroke="#fff" stroke-width="1.8" />
              <text x="12" y="-8.5" text-anchor="middle" fill="#fff" font-size="10" font-weight="700" font-family="var(--sans)">!</text>
            </g>
            <g class="st-label-g">
              <rect class="st-label-bg" :x="labelX(s)" y="-18" :width="labelWidth(s)" height="36" rx="18" />
              <text class="st-label" :x="labelTextX(s)" y="8">{{ s.name }}</text>
            </g>
          </g>
        </g>
      </g>
    </svg>

    <!-- 图例 -->
    <div class="hydro-legend">
      <span><i class="lg lg-water"></i>水体</span>
      <span><i class="lg lg-river"></i>河流</span>
      <span><i class="lg lg-admin"></i>区县</span>
      <span><i class="lg lg-st ok"></i>正常</span>
      <span><i class="lg lg-st warn"></i>预警</span>
      <span><i class="lg lg-st danger"></i>告警</span>
      <span><i class="lg lg-anomaly"></i>数据异常</span>
    </div>

    <!-- 站点悬浮信息卡（Teleport 到 #app 外部的 #popups，彻底脱离所有 stacking context） -->
    <Teleport to="#popups">
      <div v-if="hovered" class="st-tooltip" :class="{ below: hovered.below }" :style="{ left: hovered.px + 'px', top: hovered.py + 'px' }">
      <div class="stt-head">
        <b>{{ hovered.name }}</b>
        <span class="stt-badge" :class="'lv-'+hovered.statusTag">{{ statusLabel(hovered.statusTag) }}</span>
      </div>
      <div class="stt-stats">
        <div class="stt-stat"><span>水位</span><b>{{ hovered.level != null ? Number(hovered.level).toFixed(2) : '—' }}<small>m</small></b></div>
        <div class="stt-stat"><span>流量</span><b>{{ hovered.flow != null ? Number(hovered.flow).toFixed(0) : '—' }}<small>m³/s</small></b></div>
        <div class="stt-stat"><span>更新</span><b>{{ fmtTimeShort(hovered.time) }}</b></div>
      </div>
      <div v-if="hovered.anomaly && hovered.anomaly.flagged" class="stt-anomaly">
        <span class="stt-anomaly-label">⚠ 数据存疑</span>
        <p>{{ hovered.anomaly.reason }}</p>
      </div>
      <div class="stt-foot">点击查看详情 · 监测视频</div>
    </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { STATIONS } from '../stations'

const props = defineProps({
  // code -> level ('ok'|'warn'|'danger') 用于站点着色
  stationLevel: { type: Object, default: () => ({}) },
  // code -> { level, flow, time } 每站实时数据（悬浮卡 + 水位角标）
  stationData: { type: Object, default: () => ({}) },
  // 当前钉选/轮播站 code（高亮焦点）
  activeCode: { type: String, default: '' },
})
defineEmits(['station-click', 'background-click'])

const wrap = ref(null)
const hydro = ref({ rivers: [], water: [] })
const stationsGeo = ref([]) // [{code,name,lon,lat}]
const admin = ref([]) // [{rings, name, cx, cy}] 区县行政底图
// 行政区划分区设色衬底：冷调低饱和中性灰（与灰地形统一画布，避免暖米色"发脏"）。
// 区县用差异衬色区分（行政区划图惯例 / GB 制图），但色相统一在冷灰，让蓝色水体当主角。
const adminPalette = ['#EEF1F4', '#E7EBEF', '#F1F3F5', '#E3E7EC', '#EDF0F3', '#E5E9ED']

// 以「四站实际范围」为框（不再被整张水系数据撑大），按容器宽高比补窄边留白，
// 保证 slice 只裁左右、不裁站点。水系数据仍渲染，仅作衬底、超框自动裁掉。
const containerAspect = ref(2.4)   // 容器宽:高（computeLetterbox 实测更新；默认偏宽防裁站点）
const PAD_FRAC = 0.18       // 各向留白比例
const LON_KM = 100, LAT_KM = 111  // 25.8°N 附近经纬度→公里近似

const bbox = computed(() => {
  let minLon = 180, minLat = 90, maxLon = -180, maxLat = -90
  const feed = (lon, lat) => {
    if (lon < minLon) minLon = lon
    if (lat < minLat) minLat = lat
    if (lon > maxLon) maxLon = lon
    if (lat > maxLat) maxLat = lat
  }
  // 站点为种子：STATIONS 静态常量立即可用（无加载闪烁），stationsGeo 到位后同等
  const seed = stationsGeo.value.length
    ? stationsGeo.value
    : STATIONS.map(s => ({ lon: s.lon, lat: s.lat }))
  seed.forEach(s => feed(s.lon, s.lat))
  if (minLon === 180) return { minLon: 112.95, minLat: 25.70, maxLon: 113.10, maxLat: 25.84 }

  // 基础留白
  const spanLon = maxLon - minLon, spanLat = maxLat - minLat
  minLon -= spanLon * PAD_FRAC; maxLon += spanLon * PAD_FRAC
  minLat -= spanLat * PAD_FRAC; maxLat += spanLat * PAD_FRAC

  // 补到容器宽高比：只加窄边，站点跨度方向不动 → 站点不会被裁
  const ar = containerAspect.value
  const wKm = (maxLon - minLon) * LON_KM
  const hKm = (maxLat - minLat) * LAT_KM
  if (wKm / hKm < ar) {
    const addDeg = (hKm * ar - wKm) / LON_KM / 2
    minLon -= addDeg; maxLon += addDeg
  } else {
    const addDeg = (wKm / ar - hKm) / LAT_KM / 2
    minLat -= addDeg; maxLat += addDeg
  }
  return { minLon, minLat, maxLon, maxLat }
})

const W = 1000, H = 1000 // viewBox 逻辑尺寸
const vbX = ref(0), vbY = ref(0), vbW = ref(1000), vbH = ref(1000)
const viewBox = computed(() => `${vbX.value} ${vbY.value} ${vbW.value} ${vbH.value}`)

// 投影：lon/lat -> viewBox x/y（等比填充，含 letterbox）
function project(lon, lat) {
  const b = bbox.value
  const spanLon = b.maxLon - b.minLon || 1
  const spanLat = b.maxLat - b.minLat || 1
  const x = ((lon - b.minLon) / spanLon) * vbW.value
  const y = vbH.value - ((lat - b.minLat) / spanLat) * vbH.value // y 翻转
  return [x, y]
}

onMounted(async () => {
  // 加载简化水系
  try {
    const res = await fetch('/geo/chenzhou_hydro_simple.geojson')
    const data = await res.json()
    const rivers = [], water = []
    const extractRings = (geom) => {
      // 返回 [[ [x,y],... ], ...] —— 一个多边形可能含外环+洞
      if (geom.type === 'Polygon') return geom.coordinates
      if (geom.type === 'MultiPolygon') return geom.coordinates.flat()
      return []
    }
    for (const f of data.features) {
      const g = f.geometry
      if (!g) continue
      const kind = f.properties?._kind
      if (kind === 'water' || g.type === 'Polygon' || g.type === 'MultiPolygon') {
        const rings = extractRings(g).map(r => r.map(c => [c[0], c[1]]))
        if (rings.length) water.push({ rings })
      } else {
        const lines = g.type === 'LineString' ? [g.coordinates] : g.coordinates
        lines.forEach(l => {
          if (!l || l.length < 2) return
          const w = f.properties?.width || ''
          const m = String(w).match(/(\d+)/)
          const isMain = m ? parseInt(m[1]) >= 30 : false
          rivers.push({ coords: l.map(c => [c[0], c[1]]), main: isMain })
        })
      }
    }
    hydro.value = { rivers, water }
  } catch (e) {
    console.warn('[HydroMap] load hydro failed', e)
  }
  // 站点坐标（来自本地精确坐标）
  try {
    const res = await fetch('/geo/station_locations.geojson')
    const data = await res.json()
    stationsGeo.value = (data.features || []).map(f => ({
      code: f.properties.station_code,
      name: f.properties.station_name,
      lon: f.geometry.coordinates[0],
      lat: f.geometry.coordinates[1],
    }))
  } catch (e) {
    // 退化：用 STATIONS 静态坐标（如果有）
    stationsGeo.value = []
  }
  // 行政区划底图（DataV 郴州区县，垫在水系之下）
  try {
    const res = await fetch('/geo/chenzhou_admin.geojson')
    const data = await res.json()
    admin.value = (data.features || []).map(f => {
      const g = f.geometry || {}
      const props = f.properties || {}
      const polys = g.type === 'Polygon' ? [g.coordinates] : (g.coordinates || [])
      const rings = []
      for (const poly of polys) for (const ring of poly) rings.push(ring.map(c => [c[0], c[1]]))
      // 标签位置：优先 DataV center，否则最大环坐标均值
      let cx, cy
      if (Array.isArray(props.center) && props.center.length >= 2) {
        cx = props.center[0]; cy = props.center[1]
      } else if (rings.length) {
        let big = rings[0]
        for (const r of rings) if (r.length > big.length) big = r
        cx = big.reduce((s, c) => s + c[0], 0) / big.length
        cy = big.reduce((s, c) => s + c[1], 0) / big.length
      }
      return { rings, name: (props.name || '').replace(/[区县市]$/, ''), cx, cy }
    })
  } catch (e) {
    console.warn('[HydroMap] load admin failed', e)
  }
  computeLetterbox()
  window.addEventListener('resize', computeLetterbox)
})

function computeLetterbox() {
  // viewBox 跟随容器真实宽高比，让 slice 完美贴合、不裁站点；bbox 也用同一比例
  const el = wrap.value
  const ar = (el && el.clientWidth > 0 && el.clientHeight > 0)
    ? el.clientWidth / el.clientHeight
    : 2.4
  containerAspect.value = ar
  vbH.value = 1000
  vbW.value = Math.round(1000 * ar)
  vbX.value = 0; vbY.value = 0
}

// ── 路径生成 ──
const waterPaths = computed(() => {
  return hydro.value.water.map(poly => {
    return poly.rings.map(ring => {
      const pts = ring.map(([x, y]) => project(x, y))
      if (pts.length < 3) return ''
      const [sx, sy] = pts[0]
      let d = `M${sx.toFixed(1)} ${sy.toFixed(1)}`
      for (let i = 1; i < pts.length; i++) d += `L${pts[i][0].toFixed(1)} ${pts[i][1].toFixed(1)}`
      d += 'Z'
      return d
    }).filter(Boolean).join(' ')
  })
})

const riverPaths = computed(() => {
  const main = [], stream = []
  hydro.value.rivers.forEach(r => {
    const pts = r.coords.map(([x, y]) => project(x, y))
    if (pts.length < 2) return
    let d = `M${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`
    for (let i = 1; i < pts.length; i++) d += `L${pts[i][0].toFixed(1)} ${pts[i][1].toFixed(1)}`
    if (r.main) main.push(d); else stream.push(d)
  })
  return { main, stream }
})

// 行政区划：区县多边形路径 + 名称标注（垫在水系之下）
const adminPaths = computed(() => {
  return admin.value.map(d => {
    return d.rings.map(ring => {
      const pts = ring.map(([x, y]) => project(x, y))
      if (pts.length < 3) return ''
      const [sx, sy] = pts[0]
      let dd = `M${sx.toFixed(1)} ${sy.toFixed(1)}`
      for (let i = 1; i < pts.length; i++) dd += `L${pts[i][0].toFixed(1)} ${pts[i][1].toFixed(1)}`
      dd += 'Z'
      return dd
    }).filter(Boolean).join(' ')
  })
})
const adminLabels = computed(() => {
  const b = bbox.value
  const inFrame = (lon, lat) => lon >= b.minLon && lon <= b.maxLon && lat >= b.minLat && lat <= b.maxLat
  return admin.value
    .map(d => {
      // 标签落在「画框内可见部分」的质心，这样只切进来一片的区县也能被标名
      let sx = 0, sy = 0, n = 0
      for (const ring of d.rings) for (const [x, y] of ring) if (inFrame(x, y)) { sx += x; sy += y; n++ }
      if (!n) return null
      const [px, py] = project(sx / n, sy / n)
      return { name: d.name, x: px, y: py }
    })
    .filter(Boolean)
})

// 站点投影
const projectedStations = computed(() => {
  return stationsGeo.value.map(s => {
    const [x, y] = project(s.lon, s.lat)
    const lvl = props.stationLevel?.[s.code] || 'ok'
    const data = props.stationData?.[s.code] || null
    return { ...s, x, y, level: lvl, data, active: props.activeCode === s.code, raw: s }
  })
})

// 站点标签：避免出界，根据 x 位置决定左/右偏移
function labelTransform(s) { return '' }
// 站名统一置于站点右侧：胶囊左边缘距圆心 = 2/3 图标直径（直径=2×环半径15=30 → 偏移 20）
function labelX(s) { return 20 }
function labelWidth(s) {
  return Math.max(76, s.name.length * 28 + 24)
}
function labelTextX(s) { return 29 }

// ── 悬浮信息卡 + 水位角标 ──
const hovered = ref(null)
function statusLabel(tag) {
  return tag === 'danger' ? '告警' : tag === 'warn' ? '预警' : '正常'
}
function levelPillWidth(s) {
  const v = (s.data && s.data.level != null) ? Number(s.data.level).toFixed(2) + ' m' : ''
  return Math.max(50, v.length * 7.2 + 18)
}
function fmtTimeShort(t) {
  if (!t) return '—'
  const d = new Date(t)
  if (isNaN(d.getTime())) return '—'
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
function onStationEnter(e, s) {
  const core = e.currentTarget.querySelector && e.currentTarget.querySelector('.st-core')
  const anchor = core || e.currentTarget
  if (!anchor) return
  const r = anchor.getBoundingClientRect()
  /* position:fixed 使用视口坐标，不受父级 overflow:hidden 裁剪 */
  hovered.value = {
    code: s.code, name: s.name,
    level: s.data?.level, flow: s.data?.flow, time: s.data?.time,
    anomaly: s.data?.anomaly,
    statusTag: s.level,
    px: r.left + r.width / 2,
    py: r.top + r.height / 2,
    below: (r.top - (wrap.value ? wrap.value.getBoundingClientRect().top : 0)) < 140,   // 靠近地图顶部 → 向下展开
  }
}
function onStationLeave() { hovered.value = null }
</script>

<style scoped>
.hydro-map { position: relative; width: 100%; height: 100%; overflow: hidden; }
.hydro-svg { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }

.layer-water { stroke-linejoin: round; }
.layer-admin path { transition: fill .15s var(--ease-soft); }
.admin-label {
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 600;
  fill: #1A1A1A;
  text-anchor: middle;
  dominant-baseline: central;
  letter-spacing: .04em;
  paint-order: stroke;
  stroke: rgba(255, 255, 255, .85);
  stroke-width: 2.5px;
  stroke-linejoin: round;
  pointer-events: none;
}

/* 站点 */
.station-g { cursor: pointer; }
.st-pulse { fill: none; stroke: currentColor; stroke-width: 3; opacity: 0; }
.st-ring { fill: #fff; stroke-width: 4; filter: drop-shadow(0 2px 4px rgba(15, 23, 42, .18)); }
.st-core { stroke: #fff; stroke-width: 3; }

.station-g.st-ok { color: #16A34A; }
.station-g.st-ok .st-ring { stroke: #16A34A; }
.station-g.st-ok .st-core { fill: #16A34A; }

.station-g.st-warn { color: #EA580C; }
.station-g.st-warn .st-ring { stroke: #EA580C; }
.station-g.st-warn .st-core { fill: #EA580C; }

.station-g.st-danger { color: #DC2626; }
.station-g.st-danger .st-ring { stroke: #DC2626; }
.station-g.st-danger .st-core { fill: #DC2626; }

/* 预警脉冲 */
.station-g.st-warn .st-pulse { stroke: #EA580C; animation: stpulse 2.4s ease-out infinite; }
.station-g.st-danger .st-pulse { stroke: #DC2626; animation: stpulse 1.5s ease-out infinite; }
@keyframes stpulse {
  0% { transform: scale(0.7); opacity: 0.7; }
  100% { transform: scale(2.2); opacity: 0; }
}

.st-label-bg { fill: rgba(255, 255, 255, .92); stroke: rgba(30, 58, 95, .18); stroke-width: 1.6; }
.st-label { font-family: var(--sans); font-size: 24px; fill: #1E293B; font-weight: 600; }
.station-g:hover .st-label-bg { fill: #fff; }
.station-g:hover .st-core { filter: drop-shadow(0 0 4px currentColor); }

/* 图例 */
.hydro-legend {
  position: absolute; left: 12px; bottom: 12px;
  display: flex; flex-wrap: wrap; gap: 10px;
  padding: 8px 12px;
  border-radius: var(--radius-md);
  background: var(--bg-2);
  border: 1px solid var(--line);
  box-shadow: var(--shadow-1);
  font-size: 11px; color: var(--ink-2);
  font-family: var(--sans);
}
.hydro-legend span { display: inline-flex; align-items: center; gap: 5px; }
.lg { width: 12px; height: 12px; border-radius: 3px; display: inline-block; }
.lg-water { background: linear-gradient(180deg, #BDECFF, #A6D2EE); }
.lg-river { background: #0070A8; height: 3px; border-radius: 2px; align-self: center; }
.lg-admin { background: #EDE7DC; border: 1px solid #333; }
.lg-st { border-radius: 50%; }
.lg-st.ok { background: #16A34A; }
.lg-st.warn { background: #EA580C; }
.lg-st.danger { background: #DC2626; }

/* ── 站点交互增强 ── */
.map-bg-hit { fill: transparent; cursor: default; }
.station-g { cursor: pointer; outline: none; }
.st-mark {
  transition: transform .15s var(--ease-soft);
  transform-box: fill-box;
  transform-origin: center;
}
.station-g:hover .st-mark,
.station-g:focus-visible .st-mark { transform: scale(1.14); }
.station-g:focus-visible .st-ring { stroke-width: 5; }
.station-g:focus-visible:focus { outline: none; }

/* 当前钉选/轮播站：旋转虚线焦点环 */
.st-active-ring {
  fill: none; stroke: var(--primary); stroke-width: 2;
  stroke-dasharray: 4 4; opacity: .85;
  transform-box: fill-box; transform-origin: center;
  animation: stspin 10s linear infinite;
}
@keyframes stspin { to { transform: rotate(360deg); } }

/* 实时水位角标（站点正下方，按状态着色） */
.st-level-pill .pill-bg { stroke: rgba(0, 0, 0, .06); stroke-width: 1; }
.st-level-pill .pill-text {
  font-family: var(--mono); font-size: 12px; font-weight: 600;
  text-anchor: middle; dominant-baseline: middle;
}
.st-level-pill.lv-ok .pill-bg { fill: rgba(22, 163, 74, .14); }
.st-level-pill.lv-ok .pill-text { fill: #15803D; }
.st-level-pill.lv-warn .pill-bg { fill: rgba(234, 88, 12, .16); }
.st-level-pill.lv-warn .pill-text { fill: #C2410C; }
.st-level-pill.lv-danger .pill-bg { fill: rgba(220, 38, 38, .16); }
.st-level-pill.lv-danger .pill-text { fill: #B91C1C; }

/* 站点悬浮信息卡（position:fixed 脱离父级 overflow:hidden 裁剪） */
.st-tooltip {
  position: fixed; z-index: 99999;
  transform: translate(-50%, calc(-100% - 16px));
  min-width: 196px;
  padding: 10px 12px 9px;
  background: var(--glass-strong);
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-3);
  pointer-events: none;
  animation: tt-in .12s var(--ease-soft);
}
.st-tooltip.below { transform: translate(-50%, 18px); }
.st-tooltip::after {
  content: ""; position: absolute; left: 50%; bottom: -5px;
  width: 10px; height: 10px; transform: translateX(-50%) rotate(45deg);
  background: var(--glass-strong);
  border-right: 1px solid var(--line); border-bottom: 1px solid var(--line);
}
.st-tooltip.below::after {
  bottom: auto; top: -5px;
  border: 0; border-left: 1px solid var(--line); border-top: 1px solid var(--line);
}
@keyframes tt-in { from { opacity: 0; transform: translate(-50%, calc(-100% - 10px)); } to { opacity: 1; } }
.stt-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.stt-head b { font-family: var(--sans); font-size: 13px; font-weight: 600; color: var(--ink); }
.stt-badge { font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 999px; color: #fff; }
.stt-badge.lv-ok { background: #16A34A; }
.stt-badge.lv-warn { background: #EA580C; }
.stt-badge.lv-danger { background: #DC2626; }
.stt-stats { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
.stt-stat span { display: block; font-size: 10px; color: var(--muted); margin-bottom: 2px; }
.stt-stat b { font-family: var(--display); font-size: 15px; font-weight: 600; color: var(--ink); }
.stt-stat b small { font-size: 10px; color: var(--muted); font-weight: 500; margin-left: 2px; }
.stt-foot { margin-top: 8px; font-size: 10.5px; color: var(--primary); font-weight: 500; }

/* 数据异常：悬浮卡内的存疑说明 */
.stt-anomaly {
  margin-top: 8px; padding: 6px 8px;
  border-radius: var(--radius-sm);
  background: var(--anomaly-soft);
  border-left: 3px solid var(--anomaly);
}
.stt-anomaly-label { font-size: 10.5px; font-weight: 700; color: var(--anomaly); }
.stt-anomaly p { margin: 3px 0 0; font-size: 11px; line-height: 1.5; color: var(--ink-2); }

/* 图例：数据异常紫点 */
.lg-anomaly { width: 12px; height: 12px; border-radius: 50%; background: #7C3AED; display: inline-block; }
</style>

<!-- Teleport 到 #popups 后 scoped 样式失效，以下为非 scoped 全局样式 -->
<style>
.st-tooltip {
  position: fixed !important;
  z-index: 2147483647 !important;
  transform: translate(-50%, calc(-100% - 16px));
  min-width: 196px;
  padding: 10px 12px 9px;
  background: var(--glass-strong);
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-3);
  pointer-events: none;
  animation: tt-in-global .12s ease-out;
}
.st-tooltip.below { transform: translate(-50%, 18px); }
.st-tooltip::after {
  content: ""; position: absolute; left: 50%; bottom: -5px;
  width: 10px; height: 10px; transform: translateX(-50%) rotate(45deg);
  background: var(--glass-strong);
  border-right: 1px solid var(--line); border-bottom: 1px solid var(--line);
}
.st-tooltip.below::after {
  bottom: auto; top: -5px;
  border: 0; border-left: 1px solid var(--line); border-top: 1px solid var(--line);
}
@keyframes tt-in-global { from { opacity: 0; transform: translate(-50%, calc(-100% - 10px)); } to { opacity: 1; } }
.stt-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.stt-head b { font-family: var(--sans); font-size: 13px; font-weight: 600; color: var(--ink); }
.stt-badge { font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 999px; color: #fff; }
.stt-badge.lv-ok { background: #16A34A; }
.stt-badge.lv-warn { background: #EA580C; }
.stt-badge.lv-danger { background: #DC2626; }
.stt-stats { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
.stt-stat span { display: block; font-size: 10px; color: var(--muted); margin-bottom: 2px; }
.stt-stat b { font-family: var(--display); font-size: 15px; font-weight: 600; color: var(--ink); }
.stt-stat b small { font-size: 10px; color: var(--muted); font-weight: 500; margin-left: 2px; }
.stt-foot { margin-top: 8px; font-size: 10.5px; color: var(--primary); font-weight: 500; }
.stt-anomaly {
  margin-top: 8px; padding: 6px 8px;
  border-radius: var(--radius-sm);
  background: var(--anomaly-soft);
  border-left: 3px solid var(--anomaly);
}
.stt-anomaly-label { font-size: 10.5px; font-weight: 700; color: var(--anomaly); }
.stt-anomaly p { margin: 3px 0 0; font-size: 11px; line-height: 1.5; color: var(--ink-2); }
</style>

