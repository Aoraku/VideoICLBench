import { createPortal } from 'react-dom'
import { useEffect, useRef } from 'react'

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
    document.addEventListener('pointerdown', onDocPointer, true)
    document.addEventListener('keydown', onEsc)
    window.addEventListener('scroll', onClose, true)
    return () => {
      document.removeEventListener('pointerdown', onDocPointer, true)
      document.removeEventListener('keydown', onEsc)
      window.removeEventListener('scroll', onClose, true)
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
        left,
        top,
        transform: transform || undefined,
        zIndex: 10000,
      }}
    >
      {children}
    </div>,
    document.body,
  )
}
