import { useContext } from 'react'
import { ConversationStoreContext } from '../stores/conversationStoreContext.js'

export function useConversationStore() {
  const ctx = useContext(ConversationStoreContext)
  if (!ctx) {
    throw new Error('useConversationStore 必须在 ConversationStoreProvider 内使用')
  }
  return ctx
}
