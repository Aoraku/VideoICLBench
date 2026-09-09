import { useEffect, useId, useRef, useState } from 'react'
import GroupModalPortal from '../layout/GroupModalPortal.jsx'

/**
 * 群资料等场景：单行文本编辑（挂 body，与群管理其它弹窗一致）。
 *
 * @param {{
 *   open: boolean,
 *   onClose: () => void,
 *   title: string,
 *   hint?: string,
 *   initialValue: string,
 *   maxLength: number,
 *   requireNonEmpty?: boolean,
 *   submitting?: boolean,
 *   serverError?: string,
 *   confirmLabel?: string,
 *   inputPlaceholder?: string,
 *   onConfirm: (trimmed: string) => void | Promise<void>,
 * }} props
 */
export default function GroupStringEditDialog({
  open,
  ...props
}) {
  if (!open) return null
  return <GroupStringEditDialogBody key={String(props.initialValue ?? '')} {...props} />
}

function GroupStringEditDialogBody({
  onClose,
  title,
  hint = '',
  initialValue,
  maxLength,
  requireNonEmpty = true,
  submitting = false,
  serverError = '',
  confirmLabel = '确定',
  inputPlaceholder = '',
  onConfirm,
}) {
  const titleId = useId()
  const [draft, setDraft] = useState(initialValue ?? '')
  const [localError, setLocalError] = useState('')
  const inputRef = useRef(/** @type {HTMLInputElement | null} */ (null))

  useEffect(() => {
    const t = window.setTimeout(() => inputRef.current?.focus(), 0)
    return () => window.clearTimeout(t)
  }, [])

  const mergedError = serverError || localError

  async function handleSubmit() {
    setLocalError('')
    const t = draft.trim()
    if (requireNonEmpty && !t) {
      setLocalError('不能为空')
      return
    }
    if (draft.length > maxLength) {
      setLocalError(`最多 ${maxLength} 个字符`)
      return
    }
    await onConfirm(t)
  }

  function handleKeyDown(e) {
    if (e.key === 'Escape' && !submitting) {
      e.stopPropagation()
      onClose()
    }
    if (e.key === 'Enter' && !e.nativeEvent.isComposing && !submitting) {
      e.preventDefault()
      void handleSubmit()
    }
  }

  return (
    <GroupModalPortal>
      <div className="groupDialogOverlay" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <button
          type="button"
          className="groupDialogOverlay__backdrop"
          aria-label="关闭"
          onClick={() => {
            if (!submitting) onClose()
          }}
        />
        <div className="groupDialog groupDialog--themeChat">
          <div className="groupDialog__head">
            <div className="groupDialog__title" id={titleId}>
              {title}
            </div>
            <button type="button" className="groupDialog__close" onClick={() => !submitting && onClose()} disabled={submitting}>
              ×
            </button>
          </div>
          <div className="groupDialog__body">
            {hint ? <p className="groupStringEditDialog__hint">{hint}</p> : null}
            <input
              ref={inputRef}
              type="text"
              className="groupStringEditDialog__input"
              value={draft}
              maxLength={maxLength}
              placeholder={inputPlaceholder}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={submitting}
              autoComplete="off"
            />
            <div className="groupStringEditDialog__meta">
              <span>{draft.length}</span>
              <span>/</span>
              <span>{maxLength}</span>
            </div>
            {mergedError ? <div className="groupStringEditDialog__err">{mergedError}</div> : null}
            <div className="groupStringEditDialog__actions">
              <button type="button" className="wxBtn" onClick={() => !submitting && onClose()} disabled={submitting}>
                取消
              </button>
              <button type="button" className="wxBtn wxBtn--primary" onClick={() => void handleSubmit()} disabled={submitting}>
                {submitting ? '保存中…' : confirmLabel}
              </button>
            </div>
          </div>
        </div>
      </div>
    </GroupModalPortal>
  )
}
