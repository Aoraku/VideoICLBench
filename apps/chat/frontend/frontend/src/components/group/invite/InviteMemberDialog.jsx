import { useEffect, useMemo, useState } from 'react'
import { listFriends } from '../../../api/friends.js'
import { useGroupInviteActions } from '../../../hooks/group/useGroupInviteActions.js'
import GroupModalPortal from '../layout/GroupModalPortal.jsx'
import { getFriendDisplayName } from '../../../utils/friends.js'
import { userFacingError } from '../../../utils/userFacingError.js'

/**
 * @param {{
 *   groupId: string,
 *   currentUserRole: import('../../../types/group.js').GroupRole | null,
 *   members: import('../../../types/group.js').GroupMember[],
 *   isGroupMember?: boolean,
 * }} props
 */
export default function InviteMemberDialog({ groupId, currentUserRole, members, isGroupMember = false }) {
  const { sendingInviteId, error, clearError, inviteFriend } = useGroupInviteActions()
  const [open, setOpen] = useState(false)
  const [friends, setFriends] = useState([])
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState('')
  const [loadError, setLoadError] = useState('')

  /** 能打开群资料页说明已通过群接口鉴权；角色可能因 id 匹配失败暂为 null，仍应允许普通成员邀请 */
  const canInvite = Boolean(isGroupMember || currentUserRole)

  const invitables = useMemo(() => {
    const memberIds = new Set(members.map((m) => String(m.id)))
    return friends.filter((f) => !memberIds.has(String(f.user_id)))
  }, [friends, members])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setLoadError('')
      clearError()
      try {
        const data = await listFriends({ page: 1, pageSize: 200 })
        const rows = Array.isArray(data?.results) ? data.results : []
        if (!cancelled) setFriends(rows)
      } catch (e) {
        if (!cancelled) setLoadError(userFacingError(e, '加载好友失败'))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [open, clearError])

  async function handleInvite(friendId) {
    if (!groupId || sendingInviteId) return
    clearError()
    setSuccess('')
    const ok = await inviteFriend(groupId, friendId)
    if (ok) {
      setSuccess('邀请已发送，等待群主/管理员审核。')
    }
  }

  return (
    <section className="groupCard groupInviteMember">
      <h3 className="groupCard__title">邀请好友</h3>
      {!canInvite ? (
        <p className="groupMuted">加载群信息后即可邀请好友。</p>
      ) : (
        <button
          type="button"
          className="wxBtn"
          onClick={() => {
            setOpen(true)
            clearError()
            setLoadError('')
            setSuccess('')
          }}
        >
          邀请好友
        </button>
      )}

      {open ? (
        <GroupModalPortal>
        <div className="groupDialogOverlay" role="dialog" aria-modal="true" aria-label="邀请好友加入群聊">
          <button type="button" className="groupDialogOverlay__backdrop" aria-label="关闭" onClick={() => setOpen(false)} />
          <div className="groupDialog">
            <div className="groupDialog__head">
              <div className="groupDialog__title">邀请好友加入群聊</div>
              <button type="button" className="groupDialog__close" onClick={() => setOpen(false)} disabled={Boolean(sendingInviteId)}>
                ×
              </button>
            </div>
            <div className="groupDialog__body">
              {loading ? <div className="groupMuted">加载好友列表中…</div> : null}
              {!loading && invitables.length === 0 ? <div className="groupMuted">暂无可邀请好友。</div> : null}
              {invitables.length > 0 ? (
                <ul className="groupRoleManager__list">
                  {invitables.map((f) => {
                    const fid = String(f.user_id)
                    return (
                      <li key={fid} className="groupRoleManager__row">
                        <div>
                          <div className="groupRoleManager__name">{getFriendDisplayName(f)}</div>
                          <div className="groupRoleManager__sub">@{f.username}</div>
                        </div>
                        <button type="button" className="wxBtn wxBtn--primary" disabled={Boolean(sendingInviteId)} onClick={() => handleInvite(fid)}>
                          {sendingInviteId === fid ? '发送中…' : '发送邀请'}
                        </button>
                      </li>
                    )
                  })}
                </ul>
              ) : null}
              {success ? <div className="wxNotice">{success}</div> : null}
              {loadError ? <div className="wxNotice is-err">{loadError}</div> : null}
              {error ? <div className="wxNotice is-err">{error}</div> : null}
            </div>
          </div>
        </div>
        </GroupModalPortal>
      ) : null}
    </section>
  )
}
