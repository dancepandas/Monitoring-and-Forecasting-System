<template>
  <div class="app-layout">
    <CesiumMap />
    <header class="app-banner">
      <span class="banner-side left"></span>
      <h1 class="banner-title">水文监测预报指挥中心</h1>
      <span class="banner-side right"></span>
      <TabBar />
      <div class="banner-spacer"></div>
      <span class="system-status" :class="statusClass" :title="statusTitle">
        <i class="status-dot"></i>
        <span class="status-text">{{ statusLabel }}</span>
      </span>
      <button v-if="isAdmin" class="admin-gear" @click="showAdminMenu = !showAdminMenu" title="管理">
        ⚙
        <transition name="admin-pop">
          <div v-if="showAdminMenu" class="admin-menu" @click.stop>
            <router-link to="/admin/users" class="admin-link" @click="showAdminMenu = false">用户管理</router-link>
            <router-link to="/admin/settings" class="admin-link" @click="showAdminMenu = false">系统设置</router-link>
          </div>
        </transition>
      </button>
      <button class="logout-btn" @click="handleLogout">退出</button>
    </header>
    <main class="workspace" :data-page="$route.name">
      <router-view />
      <ContextMenu v-if="$route.name !== 'agent'" />
    </main>
    <VoiceAssistant />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import CesiumMap from '../components/CesiumMap.vue'
import TabBar from '../components/TabBar.vue'
import ContextMenu from '../components/ContextMenu.vue'
import VoiceAssistant from '../components/VoiceAssistant.vue'
import { useAuthStore } from '../store/auth'

const router = useRouter()
const auth = useAuthStore()

const showAdminMenu = ref(false)
const isAdmin = computed(() => auth.role === 'admin' || auth.role === 'super_admin')

function handleLogout() {
  auth.logout()
  router.push('/login')
}

// ── 系统状态 ──
const sysDiagnosis = ref('unknown')
const sysSummary = ref('')

const statusLabel = computed(() => {
  switch (sysDiagnosis.value) {
    case 'healthy': return '系统正常'
    case 'warning': return '系统异常'
    case 'critical': return '系统故障'
    default: return '状态未知'
  }
})
const statusClass = computed(() => sysDiagnosis.value)
const statusTitle = computed(() => sysSummary.value || sysDiagnosis.value)

let statusTimer = null
async function fetchStatus() {
  try {
    const res = await fetch('/api/system/status', {
      headers: { 'Authorization': `Bearer ${auth.token}` }
    })
    if (res.ok) {
      const data = await res.json()
      sysDiagnosis.value = data.diagnosis || 'unknown'
      sysSummary.value = data.summary || ''
    }
  } catch {}
}

onMounted(() => {
  const root = document.documentElement
  root.style.setProperty('--topbar-h', '8.5fr')
  root.style.setProperty('--overview-h', '9.0fr')
  root.style.setProperty('--middle-h', '50.0fr')
  root.style.setProperty('--bottom-h', '32.5fr')
  root.style.setProperty('--video-w', '21fr')
  root.style.setProperty('--map-w', '51fr')
  root.style.setProperty('--warning-w', '28fr')
  root.style.setProperty('--gap', '10px')
  root.style.setProperty('--pad', '10px')
  fetchStatus()
  statusTimer = setInterval(fetchStatus, 60000)
})
onUnmounted(() => { if (statusTimer) clearInterval(statusTimer) })
</script>
