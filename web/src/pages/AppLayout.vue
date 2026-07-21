<template>
  <div class="app-shell">
    <!-- 顶部细导航条：朴素、干净、上手即懂 -->
    <header class="app-topbar">
      <div class="tb-brand">
        <span class="tb-mark"></span>
        <span class="tb-name">郴州水文监测预报</span>
      </div>

      <nav class="tb-nav">
        <router-link v-for="n in nav" :key="n.to" :to="n.to" class="tb-tab" :class="{ active: isActive(n) }">
          {{ n.label }}
        </router-link>
      </nav>

      <div class="tb-meta">
        <SystemStatus />
        <span class="tb-user">{{ auth.user?.display_name || auth.user?.username || '—' }}</span>
        <button v-if="isAdmin" class="tb-icon" @click="showAdmin = !showAdmin" title="管理">⚙
          <transition name="admin-pop">
            <div v-if="showAdmin" class="tb-menu" @click.stop>
              <router-link to="/admin/users" class="tb-menu-link" @click="showAdmin = false">用户管理</router-link>
              <router-link to="/admin/settings" class="tb-menu-link" @click="showAdmin = false">系统设置</router-link>
            </div>
          </transition>
        </button>
        <button class="tb-icon" @click="handleLogout" title="退出登录">⏻</button>
      </div>
    </header>

    <main class="app-main">
      <div class="app-main-scroll" :data-page="$route.name">
        <router-view />
        <ContextMenu v-if="$route.name !== 'Agent'" />
      </div>
    </main>

    <VoiceAssistant />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import SystemStatus from '../components/SystemStatus.vue'
import ContextMenu from '../components/ContextMenu.vue'
import VoiceAssistant from '../components/VoiceAssistant.vue'
import { useAuthStore } from '../store/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const showAdmin = ref(false)
const isAdmin = computed(() => auth.role === 'admin' || auth.role === 'super_admin')

const nav = [
  { to: '/', name: 'Overview', label: '态势总览' },
  { to: '/warnings', name: 'Warnings', label: '预警处置' },
  { to: '/devices', name: 'Devices', label: '视频巡检' },
  { to: '/reports', name: 'Reports', label: '日报归档' },
]

function isActive(n) {
  if (n.to === '/') return route.name === 'Overview'
  return route.name === n.name || route.path.startsWith(n.to)
}

function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.app-shell {
  display: grid;
  grid-template-rows: 52px 1fr;
  height: 100vh;
  min-height: 0;
  background: var(--bg);
}

/* ── 顶部细导航 ── */
.app-topbar {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 0 20px;
  background: var(--bg-2);
  border-bottom: 1px solid var(--line);
  box-shadow: 0 1px 0 rgba(16, 24, 40, .02);
  z-index: 20;
}
.tb-brand {
  display: flex;
  align-items: center;
  gap: 9px;
  flex-shrink: 0;
}
.tb-mark {
  width: 24px; height: 24px;
  border-radius: 6px;
  background: linear-gradient(135deg, var(--primary), var(--accent));
  flex-shrink: 0;
}
.tb-name {
  font-family: var(--display);
  font-size: 14.5px;
  font-weight: 600;
  color: var(--ink);
  letter-spacing: .01em;
  white-space: nowrap;
}

.tb-nav {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: 1;
  min-width: 0;
}
.tb-tab {
  padding: 7px 14px;
  border-radius: var(--radius-md);
  color: var(--ink-2);
  text-decoration: none;
  font-size: 13.5px;
  font-weight: 500;
  white-space: nowrap;
  transition: background .15s var(--ease-soft), color .15s var(--ease-soft);
}
.tb-tab:hover { background: var(--bg-3); color: var(--ink); }
.tb-tab.active { color: var(--primary); background: var(--primary-soft); font-weight: 600; }

.tb-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.tb-user {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--ink-2);
  max-width: 120px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tb-icon {
  position: relative;
  width: 32px; height: 32px;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: var(--bg-2);
  color: var(--muted);
  font-size: 14px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background .15s var(--ease-soft), color .15s var(--ease-soft), border-color .15s var(--ease-soft);
}
.tb-icon:hover { background: var(--bg-3); color: var(--ink); border-color: var(--line-strong); }
.tb-icon:last-child:hover { color: var(--danger); background: var(--danger-soft); border-color: rgba(220, 38, 38, .2); }

.tb-menu {
  position: absolute;
  right: 0; top: calc(100% + 6px);
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px;
  background: var(--bg-2);
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-3);
  min-width: 130px;
  z-index: 50;
}
.tb-menu-link {
  padding: 7px 12px;
  border-radius: var(--radius-sm);
  color: var(--ink-2);
  text-decoration: none;
  font-size: 12.5px;
}
.tb-menu-link:hover { background: var(--bg-3); color: var(--ink); }

.admin-pop-enter-active, .admin-pop-leave-active { transition: all .15s var(--ease-soft); }
.admin-pop-enter-from, .admin-pop-leave-to { opacity: 0; transform: translateY(-4px); }

/* ── 主区 ── */
.app-main {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
.app-main-scroll {
  height: 100%;
  min-height: 0;
  overflow-y: auto;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: var(--gap, 14px);
  padding: 16px 22px 22px;
}
.app-main-scroll[data-page="Overview"] {
  grid-template-rows: minmax(0, 1fr);
  overflow: hidden;
  padding: 14px;
}
.app-main-scroll[data-page="Warnings"],
.app-main-scroll[data-page="Devices"] {
  grid-template-rows: auto minmax(0, 1fr);
  overflow: hidden;
}
.app-main-scroll[data-page="Agent"] {
  grid-template-rows: auto minmax(0, 1fr) auto;
}
.app-main-scroll > * { min-height: 0; }

@media (max-width: 760px) {
  .tb-name { display: none; }
  .tb-nav { gap: 0; }
  .tb-tab { padding: 7px 10px; font-size: 12.5px; }
  .tb-user { display: none; }
}
</style>
