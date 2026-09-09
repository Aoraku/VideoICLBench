import { useContext } from 'react'
import { MessageStoreContext } from '../stores/messageStoreContext.js'

export function useMessageStore() {
  const ctx = useContext(MessageStoreContext)
  if (!ctx) {
    throw new Error('useMessageStore 必须在 MessageStoreProvider 内使用')
  }
  return ctx
}
