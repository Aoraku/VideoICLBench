import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { userFacingError } from '../../utils/userFacingError.js'

/**
 * 4.4 / 4.5：会话列表右键菜单（置顶、免打扰、删除）
 */
export default function ConversationContextMenu({
  x,
  y,
  conversation,
  onClose,
  onPinned,
  onMuted,
  onDelete,
}) {
  const ref = useRef(null)
  const [pos, setPos] = useState({ left: x, top: y })
  const [running, setRunning] = useState(false)

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const pad = 8
    let left = x
    let top = y
    if (left + rect.width > window.innerWidth - pad) left = window.innerWidth - rect.width - pad
    if (top + rect.height > window.innerHeight - pad) top = window.innerHeight - rect.height - pad
    if (left < pad) left = pad
    if (top < pad) top = pad
    setPos({ left, top })
  }, [x, y])

  useEffect(() => {
    const onDoc = (e) => {
      if (ref.current && !ref.current.contains(e.target)) onClose()
    }
    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [onClose])

  if (!conversation) return null

  const id = conversation.conversation_id
  const pinned = Boolean(conversation.is_pinned)
  const muted = Boolean(conversation.is_muted)

  const run = async (fn) => {
    if (running) return
    setRunning(true)
    try {
      await fn()
      onClose()
    } catch (e) {
      window.alert(userFacingError(e, '操作失败'))
    } finally {
      setRunning(false)
    }
  }

  return (
    <div
      ref={ref}
      className="convMenu"
      role="menu"
      style={{ left: pos.left, top: pos.top }}
      onContextMenu={(e) => e.preventDefault()}
    >
      <button
        type="button"
        className="convMenu__item"
        role="menuitem"
        disabled={running}
        onClick={() => run(() => onPinned(id, !pinned))}
      >
        {running ? '处理中…' : pinned ? '取消置顶' : '置顶会话'}
      </button>
      <button
        type="button"
        className="convMenu__item"
        role="menuitem"
        disabled={running}
        onClick={() => run(() => onMuted(id, !muted))}
      >
        {muted ? '关闭免打扰' : '消息免打扰'}
      </button>
      <button
        type="button"
        className="convMenu__item convMenu__item--danger"
        role="menuitem"
        disabled={running}
        onClick={() => {
          if (!window.confirm('确定删除该会话？仅影响你本机的会话视图。')) return
          run(() => onDelete(id))
        }}
      >
        删除会话
      </button>
    </div>
  )
}
