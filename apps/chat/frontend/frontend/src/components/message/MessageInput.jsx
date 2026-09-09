import { useState } from 'react'

/**
 * 输入框与发送（B）
 * @param {{ currentConversationId: string | null, onSend: (text: string) => Promise<void> | void }} props
 */
export default function MessageInput({ currentConversationId, onSend }) {
  const [text, setText] = useState('')

  const send = async () => {
    const t = text.trim()
    if (!t || !currentConversationId) return
    setText('')
    await onSend(t)
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void send()
    }
  }

  return (
    <footer className="chatInput">
      <div className="chatInput__tools">
        <button type="button" className="toolBtn" aria-label="emoji" disabled>
          🙂
        </button>
        <button type="button" className="toolBtn" aria-label="image" disabled>
          🖼️
        </button>
        <button type="button" className="toolBtn" aria-label="attach" disabled>
          📎
        </button>
      </div>
      <input
        className="chatInput__box"
        placeholder={currentConversationId ? 'Type a message...' : '先选择会话'}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        disabled={!currentConversationId}
      />
      <button type="button" className="sendBtn" aria-label="send" onClick={send} disabled={!currentConversationId}>
        ➤
      </button>
    </footer>
  )
}
