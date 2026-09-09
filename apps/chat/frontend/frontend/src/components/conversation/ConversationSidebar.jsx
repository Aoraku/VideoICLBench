import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { searchConversationRecords } from '../../api/conversations.js'
import { CHAT_EVENT_JUMP_TO_MESSAGE } from '../../constants/chatEvents.js'
import { useConversationStore } from '../../stores/conversationStore.jsx'
import { conversationTitle } from '../../utils/conversationDisplay.js'
import { userFacingError } from '../../utils/userFacingError.js'
import ConversationList from './ConversationList.jsx'

/**
 * 会话列表面板（左侧栏）：未读、置顶、免打扰、右键菜单等由子组件与 store 实现。
 */
export default function ConversationSidebar() {
  const [filterQuery, setFilterQuery] = useState('')
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const { conversations, selectConversation } = useConversationStore()

  const conversationMap = useMemo(() => {
    const map = new Map()
    conversations.forEach((c) => map.set(c.conversation_id, c))
    return map
  }, [conversations])

  useEffect(() => {
    const keyword = filterQuery.trim()
    if (keyword.length < 2) {
      setSearchLoading(false)
      setSearchError('')
      setSearchResults([])
      return
    }
    let cancelled = false
    const timer = window.setTimeout(async () => {
      setSearchLoading(true)
      setSearchError('')
      try {
        const data = await searchConversationRecords({ keyword, page: 1, pageSize: 8 })
        if (!cancelled) setSearchResults(Array.isArray(data?.results) ? data.results : [])
      } catch (e) {
        if (!cancelled) {
          setSearchResults([])
          setSearchError(userFacingError(e, '搜索失败'))
        }
      } finally {
        if (!cancelled) setSearchLoading(false)
      }
    }, 260)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [filterQuery])

  const onJumpSearchResult = async (item) => {
    const convId = Number(item?.conversation_id)
    const msgId = Number(item?.msg_id)
    if (!convId) return
    await selectConversation(convId, Number.isFinite(msgId) ? msgId : undefined)
    window.dispatchEvent(new CustomEvent(CHAT_EVENT_JUMP_TO_MESSAGE, { detail: { conversation_id: convId, msg_id: msgId } }))
  }

  return (
    <>
      <div className="pane__search">
        <div className="pane__searchRow">
          <input
            className="search-input"
            value={filterQuery}
            onChange={(e) => setFilterQuery(e.target.value)}
            placeholder="筛选会话…"
            aria-label="筛选会话"
          />
          {filterQuery ? (
            <button
              type="button"
              className="pane__searchClear"
              onClick={() => setFilterQuery('')}
              aria-label="清空会话筛选"
              title="清空筛选"
            >
              ×
            </button>
          ) : null}
          <Link className="pane__searchLink" to="/contacts/search">
            找用户
          </Link>
        </div>
        {filterQuery.trim().length >= 2 ? (
          <div className="paneSearchResultWrap">
            {searchLoading ? <div className="paneSearchResultHint">搜索中…</div> : null}
            {searchError ? <div className="paneSearchResultHint paneSearchResultHint--error">{searchError}</div> : null}
            {!searchLoading && !searchError && searchResults.length === 0 ? (
              <div className="paneSearchResultHint">无匹配记录</div>
            ) : null}
            {!searchLoading && !searchError && searchResults.length > 0 ? (
              <ul className="paneSearchResultList">
                {searchResults.map((item) => {
                  const conv = conversationMap.get(item.conversation_id)
                  const convName = conv ? conversationTitle(conv) : item.conversation_name || `会话 ${item.conversation_id}`
                  const preview = item?.content?.text || `[${item?.type || '消息'}]`
                  return (
                    <li key={`${item.conversation_id}:${item.msg_id}`}>
                      <button type="button" className="paneSearchResultItem" onClick={() => onJumpSearchResult(item)}>
                        <div className="paneSearchResultTitle">{convName}</div>
                        <div className="paneSearchResultSub">{preview}</div>
                      </button>
                    </li>
                  )
                })}
              </ul>
            ) : null}
          </div>
        ) : null}
      </div>
      <div className="pane__scroll">
        <ConversationList filterQuery={filterQuery} />
      </div>
    </>
  )
}
