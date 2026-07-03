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
  gap: 6px;
  flex-shrink: 0;
}

.tab-item {
  position: relative;
  padding: 7px 16px;
  border: 1px solid var(--edge);
  border-radius: 4px;
  clip-path: var(--clip);
  background: linear-gradient(to top,
    rgba(14, 42, 78, .00) 0%,
    rgba(14, 42, 78, .15) 30%,
    rgba(14, 42, 78, .45) 58%,
    rgba(14, 42, 78, .75) 82%,
    rgba(14, 42, 78, .90) 100%);
  -webkit-backdrop-filter: blur(16px) saturate(1.1);
  backdrop-filter: blur(16px) saturate(1.1);
  color: var(--muted);
  text-decoration: none;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: .12em;
  transition: all .18s;
  white-space: nowrap;
}
.tab-item:hover { color: #fff; border-color: var(--primary); }
.tab-item.active {
  color: #fff;
  border-color: var(--primary);
  background: rgba(30, 144, 255, .15);
  text-shadow: 0 0 10px rgba(30, 144, 255, .5);
  box-shadow: 0 0 12px rgba(30, 144, 255, .18);
}

.tab-underline {
  display: none;
}
</style>
