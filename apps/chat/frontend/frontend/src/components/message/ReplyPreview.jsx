import { summarizeMessageContent } from '../../utils/messageContent.js'

/**
 * 输入区上方的「正在回复」预览（B）
 *
 * @param {Object} props
 * @param {import('../../types/chat.js').ApiChatMessage | null} props.target
 * @param {() => void} props.onCancel
 */
export default function ReplyPreview({ target, onCancel }) {
  if (!target) return null
  const type = typeof target.type === 'string' ? target.type : 'text'
  const preview =
    type === 'text' && target.content && typeof target.content.text === 'string'
      ? target.content.text.slice(0, 80)
      : summarizeMessageContent(type, target.content)
  return (
    <div className="replyPreviewBar">
      <div className="replyPreviewBar__main">
        <div className="replyPreviewBar__title">回复消息</div>
        <div className="replyPreviewBar__sub">{preview || '…'}</div>
      </div>
      <button type="button" className="replyPreviewBar__close" aria-label="取消回复" onClick={onCancel}>
        ×
      </button>
    </div>
  )
}
