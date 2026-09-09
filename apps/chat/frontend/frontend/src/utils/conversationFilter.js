import { conversationTitle } from './conversationDisplay.js'
import { lastMessagePreview } from './lastMessagePreview.js'

/**
 * 本地按标题与最后一条摘要筛选会话（不涉及后端搜索）。
 * @param {Record<string, unknown>} conv
 * @param {string} query
 * @param {string} [draftText]
 */
export function matchesConversationFilter(conv, query, draftText = '') {
  const q = String(query || '').trim().toLowerCase()
  if (!q) return true
  const title = conversationTitle(conv).toLowerCase()
  const preview = lastMessagePreview(conv.last_message).toLowerCase()
  const draft = String(draftText || '').toLowerCase()
  return title.includes(q) || draft.includes(q) || preview.includes(q)
}
