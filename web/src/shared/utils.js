// ── 共享工具函数（AgentPage / AgentChatPanel / VoiceAssistant 统一引用）──

/**
 * 生成唯一 ID（优先使用 crypto.randomUUID，回退到时间戳+随机数）。
 */
export function uid() {
  try { return crypto.randomUUID() } catch {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 10)
  }
}

/**
 * 在消息前追加当前系统时间前缀。
 */
export function withTime(text) {
  const n = new Date()
  const p = x => String(x).padStart(2, '0')
  return `[当前系统时间: ${n.getFullYear()}-${p(n.getMonth() + 1)}-${p(n.getDate())} ${p(n.getHours())}:${p(n.getMinutes())}]\n\n${text}`
}

/**
 * 数字格式化：>1M 显示为 X.XM，>1K 显示为 X.XK，否则原样。
 */
export function fmtNum(n) {
  if (!n) return '0'
  return n >= 1e6 ? (n / 1e6).toFixed(1) + 'M'
    : n >= 1e3 ? (n / 1e3).toFixed(1) + 'K'
    : String(n)
}

/**
 * 字符串截断，超过 N 字符追加 "..."。
 */
export function truncate(s, n) {
  const t = String(s || '')
  return t.length > n ? t.slice(0, n) + '...' : t
}
