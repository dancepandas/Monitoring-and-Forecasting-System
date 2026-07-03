<template>
  <div class="admin-page">
    <Topbar title="用户管理" subtitle="用户列表与权限管理。" />
    <article class="panel">
      <div class="panel-head"><h2>用户列表</h2><span>{{ users.length }} 人</span></div>
      <div class="panel-body">
        <div class="risk-list">
          <div v-if="users.length === 0" class="empty-state">暂无用户</div>
          <div class="risk-item" v-for="u in users" :key="u.id">
            <div class="risk-row">
              <b>{{ u.display_name || u.name }}</b>
              <span class="badge" :class="badgeClass(u.role)">{{ u.role || '—' }}</span>
            </div>
            <p>{{ u.username }} · {{ u.created_at || '—' }}</p>
          </div>
        </div>
      </div>
    </article>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import Topbar from '../components/Topbar.vue'
import { api } from '../api'

const users = ref([])

function badgeClass(role) {
  if (role === 'super_admin') return 'primary'
  if (role === 'admin') return 'warn'
  return 'ok'
}

onMounted(async () => {
  try {
    const data = await api.getUsers()
    users.value = data.users || []
  } catch (e) {
    console.error('Failed to load users:', e)
  }
})
</script>
<style scoped>
.admin-page {
  min-height: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
}
.empty-state { padding: 40px 0; text-align: center; color: var(--muted); font-size: 13px; }
.risk-row b { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.risk-item p { overflow-wrap: break-word; }
</style>
