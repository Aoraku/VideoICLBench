import { useNavigate } from 'react-router-dom'
import { useGroupAdminActions } from '../../../hooks/group/useGroupAdminActions.js'
import { canLeaveGroupDirectly } from '../../../utils/groupPermission.js'

/**
 * @param {{
 *   groupId: string,
 *   currentUserRole: import('../../../types/group.js').GroupRole | null,
 * }} props
 */
export default function LeaveGroupButton({ groupId, currentUserRole }) {
  const navigate = useNavigate()
  const { submitting, error, clearError, leaveCurrentGroup } = useGroupAdminActions()

  const canLeave = canLeaveGroupDirectly(currentUserRole)
  const isOwner = currentUserRole === 'owner'

  async function handleLeave() {
    if (!groupId || submitting || !canLeave) return
    const ok = window.confirm('确认退出该群聊？退出后将无法继续接收该群消息。')
    if (!ok) return

    clearError()
    const done = await leaveCurrentGroup(groupId)
    if (done) {
      navigate('/groups')
    }
  }

  return (
    <section className="groupCard groupLeaveGroup">
      <h3 className="groupCard__title">退出群聊</h3>
      {isOwner ? (
        <p className="groupMuted">你当前是群主，请先转让群主后再退出群聊。</p>
      ) : (
        <button type="button" className="wxBtn wxDangerText" disabled={!canLeave || submitting} onClick={handleLeave}>
          {submitting ? '退出中…' : '退出群聊'}
        </button>
      )}
      {error ? <div className="wxNotice is-err">{error}</div> : null}
    </section>
  )
}
