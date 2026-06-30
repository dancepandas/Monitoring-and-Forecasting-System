<template>
  <div class="banner-tabs">
    <router-link v-for="t in tabs" :key="t.to" :to="t.to" class="tab-item" :class="{ active: isActive(t) }">
      <span class="tab-label">{{ t.label }}</span>
      <i class="tab-underline"></i>
    </router-link>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const tabs = [
  { to: '/', name: 'Overview', label: '态势' },
  { to: '/warnings', name: 'Warnings', label: '预警' },
  { to: '/devices', name: 'Devices', label: '视频' },
  { to: '/reports', name: 'Reports', label: '日报' },
]

function isActive(t) {
  if (t.to === '/') return route.name === 'Overview'
  return route.name === t.name || route.path.startsWith(t.to)
}
</script>

<style scoped>
.banner-tabs {
  display: flex;
  align-items: center;
  gap: 0;
  flex-shrink: 0;
}

.tab-item {
  position: relative;
  padding: 7px 18px;
  color: var(--muted);
  text-decoration: none;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: .12em;
  transition: color .18s;
  white-space: nowrap;
}
.tab-item:hover { color: #fff; }
.tab-item.active { color: #fff; text-shadow: 0 0 10px rgba(30, 144, 255, .5); }

.tab-underline {
  position: absolute;
  left: 50%;
  bottom: 0;
  width: 0;
  height: 2px;
  background: var(--primary);
  box-shadow: 0 0 8px rgba(30, 144, 255, .6);
  transform: translateX(-50%);
  transition: width .2s ease;
}
.tab-item.active .tab-underline { width: 60%; }
</style>
