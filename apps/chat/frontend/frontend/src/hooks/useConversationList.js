import { useConversationStore } from './useConversationStore.js'

/**
 * 会话列表域 hook（A 实现列表拉取、排序、未读等）
 */
export function useConversationList() {
  const {
    conversationList,
    currentConversationId,
    selectConversation,
    unreadCountMap,
    muteConversationSet,
    pinnedConversationSet,
  } = useConversationStore()

  return {
    conversationList,
    currentConversationId,
    selectConversation,
    unreadCountMap,
    muteConversationSet,
    pinnedConversationSet,
  }
}
