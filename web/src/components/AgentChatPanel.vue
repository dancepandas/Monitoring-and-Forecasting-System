<template>
  <div class="chat-panel">
    <div v-if="permissionAsk" class="perm-banner">
      <span>权限确认 — {{ permissionAsk.askReason || '请求操作权限' }}</span>
      <div class="perm-btns">
        <button class="btn" @click="respondPerm(false)">拒绝</button>
        <button class="btn primary" @click="respondPerm(true)">批准</button>
      </div>
    </div>
    <div v-if="reconnecting" class="recon-banner">
      <span class="spin">⟳</span> 连接断开，自动重连中...
    </div>

    <!-- Messages -->
    <div ref="scrollRef" class="chat-msgs">
      <div v-if="msgs.length === 0" class="welcome-msg">
        <div class="welcome-icon">FloodMind</div>
        <b>FloodMind 智能水文预报助手</b>
        <p>输入问题即可获得智能分析</p>
      </div>
      <template v-for="msg in msgs" :key="msg.id">
        <div v-if="msg.role === 'user'" class="msg-user">{{ msg.content }}</div>
        <div v-else class="msg-ai">
          <template v-for="g in buildGroups(msg)" :key="g._key">
            <!-- CoT -->
            <div v-if="g.type === 'cot'" class="cot-wrap" :class="{collapsed: !g._open, streaming: g._streaming}">
              <div class="cot-hd" @click="g._open = !g._open">
                <span class="cot-arrow">{{ g._open ? '▼' : '▶' }}</span>
                <span class="cot-label"><span class="cot-dot" :class="{pulse: g._streaming}"></span>{{ g._streaming ? '思考中' : '已思考' }}</span>
                <span class="cot-meta">{{ g._thoughtCount }} 步 · {{ g._toolCount }} 工具</span>
              </div>
              <div v-if="g._open" class="cot-body">
                <template v-for="b in g.items" :key="b._uk">
                  <div v-if="b.type === 'thought'" class="thought-step">
                    <div class="thought-dot-row"><span class="thought-dot-indicator" :class="{live: b._streaming}"></span></div>
                    <div class="thought-text" :class="{live: b._streaming}">{{ b.content }}</div>
                  </div>
                  <div v-if="b.type === 'tool'" class="tool-card" :class="{running: b.status==='running', error: b.status==='error'}" @click="b._open=!b._open">
                    <div class="tool-row">
                      <span class="tool-icon" :class="'ti-'+b.status">{{ toolIcon(b) }}</span>
                      <span class="tool-name">{{ b.toolName }}</span>
                      <span v-if="b.argsPreview" class="tool-args">{{ b.argsPreview }}</span>
                      <span class="tool-status">{{ b.status==='running'?'执行中':b.status==='done'?'完成':'失败' }}</span>
                      <span class="tool-expand">{{ b._open ? '▼' : '▶' }}</span>
                    </div>
                    <div v-if="b._open && b.output" class="tool-detail">
                      <div class="tool-output">{{ truncate(b.output, 300) }}</div>
                    </div>
                  </div>
                </template>
              </div>
            </div>
            <div v-if="g.type === 'answer' && g.items[0]?.content" class="answer-block">
              <div class="answer-text" v-html="renderMd(g.items[0].content)"></div>
            </div>
            <div v-if="g.type === 'error'" class="err-block">错误 — {{ g.items[0]?.content }}</div>
          </template>
          <div v-if="msg.tokenUsage" class="token-line">
            Tokens: {{ fmtNum(msg.tokenUsage.prompt) }} 入 · {{ fmtNum(msg.tokenUsage.completion) }} 出
          </div>
          <span v-if="msg._streaming" class="cursor">▍</span>
        </div>
      </template>
    </div>

    <!-- Input -->
    <div class="input-row">
      <textarea v-model="input" id="agentChatInput" name="message" class="chat-input" placeholder="输入任务指令..." aria-label="输入消息"
        :disabled="streaming" rows="1" @keydown="onKey" ref="inputRef"></textarea>
      <button v-if="streaming" class="btn danger send-btn" @click="doCancel">暂停</button>
      <button v-else class="btn primary send-btn" :disabled="!input.trim()" @click="doSend">发送</button>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { agentApi } from '../api/agent.js'
import { marked } from 'marked'
marked.setOptions({ breaks: true, gfm: true })

const props = defineProps({ sessionId: { type: String, required: true } })

function uid() { try { return crypto.randomUUID() } catch { return Date.now().toString(36) + Math.random().toString(36).slice(2, 10) } }

const msgs = reactive([])
const input = ref('')
const streaming = ref(false)
const reconnecting = ref(false)
const permissionAsk = ref(null)
const abortCtrl = ref(null)
const retryCount = ref(0)
const MAX_RETRIES = 3
const scrollRef = ref(null)
const inputRef = ref(null)

let stepCounter = 0; let blockId = 0
function bId() { return 'b' + (++blockId) }
function scroll() { nextTick(() => { const el = scrollRef.value; if (el) el.scrollTop = el.scrollHeight }) }
function fmtNum(n) { if (!n) return '0'; return n >= 1e6 ? (n/1e6).toFixed(1)+'M' : n >= 1e3 ? (n/1e3).toFixed(1)+'K' : String(n) }
function truncate(s, n) { s = String(s||''); return s.length > n ? s.slice(0, n) + '...' : s }
function toolIcon(b) { if (b.status === 'running') return '◌'; if (b.status === 'done') return '✓'; if (b.status === 'error') return '✗'; return '○' }
function renderMd(text) { return marked.parse(text || '') }

function buildGroups(msg) {
  const blocks = msg._blocks || []; const groups = []; let cotItems = []; let cotKey = 0
  function flushCOT() {
    if (cotItems.length === 0) return
    const streaming = cotItems.some(b => b._streaming || b.status === 'running')
    groups.push({ _key: 'cot'+ (++cotKey), type: 'cot', _open: streaming || cotItems.length <= 2, _streaming: streaming, _thoughtCount: cotItems.filter(b => b.type === 'thought').length, _toolCount: cotItems.filter(b => b.type === 'tool').length, items: [...cotItems] })
    cotItems = []
  }
  for (const b of blocks) {
    if (b.type === 'answer') { flushCOT(); groups.push({ _key: b._uk, type: 'answer', items: [b] }) }
    else if (b.type === 'error') { flushCOT(); groups.push({ _key: b._uk, type: 'error', items: [b] }) }
    else if (b.type === 'thought' || b.type === 'action') {
      if (b._archived && !msg._showArchived) continue
      const items = (b.type === 'action' ? (b.actions || []).map(a => ({ _uk: bId(), type: 'tool', toolName: a.toolName, status: a.status, output: a.content, argsPreview: a.argsPreview || '', _streaming: a.status === 'running', _open: a.status === 'error' })) : [b])
      cotItems.push(...items)
    }
  }
  flushCOT()
  return groups
}

async function doSend() {
  const text = input.value.trim(); if (!text || streaming.value) return
  input.value = ''
  msgs.push({ id: uid(), role: 'user', content: text })
  const aMsg = reactive({ id: uid(), role: 'assistant', content: '', _blocks: [], _streaming: true, _showArchived: false, tokenUsage: null })
  msgs.push(aMsg)
  streaming.value = true; reconnecting.value = false; retryCount.value = 0; permissionAsk.value = null; stepCounter = 0
  scroll()
  // 如果是从面板右键"询问智能体"进来的，注入面板上下文
  let fullMsg = text
  const ctx = window.__ctxPanelData
  if (ctx) {
    window.__ctxPanelData = null
    const now = new Date()
    const ts = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')} ${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`
    fullMsg = `[当前系统时间: ${ts}]\n\n以下是一个面板的当前数据内容：\n[面板: ${ctx.title}]\n${ctx.content}\n\n用户问题：${text}\n\n请根据以上面板数据回答用户问题。`
  }
  await streamChat(fullMsg, aMsg)
}

async function streamChat(message, aMsg) {
  const ctrl = new AbortController(); abortCtrl.value = ctrl
  try {
    const res = await agentApi.createChatRequest(props.sessionId, message, [], aMsg.id)
    if (!res.ok) { addBlock(aMsg, 'error', '请求失败'); finishMsg(aMsg); return }
    await readStream(res.body.getReader(), aMsg); finishMsg(aMsg)
  } catch (e) {
    if (e.name === 'AbortError') { addBlock(aMsg, 'error', '已取消'); finishMsg(aMsg); return }
    if (retryCount.value < MAX_RETRIES) { retryCount.value++; reconnecting.value = true; await new Promise(r => setTimeout(r, Math.min(1000*Math.pow(2,retryCount.value),10000))); reconnecting.value = false; return streamChat(message, aMsg) }
    addBlock(aMsg, 'error', e.message || '连接失败'); finishMsg(aMsg)
  }
}

async function readStream(reader, aMsg) {
  const decoder = new TextDecoder(); let buf = ''
  while (true) {
    const { done, value } = await reader.read(); if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n'); buf = lines.pop() || ''
    for (const line of lines) {
      let jsonStr = line.trim(); if (jsonStr.startsWith('data: ')) jsonStr = jsonStr.slice(6).trim()
      if (jsonStr === '[DONE]' || !jsonStr) continue
      try { handleEvent(JSON.parse(jsonStr), aMsg) } catch { /* skip */ }
    }
    scroll()
  }
  if (buf.trim()) { let jsonStr = buf.trim(); if (jsonStr.startsWith('data: ')) jsonStr = jsonStr.slice(6).trim(); if (jsonStr && jsonStr !== '[DONE]') { try { handleEvent(JSON.parse(jsonStr), aMsg) } catch { /* skip */ } } }
}

function handleEvent(ev, aMsg) {
  switch (ev.type || '') {
    case 'thought_delta': case 'reasoning': appendThought(aMsg, ev.content || ev.delta || '', true); break
    case 'answer_delta': case 'token': appendAnswer(aMsg, ev.content || ev.delta || ''); break
    case 'action_start': case 'tool_status': addAction(aMsg, ev.tool_name || 'tool', ev.call_id || uid(), 'running', ev.content || '', ev.tool_input || ''); break
    case 'action_end': case 'tool_result': addAction(aMsg, ev.tool_name || 'tool', ev.call_id || uid(), ev.status === 'error' ? 'error' : 'done', ev.content || '', ev.tool_input || ''); break
    case 'permission_ask': permissionAsk.value = { askId: ev.ask_id, askReason: ev.reason || '请求操作权限', sessionId: props.sessionId }; break
    case 'permission_resolved': permissionAsk.value = null; break
    case 'token_usage': aMsg.tokenUsage = { prompt: ev.prompt_tokens||0, completion: ev.completion_tokens||0, total: ev.total_tokens||0 }; break
    case 'final': case 'final_text': if (ev.content) aMsg.content = ev.content; archiveBlocks(aMsg); break
    case 'stream_end': archiveBlocks(aMsg); break
    default: if (ev.content || ev.delta) appendAnswer(aMsg, ev.content || ev.delta || '')
  }
}

function appendThought(aMsg, content, str) {
  if (!content) return
  const blocks = aMsg._blocks; const last = blocks[blocks.length-1]
  if (str && last?.type === 'thought' && !last._archived) { last.content += content; last._streaming = true }
  else { blocks.forEach(b => { if(b.type==='thought'){b._archived=true;b._collapsed=true;b._streaming=false} }); blocks.push({ _uk:bId(), type:'thought', content, _streaming:str, _archived:false }) }
}
function appendAnswer(aMsg, content) {
  if (!content) return
  const blocks = aMsg._blocks
  blocks.forEach(b => { if(b.type==='thought'){b._collapsed=true;b._streaming=false;b._archived=true} })
  const last = blocks[blocks.length-1]
  if (last?.type==='answer' && !last._archived) { last.content += content }
  else { blocks.forEach(b => { if(b.type==='answer') b._archived=true }); blocks.push({ _uk:bId(), type:'answer', content, _archived:false }) }
  aMsg.content = blocks.filter(b => b.type==='answer'&&!b._archived).map(b=>b.content).join('\n\n')
}
function addAction(aMsg, toolName, callId, status, content, inputPreview) {
  const blocks = aMsg._blocks
  const lastT = [...blocks].reverse().find(b=>b.type==='thought'); if(lastT){lastT._collapsed=true;lastT._streaming=false}
  if (status === 'running') {
    const lastA = [...blocks].reverse().find(b=>b.type==='action'&&!b._archived)
    if (lastA) { lastA.actions.push({ callId, toolName, status, content:'', argsPreview:inputPreview }) }
    else { blocks.push({ _uk:bId(), type:'action', _archived:false, actions:[{callId,toolName,status,content:'',argsPreview:inputPreview}] }) }
  } else {
    for (const b of blocks) { if(b.type!=='action')continue; const a=(b.actions||[]).find(x=>x.callId===callId||(x.toolName===toolName&&x.status==='running')); if(a){a.status=status;a.content=content;break} }
  }
}
function addBlock(aMsg, type, content) { aMsg._blocks.push({ _uk:bId(), type, content, _archived:false }) }
function archiveBlocks(aMsg) { aMsg._blocks.forEach(b => { if(b.type==='thought'||b.type==='action'){b._archived=true;b._collapsed=true;b._streaming=false} }) }
function finishMsg(aMsg) { aMsg._streaming=false; archiveBlocks(aMsg); streaming.value=false; abortCtrl.value=null; if(!aMsg._blocks.length&&!aMsg.content)aMsg.content='(无回复)'; scroll() }
function doCancel() { if(abortCtrl.value) abortCtrl.value.abort(); streaming.value=false }
async function respondPerm(approved) { const p=permissionAsk.value; if(!p)return; permissionAsk.value=null; await agentApi.respondPermission(p.askId,approved,p.sessionId).catch(()=>{}) }
function onKey(e) { if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();doSend()} }

onMounted(() => scroll())
</script>

<style scoped>
.chat-panel { display:flex; flex-direction:column; height:100%; min-height:0; gap:6px; }
.chat-msgs { flex:1; min-height:0; max-height:none !important; overflow-y:auto; overflow-x:hidden; display:grid; align-content:start; gap:10px; padding:4px 4px 12px 0; }

/* Common message styles */
.msg-user { justify-self:end; max-width:75%; background:#2d2923; color:#fff; border-radius:18px 18px 6px 18px; padding:10px 14px; font-size:13px; line-height:1.55; word-break:break-word; animation:msgIn .2s ease; }
.msg-ai { display:grid; gap:6px; max-width:100%; }
.welcome-msg { text-align:center; padding:24px 16px; }
.welcome-icon { font-family:var(--serif); font-size:24px; font-weight:600; letter-spacing:-.04em; margin-bottom:12px; color:var(--ink); }
.welcome-msg b { display:block; font-size:15px; margin-bottom:6px; }
.welcome-msg p { margin:0; color:var(--muted); font-size:13px; }

/* Banners */
.perm-banner { display:flex; align-items:center; justify-content:space-between; gap:10px; padding:8px 14px; border:1px solid var(--amber); border-radius:12px; background:rgba(181,139,63,.08); font-size:12px; flex-shrink:0; }
.perm-btns { display:flex; gap:6px; flex-shrink:0; }
.recon-banner { display:flex; align-items:center; gap:8px; padding:8px 14px; border-radius:12px; background:rgba(109,146,159,.1); font-size:12px; color:var(--river); flex-shrink:0; }
.spin { display:inline-block; animation:spin 1s linear infinite; }
@keyframes spin { to{transform:rotate(360deg)} }
@keyframes msgIn { from{opacity:0;transform:translateY(4px)} to{opacity:1;transform:none} }

/* CoT */
.cot-wrap { border:1px solid var(--line); border-radius:12px; overflow:hidden; background:rgba(109,146,159,.025); }
.cot-wrap.streaming { border-color:var(--river-soft); box-shadow:0 0 0 1px rgba(109,146,159,.12); }
.cot-hd { display:flex; align-items:center; gap:8px; padding:8px 12px; cursor:pointer; user-select:none; font-size:12px; }
.cot-hd:hover { background:rgba(109,146,159,.05); }
.cot-arrow { font-size:8px; width:12px; color:var(--muted); flex-shrink:0; }
.cot-label { display:flex; align-items:center; gap:6px; font-weight:600; color:var(--river); }
.cot-meta { margin-left:auto; font-size:10px; color:var(--muted); font-weight:400; }
.cot-dot { width:7px; height:7px; border-radius:50%; background:var(--river); flex-shrink:0; }
.cot-dot.pulse { animation:cotPulse 1.5s ease-in-out infinite; }
@keyframes cotPulse { 0%,100%{opacity:1;box-shadow:0 0 0 0 rgba(109,146,159,.4)} 50%{opacity:.5;box-shadow:0 0 0 6px transparent} }
.cot-body { padding:0 12px 10px; display:grid; gap:6px; }

/* Thought */
.thought-step { display:grid; grid-template-columns:auto 1fr; gap:8px; align-items:start; }
.thought-dot-row { width:16px; display:flex; justify-content:center; padding-top:3px; }
.thought-dot-indicator { width:5px; height:5px; border-radius:50%; background:var(--river); opacity:.4; }
.thought-dot-indicator.live { opacity:1; animation:cotPulse 1.5s ease-in-out infinite; }
.thought-text { font-size:11px; color:var(--ink-2); line-height:1.55; white-space:pre-wrap; word-break:break-word; }
.thought-text.live { color:var(--ink); }

/* Tool card */
.tool-card { border:1px solid var(--line); border-radius:8px; overflow:hidden; cursor:pointer; background:rgba(255,255,255,.7); transition:all .15s; }
.tool-card:hover { border-color:rgba(37,33,28,.18); }
.tool-card.running { border-color:rgba(181,139,63,.25); background:rgba(181,139,63,.04); animation:toolPulse 2s ease-in-out infinite; }
@keyframes toolPulse { 0%,100%{box-shadow:0 0 0 0 rgba(181,139,63,.1)} 50%{box-shadow:0 0 0 3px transparent} }
.tool-row { display:flex; align-items:center; gap:8px; padding:7px 10px; font-size:11px; }
.tool-icon { flex-shrink:0; width:16px; height:16px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:9px; font-weight:700; }
.ti-running { background:rgba(181,139,63,.15); color:var(--amber); animation:spin 1.5s linear infinite; }
.ti-done { background:rgba(95,117,103,.13); color:var(--ok); }
.ti-error { background:rgba(169,79,67,.12); color:var(--danger); }
.tool-name { font-weight:600; color:var(--ink-2); font-family:var(--mono); font-size:10px; white-space:nowrap; }
.tool-args { color:var(--muted); font-size:10px; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.tool-status { font-size:9px; color:var(--muted); white-space:nowrap; }
.tool-expand { font-size:7px; color:var(--muted); flex-shrink:0; }
.tool-detail { padding:0 10px 8px 28px; border-top:1px solid var(--line); }
.tool-output { font-size:10px; color:var(--ink-2); line-height:1.5; white-space:pre-wrap; word-break:break-word; max-height:150px; overflow-y:auto; }

/* Answer */
.answer-block { display:grid; gap:4px; }
.answer-text { font-size:13px; line-height:1.65; color:var(--ink); word-break:break-word; }
.answer-text :deep(h1){font-size:18px;font-weight:700;margin:12px 0 6px}
.answer-text :deep(h2){font-size:16px;font-weight:700;margin:10px 0 6px}
.answer-text :deep(h3){font-size:14px;font-weight:600;margin:8px 0 4px}
.answer-text :deep(ul),.answer-text :deep(ol){margin:4px 0;padding-left:20px}
.answer-text :deep(li){margin:2px 0}
.answer-text :deep(table){border-collapse:collapse;width:100%;margin:8px 0;font-size:12px}
.answer-text :deep(th),.answer-text :deep(td){border:1px solid var(--line);padding:4px 8px;text-align:left}
.answer-text :deep(th){background:rgba(37,33,28,.04);font-weight:600}
.answer-text :deep(pre){margin:8px 0;padding:10px;border-radius:10px;background:rgba(37,33,28,.06);font-family:var(--mono);font-size:11px;overflow-x:auto;white-space:pre-wrap}
.answer-text :deep(code){font-family:var(--mono);font-size:11px;background:rgba(37,33,28,.08);border-radius:4px;padding:1px 5px}
.answer-text :deep(b){font-weight:700}

/* Error */
.err-block { padding:8px 12px; border-radius:10px; background:rgba(169,79,67,.1); color:var(--danger); font-size:12px; }

/* Token */
.token-line { font-size:9px; color:var(--muted); opacity:.5; margin-top:2px; }

/* Cursor */
.cursor { display:inline; color:var(--ink); animation:blink 1s step-end infinite; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }

/* Input */
.input-row { display:flex; align-items:flex-end; gap:8px; flex-shrink:0; }
.chat-input { flex:1; min-width:0; min-height:38px; max-height:140px; border:1px solid rgba(37,33,28,.12); border-radius:18px; background:rgba(255,255,255,.72); padding:8px 14px; outline:none; color:var(--ink); font-size:13px; resize:none; line-height:1.45; font-family:inherit; }
.chat-input:focus { border-color:var(--clay); }
.chat-input::placeholder { color:var(--muted); }
.send-btn { flex-shrink:0; min-height:36px; padding:0 16px; font-size:13px; }
.send-btn:disabled { opacity:.45; cursor:not-allowed; }
</style>
