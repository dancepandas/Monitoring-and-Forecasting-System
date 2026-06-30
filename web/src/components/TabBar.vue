<template>
  <nav class="tab-bar">
    <router-link v-for="t in tabs" :key="t.to" :to="t.to" class="tab-item" :class="{ active: isActive(t) }">
      <span class="tab-label">{{ t.label }}</span>
      <i class="tab-underline"></i>
    </router-link>
    <div class="tab-spacer"></div>
    <button v-if="isAdmin" class="admin-gear" @click="showAdminMenu = !showAdminMenu" title="管理">
      ⚙
      <transition name="admin-pop">
        <div v-if="showAdminMenu" class="admin-menu" @click.stop>
          <router-link to="/admin/users" class="admin-link" @click="showAdminMenu = false">用户管理</router-link>
          <router-link to="/admin/settings" class="admin-link" @click="showAdminMenu = false">系统设置</router-link>
        </div>
      </transition>
    </button>
  </nav>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../store/auth'

const route = useRoute()
const auth = useAuthStore()
const showAdminMenu = ref(false)

const tabs = [
  { to: '/', name: 'Overview', label: '态势' },
  { to: '/warnings', name: 'Warnings', label: '预警' },
  { to: '/devices', name: 'Devices', label: '视频' },
  { to: '/reports', name: 'Reports', label: '日报' },
]

const isAdmin = computed(() => auth.role === 'admin' || auth.role === 'super_admin')

function isActive(t) {
  if (t.to === '/') return route.name === 'Overview'
  return route.name === t.name || route.path.startsWith(t.to)
}
</script>

<style scoped>
.tab-bar {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 0 10px;
  border: 1px solid var(--edge);
  border-radius: 4px;
  clip-path: var(--clip);
  background: var(--glass);
  -webkit-backdrop-filter: blur(14px);
  backdrop-filter: blur(14px);
  background-attachment: fixed;
  min-height: 38px;
}

.tab-item {
  position: relative;
  padding: 7px 22px;
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

.tab-spacer { flex: 1; }

.admin-gear {
  position: relative;
  border: 0;
  background: transparent;
  color: var(--muted);
  font-size: 16px;
  cursor: pointer;
  padding: 4px 8px;
  transition: color .15s;
}
.admin-gear:hover { color: #fff; }

.admin-menu {
  position: absolute;
  right: 0;
  top: 100%;
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px;
  border: 1px solid var(--edge);
  border-radius: 6px;
  background: rgba(12, 36, 68, .92);
  backdrop-filter: blur(14px);
  box-shadow: var(--shadow-soft);
  z-index: 100;
  min-width: 120px;
}
.admin-link {
  padding: 6px 14px;
  color: var(--ink-2);
  text-decoration: none;
  font-size: 12px;
  border-radius: 4px;
  transition: background .15s;
}
.admin-link:hover { background: var(--chip); color: #fff; }

.admin-pop-enter-active, .admin-pop-leave-active { transition: all .15s; }
.admin-pop-enter-from, .admin-pop-leave-to { opacity: 0; transform: translateY(-4px); }
</style>