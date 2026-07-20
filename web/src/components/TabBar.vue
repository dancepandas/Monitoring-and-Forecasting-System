<template>
  <div class="banner-tabs">
    <router-link v-for="t in tabs" :key="t.to" :to="t.to" class="tab-item" :class="{ active: isActive(t) }">
      <span class="tab-label">{{ t.label }}</span>
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
  gap: 2px;
  flex-shrink: 0;
  padding: 0 4px;
}

.tab-item {
  position: relative;
  padding: 7px 16px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--ink-2);
  text-decoration: none;
  font-family: var(--display);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: .04em;
  transition: color .22s var(--ease-soft), background .22s var(--ease-soft), transform .25s var(--ease-spring);
  white-space: nowrap;
}

.tab-item:hover {
  color: var(--primary);
  background: rgba(14, 165, 233, .12);
  transform: translateY(-1px);
}

.tab-item.active {
  color: #FFFFFF;
  background: linear-gradient(180deg, var(--primary) 0%, var(--primary-600) 100%);
  box-shadow: 0 6px 16px rgba(30, 91, 141, .35), inset 0 1px 0 rgba(255, 255, 255, .35);
  animation: tab-pop .45s var(--ease-spring);
}
@keyframes tab-pop {
  0% { transform: scale(.86); }
  60% { transform: scale(1.05); }
  100% { transform: scale(1); }
}

.tab-label { position: relative; z-index: 1; }
</style>
