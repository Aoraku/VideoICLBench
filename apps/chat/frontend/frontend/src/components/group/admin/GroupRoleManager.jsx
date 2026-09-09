import { useMemo, useState } from 'react'
import { useGroupAdminActions } from '../../../hooks/group/useGroupAdminActions.js'
import { canManageRole } from '../../../utils/groupPermission.js'
import SetAdminDialog from './SetAdminDialog.jsx'
import TransferOwnerDialog from './TransferOwnerDialog.jsx'

/**
 * @param {{
 *   groupId: string,
 *   currentUserRole: import('../../../types/group.js').GroupRole | null,
 *   members: import('../../../types/group.js').GroupMember[],
 *   onChanged?: () => Promise<void> | void,
 * }} props
 */
export default function GroupRoleManager({ groupId, currentUserRole, members, onChanged }) {
  const [openSetDialog, setOpenSetDialog] = useState(false)
  const [openUnsetDialog, setOpenUnsetDialog] = useState(false)
  const [openTransferDialog, setOpenTransferDialog] = useState(false)
  const { submitting, error, clearError, setAdmin, unsetAdmin, transferOwner } = useGroupAdminActions()

  const isOwner = canManageRole(currentUserRole)
  const admins = useMemo(() => members.filter((m) => m.role === 'admin'), [members])
  const memberCandidates = useMemo(() => members.filter((m) => m.role === 'member'), [members])
  const transferCandidates = useMemo(() => members.filter((m) => m.role !== 'owner'), [members])

  async function runAction(action) {
    if (!groupId || submitting) return
    const ok = await action()
    if (ok) {
      if (typeof onChanged === 'function') await onChanged()
      setOpenSetDialog(false)
      setOpenUnsetDialog(false)
      setOpenTransferDialog(false)
    }
  }

  return (
    <section className="groupCard groupRoleManager">
      <h3 className="groupCard__title">群主管理</h3>
      {!isOwner ? (
        <p className="groupMuted">仅群主可设置管理员或转让群主。</p>
      ) : (
        <>
          <div className="groupRoleManager__actions">
            <button
              type="button"
              className="wxBtn"
              disabled={memberCandidates.length === 0 || submitting}
              onClick={() => {
                clearError()
                setOpenSetDialog(true)
              }}
            >
              设为管理员
            </button>
            <button
              type="button"
              className="wxBtn"
              disabled={admins.length === 0 || submitting}
              onClick={() => {
                clearError()
                setOpenUnsetDialog(true)
              }}
            >
              取消管理员
            </button>
            <button
              type="button"
              className="wxBtn wxBtn--primary"
              disabled={transferCandidates.length === 0 || submitting}
              onClick={() => {
                clearError()
                setOpenTransferDialog(true)
              }}
            >
              转让群主
            </button>
          </div>

          {error ? <div className="wxNotice is-err">{error}</div> : null}
        </>
      )}

      <SetAdminDialog
        open={openSetDialog}
        mode="set"
        members={memberCandidates}
        submitting={submitting}
        error={error}
        onClose={() => setOpenSetDialog(false)}
        onConfirm={(userId) => runAction(() => setAdmin(groupId, userId))}
      />
      <SetAdminDialog
        open={openUnsetDialog}
        mode="unset"
        members={admins}
        submitting={submitting}
        error={error}
        onClose={() => setOpenUnsetDialog(false)}
        onConfirm={(userId) => runAction(() => unsetAdmin(groupId, userId))}
      />
      <TransferOwnerDialog
        open={openTransferDialog}
        members={transferCandidates}
        submitting={submitting}
        error={error}
        onClose={() => setOpenTransferDialog(false)}
        onConfirm={(userId) => runAction(() => transferOwner(groupId, userId))}
      />
    </section>
  )
}
