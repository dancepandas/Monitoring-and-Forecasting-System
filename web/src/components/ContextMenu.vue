<template>
  <Teleport to="body">
    <div v-if="visible" class="ctx-menu-overlay" @click="close" @contextmenu.prevent="close">
      <div class="ctx-menu" :style="{ left: x + 'px', top: y + 'px' }">
        <button class="ctx-item" @click="askAgent">询问智能体</button>
      </div>
    </div>
    <div v-if="showAgent" class="modal" @click.self="showAgent = false">
      <div class="modal-card agent-modal-card2">
        <div class="modal-actions" style="justify-content:space-between;align-items:center;">
          <h2>FloodMind 智能体</h2>
          <button class="btn" @click="showAgent = false">关闭</button>
        </div>
        <AgentChatPanel :sessionId="ctxSessionId" />
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import AgentChatPanel from './AgentChatPanel.vue'
import { GLOBAL_SESSION_ID } from '../shared/utils.js'

const visible = ref(false)
const x = ref(0)
const y = ref(0)
const panelTitle = ref('')
const panelContent = ref('')
const showAgent = ref(false)
const ctxSessionId = GLOBAL_SESSION_ID

function extractPanelContent(el) {
  // 标题
  const heading = el.querySelector('.panel-head h2, .hud-panel-head h2, h2, h3')
  const labelEl = el.querySelector('.tile-label, .hud-card-label')
  panelTitle.value = heading?.textContent?.trim() || labelEl?.textContent?.trim() || '面板'

  const body = el.querySelector('.panel-body, .hud-panel-body') || el
  const lines = []
  const seen = new Set()

  function add(line) {
    const key = line.trim()
    if (key && !seen.has(key)) { seen.add(key); lines.push(key) }
  }

  // 1. 数据卡片 (.tile / .hud-card)
  const tiles = body.querySelectorAll('.tile, .hud-card')
  for (const t of tiles) {
    const label = t.querySelector('.tile-label, .hud-card-label')?.textContent?.trim()
    const val = t.querySelector('.tile-value b, .hud-card-value b, .tile-value, .hud-card-value')?.textContent?.trim()
    const unit = t.querySelector('.tile-value span, .hud-card-value .unit')?.textContent?.trim()
    const note = t.querySelector('.tile-note, .hud-card-note')?.textContent?.trim()
    if (label) add(`- ${label}: ${val || '—'}${unit || ''}${note ? ' (' + note + ')' : ''}`)
  }

  // 2. 预警/风险条目 (.risk-item / .hud-risk-item)
  const riskItems = body.querySelectorAll('.risk-item, .hud-risk-item')
  for (const item of riskItems) {
    const title = item.querySelector('b')?.textContent?.trim()
    const badge = item.querySelector('.badge')?.textContent?.trim()
    const desc = item.querySelector('p')?.textContent?.trim()
    if (title && desc) add(`- ${title}${badge ? ' [' + badge + ']' : ''}: ${desc}`)
    else if (title) add(`- ${title}${badge ? ' [' + badge + ']' : ''}`)
  }

  // 3. 统计数字 (.mini-stat / .hud-mini-stat / .mcp-stat)
  const stats = body.querySelectorAll('.mini-stat, .hud-mini-stat, .mcp-stat')
  for (const s of stats) {
    const label = s.querySelector('span')?.textContent?.trim()
    const val = s.querySelector('b')?.textContent?.trim()
    if (label && val) add(`- ${label}: ${val}`)
  }

  // 4. 视频卡片
  const videoCards = body.querySelectorAll('.video-card')
  for (const v of videoCards) {
    const cam = v.querySelector('b')?.textContent?.trim()
    const status = v.querySelector('span')?.textContent?.trim()
    if (cam) add(`- 视频: ${cam}${status ? ' - ' + status : ''}`)
  }

  // 5. AI 解读
  const insight = body.querySelector('.hud-insight p, .forecast-insight p, .ai-insight')
  if (insight?.textContent?.trim()) add(`- 解读: ${insight.textContent.trim()}`)

  // 6. 表格数据
  const tables = body.querySelectorAll('table')
  for (const tbl of tables) {
    const headers = [...tbl.querySelectorAll('th')].map(h => h.textContent.trim())
    const rows = [...tbl.querySelectorAll('tbody tr')].slice(0, 10)
    if (headers.length && rows.length) {
      add(`--- 表格 (${headers.join(' | ')}) ---`)
      for (const row of rows) {
        const cells = [...row.querySelectorAll('td')].map(c => c.textContent.trim())
        if (cells.some(Boolean)) add(`  ${cells.join(' | ')}`)
      }
    }
  }

  // 7. 通用列表项
  const listItems = body.querySelectorAll('li')
  for (const li of listItems) {
    const text = li.textContent?.trim()
    if (text && text.length < 200) add(`- ${text}`)
  }

  // 8. 兜底：如果上述都没提取到，取 body 纯文本
  if (!lines.length) {
    const text = body.textContent?.trim()
    if (text) lines.push(text.slice(0, 3000))
  }

  return lines.join('\n')
}

function onContextMenu(e) {
  const panel = e.target.closest('.panel, .tile, .hud-panel, .hud-card, .hud-risk-item, .risk-item, .video-card')
  if (!panel) return
  e.preventDefault()
  visible.value = true
  x.value = e.clientX
  y.value = e.clientY
  panelContent.value = extractPanelContent(panel)
}

function close() { visible.value = false }

async function askAgent() {
  visible.value = false
  showAgent.value = true
  await nextTick()
  // 通过 window 传递上下文给 AgentChatPanel
  ;window.__ctxPanelData = { title: panelTitle.value, content: panelContent.value }
}

onMounted(() => document.addEventListener('contextmenu', onContextMenu))
onUnmounted(() => document.removeEventListener('contextmenu', onContextMenu))
</script>

<style scoped>
.ctx-menu-overlay { position: fixed; inset: 0; z-index: 200; }
.ctx-menu { position: fixed; z-index: 201; background: var(--glass-strong); -webkit-backdrop-filter: blur(20px); backdrop-filter: blur(20px); border: 1px solid var(--edge); border-radius: var(--radius-md); box-shadow: var(--shadow-3), 0 0 20px rgba(14, 165, 233, 0.1); padding: 4px; min-width: 150px; }
.ctx-item { display: block; width: 100%; padding: 9px 16px; border: 0; background: none; cursor: pointer; font-size: 13px; text-align: left; border-radius: var(--radius-sm); font-family: inherit; color: var(--ink); transition: all .15s ease; }
.ctx-item:hover { background: var(--chip-strong); color: var(--primary); }
.agent-modal-card2 {
  width: min(720px, 100%);
  height: min(600px, calc(100vh - 80px));
  display: flex; flex-direction: column;
  padding: 22px 24px 24px;
  border: 1px solid var(--line);
  border-radius: var(--radius-xl);
  background: var(--glass-strong);
  box-shadow: var(--shadow-4), 0 0 30px rgba(14, 165, 233, 0.08);
}
.agent-modal-card2 h2 {
  margin: 0; font-family: var(--display);
  font-size: 22px; font-weight: 600; letter-spacing: .03em; color: var(--ink);
}
.agent-modal-card2 :deep(.chat-panel) { flex: 1; min-height: 0; display: flex; flex-direction: column; }
</style>
