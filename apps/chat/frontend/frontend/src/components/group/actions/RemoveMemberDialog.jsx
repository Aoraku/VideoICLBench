import { useMemo, useState } from 'react'
import { useGroupAdminActions } from '../../../hooks/group/useGroupAdminActions.js'
import { useCurrentUserId } from '../../../hooks/useCurrentUserId.js'
import GroupModalPortal from '../layout/GroupModalPortal.jsx'
import { canRemoveMember } from '../../../utils/groupPermission.js'

/**
 * @param {{
 *   groupId: string,
 *   currentUserRole: import('../../../types/group.js').GroupRole | null,
 *   members: import('../../../types/group.js').GroupMember[],
 *   onChanged?: () => Promise<void> | void,
 * }} props
 */
export default function RemoveMemberDialog({ groupId, currentUserRole, members, onChanged }) {
  const { userId: currentUserId } = useCurrentUserId()
  const { submitting, error, clearError, removeMember } = useGroupAdminActions()
  const [open, setOpen] = useState(false)
  const [submittingId, setSubmittingId] = useState('')

  const removableMembers = useMemo(() => {
    const selfId = currentUserId != null ? String(currentUserId) : ''
    return members.filter((m) => canRemoveMember(currentUserRole, m.role, m.id === selfId))
  }, [members, currentUserRole, currentUserId])

  async function handleRemove(memberId) {
    if (!groupId || !memberId || submittingId) return
    const target = removableMembers.find((m) => m.id === memberId)
    const confirmed = window.confirm(`确认将“${target?.name || '该成员'}”移出群聊吗？`)
    if (!confirmed) return
    setSubmittingId(memberId)
    clearError()
    const ok = await removeMember(groupId, memberId)
    if (ok) {
      if (typeof onChanged === 'function') await onChanged()
      setOpen(false)
    }
    setSubmittingId('')
  }

  return (
    <section className="groupCard groupRemoveMember">
      <h3 className="groupCard__title">成员管理</h3>
      {removableMembers.length === 0 ? (
        <p className="groupMuted">当前身份无可移除成员。</p>
      ) : (
        <button
          type="button"
          className="wxBtn"
          onClick={() => {
            clearError()
            setOpen(true)
          }}
        >
          移除成员
        </button>
      )}

      {open ? (
        <GroupModalPortal>
        <div className="groupDialogOverlay" role="dialog" aria-modal="true" aria-label="移除群成员">
          <button type="button" className="groupDialogOverlay__backdrop" aria-label="关闭" onClick={() => setOpen(false)} />
          <div className="groupDialog">
            <div className="groupDialog__head">
              <div className="groupDialog__title">移除群成员</div>
              <button type="button" className="groupDialog__close" onClick={() => setOpen(false)} disabled={Boolean(submittingId) || submitting}>
                ×
              </button>
            </div>
            <div className="groupDialog__body">
              <ul className="groupRoleManager__list">
                {removableMembers.map((m) => (
                  <li key={m.id} className="groupRoleManager__row">
                    <div>
                      <div className="groupRoleManager__name">{m.name}</div>
                      <div className="groupRoleManager__sub">{m.role === 'admin' ? '管理员' : '普通成员'}</div>
                    </div>
                    <button
                      type="button"
                      className="wxBtn wxDangerText"
                      disabled={Boolean(submittingId) || submitting}
                      onClick={() => handleRemove(m.id)}
                    >
                      {submittingId === m.id ? '移除中…' : '移除'}
                    </button>
                  </li>
                ))}
              </ul>
              {error ? <div className="wxNotice is-err">{error}</div> : null}
            </div>
          </div>
        </div>
        </GroupModalPortal>
      ) : null}
    </section>
  )
}
