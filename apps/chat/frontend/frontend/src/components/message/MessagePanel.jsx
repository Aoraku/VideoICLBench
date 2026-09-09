import MessageList from './MessageList.jsx'
import MessageInput from './MessageInput.jsx'
import MessageActionMenu from './MessageActionMenu.jsx'
import MessageRepliesSheet from './MessageRepliesSheet.jsx'
import RecordFilterBar from './RecordFilterBar.jsx'
import ReplyPreview from './ReplyPreview.jsx'
import { useConversationMessages } from '../../hooks/useConversationMessages.js'

/**
 * 右侧消息面板容器（B）
 */
export default function MessagePanel() {
  const {
    currentConversationId,
    messages,
    messageLoading,
    toast,
    loadingOlder,
    hasOlder,
    sendText,
    retryMessage,
    deleteMessage,
    loadOlder,
    applyFilter,
    clearFilter,
    menu,
    setMenu,
    closeMenu,
    repliesSheet,
    openReplies,
    closeReplies,
    replyTarget,
    setReplyTarget,
  } = useConversationMessages()

  const menuItems = menu.target
    ? [
        { key: 'reply', label: '回复', onClick: () => setReplyTarget(menu.target) },
        {
          key: 'del',
          label: '删除（仅自己不可见）',
          danger: true,
          onClick: () => deleteMessage(menu.target.msg_id),
        },
      ]
    : []

  return (
    <section className="pane pane--chat" aria-label="聊天窗口">
      <header className="chatHeader">
        <div>
          <div className="chatHeader__title">{currentConversationId || '未选择会话'}</div>
          <div className="chatHeader__sub">消息面板（B）</div>
        </div>
        <div className="chatHeader__actions" aria-label="actions">
          <RecordFilterBar onApply={applyFilter} onReset={clearFilter} />
        </div>
      </header>

      {toast ? <div className="chatToast">{toast}</div> : null}
      <ReplyPreview target={replyTarget} onCancel={() => setReplyTarget(null)} />
      <MessageList
        currentConversationId={currentConversationId}
        messages={messages}
        messageLoading={messageLoading}
        loadingOlder={loadingOlder}
        hasOlder={hasOlder}
        onLoadOlder={loadOlder}
        onReply={(m) => setReplyTarget(m)}
        onDelete={(m) => deleteMessage(m.msg_id)}
        onJumpToReplied={(m) => {
          const targetId = m?.reply_to?.msg_id
          if (targetId != null) openReplies(Number(targetId))
        }}
        onContextMenu={(m, e) => {
          setMenu({ open: true, x: e.clientX, y: e.clientY, target: m })
        }}
        onRetry={retryMessage}
      />
      <MessageInput currentConversationId={currentConversationId} onSend={sendText} />
      <MessageActionMenu
        open={menu.open}
        x={menu.x}
        y={menu.y}
        items={menuItems}
        onClose={closeMenu}
      />
      {currentConversationId ? (
        <MessageRepliesSheet
          open={repliesSheet.open}
          conversationId={currentConversationId}
          anchorMsgId={repliesSheet.anchorMsgId}
          onClose={closeReplies}
        />
      ) : null}
    </section>
  )
}
