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

const visible = ref(false)
const x = ref(0)
const y = ref(0)
const panelTitle = ref('')
const panelContent = ref('')
const showAgent = ref(false)
const ctxSessionId = 'ctx-menu-' + Date.now()

function extractPanelContent(el) {
  const heading = el.querySelector('.panel-head h2')
  panelTitle.value = heading?.textContent?.trim() || el.querySelector('.tile-label')?.textContent?.trim() || '面板'

  const body = el.querySelector('.panel-body') || el
  const lines = []

  const riskItems = body.querySelectorAll('.risk-item')
  if (riskItems.length) {
    for (const item of riskItems) {
      const title = item.querySelector('b')?.textContent?.trim()
      const badge = item.querySelector('.badge')?.textContent?.trim()
      const desc = item.querySelector('p')?.textContent?.trim()
      const val = item.querySelector('.mini-stat b')?.textContent?.trim()
      const label = item.querySelector('.mini-stat span')?.textContent?.trim()
      if (title && desc) lines.push(`- ${title}${badge ? ' [' + badge + ']' : ''}: ${desc}`)
      else if (label && val) lines.push(`- ${label}: ${val}`)
      else if (title) lines.push(`- ${title}`)
    }
  }

  const stats = body.querySelectorAll('.mini-stat')
  if (stats.length) {
    for (const s of stats) {
      const label = s.querySelector('span')?.textContent?.trim()
      const val = s.querySelector('b')?.textContent?.trim()
      if (label && val) lines.push(`- ${label}: ${val}`)
    }
  }

  const tiles = body.querySelectorAll('.tile')
  if (tiles.length) {
    for (const t of tiles) {
      const label = t.querySelector('.tile-label')?.textContent?.trim()
      const val = t.querySelector('.tile-value b')?.textContent?.trim()
      const unit = t.querySelector('.tile-value span')?.textContent?.trim()
      const note = t.querySelector('.tile-note')?.textContent?.trim()
      if (label) lines.push(`- ${label}: ${val || '—'}${unit || ''} (${note || ''})`)
    }
  }

  const videoCards = body.querySelectorAll('.video-card')
  if (videoCards.length) {
    for (const v of videoCards) {
      const cam = v.querySelector('b')?.textContent?.trim()
      const label = v.querySelector('span')?.textContent?.trim()
      if (cam) lines.push(`- 视频: ${cam}${label ? ' - ' + label : ''}`)
    }
  }

  if (!lines.length) {
    const text = body.textContent?.trim()
    if (text) lines.push(text.slice(0, 3000))
  }
  return lines.join('\n')
}

function onContextMenu(e) {
  const panel = e.target.closest('.panel, .tile')
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
.ctx-menu { position: fixed; z-index: 201; background: #fff; border: 1px solid var(--line); border-radius: 10px; box-shadow: 0 8px 32px rgba(0,0,0,.12); padding: 4px; min-width: 140px; }
.ctx-item { display: block; width: 100%; padding: 8px 14px; border: 0; background: none; cursor: pointer; font-size: 13px; text-align: left; border-radius: 6px; font-family: inherit; color: var(--ink); }
.ctx-item:hover { background: rgba(109,146,159,.1); color: var(--river); }
.agent-modal-card2 {
  width: min(720px, 100%);
  height: min(600px, calc(100vh - 80px));
  display: flex; flex-direction: column;
  padding: 20px 22px 22px;
}
.agent-modal-card2 h2 {
  margin: 0; font-family: var(--serif);
  font-size: 22px; font-weight: 500; letter-spacing: -.04em;
}
.agent-modal-card2 :deep(.chat-panel) { flex: 1; min-height: 0; display: flex; flex-direction: column; }
</style>
