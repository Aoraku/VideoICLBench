/**
 * 会话列表 last_message 摘要（附录 D / 4.1 实现注意）
 * @param {{ type: string, content?: Record<string, unknown> } | null | undefined} lastMessage
 * @returns {string}
 */
export function lastMessagePreview(lastMessage) {
  if (!lastMessage) return ''
  const { type, content } = lastMessage
  const c = content && typeof content === 'object' ? content : {}

  switch (type) {
    case 'text':
      return typeof c.text === 'string' ? c.text : ''
    case 'image':
      return '[图片]'
    case 'video':
      return '[视频]'
    case 'audio':
      return '[语音]'
    case 'code':
      return '[代码]'
    case 'contact_card':
      return '[名片]'
    case 'forward':
      return '[聊天记录]'
    case 'file': {
      const name = typeof c.filename === 'string' ? c.filename : ''
      return name ? `[文件] ${name}` : '[文件]'
    }
    case 'system':
      return typeof c.text === 'string' ? c.text : '[系统消息]'
    default:
      return '[消息]'
  }
}
