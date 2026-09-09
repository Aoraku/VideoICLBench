import { useRef, useState } from 'react'
import * as groupApi from '../../../api/groupApi.js'
import { CHAT_EVENT_CONVERSATION_REFRESH } from '../../../constants/chatEvents.js'
import { resolveAvatarSrc } from '../../../utils/avatarUrl.js'
import { userFacingError } from '../../../utils/userFacingError.js'
import GroupStringEditDialog from '../common/GroupStringEditDialog.jsx'
import PermissionTag from '../common/PermissionTag.jsx'

const GROUP_NAME_MAX = 50
const GROUP_NICKNAME_MAX = 30

/**
 * @param {{
 *   groupId: string,
 *   group: import('../../../types/group.js').Group | null,
 *   members: import('../../../types/group.js').GroupMember[],
 *   currentUserRole: import('../../../types/group.js').GroupRole | null,
 *   myGroupNickname?: string | null,
 *   latestAnnouncement?: import('../../../types/group.js').GroupAnnouncement | null,
 *   onRefresh?: () => void | Promise<void>,
 *   onDissolved?: () => void,
 * }} props
 */
export default function GroupInfoPanel({
  groupId,
  group,
  members,
  currentUserRole,
  myGroupNickname,
  latestAnnouncement,
  onRefresh,
  onDissolved,
}) {
  const [savingName, setSavingName] = useState(false)
  const [savingNickname, setSavingNickname] = useState(false)
  const [nameModalOpen, setNameModalOpen] = useState(false)
  const [nicknameModalOpen, setNicknameModalOpen] = useState(false)
  const [nameErr, setNameErr] = useState('')
  const [nicknameErr, setNicknameErr] = useState('')
  const [avatarErr, setAvatarErr] = useState('')
  const [savingAvatar, setSavingAvatar] = useState(false)
  const [dissolving, setDissolving] = useState(false)
  const avatarInputRef = useRef(null)

  if (!group) return null

  const canEditGroupName = currentUserRole === 'owner' || currentUserRole === 'admin'
  const canEditAvatar = canEditGroupName
  const canDissolve = currentUserRole === 'owner'
  const canEditMyNickname = Boolean(currentUserRole)

  async function runRefresh() {
    if (typeof onRefresh === 'function') await onRefresh()
  }

  async function submitGroupName(trimmed) {
    setNameErr('')
    const initial = (group.name || '').trim()
    if (!trimmed) {
      setNameErr('群名称不能为空')
      return
    }
    if (trimmed.length > GROUP_NAME_MAX) {
      setNameErr(`群名称最多 ${GROUP_NAME_MAX} 个字符`)
      return
    }
    if (trimmed === initial) {
      setNameModalOpen(false)
      return
    }
    setSavingName(true)
    try {
      await groupApi.updateGroupInfo(groupId, { name: trimmed })
      setNameModalOpen(false)
      await runRefresh()
      window.dispatchEvent(new CustomEvent(CHAT_EVENT_CONVERSATION_REFRESH))
    } catch (e) {
      setNameErr(userFacingError(e, '修改群名称失败'))
    } finally {
      setSavingName(false)
    }
  }

  async function submitNickname(trimmed) {
    setNicknameErr('')
    const initial = String(myGroupNickname ?? '').trim()
    if (trimmed.length > GROUP_NICKNAME_MAX) {
      setNicknameErr(`群昵称最多 ${GROUP_NICKNAME_MAX} 个字符`)
      return
    }
    if (trimmed === initial) {
      setNicknameModalOpen(false)
      return
    }
    setSavingNickname(true)
    try {
      await groupApi.setMyGroupNickname(groupId, trimmed)
      setNicknameModalOpen(false)
      await runRefresh()
      window.dispatchEvent(new CustomEvent(CHAT_EVENT_CONVERSATION_REFRESH))
    } catch (e) {
      setNicknameErr(userFacingError(e, '修改群昵称失败'))
    } finally {
      setSavingNickname(false)
    }
  }

  async function submitAvatar(file) {
    if (!file) return
    setAvatarErr('')
    setSavingAvatar(true)
    try {
      await groupApi.uploadGroupAvatar(groupId, file)
      await runRefresh()
      window.dispatchEvent(new CustomEvent(CHAT_EVENT_CONVERSATION_REFRESH))
    } catch (e) {
      setAvatarErr(userFacingError(e, '上传群头像失败'))
    } finally {
      setSavingAvatar(false)
      if (avatarInputRef.current) avatarInputRef.current.value = ''
    }
  }

  async function submitDissolve() {
    if (!window.confirm(`确认解散群聊「${group.name || groupId}」？`)) return
    setAvatarErr('')
    setDissolving(true)
    try {
      await groupApi.dissolveGroup(groupId)
      window.dispatchEvent(new CustomEvent(CHAT_EVENT_CONVERSATION_REFRESH))
      if (typeof onDissolved === 'function') onDissolved()
    } catch (e) {
      setAvatarErr(userFacingError(e, '解散群聊失败'))
    } finally {
      setDissolving(false)
    }
  }

  const owner = members.find((m) => m.id === group.ownerId)
  const ownerLabel =
    owner?.name ||
    (group.ownerUsername ? String(group.ownerUsername) : '') ||
    (group.ownerId ? `用户 ${group.ownerId}` : '—')
  const admins = members.filter((m) => m.role === 'admin')
  const count = group.memberCount > 0 ? group.memberCount : members.length
  const avatarSrc = resolveAvatarSrc(group.avatar)

  return (
    <section className="groupCard groupInfoPanel">
      <h2 className="groupCard__title">群信息</h2>
      <div className="groupInfoPanel__avatarBlock">
        {avatarSrc ? (
          <img className="groupInfoPanel__avatarImg" src={avatarSrc} alt="" />
        ) : (
          <div className="groupInfoPanel__avatarGrid" aria-hidden>
            {members.slice(0, 9).map((m) => {
              const src = resolveAvatarSrc(m.avatar)
              return src ? (
                <img key={m.id} src={src} alt="" />
              ) : (
                <span key={m.id}>{(m.name || m.username || '?').slice(0, 1)}</span>
              )
            })}
          </div>
        )}
        {canEditAvatar ? (
          <div className="groupInfoPanel__avatarActions">
            <input
              ref={avatarInputRef}
              type="file"
              accept="image/*"
              style={{ display: 'none' }}
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) void submitAvatar(file)
              }}
            />
            <button
              type="button"
              className="groupInfoPanel__editBtn"
              disabled={savingAvatar}
              onClick={() => avatarInputRef.current?.click()}
            >
              {savingAvatar ? '上传中…' : '上传群头像'}
            </button>
            {canDissolve ? (
              <button
                type="button"
                className="groupInfoPanel__editBtn groupInfoPanel__editBtn--danger"
                disabled={dissolving}
                onClick={() => void submitDissolve()}
              >
                {dissolving ? '处理中…' : '解散群聊'}
              </button>
            ) : null}
            {avatarErr ? <div className="groupInfoPanel__error">{avatarErr}</div> : null}
          </div>
        ) : null}
      </div>
      <dl className="groupInfoPanel__dl">
        <dt>群名称</dt>
        <dd className="groupInfoPanel__ddRow">
          <span className="groupInfoPanel__ddText">{group.name || '—'}</span>
          {canEditGroupName ? (
            <button
              type="button"
              className="groupInfoPanel__editBtn"
              onClick={() => {
                setNameErr('')
                setNameModalOpen(true)
              }}
              disabled={savingName}
            >
              {savingName ? '保存中…' : '修改'}
            </button>
          ) : null}
        </dd>
        <dt>成员数量</dt>
        <dd>{count}</dd>
        <dt>群主</dt>
        <dd>{ownerLabel}</dd>
        <dt>管理员</dt>
        <dd>
          {admins.length === 0 ? (
            <span className="groupMuted">暂无</span>
          ) : (
            <ul className="groupInfoPanel__adminList">
              {admins.map((a) => (
                <li key={a.id}>{a.name}</li>
              ))}
            </ul>
          )}
        </dd>
        <dt>我在本群</dt>
        <dd>
          {currentUserRole ? <PermissionTag role={currentUserRole} /> : <span className="groupMuted">未知</span>}
        </dd>
        <dt>我在本群的昵称</dt>
        <dd className="groupInfoPanel__ddRow">
          <span className="groupInfoPanel__ddText">
            {myGroupNickname ? myGroupNickname : <span className="groupMuted">未设置</span>}
          </span>
          {canEditMyNickname ? (
            <button
              type="button"
              className="groupInfoPanel__editBtn"
              onClick={() => {
                setNicknameErr('')
                setNicknameModalOpen(true)
              }}
              disabled={savingNickname}
            >
              {savingNickname ? '保存中…' : '修改'}
            </button>
          ) : null}
        </dd>
        {latestAnnouncement && latestAnnouncement.content ? (
          <>
            <dt>最新公告</dt>
            <dd>
              <div className="groupInfoPanel__latestAnn">
                <p className="groupInfoPanel__latestAnnText">{latestAnnouncement.content}</p>
                <div className="groupInfoPanel__latestAnnMeta">
                  {latestAnnouncement.publisherName || '—'} · {formatTime(latestAnnouncement.createdAt)}
                </div>
              </div>
            </dd>
          </>
        ) : null}
        {group.createdAt ? (
          <>
            <dt>创建时间</dt>
            <dd>{formatTime(group.createdAt)}</dd>
          </>
        ) : null}
      </dl>

      <GroupStringEditDialog
        open={nameModalOpen}
        onClose={() => {
          if (savingName) return
          setNameModalOpen(false)
          setNameErr('')
        }}
        title="修改群名称"
        hint={`请输入新群名称，1～${GROUP_NAME_MAX} 字，将显示在会话列表与群资料中。`}
        initialValue={group.name || ''}
        maxLength={GROUP_NAME_MAX}
        requireNonEmpty
        submitting={savingName}
        serverError={nameErr}
        confirmLabel="保存"
        inputPlaceholder="群名称"
        onConfirm={submitGroupName}
      />

      <GroupStringEditDialog
        open={nicknameModalOpen}
        onClose={() => {
          if (savingNickname) return
          setNicknameModalOpen(false)
          setNicknameErr('')
        }}
        title="我在本群的昵称"
        hint={`最多 ${GROUP_NICKNAME_MAX} 字。留空并保存可清除昵称，群内显示名将恢复为账号名。`}
        initialValue={myGroupNickname ?? ''}
        maxLength={GROUP_NICKNAME_MAX}
        requireNonEmpty={false}
        submitting={savingNickname}
        serverError={nicknameErr}
        confirmLabel="保存"
        inputPlaceholder="群昵称（可选）"
        onConfirm={submitNickname}
      />
    </section>
  )
}

function formatTime(iso) {
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleString('zh-CN')
  } catch {
    return iso
  }
}
