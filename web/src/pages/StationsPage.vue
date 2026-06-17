<template>
  <Topbar title="监测站点" subtitle="42 路设备接入，水位、流量与视频链路状态。" />
  <div class="command-grid">
    <article class="panel">
      <div class="panel-head"><h2>关键站点</h2><span>当前状态</span></div>
        <div class="panel-body">
          <div class="risk-list">
            <div class="risk-item" v-for="s in stations" :key="s.code">
              <div class="risk-row"><b>{{ s.name }}</b><span :class="['badge', s.badgeClass]">{{ s.status }}</span></div>
              <p>水位 {{ s.level }}m · 流量 {{ s.flow || '—' }}m³/s · {{ s.detail }}</p>
            </div>
          </div>
        </div>
      </article>
      <article class="panel">
        <div class="panel-head"><h2>设备统计</h2><span>42 路</span></div>
        <div class="panel-body">
          <div class="risk-list">
            <div class="risk-item" v-for="d in deviceStats" :key="d.label"><div class="risk-row"><b>{{ d.label }}</b><span style="font-family:var(--mono);color:var(--muted)">{{ d.value }}</span></div></div>
          </div>
        </div>
      </article>
    </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import Topbar from '../components/Topbar.vue'
import { api } from '../api'

const STATIONS = [
  { code: '00106', name: '湖北-仙桃', deviceCode: 'FD000489923695' },
]

const stations = ref([])
const deviceStats = ref([
  { label: '在线', value: '—' },
  { label: '离线', value: '—' },
  { label: '无数据', value: '—' },
])

onMounted(async () => {
  try {
    // 设备统计
    const stats = await api.getDeviceStats('00106')
    deviceStats.value = [
      { label: '在线', value: `${stats.online}` },
      { label: '离线', value: `${stats.offline}` },
      { label: '无数据', value: `${stats.total - stats.online - stats.offline}` },
    ]

    // 测站数据
    const results = []
    for (const s of STATIONS) {
      try {
        const data = await api.getFlowRaw(s.code, s.deviceCode)
        const items = data?.data || []
        if (items.length > 0) {
          const latest = items[0]
          const lv = latest.waterLevel
          results.push({
            code: s.code, name: s.name,
            level: lv != null ? Number(lv).toFixed(2) : '—',
            flow: latest.virtualFlow != null ? Number(latest.virtualFlow).toFixed(0) : '—',
            status: '正常',
            badgeClass: 'ok',
            detail: lv != null ? `最新水位 ${Number(lv).toFixed(2)}m` : '暂无数据',
          })
        } else {
          results.push({ code: s.code, name: s.name, level: '—', flow: '—', status: '无数据', badgeClass: '', detail: '暂无上报数据' })
        }
      } catch {
        results.push({ code: s.code, name: s.name, level: '—', flow: '—', status: '离线', badgeClass: '', detail: '数据获取失败' })
      }
    }
    stations.value = results
  } catch (e) {
    console.error('Stations load failed:', e)
  }
})
</script>
