<template>
  <!--
    TerrainPanel.vue — 3D 地形 & 水系叠加控制面板
    悬浮在 Overview 页面上，提供地形/水系/等高线的开关和参数调节
    暗色驾驶舱风格，玻璃面板 + 终端标题
  -->
  <div class="terrain-panel" :class="{ collapsed }">
    <!-- 标题栏 -->
    <div class="panel-header" @click="collapsed = !collapsed">
      <span class="header-dot"></span>
      <span class="header-title">流域地形控制</span>
      <span class="header-chevron">{{ collapsed ? '▶' : '▼' }}</span>
    </div>

    <!-- 控制项 -->
    <div v-show="!collapsed" class="panel-body">
      <!-- 高精度地形开关 -->
      <div class="control-row">
        <label class="control-label">
          <span class="label-icon">⛰</span>
          高精度地形 (30m DEM)
        </label>
        <label class="toggle">
          <input
            type="checkbox"
            :checked="useCustomTerrain"
            @change="$emit('update:useCustomTerrain', $event.target.checked)"
          />
          <span class="toggle-track">
            <span class="toggle-thumb"></span>
          </span>
        </label>
      </div>

      <!-- 地形夸张 -->
      <div class="control-row" v-if="useCustomTerrain">
        <label class="control-label">
          <span class="label-icon">📐</span>
          地形夸张 <span class="value-tag">{{ terrainExaggeration.toFixed(1) }}x</span>
        </label>
        <div class="slider-wrap">
          <input
            type="range"
            min="1.0"
            max="3.0"
            step="0.1"
            :value="terrainExaggeration"
            @input="$emit('update:terrainExaggeration', parseFloat($event.target.value))"
            class="terrain-slider"
          />
          <div class="slider-ticks">
            <span>1x</span>
            <span>2x</span>
            <span>3x</span>
          </div>
        </div>
      </div>

      <div class="divider"></div>

      <!-- 水系叠加 -->
      <div class="control-row">
        <label class="control-label">
          <span class="label-icon">🌊</span>
          水系叠加 (河流/湖泊)
        </label>
        <label class="toggle">
          <input
            type="checkbox"
            :checked="showWaterSystem"
            @change="$emit('update:showWaterSystem', $event.target.checked)"
          />
          <span class="toggle-track">
            <span class="toggle-thumb"></span>
          </span>
        </label>
      </div>

      <!-- 等高线 -->
      <div class="control-row">
        <label class="control-label">
          <span class="label-icon">〰</span>
          等高线 (50m间隔)
        </label>
        <label class="toggle">
          <input
            type="checkbox"
            :checked="showContours"
            @change="$emit('update:showContours', $event.target.checked)"
          />
          <span class="toggle-track">
            <span class="toggle-thumb"></span>
          </span>
        </label>
      </div>

      <div class="divider"></div>

      <!-- 快速定位 -->
      <div class="control-row" style="flex-direction: column; align-items: flex-start; gap: 6px;">
        <label class="control-label">
          <span class="label-icon">📍</span>
          快速定位站点
        </label>
        <div class="station-chips">
          <button
            v-for="s in stations"
            :key="s.code"
            class="station-chip"
            @click="$emit('flyTo', s.code)"
          >
            {{ s.name.split('-').pop() }}
          </button>
          <button class="station-chip overview-chip" @click="$emit('flyToOverview')">
            总览
          </button>
        </div>
      </div>

      <!-- 重置视角 -->
      <div class="control-row" style="flex-direction: column; align-items: stretch; gap: 6px;">
        <button class="reset-view-btn" @click="$emit('reset-view')">
          <span class="label-icon">↺</span>
          重置视角
        </button>
      </div>

      <!-- 状态指示 -->
      <div class="status-bar">
        <span class="status-dot" :class="{ online: terrainReady }"></span>
        <span class="status-text">
          {{ terrainReady ? 'DEM地形已加载' : '使用默认地形' }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { STATIONS } from '../stations'

defineProps({
  useCustomTerrain: { type: Boolean, default: true },
  terrainExaggeration: { type: Number, default: 1.8 },
  showWaterSystem: { type: Boolean, default: true },
  showContours: { type: Boolean, default: false },
  terrainReady: { type: Boolean, default: false },
})

defineEmits([
  'update:useCustomTerrain',
  'update:terrainExaggeration',
  'update:showWaterSystem',
  'update:showContours',
  'flyTo',
  'flyToOverview',
  'reset-view',
])

const collapsed = ref(false)
const stations = STATIONS
</script>

<style scoped>
.terrain-panel {
  position: fixed;
  right: 16px;
  top: 120px;
  z-index: 20;
  width: 260px;
  background: radial-gradient(ellipse at top left, rgba(8, 47, 73, 0.75), rgba(2, 13, 20, 0.92));
  border: 1px solid rgba(34, 211, 238, 0.2);
  border-radius: 12px;
  box-shadow:
    0 0 60px rgba(8, 47, 73, 0.5),
    inset 0 1px 0 rgba(103, 232, 249, 0.08);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  transition: all 0.3s ease;
  font-family: 'SF Mono', 'JetBrains Mono', Consolas, monospace;
  user-select: none;
}

.terrain-panel.collapsed {
  width: 180px;
}

/* ── 标题栏 ── */
.panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  cursor: pointer;
  border-bottom: 1px solid rgba(34, 211, 238, 0.08);
}

.header-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #22D3EE;
  box-shadow: 0 0 8px #22D3EE;
  flex-shrink: 0;
}

.header-title {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: #A5F3FC;
  text-shadow: 0 0 20px rgba(34, 211, 238, 0.4);
  flex: 1;
}

.header-chevron {
  font-size: 10px;
  color: #64748B;
}

/* ── 面板体 ── */
.panel-body {
  padding: 12px 14px 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.divider {
  height: 1px;
  background: linear-gradient(to right, transparent, rgba(34, 211, 238, 0.15), transparent);
}

/* ── 控制行 ── */
.control-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.control-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #CBD5E1;
  white-space: nowrap;
}

.label-icon {
  font-size: 13px;
  flex-shrink: 0;
}

.value-tag {
  font-size: 10px;
  color: #22D3EE;
  background: rgba(34, 211, 238, 0.1);
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid rgba(34, 211, 238, 0.2);
}

/* ── 拨动开关 ── */
.toggle {
  position: relative;
  display: inline-block;
  cursor: pointer;
}

.toggle input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-track {
  display: block;
  width: 38px;
  height: 20px;
  border-radius: 10px;
  background: rgba(30, 41, 59, 0.8);
  border: 1px solid rgba(71, 85, 105, 0.5);
  transition: all 0.25s ease;
  position: relative;
}

.toggle input:checked + .toggle-track {
  background: rgba(8, 145, 178, 0.5);
  border-color: #22D3EE;
  box-shadow: 0 0 12px rgba(34, 211, 238, 0.2);
}

.toggle-thumb {
  position: absolute;
  top: 2px;
  left: 3px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #94A3B8;
  transition: all 0.25s ease;
}

.toggle input:checked + .toggle-track .toggle-thumb {
  left: 19px;
  background: #22D3EE;
  box-shadow: 0 0 6px rgba(34, 211, 238, 0.6);
}

/* ── 滑块 ── */
.slider-wrap {
  width: 100%;
  margin-top: 4px;
}

.terrain-slider {
  -webkit-appearance: none;
  width: 100%;
  height: 4px;
  border-radius: 2px;
  background: linear-gradient(to right, #0C4A6E, #22D3EE);
  outline: none;
  cursor: pointer;
}

.terrain-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #22D3EE;
  border: 2px solid #082F49;
  box-shadow: 0 0 10px rgba(34, 211, 238, 0.5);
  cursor: pointer;
}

.slider-ticks {
  display: flex;
  justify-content: space-between;
  font-size: 9px;
  color: #64748B;
  margin-top: 2px;
}

/* ── 站点芯片 ── */
.station-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.station-chip {
  font-family: inherit;
  font-size: 10px;
  padding: 3px 10px;
  border-radius: 6px;
  border: 1px solid rgba(34, 211, 238, 0.25);
  background: rgba(8, 47, 73, 0.5);
  color: #A5F3FC;
  cursor: pointer;
  transition: all 0.2s;
}

.station-chip:hover {
  background: rgba(8, 145, 178, 0.4);
  border-color: #22D3EE;
  box-shadow: 0 0 10px rgba(34, 211, 238, 0.3);
}

.overview-chip {
  border-color: rgba(168, 85, 247, 0.4);
  color: #C4B5FD;
}

.overview-chip:hover {
  background: rgba(126, 34, 206, 0.3);
  border-color: #A855F7;
  box-shadow: 0 0 10px rgba(168, 85, 247, 0.3);
}

/* ── 重置视角按钮 ── */
.reset-view-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-family: inherit;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid rgba(34, 211, 238, 0.35);
  background: rgba(8, 47, 73, 0.6);
  color: #A5F3FC;
  cursor: pointer;
  transition: all 0.2s ease;
}

.reset-view-btn:hover {
  background: rgba(8, 145, 178, 0.5);
  border-color: #22D3EE;
  box-shadow: 0 0 14px rgba(34, 211, 238, 0.35);
}

.reset-view-btn:active {
  transform: scale(0.98);
}

/* ── 状态栏 ── */
.status-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding-top: 6px;
  border-top: 1px solid rgba(34, 211, 238, 0.06);
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #64748B;
  flex-shrink: 0;
}

.status-dot.online {
  background: #22D3EE;
  box-shadow: 0 0 6px rgba(34, 211, 238, 0.6);
  animation: pulse-dot 2s infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.status-text {
  font-size: 10px;
  color: #94A3B8;
}
</style>
