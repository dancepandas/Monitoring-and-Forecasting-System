<template>
  <header class="topbar">
    <div class="page-title">
      <h1>{{ title }}</h1>
      <p>{{ subtitle }}</p>
    </div>
    <div class="top-actions">
      <SystemStatus />
      <div class="clock">{{ clockText }}</div>
      <button class="btn primary" @click="$emit('primary-action')" v-if="actionLabel">{{ actionLabel }}</button>
      <button class="btn" @click="auth.logout(); $router.push('/login')">退出</button>
    </div>
  </header>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '../store/auth'
import SystemStatus from './SystemStatus.vue'

defineProps({
  title: String,
  subtitle: String,
  actionLabel: String
})

defineEmits(['primary-action'])

const auth = useAuthStore()
const clockText = ref('--')

let timer
function tick() {
  const d = new Date()
  const pad = n => String(n).padStart(2, '0')
  clockText.value = `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
onMounted(() => { tick(); timer = setInterval(tick, 1000) })
onUnmounted(() => clearInterval(timer))
</script>
