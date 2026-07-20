<template>
  <!--
    TerrainPanel.vue — 3D 地形控制面板（精简版）
    仅保留重置视角按钮
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
      <div class="control-row" style="flex-direction: column; align-items: stretch; gap: 6px;">
        <button class="reset-view-btn" @click="$emit('reset-view')">
          <span class="label-icon">↺</span>
          重置视角
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineEmits(['reset-view'])

const collapsed = ref(false)
</script>

<style scoped>
.terrain-panel {
  position: fixed;
  right: 16px;
  top: 120px;
  z-index: 20;
  width: 180px;
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
</style>
