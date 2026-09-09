/**
 * 消息域 API（B 维护）
 * 路径与字段与 API 文档 5.1 / 5.2 一致。
 */
import { apiFetch } from './request.js'

/**
 * 5.2 获取聊天记录
 * @param {string|number} conversationId
 * @param {{
 *   page?: number,
 *   page_size?: number,
 *   before?: string,
 *   after?: string,
 *   sender_id?: number,
 *   keyword?: string,
 *   type?: string
 * }} [params]
 */
export function listConversationMessages(conversationId, params = {}) {
  const {
    page = 1,
    page_size = params.pageSize ?? 50,
    before,
    after,
    sender_id,
    keyword,
    type,
  } = params
  const q = new URLSearchParams({
    page: String(page),
    page_size: String(page_size),
  })
  if (before != null && before !== '') q.set('before', String(before))
  if (after != null && after !== '') q.set('after', String(after))
  if (sender_id != null) q.set('sender_id', String(sender_id))
  if (keyword != null && keyword !== '') q.set('keyword', String(keyword))
  if (type != null && type !== '') q.set('type', String(type))
  return apiFetch(`/conversations/${conversationId}/messages?${q}`)
}

/**
 * 5.1 发送消息
 * @param {string|number} conversationId
 * @param {{
 *   type: string,
 *   content: Record<string, unknown>,
 *   reply_to_msg_id?: number|null,
 *   mentions?: number[],
 * }} body
 */
export function postConversationMessage(conversationId, body) {
  return apiFetch(`/conversations/${conversationId}/messages`, {
    method: 'POST',
    json: {
      mentions: [],
      reply_to_msg_id: null,
      ...body,
    },
  })
}

/**
 * 5.5 删除消息
 * @param {string|number} conversationId
 * @param {string|number} msgId
 */
export function deleteConversationMessage(conversationId, msgId) {
  return apiFetch(`/conversations/${conversationId}/messages/${msgId}`, { method: 'DELETE' })
}

/**
 * 5.3 获取回复列表
 * @param {string|number} conversationId
 * @param {string|number} msgId
 * @param {{page?:number,page_size?:number,pageSize?:number}} [params]
 */
export function listMessageReplies(conversationId, msgId, params = {}) {
  const page = params.page ?? 1
  const pageSize = params.page_size ?? params.pageSize ?? 20
  const q = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  return apiFetch(`/conversations/${conversationId}/messages/${msgId}/replies?${q}`)
}
