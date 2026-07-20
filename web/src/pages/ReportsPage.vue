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
            <div class="risk-foot">
              <button class="btn sm gen-btn" :disabled="!!generating[r.key]" @click.stop="generateNow(r)">
                {{ generating[r.key] ? '生成中…' : '立即生成' }}
              </button>
            </div>
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

  <!-- 最新内容弹窗 —— 文档阅读器 -->
  <Teleport to="body">
    <div v-if="showPreview" class="modal-overlay" @click.self="closePreview">
      <div class="report-modal">
        <div class="rm-header">
          <div class="rm-title">
            <span class="rm-title-icon">📄</span>
            <span>{{ previewTitle }}</span>
          </div>
          <div class="rm-actions">
            <button class="btn sm" @click="downloadCurrent">
              <span class="btn-icon">↓</span> 下载
            </button>
            <button class="btn sm btn-close" @click="closePreview">
              <span class="btn-icon">✕</span> 关闭
            </button>
          </div>
        </div>
        <div class="rm-body">
          <div ref="previewContainer" class="docx-canvas" v-show="previewType !== 'text'"></div>
          <div v-if="previewType === 'text'" class="preview-text">
            <pre class="report-content">{{ previewContent }}</pre>
          </div>
          <div v-if="previewLoading" class="preview-loading">
            <span class="spinner"></span> 加载文档中…
          </div>
        </div>
      </div>
    </div>
  </Teleport>

  <!-- 归档列表弹窗 -->
  <Teleport to="body">
    <div v-if="showArchive" class="modal-overlay" @click.self="showArchive = false">
      <div class="report-modal report-modal--list">
        <div class="rm-header">
          <div class="rm-title">{{ archiveTitle }} · 历史归档</div>
          <div class="rm-actions">
            <button class="btn sm btn-close" @click="showArchive = false">
              <span class="btn-icon">✕</span> 关闭
            </button>
          </div>
        </div>
        <div class="rm-body">
          <div v-if="archiveLoading" class="preview-loading"><span class="spinner"></span> 加载中…</div>
          <div v-else-if="archiveList.length === 0" class="preview-empty">暂无报告</div>
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
    <div v-if="showArchiveDetail" class="modal-overlay" @click.self="closeArchiveDetail">
      <div class="report-modal">
        <div class="rm-header">
          <div class="rm-title">
            <span class="rm-title-icon">📄</span>
            <span>{{ archiveDetailTitle }}</span>
          </div>
          <div class="rm-actions">
            <button class="btn sm" @click="downloadCurrent">↓ 下载</button>
            <button class="btn sm btn-close" @click="closeArchiveDetail">✕ 关闭</button>
          </div>
        </div>
        <div class="rm-body">
          <div ref="archiveDetailContainer" class="docx-canvas" v-show="archiveDetailType !== 'text'"></div>
          <div v-if="archiveDetailType === 'text'" class="preview-text">
            <pre class="report-content">{{ archiveDetailContent }}</pre>
          </div>
          <div v-if="archiveDetailLoading" class="preview-loading"><span class="spinner"></span> 加载文档中…</div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { renderAsync } from 'docx-preview'
import Topbar from '../components/Topbar.vue'
import { api } from '../api'

// 预览走 docx-preview（专业 docx→HTML 渲染，保留 Word 原排版：标题/表格/页眉脚）。
// 关键避坑：常驻容器 + nextTick 等挂载 + loading 作 absolute 遮罩，不用 v-if 隐藏 ref。
// 渲染失败回退到后端 /reports/preview 纯文本，保证一定可见。

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
const previewType = ref('')
const previewContainer = ref(null)
const currentFile = ref('')
const generating = ref({})

const showArchive = ref(false)
const archiveTitle = ref('')
const archiveList = ref([])
const archiveLoading = ref(false)

const showArchiveDetail = ref(false)
const archiveDetailTitle = ref('')
const archiveDetailContent = ref('')
const archiveDetailLoading = ref(false)
const archiveDetailType = ref('')
const archiveDetailContainer = ref(null)

async function loadStats() {
  try {
    const data = await api.listReports()
    const reports = data.reports || []
    for (const t of reportTypes.value) {
      const typeReports = reports.filter(r => r.type === t.key)
      stats.value.find(s => s.key === t.key).count = typeReports.length
      if (typeReports.length > 0) {
        const latest = typeReports[0]
        t.latestDate = latest.date || '—'
        t.latestFile = latest.filename
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

async function generateNow(r) {
  generating.value = { ...generating.value, [r.key]: true }
  try {
    await api.generateReport({ report_type: r.key })
    await loadStats()
  } catch (e) {
    alert('生成失败：' + (e?.message || e))
  } finally {
    generating.value = { ...generating.value, [r.key]: false }
  }
}

async function openLatest(r) {
  if (!r.latestFile) return
  showPreview.value = true
  previewTitle.value = r.label
  previewLoading.value = true
  previewType.value = ''
  previewContent.value = ''
  currentFile.value = r.latestFile
  await nextTick()
  await renderDocxOrFallback(r.latestFile, previewContainer.value, {
    setText: v => { previewContent.value = v },
    setType: v => { previewType.value = v },
  })
  previewLoading.value = false
}

function closePreview() {
  showPreview.value = false
  previewType.value = ''
  previewContent.value = ''
  if (previewContainer.value) previewContainer.value.innerHTML = ''
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
  archiveDetailType.value = ''
  archiveDetailContent.value = ''
  currentFile.value = item.filename
  await nextTick()
  await renderDocxOrFallback(item.filename, archiveDetailContainer.value, {
    setText: v => { archiveDetailContent.value = v },
    setType: v => { archiveDetailType.value = v },
  })
  archiveDetailLoading.value = false
}

function closeArchiveDetail() {
  showArchiveDetail.value = false
  archiveDetailType.value = ''
  archiveDetailContent.value = ''
  if (archiveDetailContainer.value) archiveDetailContainer.value.innerHTML = ''
}

async function downloadFile(filename) {
  const blob = await fetchDocxBlob(filename)
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}

// 拉 docx 二进制（带鉴权），复用于预览渲染与下载
async function fetchDocxBlob(filename) {
  const token = localStorage.getItem('token')
  const url = api.downloadReport(filename)
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
  if (!res.ok) throw new Error('下载失败')
  return await res.blob()
}

// docx-preview 渲染到 container；失败回退后端纯文本预览，保证一定可见
async function renderDocxOrFallback(filename, container, { setText, setType }) {
  if (!container) { setText('容器未就绪'); setType('text'); return }
  try {
    const blob = await fetchDocxBlob(filename)
    container.innerHTML = ''
    await renderAsync(blob, container, null, {
      inWrapper: true,
      className: 'docx-page',
      ignoreWidth: false,
      ignoreHeight: false,
      renderHeaders: true,
      renderFooters: true,
      breakPages: true,
      experimental: true,
    })
    setType('docx')
  } catch (e) {
    console.warn('[report] docx 渲染失败，回退文本预览：', e)
    container.innerHTML = ''
    try {
      const data = await api.previewReport(filename)
      setText((data && data.content) || '（文档无文本内容，请下载后查看）')
    } catch (e2) {
      setText('加载失败：' + (e2.message || e2))
    }
    setType('text')
  }
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
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--gap, 10px);
}

.clickable { cursor: pointer; }
.clickable:hover { background: rgba(14, 165, 233, 0.06); border-color: var(--edge); }

.risk-foot { display: flex; justify-content: flex-end; margin-top: 6px; }
.gen-btn { border-radius: 999px; }
.gen-btn:disabled { opacity: .6; cursor: progress; }

.risk-meta {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--muted);
  flex-shrink: 0;
}

/* ── 弹窗遮罩 ── */
.modal-overlay {
  position: fixed; inset: 0; z-index: 100;
  background: rgba(15, 23, 42, 0.7);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
}

/* ── 文档阅读器主体 ── */
.report-modal {
  width: min(1100px, calc(100vw - 40px));
  height: calc(100vh - 40px);
  max-height: none;
  background: var(--glass-strong);
  border: 1px solid var(--line);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-4), 0 0 40px rgba(14, 165, 233, 0.08);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.report-modal--list {
  width: min(640px, calc(100vw - 40px));
  height: auto;
  max-height: calc(100vh - 40px);
}

/* ── 顶部工具栏 ── */
.rm-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 24px;
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
  gap: 12px;
}

.rm-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--ink);
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rm-title-icon {
  font-size: 18px;
  flex-shrink: 0;
}

.rm-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.rm-actions .btn {
  min-height: 34px;
  padding: 0 14px;
  border-radius: var(--radius-md);
  background: var(--bg-3);
  color: var(--ink-2);
  border: 1px solid var(--line);
  font-size: 13px;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 5px;
  cursor: pointer;
  transition: all .15s;
}
.rm-actions .btn:hover {
  background: var(--bg-4);
  border-color: var(--edge);
}
.rm-actions .btn-close {
  color: var(--muted);
}
.rm-actions .btn-close:hover {
  background: var(--danger-soft);
  border-color: rgba(248, 113, 113, .25);
  color: var(--danger);
}

.btn-icon {
  font-size: 12px;
  font-weight: 700;
}

/* ── 正文滚动区（Word 阅读器灰底 + 居中纸张） ── */
.rm-body {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0;
  position: relative;
  background: #E8E8EB;
}

/* docx-preview 渲染画布：灰底衬纸效果 */
.docx-canvas {
  width: 100%;
  min-height: 100%;
  padding: 28px 16px 40px;
  box-sizing: border-box;
}
/* docx-preview 输出的页面：白纸 + 柔影，居中 */
.docx-canvas :deep(.docx-wrapper) {
  background: transparent;
  padding: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.docx-canvas :deep(.docx-wrapper > section),
.docx-canvas :deep(.docx-page) {
  background: #FFFFFF !important;
  box-shadow: 0 1px 2px rgba(0, 0, 0, .06), 0 8px 28px rgba(0, 0, 0, .10);
  border-radius: 2px;
  margin: 0 auto 20px !important;
  color: #1D1D1F;
}
/* docx 内文字走系统衬线，贴近 Word 默认 Calibri/宋体观感 */
.docx-canvas :deep(.docx-wrapper) p,
.docx-canvas :deep(.docx-wrapper) span,
.docx-canvas :deep(.docx-wrapper) td,
.docx-canvas :deep(.docx-wrapper) li {
  font-family: "Calibri", "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif;
}
.docx-canvas :deep(.docx-wrapper) h1,
.docx-canvas :deep(.docx-wrapper) h2,
.docx-canvas :deep(.docx-wrapper) h3 {
  color: #111827;
}

/* ── 加载遮罩（absolute 覆盖正文，不卸载容器） ── */
.preview-loading {
  position: absolute;
  inset: 0;
  z-index: 5;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--ink-2);
  font-size: 14px;
  background: rgba(232, 232, 235, .72);
  -webkit-backdrop-filter: blur(2px);
  backdrop-filter: blur(2px);
}
.preview-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 260px;
  color: var(--muted);
  font-size: 14px;
}

.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid var(--bg-4);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin .6s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.preview-text {
  max-width: 880px;
  margin: 28px auto 40px;
  padding: 40px 48px;
  background: #FFFFFF;
  border-radius: 2px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, .06), 0 8px 28px rgba(0, 0, 0, .10);
}

.report-content {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--sans);
  font-size: 14px;
  line-height: 1.85;
  margin: 0;
  color: var(--ink);
}

/* ── 归档列表 ── */
.archive-list {
  display: grid; gap: 6px;
  padding: 16px 24px;
}

.archive-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px;
  border-radius: 10px;
  cursor: pointer;
  transition: all .12s;
  gap: 8px;
  background: var(--bg-3);
  border: 1px solid var(--line);
}
.archive-row:hover { background: var(--bg-4); border-color: var(--edge); }

.ar-info {
  display: flex; flex-direction: column; gap: 2px;
  min-width: 0;
}
.ar-info b {
  font-size: 13px; color: var(--ink);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.ar-info span {
  font-size: 11px; color: var(--muted);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.ar-actions { flex-shrink: 0; }
.ar-actions .btn {
  min-height: 28px;
  padding: 0 12px;
  border-radius: 999px;
  background: var(--bg-2);
  color: var(--ink-2);
  border: 1px solid var(--line);
  font-size: 12px;
  transition: all .15s;
}
.ar-actions .btn:hover { background: var(--bg-3); border-color: var(--edge); }
.sm { font-size: 11px; padding: 4px 10px; }
</style>
