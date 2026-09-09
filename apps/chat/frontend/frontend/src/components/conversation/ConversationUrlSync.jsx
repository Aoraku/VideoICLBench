import { useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useConversationStore } from '../../stores/conversationStore.jsx'

/**
 * 将当前会话与 URL 查询参数 `?conv=<conversation_id>` 同步，便于刷新/分享链接。
 */
export default function ConversationUrlSync() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { conversations, loading, currentConversationId, selectConversation } = useConversationStore()

  useEffect(() => {
    if (loading) return
    const raw = searchParams.get('conv')
    const urlId = raw === null || raw === '' ? null : Number(raw)
    if (urlId != null && Number.isNaN(urlId)) {
      setSearchParams(
        (prev) => {
          const p = new URLSearchParams(prev)
          p.delete('conv')
          return p
        },
        { replace: true },
      )
      return
    }
    if (urlId === currentConversationId) return

    if (urlId != null) {
      const conv = conversations.find((c) => c.conversation_id === urlId)
      if (conv) {
        if (currentConversationId !== urlId) {
          selectConversation(urlId, conv.last_message?.msg_id)
        }
        return
      }
      if (conversations.length > 0) {
        setSearchParams(
          (prev) => {
            const p = new URLSearchParams(prev)
            p.delete('conv')
            return p
          },
          { replace: true },
        )
      }
      return
    }
  }, [loading, conversations, searchParams, currentConversationId, selectConversation, setSearchParams])

  useEffect(() => {
    if (loading) return
    const cur = searchParams.get('conv')
    const want = currentConversationId == null ? null : String(currentConversationId)
    if (want === cur || (want === null && (cur === null || cur === ''))) return
    setSearchParams(
      (prev) => {
        const p = new URLSearchParams(prev)
        if (want === null) p.delete('conv')
        else p.set('conv', want)
        return p
      },
      { replace: true },
    )
  }, [currentConversationId, loading, searchParams, setSearchParams])

  return null
}
