import { conversationAvatarSrc, conversationTitle, formatConversationTime } from '../../utils/conversationDisplay.js'
import { lastMessagePreview } from '../../utils/lastMessagePreview.js'

export default function ConversationItem({
  conversation,
  draftText = '',
  busy = false,
  active,
  onSelect,
  onOpenMenu,
}) {
  const title = conversationTitle(conversation)
  const avatar = conversationAvatarSrc(conversation)
  const last = conversation.last_message
  const preview = lastMessagePreview(last)
  const hasDraft = Boolean(String(draftText).trim())
  const time = formatConversationTime(last?.created_at || conversation.updated_at)
  const unread = Number(conversation.unread_count) || 0
  const muted = Boolean(conversation.is_muted)
  const pinned = Boolean(conversation.is_pinned)

  return (
    <div
      className={[
        'list__item',
        active ? 'is-active' : '',
        muted ? 'list__item--muted' : '',
        busy ? 'is-busy' : '',
      ]
        .filter(Boolean)
        .join(' ')}
      role="button"
      tabIndex={0}
      onClick={() => {
        if (busy) return
        onSelect(conversation.conversation_id, conversation.last_message?.msg_id)
      }}
      onKeyDown={(e) => {
        if (busy) return
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelect(conversation.conversation_id, conversation.last_message?.msg_id)
        }
      }}
      onContextMenu={(e) => {
        if (busy) return
        e.preventDefault()
        onOpenMenu(e, conversation)
      }}
    >
      <div className="list__avatar">
        {avatar ? (
          <img src={avatar} alt="" className="list__avatarImg" />
        ) : (
          <svg viewBox="0 0 24 24" className="list__avatarDefaultIcon" aria-hidden>
            <circle cx="12" cy="8" r="4" />
            <path d="M4 20c0-4 3.6-6 8-6s8 2 8 6" />
          </svg>
        )}
      </div>
      <div className="list__meta">
        <div className="list__titleRow">
          <div className="list__title">
            {pinned ? <span className="list__pinMark" title="置顶">📌 </span> : null}
            {muted ? <span className="list__muteMark" title="免打扰">🔕 </span> : null}
            {title}
          </div>
          {time ? <div className="list__time">{time}</div> : null}
        </div>
        <div className={hasDraft ? 'list__sub list__sub--draft' : 'list__sub'}>
          {hasDraft ? `[草稿] ${draftText}` : (preview || '暂无消息')}
        </div>
      </div>
      {unread > 0 ? (
        <div className={muted ? 'list__badge list__badge--muted' : 'list__badge'}>
          {unread > 99 ? '99+' : unread}
        </div>
      ) : (
        <span className="list__badgeSpacer" aria-hidden />
      )}
    </div>
  )
}
