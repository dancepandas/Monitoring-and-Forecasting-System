<template>
  <Topbar title="FloodMind 智能体" subtitle="数据分析 / 模型调用 / 报告生成 · Enter 发送 · Shift+Enter 换行" />
  <section class="agent-page">

    <article class="panel agent-chat-panel">
      <div class="chat-body">
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
        <div ref="scrollRef" class="messages chat-msgs">
          <div v-if="msgs.length === 0" class="welcome-msg">
            <div class="welcome-icon">FloodMind</div>
            <b>FloodMind 智能水文预报助手</b>
            <p>可以帮你分析水位流量、运行预报模型、生成报告。<br>点击下方任务快速开始，或直接输入指令。</p>
            <div class="quick-tasks">
              <div class="qt-title">常用任务</div>
              <div class="qt-grid">
                <button class="qt-card" v-for="t in quickTasks" :key="t.id" @click="runQuickTask(t)" :disabled="streaming">
                  
                  <div class="qt-info">
                    <span class="qt-label">{{ t.label }}</span>
                    <span class="qt-desc">{{ t.desc }}</span>
                  </div>
                </button>
              </div>
            </div>
          </div>

          <!-- Quick task bar (always visible) -->
          <div class="quick-bar" v-if="quickTasks.length" style="padding-top:6px;">
            <button v-for="t in quickTasks" :key="'bar'+t.id" class="qt-chip" :title="t.desc" @click="runQuickTask(t)" :disabled="streaming">
              {{ t.label }}
            </button>
          </div>

          <template v-for="msg in msgs" :key="msg.id">
            <!-- User message -->
            <div v-if="msg.role === 'user'" class="msg-user">{{ msg.content }}</div>

            <!-- Assistant message -->
            <div v-else class="msg-ai">
              <div v-if="msg._archivedCount" class="archived-hint" @click="msg._showArchived = !msg._showArchived">
                {{ msg._showArchived ? '收起' : '展开 ' + msg._archivedCount + ' 个已归档步骤' }}
              </div>

              <!-- Build CoT groups from blocks -->
              <template v-for="g in buildGroups(msg)" :key="g._key">
                <!-- Chain-of-Thought wrapper -->
                <div v-if="g.type === 'cot'" class="cot-wrap" :class="{collapsed: !g._open, streaming: g._streaming}">
                  <div class="cot-hd" @click="g._open = !g._open">
                    <span class="cot-arrow">{{ g._open ? '▼' : '▶' }}</span>
                    <span class="cot-label">
                      <span class="cot-dot" :class="{pulse: g._streaming}"></span>
                      {{ g._streaming ? '思考中' : '已思考' }}
                    </span>
                    <span class="cot-meta">{{ g._thoughtCount }} 步 · {{ g._toolCount }} 工具</span>
                  </div>
                  <div v-if="g._open" class="cot-body">
                    <template v-for="b in g.items" :key="b._uk">
                      <!-- Thought step -->
                      <div v-if="b.type === 'thought'" class="thought-step">
                        <div class="thought-dot-row">
                          <span class="thought-dot-indicator" :class="{live: b._streaming}"></span>
                        </div>
                        <div class="thought-text" :class="{live: b._streaming}">{{ b.content }}</div>
                      </div>

                      <!-- Tool card -->
                      <div v-if="b.type === 'tool'" class="tool-card" :class="{running: b.status==='running', error: b.status==='error'}" @click="b._open=!b._open">
                        <div class="tool-row">
                          <span class="tool-icon" :class="'ti-'+b.status">{{ toolIcon(b) }}</span>
                          <span class="tool-name">{{ b.toolName }}</span>
                          <span v-if="b.argsPreview" class="tool-args">{{ b.argsPreview }}</span>
                          <span class="tool-status">{{ b.status==='running'?'执行中':b.status==='done'?'完成':'失败' }}</span>
                          <span class="tool-expand">{{ b._open ? '▼' : '▶' }}</span>
                        </div>
                        <div v-if="b._open && (b.argsPreview || b.output)" class="tool-detail">
                          <div v-if="b.output" class="tool-output">{{ truncate(b.output, 300) }}</div>
                          <div v-if="b.status==='error'" class="tool-error">{{ b.error || b.output }}</div>
                        </div>
                      </div>
                    </template>
                  </div>
                </div>

                <!-- Standalone answer block (outside CoT) -->
                <div v-if="g.type === 'answer' && g.items[0]?.content" class="answer-block">
                  <div class="answer-text" v-html="renderMd(g.items[0].content)"></div>
                </div>

                <!-- Error block -->
                <div v-if="g.type === 'error'" class="err-block">错误 — {{ g.items[0]?.content }}</div>
              </template>

              <!-- References -->
              <div v-if="msg.refs?.length" class="refs-block">
                <div class="refs-title">参考来源</div>
                <a v-for="(r,i) in msg.refs" :key="i" class="ref-item" :href="r.url||'#'" target="_blank">
                  <span class="ref-idx">{{ i+1 }}</span> {{ r.title }}
                </a>
              </div>

              <!-- Artifacts -->
              <div v-for="a in msg.artifacts||[]" :key="a.id" class="artifact-row">
                <span v-if="a.type==='image_generated'" class="artifact-img-wrap" @click="previewImg = a">
                  <img v-if="a.image_url" :src="a.image_url" class="artifact-img" />
                  <span v-else class="artifact-label">图片 — {{ a.name }}</span>
                </span>
                <span v-else class="artifact-file">文件 — {{ a.name }}
                  <a v-if="a.download_url" :href="a.download_url" target="_blank">下载</a>
                </span>
              </div>

              <!-- Token usage -->
              <div v-if="msg.tokenUsage" class="token-line">
                Tokens: {{ fmtNum(msg.tokenUsage.prompt) }} 入 · {{ fmtNum(msg.tokenUsage.completion) }} 出 · {{ fmtNum(msg.tokenUsage.total) }} 总计
              </div>

              <!-- Streaming cursor -->
              <span v-if="msg._streaming" class="cursor">▍</span>
            </div>
          </template>
        </div>

        <!-- Context bar -->
        <div v-if="files.length || workflow" class="ctx-bar">
          <span v-for="f in files" :key="f.id" class="ctx-file" @click="previewFile(f)">文件 · {{ f.name }}</span>
          <span v-if="workflow" class="ctx-wf">
            流程 · {{ workflow.title }} {{ workflow.steps?.filter(s=>s.status==='completed').length||0 }}/{{ workflow.steps?.length||0 }}
          </span>
        </div>

        <!-- Context bar inside chat panel -->
        <div v-if="files.length || workflow" class="ctx-bar">
          <span v-for="f in files" :key="f.id" class="ctx-file" @click="previewFile(f)">文件 · {{ f.name }}</span>
          <span v-if="workflow" class="ctx-wf">
            流程 · {{ workflow.title }} {{ workflow.steps?.filter(s=>s.status==='completed').length||0 }}/{{ workflow.steps?.length||0 }}
          </span>
        </div>
      </div>
    </article>

    <!-- Right panel -->
    <aside class="agent-side">
      <div class="side-card" v-if="todos.length">
        <div class="side-hd">任务列表 <span class="side-count">{{ todos.filter(t=>t.status==='completed').length }}/{{ todos.length }}</span></div>
        <div class="side-body">
          <div v-for="t in todos" :key="t.id" class="todo-row" :class="'todo-'+t.status">
            <span class="todo-dot">{{ t.status==='completed'?'✓':t.status==='in_progress'?'◎':'○' }}</span>
            <span class="todo-txt">{{ t.content }}</span>
            <span v-if="t.priority==='high'" class="todo-prio">高</span>
          </div>
        </div>
      </div>

      <div class="side-card" v-if="sessionTokens.total">
        <div class="side-hd">Token 用量</div>
        <div class="side-body">
          <div class="tok-row"><span>输入</span><b>{{ fmtNum(sessionTokens.prompt) }}</b></div>
          <div class="tok-row"><span>输出</span><b>{{ fmtNum(sessionTokens.completion) }}</b></div>
          <div class="tok-row"><span>总计</span><b>{{ fmtNum(sessionTokens.total) }}</b></div>
        </div>
      </div>

      <div class="side-card">
        <div class="side-hd">历史对话 <button class="side-new" @click="newSession">+ 新建</button></div>
        <div class="side-body sess-list">
          <div v-for="s in sessions" :key="s.session_id" class="sess-row" :class="{active:s.session_id===sid}" @click="switchSess(s.session_id)">
            <span class="sess-name">{{ s.title||'新对话' }}</span>
            <span class="sess-time">{{ fmtTs(s.updated_at||s.created_at) }}</span>
            <button class="sess-del" @click.stop="delSession(s.session_id)">x</button>
          </div>
          <div v-if="!sessions.length" class="sess-empty">暂无历史会话</div>
        </div>
      </div>
    </aside>
  </section>

  <!-- Input panel — workspace grid row 3, same column layout as agent-page -->
  <div class="input-panel-wrap">
    <div class="input-panel-main">
      <div class="input-row">
        <button class="btn upload-btn" title="上传文件" @click="$refs.fileInput.click()" :disabled="streaming">+</button>
        <input ref="fileInput" id="fileInput" name="file" type="file" hidden multiple
          accept=".csv,.xlsx,.xls,.txt,.json,.docx,.pdf,.md,.png,.jpg,.jpeg,.webp,.gif,.bmp"
          @change="onFileChange" />
        <textarea v-model="input" id="chatInput" name="message" class="chat-input" placeholder="输入任务指令..." aria-label="输入消息"
          :disabled="streaming" rows="1" @keydown="onKey" ref="inputRef"></textarea>
        <button v-if="streaming" class="btn danger send-btn" @click="doCancel">暂停</button>
        <button v-else class="btn primary send-btn" :disabled="!input.trim()" @click="doSend">发送</button>
      </div>
      <div class="toolbar">
        <button class="tb-btn" :class="{on:config.enable_reasoning}" @click="config.enable_reasoning=!config.enable_reasoning">思考</button>
        <label for="agent-model-select" class="sr-only">选择模型</label>
        <select v-if="models.length" id="agent-model-select" name="model" v-model="config.model_key" class="tb-select" aria-label="选择模型" @change="onModelChange">
          <option v-for="m in models" :key="m.key" :value="m.key">{{ m.label }}</option>
        </select>
      </div>
    </div>
    <div class="input-panel-side"></div>
  </div>

  <Teleport to="body">
    <div v-if="previewImg" class="img-modal" @click.self="previewImg=null">
      <img :src="previewImg.image_url||previewImg.url" />
      <button class="btn img-close" @click="previewImg=null">关闭</button>
    </div>
  </Teleport>
</template>

<script setup>
import { reactive, ref, onMounted, onUnmounted, nextTick } from 'vue'
import Topbar from '../components/Topbar.vue'
import { agentApi } from '../api/agent.js'
import { marked } from 'marked'

marked.setOptions({ breaks: true, gfm: true })

function uid() {
  try { return crypto.randomUUID() } catch { return Date.now().toString(36) + Math.random().toString(36).slice(2, 10) }
}

const sid = ref(localStorage.getItem('floodmind_sid') || uid())
localStorage.setItem('floodmind_sid', sid.value)

const msgs = reactive([])
const input = ref('')
const streaming = ref(false)
const reconnecting = ref(false)
const permissionAsk = ref(null)
const abortCtrl = ref(null)
const readerRef = ref(null)
const wasStreaming = ref(false)
const retryCount = ref(0)
const MAX_RETRIES = 10

const todos = reactive([])
const sessionTokens = reactive({ prompt: 0, completion: 0, total: 0 })
const sessions = ref([])
const workflow = ref(null)
const files = ref([])
const models = ref([])
const config = reactive({ model_key: '', enable_reasoning: true, enable_search: false })
const previewImg = ref(null)

// ── 常用任务 ──
const quickTasks = [
  {
    id: 'realtime',    label: '最新水情',
    desc: '查询仙桃站最新水位和设备状态',
    prompt: `查询仙桃站（00106）最新水情。

1. 调用 query_latest(station_codes="00106") 获取最新一条水位数据；
2. 调用 query_devices(station_code="00106") 获取设备状态。

直接用返回的最新数值展示即可，无需指定时间范围。若数据为空则说明缓存未就绪。

输出格式：
## 最新水情（仙桃站 00106）
- 最新水位：{waterLevel} m（上报时间：{measureTime}）
- 设备状态：在线/离线
- 判断：与警戒水位 35.1m 比较，给出是否正常的结论。`
  },
  {
    id: 'trend',    label: '趋势分析',
    desc: '分析近期水位与流量变化趋势',
    prompt: `分析仙桃站（00106）近期水情趋势。

1. 调用 analyze_trend(station_code="00106", metric="level") 分析水位；
2. 调用 analyze_trend(station_code="00106", metric="flow") 分析流量。

工具会自动拉取缓存中全部可用数据计算趋势，无需手动指定时间范围。

输出格式：
## 趋势分析
| 指标 | 数据点数 | 最新值 | 趋势 | 斜率 |
|------|---------|--------|------|------|
| 水位 | {count} | {latest} m | {up/down/stable} | {slope} |
| 流量 | {count} | {latest} m³/s | {up/down/stable} | {slope} |
- 结论：水位和流量是否同步变化？是否需要关注？`
  },
  {
    id: 'forecast',    label: '流量预报',
    desc: '运行模型预测未来 12h 流量',
    prompt: `对仙桃站（00106）进行未来 12 小时流量预报。

调用 run_forecast(station_code="00106", prediction_length=12, target="Flow")。

工具会从缓存中读取历史流量数据并自动预处理（等间隔对齐、插值空缺），无需手动传 begin/end。

输出格式：
## 流量预报（未来 12h）
- 输入数据点数：{input_count}，预处理：{preprocess.gap_info}
- 预报峰值：{max(predictions)} m³/s，谷值：{min(predictions)} m³/s
- 趋势：上升/下降/平稳
- 若返回 error 请说明原因。`
  },
  {
    id: 'warning',    label: '预警研判',
    desc: '检查最新预警状态并给出处置建议',
    prompt: `对仙桃站（00106）进行预警研判。

1. 调用 query_latest(station_codes="00106") 获取最新水位；
2. 调用 list_warnings(station_codes="00106") 获取当前预警；
3. 如有预警，根据等级调用 generate_disposal(station_code="00106", level="{等级}", metric="level")。

输出格式：
## 当前状态
- 最新水位：{waterLevel} m
- 预警：{total} 条，最高等级：{level}
## 处置建议
按优先级列出。若无预警，说明当前安全。`
  },
  {
    id: 'daily',    label: '生成日报',
    desc: '调用脚本生成昨日水情日报',
    prompt: `生成仙桃站（00106）昨日水情日报。

1. 调用 generate_report(report_type="daily", station_code="00106")，不传 date 则默认取昨天；
2. 调用 query_reports() 确认文件已生成。

输出格式：
## 日报生成结果
- 文件名：{filename}，路径：{path}，大小：{size} bytes
- 若失败，说明原因。`
  },
  {
    id: 'compare',    label: '多站对比',
    desc: '对比三个站点的最新水情',
    prompt: `对比仙桃站(00106)、城西站(00107)、南桥站(00108)最新水情。

1. 调用 compare_stations(station_codes="00106,00107,00108", metric="level")；
2. 调用 compare_stations(station_codes="00106,00107,00108", metric="flow")。

工具从缓存读取各站最新可用数据做统计，无需指定时间范围。

输出格式：
## 多站水情对比
| 站点 | 水位 max/min/avg | 流量 max/min/avg |
|------|------------------|-------------------|
- 上下游关系判断，流域整体风险。`
  },
  {
    id: 'devices',    label: '设备巡检',
    desc: '检查设备在线状态与视频监控',
    prompt: `检查仙桃站（00106）监测设备和视频状态。

1. 调用 query_devices(station_code="00106")；
2. 调用 query_video_status(station_code="00106")。

输出格式：
## 设备状态
| 设备编码 | 类型 | 状态 |
## 视频监控
| 摄像头ID | 状态 |
- 是否存在离线？给出处理建议。`
  },
  {
    id: 'schedule',    label: '定时日报',
    desc: '每天 0:00 自动生成日报 / 周一生成周报',
    prompt: `创建自动日报/周报定时任务。

日报：调用 CreateScheduledTask(task_type="agent_daily_report", cron="0 0 * * *")，每天 0:00 采集全站水位/流量/预警数据，LLM 整理为完整日报。
周报：调用 CreateScheduledTask(task_type="agent_weekly_report", cron="0 0 * * 1")，每周一 0:00 汇总过去 7 天日报为周报。
最后调用 ListScheduledTasks() 确认。

输出格式：
## 定时任务
- 任务ID：{task_id}，类型：{task_type}
- 周期说明，下次执行：{next_run_time}`
  }
]

function withTime(text) {
  const now = new Date()
  const ts = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')} ${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`
  return `[当前系统时间: ${ts}]\n\n${text}`
}

function runQuickTask(t) {
  if (streaming.value) return
  msgs.push({ id: uid(), role: 'user', content: t.label })
  const aMsg = reactive({
    id: uid(), role: 'assistant', content: '',
    _blocks: [], _streaming: true, _archivedCount: 0, _showArchived: false,
    refs: [], artifacts: [], tokenUsage: null
  })
  msgs.push(aMsg)
  streaming.value = true; reconnecting.value = false; retryCount.value = 0
  permissionAsk.value = null; stepCounter = 0
  scroll()
  streamChat(withTime(t.prompt), aMsg)
}

const scrollRef = ref(null)
const inputRef = ref(null)
const fileInput = ref(null)

let stepCounter = 0
let blockId = 0
function bId() { return 'b' + (++blockId) }
function scroll() { nextTick(() => { const el = scrollRef.value; if (el) el.scrollTop = el.scrollHeight }) }
function fmtNum(n) { if (!n) return '0'; return n >= 1e6 ? (n/1e6).toFixed(1)+'M' : n >= 1e3 ? (n/1e3).toFixed(1)+'K' : String(n) }
function fmtTs(ts) { if (!ts) return ''; const d = new Date(ts); return `${d.getMonth()+1}/${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}` }
function truncate(s, n) { s = String(s||''); return s.length > n ? s.slice(0, n) + '...' : s }

// ── CoT grouping ──
function buildGroups(msg) {
  const blocks = msg._blocks || []
  const streaming = msg._streaming
  const groups = []
  let cotItems = []
  let cotKey = 0

  function flushCOT() {
    if (cotItems.length === 0) return
    const streaming = cotItems.some(b => b._streaming || b.status === 'running')
    const open = streaming || (cotItems.length <= 2)
    groups.push({
      _key: 'cot' + (++cotKey),
      type: 'cot',
      _open: open,
      _streaming: streaming,
      _thoughtCount: cotItems.filter(b => b.type === 'thought').length,
      _toolCount: cotItems.filter(b => b.type === 'tool').length,
      items: [...cotItems]
    })
    cotItems = []
  }

  // Convert action blocks to individual tool entries
  function flattenTools(b) {
    if (b.type !== 'action') return [b]
    return (b.actions || []).map(a => ({
      _uk: bId(),
      type: 'tool',
      toolName: a.toolName,
      status: a.status,
      output: a.content,
      argsPreview: a.argsPreview || '',
      _streaming: a.status === 'running',
      _open: a.status === 'error'
    }))
  }

  for (const b of blocks) {
    if (b.type === 'answer') {
      flushCOT()
      groups.push({ _key: b._uk, type: 'answer', items: [b] })
    } else if (b.type === 'error') {
      flushCOT()
      groups.push({ _key: b._uk, type: 'error', items: [b] })
    } else if (b.type === 'thought' || b.type === 'action') {
      if (b._archived && !msg._showArchived) continue
      const items = flattenTools(b)
      cotItems.push(...items)
    }
  }

  if (streaming) {
    // Keep CoT open during streaming
  } else {
    flushCOT()
  }

  return groups
}

function toolIcon(b) {
  if (b.status === 'running') return '◌'
  if (b.status === 'done') return '✓'
  if (b.status === 'error') return '✗'
  return '○'
}

// ── Markdown ──
function renderMd(text) {
  return marked.parse(text || '')
}

function lastA() {
  for (let i = msgs.length - 1; i >= 0; i--) if (msgs[i].role === 'assistant') return msgs[i]
  return null
}

// ── Send ──
async function doSend() {
  const text = input.value.trim()
  if (!text || streaming.value) return
  input.value = ''
  msgs.push({ id: uid(), role: 'user', content: text })
  const aMsg = reactive({
    id: uid(), role: 'assistant', content: '',
    _blocks: [], _streaming: true, _archivedCount: 0, _showArchived: false,
    refs: [], artifacts: [], tokenUsage: null
  })
  msgs.push(aMsg)
  streaming.value = true; reconnecting.value = false; retryCount.value = 0
  permissionAsk.value = null; stepCounter = 0
  scroll()
  await streamChat(withTime(text), aMsg)
}

async function streamChat(message, aMsg) {
  const ctrl = new AbortController(); abortCtrl.value = ctrl
  try {
    const res = await agentApi.createChatRequest(sid.value, message, [], aMsg.id)
    if (!res.ok) {
      const errText = await res.text().catch(() => '')
      if (res.status >= 400 && res.status < 500) { addBlock(aMsg, 'error', errText || `请求失败`); finishMsg(aMsg); return }
      throw new Error(errText || `HTTP ${res.status}`)
    }
    await readStream(res.body.getReader(), aMsg)
    finishMsg(aMsg)
    await agentApi.saveSession(sid.value).catch(() => {})
  } catch (e) {
    if (e.name === 'AbortError') { addBlock(aMsg, 'error', '已取消'); finishMsg(aMsg); return }
    if (retryCount.value < MAX_RETRIES) {
      retryCount.value++; reconnecting.value = true
      await new Promise(r => setTimeout(r, Math.min(1000 * Math.pow(2, retryCount.value), 30000)))
      reconnecting.value = false
      return streamChat(message, aMsg)
    }
    addBlock(aMsg, 'error', e.message || '连接失败'); finishMsg(aMsg)
  }
}

async function readStream(reader, aMsg) {
  readerRef.value = reader
  const decoder = new TextDecoder(); let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n'); buf = lines.pop() || ''
    for (const line of lines) {
      const raw = line.trim()
      let jsonStr = raw
      if (raw.startsWith('data: ')) jsonStr = raw.slice(6).trim()
      if (jsonStr === '[DONE]' || !jsonStr) continue
      try { handleEvent(JSON.parse(jsonStr), aMsg) } catch { /* skip */ }
    }
    scroll()
  }
  if (buf.trim()) {
    let jsonStr = buf.trim()
    if (jsonStr.startsWith('data: ')) jsonStr = jsonStr.slice(6).trim()
    if (jsonStr && jsonStr !== '[DONE]') {
      try { handleEvent(JSON.parse(jsonStr), aMsg) } catch { /* skip */ }
    }
  }
}

function handleEvent(ev, aMsg) {
  const type = ev.type || ''
  switch (type) {
    case 'thought_delta': case 'reasoning':
      appendThought(aMsg, ev.content || ev.delta || '', true); break
    case 'answer_delta': case 'token':
      appendAnswer(aMsg, ev.content || ev.delta || ''); break
    case 'action_start': case 'tool_status':
      addAction(aMsg, ev.tool_name || 'tool', ev.call_id || uid(), 'running', ev.content || '', ev.tool_input || ''); break
    case 'action_end': case 'tool_result':
      addAction(aMsg, ev.tool_name || 'tool', ev.call_id || uid(), ev.status === 'error' ? 'error' : 'done', ev.content || '', ev.tool_input || ''); break
    case 'permission_ask':
      permissionAsk.value = { askId: ev.ask_id, askReason: ev.reason || '请求操作权限', sessionId: sid.value }; break
    case 'permission_resolved':
      permissionAsk.value = null; break
    case 'todo_updated': {
      const items = ev.todos || []; todos.length = 0
      items.forEach(t => todos.push({ id: t.id, content: t.content, status: t.status||'pending', priority: t.priority||'normal' }))
    } break
    case 'workflow_plan':
      workflow.value = { title: ev.title || '调度', steps: (ev.steps||[]).map(s => ({ ...s, status: s.status==='done'?'completed':s.status||'pending' })) }; break
    case 'workflow_step':
      if (workflow.value) {
        const idx = workflow.value.steps.findIndex(s => s.key === ev.step_key)
        if (idx >= 0) workflow.value.steps[idx].status = ev.status==='done'?'completed':ev.status||workflow.value.steps[idx].status
      } break
    case 'token_usage':
      aMsg.tokenUsage = { prompt: ev.prompt_tokens||0, completion: ev.completion_tokens||0, total: ev.total_tokens||0 }
      sessionTokens.prompt = aMsg.tokenUsage.prompt
      sessionTokens.completion = aMsg.tokenUsage.completion
      sessionTokens.total = aMsg.tokenUsage.total
      break
    case 'file_generated': case 'image_generated':
      if (!aMsg.artifacts) aMsg.artifacts = []
      aMsg.artifacts.push({ id: uid(), type: ev.type||type, name: ev.filename||ev.name||'file', image_url: ev.image_url, download_url: ev.download_url, url: ev.url }); break
    case 'error': case 'llm_token_error':
      addBlock(aMsg, 'error', ev.content || ev.message || '处理出错'); break
    case 'final': case 'final_text':
      if (ev.content) aMsg.content = ev.content
      archiveBlocks(aMsg); break
    case 'stream_end':
      archiveBlocks(aMsg); break
    default:
      if (ev.content || ev.delta) appendAnswer(aMsg, ev.content || ev.delta || '')
  }
}

// ── Block helpers ──
function appendThought(aMsg, content, streaming) {
  if (!content) return
  const blocks = aMsg._blocks
  const last = blocks[blocks.length - 1]
  if (streaming && last?.type === 'thought' && !last._archived) {
    last.content += content; last._streaming = true
  } else {
    blocks.forEach(b => { if (b.type === 'thought') { b._archived = true; b._collapsed = true; b._streaming = false } })
    blocks.push({ _uk: bId(), type: 'thought', content, _streaming: streaming, _archived: false })
    trimArchived(blocks)
  }
}

function appendAnswer(aMsg, content) {
  if (!content) return
  const blocks = aMsg._blocks
  blocks.forEach(b => { if (b.type === 'thought') { b._collapsed = true; b._streaming = false; b._archived = true } })
  const last = blocks[blocks.length - 1]
  if (last?.type === 'answer' && !last._archived) {
    last.content += content
  } else {
    blocks.forEach(b => { if (b.type === 'answer') { b._archived = true } })
    blocks.push({ _uk: bId(), type: 'answer', content, _archived: false })
  }
  aMsg.content = blocks.filter(b => b.type === 'answer' && !b._archived).map(b => b.content).join('\n\n')
}

function addAction(aMsg, toolName, callId, status, content, inputPreview) {
  const blocks = aMsg._blocks
  const lastT = [...blocks].reverse().find(b => b.type === 'thought')
  if (lastT) { lastT._collapsed = true; lastT._streaming = false }

  if (status === 'running') {
    const lastA = [...blocks].reverse().find(b => b.type === 'action' && !b._archived)
    if (lastA) {
      lastA.actions.push({ callId, toolName, status, content: '', argsPreview: inputPreview })
    } else {
      blocks.push({ _uk: bId(), type: 'action', _archived: false, actions: [{ callId, toolName, status, content: '', argsPreview: inputPreview }] })
      trimArchived(blocks)
    }
  } else {
    for (const b of blocks) {
      if (b.type !== 'action') continue
      const a = (b.actions||[]).find(x => x.callId === callId || (x.toolName === toolName && x.status === 'running'))
      if (a) { a.status = status; a.content = content; break }
    }
  }
}

function addBlock(aMsg, type, content) {
  aMsg._blocks.push({ _uk: bId(), type, content, _archived: false })
}

function archiveBlocks(aMsg) {
  aMsg._blocks.forEach(b => {
    if (b.type === 'thought' || b.type === 'action') { b._archived = true; b._collapsed = true; b._streaming = false }
  })
}

function trimArchived(blocks) {
  const maxVisible = 6
  const visible = blocks.filter(b => (b.type === 'thought' || b.type === 'action') && !b._archived)
  const excess = visible.length - maxVisible
  if (excess > 0) {
    for (let i = 0; i < excess; i++) { visible[i]._archived = true; visible[i]._collapsed = true; visible[i]._streaming = false }
  }
}

function finishMsg(aMsg) {
  aMsg._streaming = false
  archiveBlocks(aMsg)
  streaming.value = false; abortCtrl.value = null; readerRef.value = null
  if (aMsg._blocks.length === 0 && !aMsg.content) aMsg.content = '(无回复)'
  scroll()
}

function doCancel() {
  if (abortCtrl.value) abortCtrl.value.abort()
  streaming.value = false
}

async function respondPerm(approved) {
  const p = permissionAsk.value; if (!p) return
  permissionAsk.value = null
  await agentApi.respondPermission(p.askId, approved, p.sessionId).catch(()=>{})
}

async function onFileChange(e) {
  const file = e.target.files?.[0]; if (!file) return
  if (file.size > 50 * 1024 * 1024) { alert('文件不能超过 50MB'); return }
  await agentApi.uploadFile(sid.value, file).catch(e => alert('上传失败: ' + e.message))
  await refreshFiles()
  e.target.value = ''
}

async function refreshFiles() {
  try { const r = await agentApi.fetchSessionFiles(sid.value); files.value = r.files || r || [] } catch { files.value = [] }
}

function previewFile(f) { if (f.path) window.open(f.path, '_blank') }

function onModelChange() {
  agentApi.updateSessionConfig(sid.value, { model_key: config.model_key, enable_reasoning: config.enable_reasoning, enable_search: config.enable_search }).catch(()=>{})
}

function onKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); doSend() }
}

async function loadSessions() {
  try { const r = await agentApi.fetchSessions(); sessions.value = r.sessions || r || [] } catch { sessions.value = [] }
}

async function switchSess(newSid) {
  if (newSid === sid.value) return
  sid.value = newSid; localStorage.setItem('floodmind_sid', newSid)
  msgs.length = 0; todos.length = 0; workflow.value = null
  sessionTokens.prompt = sessionTokens.completion = sessionTokens.total = 0; files.value = []
  try {
    const data = await agentApi.fetchSessionMessages(newSid)
    if (data?.messages) {
      data.messages.forEach(m => {
        if (m.role === 'user') {
          msgs.push({ id: uid(), role: 'user', content: m.content || '' })
        } else if (m.role === 'assistant') {
          msgs.push(reactive({
            id: uid(), role: 'assistant', content: m.content || '',
            _blocks: [{ _uk: bId(), type: 'answer', content: m.content || '', _archived: false }],
            _streaming: false, _archivedCount: 0, _showArchived: false,
            refs: [], artifacts: [], tokenUsage: null
          }))
        }
      })
      scroll()
    }
  } catch { agentApi.initSession(newSid).catch(()=>{}) }
  await loadSessions()
}

async function newSession() {
  const newSid = uid()
  sid.value = newSid; localStorage.setItem('floodmind_sid', newSid)
  msgs.length = 0; todos.length = 0; workflow.value = null; files.value = []
  sessionTokens.prompt = sessionTokens.completion = sessionTokens.total = 0
  await agentApi.initSession(newSid).catch(()=>{})
  await loadSessions()
}

async function delSession(delSid) {
  await agentApi.deleteSession(delSid).catch(()=>{})
  if (delSid === sid.value) await newSession()
  else await loadSessions()
}

function onVisibility() {
  if (document.hidden) { wasStreaming.value = streaming.value }
  else if (wasStreaming.value && !streaming.value) {
    reconnecting.value = true; retryCount.value = 0
    const aMsg = lastA()
    if (aMsg) {
      agentApi.resumeStream(sid.value, retryCount.value).then(res => {
        reconnecting.value = false; streaming.value = true
        aMsg._streaming = true
        return readStream(res.body.getReader(), aMsg).then(() => finishMsg(aMsg))
      }).catch(() => { reconnecting.value = false; wasStreaming.value = false })
    } else { reconnecting.value = false; wasStreaming.value = false }
  }
}

onMounted(async () => {
  document.addEventListener('visibilitychange', onVisibility)
  await loadSessions()
  try {
    const m = await agentApi.fetchModels()
    models.value = (m||[]).map(x => ({ key: x.id||x.key, label: x.name||x.label||x.id }))
    if (models.value.length) config.model_key = models.value[0].key
  } catch { /* offline */ }
  try {
    const data = await agentApi.fetchSessionMessages(sid.value)
    if (data?.messages?.length) {
      data.messages.forEach(m => {
        if (m.role === 'user') {
          msgs.push({ id: uid(), role: 'user', content: m.content || '' })
        } else if (m.role === 'assistant') {
          msgs.push(reactive({
            id: uid(), role: 'assistant', content: m.content || '',
            _blocks: [{ _uk: bId(), type: 'answer', content: m.content || '', _archived: false }],
            _streaming: false, _archivedCount: 0, _showArchived: false,
            refs: [], artifacts: [], tokenUsage: null
          }))
        }
      })
      scroll()
    }
  } catch { /* no history */ }
})

onUnmounted(() => { document.removeEventListener('visibilitychange', onVisibility) })
</script>

<style scoped>
/* ── Layout ── */
.agent-page { min-height:0; height:100%; display:grid; grid-template-columns:1fr 240px; gap:var(--gap,10px); }
.agent-chat-panel { height:100%; min-height:0; display:block !important; overflow:hidden; border:1px solid var(--line); border-radius:var(--radius-xl); background:rgba(255,255,255,.64); box-shadow:var(--shadow-soft); }
.agent-chat-panel .chat-body { display:flex; flex-direction:column; height:100%; min-height:0; gap:8px; padding:14px 14px 6px; }
.agent-chat-panel .panel-head { display:none; }

/* ── Banners ── */
.perm-banner { display:flex; align-items:center; justify-content:space-between; gap:10px; padding:8px 14px; border:1px solid var(--amber); border-radius:12px; background:rgba(181,139,63,.08); font-size:12px; flex-shrink:0; }
.perm-btns { display:flex; gap:6px; flex-shrink:0; }
.recon-banner { display:flex; align-items:center; gap:8px; padding:8px 14px; border-radius:12px; background:rgba(109,146,159,.1); font-size:12px; color:var(--river); flex-shrink:0; }
.spin { display:inline-block; animation:spin 1s linear infinite; }

/* ── Messages area ── */
.chat-msgs { flex:1; min-height:0; max-height:none !important; overflow-y:auto; overflow-x:hidden; display:grid; align-content:start; gap:10px; padding:4px 4px 12px 0; }
.welcome-msg { text-align:center; padding:40px 20px; }
.welcome-icon { font-family:var(--serif); font-size:28px; font-weight:600; letter-spacing:-.04em; margin-bottom:16px; color:var(--ink); }
.welcome-msg b { display:block; font-size:16px; margin-bottom:8px; }
.welcome-msg p { margin:0; color:var(--muted); font-size:13px; line-height:1.7; }

.msg-user { justify-self:end; max-width:75%; background:#2d2923; color:#fff; border-radius:18px 18px 6px 18px; padding:10px 14px; font-size:13px; line-height:1.55; word-break:break-word; animation:msgIn .2s ease; }
.msg-ai { display:grid; gap:6px; max-width:100%; animation:msgIn .2s ease; }
.archived-hint { font-size:10px; color:var(--muted); cursor:pointer; padding:2px 0; }
.archived-hint:hover { color:var(--ink-2); }

@keyframes msgIn { from { opacity:0; transform:translateY(4px); } to { opacity:1; transform:none; } }

/* ── Chain-of-Thought wrapper ── */
.cot-wrap { border:1px solid var(--line); border-radius:12px; overflow:hidden; background:rgba(109,146,159,.025); }
.cot-wrap.streaming { border-color:var(--river-soft); box-shadow:0 0 0 1px rgba(109,146,159,.12); }
.cot-wrap.collapsed { border-color:var(--line); box-shadow:none; }

.cot-hd { display:flex; align-items:center; gap:8px; padding:8px 12px; cursor:pointer; user-select:none; font-size:12px; }
.cot-hd:hover { background:rgba(109,146,159,.05); }
.cot-arrow { font-size:8px; width:12px; color:var(--muted); flex-shrink:0; }
.cot-label { display:flex; align-items:center; gap:6px; font-weight:600; color:var(--river); }
.cot-meta { margin-left:auto; font-size:10px; color:var(--muted); font-weight:400; }

.cot-dot { width:7px; height:7px; border-radius:50%; background:var(--river); flex-shrink:0; }
.cot-dot.pulse { animation:cotPulse 1.5s ease-in-out infinite; }
@keyframes cotPulse { 0%,100%{ opacity:1; box-shadow:0 0 0 0 rgba(109,146,159,.4); } 50%{ opacity:.5; box-shadow:0 0 0 6px transparent; } }

.cot-body { padding:0 12px 10px; display:grid; gap:6px; }

/* ── Thought step ── */
.thought-step { display:grid; grid-template-columns:auto 1fr; gap:8px; align-items:start; }
.thought-dot-row { width:16px; display:flex; justify-content:center; padding-top:3px; }
.thought-dot-indicator { width:5px; height:5px; border-radius:50%; background:var(--river); opacity:.4; }
.thought-dot-indicator.live { opacity:1; animation:cotPulse 1.5s ease-in-out infinite; }
.thought-text { font-size:11px; color:var(--ink-2); line-height:1.55; white-space:pre-wrap; word-break:break-word; }
.thought-text.live { color:var(--ink); }

/* ── Tool card ── */
.tool-card { border:1px solid var(--line); border-radius:8px; overflow:hidden; cursor:pointer; background:rgba(255,255,255,.7); transition:all .15s; }
.tool-card:hover { border-color:rgba(37,33,28,.18); }
.tool-card.running { border-color:rgba(181,139,63,.25); background:rgba(181,139,63,.04); animation:toolPulse 2s ease-in-out infinite; }
.tool-card.error { border-color:rgba(169,79,67,.2); background:rgba(169,79,67,.03); }

@keyframes toolPulse { 0%,100%{ box-shadow:0 0 0 0 rgba(181,139,63,.1); } 50%{ box-shadow:0 0 0 3px transparent; } }

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
.tool-error { font-size:10px; color:var(--danger); line-height:1.5; }

/* ── Answer ── */
.answer-block { display:grid; gap:4px; }
.answer-text { font-size:13px; line-height:1.65; color:var(--ink); word-break:break-word; }
.answer-text :deep(h1) { font-size:18px; font-weight:700; margin:12px 0 6px; }
.answer-text :deep(h2) { font-size:16px; font-weight:700; margin:10px 0 6px; }
.answer-text :deep(h3) { font-size:14px; font-weight:600; margin:8px 0 4px; }
.answer-text :deep(ul),.answer-text :deep(ol) { margin:4px 0; padding-left:20px; }
.answer-text :deep(li) { margin:2px 0; }
.answer-text :deep(table) { border-collapse:collapse; width:100%; margin:8px 0; font-size:12px; }
.answer-text :deep(th),.answer-text :deep(td) { border:1px solid var(--line); padding:4px 8px; text-align:left; }
.answer-text :deep(th) { background:rgba(37,33,28,.04); font-weight:600; }
.answer-text :deep(pre) { margin:8px 0; padding:10px; border-radius:10px; background:rgba(37,33,28,.06); font-family:var(--mono); font-size:11px; overflow-x:auto; white-space:pre-wrap; }
.answer-text :deep(code) { font-family:var(--mono); font-size:11px; background:rgba(37,33,28,.08); border-radius:4px; padding:1px 5px; }
.answer-text :deep(b) { font-weight:700; }

/* ── Error ── */
.err-block { padding:8px 12px; border-radius:10px; background:rgba(169,79,67,.1); color:var(--danger); font-size:12px; }

/* ── Refs/Artifacts ── */
.refs-block { border-top:1px solid rgba(37,33,28,.08); padding-top:8px; }
.refs-title { font-size:11px; color:var(--muted); margin-bottom:4px; }
.ref-item { display:flex; align-items:center; gap:6px; font-size:11px; color:var(--river); text-decoration:none; padding:2px 0; }
.ref-item:hover { color:var(--river-soft); }
.ref-idx { display:inline-flex; align-items:center; justify-content:center; width:16px; height:16px; border-radius:50%; background:rgba(109,146,159,.15); font-size:9px; font-weight:700; }
.artifact-row { display:flex; gap:8px; }
.artifact-img-wrap { cursor:pointer; }
.artifact-label { font-size:11px; color:var(--muted); }
.artifact-img { max-width:200px; max-height:150px; border-radius:10px; border:1px solid rgba(37,33,28,.1); }
.artifact-file { font-size:11px; color:var(--river); display:flex; align-items:center; gap:8px; padding:6px 10px; border:1px solid rgba(37,33,28,.1); border-radius:10px; }
.artifact-file a { color:var(--river-soft); }

/* ── Token ── */
.token-line { font-size:9px; color:var(--muted); opacity:.5; margin-top:2px; }

/* ── Cursor ── */
.cursor { display:inline; color:var(--ink); animation:blink 1s step-end infinite; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }

/* ── Context ── */
.ctx-bar { display:flex; gap:6px; flex-wrap:wrap; padding:0 0 4px; }
.ctx-file { padding:3px 8px; border:1px solid var(--line); border-radius:999px; font-size:10px; color:var(--ink-2); cursor:pointer; background:rgba(255,255,255,.4); }
.ctx-file:hover { border-color:var(--river); }
.ctx-wf { padding:3px 8px; border-radius:999px; font-size:10px; color:var(--river); background:rgba(109,146,159,.08); }

/* ── Input panel (workspace row 3) ── */
.input-panel-wrap { min-height:0; display:grid; grid-template-columns:1fr 240px; gap:var(--gap,10px); }
.input-panel-main { padding:10px 16px; border:1px solid var(--line); border-radius:16px; background:rgba(255,255,255,.72); box-shadow:var(--shadow-soft); display:grid; gap:8px; }
.input-panel-side { /* matches sidebar width */ }

.input-row { display:flex; align-items:flex-end; gap:8px; }
.upload-btn { flex-shrink:0; min-height:36px; min-width:36px; padding:0; display:flex; align-items:center; justify-content:center; font-size:16px; }
.chat-input { flex:1; min-width:0; min-height:38px; max-height:140px; border:1px solid rgba(37,33,28,.12); border-radius:18px; background:rgba(255,255,255,.72); padding:8px 14px; outline:none; color:var(--ink); font-size:13px; resize:none; line-height:1.45; font-family:inherit; }
.chat-input:focus { border-color:var(--clay); }
.chat-input::placeholder { color:var(--muted); }
.send-btn { flex-shrink:0; min-height:36px; padding:0 18px; font-size:13px; }
.send-btn:disabled { opacity:.45; cursor:not-allowed; }
.toolbar { display:flex; align-items:center; gap:6px; flex-wrap:wrap; }
.tb-btn { padding:4px 10px; border:1px solid var(--line); border-radius:999px; background:rgba(255,255,255,.5); font-size:11px; cursor:pointer; color:var(--ink-2); transition:all .15s; }
.tb-btn:hover { border-color:var(--clay); }
.tb-btn.on { color:var(--river); border-color:var(--river); background:rgba(109,146,159,.08); }
.tb-select { max-width:140px; border:1px solid var(--line); border-radius:999px; background:rgba(255,255,255,.5); padding:4px 8px; font-size:11px; outline:none; color:var(--ink); cursor:pointer; }

/* ── Side panel ── */
.agent-side { min-height:0; height:100%; display:flex; flex-direction:column; gap:var(--gap,10px); overflow:hidden; }
.side-card { border:1px solid var(--line); border-radius:18px; background:rgba(255,255,255,.5); overflow:hidden; display:flex; flex-direction:column; }
.side-card:last-child { flex:1; min-height:0; }
.side-hd { padding:10px 12px; border-bottom:1px solid var(--line); font-size:12px; font-weight:600; display:flex; align-items:center; justify-content:space-between; }
.side-count { font-size:10px; color:var(--muted); font-weight:400; }
.side-body { padding:6px; flex:1; min-height:0; overflow-y:auto; }
.side-new { border:1px solid var(--line); border-radius:999px; padding:2px 8px; font-size:10px; background:transparent; cursor:pointer; color:var(--muted); }
.side-new:hover { background:rgba(37,33,28,.05); }
.todo-row { display:flex; align-items:flex-start; gap:6px; padding:5px 6px; border-radius:6px; font-size:11px; line-height:1.45; }
.todo-row:hover { background:rgba(37,33,28,.03); }
.todo-dot { flex-shrink:0; width:14px; text-align:center; font-size:11px; }
.todo-txt { color:var(--ink-2); flex:1; }
.todo-prio { padding:1px 5px; border-radius:4px; background:rgba(181,139,63,.12); color:var(--amber); font-size:9px; font-weight:700; }
.todo-completed .todo-dot { color:var(--ok); }
.todo-completed .todo-txt { color:var(--muted); text-decoration:line-through; }
.todo-in_progress .todo-dot { color:var(--amber); }
.tok-row { display:flex; justify-content:space-between; align-items:center; padding:5px 6px; font-size:11px; border-bottom:1px solid rgba(37,33,28,.04); }
.tok-row:last-child { border-bottom:0; }
.tok-row span { color:var(--muted); }
.tok-row b { font-family:var(--mono); font-size:12px; color:var(--ink-2); }
.sess-list { /* fills parent side-body */ }
.sess-row { display:grid; grid-template-columns:1fr auto auto; align-items:center; gap:6px; padding:7px 8px; border-radius:8px; cursor:pointer; font-size:11px; }
.sess-row:hover { background:rgba(37,33,28,.04); }
.sess-row.active { background:rgba(200,111,76,.08); }
.sess-row.active .sess-name { font-weight:600; color:var(--ink); }
.sess-name { color:var(--ink-2); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.sess-time { color:var(--muted); font-size:9px; white-space:nowrap; }
.sess-del { visibility:hidden; border:0; background:transparent; color:var(--muted); cursor:pointer; font-size:10px; padding:0 4px; }
.sess-row:hover .sess-del { visibility:visible; }
.sess-del:hover { color:var(--danger); }
.sess-empty { padding:12px; text-align:center; color:var(--muted); font-size:11px; }
.img-modal { position:fixed; inset:0; z-index:100; display:flex; align-items:center; justify-content:center; background:rgba(0,0,0,.8); backdrop-filter:blur(8px); padding:40px; }
.img-modal img { max-width:90vw; max-height:80vh; border-radius:12px; }
.img-close { position:absolute; top:20px; right:20px; }

/* ── Quick tasks ── */
.quick-tasks { margin-top: 20px; text-align: left; }
.qt-title { font-size: 11px; color: var(--muted); margin-bottom: 8px; font-weight: 600; }
.qt-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
.qt-card {
  display: flex; align-items: flex-start; gap: 8px;
  padding: 10px 12px; border: 1px solid var(--line); border-radius: 12px;
  background: rgba(255,255,255,.6); cursor: pointer; text-align: left;
  transition: all .15s; color: var(--ink); font-family: inherit;
}
.qt-card:hover { border-color: var(--river); background: rgba(109,146,159,.05); box-shadow: 0 2px 8px rgba(0,0,0,.04); }
.qt-card:disabled { opacity: .4; cursor: not-allowed; }
.qt-icon { font-size: 18px; flex-shrink: 0; line-height: 1.3; }
.qt-info { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.qt-label { font-size: 12px; font-weight: 600; white-space: nowrap; }
.qt-desc { font-size: 10px; color: var(--muted); line-height: 1.35; }

/* ── Quick task bar ── */
.quick-bar { display: flex; gap: 6px; flex-wrap: wrap; flex-shrink: 0; }
.qt-chip {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 10px; border: 1px solid var(--line); border-radius: 999px;
  background: rgba(255,255,255,.5); cursor: pointer;
  font-size: 11px; color: var(--ink-2); font-family: inherit;
  transition: all .15s; white-space: nowrap;
}
.qt-chip:hover { border-color: var(--river); color: var(--river); background: rgba(109,146,159,.05); }
.qt-chip:disabled { opacity: .4; cursor: not-allowed; }
.qt-chip-icon { font-size: 12px; }
</style>
