// 预警/告警级别标签的统一归一化。
// 后端 level 字段的可能取值：
//   实测预警：蓝色预警 / 黄色预警 / 橙色预警 / 红色预警
//   预报警报：预报蓝色预警 / 预报黄色预警 / 预报橙色预警 / 预报红色预警
//   系统告警：提示 / 黄色 / 红色 / 橙色（裸色名）
//   正常：正常

// 显示文本：实测/预报保留「X色预警」；系统裸色名补「告警」；提示/正常/数据异常原样。
export function levelLabel(level) {
  const s = String(level ?? '').trim()
  if (!s) return '—'
  if (s.endsWith('预警')) return s
  if (s === '提示' || s === '正常' || s === '数据异常') return s
  if (['红色', '橙色', '黄色', '蓝色'].includes(s)) return s + '告警'
  return s
}

// 徽章颜色类：按颜色统一（红→danger / 橙·黄→warn / 蓝→ok）；
// 提示=轻微异常→info(中性灰)；正常=全系统健康→ok(绿色，绿色仅此一项)；
// 数据异常=数据质量存疑→anomaly(紫，区别于洪水四色)。
export function levelBadgeClass(level) {
  const s = String(level ?? '')
  if (s === '数据异常') return 'anomaly'
  if (s === '提示') return 'info'
  if (s === '正常') return 'ok'
  if (s.includes('红')) return 'danger'
  if (s.includes('橙')) return 'warn'
  if (s.includes('黄')) return 'warn'
  if (s.includes('蓝')) return 'ok'
  return ''
}

// 排序权重：越严重越小；同色预报略晚于实测（实测更紧急）。
// 数据异常=3.5，排在洪水四色（0~3）之后、提示（4）之前——可见但不压过真实险情。
export function levelSeverity(level) {
  const s = String(level ?? '')
  let base
  if (s.includes('红')) base = 0
  else if (s.includes('橙')) base = 1
  else if (s.includes('黄')) base = 2
  else if (s.includes('蓝')) base = 3
  else if (s === '数据异常') return 3.5
  else if (s === '提示') return 4
  else if (s === '正常') return 5
  else return 6
  return base + (s.startsWith('预报') ? 0.5 : 0)
}
