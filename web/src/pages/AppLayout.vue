<template>
  <div class="app-layout">
    <Sidebar />
    <main class="workspace" :data-page="$route.name">
      <router-view />
      <ContextMenu v-if="$route.name !== 'agent'" />
    </main>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import Sidebar from '../components/Sidebar.vue'
import ContextMenu from '../components/ContextMenu.vue'

onMounted(() => {
  const root = document.documentElement
  root.style.setProperty('--topbar-h', '7.9fr')
  root.style.setProperty('--overview-h', '10.5fr')
  root.style.setProperty('--middle-h', '50.0fr')
  root.style.setProperty('--bottom-h', '31.6fr')
  root.style.setProperty('--video-w', '21.6fr')
  root.style.setProperty('--map-w', '51.0fr')
  root.style.setProperty('--warning-w', '27.5fr')
  root.style.setProperty('--gap', '10px')
  root.style.setProperty('--pad', '10px')
  root.style.setProperty('--sidebar-w', '220px')
})
</script>
