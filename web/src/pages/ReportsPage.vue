<template>
  <Topbar title="日报归档" subtitle="自动生成的流域运行日报与处置记录。" />
  <div class="command-grid">
    <article class="panel">
      <div class="panel-head"><h2>日报列表</h2><span>最近 30 天</span></div>
      <div class="panel-body">
        <div class="risk-list">
          <div class="risk-item clickable" v-for="r in reportTypes" :key="r.key" @click="openLatest(r)">
            <div class="risk-row">
              <b>{{ r.label }}</b>
              <span class="risk-meta">{{ r.latestDate || '暂无' }}</span>
            </div>
            <p>{{ r.latestSummary || '点击查看最新日报内容' }}</p>
          </div>
        </div>
      </div>
    </article>
    <article class="panel">
      <div class="panel-head"><h2>归档统计</h2><span>本月</span></div>
      <div class="panel-body">
        <div class="risk-list">
          <div class="risk-item clickable" v-for="s in stats" :key="s.key" @click="openArchive(s)">
            <div class="risk-row">
              <b>{{ s.label }}</b>
              <span>{{ s.count }} 份</span>
            </div>
          </div>
        </div>
      </div>
    </article>
  </div>

  <!-- 最新内容弹窗 -->
  <Teleport to="body">
    <div v-if="showPreview" class="modal-overlay" @click.self="showPreview = false">
      <div class="report-modal">
        <div class="rm-head">
          <h2>{{ previewTitle }}</h2>
          <div class="rm-head-actions">
            <button class="btn" @click="downloadCurrent">导出 Word</button>
            <button class="btn" @click="showPreview = false">关闭</button>
          </div>
        </div>
        <div class="rm-body" v-if="previewLoading">加载中...</div>
        <div class="rm-body" v-else-if="previewContent">
          <pre class="report-content">{{ previewContent }}</pre>
        </div>
        <div class="rm-body" v-else>暂无内容</div>
      </div>
    </div>
  </Teleport>

  <!-- 归档列表弹窗 -->
  <Teleport to="body">
    <div v-if="showArchive" class="modal-overlay" @click.self="showArchive = false">
      <div class="report-modal">
        <div class="rm-head">
          <h2>{{ archiveTitle }} - 历史归档</h2>
          <button class="btn" @click="showArchive = false">关闭</button>
        </div>
        <div class="rm-body">
          <div v-if="archiveLoading">加载中...</div>
          <div v-else-if="archiveList.length === 0">暂无报告</div>
          <div class="archive-list" v-else>
            <div class="archive-row" v-for="item in archiveList" :key="item.filename" @click="viewArchiveItem(item)">
              <div class="ar-info">
                <b>{{ item.date || item.filename }}</b>
                <span>{{ fmtSize(item.size) }} · {{ fmtTime(item.modified) }}</span>
              </div>
              <div class="ar-actions">
                <button class="btn sm" @click.stop="downloadArchiveItem(item)">导出</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>

  <!-- 归档项详情弹窗 -->
  <Teleport to="body">
    <div v-if="showArchiveDetail" class="modal-overlay" @click.self="showArchiveDetail = false">
      <div class="report-modal">
        <div class="rm-head">
          <h2>{{ archiveDetailTitle }}</h2>
          <div class="rm-head-actions">
            <button class="btn" @click="downloadCurrent">导出 Word</button>
            <button class="btn" @click="showArchiveDetail = false">关闭</button>
          </div>
        </div>
        <div class="rm-body" v-if="archiveDetailLoading">加载中...</div>
        <div class="rm-body" v-else-if="archiveDetailContent">
          <pre class="report-content">{{ archiveDetailContent }}</pre>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import Topbar from '../components/Topbar.vue'
import { api } from '../api'

const reportTypes = ref([
  { key: 'daily', label: '流域运行日报', latestDate: '—', latestSummary: '加载中...', latestFile: '' },
  { key: 'review', label: '预警处置复盘', latestDate: '—', latestSummary: '加载中...', latestFile: '' },
  { key: 'device', label: '设备在线率日报', latestDate: '—', latestSummary: '加载中...', latestFile: '' },
  { key: 'model', label: '模型预报一致性', latestDate: '—', latestSummary: '加载中...', latestFile: '' },
])
const stats = ref([
  { key: 'daily', label: '日报', count: 0 },
  { key: 'review', label: '复盘', count: 0 },
  { key: 'device', label: '设备报告', count: 0 },
  { key: 'model', label: '模型评估', count: 0 },
])

const showPreview = ref(false)
const previewTitle = ref('')
const previewContent = ref('')
const previewLoading = ref(false)
const currentFile = ref('')

const showArchive = ref(false)
const archiveTitle = ref('')
const archiveList = ref([])
const archiveLoading = ref(false)

const showArchiveDetail = ref(false)
const archiveDetailTitle = ref('')
const archiveDetailContent = ref('')
const archiveDetailLoading = ref(false)

async function loadStats() {
  try {
    const data = await api.listReports()
    const reports = data.reports || []
    // 更新每种类型的数量和最新信息
    for (const t of reportTypes.value) {
      const typeReports = reports.filter(r => r.type === t.key)
      stats.value.find(s => s.key === t.key).count = typeReports.length
      if (typeReports.length > 0) {
        const latest = typeReports[0]
        t.latestDate = latest.date || '—'
        t.latestFile = latest.filename
        // 尝试加载最新一条的摘要
        try {
          const preview = await api.previewReport(latest.filename)
          t.latestSummary = (preview.content || '').split('\n')[0]?.slice(0, 60) || '暂无摘要'
        } catch {
          t.latestSummary = latest.filename
        }
      } else {
        t.latestDate = '暂无'
        t.latestSummary = '暂无报告'
        t.latestFile = ''
      }
    }
  } catch (e) {
    console.error('loadStats failed:', e)
  }
}

async function openLatest(r) {
  if (!r.latestFile) return
  showPreview.value = true
  previewTitle.value = r.label
  previewLoading.value = true
  previewContent.value = ''
  currentFile.value = r.latestFile
  try {
    const data = await api.previewReport(r.latestFile)
    previewContent.value = data.content || ''
  } catch (e) {
    previewContent.value = '加载失败：' + e.message
  } finally {
    previewLoading.value = false
  }
}

async function openArchive(s) {
  showArchive.value = true
  archiveTitle.value = s.label
  archiveLoading.value = true
  archiveList.value = []
  try {
    const data = await api.listReports(s.key)
    archiveList.value = data.reports || []
  } catch (e) {
    console.error('openArchive failed:', e)
  } finally {
    archiveLoading.value = false
  }
}

async function viewArchiveItem(item) {
  showArchiveDetail.value = true
  archiveDetailTitle.value = item.date || item.filename
  archiveDetailLoading.value = true
  archiveDetailContent.value = ''
  currentFile.value = item.filename
  try {
    const data = await api.previewReport(item.filename)
    archiveDetailContent.value = data.content || ''
  } catch (e) {
    archiveDetailContent.value = '加载失败：' + e.message
  } finally {
    archiveDetailLoading.value = false
  }
}

async function downloadFile(filename) {
  const token = localStorage.getItem('token')
  const url = api.downloadReport(filename)
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
  if (!res.ok) throw new Error('下载失败')
  const blob = await res.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}

function downloadCurrent() {
  if (currentFile.value) downloadFile(currentFile.value).catch(e => alert(e.message))
}

function downloadArchiveItem(item) {
  downloadFile(item.filename).catch(e => alert(e.message))
}

function fmtSize(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return bytes + ' B'
  return (bytes / 1024).toFixed(1) + ' KB'
}

function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

onMounted(() => { loadStats() })
</script>

<style scoped>
.command-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--gap, 10px);
}

.clickable { cursor: pointer; }
.clickable:hover { background: rgba(109, 146, 159, .05); }

.risk-meta {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--muted);
}

/* Modal overlay */
.modal-overlay {
  position: fixed; inset: 0; z-index: 100;
  background: rgba(0, 0, 0, .4);
  backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
  padding: 40px;
}

.report-modal {
  width: min(720px, 100%);
  max-height: 80vh;
  background: #fff;
  border-radius: 18px;
  box-shadow: 0 16px 48px rgba(0,0,0,.15);
  display: flex; flex-direction: column;
  overflow: hidden;
}

.rm-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--line);
  gap: 12px;
  flex-shrink: 0;
}

.rm-head h2 {
  margin: 0;
  font-family: var(--serif);
  font-size: 18px;
  font-weight: 500;
}

.rm-head-actions {
  display: flex; gap: 8px;
  flex-shrink: 0;
}

.rm-body {
  padding: 16px 20px;
  flex: 1; overflow-y: auto;
  color: var(--ink-2);
  font-size: 13px;
}

.report-content {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--mono);
  font-size: 12px;
  line-height: 1.7;
  margin: 0;
  color: var(--ink-2);
}

.archive-list {
  display: grid; gap: 4px;
}

.archive-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  cursor: pointer;
  transition: background .12s;
  gap: 8px;
}

.archive-row:hover { background: rgba(109, 146, 159, .05); }

.ar-info {
  display: flex; flex-direction: column; gap: 2px;
  min-width: 0;
}

.ar-info b {
  font-size: 13px; color: var(--ink);
}

.ar-info span {
  font-size: 10px; color: var(--muted);
}

.ar-actions { flex-shrink: 0; }
.sm { font-size: 11px; padding: 4px 10px; }
</style>
