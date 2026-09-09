import { useCallback, useEffect, useState } from 'react'
import { useGroupInviteActions } from '../../../hooks/group/useGroupInviteActions.js'
import { canReviewInvite } from '../../../utils/groupPermission.js'

/**
 * @param {{
 *   groupId: string,
 *   currentUserRole: import('../../../types/group.js').GroupRole | null,
 *   onChanged?: () => Promise<void> | void,
 * }} props
 */
export default function InviteReviewPanel({ groupId, currentUserRole, onChanged }) {
  const { requests, loadingRequests, actingRequestId, error, clearError, loadPendingRequests, approveRequest, rejectRequest } =
    useGroupInviteActions()

  const canReview = canReviewInvite(currentUserRole)
  const [refreshTick, setRefreshTick] = useState(0)

  const load = useCallback(async () => {
    if (!groupId || !canReview) {
      return
    }
    await loadPendingRequests(groupId)
  }, [groupId, canReview, loadPendingRequests])

  useEffect(() => {
    load()
  }, [load, refreshTick])

  async function handleAction(invitationId, action) {
    if (!groupId || !invitationId || actingRequestId) return
    clearError()
    const ok = action === 'approve' ? await approveRequest(groupId, invitationId) : await rejectRequest(groupId, invitationId)
    if (ok) {
      await load()
      if (typeof onChanged === 'function') await onChanged()
    }
  }

  if (!canReview) return null

  return (
    <section className="groupCard groupInviteReview">
      <div className="groupInviteReview__head">
        <h3 className="groupCard__title">待审核邀请</h3>
        <button
          type="button"
          className="wxBtn"
          onClick={() => setRefreshTick((x) => x + 1)}
          disabled={loadingRequests || Boolean(actingRequestId)}
        >
          {loadingRequests ? '刷新中…' : '刷新'}
        </button>
      </div>

      {requests.length === 0 && !loadingRequests ? <p className="groupMuted">当前没有待审核邀请。</p> : null}
      {loadingRequests ? <p className="groupMuted">加载中…</p> : null}

      {requests.length > 0 ? (
        <ul className="groupRoleManager__list">
          {requests.map((r) => (
            <li key={r.id} className="groupRoleManager__row">
              <div>
                <div className="groupRoleManager__name">{r.inviteeName || `用户 ${r.inviteeId}`}</div>
                <div className="groupRoleManager__sub">邀请人：{r.inviterName || `用户 ${r.inviterId}`}</div>
              </div>
              <div className="groupInviteReview__actions">
                <button
                  type="button"
                  className="wxBtn wxBtn--primary"
                  disabled={Boolean(actingRequestId)}
                  onClick={() => handleAction(r.id, 'approve')}
                >
                  {actingRequestId === r.id ? '处理中…' : '通过'}
                </button>
                <button
                  type="button"
                  className="wxBtn"
                  disabled={Boolean(actingRequestId)}
                  onClick={() => handleAction(r.id, 'reject')}
                >
                  拒绝
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : null}

      {error ? <div className="wxNotice is-err">{error}</div> : null}
    </section>
  )
}
