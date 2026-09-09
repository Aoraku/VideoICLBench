import { useState } from 'react'
import { useGroupAdminActions } from '../../../hooks/group/useGroupAdminActions.js'
import GroupModalPortal from '../layout/GroupModalPortal.jsx'
import { canPublishAnnouncement } from '../../../utils/groupPermission.js'

/**
 * @param {{
 *   groupId: string,
 *   currentUserRole: import('../../../types/group.js').GroupRole | null,
 *   onChanged?: () => Promise<void> | void,
 * }} props
 */
export default function PublishAnnouncementDialog({ groupId, currentUserRole, onChanged }) {
  const { submitting, error, clearError, publishAnnouncement } = useGroupAdminActions()
  const [open, setOpen] = useState(false)
  const [content, setContent] = useState('')
  const [localError, setLocalError] = useState('')

  const canPublish = canPublishAnnouncement(currentUserRole)

  async function handlePublish() {
    if (!groupId || submitting) return
    const text = content.trim()
    if (!text) {
      setLocalError('公告内容不能为空')
      return
    }
    setLocalError('')
    clearError()
    const ok = await publishAnnouncement(groupId, text)
    if (ok) {
      setContent('')
      setOpen(false)
      if (typeof onChanged === 'function') await onChanged()
    }
  }

  return (
    <section className="groupCard groupPublishAnnouncement">
      <h3 className="groupCard__title">群公告</h3>
      {!canPublish ? (
        <p className="groupMuted">仅群主或管理员可发布公告。</p>
      ) : (
        <button
          type="button"
          className="wxBtn wxBtn--primary"
          onClick={() => {
            clearError()
            setLocalError('')
            setOpen(true)
          }}
        >
          发布公告
        </button>
      )}

      {open ? (
        <GroupModalPortal>
        <div className="groupDialogOverlay" role="dialog" aria-modal="true" aria-label="发布公告">
          <button type="button" className="groupDialogOverlay__backdrop" aria-label="关闭" onClick={() => setOpen(false)} />
          <div className="groupDialog">
            <div className="groupDialog__head">
              <div className="groupDialog__title">发布群公告</div>
              <button type="button" className="groupDialog__close" onClick={() => setOpen(false)} disabled={submitting}>
                ×
              </button>
            </div>
            <div className="groupDialog__body">
              <label className="groupPublishAnnouncement__field">
                <span className="groupPublishAnnouncement__label">公告内容</span>
                <textarea
                  className="groupPublishAnnouncement__textarea"
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  maxLength={300}
                  rows={5}
                  placeholder="请输入公告内容（不超过 300 字）"
                />
              </label>
              <div className="groupPublishAnnouncement__meta">{content.trim().length}/300</div>
              {localError ? <div className="wxNotice is-err">{localError}</div> : null}
              {error ? <div className="wxNotice is-err">{error}</div> : null}
              <div className="groupPublishAnnouncement__actions">
                <button type="button" className="wxBtn" onClick={() => setOpen(false)} disabled={submitting}>
                  取消
                </button>
                <button type="button" className="wxBtn wxBtn--primary" onClick={handlePublish} disabled={submitting}>
                  {submitting ? '发布中…' : '确认发布'}
                </button>
              </div>
            </div>
          </div>
        </div>
        </GroupModalPortal>
      ) : null}
    </section>
  )
}
