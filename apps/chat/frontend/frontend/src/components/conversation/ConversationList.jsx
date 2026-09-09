import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { CHAT_EVENT_DRAFT_UPDATED } from '../../constants/chatEvents.js'
import { useConversationStore } from '../../stores/conversationStore.jsx'
import { getConversationDraft } from '../../utils/conversationDraft.js'
import { matchesConversationFilter } from '../../utils/conversationFilter.js'
import ConversationContextMenu from './ConversationContextMenu.jsx'
import ConversationItem from './ConversationItem.jsx'

export default function ConversationList({ filterQuery = '' }) {
  const {
    conversations,
    currentConversationId,
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
  } = useConversationStore()
  const [mode, setMode] = useState('all')
  const [readingAll, setReadingAll] = useState(false)
  const sentinelRef = useRef(null)

  const [draftRevision, setDraftRevision] = useState(0)
  useEffect(() => {
    const bump = () => setDraftRevision((v) => v + 1)
    const onStorage = (ev) => {
      if (ev?.key && !ev.key.startsWith('draft:')) return
      bump()
    }
    window.addEventListener('storage', onStorage)
    window.addEventListener(CHAT_EVENT_DRAFT_UPDATED, bump)
    return () => {
      window.removeEventListener('storage', onStorage)
      window.removeEventListener(CHAT_EVENT_DRAFT_UPDATED, bump)
    }
  }, [])

  const drafts = useMemo(() => {
    if (draftRevision < 0) return new Map()
    const map = new Map()
    conversations.forEach((c) => {
      map.set(c.conversation_id, getConversationDraft(c.conversation_id))
    })
    return map
  }, [conversations, draftRevision])

  const visible = useMemo(() => {
    return conversations
      .filter((c) => matchesConversationFilter(c, filterQuery, drafts.get(c.conversation_id) || ''))
      .filter((c) => {
        if (mode === 'unread') return Number(c.unread_count) > 0
        if (mode === 'pinned') return Boolean(c.is_pinned)
        if (mode === 'muted') return Boolean(c.is_muted)
        return true
      })
  }, [conversations, drafts, filterQuery, mode])

  const counts = useMemo(() => {
    const unread = conversations.reduce((acc, c) => acc + ((Number(c.unread_count) || 0) > 0 ? 1 : 0), 0)
    const pinned = conversations.reduce((acc, c) => acc + (c.is_pinned ? 1 : 0), 0)
    const muted = conversations.reduce((acc, c) => acc + (c.is_muted ? 1 : 0), 0)
    return { all: conversations.length, unread, pinned, muted }
  }, [conversations])

  const [menu, setMenu] = useState(null)

  const onOpenMenu = useCallback((e, conversation) => {
    setMenu({ x: e.clientX, y: e.clientY, conversation })
  }, [])

  const closeMenu = useCallback(() => setMenu(null), [])

  useEffect(() => {
    const node = sentinelRef.current
    if (!node) return
    if (!hasMore) return
    const io = new IntersectionObserver(
      (entries) => {
        const hit = entries.some((e) => e.isIntersecting)
        if (hit) loadMoreConversations()
      },
      { rootMargin: '120px' },
    )
    io.observe(node)
    return () => io.disconnect()
  }, [hasMore, loadMoreConversations])

  const onMarkAllRead = useCallback(async () => {
    setReadingAll(true)
    try {
      await markAllAsRead()
    } finally {
      setReadingAll(false)
    }
  }, [markAllAsRead])

  return (
    <>
      {error ? (
        <div className="pane__banner pane__banner--error" role="alert">
          <span className="pane__bannerText">{error}</span>
          <button type="button" className="pane__bannerBtn" onClick={() => refreshConversations()}>
            重试
          </button>
        </div>
      ) : null}
      <div
        className={wsConnected ? 'pane__wsHint pane__wsHint--ok' : 'pane__wsHint pane__wsHint--bad'}
        role="status"
      >
        {wsConnected ? '实时通道已连接' : '实时通道未连接'}
      </div>
      {loading && conversations.length === 0 ? (
        <div className="pane__hint">加载中…</div>
      ) : null}
      <div className="listFilters" role="tablist" aria-label="会话筛选">
        <button
          type="button"
          className="listFilters__ghostBtn"
          onClick={onMarkAllRead}
          disabled={readingAll || counts.unread === 0}
          title="将当前所有未读会话标记为已读"
        >
          {readingAll ? '处理中…' : '全部已读'}
        </button>
        <button
          type="button"
          className={mode === 'all' ? 'listFilters__chip is-active' : 'listFilters__chip'}
          onClick={() => setMode('all')}
        >
          全部{counts.all ? ` (${counts.all})` : ''}
        </button>
        <button
          type="button"
          className={mode === 'unread' ? 'listFilters__chip is-active' : 'listFilters__chip'}
          onClick={() => setMode('unread')}
        >
          未读{counts.unread ? ` (${counts.unread})` : ''}
        </button>
        <button
          type="button"
          className={mode === 'pinned' ? 'listFilters__chip is-active' : 'listFilters__chip'}
          onClick={() => setMode('pinned')}
        >
          置顶{counts.pinned ? ` (${counts.pinned})` : ''}
        </button>
        <button
          type="button"
          className={mode === 'muted' ? 'listFilters__chip is-active' : 'listFilters__chip'}
          onClick={() => setMode('muted')}
        >
          免打扰{counts.muted ? ` (${counts.muted})` : ''}
        </button>
      </div>
      <div className="list" aria-busy={loading}>
        {conversations.length === 0 && !loading ? (
          <div className="pane__empty">暂无会话</div>
        ) : visible.length === 0 && !loading ? (
          <div className="pane__empty">没有匹配的会话</div>
        ) : (
          visible.map((c) => (
            <ConversationItem
              key={c.conversation_id}
              conversation={c}
              draftText={drafts.get(c.conversation_id) || ''}
              busy={Boolean(busyMap[c.conversation_id])}
              active={c.conversation_id === currentConversationId}
              onSelect={selectConversation}
              onOpenMenu={onOpenMenu}
            />
          ))
        )}
      </div>
      {hasMore ? (
        <div className="listMoreWrap">
          <button
            type="button"
            className="listMoreBtn"
            onClick={() => loadMoreConversations()}
            disabled={loadingMore}
          >
            {loadingMore ? '加载中…' : '加载更多会话'}
          </button>
          <div ref={sentinelRef} className="listMoreSentinel" aria-hidden />
        </div>
      ) : null}

      {menu ? (
        <ConversationContextMenu
          x={menu.x}
          y={menu.y}
          conversation={menu.conversation}
          onClose={closeMenu}
          onPinned={setPinned}
          onMuted={setMuted}
          onDelete={removeConversation}
        />
      ) : null}
    </>
  )
}
