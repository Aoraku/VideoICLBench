import GroupModalPortal from '../layout/GroupModalPortal.jsx'

/**
 * @param {{
 *   open: boolean,
 *   mode: 'set'|'unset',
 *   members: import('../../../types/group.js').GroupMember[],
 *   submitting?: boolean,
 *   error?: string,
 *   onClose: () => void,
 *   onConfirm: (userId: string) => void,
 * }} props
 */
export default function SetAdminDialog({ open, mode, members, submitting = false, error = '', onClose, onConfirm }) {
  if (!open) return null

  const title = mode === 'unset' ? '取消管理员' : '设为管理员'
  const actionLabel = mode === 'unset' ? '取消管理员' : '设为管理员'

  return (
    <GroupModalPortal>
    <div className="groupDialogOverlay" role="dialog" aria-modal="true" aria-label={title}>
      <button type="button" className="groupDialogOverlay__backdrop" aria-label="关闭" onClick={onClose} />
      <div className="groupDialog">
        <div className="groupDialog__head">
          <div className="groupDialog__title">{title}</div>
          <button type="button" className="groupDialog__close" onClick={onClose} disabled={submitting}>
            ×
          </button>
        </div>
        <div className="groupDialog__body">
          {members.length === 0 ? (
            <div className="groupMuted">暂无可操作成员</div>
          ) : (
            <ul className="groupRoleManager__list">
              {members.map((m) => (
                <li key={m.id} className="groupRoleManager__row">
                  <div>
                    <div className="groupRoleManager__name">{m.name}</div>
                    {m.username ? <div className="groupRoleManager__sub">@{m.username}</div> : null}
                  </div>
                  <button type="button" className="wxBtn wxBtn--primary" disabled={submitting} onClick={() => onConfirm(m.id)}>
                    {submitting ? '提交中…' : actionLabel}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {error ? <div className="wxNotice is-err">{error}</div> : null}
        </div>
      </div>
    </div>
    </GroupModalPortal>
  )
}
