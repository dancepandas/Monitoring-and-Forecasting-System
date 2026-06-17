<template><div><Topbar title="系统配置" subtitle="自动化任务、模型与通知设置。" /><div class="command-grid"><article class="panel"><div class="panel-head"><h2>自动化定时任务</h2></div><div class="panel-body"><div class="risk-list"><div class="risk-item" v-for="t in tasks" :key="t.task_id"><div class="risk-row"><b>{{ t.task_type }}</b><span class="badge ok">活跃</span></div><p>{{ t.trigger || t.cron }} · 下次：{{ t.next_run_time || '—' }}</p></div></div><div class="risk-item" v-if="!tasks.length"><div class="risk-row"><b>暂无定时任务</b></div><p>可通过智能体创建日报/周报定时任务</p></div></div></article><article class="panel"><div class="panel-head"><h2>预警标准</h2></div><div class="panel-body"><div class="risk-list"><div class="risk-item"><div class="risk-row"><b>水位预警阈值</b></div><p>蓝: 34.0m · 黄: 35.0m · 橙: 35.5m · 红: 36.0m</p></div><div class="risk-item"><div class="risk-row"><b>流量预警阈值</b></div><p>蓝: 5000 · 黄: 8000 · 橙: 12000 · 红: 18000 m³/s</p></div></div></div></article></div></div></template>
<script setup>
import { ref, onMounted } from 'vue'
import Topbar from '../components/Topbar.vue'
import { api } from '../api'

const tasks = ref([])

onMounted(async () => {
  try {
    const data = await api.getScheduledTasks()
    tasks.value = data.tasks || []
  } catch { /* no tasks yet */ }
})
</script>
