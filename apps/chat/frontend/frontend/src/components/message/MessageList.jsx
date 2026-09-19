import {command, nativeRun, currentBusiness} from '../../benchmark/bridge.js'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { resolveAvatarSrc } from '../../utils/avatarUrl.js'
import { CHAT_EVENT_JUMP_TO_MESSAGE } from '../../constants/chatEvents.js'
import { summarizeMessageContent } from '../../utils/messageContent.js'
import { getMessagePlainText } from '../../utils/messageText.js'
import PopMenu from '../ui/PopMenu.jsx'
import FilePreviewModal from './FilePreviewModal.jsx'
import RichMarkdown, { CodeBlock } from './RichMarkdown.jsx'

function contentUrl(content) {
  return String(content?.url || content?.file_url || content?.download_url || content?.src || '')
}

function formatMsgTime(iso) {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', {
      month: 'numeric',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
}

function senderLabel(sender) {
  if (!sender || typeof sender !== 'object') return '未知'
  return sender.group_nickname || sender.username || '用户'
}

/** 系统消息：居中展示；发送中/失败仍走气泡以便重试 */
/** @param {Record<string, unknown>} row */
function isSystemNoticeLayout(row) {
  if (!row || typeof row !== 'object') return false
  if (row.type !== 'system') return false
  const st = row.send_status
  if (st === 'pending' || st === 'failed') return false
  return true
}

function MessageAvatar({ avatarUrl }) {
  const [brokenAvatarUrl, setBrokenAvatarUrl] = useState(null)
  const broken = avatarUrl && brokenAvatarUrl === avatarUrl
  return (
    <div className="msgAvatar" aria-hidden>
      {avatarUrl && !broken ? (
        <img
          className="msgAvatar__img"
          src={avatarUrl}
          alt=""
          onError={() => setBrokenAvatarUrl(avatarUrl)}
        />
      ) : (
        <div className="msgAvatar__default">
          <svg viewBox="0 0 24 24" className="msgAvatar__defaultIcon" aria-hidden="true">
            <circle cx="12" cy="8" r="4" />
            <path d="M4 20c0-4 3.6-6 8-6s8 2 8 6" />
          </svg>
        </div>
      )}
    </div>
  )
}

/** @param {unknown} row */
function canReplyToRow(row) {
  if (!row || typeof row !== 'object') return false
  const mid = /** @type {Record<string, unknown>} */ (row).msg_id
  if (mid == null) return false
  const n = typeof mid === 'number' ? mid : Number(mid)
  return Number.isFinite(n) && n > 0
}

/** DOM 锚点 id（用于跳转到指定消息） */
/** @param {Record<string, unknown>} row */
function messageAnchorId(row) {
  const mid = row.msg_id
  if (mid != null) {
    const n = typeof mid === 'number' ? mid : Number(mid)
    if (Number.isFinite(n) && n > 0) return `msg-${n}`
  }
  const cid = row.client_msg_id
  if (typeof cid === 'string' && cid.trim()) {
    const safe = cid.trim().replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 72)
    return safe ? `msg-client-${safe}` : undefined
  }
  return undefined
}

/** 回复引用指向的原消息 id（服务端） */
/** @param {Record<string, unknown>|null|undefined} replyTo */
/** @param {unknown} row */
function canDeleteRow(row) {
  if (!row || typeof row !== 'object') return false
  const mid = /** @type {Record<string, unknown>} */ (row).msg_id
  if (mid == null) return false
  const n = typeof mid === 'number' ? mid : Number(mid)
  return Number.isFinite(n) && n > 0
}

function replyReferencedServerMsgId(replyTo) {
  if (!replyTo || typeof replyTo !== 'object') return null
  const raw =
    /** @type {Record<string, unknown>} */ (replyTo).msg_id ??
    /** @type {Record<string, unknown>} */ (replyTo).reply_to_msg_id
  if (raw == null) return null
  const n = typeof raw === 'number' ? raw : Number(raw)
  return Number.isFinite(n) && n > 0 ? n : null
}

function getReplyCount(row) {
  if (!row || typeof row !== 'object') return 0
  const o = /** @type {Record<string, unknown>} */ (row)
  const raw =
    o.reply_count ??
    o.replied_count ??
    o.replies_count ??
    (o.reply_to && typeof o.reply_to === 'object'
      ? /** @type {Record<string, unknown>} */ (o.reply_to).reply_count
      : null)
  const n = typeof raw === 'number' ? raw : Number(raw)
  return Number.isFinite(n) && n > 0 ? n : 0
}

function formatFileSize(size) {
  const n = Number(size)
  if (!Number.isFinite(n) || n <= 0) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

function renderForwardContent(content) {
  const title = typeof content.title === 'string' ? content.title : '聊天记录'
  const summary = Array.isArray(content.summary) ? content.summary : []
  return (
    <div className="msgForwardCard">
      <div className="msgForwardCard__title">{title}</div>
      {summary.slice(0, 3).map((line, idx) => (
        <div key={`${line}-${idx}`} className="msgForwardCard__line">
          {String(line)}
        </div>
      ))}
    </div>
  )
}

function renderContactCard(content, onContactCardOpen) {
  return (
    <button type="button" className="msgContactCard" onClick={() => onContactCardOpen?.(content)}>
      <div className="msgContactCard__avatar" aria-hidden>
        {String(content.username || content.user_id || '?').slice(0, 1).toUpperCase()}
      </div>
      <div>
        <div className="msgContactCard__name">{content.username || `用户 ${content.user_id}`}</div>
        <div className="msgContactCard__meta">联系人名片</div>
      </div>
    </button>
  )
}

function formatEventRange(content) {
  const opts = { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }
  try {
    const start = content.start_at ? new Date(String(content.start_at)).toLocaleString('zh-CN', opts) : ''
    const end = content.end_at ? new Date(String(content.end_at)).toLocaleString('zh-CN', opts) : ''
    return start && end ? `${start} - ${end}` : start || end
  } catch {
    return ''
  }
}

function renderCalendarInvite(content, { isMine = false, onCalendarInviteAction } = {}) {
  const status = String(content.status || 'pending')
  const statusText = status === 'accepted' ? '已同意' : status === 'rejected' ? '已拒绝' : '待处理'
  const participantId = Number(content.participant_id)
  const canRespond = !isMine && status === 'pending' && Number.isFinite(participantId) && participantId > 0
  return (
    <div className="msgCalendarInvite">
      <div className="msgCalendarInvite__eyebrow">日程邀请</div>
      <div className="msgCalendarInvite__title">{content.title || '未命名日程'}</div>
      <div className="msgCalendarInvite__time">{formatEventRange(content)}</div>
      {content.description ? <div className="msgCalendarInvite__desc">{String(content.description)}</div> : null}
      <div className="msgCalendarInvite__footer">
        <span className={`msgCalendarInvite__status is-${status}`}>{statusText}</span>
        {canRespond ? (
          <span className="msgCalendarInvite__actions">
            <button type="button" onClick={() => onCalendarInviteAction?.(participantId, 'accept')}>
              同意
            </button>
            <button type="button" onClick={() => onCalendarInviteAction?.(participantId, 'reject')}>
              拒绝
            </button>
          </span>
        ) : null}
      </div>
    </div>
  )
}

function renderRichContent(type, content, fallbackText, onPreviewFile, options = {}) {
  const url = contentUrl(content)
  if (type === 'image' && url) {
    return (
      <a href={url} target="_blank" rel="noreferrer" className="msgMediaLink">
        <img className="msgImage" src={String(content.thumbnail_url || url)} alt={String(content.filename || '图片')} />
      </a>
    )
  }
  if (type === 'video' && url) {
    return <video className="msgVideo" src={url} controls />
  }
  if (type === 'audio' && url) {
    return <audio className="msgAudio" src={url} controls />
  }
  if (type === 'file' && url) {
    return (
      <button type="button" className="msgFileCard" onClick={() => onPreviewFile?.({ ...content, url })}>
        <span className="msgFileCard__icon" aria-hidden>FILE</span>
        <span className="msgFileCard__main">
          <span className="msgFileCard__name">{content.filename || '文件'}</span>
          <span className="msgFileCard__meta">{formatFileSize(content.size)}</span>
        </span>
      </button>
    )
  }
  if (type === 'code') {
    return <CodeBlock code={String(content.code || '')} language={String(content.language || 'text')} />
  }
  if (type === 'calendar_invite') return renderCalendarInvite(content, options)
  if (type === 'contact_card') return renderContactCard(content, options.onContactCardOpen)
  if (type === 'forward') return renderForwardContent(content)
  if (type === 'text') return <RichMarkdown text={fallbackText || ''} />
  return fallbackText ? <RichMarkdown text={fallbackText} /> : '[不支持的消息类型]'
}

/**
 * @param {{
 *   messages: Array<Record<string, unknown>>,
 *   currentUserId: number | null,
 *   currentUserAvatar?: string | null,
 *   peerAvatar?: string | null,
 *   hasMoreOlder?: boolean,
 *   loadingOlder?: boolean,
 *   onLoadOlder?: () => Promise<void> | void,
 *   onRetryFailed?: (row: Record<string, unknown>) => void,
 *   onCopyMessage?: (row: Record<string, unknown>) => void | Promise<void>,
 *   onReplyToMessage?: (row: Record<string, unknown>) => void,
 *   onDeleteMessage?: (row: Record<string, unknown>) => void | Promise<void>,
 *   onRecallMessage?: (row: Record<string, unknown>) => void | Promise<void>,
 *   onForwardMessage?: (row: Record<string, unknown>) => void | Promise<void>,
 *   onBookmarkMessage?: (row: Record<string, unknown>) => void | Promise<void>,
 *   onReactMessage?: (row: Record<string, unknown>, emoji: string, reactedByMe?: boolean) => void | Promise<void>,
 *   onReadStatus?: (row: Record<string, unknown>) => void | Promise<void>,
 *   onCalendarInviteAction?: (participantId: number, action: 'accept' | 'reject') => void | Promise<void>,
 *   onContactCardOpen?: (content: Record<string, unknown>) => void | Promise<void>,
 *   onCopyImageMessage?: (row: Record<string, unknown>) => void | Promise<void>,
 * }} props
 */
export default function MessageList({
  messages,
  currentUserId,
  currentUserAvatar = null,
  peerAvatar = null,
  hasMoreOlder = false,
  loadingOlder = false,
  onLoadOlder,
  onRetryFailed,
  onCopyMessage,
  onReplyToMessage,
  onDeleteMessage,
  onRecallMessage,
  onForwardMessage,
  onBookmarkMessage,
  onReactMessage,
  onReadStatus,
  onCalendarInviteAction,
  onContactCardOpen,
  onCopyImageMessage,
}) {
  const bottomRef = useRef(null)
  /** @type {[{ x: number, y: number, row: Record<string, unknown> } | null, function]} */
  const [menu, setMenu] = useState(null)
  const [savedLabels, setSavedLabels] = useState({})
  const [labelError, setLabelError] = useState('')
  const [previewFile, setPreviewFile] = useState(null)
  /** 与 `messageAnchorId(row)` 一致，用于跳转后短时高亮 */
  const [highlightAnchorId, setHighlightAnchorId] = useState(/** @type {string|null} */ (null))
  const [jumpHint, setJumpHint] = useState('')
  const localReplyCountMap = useMemo(() => {
    const map = new Map()
    for (const row of messages) {
      if (!row || typeof row !== 'object') continue
      const rt = row.reply_to
      if (!rt || typeof rt !== 'object') continue
      const raw = rt.msg_id ?? rt.reply_to_msg_id
      const targetId = typeof raw === 'number' ? raw : Number(raw)
      if (!Number.isFinite(targetId) || targetId <= 0) continue
      map.set(targetId, (map.get(targetId) || 0) + 1)
    }
    return map
  }, [messages])

  const closeMenu = useCallback(() => setMenu(null), [])
  const blockAutoScrollUntilRef = useRef(0)

  const scrollToMessageId = useCallback(async (targetId) => {
    const anchor = `msg-${targetId}`
    const scrollAndHighlight = () => {
      const el = document.getElementById(anchor)
      if (!el) return false
      blockAutoScrollUntilRef.current = Date.now() + 3000
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      setHighlightAnchorId(anchor)
      window.setTimeout(() => setHighlightAnchorId(null), 1600)
      return true
    }
    if (scrollAndHighlight()) return

    // 引用目标未在当前窗口时，尝试向上加载历史后再次定位。
    if (typeof onLoadOlder === 'function' && hasMoreOlder && !loadingOlder) {
      try {
        await onLoadOlder()
        await new Promise((resolve) => window.setTimeout(resolve, 80))
        if (scrollAndHighlight()) return
      } catch {
        // ignore and fallthrough to hint
      }
    }
    setJumpHint('未找到原消息（可能不在已加载记录中）')
    window.setTimeout(() => setJumpHint(''), 2800)
  }, [hasMoreOlder, loadingOlder, onLoadOlder])

  const scrollToReferencedMessage = useCallback(async (replyTo) => {
    const targetId = replyReferencedServerMsgId(replyTo)
    if (targetId == null) {
      setJumpHint('无法定位原消息')
      window.setTimeout(() => setJumpHint(''), 2400)
      return
    }
    await scrollToMessageId(targetId)
  }, [scrollToMessageId])

  useEffect(() => {
    const onJump = (ev) => {
      const targetId = Number(ev?.detail?.msg_id)
      if (!Number.isFinite(targetId) || targetId <= 0) return
      void scrollToMessageId(targetId)
    }
    window.addEventListener(CHAT_EVENT_JUMP_TO_MESSAGE, onJump)
    return () => window.removeEventListener(CHAT_EVENT_JUMP_TO_MESSAGE, onJump)
  }, [scrollToMessageId])

  const scrollSkipRef = useRef({ len: 0, firstKey: '' })

  useLayoutEffect(() => {
    const first = messages[0]
    const firstKey = String(first?.msg_id ?? first?.client_msg_id ?? '')
    const { len: prevLen, firstKey: prevFirst } = scrollSkipRef.current
    const prepended =
      messages.length > prevLen && firstKey !== prevFirst && prevLen > 0
    scrollSkipRef.current = { len: messages.length, firstKey }
    if (prepended) return
    if (Date.now() < blockAutoScrollUntilRef.current) return
    const scrollEl =
      typeof document !== 'undefined' ? document.querySelector('.chatBody[data-chat-scroll="1"]') : null
    if (scrollEl) {
      const distanceToBottom = scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight
      if (distanceToBottom > 120) return
    }
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages])

  const openMenuAtPoint = useCallback((clientX, clientY, row) => {
    setMenu({ x: clientX, y: clientY, row })
  }, [])

  const handleRowContextMenu = useCallback(
    (e, row) => {
      e.preventDefault()
      openMenuAtPoint(e.clientX, e.clientY, row)
    },
    [openMenuAtPoint],
  )

  const handleMoreClick = useCallback(
    (e, row) => {
      e.preventDefault()
      e.stopPropagation()
      const r = e.currentTarget.getBoundingClientRect()
      openMenuAtPoint(r.right, r.bottom + 2, row)
    },
    [openMenuAtPoint],
  )

  const runCopy = useCallback(() => {
    if (!menu?.row || typeof onCopyMessage !== 'function') return
    void onCopyMessage(menu.row)
    closeMenu()
  }, [menu, onCopyMessage, closeMenu])

  const runReply = useCallback(() => {
    if (!menu?.row || typeof onReplyToMessage !== 'function') return
    if (!canReplyToRow(menu.row)) return
    onReplyToMessage(menu.row)
    closeMenu()
  }, [menu, onReplyToMessage, closeMenu])

  const runDelete = useCallback(() => {
    const row = menu?.row
    if (!row || typeof onDeleteMessage !== 'function') return
    if (!canDeleteRow(row)) return
    if (!window.confirm('删除后仅对你不可见，确定删除这条消息吗？')) return
    void onDeleteMessage(row)
    closeMenu()
  }, [menu, onDeleteMessage, closeMenu])

  const runRecall = useCallback(() => {
    const row = menu?.row
    if (!row || typeof onRecallMessage !== 'function') return
    if (!canDeleteRow(row)) return
    if (!window.confirm('确定撤回这条消息吗？')) return
    void onRecallMessage(row)
    closeMenu()
  }, [menu, onRecallMessage, closeMenu])

  const runForward = useCallback(() => {
    const row = menu?.row
    if (!row || typeof onForwardMessage !== 'function') return
    if (!canDeleteRow(row)) return
    void onForwardMessage(row)
    closeMenu()
  }, [menu, onForwardMessage, closeMenu])

  const runBookmark = useCallback(() => {
    const row = menu?.row
    if (!row || typeof onBookmarkMessage !== 'function') return
    if (!canDeleteRow(row)) return
    void onBookmarkMessage(row)
    closeMenu()
  }, [menu, onBookmarkMessage, closeMenu])

  const runReadStatus = useCallback(() => {
    const row = menu?.row
    if (!row || typeof onReadStatus !== 'function') return
    if (!canDeleteRow(row)) return
    void onReadStatus(row)
    closeMenu()
  }, [menu, onReadStatus, closeMenu])

  const runCopyImage = useCallback(() => {
    const row = menu?.row
    if (!row || typeof onCopyImageMessage !== 'function') return
    if (row.type !== 'image') return
    const c = row.content && typeof row.content === 'object' ? row.content : {}
    if (!contentUrl(c)) return
    void onCopyImageMessage(row)
    closeMenu()
  }, [menu, onCopyImageMessage, closeMenu])

  if (!messages.length) {
    return <div className="msgEmptySpace" aria-hidden />
  }

  return (
    <>
      {jumpHint ? (
        <div className="msgJumpHint" role="status">
          {jumpHint}
        </div>
      ) : null}
      {messages.map((row, idx) => {
        const sender = row.sender && typeof row.sender === 'object' ? row.sender : {}
        const sid = sender.user_id
        const uid = typeof sid === 'number' ? sid : Number(sid)
        const isMine = currentUserId != null && Number.isFinite(uid) && uid === currentUserId
        const type = typeof row.type === 'string' ? row.type : 'text'
        const contentObj = row.content && typeof row.content === 'object' ? row.content : {}
        const anchorId = messageAnchorId(row)
        const rowHighlight = anchorId && highlightAnchorId === anchorId

        if (isSystemNoticeLayout(row)) {
          const noticeText = row.is_recalled
            ? isMine
              ? '你撤回了一条消息'
              : `${senderLabel(sender)} 撤回了一条消息`
            : getMessagePlainText(row.content, type) ||
              summarizeMessageContent(type, contentObj) ||
              '[系统消息]'
          return (
            <div
              key={String(row.msg_id ?? row.client_msg_id ?? idx)}
              id={anchorId}
              className={`msgRow msgRow--systemNotice${rowHighlight ? ' msgRow--highlight' : ''}`}
              onContextMenu={(e) => handleRowContextMenu(e, row)}
            >
              <div className="msgSystemNotice" role="status">
                {noticeText}
              </div>
            </div>
          )
        }

        const isAnnouncement = type === 'group_announcement' || type === 'announcement'
        const announcementText =
          typeof contentObj.content === 'string'
            ? contentObj.content
            : typeof contentObj.text === 'string'
              ? contentObj.text
              : ''
        const text =
          getMessagePlainText(row.content, type) || summarizeMessageContent(type, contentObj)
        const recalled = Boolean(row.is_recalled)
        const msgIdRaw = row.msg_id
        const msgId = typeof msgIdRaw === 'number' ? msgIdRaw : Number(msgIdRaw)
        const localReplyCount = Number.isFinite(msgId) ? (localReplyCountMap.get(msgId) || 0) : 0
        const replyCount = Math.max(getReplyCount(row), localReplyCount)
        const replyTo =
          row.reply_to && typeof row.reply_to === 'object'
            ? /** @type {Record<string, unknown>} */ (row.reply_to)
            : null

        const avatarUrl = isMine
          ? resolveAvatarSrc(currentUserAvatar || sender.avatar)
          : resolveAvatarSrc(sender.avatar || peerAvatar)

        const bubble = (
          <div className={`bubble ${isMine ? 'bubble--right' : 'bubble--left'}`}>
            {!isMine && !isAnnouncement ? <div className="bubble__name">{senderLabel(sender)}</div> : null}
            {replyTo ? (
              <button
                type="button"
                className="replyCard replyCard--jump"
                aria-label="查看引用原消息位置"
                title="跳转到原消息"
                onClick={(e) => {
                  e.stopPropagation()
                  scrollToReferencedMessage(replyTo)
                }}
              >
                <div className="replyCard__title">
                  回复 {typeof replyTo.sender_name === 'string' ? replyTo.sender_name : '消息'}
                </div>
                <div className="replyCard__sub">
                  {typeof replyTo.content_summary === 'string' ? replyTo.content_summary : ''}
                </div>
              </button>
            ) : null}
            <div className={`bubble__content${isAnnouncement ? ' bubble__content--announcement' : ''}`}>
              {recalled ? (
                isMine ? (
                  '你撤回了一条消息'
                ) : (
                  `${senderLabel(sender)} 撤回了一条消息`
                )
              ) : isAnnouncement ? (
                <>
                  <div className="bubble__annTitle">群公告</div>
                  <div className="bubble__annText">{announcementText || '—'}</div>
                </>
              ) : (
                renderRichContent(type, contentObj, text, setPreviewFile, { isMine, onCalendarInviteAction, onContactCardOpen })
              )}
            </div>
            {!recalled && Array.isArray(row.reactions) && row.reactions.length > 0 ? (
              <div className="bubble__reactions">
                {row.reactions.map((reaction, reactionIdx) => {
                  const emoji = String(reaction?.emoji || '')
                  const count = Number(reaction?.count) || 0
                  const reactedByMe = Boolean(reaction?.is_me ?? reaction?.reacted_by_me)
                  if (!emoji) return null
                  return (
                    <button
                      type="button"
                      key={`${emoji}-${reactionIdx}`}
                      className={`bubble__reaction${reactedByMe ? ' is-me' : ''}`}
                      onClick={() => onReactMessage?.(row, emoji, reactedByMe)}
                    >
                      {emoji} {count}
                    </button>
                  )
                })}
              </div>
            ) : null}
            {replyCount > 0 ? (
              <div className="bubble__replyCount">被回复 {replyCount} 次</div>
            ) : null}
            <div className="bubble__time">
              {formatMsgTime(row.created_at)}
              {row.send_status === 'pending' ? (
                <span className="bubble__sendState bubble__sendState--pending" aria-live="polite">
                  {' '}
                  · 发送中…
                </span>
              ) : null}
              {row.send_status === 'sent' ? (
                <span className="bubble__sendState bubble__sendState--ok" aria-live="polite">
                  {' '}
                  · 已送达
                </span>
              ) : null}
              {row.send_status === 'failed' ? (
                <>
                  <span className="bubble__sendState bubble__sendState--err" aria-live="polite">
                    {' '}
                    · 发送失败
                  </span>
                  {typeof onRetryFailed === 'function' ? (
                    <button
                      type="button"
                      className="bubble__retryBtn"
                      onClick={() => onRetryFailed(row)}
                    >
                      重试
                    </button>
                  ) : null}
                </>
              ) : null}
            </div>
          </div>
        )

        const avatar = <MessageAvatar avatarUrl={avatarUrl} />

        return (
          <div
            key={String(row.msg_id ?? row.client_msg_id ?? idx)}
            id={anchorId}
            className={`msgRow${isMine ? ' msgRow--mine' : ''}${rowHighlight ? ' msgRow--highlight' : ''}`}
            onContextMenu={(e) => handleRowContextMenu(e, row)}
          >
            {!isMine ? (
              <>
                {avatar}
                <div className="bubbleWrap">
                  <button
                    type="button"
                    className="bubble__more"
                    aria-label="消息操作"
                    onClick={(e) => handleMoreClick(e, row)}
                  />
                  {bubble}
                  {(savedLabels[row.benchmark_object] ?? row.benchmark_label) && <span style={{display:'block',marginTop:6,fontSize:12,color:({'蓝色':'#3478db','红色':'#df5454','绿色':'#2c9c6a'})[savedLabels[row.benchmark_object] ?? row.benchmark_label]||'#516373'}}>● {savedLabels[row.benchmark_object] ?? row.benchmark_label}</span>}
                </div>
              </>
            ) : (
              <>
                <div className="bubbleWrap">
                  <button
                    type="button"
                    className="bubble__more"
                    aria-label="消息操作"
                    onClick={(e) => handleMoreClick(e, row)}
                  />
                  {bubble}
                  {(savedLabels[row.benchmark_object] ?? row.benchmark_label) && <span style={{display:'block',marginTop:6,fontSize:12,color:({'蓝色':'#3478db','红色':'#df5454','绿色':'#2c9c6a'})[savedLabels[row.benchmark_object] ?? row.benchmark_label]||'#516373'}}>● {savedLabels[row.benchmark_object] ?? row.benchmark_label}</span>}
                </div>
                {avatar}
              </>
            )}
          </div>
        )
      })}
      <div ref={bottomRef} />

      <PopMenu
        open={Boolean(menu)}
        anchorX={menu?.x ?? 0}
        anchorY={menu?.y ?? 0}
        onClose={closeMenu}
      >
        {nativeRun && menu?.row?.benchmark_object && menu.row.benchmark_options?.length > 0 && <>
          <div style={{padding:'8px 12px',fontSize:12,color:'#75808c'}}>消息标签</div>
          {['',...menu.row.benchmark_options].map(label=><button type="button" role="menuitem" className="popMenu__item" key={label} onClick={async()=>{const object=menu.row.benchmark_object;try{await command('label',object,label);setSavedLabels(prev=>({...prev,[object]:label}));setLabelError('');closeMenu()}catch(e){setLabelError(e.message)}}}><span style={{color:({'蓝色':'#3478db','红色':'#df5454','绿色':'#2c9c6a'})[label]||'#8c96a3'}}>●</span> {label||'清除标签'}</button>)}
          {labelError&&<div role="alert">{labelError}</div>}
        </>}
        {nativeRun && currentBusiness()?.task_id===13 && menu?.row?.benchmark_object && <button type="button" role="menuitem" className="popMenu__item" onClick={async()=>{try{await command('action',menu.row.benchmark_object,'归档');closeMenu()}catch(e){setLabelError(e.message)}}}>归档消息</button>}
        <div className="popMenu__emojiRow" role="group" aria-label="快速表情">
          {['👍', '❤️', '😂', '😮', '🙏'].map((emoji) => (
            <button
              type="button"
              key={emoji}
              className="popMenu__emojiBtn"
              disabled={!menu?.row || Boolean(menu?.row?.is_recalled) || typeof onReactMessage !== 'function'}
              onClick={() => {
                if (menu?.row) void onReactMessage?.(menu.row, emoji, false)
                closeMenu()
              }}
            >
              {emoji}
            </button>
          ))}
        </div>
        <button
          type="button"
          role="menuitem"
          className="popMenu__item"
          disabled={Boolean(menu?.row?.is_recalled)}
          onClick={runCopy}
        >
          复制文字
        </button>
        <button
          type="button"
          role="menuitem"
          className="popMenu__item"
          disabled={
            !menu?.row ||
            menu.row.type !== 'image' ||
            !contentUrl(menu.row.content && typeof menu.row.content === 'object' ? menu.row.content : {}) ||
            typeof onCopyImageMessage !== 'function'
          }
          onClick={runCopyImage}
        >
          复制图片
        </button>
        <button
          type="button"
          role="menuitem"
          className="popMenu__item"
          disabled={
            !menu?.row ||
            !canReplyToRow(menu.row) ||
            typeof onReplyToMessage !== 'function'
          }
          onClick={runReply}
        >
          回复此消息
        </button>
        <button
          type="button"
          role="menuitem"
          className="popMenu__item"
          disabled={!menu?.row || !canDeleteRow(menu.row) || typeof onForwardMessage !== 'function'}
          onClick={runForward}
        >
          转发消息
        </button>
        <button
          type="button"
          role="menuitem"
          className="popMenu__item"
          disabled={!menu?.row || !canDeleteRow(menu.row) || typeof onBookmarkMessage !== 'function'}
          onClick={runBookmark}
        >
          {nativeRun ? '收藏消息' : '加入待办'}
        </button>
        <button
          type="button"
          role="menuitem"
          className="popMenu__item"
          disabled={!menu?.row || !canDeleteRow(menu.row) || typeof onReadStatus !== 'function'}
          onClick={runReadStatus}
        >
          已读详情
        </button>
        <button
          type="button"
          role="menuitem"
          className="popMenu__item"
          disabled={!menu?.row || !canDeleteRow(menu.row) || Boolean(menu?.row?.is_recalled) || typeof onRecallMessage !== 'function'}
          onClick={runRecall}
        >
          撤回消息
        </button>
        <button
          type="button"
          role="menuitem"
          className="popMenu__item popMenu__item--danger"
          disabled={
            !menu?.row ||
            !canDeleteRow(menu.row) ||
            typeof onDeleteMessage !== 'function'
          }
          onClick={runDelete}
        >
          删除消息
        </button>
      </PopMenu>
      <FilePreviewModal file={previewFile} onClose={() => setPreviewFile(null)} />
    </>
  )
}
