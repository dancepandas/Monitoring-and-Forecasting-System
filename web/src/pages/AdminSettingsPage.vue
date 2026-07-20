<template>
  <div class="settings-page">
    <Topbar title="系统配置" subtitle="自动化任务、模型与通知设置。" />
    <div class="command-grid">
      <article class="panel">
        <div class="panel-head"><h2>自动化定时任务</h2></div>
        <div class="panel-body">
          <div class="risk-list">
            <div class="risk-item" v-for="t in tasks" :key="t.task_id">
              <div class="risk-row">
                <b>{{ t.task_type }}</b>
                <span class="badge ok">活跃</span>
              </div>
              <p class="task-meta">
                <span>触发：{{ t.trigger || t.cron }}</span>
                <span>下次：{{ t.next_run_time || '—' }}</span>
              </p>
            </div>
            <div class="risk-item" v-if="!tasks.length">
              <div class="risk-row"><b>暂无定时任务</b></div>
              <p>可通过智能体创建日报/周报定时任务</p>
            </div>
          </div>
        </div>
      </article>

      <article class="panel">
        <div class="panel-head"><h2>预警标准</h2><span>每站独立配置</span></div>
        <div class="panel-body">
          <div v-if="loading" class="risk-item"><p>加载中...</p></div>
          <div class="risk-list" v-else>
            <div class="risk-item" v-for="(s, code) in stationThresholds" :key="code">
              <div class="risk-row"><b>{{ s.name }}</b></div>
              <div class="thresholds">
                <span class="threshold-tag level" v-for="(v, lv) in s.level" :key="'wl-'+lv">
                  {{ levelLabel(lv) }} {{ v }}m
                </span>
              </div>
              <div class="thresholds" style="margin-top:4px">
                <span class="threshold-tag flow" v-for="(v, lv) in s.flow" :key="'vf-'+lv">
                  {{ levelLabel(lv) }} {{ v }} m³/s
                </span>
              </div>
            </div>
            <div class="risk-item" style="opacity:.6">
              <div class="risk-row"><b>默认值（新站点回退）</b></div>
              <div class="thresholds">
                <span class="threshold-tag" v-for="(v, lv) in defaults.level" :key="'def-wl-'+lv">
                  {{ levelLabel(lv) }} {{ v }}m
                </span>
              </div>
            </div>
          </div>
        </div>
      </article>
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import Topbar from '../components/Topbar.vue'
import { api } from '../api'

const tasks = ref([])
const stationThresholds = ref({})
const defaults = ref({ level: {}, flow: {} })
const loading = ref(true)

const LEVEL_NAMES = { blue: '蓝', yellow: '黄', orange: '橙', red: '红' }
function levelLabel(lv) { return LEVEL_NAMES[lv] || lv }

onMounted(async () => {
  try {
    const data = await api.getScheduledTasks()
    tasks.value = data.tasks || []
  } catch { /* no tasks yet */ }

  try {
    const data = await api.getWarningStandards()
    stationThresholds.value = data.stations || {}
    defaults.value = data.defaults || { level: {}, flow: {} }
  } catch (e) {
    console.error('load warning standards failed:', e)
  } finally {
    loading.value = false
  }
})
</script>
<style scoped>
.settings-page {
  min-height: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
}
.risk-row {
  gap: 8px;
  flex-wrap: wrap;
}
.risk-row .badge {
  flex-shrink: 0;
}
.task-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
  margin: 0;
  color: var(--ink-2);
  font-size: 11px;
  line-height: 1.5;
}
.thresholds {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}
.threshold-tag {
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 11px;
  color: var(--ink-2);
  background: var(--glass-strong);
}
.threshold-tag.level { border-color: rgba(0,150,255,.25); }
.threshold-tag.flow { border-color: rgba(255,150,50,.25); }
</style>
