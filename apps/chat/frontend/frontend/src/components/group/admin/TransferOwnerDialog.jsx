import GroupModalPortal from '../layout/GroupModalPortal.jsx'

/**
 * @param {{
 *   open: boolean,
 *   members: import('../../../types/group.js').GroupMember[],
 *   submitting?: boolean,
 *   error?: string,
 *   onClose: () => void,
 *   onConfirm: (userId: string) => void,
 * }} props
 */
export default function TransferOwnerDialog({ open, members, submitting = false, error = '', onClose, onConfirm }) {
  if (!open) return null

  return (
    <GroupModalPortal>
    <div className="groupDialogOverlay" role="dialog" aria-modal="true" aria-label="转让群主">
      <button type="button" className="groupDialogOverlay__backdrop" aria-label="关闭" onClick={onClose} />
      <div className="groupDialog">
        <div className="groupDialog__head">
          <div className="groupDialog__title">转让群主</div>
          <button type="button" className="groupDialog__close" onClick={onClose} disabled={submitting}>
            ×
          </button>
        </div>
        <div className="groupDialog__body">
          <p className="groupMuted">转让后你将不再是群主，请谨慎操作。</p>
          {members.length === 0 ? (
            <div className="groupMuted">暂无可转让对象</div>
          ) : (
            <ul className="groupRoleManager__list">
              {members.map((m) => (
                <li key={m.id} className="groupRoleManager__row">
                  <div>
                    <div className="groupRoleManager__name">{m.name}</div>
                    {m.username ? <div className="groupRoleManager__sub">@{m.username}</div> : null}
                  </div>
                  <button type="button" className="wxBtn wxBtn--primary" disabled={submitting} onClick={() => onConfirm(m.id)}>
                    {submitting ? '提交中…' : '转让给 TA'}
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
