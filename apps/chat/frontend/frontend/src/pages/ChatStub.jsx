import ConversationSidebar from '../components/conversation/ConversationSidebar.jsx'
import ConversationUrlSync from '../components/conversation/ConversationUrlSync.jsx'
import { ConversationProvider, useConversationStore } from '../stores/conversationStore.jsx'
import { conversationTitle } from '../utils/conversationDisplay.js'
import { userFacingError } from '../utils/userFacingError.js'

export default function ChatStub() {
  return (
    <ConversationProvider>
      <ConversationUrlSync />
      <ChatWorkspace />
    </ConversationProvider>
  )
}

function ChatWorkspace() {
  const { currentConversation, currentConversationId, setPinned, setMuted } = useConversationStore()
  const title = currentConversation ? conversationTitle(currentConversation) : '聊天'
  const pinned = Boolean(currentConversation?.is_pinned)
  const muted = Boolean(currentConversation?.is_muted)

  const updateCurrentSettings = async (kind) => {
    if (!currentConversationId) return
    try {
      if (kind === 'pin') {
        await setPinned(currentConversationId, !pinned)
      } else {
        await setMuted(currentConversationId, !muted)
      }
    } catch (e) {
      window.alert(userFacingError(e, '更新会话设置失败'))
    }
  }

  return (
    <div className="workspace">
      <section className="pane pane--list" aria-label="会话列表">
        <ConversationSidebar />
      </section>

      <section className="pane pane--chat" aria-label="聊天窗口">
        <header className="chatHeader">
          <div>
            <div className="chatHeader__title">{title}</div>
            <div className="chatHeader__sub">
              {currentConversationId
                ? `会话 ID ${currentConversationId}（消息区由 dev/message 分支接入）`
                : '请从左侧选择一个会话'}
            </div>
          </div>
          {currentConversationId ? (
            <div className="chatHeader__actions" aria-label="会话快捷操作">
              <button
                type="button"
                className={pinned ? 'iconBtn iconBtn--active' : 'iconBtn'}
                onClick={() => updateCurrentSettings('pin')}
                aria-label={pinned ? '取消置顶会话' : '置顶会话'}
                title={pinned ? '取消置顶' : '置顶会话'}
              >
                📌
              </button>
              <button
                type="button"
                className={muted ? 'iconBtn iconBtn--active' : 'iconBtn'}
                onClick={() => updateCurrentSettings('mute')}
                aria-label={muted ? '关闭免打扰' : '消息免打扰'}
                title={muted ? '关闭免打扰' : '消息免打扰'}
              >
                🔕
              </button>
            </div>
          ) : null}
        </header>

        <div className="chatBody chatBody--placeholder">
          {currentConversationId ? (
            <div className="emptyState">
              <div className="emptyState__illu" aria-hidden="true">
                💬
              </div>
              <div className="emptyState__title">消息面板占位</div>
              <div className="emptyState__sub">当前会话已选中，发送与消息列表由队友在 MessagePanel 中实现。</div>
            </div>
          ) : (
            <div className="emptyState">
              <div className="emptyState__illu" aria-hidden="true">
                🤖
              </div>
              <div className="emptyState__title">开始聊天</div>
              <div className="emptyState__sub">从左侧列表选择一个会话，或使用通讯录发起会话。</div>
            </div>
          )}
        </div>

        <footer className="chatInput chatInput--disabled" aria-hidden={!currentConversationId}>
          <div className="chatInput__tools">
            <button type="button" className="toolBtn" disabled aria-label="emoji">
              🙂
            </button>
            <button type="button" className="toolBtn" disabled aria-label="image">
              🖼️
            </button>
            <button type="button" className="toolBtn" disabled aria-label="attach">
              📎
            </button>
          </div>
          <input className="chatInput__box" placeholder="消息输入将由消息模块接入…" disabled />
          <button type="button" className="sendBtn" disabled aria-label="send">
            ➤
          </button>
        </footer>
      </section>
    </div>
  )
}
