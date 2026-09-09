import { useEffect, useLayoutEffect, useRef } from 'react'

/**
 * @param {{
 *   open: boolean,
 *   x: number,
 *   y: number,
 *   items: Array<{ key: string, label: string, danger?: boolean, onClick: () => void }>,
 *   onClose: () => void,
 * }} props
 */
export default function MessageActionMenu({ open, x, y, items, onClose }) {
  const ref = useRef(null)

  useLayoutEffect(() => {
    if (!open || !ref.current) return
    const el = ref.current
    const rect = el.getBoundingClientRect()
    const pad = 8
    let nx = x
    let ny = y
    if (nx + rect.width > window.innerWidth - pad) nx = window.innerWidth - rect.width - pad
    if (ny + rect.height > window.innerHeight - pad) ny = window.innerHeight - rect.height - pad
    if (nx < pad) nx = pad
    if (ny < pad) ny = pad
    el.style.left = `${nx}px`
    el.style.top = `${ny}px`
  }, [open, x, y])

  useEffect(() => {
    if (!open) return
    const onMouseDown = (e) => {
      if (ref.current && !ref.current.contains(e.target)) onClose()
    }
    const onKeyDown = (e) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', onMouseDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onMouseDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div ref={ref} className="msgActionMenu" role="menu">
      {items.map((it) => (
        <button
          key={it.key}
          type="button"
          role="menuitem"
          className={`msgActionMenu__item${it.danger ? ' is-danger' : ''}`}
          onClick={() => {
            it.onClick()
            onClose()
          }}
        >
          {it.label}
        </button>
      ))}
    </div>
  )
}
