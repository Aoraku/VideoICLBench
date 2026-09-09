import { resolveAvatarSrc } from './avatarUrl.js'

/**
 * @param {Record<string, unknown>} conv
 * @returns {string}
 */
export function conversationTitle(conv) {
  if (!conv) return ''
  const peer = conv.peer_user
  if (peer && typeof peer === 'object') {
    const remark = peer.remark && String(peer.remark).trim()
    if (remark) return remark
    if (typeof peer.username === 'string' && peer.username.trim()) return peer.username
  }
  if (conv.type === 'group' && conv.name && String(conv.name).trim()) return String(conv.name)
  return conv.type === 'group' ? '群聊' : '私聊'
}

/**
 * @param {Record<string, unknown>} conv
 * @returns {string}
 */
export function conversationAvatarSrc(conv) {
  if (!conv) return ''
  if (conv.type === 'private' && conv.peer_user && typeof conv.peer_user === 'object') {
    return resolveAvatarSrc(conv.peer_user.avatar)
  }
  return resolveAvatarSrc(conv.avatar)
}

/**
 * @param {string | undefined} iso
 * @returns {string}
 */
export function formatConversationTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const now = new Date()
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  if (sameDay) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}
