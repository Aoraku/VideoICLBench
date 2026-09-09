/**
 * 兼容 REST / WS 多种公告正文字段
 * @param {Record<string, unknown>} c
 */
function announcementPlainBody(c) {
  if (!c || typeof c !== 'object') return ''
  if (typeof c.content === 'string' && c.content.trim()) return c.content.trim()
  if (typeof c.text === 'string' && c.text.trim()) return c.text.trim()
  if (typeof c.body === 'string' && c.body.trim()) return c.body.trim()
  const d = c.data
  if (d && typeof d === 'object' && typeof d.content === 'string' && d.content.trim()) return d.content.trim()
  return ''
}

/** 后端仅返回 action、无 text 时的居中提示文案 */
function systemActionFallbackText(action) {
  const map = {
    member_joined: '新成员加入了群聊',
    member_left: '成员已退出群聊',
    member_removed: '成员已被移出群聊',
    member_invited: '成员被邀请加入群聊',
    admin_promoted: '管理员设置已更新',
    admin_demoted: '管理员设置已更新',
    owner_transferred: '群主已转让',
    group_renamed: '群名称已更新',
    group_avatar_updated: '群头像已更新',
  }
  if (map[action]) return map[action]
  if (action.startsWith('admin_')) return '管理员设置已更新'
  if (action.startsWith('member_')) return '群成员有变动'
  return ''
}

/**
 * @param {Record<string, unknown>|null|undefined} content
 * @param {string} [type]
 */
export function getMessagePlainText(content, type = 'text') {
  if (!content || typeof content !== 'object') return ''
  const c = /** @type {Record<string, unknown>} */ (content)
  if (type === 'text' && typeof c.text === 'string') return c.text
  if (type === 'code' && typeof c.code === 'string') return c.code
  if (type === 'calendar_invite') {
    const title = typeof c.title === 'string' && c.title.trim() ? c.title.trim() : '日程邀请'
    const desc = typeof c.description === 'string' && c.description.trim() ? ` ${c.description.trim()}` : ''
    return `[日程] ${title}${desc}`
  }
  if (type === 'system') {
    const ann = announcementPlainBody(c)
    const action = typeof c.action === 'string' ? c.action : ''
    if (ann && (action.includes('announce') || action === 'group_announcement')) {
      return ann.startsWith('[群公告]') ? ann : `[群公告] ${ann}`
    }
    if (typeof c.text === 'string' && c.text) return c.text
    if (action) return systemActionFallbackText(action)
    return ''
  }
  if (type === 'group_announcement' || type === 'announcement') {
    const ann = announcementPlainBody(c)
    return ann ? `[群公告] ${ann}` : '[群公告]'
  }
  return ''
}
