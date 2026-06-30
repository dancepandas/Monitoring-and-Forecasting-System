<template>
  <div class="app-layout">
    <CesiumMap />
    <header class="app-banner">
      <span class="banner-side left"></span>
      <h1 class="banner-title">水文监测预报指挥中心</h1>
      <span class="banner-side right"></span>
    </header>
    <TabBar />
    <main class="workspace" :data-page="$route.name">
      <router-view />
      <ContextMenu v-if="$route.name !== 'agent'" />
    </main>
    <VoiceAssistant />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import CesiumMap from '../components/CesiumMap.vue'
import TabBar from '../components/TabBar.vue'
import ContextMenu from '../components/ContextMenu.vue'
import VoiceAssistant from '../components/VoiceAssistant.vue'

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
})
</script>
