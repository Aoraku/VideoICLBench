import { apiFetch } from './client.js'

export function listConversations({ page = 1, pageSize = 50 } = {}) {
  const q = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  return apiFetch(`/conversations/?${q}`)
}

/**
 * 4.3 获取会话详情（用于补全 peer_user 信息）。
 * @param {number|string} convId
 */
export function getConversationDetail(convId) {
  return apiFetch(`/conversations/${convId}`)
}

/**
 * 4.2 创建私聊会话；若已存在（409），回退返回已存在的 conversation_id。
 * @param {number|string} peerUserId
 */
export async function createPrivateConversation(peerUserId) {
  const id = Number(peerUserId)
  const payload = {
    type: 'private',
    peer_user_id: Number.isFinite(id) ? id : peerUserId,
  }
  try {
    return await apiFetch('/conversations/', { method: 'POST', json: payload })
  } catch (err) {
    if (err?.status === 409 && err?.body?.conversation_id) {
      return {
        conversation_id: err.body.conversation_id,
        existing: true,
      }
    }
    throw err
  }
}

/**
 * 4.7 搜索聊天记录（全局或指定会话）
 * @param {{ keyword: string, conversationId?: number|string, page?: number, pageSize?: number }} params
 */
export function searchConversationRecords({ keyword, conversationId, page = 1, pageSize = 20 }) {
  const q = new URLSearchParams({
    keyword: String(keyword || ''),
    page: String(page),
    page_size: String(pageSize),
  })
  if (conversationId != null && conversationId !== '') {
    q.set('conversation_id', String(conversationId))
  }
  return apiFetch(`/conversations/search?${q}`)
}

/**
 * 4.4 更新会话设置（置顶 / 免打扰）
 * @param {number|string} convId
 * @param {{ is_pinned?: boolean, is_muted?: boolean }} body
 */
export function updateConversationSettings(convId, body) {
  return apiFetch(`/conversations/${convId}`, { method: 'PUT', json: body })
}

/**
 * 4.5 删除会话（当前用户侧）
 * @param {number|string} convId
 */
export function deleteConversation(convId) {
  return apiFetch(`/conversations/${convId}`, { method: 'DELETE' })
}

/**
 * 4.6 标记会话已读
 * @param {number|string} convId
 * @param {number|string} lastReadMsgId
 */
export function markConversationRead(convId, lastReadMsgId) {
  return apiFetch(`/conversations/${convId}/read`, {
    method: 'PUT',
    json: { last_read_msg_id: lastReadMsgId },
  })
}
