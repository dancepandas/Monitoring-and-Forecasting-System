<template>
  <header class="topbar">
    <div class="page-title">
      <span v-if="sectionCode" class="section-code">{{ sectionCode }}</span>
      <h1>{{ title }}</h1>
      <p>{{ subtitle }}</p>
    </div>
    <div class="top-actions">
      <SystemStatus />
      <button class="btn primary" @click="$emit('primary-action')" v-if="actionLabel">{{ actionLabel }}</button>
      <button class="btn" @click="auth.logout(); $router.push('/login')">退出</button>
    </div>
  </header>
</template>

<script setup>
import { useAuthStore } from '../store/auth'
import SystemStatus from './SystemStatus.vue'

defineProps({
  title: String,
  subtitle: String,
  actionLabel: String,
  sectionCode: String
})

defineEmits(['primary-action'])

const auth = useAuthStore()
</script>
