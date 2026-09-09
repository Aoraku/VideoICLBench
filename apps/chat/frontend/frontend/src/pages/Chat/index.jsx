import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  createPrivateConversation,
  getConversationDetail,
  deleteConversation,
  listConversations,
  markConversationRead,
  searchConversationRecords,
  updateConversationSettings,
} from '../../api/conversations.js'
import {
  addBookmark,
  addReaction,
  deleteMessage,
  forwardMessages,
  getReadStatus,
  recallMessage,
  removeReaction,
  sendMessage,
  sendTextMessage,
} from '../../api/messages.js'
import { uploadFile } from '../../api/upload.js'
import { createAIConversation, sendAIMessageStream } from '../../api/ai.js'
import { respondCalendarInvitation } from '../../api/calendar.js'
import { listFriends, sendFriendRequest } from '../../api/friends.js'
import { getUser } from '../../api/users.js'
import { syncMessages } from '../../api/sync.js'
import { getGroupDetailRaw, getGroupMembers, parseGroupDetailPayload } from '../../api/groupApi.js'
import ImageEditorModal from '../../components/message/ImageEditorModal.jsx'
import MessageList from '../../components/message/MessageList.jsx'
import PopMenu from '../../components/ui/PopMenu.jsx'
import {
  CHAT_EVENT_CONVERSATION_REFRESH,
  CHAT_EVENT_JUMP_TO_MESSAGE,
  CHAT_EVENT_NEW_MESSAGE,
  CHAT_EVENT_NEW_MESSAGE_LEGACY,
} from '../../constants/chatEvents.js'
import { useConversationMessages } from '../../hooks/useConversationMessages.js'
import { useCurrentUserId } from '../../hooks/useCurrentUserId.js'
import { connectChatSocket } from '../../services/chatSocket.js'
import { getMessagePlainText } from '../../utils/messageText.js'
import { summarizeMessageContent } from '../../utils/messageContent.js'
import { buildOptimisticTextMessage } from '../../utils/normalizeMessage.js'
import { resolveAvatarSrc } from '../../utils/avatarUrl.js'
import { getFriendDisplayName, getPresenceLabel, presenceClass } from '../../utils/friends.js'
import { userFacingError } from '../../utils/userFacingError.js'

function sortConversationRows(rows) {
  return [...rows].sort((a, b) => {
    const pa = Boolean(a?.is_pinned)
    const pb = Boolean(b?.is_pinned)
    if (pa !== pb) return pa ? -1 : 1
    const ta = new Date(a?.updated_at || a?.last_message?.created_at || 0).getTime()
    const tb = new Date(b?.updated_at || b?.last_message?.created_at || 0).getTime()
    return tb - ta
  })
}

function convTitle(c) {
  if (!c || typeof c !== 'object') return '会话'
  const peer = c.peer_user
  if (peer && typeof peer === 'object') {
    return peer.remark || peer.username || '私聊'
  }
  if (c.type === 'group') return c.name || '群聊'
  if (c.type === 'ai') return c.name || 'AI助手'
  return '私聊'
}

function convListAvatar(c) {
  if (!c || typeof c !== 'object') return ''
  if (c.type === 'group') return resolveAvatarSrc(c.avatar)
  const peer = c.peer_user
  if (peer && typeof peer === 'object') return resolveAvatarSrc(peer.avatar)
  return ''
}

const EMPTY_MSG_FILTER = { senderId: '', from: '', to: '', keyword: '' }
const FILTER_MODE_ALL = 'all'
const FILTER_MODE_KEYWORD = 'keyword'
const FILTER_MODE_TIME = 'time'
const FILTER_MODE_SENDER = 'sender'
const SYNC_TS_KEY = 'chatglmj:lastSyncAt'
const CODE_LANGUAGES = [
  ['text', 'Text'],
  ['markdown', 'Markdown'],
  ['javascript', 'JavaScript'],
  ['typescript', 'TypeScript'],
  ['python', 'Python'],
  ['java', 'Java'],
  ['cpp', 'C/C++'],
  ['go', 'Go'],
  ['rust', 'Rust'],
  ['json', 'JSON'],
]

function ToolIcon({ type }) {
  if (type === 'file') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden>
        <path d="M5 7.5h5l2 2h7v7.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9.5a2 2 0 0 1 2-2Z" />
      </svg>
    )
  }
  if (type === 'contact') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden>
        <rect x="4" y="5" width="16" height="14" rx="2" />
        <circle cx="10" cy="11" r="2" />
        <path d="M7.5 16c.5-1.7 1.4-2.5 2.5-2.5s2 .8 2.5 2.5" />
        <path d="M14.5 10h2.5M14.5 14h2.5" />
      </svg>
    )
  }
  if (type === 'mention') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden>
        <circle cx="12" cy="12" r="4" />
        <path d="M16 8v5.2c0 1.4.7 2.3 2 2.3 1.7 0 3-1.5 3-3.7A9 9 0 1 0 12 21" />
      </svg>
    )
  }
  if (type === 'ai') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden>
        <path d="M12 3v3M12 18v3M4.5 12h3M16.5 12h3" />
        <path d="M8.5 8.5h7v7h-7z" />
        <path d="m7 5 1.5 3.5M17 5l-1.5 3.5M7 19l1.5-3.5M17 19l-1.5-3.5" />
      </svg>
    )
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden>
      <path d="M8 8 4 12l4 4M16 8l4 4-4 4" />
      <path d="m14 5-4 14" />
    </svg>
  )
}

function messageContentUrl(content) {
  return String(content?.url || content?.file_url || content?.download_url || content?.src || '')
}

function absoluteContentUrl(url) {
  if (!url) return ''
  try {
    return new URL(url, window.location.origin).href
  } catch {
    return url
  }
}

async function imageBlobToPngBlob(blob) {
  const objectUrl = URL.createObjectURL(blob)
  try {
    const image = await new Promise((resolve, reject) => {
      const img = new Image()
      img.onload = () => resolve(img)
      img.onerror = () => reject(new Error('图片转换失败'))
      img.src = objectUrl
    })
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, image.naturalWidth || image.width || 1)
    canvas.height = Math.max(1, image.naturalHeight || image.height || 1)
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('图片转换失败')
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height)
    const pngBlob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png', 0.92))
    if (!pngBlob) throw new Error('图片转换失败')
    return pngBlob
  } finally {
    URL.revokeObjectURL(objectUrl)
  }
}

async function copyImageBlobToClipboard(blob) {
  if (!navigator.clipboard || !window.ClipboardItem) {
    throw new Error('当前浏览器不支持图片写入剪贴板')
  }
  const mime = blob.type && blob.type.startsWith('image/') ? blob.type : 'image/png'
  try {
    await navigator.clipboard.write([new window.ClipboardItem({ [mime]: blob })])
  } catch (err) {
    if (mime === 'image/png') throw err
    const pngBlob = await imageBlobToPngBlob(blob)
    await navigator.clipboard.write([new window.ClipboardItem({ 'image/png': pngBlob })])
  }
}

function clampNumber(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function parseFlexibleDateToIso(input, endOfDay = false) {
  const raw = String(input || '').trim()
  if (!raw) return null
  const normalized = raw
    .replace(/\s+/g, '')
    .replace(/[年/.]/g, '-')
    .replace(/月/g, '-')
    .replace(/日/g, '')
  const m = normalized.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/)
  if (!m) return null
  const y = Number(m[1])
  const mm = Number(m[2])
  const d = Number(m[3])
  if (!Number.isFinite(y) || !Number.isFinite(mm) || !Number.isFinite(d)) return null
  const hh = endOfDay ? 23 : 0
  const mi = endOfDay ? 59 : 0
  const ss = endOfDay ? 59 : 0
  const ms = endOfDay ? 999 : 0
  const date = new Date(y, mm - 1, d, hh, mi, ss, ms)
  if (Number.isNaN(date.getTime())) return null
  return date.toISOString()
}

function normalizeDateDisplay(input) {
  const raw = String(input || '').trim()
  if (!raw) return ''
  const normalized = raw
    .replace(/\s+/g, '')
    .replace(/[年/.]/g, '-')
    .replace(/月/g, '-')
    .replace(/日/g, '')
  const m = normalized.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/)
  if (!m) return raw
  const y = Number(m[1])
  const mm = String(Number(m[2])).padStart(2, '0')
  const d = String(Number(m[3])).padStart(2, '0')
  return `${y}年${mm}月${d}日`
}

function formatAnnouncementTime(iso) {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return String(iso)
    return d.toLocaleString('zh-CN', {
      month: 'numeric',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return String(iso)
  }
}

function normalizeGroupAnnouncementFromPush(data) {
  if (!data || typeof data !== 'object') return null
  const d = /** @type {Record<string, unknown>} */ (data)
  const convId = d.conversation_id
  const groupId = convId != null ? String(convId) : ''
  if (!groupId) return null
  const annId = d.announcement_id
  const id = annId != null ? String(annId) : ''
  const publisher = d.publisher && typeof d.publisher === 'object' ? d.publisher : {}
  return {
    id: id || `ann-${groupId}`,
    groupId,
    content: String(d.content ?? ''),
    publisherId: String(publisher.user_id ?? ''),
    publisherName: typeof publisher.username === 'string' ? publisher.username : '',
    createdAt: String(d.created_at ?? ''),
  }
}

function buildAnnouncementMessage(announcement) {
  if (!announcement || !announcement.content) return null
  const publisherId = announcement.publisherId
  const parsedId = typeof publisherId === 'number' ? publisherId : Number(publisherId)
  const senderId = Number.isFinite(parsedId) ? parsedId : -1
  const createdAt = announcement.createdAt || new Date().toISOString()
  const msgKey = announcement.id || createdAt
  return {
    client_msg_id: `ann-${announcement.groupId}-${msgKey}`,
    msg_id: null,
    sender: {
      user_id: senderId,
      username: announcement.publisherName || '',
      avatar: null,
      group_nickname: null,
    },
    sender_name: announcement.publisherName || '',
    type: 'group_announcement',
    content: {
      content: announcement.content,
      announcement_id: announcement.id || null,
    },
    created_at: createdAt,
    reply_to: null,
    is_recalled: false,
    send_status: 'sent',
    reactions: [],
    read_by_count: 0,
  }
}

function insertMessageByTime(list, row) {
  if (!row) return list
  const createdAt = row.created_at
  const ts = Date.parse(createdAt || '')
  if (!Number.isFinite(ts)) return [...list, row]
  const idx = list.findIndex((item) => {
    const t = Date.parse(String(item?.created_at || ''))
    return Number.isFinite(t) && t > ts
  })
  if (idx < 0) return [...list, row]
  return [...list.slice(0, idx), row, ...list.slice(idx)]
}

function lastPreview(last) {
  if (!last || typeof last !== 'object') return '暂无消息'
  const type = typeof last.type === 'string' ? last.type : 'text'
  if (last.is_recalled) return '撤回了一条消息'
  switch (type) {
    case 'text':
      return getMessagePlainText(last.content, type) || '[消息]'
    case 'image':
      return '[图片]'
    case 'file':
      return '[文件]'
    case 'audio':
      return '[语音]'
    case 'video':
      return '[视频]'
    case 'code':
      return '[代码]'
    case 'group_announcement':
    case 'announcement':
      return getMessagePlainText(last.content, type) || '[群公告]'
    default:
      return '[消息]'
  }
}

function extractSenderId(message) {
  const raw = message?.sender?.user_id ?? message?.sender_id ?? message?.sender?.id ?? null
  const id = typeof raw === 'number' ? raw : Number(raw)
  return Number.isFinite(id) ? id : null
}

async function hydratePeerUsers(rows) {
  if (!Array.isArray(rows) || rows.length === 0) return rows
  const targets = rows.filter((c) => {
    if (!c || typeof c !== 'object') return false
    if (c.peer_user && typeof c.peer_user === 'object') return false
    if (c.type === 'group') return false
    const id = Number(c.conversation_id)
    return Number.isFinite(id) && id > 0
  })
  if (targets.length === 0) return rows

  const pairs = await Promise.all(
    targets.map(async (c) => {
      const convId = Number(c.conversation_id)
      try {
        const detail = await getConversationDetail(convId)
        return [convId, detail?.peer_user && typeof detail.peer_user === 'object' ? detail.peer_user : null]
      } catch {
        return [convId, null]
      }
    }),
  )
  const peerMap = new Map(pairs.filter((x) => x[1] != null))
  if (peerMap.size === 0) return rows
  return rows.map((c) => {
    const id = Number(c?.conversation_id)
    if (!Number.isFinite(id)) return c
    if (!peerMap.has(id)) return c
    return { ...c, peer_user: peerMap.get(id) }
  })
}

export default function ChatPage() {
  const [searchParams] = useSearchParams()
  const openParam = searchParams.get('open') || searchParams.get('conv')
  const jumpMsgParam = searchParams.get('msg') || searchParams.get('message')

  const { userId: currentUserId, username: meUsername, avatar: meAvatar } = useCurrentUserId()
  const [conversations, setConversations] = useState([])
  const [listLoading, setListLoading] = useState(false)
  const [listError, setListError] = useState('')
  const [selectedId, setSelectedId] = useState(null)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState('')
  /** 空白/纯空格发送时短时提示（与 sendError 区分） */
  const [sendHint, setSendHint] = useState('')
  /** 发送未回包前，在列表尾部挂乐观消息（含当前时间，与 send_status 联动） */
  const [optimisticTail, setOptimisticTail] = useState(/** @type {Record<string, unknown>|Record<string, unknown>[]|null} */ (null))
  /** 从消息菜单选择的回复目标（需服务端 msg_id） */
  const [replyTargetRow, setReplyTargetRow] = useState(/** @type {Record<string, unknown>|null} */ (null))
  /** 左侧会话列表：右键 / 「更多」菜单 */
  const [convMenu, setConvMenu] = useState(
    /** @type {{ x: number, y: number, conv: Record<string, unknown> } | null} */ (null),
  )
  const draftInputRef = useRef(/** @type {HTMLTextAreaElement | null} */ (null))
  const fileInputRef = useRef(/** @type {HTMLInputElement | null} */ (null))
  const socketRef = useRef(null)
  const typingThrottleRef = useRef(0)
  const [convBusyMap, setConvBusyMap] = useState({})
  const [groupAnnouncementByConv, setGroupAnnouncementByConv] = useState({})
  const [typingUsers, setTypingUsers] = useState({})
  const [fileUploading, setFileUploading] = useState(false)
  const [mentionUserIds, setMentionUserIds] = useState([])
  const [mentionMembers, setMentionMembers] = useState([])
  const [mentionPickerOpen, setMentionPickerOpen] = useState(false)
  const [mentionLoading, setMentionLoading] = useState(false)
  const [mentionError, setMentionError] = useState('')

  const [convSearch, setConvSearch] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [convSearchLoading, setConvSearchLoading] = useState(false)
  const [convSearchError, setConvSearchError] = useState('')
  const [convSearchRows, setConvSearchRows] = useState([])
  const [filterDraft, setFilterDraft] = useState(() => ({ ...EMPTY_MSG_FILTER }))
  const [filterApplied, setFilterApplied] = useState(() => ({ ...EMPTY_MSG_FILTER }))
  const [msgFilterOpen, setMsgFilterOpen] = useState(false)
  const [msgFilterMode, setMsgFilterMode] = useState(FILTER_MODE_ALL)
  const [readingAll, setReadingAll] = useState(false)
  const [headerAvatarBroken, setHeaderAvatarBroken] = useState(false)
  const processedIncomingRef = useRef(new Set())
  const processedIncomingTransientRef = useRef(new Map())
  const ownClientMsgIdsRef = useRef(new Set())
  const jumpDispatchedRef = useRef('')
  const consumedOpenParamRef = useRef('')
  const aiStreamingRef = useRef(false)
  const [codeMode, setCodeMode] = useState(false)
  const [codeLanguage, setCodeLanguage] = useState('text')
  const [inputHeight, setInputHeight] = useState(54)
  const [contactPickerOpen, setContactPickerOpen] = useState(false)
  const [contactPickerLoading, setContactPickerLoading] = useState(false)
  const [contactPickerError, setContactPickerError] = useState('')
  const [contactFriends, setContactFriends] = useState([])
  const [contactQuery, setContactQuery] = useState('')
  const [imageEditorFile, setImageEditorFile] = useState(null)
  const [forwardPickerOpen, setForwardPickerOpen] = useState(false)
  const [forwardTargetRow, setForwardTargetRow] = useState(null)
  const [forwardMode, setForwardMode] = useState('individual')
  const [forwardQuery, setForwardQuery] = useState('')
  const [forwardSending, setForwardSending] = useState(false)
  const [todoDialogOpen, setTodoDialogOpen] = useState(false)
  const [todoTargetRow, setTodoTargetRow] = useState(null)
  const [todoNote, setTodoNote] = useState('')
  const [todoSaving, setTodoSaving] = useState(false)
  const [contactCardOpen, setContactCardOpen] = useState(false)
  const [contactCardLoading, setContactCardLoading] = useState(false)
  const [contactCardError, setContactCardError] = useState('')
  const [contactCardProfile, setContactCardProfile] = useState(null)
  const [contactCardRequesting, setContactCardRequesting] = useState(false)

  const messageFilterOpts = useMemo(() => {
    const rangeAfter = parseFlexibleDateToIso(filterApplied.from, false)
    const rangeBefore = parseFlexibleDateToIso(filterApplied.to, true)
    let senderId = null
    if (filterApplied.senderId !== '' && filterApplied.senderId != null) {
      const n = Number(filterApplied.senderId)
      if (Number.isFinite(n)) senderId = n
    }
    const kw = filterApplied.keyword.trim()
    return {
      senderId,
      keyword: kw || null,
      rangeAfter,
      rangeBefore,
    }
  }, [filterApplied])

  const {
    messages,
    loading: msgLoading,
    loadingOlder,
    hasMoreOlder,
    error: msgError,
    refetch: refetchMessages,
    loadOlder,
  } = useConversationMessages(selectedId, messageFilterOpts)

  const chatBodyRef = useRef(/** @type {HTMLDivElement|null} */ (null))

  const senderPickOptions = useMemo(() => {
    const map = new Map()
    for (const row of messages) {
      const s = row.sender && typeof row.sender === 'object' ? row.sender : null
      if (!s || s.user_id == null) continue
      const uid = s.user_id
      const id = typeof uid === 'number' ? uid : Number(uid)
      if (!Number.isFinite(id)) continue
      const label = String((s.group_nickname || s.username || '').trim() || id)
      map.set(id, label)
    }
    return [...map.entries()].sort((a, b) => a[1].localeCompare(b[1], 'zh-CN'))
  }, [messages])

  const selectedConv = useMemo(
    () => conversations.find((c) => String(c.conversation_id) === String(selectedId)) ?? null,
    [conversations, selectedId],
  )

  const selectedGroupAnnouncement = useMemo(() => {
    if (!selectedId || selectedConv?.type !== 'group') return null
    const key = String(selectedId)
    return Object.prototype.hasOwnProperty.call(groupAnnouncementByConv, key)
      ? groupAnnouncementByConv[key]
      : null
  }, [groupAnnouncementByConv, selectedConv?.type, selectedId])

  const messagesForList = useMemo(() => {
    let rows = messages
    if (selectedConv?.type === 'group' && selectedGroupAnnouncement?.content) {
      const annId = selectedGroupAnnouncement.id
      const hasAnnouncement = rows.some((row) => {
        if (!row || row.type !== 'group_announcement') return false
        const c = row.content && typeof row.content === 'object' ? row.content : {}
        if (annId != null && c.announcement_id != null) {
          return String(c.announcement_id) === String(annId)
        }
        if (typeof c.content === 'string') {
          return c.content === selectedGroupAnnouncement.content
        }
        return false
      })
      if (!hasAnnouncement) {
        const annRow = buildAnnouncementMessage(selectedGroupAnnouncement)
        if (annRow) rows = insertMessageByTime(rows, annRow)
      }
    }
    if (Array.isArray(optimisticTail)) {
      const serverIds = new Set(rows.map((row) => Number(row?.msg_id)).filter((id) => Number.isFinite(id) && id > 0))
      rows = [
        ...rows,
        ...optimisticTail.filter((row) => {
          const id = Number(row?.msg_id)
          return !Number.isFinite(id) || id <= 0 || !serverIds.has(id)
        }),
      ]
    } else if (optimisticTail) rows = [...rows, optimisticTail]
    return rows
  }, [messages, optimisticTail, selectedConv?.type, selectedGroupAnnouncement])

  useEffect(() => {
    if (!selectedId || selectedConv?.type !== 'group') return
    const key = String(selectedId)
    if (Object.prototype.hasOwnProperty.call(groupAnnouncementByConv, key)) return
    let cancelled = false
    ;(async () => {
      try {
        const raw = await getGroupDetailRaw(key)
        const parsed = parseGroupDetailPayload(raw, key)
        if (!cancelled) {
          setGroupAnnouncementByConv((prev) => ({ ...prev, [key]: parsed.latestAnnouncement ?? null }))
        }
      } catch {
        if (!cancelled) {
          setGroupAnnouncementByConv((prev) => ({ ...prev, [key]: null }))
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [groupAnnouncementByConv, selectedConv?.type, selectedId])

  useEffect(() => {
    setHeaderAvatarBroken(false)
  }, [selectedConv?.conversation_id, selectedConv?.avatar, selectedConv?.peer_user?.avatar])

  useEffect(() => {
    let cancelled = false
    setListLoading(true)
    setListError('')
    ;(async () => {
      try {
        const data = await listConversations({ page: 1, pageSize: 50 })
        const rawRows = Array.isArray(data?.results) ? data.results : []
        const rows = await hydratePeerUsers(rawRows)
        if (!cancelled) setConversations(sortConversationRows(rows))
      } catch (e) {
        if (!cancelled) setListError(userFacingError(e, '加载会话失败'))
      } finally {
        if (!cancelled) setListLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!openParam || !conversations.length) return
    if (consumedOpenParamRef.current === String(openParam)) return
    const found = conversations.find((c) => String(c.conversation_id) === String(openParam))
    if (found) {
      consumedOpenParamRef.current = String(openParam)
      setSelectedId(Number(found.conversation_id))
    }
  }, [openParam, conversations])

  useEffect(() => {
    const msgId = Number(jumpMsgParam)
    const convId = Number(selectedId)
    if (!Number.isFinite(convId) || convId <= 0 || !Number.isFinite(msgId) || msgId <= 0) return
    if (msgLoading && messagesForList.length === 0) return
    const key = `${convId}:${msgId}`
    if (jumpDispatchedRef.current === key) return
    jumpDispatchedRef.current = key
    window.setTimeout(() => {
      window.dispatchEvent(new CustomEvent(CHAT_EVENT_JUMP_TO_MESSAGE, { detail: { conversation_id: convId, msg_id: msgId } }))
    }, 0)
  }, [jumpMsgParam, messagesForList.length, msgLoading, selectedId])

  useEffect(() => {
    setDraft('')
    setSendError('')
    setSendHint('')
    setOptimisticTail(null)
    setReplyTargetRow(null)
    setMsgFilterOpen(false)
    setMsgFilterMode(FILTER_MODE_ALL)
    setFilterDraft({ ...EMPTY_MSG_FILTER })
    setFilterApplied({ ...EMPTY_MSG_FILTER })
    setMentionUserIds([])
    setMentionMembers([])
    setMentionPickerOpen(false)
    setMentionError('')
    setCodeMode(false)
    setContactPickerOpen(false)
    setContactPickerError('')
    setContactQuery('')
    setForwardPickerOpen(false)
    setForwardTargetRow(null)
    setForwardQuery('')
    setTodoDialogOpen(false)
    setTodoTargetRow(null)
    setTodoNote('')
    setContactCardOpen(false)
    setContactCardProfile(null)
    setContactCardError('')
  }, [selectedId])

  const filteredConversations = useMemo(() => {
    const q = searchOpen ? convSearch.trim().toLowerCase() : ''
    if (!q) return conversations
    return conversations.filter((c) => convTitle(c).toLowerCase().includes(q))
  }, [conversations, convSearch, searchOpen])

  const conversationTitleMap = useMemo(() => {
    const map = new Map()
    for (const c of conversations) {
      if (!c || typeof c !== 'object') continue
      const id = Number(c.conversation_id)
      if (!Number.isFinite(id) || id <= 0) continue
      map.set(id, convTitle(c))
    }
    return map
  }, [conversations])

  const selectedPeerPresence = useMemo(() => {
    if (selectedConv?.type !== 'private') return null
    const status = selectedConv.peer_user?.status
    return status && typeof status === 'object' ? status : { presence: 'offline' }
  }, [selectedConv])

  const forwardTargets = useMemo(() => {
    const q = forwardQuery.trim().toLowerCase()
    const friendRows = contactFriends.map((friend) => ({
      kind: 'friend',
      id: `friend-${friend.user_id}`,
      userId: friend.user_id,
      title: getFriendDisplayName(friend),
      meta: `私聊 · @${friend.username || friend.user_id}`,
      avatar: friend.avatar,
    }))
    const groupRows = conversations
      .filter((conv) => conv?.type === 'group')
      .map((conv) => ({
        kind: 'group',
        id: `group-${conv.conversation_id}`,
        conversationId: conv.conversation_id,
        title: convTitle(conv),
        meta: `群聊 · ${conv.member_count || ''}${conv.member_count ? ' 人' : ''}`,
        avatar: conv.avatar,
      }))
    const rows = [...friendRows, ...groupRows]
    if (!q) return rows
    return rows.filter((row) => `${row.title} ${row.meta}`.toLowerCase().includes(q))
  }, [contactFriends, conversations, forwardQuery])

  useEffect(() => {
    if (!searchOpen) {
      setConvSearchLoading(false)
      setConvSearchError('')
      setConvSearchRows([])
      return
    }
    const q = convSearch.trim()
    if (q.length < 1) {
      setConvSearchLoading(false)
      setConvSearchError('')
      setConvSearchRows([])
      return
    }
    let cancelled = false
    const timer = window.setTimeout(async () => {
      setConvSearchLoading(true)
      setConvSearchError('')
      try {
        const data = await searchConversationRecords({ keyword: q, page: 1, pageSize: 8 })
        if (!cancelled) setConvSearchRows(Array.isArray(data?.results) ? data.results : [])
      } catch (e) {
        if (!cancelled) {
          setConvSearchRows([])
          setConvSearchError(userFacingError(e, '搜索失败'))
        }
      } finally {
        if (!cancelled) setConvSearchLoading(false)
      }
    }, 260)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [convSearch, searchOpen])

  useEffect(() => {
    const onIncoming = async (ev) => {
      const data = ev?.detail
      const convId = Number(data?.conversation_id)
      if (!convId) return
      const msgId = Number(data?.msg_id)
      if (Number.isFinite(msgId) && msgId > 0) {
        const key = `${convId}:${msgId}`
        if (processedIncomingRef.current.has(key)) return
        processedIncomingRef.current.add(key)
        if (processedIncomingRef.current.size > 4000) {
          const oldest = processedIncomingRef.current.values().next().value
          if (oldest) processedIncomingRef.current.delete(oldest)
        }
      } else {
        const transientKey = [
          convId,
          data?.client_msg_id ?? '',
          data?.created_at ?? '',
          data?.sender?.user_id ?? data?.sender_id ?? '',
          typeof data?.type === 'string' ? data.type : '',
        ].join(':')
        const now = Date.now()
        const lastSeen = processedIncomingTransientRef.current.get(transientKey)
        if (typeof lastSeen === 'number' && now - lastSeen < 15000) return
        processedIncomingTransientRef.current.set(transientKey, now)
        for (const [k, ts] of processedIncomingTransientRef.current) {
          if (now - ts > 60000) processedIncomingTransientRef.current.delete(k)
        }
      }
      const senderId = extractSenderId(data)
      const clientMsgId =
        typeof data?.client_msg_id === 'string' && data.client_msg_id.trim() ? data.client_msg_id.trim() : null
      const fromSelfBySender = currentUserId != null && senderId != null && senderId === currentUserId
      const fromSelfByClientMsgId =
        clientMsgId != null && ownClientMsgIdsRef.current.has(clientMsgId)
      const fromSelf = fromSelfBySender || fromSelfByClientMsgId
      if (fromSelfByClientMsgId) ownClientMsgIdsRef.current.delete(clientMsgId)
      setConversations((prev) =>
        sortConversationRows(
          prev.map((c) => {
            if (Number(c.conversation_id) !== convId) return c
            const unread = Number(c.unread_count) || 0
            return {
              ...c,
              last_message: {
                msg_id: data?.msg_id,
                sender_id: senderId,
                sender_name: data?.sender?.username ?? data?.sender_name,
                type: data?.type,
                content: data?.content,
                created_at: data?.created_at,
              },
              updated_at: data?.created_at || c.updated_at,
              unread_count:
                !fromSelf && Number(selectedId) !== convId ? unread + 1 : unread,
            }
          }),
        ),
      )

      if (!fromSelf && Number(selectedId) === convId && Number(data?.msg_id)) {
        try {
          await markConversationRead(convId, Number(data.msg_id))
          setConversations((prev) =>
            sortConversationRows(
              prev.map((c) => (Number(c.conversation_id) === convId ? { ...c, unread_count: 0 } : c)),
            ),
          )
        } catch {
          // ignore
        }
      }
    }
    window.addEventListener(CHAT_EVENT_NEW_MESSAGE, onIncoming)
    window.addEventListener(CHAT_EVENT_NEW_MESSAGE_LEGACY, onIncoming)
    return () => {
      window.removeEventListener(CHAT_EVENT_NEW_MESSAGE, onIncoming)
      window.removeEventListener(CHAT_EVENT_NEW_MESSAGE_LEGACY, onIncoming)
    }
  }, [currentUserId, selectedId])

  const selectConversation = useCallback(async (conv) => {
    const id = Number(conv?.conversation_id)
    if (!id) return
    setSelectedId(id)
    const lastId = Number(conv?.last_message?.msg_id)
    if (!lastId) return
    try {
      await markConversationRead(id, lastId)
      setConversations((prev) =>
        sortConversationRows(
          prev.map((c) => (Number(c.conversation_id) === id ? { ...c, unread_count: 0 } : c)),
        ),
      )
    } catch {
      // 已读失败不阻塞切换
    }
  }, [])

  const runConvAction = useCallback(
    async (conv, task) => {
      const id = Number(conv?.conversation_id)
      if (!id || convBusyMap[id]) return
      setConvBusyMap((prev) => ({ ...prev, [id]: true }))
      try {
        await task(id)
      } catch (e) {
        setSendHint(userFacingError(e, '会话操作失败'))
        window.setTimeout(() => setSendHint(''), 2200)
      } finally {
        setConvBusyMap((prev) => {
          const next = { ...prev }
          delete next[id]
          return next
        })
      }
    },
    [convBusyMap],
  )

  const onMarkAllRead = useCallback(async () => {
    const targets = conversations.filter((c) => (Number(c.unread_count) || 0) > 0 && Number(c?.last_message?.msg_id))
    if (targets.length === 0) return
    setReadingAll(true)
    try {
      await Promise.allSettled(
        targets.map((c) => markConversationRead(Number(c.conversation_id), Number(c.last_message.msg_id))),
      )
      setConversations((prev) =>
        sortConversationRows(prev.map((c) => ((Number(c.unread_count) || 0) > 0 ? { ...c, unread_count: 0 } : c))),
      )
    } finally {
      setReadingAll(false)
    }
  }, [conversations])

  const onJumpSearchRow = useCallback(
    async (row) => {
      const convId = Number(row?.conversation_id)
      const msgId = Number(row?.msg_id)
      if (!convId) return
      const target = conversations.find((c) => Number(c.conversation_id) === convId) || { conversation_id: convId, last_message: { msg_id: msgId } }
      await selectConversation(target)
      window.dispatchEvent(new CustomEvent(CHAT_EVENT_JUMP_TO_MESSAGE, { detail: { conversation_id: convId, msg_id: msgId } }))
      setConvSearch('')
      setConvSearchRows([])
    },
    [conversations, selectConversation],
  )

  const onChatScroll = useCallback(() => {
    const el = chatBodyRef.current
    if (!el || loadingOlder || !hasMoreOlder || msgLoading) return
    if (el.scrollTop < 96) void loadOlder()
  }, [hasMoreOlder, loadOlder, loadingOlder, msgLoading])

  const onCopyMessage = useCallback(async (row) => {
    const type = typeof row.type === 'string' ? row.type : 'text'
    if (row.is_recalled) return
    const t = getMessagePlainText(row.content, type)
    if (!t) return
    try {
      await navigator.clipboard.writeText(t)
    } catch {
      setSendHint('复制失败，请检查浏览器权限')
      window.setTimeout(() => setSendHint(''), 2200)
    }
  }, [])

  const refreshConversationList = useCallback(async () => {
    try {
      const data = await listConversations({ page: 1, pageSize: 50 })
      const rawRows = Array.isArray(data?.results) ? data.results : []
      const rows = await hydratePeerUsers(rawRows)
      setConversations(sortConversationRows(rows))
    } catch {
      // 忽略：左侧列表不必因刷新失败打断发送成功体验
    }
  }, [])

  const onOpenAIConversation = useCallback(async () => {
    setListError('')
    try {
      const existed = conversations.find((c) => c.type === 'ai')
      if (existed?.conversation_id) {
        setSelectedId(Number(existed.conversation_id))
        return
      }
      const data = await createAIConversation('我的AI助手')
      const convId = Number(data?.conversation_id)
      await refreshConversationList()
      if (Number.isFinite(convId) && convId > 0) setSelectedId(convId)
    } catch (e) {
      setListError(userFacingError(e, '创建 AI 会话失败'))
    }
  }, [conversations, refreshConversationList])

  useEffect(() => {
    const onRefresh = () => {
      void refreshConversationList()
    }
    window.addEventListener(CHAT_EVENT_CONVERSATION_REFRESH, onRefresh)
    return () => window.removeEventListener(CHAT_EVENT_CONVERSATION_REFRESH, onRefresh)
  }, [refreshConversationList])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const fallbackSince = new Date(Date.now() - 5 * 60 * 1000).toISOString()
      const since = localStorage.getItem(SYNC_TS_KEY) || fallbackSince
      try {
        const data = await syncMessages({ since, limit: 200 })
        if (cancelled) return
        const rows = Array.isArray(data?.messages) ? data.messages : []
        for (const row of rows) {
          window.dispatchEvent(new CustomEvent(CHAT_EVENT_NEW_MESSAGE, { detail: row }))
        }
        const eventTypes = new Set((Array.isArray(data?.events) ? data.events : []).map((event) => event?.type))
        if (rows.length > 0 || eventTypes.size > 0) {
          await refreshConversationList()
          if (!cancelled && selectedId && !aiStreamingRef.current) await refetchMessages()
        }
        if (data?.sync_timestamp) localStorage.setItem(SYNC_TS_KEY, String(data.sync_timestamp))
      } catch {
        localStorage.setItem(SYNC_TS_KEY, new Date().toISOString())
      }
    })()
    return () => {
      cancelled = true
    }
  }, [refetchMessages, refreshConversationList, selectedId])

  useEffect(() => {
    // 优先使用 WS 实时消息；若后端未提供 WS 路由，由下面的轮询兜底。
    const disconnect = connectChatSocket({
      onMessage: (msg) => {
        if (msg?.type === 'new_message' && msg?.data) {
          window.dispatchEvent(new CustomEvent(CHAT_EVENT_NEW_MESSAGE, { detail: msg.data }))
          window.dispatchEvent(new CustomEvent(CHAT_EVENT_NEW_MESSAGE_LEGACY, { detail: msg.data }))
        }
        if (msg?.type === 'group_announcement' && msg?.data) {
          const ann = normalizeGroupAnnouncementFromPush(msg.data)
          if (ann?.groupId) {
            setGroupAnnouncementByConv((prev) => ({ ...prev, [ann.groupId]: ann }))
            setConversations((prev) =>
              sortConversationRows(
                prev.map((c) => {
                  if (String(c.conversation_id) !== ann.groupId) return c
                  return {
                    ...c,
                    last_message: {
                      msg_id: c?.last_message?.msg_id ?? null,
                      sender_id: ann.publisherId ? Number(ann.publisherId) : null,
                      sender_name: ann.publisherName || '',
                      type: 'group_announcement',
                      content: { content: ann.content },
                      created_at: ann.createdAt,
                    },
                    updated_at: ann.createdAt || c.updated_at,
                  }
                }),
              ),
            )
          }
        }
        if (msg?.type === 'message_recalled') {
          void refreshConversationList()
          void refetchMessages()
        }
        if (msg?.type === 'reaction_update' || msg?.type === 'read_receipt') {
          void refetchMessages()
        }
        if (msg?.type === 'presence_change' || msg?.type === 'group_member_change' || msg?.type === 'group_updated' || msg?.type === 'group_dissolved') {
          void refreshConversationList()
        }
        if (msg?.type === 'typing_indicator' && msg?.data) {
          const convId = Number(msg.data.conversation_id)
          const userId = Number(msg.data.user_id)
          if (!convId || !userId || userId === currentUserId) return
          const name = String(msg.data.username || '对方')
          setTypingUsers((prev) => ({ ...prev, [convId]: name }))
          window.setTimeout(() => {
            setTypingUsers((prev) => {
              if (prev[convId] !== name) return prev
              const next = { ...prev }
              delete next[convId]
              return next
            })
          }, 3200)
        }
      },
    })
    socketRef.current = disconnect
    return () => {
      socketRef.current = null
      disconnect()
    }
  }, [currentUserId, refetchMessages, refreshConversationList])

  useEffect(() => {
    // 课程环境下后端可能没有 WebSocket；定时拉取保证会话列表与消息可更新。
    const timer = window.setInterval(() => {
      void refreshConversationList()
      if (selectedId && !aiStreamingRef.current) void refetchMessages()
    }, 5000)
    return () => window.clearInterval(timer)
  }, [selectedId, refetchMessages, refreshConversationList])

  useEffect(() => {
    if (!selectedId || messages.length === 0) return
    const last = [...messages].reverse().find((row) => Number(row?.msg_id) > 0)
    const lastId = Number(last?.msg_id)
    if (!Number.isFinite(lastId) || lastId <= 0) return
    socketRef.current?.send?.({ type: 'msg_ack', conversation_id: Number(selectedId), msg_id: lastId })
  }, [messages, selectedId])

  const onReplyToMessage = useCallback((row) => {
    setReplyTargetRow(row)
  }, [])

  const onDeleteMessage = useCallback(
    async (row) => {
      const mid = row.msg_id
      const msgId = typeof mid === 'number' ? mid : Number(mid)
      if (selectedId == null || !Number.isFinite(msgId)) return
      try {
        await deleteMessage(selectedId, msgId)
        await refetchMessages()
        await refreshConversationList()
      } catch (e) {
        setSendHint(userFacingError(e, '删除失败'))
        window.setTimeout(() => setSendHint(''), 2600)
      }
    },
    [selectedId, refetchMessages, refreshConversationList],
  )

  const currentReplyToMsgId = useCallback(() => {
    const replyMid =
      replyTargetRow &&
      replyTargetRow.msg_id != null &&
      (typeof replyTargetRow.msg_id === 'number'
        ? replyTargetRow.msg_id
        : Number(replyTargetRow.msg_id))
    return replyMid != null && Number.isFinite(Number(replyMid)) && Number(replyMid) > 0 ? Number(replyMid) : null
  }, [replyTargetRow])

  const sendStructuredMessage = useCallback(
    async ({ type, content, clearDraft = false }) => {
      if (!selectedId || sending) return
      setSendHint('')
      setSendError('')
      setSending(true)
      try {
        const sent = await sendMessage(selectedId, {
          type,
          content,
          replyToMsgId: currentReplyToMsgId(),
          clientMsgId:
            typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
              ? crypto.randomUUID()
              : null,
        })
        if (sent && typeof sent === 'object') {
          window.dispatchEvent(new CustomEvent(CHAT_EVENT_NEW_MESSAGE, { detail: sent }))
          window.dispatchEvent(new CustomEvent(CHAT_EVENT_NEW_MESSAGE_LEGACY, { detail: sent }))
        }
        if (clearDraft) setDraft('')
        setReplyTargetRow(null)
        await refetchMessages()
        await refreshConversationList()
      } catch (e) {
        setSendError(userFacingError(e, '发送失败'))
      } finally {
        setSending(false)
      }
    },
    [currentReplyToMsgId, refetchMessages, refreshConversationList, selectedId, sending],
  )

  const onPickFile = useCallback(
    async (file) => {
      if (!file || !selectedId) return
      setFileUploading(true)
      setSendHint('')
      try {
        const uploaded = await uploadFile(file, 'message')
        const mime = String(uploaded?.mime_type || file.type || '')
        const url = uploaded?.url || uploaded?.file_url || uploaded?.download_url
        if (!url) throw new Error('上传接口未返回文件 URL')
        let type = 'file'
        if (mime.startsWith('image/')) type = 'image'
        else if (mime.startsWith('video/')) type = 'video'
        else if (mime.startsWith('audio/')) type = 'audio'
        const content = {
          file_id: uploaded?.file_id,
          url,
          thumbnail_url: uploaded?.thumbnail_url,
          filename: uploaded?.filename || file.name,
          size: uploaded?.size ?? file.size,
          mime_type: mime,
          width: uploaded?.width,
          height: uploaded?.height,
          duration: uploaded?.duration,
        }
        await sendStructuredMessage({ type, content })
      } catch (e) {
        setSendError(userFacingError(e, '上传发送失败'))
      } finally {
        setFileUploading(false)
        if (fileInputRef.current) fileInputRef.current.value = ''
      }
    },
    [selectedId, sendStructuredMessage],
  )

  const onSendCode = useCallback(async () => {
    const code = draft.replace(/\s+$/g, '')
    if (!code.trim()) {
      setSendHint('请先在输入框写入代码')
      window.setTimeout(() => setSendHint(''), 2200)
      return
    }
    await sendStructuredMessage({
      type: 'code',
      content: { language: codeLanguage || 'text', code },
      clearDraft: true,
    })
    setCodeMode(false)
  }, [codeLanguage, draft, sendStructuredMessage])

  const loadContactFriendsIfNeeded = useCallback(async () => {
    setContactPickerError('')
    if (contactFriends.length > 0) return
    setContactPickerLoading(true)
    try {
      const data = await listFriends({ page: 1, pageSize: 100 })
      setContactFriends(Array.isArray(data?.results) ? data.results : [])
    } catch (e) {
      setContactPickerError(userFacingError(e, '加载好友失败'))
    } finally {
      setContactPickerLoading(false)
    }
  }, [contactFriends.length])

  const openContactCardPicker = useCallback(async () => {
    if (!selectedId) return
    setContactPickerOpen(true)
    await loadContactFriendsIfNeeded()
  }, [loadContactFriendsIfNeeded, selectedId])

  const onSendContactCard = useCallback(async (friend) => {
    const id = Number(friend?.user_id)
    if (!Number.isFinite(id) || id <= 0) return
    await sendStructuredMessage({
      type: 'contact_card',
      content: {
        user_id: id,
        username: friend?.remark || friend?.username || `用户 ${id}`,
        avatar: friend?.avatar || null,
      },
    })
    setContactPickerOpen(false)
    setContactQuery('')
  }, [sendStructuredMessage])

  const openMentionPicker = useCallback(async () => {
    if (!selectedId || selectedConv?.type !== 'group') return
    setMentionPickerOpen(true)
    setMentionError('')
    if (mentionMembers.length > 0) return
    setMentionLoading(true)
    try {
      const rows = await getGroupMembers(selectedId)
      setMentionMembers(rows.filter((m) => Number(m?.id) !== Number(currentUserId)))
    } catch (e) {
      setMentionError(userFacingError(e, '加载群成员失败'))
    } finally {
      setMentionLoading(false)
    }
  }, [currentUserId, mentionMembers.length, selectedConv?.type, selectedId])

  const onMentionMember = useCallback((member) => {
    const userId = Number(member?.id)
    if (!Number.isFinite(userId) || userId <= 0) return
    const name = String(member?.name || member?.username || `用户${userId}`).trim()
    setMentionUserIds((prev) => (prev.includes(userId) ? prev : [...prev, userId]))
    const nextDraft = draft.trim() ? `${draft} @${name} ` : `@${name} `
    setDraft(nextDraft)
    setMentionPickerOpen(false)
    requestAnimationFrame(() => draftInputRef.current?.focus())
  }, [draft])

  const onRecallMessage = useCallback(
    async (row) => {
      const msgId = Number(row?.msg_id)
      if (!selectedId || !Number.isFinite(msgId) || msgId <= 0) return
      try {
        await recallMessage(selectedId, msgId)
        await refetchMessages()
        await refreshConversationList()
      } catch (e) {
        setSendHint(userFacingError(e, '撤回失败'))
        window.setTimeout(() => setSendHint(''), 2600)
      }
    },
    [selectedId, refetchMessages, refreshConversationList],
  )

  const onForwardMessage = useCallback(
    async (row) => {
      const msgId = Number(row?.msg_id)
      if (!selectedId || !Number.isFinite(msgId) || msgId <= 0) return
      setForwardTargetRow(row)
      setForwardMode('individual')
      setForwardQuery('')
      setForwardPickerOpen(true)
      await loadContactFriendsIfNeeded()
    },
    [loadContactFriendsIfNeeded, selectedId],
  )

  const submitForwardTarget = useCallback(
    async (target) => {
      const msgId = Number(forwardTargetRow?.msg_id)
      if (!selectedId || !Number.isFinite(msgId) || msgId <= 0 || !target) return
      setForwardSending(true)
      setSendHint('')
      try {
        let targetConvId = Number(target.conversationId)
        if (target.kind === 'friend') {
          const data = await createPrivateConversation(Number(target.userId))
          targetConvId = Number(data?.conversation_id)
        }
        if (!Number.isFinite(targetConvId) || targetConvId <= 0) throw new Error('未找到可转发的会话')
        await forwardMessages({
          mode: forwardMode,
          sourceConvId: selectedId,
          msgIds: [msgId],
          targetConvIds: [targetConvId],
        })
        await refreshConversationList()
        setForwardPickerOpen(false)
        setForwardTargetRow(null)
        setSendHint('已转发')
        window.setTimeout(() => setSendHint(''), 1800)
      } catch (e) {
        setSendHint(userFacingError(e, '转发失败'))
        window.setTimeout(() => setSendHint(''), 2600)
      } finally {
        setForwardSending(false)
      }
    },
    [forwardMode, forwardTargetRow, refreshConversationList, selectedId],
  )

  const onBookmarkMessage = useCallback(
    async (row) => {
      const msgId = Number(row?.msg_id)
      if (!selectedId || !Number.isFinite(msgId) || msgId <= 0) return
      setTodoTargetRow(row)
      setTodoNote('')
      setTodoDialogOpen(true)
    },
    [selectedId],
  )

  const submitTodoDialog = useCallback(
    async () => {
      const msgId = Number(todoTargetRow?.msg_id)
      if (!selectedId || !Number.isFinite(msgId) || msgId <= 0) return
      setTodoSaving(true)
      setSendHint('')
      try {
        await addBookmark({ conversationId: selectedId, msgId, note: todoNote.trim() })
        setTodoDialogOpen(false)
        setTodoTargetRow(null)
        setTodoNote('')
        setSendHint('已加入待办')
        window.setTimeout(() => setSendHint(''), 1800)
      } catch (e) {
        setSendHint(userFacingError(e, '加入待办失败'))
        window.setTimeout(() => setSendHint(''), 2600)
      } finally {
        setTodoSaving(false)
      }
    },
    [selectedId, todoNote, todoTargetRow],
  )

  const onCalendarInviteAction = useCallback(
    async (participantId, action) => {
      const pid = Number(participantId)
      if (!Number.isFinite(pid) || pid <= 0) return
      try {
        await respondCalendarInvitation(pid, action)
        await refetchMessages()
        await refreshConversationList()
        setSendHint(action === 'accept' ? '已同意日程邀请' : '已拒绝日程邀请')
        window.setTimeout(() => setSendHint(''), 1800)
      } catch (e) {
        setSendHint(userFacingError(e, '处理日程邀请失败'))
        window.setTimeout(() => setSendHint(''), 2600)
      }
    },
    [refetchMessages, refreshConversationList],
  )

  const onContactCardOpen = useCallback(async (content) => {
    const userId = Number(content?.user_id)
    if (!Number.isFinite(userId) || userId <= 0) return
    setContactCardOpen(true)
    setContactCardLoading(true)
    setContactCardError('')
    setContactCardProfile({
      user_id: userId,
      username: content?.username || `用户 ${userId}`,
      avatar: content?.avatar || null,
    })
    try {
      const data = await getUser(userId)
      setContactCardProfile(data)
    } catch (e) {
      setContactCardError(userFacingError(e, '加载名片资料失败'))
    } finally {
      setContactCardLoading(false)
    }
  }, [])

  const onRequestContactCardFriend = useCallback(async () => {
    const userId = Number(contactCardProfile?.user_id)
    if (!Number.isFinite(userId) || userId <= 0 || userId === currentUserId || contactCardProfile?.is_friend) return
    setContactCardRequesting(true)
    setContactCardError('')
    try {
      await sendFriendRequest({ targetUserId: userId, source: 'contact_card', message: '你好，想加你为好友' })
      setContactCardProfile((prev) => (prev ? { ...prev, request_sent: true } : prev))
      setSendHint('好友申请已发送')
      window.setTimeout(() => setSendHint(''), 1800)
    } catch (e) {
      setContactCardError(userFacingError(e, '发送好友申请失败'))
    } finally {
      setContactCardRequesting(false)
    }
  }, [contactCardProfile, currentUserId])

  const onCopyImageMessage = useCallback(async (row) => {
    const content = row?.content && typeof row.content === 'object' ? row.content : {}
    const url = absoluteContentUrl(messageContentUrl(content))
    if (!url) return
    setSendHint('')
    try {
      const res = await fetch(url, { credentials: 'include' })
      if (!res.ok) throw new Error('图片读取失败')
      const blob = await res.blob()
      await copyImageBlobToClipboard(blob)
      setSendHint('图片已复制到剪贴板')
      window.setTimeout(() => setSendHint(''), 1800)
    } catch (e) {
      setSendHint(userFacingError(e, '复制图片失败'))
      window.setTimeout(() => setSendHint(''), 2600)
    }
  }, [])

  const onReactMessage = useCallback(
    async (row, emoji, reactedByMe = false) => {
      const msgId = Number(row?.msg_id)
      if (!selectedId || !Number.isFinite(msgId) || msgId <= 0) return
      try {
        if (reactedByMe) await removeReaction(selectedId, msgId, emoji)
        else await addReaction(selectedId, msgId, emoji)
        await refetchMessages()
      } catch (e) {
        setSendHint(userFacingError(e, '表情回应失败'))
        window.setTimeout(() => setSendHint(''), 2400)
      }
    },
    [selectedId, refetchMessages],
  )

  const onReadStatus = useCallback(
    async (row) => {
      const msgId = Number(row?.msg_id)
      if (!selectedId || !Number.isFinite(msgId) || msgId <= 0) return
      try {
        const data = await getReadStatus(selectedId, msgId)
        const text =
          data?.peer_is_read != null
            ? `对方${data.peer_is_read ? '已读' : '未读'}`
            : `已读 ${data?.read_count ?? 0}，未读 ${data?.unread_count ?? 0}`
        window.alert(text)
      } catch (e) {
        setSendHint(userFacingError(e, '读取已读状态失败'))
        window.setTimeout(() => setSendHint(''), 2400)
      }
    },
    [selectedId],
  )

  const handleSend = async () => {
    const raw = draft
    const text = typeof raw === 'string' ? raw.trim() : ''
    setSendHint('')

    if (!selectedId || sending) return
    if (codeMode) {
      await onSendCode()
      return
    }

    /** 空消息拦截：仅有空格/换行不发 */
    if (!text) {
      if (typeof raw === 'string' && raw.length > 0) {
        setSendHint('不能发送空白消息')
        window.setTimeout(() => setSendHint(''), 2200)
      }
      return
    }

    if (currentUserId == null) {
      setSendError('正在获取登录信息，请稍后重试')
      return
    }

    if (selectedConv?.type === 'ai') {
      setSendError('')
      setSending(true)
      const aiClientMsgId = `ai-stream-${Date.now()}`
      const aiUserClientMsgId = `ai-user-${Date.now()}`
      let aiText = ''
      const localUser = buildOptimisticTextMessage({
        clientMsgId: aiUserClientMsgId,
        text,
        userId: currentUserId,
        username: meUsername || '我',
        avatar: meAvatar,
        replyTarget: null,
      })
      const updateAiTail = (patch) => {
        setOptimisticTail((prev) => {
          const rows = Array.isArray(prev) ? prev : prev ? [prev] : []
          return rows.map((row) => (
            row?.client_msg_id === aiClientMsgId
              ? { ...row, ...patch, content: { ...(row.content || {}), ...(patch.content || {}) } }
              : row
          ))
        })
      }
      setOptimisticTail([
        localUser,
        {
          client_msg_id: aiClientMsgId,
          msg_id: null,
          sender: { user_id: 0, username: 'AI 助手', avatar: null },
          type: 'text',
          content: { text: '' },
          is_recalled: false,
          reactions: [],
          reply_to: null,
          reply_count: 0,
          created_at: new Date().toISOString(),
          send_status: 'pending',
        },
      ])
      try {
        aiStreamingRef.current = true
        setDraft('')
        setReplyTargetRow(null)
        await sendAIMessageStream(selectedId, text, {
          onStart: (payload) => {
            setOptimisticTail((prev) => {
              const rows = Array.isArray(prev) ? prev : prev ? [prev] : []
              return rows.map((row) => {
                if (row?.client_msg_id === aiUserClientMsgId && payload?.user_msg_id) {
                  return { ...row, msg_id: payload.user_msg_id, send_status: 'sent' }
                }
                if (row?.client_msg_id === aiClientMsgId && payload?.msg_id) {
                  return { ...row, msg_id: payload.msg_id }
                }
                return row
              })
            })
          },
          onDelta: (delta) => {
            aiText += delta
            updateAiTail({ content: { text: aiText } })
          },
          onDone: (payload) => {
            aiText = String(payload?.full_content || aiText)
            updateAiTail({ content: { text: aiText }, send_status: 'sent' })
          },
        })
        await refetchMessages()
        await refreshConversationList()
        setOptimisticTail(null)
      } catch (e) {
        updateAiTail({ send_status: 'failed' })
        setSendError(userFacingError(e, 'AI 回复失败'))
      } finally {
        aiStreamingRef.current = false
        setSending(false)
      }
      return
    }

    const clientMsgId =
      typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : `local-${Date.now()}`

    const replyToMsgId = currentReplyToMsgId()

    const optimistic = buildOptimisticTextMessage({
      clientMsgId,
      text,
      userId: currentUserId,
      username: meUsername || '我',
      avatar: meAvatar,
      replyTarget: replyToMsgId != null ? replyTargetRow : undefined,
    })

    setSendError('')
    setSending(true)
    setOptimisticTail(optimistic)
    ownClientMsgIdsRef.current.add(clientMsgId)

    try {
      const apiOpts =
        typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
          ? { clientMsgId: /** @type {string} */ (clientMsgId) }
          : {}
      const sent = await sendTextMessage(selectedId, text, {
        ...apiOpts,
        ...(replyToMsgId != null ? { replyToMsgId } : {}),
        mentions: selectedConv?.type === 'group' ? mentionUserIds : [],
      })
      if (sent && typeof sent === 'object') {
        window.dispatchEvent(new CustomEvent(CHAT_EVENT_NEW_MESSAGE, { detail: sent }))
        window.dispatchEvent(new CustomEvent(CHAT_EVENT_NEW_MESSAGE_LEGACY, { detail: sent }))
      }
      setDraft('')
      setMentionUserIds([])
      setReplyTargetRow(null)
      /** 发送成功：短暂显示「已送达」，再拉取服务端时间线 */
      setOptimisticTail((prev) =>
        prev && typeof prev === 'object' ? { ...prev, send_status: 'sent' } : prev,
      )
      await refetchMessages()
      await refreshConversationList()
      setOptimisticTail(null)
    } catch (e) {
      ownClientMsgIdsRef.current.delete(clientMsgId)
      setOptimisticTail((prev) =>
        prev && typeof prev === 'object' ? { ...prev, send_status: 'failed' } : prev,
      )
      setSendError(userFacingError(e, '发送失败'))
    } finally {
      setSending(false)
      requestAnimationFrame(() => {
        draftInputRef.current?.focus()
      })
    }
  }

  const onRetryFailed = useCallback((row) => {
    const t =
      getMessagePlainText(row.content, typeof row.type === 'string' ? row.type : 'text') ||
      summarizeMessageContent(typeof row.type === 'string' ? row.type : 'text', row.content)
    if (!t) return
    setDraft(t)
    setOptimisticTail(null)
    setSendError('')
    setSendHint('')
  }, [])

  const onDraftKeyDown = (e) => {
    /** 输入法组字期间不按 Enter 发送 */
    if (e.nativeEvent?.isComposing || e.key === 'Process') return
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void handleSend()
    }
  }

  const onDraftPaste = (e) => {
    if (!selectedId || sending) return
    const items = Array.from(e.clipboardData?.items || [])
    const imageItem = items.find((item) => item.kind === 'file' && item.type.startsWith('image/'))
    if (!imageItem) return
    const file = imageItem.getAsFile()
    if (!file) return
    e.preventDefault()
    const named = new File([file], file.name || `pasted-${Date.now()}.png`, { type: file.type || 'image/png' })
    setImageEditorFile(named)
  }

  const onStartInputResize = useCallback((event) => {
    event.preventDefault()
    const startY = event.clientY
    const startHeight = inputHeight
    const onMove = (moveEvent) => {
      const next = clampNumber(startHeight + startY - moveEvent.clientY, 44, 280)
      setInputHeight(next)
    }
    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      window.removeEventListener('pointercancel', onUp)
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    window.addEventListener('pointercancel', onUp)
  }, [inputHeight])

  const onDraftChange = (value) => {
    setDraft(value)
    if (!selectedId) return
    const now = Date.now()
    if (now - typingThrottleRef.current < 3000) return
    typingThrottleRef.current = now
    socketRef.current?.send?.({ type: 'typing', conversation_id: Number(selectedId) })
  }

  const inputDisabled = !selectedId || sending
  const sendDisabled = !selectedId || sending || !draft.trim()

  return (
    <div className="workspace">
      <section className="pane pane--list" aria-label="会话列表">
        <div className="pane__search">
          <div className="pane__searchRow" style={{ justifyContent: 'space-between' }}>
            <button
              type="button"
              className="listFilters__ghostBtn"
              onClick={() => void onOpenAIConversation()}
            >
              AI助手
            </button>
            <button
              type="button"
              className="listFilters__ghostBtn"
              onClick={() => {
                setSearchOpen((prev) => {
                  const next = !prev
                  if (!next) setConvSearch('')
                  return next
                })
              }}
            >
              {searchOpen ? '关闭搜索' : '搜索记录'}
            </button>
            <button
              type="button"
              className="listFilters__ghostBtn"
              onClick={onMarkAllRead}
              disabled={readingAll || conversations.every((c) => (Number(c.unread_count) || 0) === 0)}
            >
              {readingAll ? '处理中…' : '全部已读'}
            </button>
          </div>
          {searchOpen ? (
            <div className="paneSearchResultWrap">
              <input
                className="search-input"
                placeholder="输入关键词后搜索聊天记录…"
                value={convSearch}
                onChange={(e) => setConvSearch(e.target.value)}
                aria-label="搜索聊天记录"
              />
            </div>
          ) : null}
          {searchOpen && convSearch.trim().length >= 1 ? (
            <div className="paneSearchResultWrap">
              {convSearchLoading ? <div className="paneSearchResultHint">搜索中…</div> : null}
              {convSearchError ? <div className="paneSearchResultHint paneSearchResultHint--error">{convSearchError}</div> : null}
              {!convSearchLoading && !convSearchError && convSearchRows.length === 0 ? (
                <div className="paneSearchResultHint">无匹配记录</div>
              ) : null}
              {!convSearchLoading && !convSearchError && convSearchRows.length > 0 ? (
                <ul className="paneSearchResultList">
                  {convSearchRows.map((item) => (
                    <li key={`${item.conversation_id}:${item.msg_id}`}>
                      <button type="button" className="paneSearchResultItem" onClick={() => void onJumpSearchRow(item)}>
                        <div className="paneSearchResultTitle">
                          {(
                            (typeof item.conversation_name === 'string' && item.conversation_name.trim()) ||
                            (typeof item.conversation_title === 'string' && item.conversation_title.trim()) ||
                            (typeof item.group_name === 'string' && item.group_name.trim()) ||
                            (typeof item.peer_name === 'string' && item.peer_name.trim()) ||
                            conversationTitleMap.get(Number(item.conversation_id)) ||
                            `会话 ${item.conversation_id}`
                          )}
                        </div>
                        <div className="paneSearchResultSub">
                          {typeof item?.content?.text === 'string' && item.content.text
                            ? item.content.text
                            : `[${item?.type || '消息'}]`}
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </div>
        {listError ? (
          <div className="pane__outlet" style={{ fontSize: 13, color: 'var(--danger)' }}>
            {listError}
          </div>
        ) : null}
        <div className="list">
          {listLoading ? (
            <div className="emptyState" style={{ border: 'none', margin: 8 }}>
              <div className="emptyState__sub">加载会话中…</div>
            </div>
          ) : conversations.length === 0 ? (
            <div className="emptyState" style={{ border: 'none', margin: 8 }}>
              <div className="emptyState__title">暂无会话</div>
              <div className="emptyState__sub">在通讯录中向好友发消息即可创建私聊。</div>
            </div>
          ) : (
            filteredConversations.map((c) => {
              const id = c.conversation_id
              const active = String(selectedId) === String(id)
              const av = convListAvatar(c)
              const last = c.last_message
              const time = last?.created_at ? formatListTime(last.created_at) : ''
              return (
                <div
                  key={String(id)}
                  className={`list__itemWrap${active ? ' is-active' : ''}`}
                  onContextMenu={(e) => {
                    e.preventDefault()
                    setConvMenu({ x: e.clientX, y: e.clientY, conv: c })
                  }}
                >
                  <button
                    type="button"
                    className="list__item"
                    disabled={Boolean(convBusyMap[id])}
                    onClick={() => void selectConversation(c)}
                  >
                    {av ? (
                      <div
                        className="list__avatar"
                        style={{
                          backgroundImage: `url(${av})`,
                          backgroundSize: 'cover',
                          backgroundPosition: 'center',
                        }}
                      />
                    ) : (
                      <div className="list__avatar" aria-hidden>
                        <svg viewBox="0 0 24 24" className="list__avatarDefaultIcon">
                          <circle cx="12" cy="8" r="4" />
                          <path d="M4 20c0-4 3.6-6 8-6s8 2 8 6" />
                        </svg>
                      </div>
                    )}
                    <div className="list__meta">
                      <div className="list__titleRow">
                        <div className="list__title">
                          {c.is_pinned ? '📌 ' : ''}
                          {c.is_muted ? '🔕 ' : ''}
                          {convTitle(c)}
                        </div>
                        <div className="list__time">{time}</div>
                      </div>
                      <div className="list__sub">{lastPreview(last)}</div>
                    </div>
                    {c.unread_count > 0 ? (
                      <div className={c.is_muted ? 'list__badge list__badge--muted' : 'list__badge'}>
                        {c.unread_count > 99 ? '99+' : c.unread_count}
                      </div>
                    ) : (
                      <span className="list__badgeSpacer" aria-hidden />
                    )}
                  </button>
                  <button
                    type="button"
                    className="list__itemMore"
                    disabled={Boolean(convBusyMap[id])}
                    aria-label="会话操作"
                    onClick={(e) => {
                      e.preventDefault()
                      e.stopPropagation()
                      const r = e.currentTarget.getBoundingClientRect()
                      setConvMenu({ x: r.right, y: r.bottom + 2, conv: c })
                    }}
                  >
                    ⋮
                  </button>
                </div>
              )
            })
          )}
        </div>
      </section>

      <section className="pane pane--chat" aria-label="聊天窗口">
        <header className="chatHeader">
          <div>
            <div className="chatHeader__title">
              {selectedConv ? (
                <>
                  {convListAvatar(selectedConv) && !headerAvatarBroken ? (
                    <img
                      className="chatHeader__avatar"
                      src={convListAvatar(selectedConv)}
                      alt=""
                      onError={() => setHeaderAvatarBroken(true)}
                    />
                  ) : null}
                  {convTitle(selectedConv)}
                </>
              ) : (
                '聊天'
              )}
            </div>
            <div className="chatHeader__sub">
              {selectedConv ? (
                selectedConv.type === 'private' ? (
                  <span className="chatHeader__presence">
                    <span className={`presenceDot ${presenceClass(selectedPeerPresence?.presence)}`} aria-hidden />
                    {getPresenceLabel(selectedPeerPresence?.presence)}
                  </span>
                ) : selectedConv.type === 'group' ? '群聊' : 'AI 会话'
              ) : '请选择左侧会话'}
            </div>
          </div>
          <div className="chatHeader__actions">
            {selectedConv?.type === 'group' && selectedId ? (
              <Link className="chatHeader__groupLink" to={`/groups/${selectedId}?from=chat`}>
                群资料
              </Link>
            ) : null}
            {selectedId ? (
              <button
                type="button"
                className={`chatFilterIconBtn${msgFilterOpen ? ' is-active' : ''}`}
                onClick={() => setMsgFilterOpen((v) => !v)}
                aria-label={msgFilterOpen ? '关闭记录筛选' : '打开记录筛选'}
                title={msgFilterOpen ? '关闭记录筛选' : '筛选聊天记录'}
              >
                <svg
                  aria-hidden="true"
                  viewBox="0 0 24 24"
                  className="chatFilterIconBtn__icon"
                >
                  <circle cx="11" cy="11" r="6" />
                  <line x1="15.5" y1="15.5" x2="20" y2="20" />
                </svg>
              </button>
            ) : null}
          </div>
        </header>

        {selectedId && msgFilterOpen ? (
          <div className="chatToolbar" aria-label="消息筛选">
            <div className="chatToolbar__modes" role="tablist" aria-label="聊天筛选模式">
              <button
                type="button"
                className={`chatToolbar__chip${msgFilterMode === FILTER_MODE_ALL ? ' is-active' : ''}`}
                onClick={() => setMsgFilterMode(FILTER_MODE_ALL)}
              >
                全部
              </button>
              <button
                type="button"
                className={`chatToolbar__chip${msgFilterMode === FILTER_MODE_KEYWORD ? ' is-active' : ''}`}
                onClick={() => setMsgFilterMode(FILTER_MODE_KEYWORD)}
              >
                关键词
              </button>
              <button
                type="button"
                className={`chatToolbar__chip${msgFilterMode === FILTER_MODE_TIME ? ' is-active' : ''}`}
                onClick={() => setMsgFilterMode(FILTER_MODE_TIME)}
              >
                时间
              </button>
              <button
                type="button"
                className={`chatToolbar__chip${msgFilterMode === FILTER_MODE_SENDER ? ' is-active' : ''}`}
                onClick={() => setMsgFilterMode(FILTER_MODE_SENDER)}
              >
                成员
              </button>
            </div>
            {msgFilterMode === FILTER_MODE_ALL || msgFilterMode === FILTER_MODE_KEYWORD ? (
              <input
                className="chatToolbar__keyword"
                placeholder="输入关键词筛选消息"
                value={filterDraft.keyword}
                onChange={(e) => setFilterDraft((p) => ({ ...p, keyword: e.target.value }))}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') setFilterApplied({ ...filterDraft })
                }}
                aria-label="按正文关键词"
              />
            ) : null}
            {msgFilterMode === FILTER_MODE_ALL || msgFilterMode === FILTER_MODE_TIME ? (
              <>
                <label className="chatToolbar__dt">
                  起
                  <input
                    type="text"
                    placeholder="2026年04月29日"
                    value={filterDraft.from}
                    onChange={(e) => setFilterDraft((p) => ({ ...p, from: e.target.value }))}
                    onBlur={(e) => setFilterDraft((p) => ({ ...p, from: normalizeDateDisplay(e.target.value) }))}
                  />
                </label>
                <label className="chatToolbar__dt">
                  止
                  <input
                    type="text"
                    placeholder="2026年04月29日"
                    value={filterDraft.to}
                    onChange={(e) => setFilterDraft((p) => ({ ...p, to: e.target.value }))}
                    onBlur={(e) => setFilterDraft((p) => ({ ...p, to: normalizeDateDisplay(e.target.value) }))}
                  />
                </label>
              </>
            ) : null}
            {msgFilterMode === FILTER_MODE_ALL || msgFilterMode === FILTER_MODE_SENDER ? (
              <select
                className="chatToolbar__select"
                value={filterDraft.senderId}
                onChange={(e) => setFilterDraft((p) => ({ ...p, senderId: e.target.value }))}
                aria-label="按发送者筛选"
              >
                <option value="">全部成员</option>
                {senderPickOptions.map(([id, name]) => (
                  <option key={id} value={String(id)}>
                    {name}
                  </option>
                ))}
              </select>
            ) : null}
            <button
              type="button"
              className="chatToolbar__btn"
              onClick={() => setFilterApplied({ ...filterDraft })}
            >
              应用筛选
            </button>
            <button
              type="button"
              className="chatToolbar__btn chatToolbar__btn--ghost"
              onClick={() => {
                setFilterDraft({ ...EMPTY_MSG_FILTER })
                setFilterApplied({ ...EMPTY_MSG_FILTER })
              }}
            >
              清除
            </button>
          </div>
        ) : null}

        {selectedConv?.type === 'group' && selectedGroupAnnouncement?.content ? (
          <div className="chatBanner" role="status">
            群公告：{selectedGroupAnnouncement.content}
            <span className="chatBanner__meta">
              {selectedGroupAnnouncement.publisherName || '—'} · {formatAnnouncementTime(selectedGroupAnnouncement.createdAt)}
            </span>
          </div>
        ) : null}

        <div
          ref={chatBodyRef}
          className="chatBody"
          data-chat-scroll="1"
          onScroll={onChatScroll}
          aria-live="polite"
        >
          {!selectedId ? (
            <div className="msgEmptySpace" aria-hidden />
          ) : msgLoading ? (
            <div className="emptyState" style={{ borderStyle: 'solid' }}>
              <div className="emptyState__sub">加载消息中…</div>
            </div>
          ) : (
            <>
              {msgError ? (
                <div style={{ padding: '0 0 12px', fontSize: 13, color: 'var(--danger)' }}>{msgError}</div>
              ) : null}
              {loadingOlder ? (
                <div className="chatLoadOlder" role="status">
                  加载更早消息…
                </div>
              ) : null}
              <MessageList
                messages={messagesForList}
                currentUserId={currentUserId}
                currentUserAvatar={meAvatar}
                peerAvatar={selectedConv?.type === 'private' ? convListAvatar(selectedConv) : null}
                hasMoreOlder={hasMoreOlder}
                loadingOlder={loadingOlder}
                onLoadOlder={loadOlder}
                onRetryFailed={onRetryFailed}
                onCopyMessage={onCopyMessage}
                onReplyToMessage={onReplyToMessage}
                onDeleteMessage={onDeleteMessage}
                onRecallMessage={onRecallMessage}
                onForwardMessage={onForwardMessage}
                onBookmarkMessage={onBookmarkMessage}
                onReactMessage={onReactMessage}
                onReadStatus={onReadStatus}
                onCalendarInviteAction={onCalendarInviteAction}
                onContactCardOpen={onContactCardOpen}
                onCopyImageMessage={onCopyImageMessage}
              />
            </>
          )}
        </div>

        <footer className="chatInput" aria-label="消息输入">
          <div className="chatInput__tools">
            <input
              ref={fileInputRef}
              type="file"
              style={{ display: 'none' }}
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) void onPickFile(file)
              }}
            />
            <button
              type="button"
              className="chatToolBtn"
              disabled={!selectedId || fileUploading || sending}
              onClick={() => fileInputRef.current?.click()}
              title="发送文件"
              aria-label="发送文件"
            >
              {fileUploading ? '…' : <ToolIcon type="file" />}
            </button>
            <button
              type="button"
              className={`chatToolBtn${codeMode ? ' is-active' : ''}`}
              disabled={!selectedId || sending}
              onClick={() => {
                setCodeMode((v) => !v)
                requestAnimationFrame(() => draftInputRef.current?.focus())
              }}
              title="发送代码"
              aria-label="发送代码"
            >
              <ToolIcon type="code" />
            </button>
            <button
              type="button"
              className="chatToolBtn"
              disabled={!selectedId || sending}
              onClick={() => void openContactCardPicker()}
              title="发送名片"
              aria-label="发送名片"
            >
              <ToolIcon type="contact" />
            </button>
            {selectedConv?.type === 'group' ? (
              <>
                <button
                  type="button"
                  className="chatToolBtn"
                  disabled={!selectedId || sending}
                  onClick={() => void openMentionPicker()}
                  title="提及群成员"
                  aria-label="提及群成员"
                >
                  <ToolIcon type="mention" />
                </button>
                <button
                  type="button"
                  className="chatToolBtn"
                  disabled={!selectedId || sending}
                  onClick={() => {
                    const prefix = draft.trim() ? `${draft} @AI ` : '@AI '
                    onDraftChange(prefix)
                    requestAnimationFrame(() => draftInputRef.current?.focus())
                  }}
                  title="群聊中提及 AI"
                  aria-label="群聊中提及 AI"
                >
                  <ToolIcon type="ai" />
                </button>
              </>
            ) : null}
          </div>
          <div className="chatInput__field">
            {codeMode ? (
              <div className="chatInput__codeBar">
                <span>代码</span>
                <select value={codeLanguage} onChange={(e) => setCodeLanguage(e.target.value)} disabled={sending}>
                  {CODE_LANGUAGES.map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>
            ) : null}
            {contactPickerOpen ? (
              <div className="mentionPicker contactPicker">
                <div className="mentionPicker__header">
                  <span>选择名片</span>
                  <button type="button" className="mentionPicker__close" onClick={() => setContactPickerOpen(false)} aria-label="关闭">
                    ×
                  </button>
                </div>
                <div className="contactPicker__search">
                  <input
                    value={contactQuery}
                    onChange={(e) => setContactQuery(e.target.value)}
                    placeholder="按用户名或备注搜索"
                  />
                </div>
                {contactPickerLoading ? <div className="mentionPicker__hint">加载中…</div> : null}
                {contactPickerError ? <div className="mentionPicker__hint is-err">{contactPickerError}</div> : null}
                {!contactPickerLoading && contactFriends.length === 0 && !contactPickerError ? (
                  <div className="mentionPicker__hint">暂无好友可发送</div>
                ) : null}
                {contactFriends.length > 0 ? (
                  <div className="mentionPicker__list">
                    {contactFriends
                      .filter((friend) => {
                        const q = contactQuery.trim().toLowerCase()
                        if (!q) return true
                        return String(friend.username || '').toLowerCase().includes(q) || String(friend.remark || '').toLowerCase().includes(q)
                      })
                      .map((friend) => (
                        <button
                          type="button"
                          key={friend.user_id}
                          className="mentionPicker__item"
                          onClick={() => void onSendContactCard(friend)}
                        >
                          <span>{friend.remark || friend.username}</span>
                          <small>@{friend.username}</small>
                        </button>
                      ))}
                  </div>
                ) : null}
              </div>
            ) : null}
            {mentionPickerOpen ? (
              <div className="mentionPicker">
                <div className="mentionPicker__header">
                  <span>选择成员</span>
                  <button type="button" className="mentionPicker__close" onClick={() => setMentionPickerOpen(false)} aria-label="关闭">
                    ×
                  </button>
                </div>
                {mentionLoading ? <div className="mentionPicker__hint">加载中…</div> : null}
                {mentionError ? <div className="mentionPicker__hint is-err">{mentionError}</div> : null}
                {!mentionLoading && mentionMembers.length === 0 && !mentionError ? (
                  <div className="mentionPicker__hint">暂无可提及成员</div>
                ) : null}
                {mentionMembers.length > 0 ? (
                  <div className="mentionPicker__list">
                    {mentionMembers.map((member) => (
                      <button
                        type="button"
                        key={member.id}
                        className="mentionPicker__item"
                        onClick={() => onMentionMember(member)}
                      >
                        <span>{member.name || `用户 ${member.id}`}</span>
                        <small>{member.role === 'owner' ? '群主' : member.role === 'admin' ? '管理员' : '成员'}</small>
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
            {replyTargetRow ? (
              <div className="chatInput__replyBar">
                <span title={replySnippet(replyTargetRow)}>
                  回复：{replySnippet(replyTargetRow)}
                </span>
                <button
                  type="button"
                  className="chatInput__replyDismiss"
                  aria-label="取消回复"
                  onClick={() => setReplyTargetRow(null)}
                >
                  ×
                </button>
              </div>
            ) : null}
            <div
              className="chatInput__resizeHandle"
              role="separator"
              aria-orientation="horizontal"
              title="拖拽调整输入框高度"
              onPointerDown={onStartInputResize}
            />
            <textarea
              ref={draftInputRef}
              className="chatInput__box"
              rows={2}
              style={{ height: inputHeight }}
              placeholder={
                selectedId
                  ? codeMode
                    ? '输入代码，选择语言后按 Enter 发送'
                    : '输入消息，Enter 发送 · 支持粘贴图片'
                  : '请先选择左侧会话'
              }
              value={draft}
              disabled={inputDisabled}
              onChange={(e) => onDraftChange(e.target.value)}
              onKeyDown={onDraftKeyDown}
              onPaste={onDraftPaste}
              aria-invalid={sendError ? 'true' : undefined}
            />
            {sendHint ? (
              <div className="chatInput__hint" role="status">
                {sendHint}
              </div>
            ) : null}
            {selectedId && typingUsers[selectedId] ? (
              <div className="chatInput__hint" role="status">
                {typingUsers[selectedId]} 正在输入…
              </div>
            ) : null}
            {sendError ? (
              <div className="chatInput__hint chatInput__hint--err" role="alert">
                {sendError}
              </div>
            ) : null}
          </div>
          <button
            type="button"
            className="sendBtn"
            disabled={sendDisabled}
            aria-busy={sending}
            title={sending ? '发送中…' : '发送'}
            onClick={() => void handleSend()}
          >
            {sending ? '…' : '➤'}
          </button>
        </footer>
      </section>

      {forwardPickerOpen ? (
        <div className="chatOverlay" role="dialog" aria-modal="true" aria-label="转发消息">
          <div className="chatDialog">
            <div className="chatDialog__head">
              <div>
                <div className="chatDialog__title">转发消息</div>
                <div className="chatDialog__sub">选择好友或群聊</div>
              </div>
              <button type="button" className="chatDialog__close" onClick={() => setForwardPickerOpen(false)} aria-label="关闭">
                ×
              </button>
            </div>
            <div className="chatDialog__seg" role="tablist" aria-label="转发模式">
              <button type="button" className={forwardMode === 'individual' ? 'is-active' : ''} onClick={() => setForwardMode('individual')}>
                逐条转发
              </button>
              <button type="button" className={forwardMode === 'merged' ? 'is-active' : ''} onClick={() => setForwardMode('merged')}>
                合并转发
              </button>
            </div>
            <input
              className="chatDialog__input"
              value={forwardQuery}
              onChange={(e) => setForwardQuery(e.target.value)}
              placeholder="搜索好友或群聊"
              autoFocus
            />
            {contactPickerLoading ? <div className="chatDialog__hint">加载通讯录…</div> : null}
            {contactPickerError ? <div className="chatDialog__hint is-err">{contactPickerError}</div> : null}
            <div className="chatDialog__list">
              {forwardTargets.map((target) => {
                const avatarSrc = resolveAvatarSrc(target.avatar)
                return (
                  <button
                    type="button"
                    key={target.id}
                    className="chatDialog__target"
                    disabled={forwardSending}
                    onClick={() => void submitForwardTarget(target)}
                  >
                    <span
                      className="chatDialog__avatar"
                      style={avatarSrc ? { backgroundImage: `url(${avatarSrc})` } : undefined}
                      aria-hidden
                    >
                      {!avatarSrc ? target.title.slice(0, 1).toUpperCase() : null}
                    </span>
                    <span className="chatDialog__targetMain">
                      <span>{target.title}</span>
                      <small>{target.meta}</small>
                    </span>
                  </button>
                )
              })}
              {!contactPickerLoading && forwardTargets.length === 0 ? (
                <div className="chatDialog__hint">没有匹配的联系人或群聊</div>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      {todoDialogOpen ? (
        <div className="chatOverlay" role="dialog" aria-modal="true" aria-label="加入待办">
          <div className="chatDialog chatDialog--compact">
            <div className="chatDialog__head">
              <div>
                <div className="chatDialog__title">加入待办</div>
                <div className="chatDialog__sub">{replySnippet(todoTargetRow)}</div>
              </div>
              <button type="button" className="chatDialog__close" onClick={() => setTodoDialogOpen(false)} aria-label="关闭">
                ×
              </button>
            </div>
            <textarea
              className="chatDialog__textarea"
              value={todoNote}
              onChange={(e) => setTodoNote(e.target.value)}
              placeholder="备注，可留空"
              rows={4}
              autoFocus
            />
            <div className="chatDialog__actions">
              <button type="button" className="wxBtn" onClick={() => setTodoDialogOpen(false)} disabled={todoSaving}>
                取消
              </button>
              <button type="button" className="wxBtn wxBtn--primary" onClick={() => void submitTodoDialog()} disabled={todoSaving}>
                {todoSaving ? '保存中…' : '加入'}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {contactCardOpen ? (
        <div className="chatOverlay" role="dialog" aria-modal="true" aria-label="名片资料">
          <div className="chatDialog chatDialog--compact">
            <div className="chatDialog__head">
              <div>
                <div className="chatDialog__title">名片资料</div>
                <div className="chatDialog__sub">查看资料并发送好友申请</div>
              </div>
              <button type="button" className="chatDialog__close" onClick={() => setContactCardOpen(false)} aria-label="关闭">
                ×
              </button>
            </div>
            <div className="contactCardProfile">
              <span
                className="contactCardProfile__avatar"
                style={resolveAvatarSrc(contactCardProfile?.avatar) ? { backgroundImage: `url(${resolveAvatarSrc(contactCardProfile.avatar)})` } : undefined}
                aria-hidden
              >
                {!resolveAvatarSrc(contactCardProfile?.avatar) ? String(contactCardProfile?.username || '?').slice(0, 1).toUpperCase() : null}
              </span>
              <div className="contactCardProfile__main">
                <div className="contactCardProfile__name">{contactCardProfile?.username || '用户'}</div>
                <div className="contactCardProfile__meta">用户 ID {contactCardProfile?.user_id ?? '-'}</div>
                {contactCardProfile?.remark ? <div className="contactCardProfile__meta">备注：{contactCardProfile.remark}</div> : null}
              </div>
            </div>
            {contactCardLoading ? <div className="chatDialog__hint">加载资料中…</div> : null}
            {contactCardError ? <div className="chatDialog__hint is-err">{contactCardError}</div> : null}
            <div className="chatDialog__actions">
              <button type="button" className="wxBtn" onClick={() => setContactCardOpen(false)}>
                关闭
              </button>
              <button
                type="button"
                className="wxBtn wxBtn--primary"
                disabled={
                  contactCardLoading ||
                  contactCardRequesting ||
                  Number(contactCardProfile?.user_id) === Number(currentUserId) ||
                  Boolean(contactCardProfile?.is_friend) ||
                  Boolean(contactCardProfile?.request_sent)
                }
                onClick={() => void onRequestContactCardFriend()}
              >
                {Number(contactCardProfile?.user_id) === Number(currentUserId)
                  ? '这是你自己'
                  : contactCardProfile?.is_friend
                    ? '已是好友'
                    : contactCardProfile?.request_sent
                      ? '已发送'
                      : contactCardRequesting
                        ? '发送中…'
                        : '加为好友'}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <PopMenu
        open={Boolean(convMenu)}
        anchorX={convMenu?.x ?? 0}
        anchorY={convMenu?.y ?? 0}
        onClose={() => setConvMenu(null)}
      >
        <button
          type="button"
          role="menuitem"
          className="popMenu__item"
          onClick={() => {
            const c = convMenu?.conv
            if (c) void selectConversation(c)
            setConvMenu(null)
          }}
        >
          打开会话
        </button>
        <button
          type="button"
          role="menuitem"
          className="popMenu__item"
          onClick={() => {
            const c = convMenu?.conv
            if (!c) return
            void runConvAction(c, async (id) => {
              const nextPinned = !c.is_pinned
              const data = await updateConversationSettings(id, { is_pinned: nextPinned })
              setConversations((prev) =>
                sortConversationRows(
                  prev.map((x) =>
                    Number(x.conversation_id) === id
                      ? { ...x, is_pinned: data?.is_pinned ?? nextPinned, updated_at: data?.updated_at || x.updated_at }
                      : x,
                  ),
                ),
              )
            })
            setConvMenu(null)
          }}
        >
          {convMenu?.conv?.is_pinned ? '取消置顶' : '置顶会话'}
        </button>
        <button
          type="button"
          role="menuitem"
          className="popMenu__item"
          onClick={() => {
            const c = convMenu?.conv
            if (!c) return
            void runConvAction(c, async (id) => {
              const nextMuted = !c.is_muted
              const data = await updateConversationSettings(id, { is_muted: nextMuted })
              setConversations((prev) =>
                sortConversationRows(
                  prev.map((x) =>
                    Number(x.conversation_id) === id
                      ? { ...x, is_muted: data?.is_muted ?? nextMuted, updated_at: data?.updated_at || x.updated_at }
                      : x,
                  ),
                ),
              )
            })
            setConvMenu(null)
          }}
        >
          {convMenu?.conv?.is_muted ? '关闭免打扰' : '消息免打扰'}
        </button>
        <button
          type="button"
          role="menuitem"
          className="popMenu__item popMenu__item--danger"
          onClick={() => {
            const c = convMenu?.conv
            if (!c) return
            if (!window.confirm('确定删除该会话？仅影响你本地视图。')) return
            void runConvAction(c, async (id) => {
              await deleteConversation(id)
              setConversations((prev) => prev.filter((x) => Number(x.conversation_id) !== id))
              setSelectedId((cur) => (Number(cur) === id ? null : cur))
            })
            setConvMenu(null)
          }}
        >
          删除会话
        </button>
        <button
          type="button"
          role="menuitem"
          className="popMenu__item"
          onClick={async () => {
            const c = convMenu?.conv
            if (!c || typeof c !== 'object') return
            try {
              await navigator.clipboard.writeText(convTitle(c))
            } catch {
              setSendHint('复制失败')
              window.setTimeout(() => setSendHint(''), 2200)
            }
            setConvMenu(null)
          }}
        >
          复制会话名称
        </button>
      </PopMenu>
      <ImageEditorModal
        file={imageEditorFile}
        onCancel={() => setImageEditorFile(null)}
        onSend={async (file) => {
          await onPickFile(file)
          setImageEditorFile(null)
        }}
      />
    </div>
  )
}

function replySnippet(row) {
  if (!row || typeof row !== 'object') return ''
    const type = typeof row.type === 'string' ? row.type : 'text'
    const contentObj = row.content && typeof row.content === 'object' ? row.content : {}
    const t = getMessagePlainText(row.content, type) || summarizeMessageContent(type, contentObj)
  const s = (t || '').trim().slice(0, 48)
  return s || '消息'
}

function formatListTime(iso) {
  try {
    const d = new Date(iso)
    const now = new Date()
    const sameDay =
      d.getFullYear() === now.getFullYear() &&
      d.getMonth() === now.getMonth() &&
      d.getDate() === now.getDate()
    if (sameDay) return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
  } catch {
    return ''
  }
}
