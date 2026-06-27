<template>
  <div class="app-layout">
    <CesiumMap />
    <Sidebar />
    <main class="workspace" :data-page="$route.name">
      <router-view />
      <ContextMenu v-if="$route.name !== 'agent'" />
    </main>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import CesiumMap from '../components/CesiumMap.vue'
import Sidebar from '../components/Sidebar.vue'
import ContextMenu from '../components/ContextMenu.vue'

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
  root.style.setProperty('--sidebar-w', '220px')
})
</script>
