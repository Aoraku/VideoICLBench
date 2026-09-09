/**
 * 附录：会话草稿存储 key 为 draft:{conversation_id}
 * 对外只暴露读取能力，写入由消息输入模块负责。
 */

function keyOf(conversationId) {
  return `draft:${conversationId}`
}

/**
 * @param {number|string} conversationId
 * @returns {string}
 */
export function getConversationDraft(conversationId) {
  if (conversationId == null) return ''
  try {
    const raw = localStorage.getItem(keyOf(conversationId))
    return typeof raw === 'string' ? raw.trim() : ''
  } catch {
    return ''
  }
}
