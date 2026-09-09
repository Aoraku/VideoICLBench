/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import {
  deleteConversation as deleteConversationApi,
  listConversations,
  markConversationRead,
  updateConversationSettings,
} from '../api/conversations.js'
import { connectChatSocket } from '../services/chatSocket.js'
import {
  CHAT_EVENT_CONVERSATION_REFRESH,
  CHAT_EVENT_NEW_MESSAGE,
  CHAT_EVENT_NEW_MESSAGE_LEGACY,
} from '../constants/chatEvents.js'
import { sortConversations } from '../utils/conversationSort.js'
import { getCurrentUserIdFromToken } from '../utils/sessionUser.js'
import { userFacingError } from '../utils/userFacingError.js'

const ConversationContext = createContext(null)
const LAST_CONVERSATION_KEY = 'chat:last_conversation_id'

function extractSenderId(payload) {
  const raw = payload?.sender?.user_id ?? payload?.sender_id ?? payload?.sender?.id ?? null
  const id = typeof raw === 'number' ? raw : Number(raw)
  return Number.isFinite(id) ? id : null
}

export function ConversationProvider({ children }) {
  const [items, setItems] = useState([])
  const [currentConversationId, setCurrentConversationId] = useState(null)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState('')
  const [busyMap, setBusyMap] = useState({})
  const [hasMore, setHasMore] = useState(false)
  const [nextPage, setNextPage] = useState(1)
  /** WebSocket 是否已连接（用于会话列表旁提示） */
  const [wsConnected, setWsConnected] = useState(false)
  const itemsRef = useRef(items)
  const currentConvRef = useRef(currentConversationId)
  const askedNotificationRef = useRef(false)
  const readAckTimerRef = useRef(null)

  useEffect(() => {
    itemsRef.current = items
  }, [items])
  useEffect(() => {
    currentConvRef.current = currentConversationId
  }, [currentConversationId])
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (currentConversationId == null) {
      localStorage.removeItem(LAST_CONVERSATION_KEY)
      return
    }
    localStorage.setItem(LAST_CONVERSATION_KEY, String(currentConversationId))
  }, [currentConversationId])

  const applySorted = useCallback((list) => {
    setItems(sortConversations(Array.isArray(list) ? list : []))
  }, [])

  const refreshConversations = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await listConversations({ page: 1, pageSize: 30 })
      applySorted(data?.results ?? [])
      const total = Number(data?.total) || 0
      const loaded = Array.isArray(data?.results) ? data.results.length : 0
      setHasMore(loaded < total)
      setNextPage(2)
    } catch (e) {
      setError(userFacingError(e, '加载会话列表失败'))
    } finally {
      setLoading(false)
    }
  }, [applySorted])

  const loadMoreConversations = useCallback(async () => {
    if (loading || loadingMore || !hasMore) return
    setLoadingMore(true)
    try {
      const data = await listConversations({ page: nextPage, pageSize: 30 })
      const incoming = Array.isArray(data?.results) ? data.results : []
      if (incoming.length === 0) {
        setHasMore(false)
        return
      }
      let mergedCount = 0
      setItems((prev) => {
        const map = new Map(prev.map((c) => [c.conversation_id, c]))
        incoming.forEach((c) => map.set(c.conversation_id, c))
        const merged = Array.from(map.values())
        mergedCount = merged.length
        return sortConversations(merged)
      })
      const total = Number(data?.total) || 0
      setHasMore(mergedCount < total)
      setNextPage((p) => p + 1)
    } catch {
      // 加载更多失败不覆盖主错误条
    } finally {
      setLoadingMore(false)
    }
  }, [hasMore, loading, loadingMore, nextPage])

  const markAllAsRead = useCallback(async () => {
    const targets = itemsRef.current.filter((c) => (Number(c.unread_count) || 0) > 0 && c.last_message?.msg_id != null)
    if (targets.length === 0) return { total: 0, success: 0 }

    const results = await Promise.allSettled(
      targets.map((c) => markConversationRead(c.conversation_id, c.last_message.msg_id)),
    )
    const successSet = new Set()
    results.forEach((r, idx) => {
      if (r.status === 'fulfilled') successSet.add(targets[idx].conversation_id)
    })
    if (successSet.size > 0) {
      setItems((prev) =>
        sortConversations(
          prev.map((c) => (successSet.has(c.conversation_id) ? { ...c, unread_count: 0 } : c)),
        ),
      )
    }
    return { total: targets.length, success: successSet.size }
  }, [])

  const setConversationBusy = useCallback((conversationId, busy) => {
    const id = Number(conversationId)
    if (!id) return
    setBusyMap((prev) => {
      const next = { ...prev }
      if (busy) next[id] = true
      else delete next[id]
      return next
    })
  }, [])

  useEffect(() => {
    refreshConversations()
  }, [refreshConversations])

  useEffect(() => {
    if (currentConversationId != null || items.length === 0) return
    if (typeof window === 'undefined') return
    const fromQuery = new URLSearchParams(window.location.search || '').get('conv')
    if (fromQuery) return
    const raw = localStorage.getItem(LAST_CONVERSATION_KEY)
    const lastId = Number(raw)
    if (!lastId) return
    const target = items.find((c) => c.conversation_id === lastId)
    if (!target) return
    setCurrentConversationId(lastId)
  }, [items, currentConversationId])

  useEffect(() => {
    if (currentConversationId == null) return
    const exists = items.some((c) => c.conversation_id === currentConversationId)
    if (!exists) setCurrentConversationId(null)
  }, [items, currentConversationId])

  /**
   * 10.3 new_message：优先增量更新会话行，减少整表重拉。
   * 当消息模块发送成功时，也可通过 window.dispatchEvent(new CustomEvent('chat:new-message', { detail })) 复用该逻辑。
   */
  const applyIncomingMessage = useCallback((payload, increaseUnread = true) => {
    const convId = Number(payload?.conversation_id)
    if (!convId) return
    setItems((prev) =>
      sortConversations(
        prev.map((c) => {
          if (c.conversation_id !== convId) return c
          const currentUnread = Number(c.unread_count) || 0
          const shouldIncrease = increaseUnread && currentConvRef.current !== convId
          return {
            ...c,
            last_message: {
              msg_id: payload?.msg_id,
              sender_id: extractSenderId(payload),
              sender_name: payload?.sender?.username ?? payload?.sender_name,
              type: payload?.type,
              content: payload?.content,
              created_at: payload?.created_at,
            },
            updated_at: payload?.created_at || c.updated_at,
            unread_count: shouldIncrease ? currentUnread + 1 : currentUnread,
          }
        }),
      ),
    )
  }, [])

  const maybeNotifyIncomingMessage = useCallback((payload) => {
    if (typeof window === 'undefined' || !('Notification' in window)) return
    const convId = Number(payload?.conversation_id)
    if (!convId) return

    const currentUserId = getCurrentUserIdFromToken()
    const senderId = Number(payload?.sender?.user_id)
    const fromSelf = currentUserId != null && senderId === currentUserId
    if (fromSelf) return

    const conv = itemsRef.current.find((c) => c.conversation_id === convId)
    const muted = Boolean(conv?.is_muted)
    const mentions = Array.isArray(payload?.mentions) ? payload.mentions : []
    const mentionHit =
      currentUserId != null &&
      mentions.some((m) => {
        if (typeof m === 'number' || typeof m === 'string') return Number(m) === currentUserId
        if (m && typeof m === 'object') return Number(m.user_id) === currentUserId
        return false
      })
    if (muted && !mentionHit) return

    const show = () => {
      const convName =
        conv?.type === 'private'
          ? conv?.peer_user?.remark || conv?.peer_user?.username || '私聊'
          : conv?.name || '群聊'
      const senderName = payload?.sender?.username || '新消息'
      const type = payload?.type
      const body = type === 'text' ? payload?.content?.text || '' : `[${type || '消息'}]`
      const n = new Notification(convName, { body: `${senderName}: ${body}` })
      n.onclick = () => {
        window.focus()
        const lastId = payload?.msg_id
        setCurrentConversationId(convId)
        if (lastId != null) {
          markConversationRead(convId, lastId)
            .then(() => {
              setItems((prev) =>
                sortConversations(
                  prev.map((c) => (c.conversation_id === convId ? { ...c, unread_count: 0 } : c)),
                ),
              )
            })
            .catch(() => {})
        }
        n.close()
      }
    }

    if (Notification.permission === 'granted') {
      show()
      return
    }
    if (Notification.permission === 'default' && !askedNotificationRef.current) {
      askedNotificationRef.current = true
      Notification.requestPermission().then((p) => {
        if (p === 'granted') show()
      })
    }
  }, [])

  const ackConversationReadSoon = useCallback((convId, msgId) => {
    if (!convId || !msgId) return
    clearTimeout(readAckTimerRef.current)
    readAckTimerRef.current = window.setTimeout(() => {
      markConversationRead(convId, msgId)
        .then(() => {
          setItems((prev) =>
            sortConversations(
              prev.map((c) => (c.conversation_id === convId ? { ...c, unread_count: 0 } : c)),
            ),
          )
        })
        .catch(() => {})
    }, 220)
  }, [])

  useEffect(() => {
    const disconnect = connectChatSocket({
      onOpen: () => setWsConnected(true),
      onClose: () => setWsConnected(false),
      onMessage: (msg) => {
        if (msg?.type === 'new_message' && msg?.data) {
          const currentUserId = getCurrentUserIdFromToken()
          const senderId = extractSenderId(msg.data)
          const fromSelf = currentUserId != null && senderId != null && senderId === currentUserId
          const convId = Number(msg.data?.conversation_id)
          const msgId = Number(msg.data?.msg_id)
          applyIncomingMessage(msg.data, !fromSelf)
          maybeNotifyIncomingMessage(msg.data)
          if (!fromSelf && convId && convId === currentConvRef.current && msgId) {
            ackConversationReadSoon(convId, msgId)
          }
          return
        }
        if (msg?.type === 'message_recalled') {
          refreshConversations()
        }
      },
    })
    const onRefresh = () => refreshConversations()
    const onIncoming = (ev) => {
      if (ev?.detail) applyIncomingMessage(ev.detail, false)
    }
    window.addEventListener(CHAT_EVENT_CONVERSATION_REFRESH, onRefresh)
    window.addEventListener(CHAT_EVENT_NEW_MESSAGE, onIncoming)
    window.addEventListener(CHAT_EVENT_NEW_MESSAGE_LEGACY, onIncoming)
    return () => {
      clearTimeout(readAckTimerRef.current)
      disconnect()
      window.removeEventListener(CHAT_EVENT_CONVERSATION_REFRESH, onRefresh)
      window.removeEventListener(CHAT_EVENT_NEW_MESSAGE, onIncoming)
      window.removeEventListener(CHAT_EVENT_NEW_MESSAGE_LEGACY, onIncoming)
    }
  }, [ackConversationReadSoon, applyIncomingMessage, maybeNotifyIncomingMessage, refreshConversations])

  const selectConversation = useCallback(async (conversationId, lastReadMsgId) => {
    const id = Number(conversationId)
    setCurrentConversationId(id)
    const fallbackLastId = items.find((c) => c.conversation_id === id)?.last_message?.msg_id
    const lastId = lastReadMsgId != null ? lastReadMsgId : fallbackLastId
    if (lastId == null) return
    try {
      await markConversationRead(id, lastId)
      setItems((prev) =>
        sortConversations(
          prev.map((c) => (c.conversation_id === id ? { ...c, unread_count: 0 } : c)),
        ),
      )
    } catch {
      // 已读失败不阻塞切换；消息区仍可加载
    }
  }, [items])

  const patchConversation = useCallback((conversationId, partial) => {
    setItems((prev) =>
      sortConversations(
        prev.map((c) => (c.conversation_id === conversationId ? { ...c, ...partial } : c)),
      ),
    )
  }, [])

  const setPinned = useCallback(
    async (conversationId, isPinned) => {
      if (busyMap[conversationId]) return
      setConversationBusy(conversationId, true)
      try {
        const data = await updateConversationSettings(conversationId, { is_pinned: isPinned })
        patchConversation(conversationId, {
          is_pinned: data?.is_pinned ?? isPinned,
          updated_at: data?.updated_at,
        })
      } finally {
        setConversationBusy(conversationId, false)
      }
    },
    [busyMap, patchConversation, setConversationBusy],
  )

  const setMuted = useCallback(
    async (conversationId, isMuted) => {
      if (busyMap[conversationId]) return
      setConversationBusy(conversationId, true)
      try {
        const data = await updateConversationSettings(conversationId, { is_muted: isMuted })
        patchConversation(conversationId, {
          is_muted: data?.is_muted ?? isMuted,
          updated_at: data?.updated_at,
        })
      } finally {
        setConversationBusy(conversationId, false)
      }
    },
    [busyMap, patchConversation, setConversationBusy],
  )

  const removeConversation = useCallback(
    async (conversationId) => {
      if (busyMap[conversationId]) return
      setConversationBusy(conversationId, true)
      const id = Number(conversationId)
      const snapshot = itemsRef.current
      const currentIdx = snapshot.findIndex((c) => c.conversation_id === id)
      const fallbackNext =
        currentIdx >= 0
          ? snapshot[currentIdx + 1] || snapshot[currentIdx - 1] || null
          : null
      try {
        await deleteConversationApi(conversationId)
        setItems((prev) => prev.filter((c) => c.conversation_id !== id))
        setCurrentConversationId((cur) => (cur === id ? (fallbackNext?.conversation_id ?? null) : cur))

        if (currentConvRef.current === id && fallbackNext?.conversation_id && fallbackNext?.last_message?.msg_id != null) {
          markConversationRead(fallbackNext.conversation_id, fallbackNext.last_message.msg_id)
            .then(() => {
              setItems((prev) =>
                sortConversations(
                  prev.map((c) =>
                    c.conversation_id === fallbackNext.conversation_id ? { ...c, unread_count: 0 } : c,
                  ),
                ),
              )
            })
            .catch(() => {})
        }
      } finally {
        setConversationBusy(conversationId, false)
      }
    },
    [busyMap, setConversationBusy],
  )

  const currentConversation = useMemo(
    () => items.find((c) => c.conversation_id === currentConversationId) ?? null,
    [items, currentConversationId],
  )

  const value = useMemo(
    () => ({
      conversations: items,
      currentConversationId,
      currentConversation,
      loading,
      error,
      busyMap,
      wsConnected,
      refreshConversations,
      loadMoreConversations,
      loadingMore,
      hasMore,
      markAllAsRead,
      selectConversation,
      setPinned,
      setMuted,
      removeConversation,
      patchConversation,
      applyIncomingMessage,
      maybeNotifyIncomingMessage,
      /** 供 WebSocket / 队友消息发送后增量更新会话行 */
      setConversationList: applySorted,
    }),
    [
      items,
      currentConversationId,
      currentConversation,
      loading,
      error,
      busyMap,
      wsConnected,
      refreshConversations,
      loadMoreConversations,
      loadingMore,
      hasMore,
      markAllAsRead,
      selectConversation,
      setPinned,
      setMuted,
      removeConversation,
      patchConversation,
      applyIncomingMessage,
      maybeNotifyIncomingMessage,
      applySorted,
    ],
  )

  return <ConversationContext.Provider value={value}>{children}</ConversationContext.Provider>
}

export function useConversationStore() {
  const ctx = useContext(ConversationContext)
  if (!ctx) throw new Error('useConversationStore must be used within ConversationProvider')
  return ctx
}

/** 与消息面板协作时可使用简短别名 */
export const useConversation = useConversationStore
