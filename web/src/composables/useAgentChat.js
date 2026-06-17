import { ref, reactive, computed, nextTick } from 'vue'
import { agentApi } from '../api/agent.js'

let _idCounter = 0

function uid() {
  try { return crypto.randomUUID() } catch { _idCounter++; return `${Date.now()}-${_idCounter}-${Math.random().toString(36).slice(2, 9)}` }
}

/**
 * @param {string} sessionId - The chat session identifier
 * @param {object} [options]
 * @param {string} [options.assistantId] - Optional assistant identifier
 */
export function useAgentChat(sessionId, options = {}) {
  const { assistantId = '' } = options

  // ── Reactive state ──────────────────────────────────────────────
  const messages = reactive([])
  const isStreaming = ref(false)
  const inputValue = ref('')
  const pendingPermission = ref(null)
  const abortController = ref(null)

  // Auto-scroll ref (assign in template: <div ref="scrollRef">)
  const scrollRef = ref(null)

  // ── Helpers ─────────────────────────────────────────────────────
  function scrollToBottom() {
    nextTick(() => {
      const el = scrollRef.value
      if (el) {
        el.scrollTop = el.scrollHeight
      }
    })
  }

  /** Find the last assistant message (the streaming placeholder). */
  function lastAssistant() {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'assistant') return messages[i]
    }
    return null
  }

  // ── send() ──────────────────────────────────────────────────────
  async function send() {
    const content = inputValue.value.trim()
    if (!content || isStreaming.value) return
    inputValue.value = ''

    // User message
    const userMsg = reactive({
      id: uid(),
      role: 'user',
      content,
      blocks: [{ type: 'answer', content }]
    })
    messages.push(userMsg)

    // Assistant placeholder
    const assistantMsg = reactive({
      id: uid(),
      role: 'assistant',
      content: '',
      isComplete: false,
      blocks: [],
      thoughts: [],
      actions: [],
      artifacts: [],
      todos: [],
      workflow: null,
      tokenUsage: null,
      error: null
    })
    messages.push(assistantMsg)

    isStreaming.value = true
    scrollToBottom()

    const ctrl = new AbortController()
    abortController.value = ctrl

    try {
      const response = await agentApi.createChatRequest(
        sessionId,
        content,
        [],                   // uploadedFiles
        assistantId           // assistantMessageId
      )

      if (!response.body) {
        throw new Error('Stream response has no body')
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // Split on newlines; keep any trailing incomplete chunk
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const raw of lines) {
          const line = raw.trim()
          if (!line) continue
          try {
            const event = JSON.parse(line)
            handleStreamEvent(event, assistantMsg)
          } catch {
            // Skip unparseable lines silently
          }
        }
        scrollToBottom()
      }

      // Process any remaining buffer
      if (buffer.trim()) {
        try {
          const event = JSON.parse(buffer.trim())
          handleStreamEvent(event, assistantMsg)
        } catch { /* ignore */ }
      }

      // Mark complete
      assistantMsg.isComplete = true
      collapseThoughts(assistantMsg)
    } catch (err) {
      if (err.name === 'AbortError') {
        assistantMsg.content += '\n[已取消]'
      } else {
        assistantMsg.error = err.message || 'Unknown error'
        assistantMsg.content += `\n[错误: ${assistantMsg.error}]`
      }
      assistantMsg.isComplete = true
    } finally {
      isStreaming.value = false
      abortController.value = null
      scrollToBottom()
    }
  }

  /** Cancel the active stream. */
  function cancel() {
    if (abortController.value) {
      abortController.value.abort()
      abortController.value = null
    }
  }

  // ── Stream event handler ────────────────────────────────────────
  function handleStreamEvent(event, msg) {
    const type = event.type || event.event || ''
    const data = event.data !== undefined ? event.data : event

    switch (type) {
      // ── Reasoning / thoughts ──
      case 'thought_delta':
      case 'reasoning': {
        const text = typeof data === 'string' ? data : (data.delta || data.text || '')
        if (text) {
          if (!msg._streamingThought) {
            msg._streamingThought = { type: 'thought', content: '', isStreaming: true }
            msg.thoughts.push(msg._streamingThought)
          }
          msg._streamingThought.content += text
        }
        break
      }

      case 'thought_summary': {
        const summary = typeof data === 'string' ? data : (data.summary || data.text || '')
        if (msg._streamingThought) {
          msg._streamingThought.isStreaming = false
          msg._streamingThought = null
        }
        if (summary) {
          msg.thoughts.push({ type: 'thought', content: summary, isStreaming: false })
        }
        break
      }

      // ── Answer / token streaming ──
      case 'answer_delta':
      case 'token': {
        const token = typeof data === 'string' ? data : (data.delta || data.token || data.text || '')
        if (token) {
          msg.content += token
        }
        break
      }

      // ── Tool / action ──
      case 'action_start':
      case 'tool_status': {
        const name = data.tool || data.name || data.action || 'tool'
        const input = data.input || data.args || null
        const action = reactive({
          id: uid(),
          name,
          input,
          status: 'running',
          output: null
        })
        msg.actions.push(action)
        msg._currentAction = action
        break
      }

      case 'action_end':
      case 'tool_result': {
        const output = data.output || data.result || data
        if (msg._currentAction) {
          msg._currentAction.status = 'done'
          msg._currentAction.output = output
          msg._currentAction = null
        } else if (msg.actions.length > 0) {
          // resolve the last running action
          for (let i = msg.actions.length - 1; i >= 0; i--) {
            if (msg.actions[i].status === 'running') {
              msg.actions[i].status = 'done'
              msg.actions[i].output = output
              break
            }
          }
        }
        break
      }

      // ── Error ──
      case 'error':
      case 'llm_token_error': {
        const errText = typeof data === 'string' ? data : (data.message || data.error || JSON.stringify(data))
        msg.error = errText
        msg.blocks.push({ type: 'error', content: errText })
        break
      }

      // ── Final ──
      case 'final': {
        const finalContent = typeof data === 'string' ? data : (data.content || data.text || '')
        if (finalContent) {
          msg.content = finalContent
        }
        msg.isComplete = true
        break
      }

      // ── Stream end ──
      case 'stream_end': {
        msg.isComplete = true
        collapseThoughts(msg)
        break
      }

      // ── Todos ──
      case 'todo_updated': {
        const todos = Array.isArray(data) ? data : (data.todos || [])
        msg.todos = todos
        break
      }

      // ── Workflow plan ──
      case 'workflow_plan': {
        msg.workflow = typeof data === 'object' ? data : { plan: data }
        break
      }

      // ── Token usage ──
      case 'token_usage': {
        msg.tokenUsage = {
          prompt: data.prompt_tokens || data.prompt || 0,
          completion: data.completion_tokens || data.completion || 0,
          total: data.total_tokens || data.total || 0
        }
        break
      }

      // ── Permission ask ──
      case 'permission_ask': {
        pendingPermission.value = {
          askId: data.ask_id || data.id || uid(),
          message: data.message || data.text || '需要您的确认以继续操作。',
          details: data.details || null,
          sessionId
        }
        break
      }

      // ── Artifacts ──
      case 'file_generated':
      case 'image_generated': {
        const artifact = {
          id: uid(),
          type: type === 'image_generated' ? 'image' : 'file',
          name: data.name || data.filename || 'artifact',
          url: data.url || data.path || '',
          mime: data.mime || data.type || null
        }
        msg.artifacts.push(artifact)
        break
      }

      // ── Catch-all for unknown types ──
      default: {
        // Silently ignore unrecognized events; could log in dev:
        // console.debug('[useAgentChat] unhandled event type:', type, data)
        break
      }
    }
  }

  /** Finalize streamed thought text. */
  function collapseThoughts(msg) {
    if (msg._streamingThought) {
      msg._streamingThought.isStreaming = false
      msg._streamingThought = null
    }
  }

  // ── respondPermission ───────────────────────────────────────────
  async function respondPermission(approved) {
    const perm = pendingPermission.value
    if (!perm) return

    const askId = perm.askId
    pendingPermission.value = null

    try {
      await agentApi.respondPermission(askId, approved, sessionId)
      // Optionally push a system message noting the decision
      messages.push({
        id: uid(),
        role: 'system',
        content: approved ? '已批准操作。' : '已拒绝操作。',
        blocks: [{ type: 'system', content: approved ? '已批准操作。' : '已拒绝操作。' }]
      })
      scrollToBottom()
      return true
    } catch (err) {
      console.error('respondPermission failed:', err)
      messages.push({
        id: uid(),
        role: 'system',
        content: `权限响应失败: ${err.message}`,
        blocks: [{ type: 'error', content: `权限响应失败: ${err.message}` }]
      })
      scrollToBottom()
      return false
    }
  }

  // ── Clear / reset ───────────────────────────────────────────────
  function clearMessages() {
    messages.length = 0
    isStreaming.value = false
    inputValue.value = ''
    pendingPermission.value = null
    if (abortController.value) {
      abortController.value.abort()
      abortController.value = null
    }
  }

  // ── Computed ────────────────────────────────────────────────────
  const lastMessage = computed(() => {
    return messages.length > 0 ? messages[messages.length - 1] : null
  })

  const hasPendingPermission = computed(() => {
    return pendingPermission.value !== null
  })

  // ── Return ──────────────────────────────────────────────────────
  return {
    // State
    messages,
    isStreaming,
    inputValue,
    pendingPermission,
    scrollRef,

    // Computed
    lastMessage,
    hasPendingPermission,

    // Methods
    send,
    cancel,
    respondPermission,
    clearMessages,
    scrollToBottom
  }
}
