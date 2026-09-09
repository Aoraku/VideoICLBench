import { getMessagePlainText } from './messageText.js'

/**
 * 与 API 文档「附录 D：消息类型的会话列表摘要映射」及 5.2 消息体展示对齐。
 * @param {string} type
 * @param {Record<string, unknown> | null | undefined} content
 * @returns {string}
 */
export function summarizeMessageContent(type, content) {
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
    case 'file':
      return typeof c.filename === 'string' ? `[文件] ${c.filename}` : '[文件]'
    case 'code':
      return '[代码]'
    case 'contact_card':
      return typeof c.username === 'string' ? `[名片] ${c.username}` : '[名片]'
    case 'calendar_invite':
      return typeof c.title === 'string' ? `[日程] ${c.title}` : '[日程邀请]'
    case 'forward':
      return '[聊天记录]'
    case 'system': {
      const viaPlain = getMessagePlainText(c, 'system')
      if (viaPlain) return viaPlain
      return typeof c.text === 'string' ? c.text : typeof c.action === 'string' ? `[系统] ${c.action}` : '[系统消息]'
    }
    case 'group_announcement':
    case 'announcement':
      return getMessagePlainText(c, type) || '[群公告]'
    default: {
      const viaPlain = getMessagePlainText(c, type)
      return viaPlain || '[消息]'
    }
  }
}
