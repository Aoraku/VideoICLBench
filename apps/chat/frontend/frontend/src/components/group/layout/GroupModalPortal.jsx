import { createPortal } from 'react-dom'

/**
 * 群管理弹窗挂到 body，避免父级 overflow / backdrop-filter 导致错位或遮挡。
 * @param {{ children: import('react').ReactNode }} props
 */
export default function GroupModalPortal({ children }) {
  if (typeof document === 'undefined') return null
  return createPortal(children, document.body)
}
