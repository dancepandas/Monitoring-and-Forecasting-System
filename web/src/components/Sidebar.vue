<template>
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-row">
        <div class="mark"></div>
        <div><b>水文监测指挥核心</b><span>River Command Core</span></div>
      </div>
    </div>
    <nav class="nav">
      <router-link to="/"><span>流域总览</span><small>概览</small></router-link>
      <router-link to="/stations"><span>监测站点</span><small>{{ stationCount }}</small></router-link>
      <router-link to="/warnings"><span>预警处置</span><small>{{ warningCount }}</small></router-link>
      <router-link to="/forecast"><span>模型预报</span><small>AI</small></router-link>
      <router-link to="/devices"><span>视频巡检</span><small>{{ videoCount }}</small></router-link>
      <router-link to="/reports"><span>日报归档</span><small>{{ reportCount }}</small></router-link>
      <router-link to="/agent"><span>智能体对话</span><small>AI</small></router-link>
    </nav>
    <div class="sidebar-foot">
      <div class="agent-card">
        <b>FloodMind 在线</b>
        <p>可读取监测数据、运行预报模型、生成处置建议与日报草稿。</p>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'

const warningCount = ref('—')
const videoCount = ref('—')
const stationCount = ref('—')
const reportCount = ref('—')

async function loadBadges() {
  try {
    const [warnData, deviceData, reportData] = await Promise.all([
      api.getWarnings('00106,00107,00108').catch(() => ({ total: 0 })),
      api.getDeviceStats('00106,00107,00108').catch(() => ({ total: 0 })),
      api.listReports().catch(() => ({ total: 0 })),
    ])
    const wc = (warnData.warning_count || 0) + (warnData.alert_count || 0)
    warningCount.value = wc > 0 ? String(wc) : '—'
    stationCount.value = deviceData.total ? String(deviceData.total) : '3'
    videoCount.value = deviceData.online ? String(deviceData.online) : '—'
    reportCount.value = reportData.total ? String(reportData.total) : '—'
  } catch { /* offline */ }
}

onMounted(loadBadges)
</script>
