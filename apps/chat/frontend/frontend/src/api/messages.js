import { apiFetch } from './client.js'

/**
 * @param {number|string} conversationId
 * @param {{
 *   page?: number,
 *   pageSize?: number,
 *   before?: string|null,
 *   after?: string|null,
 *   senderId?: number|null,
 *   keyword?: string|null,
 *   type?: string|null,
 * }} [opts]
 */
export function listConversationMessages(conversationId, opts = {}) {
  const {
    page = 1,
    pageSize = 50,
    before = null,
    after = null,
    senderId = null,
    keyword = null,
    type = null,
  } = opts
  const q = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  if (before) q.set('before', before)
  if (after) q.set('after', after)
  if (senderId != null && senderId !== '') q.set('sender_id', String(senderId))
  if (keyword != null && String(keyword).trim()) q.set('keyword', String(keyword).trim())
  if (type != null && String(type).trim()) q.set('type', String(type).trim())
  return apiFetch(`/conversations/${conversationId}/messages?${q}`)
}

/**
 * DELETE /api/conversations/{conv_id}/messages/{msg_id} — 5.5 软删除（当前用户侧不可见）
 *
 * @param {number|string} conversationId
 * @param {number|string} msgId
 */
export function deleteMessage(conversationId, msgId) {
  return apiFetch(`/conversations/${conversationId}/messages/${msgId}`, { method: 'DELETE' })
}

/**
 * POST /api/conversations/{conv_id}/messages — 文本消息（见 API 文档 5.1）
 *
 * @param {number|string} conversationId
 * @param {string} text 纯文本正文（调用方应先 trim）
 * @param {{
 *   replyToMsgId?: number|null,
 *   clientMsgId?: string|null,
 *   mentions?: number[],
 * }} [opts]
 * - `clientMsgId`：可选 UUID 字符串，与后端幂等（网络重试时复用同一 id 可避免重复消息）
 */
export function sendTextMessage(conversationId, text, { replyToMsgId = null, clientMsgId = null, mentions = [] } = {}) {
  return sendMessage(conversationId, {
    type: 'text',
    content: { text },
    mentions,
    replyToMsgId,
    clientMsgId,
  })
}

export function sendMessage(conversationId, { type, content, replyToMsgId = null, clientMsgId = null, mentions = [] }) {
  /** @type {Record<string, unknown>} */
  const json = {
    type,
    content,
    mentions: Array.isArray(mentions) ? mentions : [],
  }
  if (replyToMsgId != null && Number.isFinite(Number(replyToMsgId))) {
    json.reply_to_msg_id = Number(replyToMsgId)
  }
  if (typeof clientMsgId === 'string' && clientMsgId.trim()) {
    json.client_msg_id = clientMsgId.trim()
  }
  return apiFetch(`/conversations/${conversationId}/messages`, {
    method: 'POST',
    json,
  })
}

export function recallMessage(conversationId, msgId) {
  return apiFetch(`/conversations/${conversationId}/messages/${msgId}/recall`, {
    method: 'POST',
    json: {},
  })
}

export function forwardMessages({ mode, sourceConvId, msgIds, targetConvIds }) {
  return apiFetch('/messages/forward', {
    method: 'POST',
    json: {
      mode,
      source_conv_id: Number(sourceConvId),
      msg_ids: msgIds.map((id) => Number(id)),
      target_conv_ids: targetConvIds.map((id) => Number(id)),
    },
  })
}

export function addReaction(conversationId, msgId, emoji) {
  return apiFetch(`/conversations/${conversationId}/messages/${msgId}/reactions`, {
    method: 'POST',
    json: { emoji },
  })
}

export function removeReaction(conversationId, msgId, emoji) {
  return apiFetch(`/conversations/${conversationId}/messages/${msgId}/reactions/${encodeURIComponent(emoji)}`, {
    method: 'DELETE',
  })
}

export function addBookmark({ conversationId = null, msgId = null, title = '', note = '' }) {
  const json = { note }
  if (conversationId != null && conversationId !== '') json.conversation_id = Number(conversationId)
  if (msgId != null && msgId !== '') json.msg_id = Number(msgId)
  if (title) json.title = title
  return apiFetch('/bookmarks', {
    method: 'POST',
    json,
  })
}

export function listBookmarks({ page = 1, pageSize = 20, archived = false } = {}) {
  const q = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  q.set('archived', archived ? 'true' : 'false')
  return apiFetch(`/bookmarks?${q}`)
}

export function updateBookmark(bookmarkId, body) {
  return apiFetch(`/bookmarks/${bookmarkId}`, {
    method: 'PUT',
    json: body,
  })
}

export function reorderBookmarks(bookmarkIds) {
  return apiFetch('/bookmarks/reorder', {
    method: 'POST',
    json: { bookmark_ids: bookmarkIds.map((id) => Number(id)) },
  })
}

export function deleteBookmark(bookmarkId) {
  return apiFetch(`/bookmarks/${bookmarkId}`, { method: 'DELETE' })
}

export function getReadStatus(conversationId, msgId) {
  return apiFetch(`/conversations/${conversationId}/messages/${msgId}/read-status`)
}
