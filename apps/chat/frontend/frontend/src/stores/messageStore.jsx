import { useCallback, useContext, useMemo, useState } from 'react'
import { ConversationStoreContext } from './conversationStoreContext.js'
import { MessageStoreContext } from './messageStoreContext.js'

/**
 * @typedef {Object} MessageStoreProviderProps
 * @property {React.ReactNode} children
 * @property {(conversationId: string, lastMessage: import('../types/chat.js').LastMessagePreview) => void} [onMessageSent]
 */

/**
 * 消息域状态（B 拥有写权限：按会话的消息列表、回复目标、筛选、加载态）
 * currentConversationId 只读来自会话域。
 */
export function MessageStoreProvider({ children, onMessageSent }) {
  const conversationCtx = useContext(ConversationStoreContext)
  if (!conversationCtx) {
    throw new Error('MessageStoreProvider 必须放在 ConversationStoreProvider 内')
  }
  const { currentConversationId } = conversationCtx

  const [messageListByConversationId, setMessageListByConversationId] = useState(
    /** @type {Record<string, import('../types/chat.js').ApiChatMessage[]>} */ ({}),
  )
  const [replyTarget, setReplyTarget] = useState(/** @type {import('../types/chat.js').ApiChatMessage | null} */ (null))
  const [messageFilter, setMessageFilter] = useState(/** @type {import('../types/chat.js').MessageFilter | null} */ (null))
  const [messageLoading, setMessageLoading] = useState(false)

  const notifyMessageSent = useCallback(
    (/** @type {string} */ conversationId, /** @type {import('../types/chat.js').LastMessagePreview} */ lastMessage) => {
      onMessageSent?.(conversationId, lastMessage)
    },
    [onMessageSent],
  )

  const value = useMemo(
    () => ({
      currentConversationId,
      messageListByConversationId,
      setMessageListByConversationId,
      replyTarget,
      setReplyTarget,
      messageFilter,
      setMessageFilter,
      messageLoading,
      setMessageLoading,
      notifyMessageSent,
    }),
    [
      currentConversationId,
      messageListByConversationId,
      replyTarget,
      messageFilter,
      messageLoading,
      notifyMessageSent,
    ],
  )

  return <MessageStoreContext.Provider value={value}>{children}</MessageStoreContext.Provider>
}
