/**
 * 将后端 _serialize_message 结果（扁平 sender 字段）规范为前端 MessageItem 使用的嵌套 sender。
 * 若已是嵌套 sender，原样返回。
 * @param {Record<string, unknown>|null|undefined} row
 * @returns {Record<string, unknown>|null|undefined}
 */
export function normalizeMessageFromApi(row) {
  if (!row || typeof row !== 'object') return row
  const o = /** @type {Record<string, unknown>} */ (row)
  if (o.sender && typeof o.sender === 'object' && typeof o.sender.user_id === 'number') {
    return o
  }
  const uid = o.sender_id
  const userId = typeof uid === 'number' ? uid : Number(uid)
  return {
    ...o,
    sender: {
      user_id: Number.isFinite(userId) ? userId : -1,
      username: typeof o.sender_name === 'string' ? o.sender_name : '',
      avatar: o.sender_avatar ?? null,
      group_nickname:
        o.group_nickname === '' || o.group_nickname == null ? null : String(o.group_nickname),
    },
  }
}

/**
 * @param {object} p
 * @param {string} p.clientMsgId
 * @param {string} p.text
 * @param {number} p.userId
 * @param {string} [p.username]
 * @param {string|null} [p.avatar]
 * @param {Record<string, unknown>|null} [p.replyTarget] 已规范化的消息行（含 reply_to 或 msg_id）
 */
export function buildOptimisticTextMessage(p) {
  const { clientMsgId, text, userId, username = '我', avatar = null, replyTarget } = p
  /** @type {Record<string, unknown>|null} */
  let reply_to = null
  if (replyTarget && typeof replyTarget === 'object') {
    const rt = replyTarget
    if (rt.reply_to && typeof rt.reply_to === 'object') {
      reply_to = { ...rt.reply_to }
    } else {
      const mid = rt.msg_id
      const sid = rt.sender?.user_id ?? rt.sender_id
      const text =
        typeof rt.content === 'object' && rt.content && typeof rt.content.text === 'string'
          ? rt.content.text
          : ''
      reply_to = {
        msg_id: typeof mid === 'number' ? mid : Number(mid),
        sender_id: typeof sid === 'number' ? sid : Number(sid) || 0,
        sender_name:
          (rt.sender && typeof rt.sender.username === 'string' && rt.sender.username) ||
          (typeof rt.sender_name === 'string' && rt.sender_name) ||
          '',
        type: typeof rt.type === 'string' ? rt.type : 'text',
        content_summary: text.slice(0, 120),
      }
    }
  }
  return {
    client_msg_id: clientMsgId,
    msg_id: null,
    sender: {
      user_id: userId,
      username,
      avatar,
      group_nickname: null,
    },
    type: 'text',
    content: { text },
    reply_to,
    is_recalled: false,
    created_at: new Date().toISOString(),
    send_status: 'pending',
    reactions: [],
    read_by_count: 0,
  }
}
