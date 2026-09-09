import { resolveAvatarSrc } from '../../utils/avatarUrl.js'
import { summarizeMessageContent } from '../../utils/messageContent.js'

/**
 * 单条消息气泡 — 字段与 API 5.2 / 5.1 响应一致（snake_case）。
 *
 * @param {Object} props
 * @param {import('../../types/chat.js').ApiChatMessage} props.message
 * @param {boolean} props.isSelf
 * @param {() => void} [props.onReplyClick]
 * @param {() => void} [props.onDeleteClick]
 * @param {() => void} [props.onJumpToReplied]
 * @param {(e: MouseEvent) => void} [props.onContextMenu]
 * @param {() => void} [props.onRetry]
 */
export default function MessageItem({
  message,
  isSelf,
  onReplyClick,
  onDeleteClick,
  onJumpToReplied,
  onContextMenu,
  onRetry,
}) {
  const sender = message.sender || {}
  const displayName =
    (typeof sender.group_nickname === 'string' && sender.group_nickname) ||
    (typeof sender.username === 'string' && sender.username) ||
    ''
  const avatarSrc = resolveAvatarSrc(sender.avatar)
  const side = isSelf ? 'right' : 'left'
  const rowClass = side === 'right' ? 'bubbleRow bubbleRow--right' : 'bubbleRow'
  const bubbleClass = side === 'right' ? 'bubble bubble--right' : 'bubble bubble--left'

  const replyTo = message.reply_to
  const recalled = Boolean(message.is_recalled)

  const formatTime = (iso) => {
    if (!iso) return ''
    try {
      const d = new Date(iso)
      if (Number.isNaN(d.getTime())) return String(iso)
      return d.toLocaleString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        month: 'numeric',
        day: 'numeric',
      })
    } catch {
      return String(iso)
    }
  }

  const renderBody = () => {
    if (recalled) {
      const who =
        isSelf ? '你' : typeof sender.username === 'string' && sender.username ? sender.username : '对方'
      return <span className="messageRecalled">{who} 撤回了一条消息</span>
    }
    const type = typeof message.type === 'string' ? message.type : 'text'
    const content = message.content && typeof message.content === 'object' ? message.content : {}

  if (type === 'group_announcement') {
    const ann = typeof content.content === 'string' ? content.content : typeof content.text === 'string' ? content.text : ''
    return ann ? `[群公告] ${ann}` : '[群公告]'
  }
  if (type === 'announcement') {
    const ann = typeof content.content === 'string' ? content.content : typeof content.text === 'string' ? content.text : ''
    return ann ? `[群公告] ${ann}` : '[群公告]'
  }
  if (type === 'text') {
      const t = typeof content.text === 'string' ? content.text : ''
      return t || ' '
    }
    if (type === 'code') {
      const lang = typeof content.language === 'string' ? content.language : ''
      const code = typeof content.code === 'string' ? content.code : ''
      return (
        <pre className="messageCodeBlock">
          {lang ? `// ${lang}\n` : null}
          {code || ' '}
        </pre>
      )
    }
    if (type === 'image' && typeof content.url === 'string' && content.url) {
      return (
        <img
          className="messageImageThumb"
          src={content.url}
          alt=""
          width={content.width ? Number(content.width) : undefined}
          height={content.height ? Number(content.height) : undefined}
        />
      )
    }
    return summarizeMessageContent(type, content)
  }

  const avatarEl =
    avatarSrc ? (
      <img className="list__avatar messageAvatarImg" src={avatarSrc} alt="" width={44} height={44} />
    ) : (
      <div className="list__avatar messageAvatarImg" aria-hidden />
    )

  const msgId =
    typeof message.msg_id === 'number' ? message.msg_id : message.msg_id != null ? Number(message.msg_id) : null

  return (
    <div
      className={rowClass}
      data-msg-id={msgId ?? ''}
      onContextMenu={(e) => {
        if (!onContextMenu) return
        e.preventDefault()
        onContextMenu(e)
      }}
    >
      {!isSelf ? <div className="msgAvatarCol">{avatarEl}</div> : null}
      <div className={bubbleClass}>
        {!isSelf && displayName ? <div className="bubble__name">{displayName}</div> : null}
        {replyTo && !recalled ? (
          <button type="button" className="replyCard replyCard--clickable" onClick={onJumpToReplied}>
            <div className="replyCard__title">
              {typeof replyTo.sender_name === 'string' ? replyTo.sender_name : '消息'}
            </div>
            <div className="replyCard__sub">
              {typeof replyTo.content_summary === 'string' && replyTo.content_summary
                ? replyTo.content_summary
                : summarizeMessageContent(
                    typeof replyTo.type === 'string' ? replyTo.type : 'text',
                    undefined,
                  )}
            </div>
          </button>
        ) : null}
        {renderBody()}
        {!recalled ? (
          <div className="messageInlineActions">
            {onReplyClick ? (
              <button type="button" className="msgInlineBtn" onClick={onReplyClick}>
                回复
              </button>
            ) : null}
            {onDeleteClick ? (
              <button type="button" className="msgInlineBtn msgInlineBtn--danger" onClick={onDeleteClick}>
                删除
              </button>
            ) : null}
          </div>
        ) : null}
        {typeof message.reply_count === 'number' && message.reply_count > 0 ? (
          <button type="button" className="msgReplyCount" onClick={onReplyClick}>
            {message.reply_count} 条回复
          </button>
        ) : null}
        <div className="bubble__time">{formatTime(message.created_at)}</div>
        {message.send_status === 'pending' ? <div className="bubble__time">发送中…</div> : null}
        {message.send_status === 'failed' ? (
          <div className="bubble__time">
            发送失败
            {onRetry ? (
              <button type="button" className="msgRetryBtn" onClick={onRetry}>
                重试
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
      {isSelf ? <div className="msgAvatarCol">{avatarEl}</div> : null}
    </div>
  )
}
