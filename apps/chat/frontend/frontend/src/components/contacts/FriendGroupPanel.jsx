import { useState } from 'react'
import { Link } from 'react-router-dom'
import { resolveAvatarSrc } from '../../utils/avatarUrl.js'
import { getFriendDisplayName, getPresenceLabel, MAX_REMARK_LENGTH, validateRemark } from '../../utils/friends.js'
import { userFacingError } from '../../utils/userFacingError.js'

export default function FriendGroupPanel({
  group,
  groups,
  list,
  expanded,
  editingGroupId,
  editingName,
  actionLoading,
  moveLoadingMap,
  remarkSavingMap,
  deletingMap,
  onToggleGroup,
  onStartRename,
  onRenameInputChange,
  onRenameSave,
  onRenameCancel,
  onDeleteGroup,
  onMoveFriend,
  onRemarkSave,
  onDeleteFriend,
}) {
  const [editingRemarkUserId, setEditingRemarkUserId] = useState(null)
  const [editingRemarkValue, setEditingRemarkValue] = useState('')
  const [remarkError, setRemarkError] = useState('')

  async function handleSaveRemark(userId) {
    setRemarkError('')
    const validation = validateRemark(editingRemarkValue)
    if (!validation.ok) {
      setRemarkError(validation.message)
      return
    }
    try {
      await onRemarkSave(userId, validation.value)
      setEditingRemarkUserId(null)
      setEditingRemarkValue('')
    } catch (err) {
      setRemarkError(userFacingError(err, '保存备注失败'))
    }
  }

  const remarkValidation = validateRemark(editingRemarkValue)
  const canSaveRemark = remarkValidation.ok

  return (
    <section className="wxGroup">
      <button
        onClick={() => onToggleGroup(group.group_id)}
        className="wxGroupHeader"
      >
        <div className="wxGroupHeader__left">
          <span className="wxGroupChevron" aria-hidden="true">
            {expanded ? '▾' : '▸'}
          </span>
          <span className="wxGroupName">{group.name}</span>
          <span className="wxGroupCount">({list.length})</span>
        </div>
      </button>

      <div className="wxGroupTools">
        <div className="wxGroupToolsRow">
        {editingGroupId === group.group_id ? (
          <>
            <input value={editingName} onChange={(e) => onRenameInputChange(e.target.value)} placeholder="分组名" />
            <button className="wxBtn wxBtn--primary" onClick={() => onRenameSave(group.group_id)} disabled={actionLoading}>
              保存
            </button>
            <button className="wxBtn" onClick={onRenameCancel} disabled={actionLoading}>
              取消
            </button>
          </>
        ) : (
          <>
            {group.group_id !== null && (
              <button className="wxBtn" onClick={() => onStartRename(group.group_id, group.name)} disabled={actionLoading}>
                改名
              </button>
            )}
            {group.group_id !== null && (
              <button className="wxBtn" onClick={() => onDeleteGroup(group.group_id)} disabled={actionLoading}>
                删除分组
              </button>
            )}
          </>
        )}
        </div>
      </div>

      {expanded && (
        <ul className="wxFriendList">
          {list.map((friend) => {
            const moving = Boolean(moveLoadingMap[friend.user_id])
            const presence = getPresenceLabel(friend.status?.presence)
            const remarkSaving = Boolean(remarkSavingMap[friend.user_id])
            const deleting = Boolean(deletingMap[friend.user_id])
            const isEditingRemark = editingRemarkUserId === friend.user_id
            const avatarUrl = resolveAvatarSrc(friend.avatar)
            return (
              <li key={friend.user_id} className="wxFriendItem">
                {avatarUrl ? (
                  <div
                    className="wxAvatar"
                    style={{
                      backgroundImage: `url(${avatarUrl})`,
                      backgroundSize: 'cover',
                      backgroundPosition: 'center',
                    }}
                  />
                ) : (
                  <div className="wxAvatar" aria-hidden>
                    <svg viewBox="0 0 24 24" className="wxAvatarDefaultIcon">
                      <circle cx="12" cy="8" r="4" />
                      <path d="M4 20c0-4 3.6-6 8-6s8 2 8 6" />
                    </svg>
                  </div>
                )}
                <div className="wxMain">
                  <div className="wxNameRow">
                    <div className="wxName">{getFriendDisplayName(friend)}</div>
                  </div>
                  <div className="wxFriendMeta">
                    @{friend.username} · {presence} {friend.status?.status_emoji || ''}
                  </div>
                </div>

                <div className="wxActions">
                  {!isEditingRemark ? (
                    <select
                      className="wxInlineSelect"
                      value={String(friend.group_id)}
                      onChange={(e) => {
                        const raw = e.target.value
                        const targetGroupId = raw === 'null' ? null : Number(raw)
                        onMoveFriend(friend.user_id, friend.group_id, targetGroupId)
                      }}
                      disabled={actionLoading || moving}
                    >
                      {groups.map((targetGroup) => (
                        <option key={String(targetGroup.group_id)} value={String(targetGroup.group_id)}>
                          移动到：{targetGroup.name}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <select className="wxInlineSelect" value={String(friend.group_id)} disabled style={{ opacity: 0.85 }}>
                      {groups.map((targetGroup) => (
                        <option key={String(targetGroup.group_id)} value={String(targetGroup.group_id)}>
                          {targetGroup.name}
                        </option>
                      ))}
                    </select>
                  )}

                  <Link className="wxBtnLink" to={`/user/${friend.user_id}`}>
                    详情
                  </Link>

                  {!isEditingRemark ? (
                    <button
                      onClick={() => {
                        setRemarkError('')
                        setEditingRemarkUserId(friend.user_id)
                        setEditingRemarkValue(friend.remark || '')
                      }}
                      disabled={actionLoading}
                      className="wxBtn"
                    >
                      编辑备注
                    </button>
                  ) : (
                    <div className="wxGroupToolsRow" style={{ flexWrap: 'wrap' }}>
                      <input
                        value={editingRemarkValue}
                        onChange={(e) => setEditingRemarkValue(e.target.value)}
                        placeholder="备注名"
                      />
                      <span className="wxMeta">
                        {editingRemarkValue.length}/{MAX_REMARK_LENGTH}
                      </span>
                      <button className="wxBtn wxBtn--primary" onClick={() => handleSaveRemark(friend.user_id)} disabled={actionLoading || remarkSaving}>
                        {remarkSaving ? '保存中...' : '保存'}
                      </button>
                      {!canSaveRemark && (
                        <span className="wxNotice is-err" style={{ padding: 0 }}>
                          {remarkValidation.message}
                        </span>
                      )}
                      <button
                        onClick={() => {
                          setRemarkError('')
                          setEditingRemarkUserId(null)
                          setEditingRemarkValue('')
                        }}
                        disabled={actionLoading || remarkSaving}
                        className="wxBtn"
                      >
                        取消
                      </button>
                    </div>
                  )}

                  {!isEditingRemark && (
                    <button
                      onClick={() => onDeleteFriend(friend.user_id)}
                      disabled={actionLoading || deleting}
                      className="wxBtn wxDangerText"
                    >
                      {deleting ? '删除中...' : '删除'}
                    </button>
                  )}
                </div>
              </li>
            )
          })}
          {list.length === 0 && <li className="wxNotice">该分组暂无好友</li>}
        </ul>
      )}
      {remarkError && <div className="wxNotice is-err">{remarkError}</div>}
    </section>
  )
}
