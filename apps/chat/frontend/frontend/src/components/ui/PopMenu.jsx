import { createPortal } from 'react-dom'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'

const M = 8

/**
 * 固定定位的弹出菜单（用于右键 / 锚点按钮），自动在视口内裁剪位置。
 *
 * @param {{
 *   open: boolean,
 *   anchorX: number,
 *   anchorY: number,
 *   onClose: () => void,
 *   children: import('react').ReactNode,
 * }} props
 */
export default function PopMenu({ open, anchorX, anchorY, onClose, children }) {
  const ref = useRef(/** @type {HTMLDivElement|null} */ (null))
  const vw = typeof window !== 'undefined' ? window.innerWidth : 0
  const vh = typeof window !== 'undefined' ? window.innerHeight : 0
  const left = vw ? Math.min(Math.max(anchorX, M), vw - M) : anchorX
  const top = vh ? Math.min(Math.max(anchorY, M), vh - M) : anchorY
  const transform = `${vw && anchorX > vw / 2 ? 'translateX(-100%)' : ''} ${vh && anchorY > vh / 2 ? 'translateY(-100%)' : ''}`.trim()
  const [position, setPosition] = useState(null)

  useLayoutEffect(() => {
    if (!open || !ref.current) { setPosition(null); return }
    const rect = ref.current.getBoundingClientRect()
    const next = {
      left: Math.max(M, Math.min(anchorX, window.innerWidth - rect.width - M)),
      top: Math.max(M, Math.min(anchorY, window.innerHeight - rect.height - M)),
    }
    setPosition(old => old?.left === next.left && old?.top === next.top ? old : next)
  }, [open, anchorX, anchorY, children])

  useEffect(() => {
    if (!open) return
    const onDocPointer = (/** @type {MouseEvent|PointerEvent} */ e) => {
      const t = /** @type {Node} */ (e.target)
      if (ref.current?.contains(t)) return
      onClose()
    }
    const onEsc = (/** @type {KeyboardEvent} */ e) => {
      if (e.key === 'Escape') onClose()
    }
    // Browsers can dispatch the scroll event from revealing/focusing the
    // trigger after its click. Ignore that already-completed scroll; close
    // only when the underlying page actually moves after opening the menu.
    const scrollPositions = new Map(Array.from(document.querySelectorAll('*'), el =>
      [el, [el.scrollTop, el.scrollLeft]]))
    const onScroll = (e) => {
      if (ref.current?.contains(e.target)) return
      const target = e.target === document ? document.scrollingElement : e.target
      const before = scrollPositions.get(target)
      if (!before || target.scrollTop !== before[0] || target.scrollLeft !== before[1]) onClose()
    }
    document.addEventListener('pointerdown', onDocPointer, true)
    document.addEventListener('keydown', onEsc)
    window.addEventListener('scroll', onScroll, true)
    return () => {
      document.removeEventListener('pointerdown', onDocPointer, true)
      document.removeEventListener('keydown', onEsc)
      window.removeEventListener('scroll', onScroll, true)
    }
  }, [open, onClose])

  if (!open) return null

  return createPortal(
    <div
      ref={ref}
      className="popMenu"
      role="menu"
      style={{
        position: 'fixed',
        left: position?.left ?? left,
        top: position?.top ?? top,
        transform: position ? undefined : transform || undefined,
        maxHeight: 'calc(100vh - 16px)',
        overflowY: 'auto',
        zIndex: 10000,
      }}
    >
      {children}
    </div>,
    document.body,
  )
}
