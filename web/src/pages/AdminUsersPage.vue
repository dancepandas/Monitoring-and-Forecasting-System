<template><div><Topbar title="用户管理" subtitle="用户列表与权限管理。" /><article class="panel"><div class="panel-head"><h2>用户列表</h2><span>{{ users.length }} 人</span></div><div class="panel-body"><div class="risk-list"><div class="risk-item" v-for="u in users" :key="u.id"><div class="risk-row"><b>{{ u.display_name || u.name }}</b><span class="badge" :class="u.role==='super_admin'?'':u.role==='admin'?'warn':'ok'">{{ u.role || '—' }}</span></div><p>{{ u.username }} · {{ u.created_at || '—' }}</p></div></div></div></article></div></template>
<script setup>
import { ref, onMounted } from 'vue'
import Topbar from '../components/Topbar.vue'
import { api } from '../api'

const users = ref([])

onMounted(async () => {
  try {
    const data = await api.getUsers()
    users.value = data.users || []
  } catch (e) {
    console.error('Failed to load users:', e)
  }
})
</script>
