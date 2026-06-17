<template>
  <Topbar title="视频巡检" subtitle="39 路视频在线，关键断面监测画面与 AI 识别结果。" />
  <section class="video-page-content">
    <div class="video-grid video-grid-3col">
      <div class="video-card" v-for="v in feeds" :key="v.cam">
        <div class="video-meta"><b>{{ v.cam }}</b><span>{{ v.label }}</span></div>
      </div>
    </div>
  </section>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import Topbar from '../components/Topbar.vue'
import { api } from '../api'

const feeds = ref([])
const totalFeeds = ref(0)

onMounted(async () => {
  try {
    const data = await api.getVideoFeeds('00106,00107,00108')
    feeds.value = (data.feeds || []).map(f => ({
      cam: f.id + ' · ' + (f.status === 'online' ? '在线' : '离线'),
      label: `${f.label} / ${(f.ai_tasks||[]).join('、') || '监测画面'}` + (f.water_level ? ` · 水位${f.water_level}m` : ''),
    }))
    totalFeeds.value = data.total || 0
  } catch (e) {
    console.error('Video feeds failed:', e)
  }
})
</script>
<style scoped>
.video-page-content {
  min-height: 0;
  overflow: hidden;
}

.video-grid-3col {
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  grid-template-rows: auto;
  grid-auto-rows: minmax(160px, auto);
  gap: var(--gap, 10px);
  padding: 0;
  align-content: start;
}

.video-grid-3col .video-card {
  min-height: 160px;
}
</style>
