import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { resolveAvatarSrc } from '../../utils/avatarUrl.js'
import { getFriendDisplayName, getPresenceLabel, presenceClass } from '../../utils/friends.js'

function Avatar({ src }) {
  const url = resolveAvatarSrc(src)
  if (url) {
    return <img className="wxDetailPane__avatarImg" src={url} alt="" />
  }
  return (
    <div className="wxDetailPane__avatarPh" aria-hidden>
      <svg viewBox="0 0 24 24" className="wxAvatarDefaultIcon">
        <circle cx="12" cy="8" r="4" />
        <path d="M4 20c0-4 3.6-6 8-6s8 2 8 6" />
      </svg>
    </div>
  )
}

/**
 * @param {{
 *   selection: null | object,
 *   allGroups: Array<{ group_id: unknown, name: string }>,
 *   onHandleRequest?: (requestId: number, action: 'accept' | 'reject') => void,
 *   requestPendingId?: number | null,
 *   onRenameFriendGroup?: (groupId: unknown, name: string) => void,
 *   onDeleteFriendGroup?: (groupId: unknown) => void,
 *   onAssignFriendToGroup?: (friendUserId: unknown, targetGroupId: number | null) => void | Promise<void>,
 *   assignGroupLoading?: boolean,
 *   onStartChat?: (friendUserId: unknown) => void | Promise<void>,
 *   onAddFriendRelation?: (friendUserId: unknown, kind: 'blacklist' | 'whitelist') => void | Promise<void>,
 * }} props
 */
export default function ContactsDetailPane({
  selection,
  allGroups,
  onHandleRequest,
  requestPendingId,
  onRenameFriendGroup,
  onDeleteFriendGroup,
  onAssignFriendToGroup,
  assignGroupLoading = false,
  onStartChat,
  onAddFriendRelation,
}) {
  const [friendGroupDraft, setFriendGroupDraft] = useState('')
  const [friendGroupDraftOwnerId, setFriendGroupDraftOwnerId] = useState(null)
  const [groupPickerOpen, setGroupPickerOpen] = useState(false)
  const groupPickerRef = useRef(null)

  useEffect(() => {
    if (!groupPickerOpen) return
    function onDoc(e) {
      if (groupPickerRef.current && !groupPickerRef.current.contains(e.target)) {
        setGroupPickerOpen(false)
      }
    }
    function onKey(e) {
      if (e.key === 'Escape') setGroupPickerOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [groupPickerOpen])

  if (!selection) {
    return (
      <div className="wxDetailPane wxDetailPane--empty">
        <p className="wxDetailPane__hint">点击左侧条目查看头像、昵称与分组信息（非聊天界面）</p>
      </div>
    )
  }

  const { kind } = selection

  if (kind === 'request') {
    const item = selection.item
    const peer = selection.peer
    const canHandle = item.status === 'pending'
    return (
      <div className="wxDetailPane">
        <div className="wxDetailPane__hero">
          <Avatar src={peer?.avatar} />
          <div className="wxDetailPane__heroText">
            <div className="wxDetailPane__title">{peer?.username || '未知用户'}</div>
            <div className="wxDetailPane__sub">新的朋友 · 用户 ID {peer?.user_id ?? '-'}</div>
          </div>
        </div>
        <dl className="wxDetailPane__dl">
          <dt>验证消息</dt>
          <dd>{item.message || '—'}</dd>
          <dt>来源</dt>
          <dd>{item.source || 'search'}</dd>
          <dt>状态</dt>
          <dd>
            {item.status === 'pending' ? '待处理' : item.status === 'accepted' ? '已同意' : item.status === 'rejected' ? '已拒绝' : item.status}
          </dd>
        </dl>
        {canHandle && onHandleRequest ? (
          <div className="wxDetailPane__actions">
            <button type="button" className="wxBtn wxBtn--primary" disabled={requestPendingId === item.request_id} onClick={() => onHandleRequest(item.request_id, 'accept')}>
              同意
            </button>
            <button type="button" className="wxBtn" disabled={requestPendingId === item.request_id} onClick={() => onHandleRequest(item.request_id, 'reject')}>
              拒绝
            </button>
          </div>
        ) : null}
      </div>
    )
  }

  if (kind === 'friend') {
    const f = selection.friend
    const name = getFriendDisplayName(f)
    const namedGroups = allGroups.filter((g) => g.group_id != null && g.group_id !== undefined)
    const fallbackDraft = f.group_id != null && f.group_id !== undefined ? String(f.group_id) : ''
    const currentFriendId = f.user_id != null && f.user_id !== undefined ? String(f.user_id) : ''
    const useLocalDraft = currentFriendId !== '' && String(friendGroupDraftOwnerId ?? '') === currentFriendId
    const effectiveFriendGroupDraft = useLocalDraft ? friendGroupDraft : fallbackDraft
    const pickerTriggerLabel =
      effectiveFriendGroupDraft === ''
        ? '未分组'
        : namedGroups.find((g) => String(g.group_id) === String(effectiveFriendGroupDraft))?.name ?? '选择分组'

    return (
      <div className="wxDetailPane">
        <div className="wxDetailPane__hero">
          <Avatar src={f.avatar} />
          <div className="wxDetailPane__heroText">
            <div className="wxDetailPane__title">{name}</div>
            <div className="wxDetailPane__sub">@{f.username}</div>
          </div>
        </div>
        <dl className="wxDetailPane__dl">
          <dt>分组</dt>
          <dd>{f.group_name || '未分组'}</dd>
          {f.status?.presence ? (
            <>
              <dt>在线状态</dt>
              <dd>
                <span className="wxPresenceInline">
                  <span className={`presenceDot ${presenceClass(f.status.presence)}`} aria-hidden />
                  {getPresenceLabel(f.status.presence)}
                  {f.status.status_text || f.status.status_emoji ? (
                    <> · {[f.status.status_emoji, f.status.status_text].filter(Boolean).join(' ')}</>
                  ) : null}
                </span>
              </dd>
            </>
          ) : null}
        </dl>
        {onAssignFriendToGroup ? (
          <div className="wxGroupAssign">
            <div className="wxGroupAssign__labelRow">
              <span className="wxGroupAssign__title">归属分组</span>
              {effectiveFriendGroupDraft === '' ? (
                <span className="wxGroupAssign__badge is-muted">未分组</span>
              ) : (
                <span className="wxGroupAssign__badge">{pickerTriggerLabel}</span>
              )}
            </div>
            <p className="wxGroupAssign__hint">点下面框展开列表，选好分组后按保存即可。</p>
            <div className="wxGroupAssign__controls">
              <div
                className={`wxGroupPicker${assignGroupLoading ? ' is-disabled' : ''}`}
                ref={groupPickerRef}
              >
                <button
                  type="button"
                  className={`wxGroupPicker__trigger${groupPickerOpen ? ' is-open' : ''}`}
                  disabled={assignGroupLoading}
                  onClick={() => setGroupPickerOpen((o) => !o)}
                  aria-expanded={groupPickerOpen}
                  aria-haspopup="listbox"
                  aria-label="选择要把好友移入的分组"
                  title={pickerTriggerLabel}
                >
                  <span className="wxGroupPicker__triggerText">{pickerTriggerLabel}</span>
                  <span className="wxGroupPicker__triggerCaret" aria-hidden />
                </button>
                {groupPickerOpen ? (
                  <ul className="wxGroupPicker__menu" role="listbox">
                    <li role="presentation">
                      <button
                        type="button"
                        role="option"
                        aria-selected={effectiveFriendGroupDraft === ''}
                        className={`wxGroupPicker__item${effectiveFriendGroupDraft === '' ? ' is-active' : ''}`}
                        onClick={() => {
                          setFriendGroupDraftOwnerId(currentFriendId)
                          setFriendGroupDraft('')
                          setGroupPickerOpen(false)
                        }}
                      >
                        未分组
                      </button>
                    </li>
                    {namedGroups.map((g) => {
                      const id = String(g.group_id)
                      const active = String(effectiveFriendGroupDraft) === id
                      return (
                        <li key={id} role="presentation">
                          <button
                            type="button"
                            role="option"
                            aria-selected={active}
                            className={`wxGroupPicker__item${active ? ' is-active' : ''}`}
                            onClick={() => {
                              setFriendGroupDraftOwnerId(currentFriendId)
                              setFriendGroupDraft(id)
                              setGroupPickerOpen(false)
                            }}
                          >
                            {g.name}
                          </button>
                        </li>
                      )
                    })}
                  </ul>
                ) : null}
              </div>
              <button
                type="button"
                className="wxBtn wxBtn--primary wxGroupAssign__btn"
                disabled={
                  assignGroupLoading || String(effectiveFriendGroupDraft) === String(f.group_id ?? '')
                }
                onClick={() =>
                  onAssignFriendToGroup(
                    f.user_id,
                    effectiveFriendGroupDraft === '' ? null : Number(effectiveFriendGroupDraft),
                  )
                }
              >
                {assignGroupLoading ? '保存中…' : '保存'}
              </button>
            </div>
          </div>
        ) : null}
        <div className="wxDetailPane__actions">
          {onStartChat ? (
            <button
              type="button"
              className="wxBtn wxBtn--primary"
              disabled={assignGroupLoading}
              onClick={() => onStartChat(f.user_id)}
            >
              发消息
            </button>
          ) : null}
          <Link className="wxBtnLink" to={`/user/${f.user_id}`}>
            查看完整资料
          </Link>
          {onAddFriendRelation ? (
            <>
              <button
                type="button"
                className="wxBtn wxBtn--danger"
                disabled={assignGroupLoading || Boolean(f.is_blocked)}
                onClick={() => onAddFriendRelation(f.user_id, 'blacklist')}
              >
                {f.is_blocked ? '已在黑名单' : '加入黑名单'}
              </button>
              <button
                type="button"
                className="wxBtn"
                disabled={assignGroupLoading}
                onClick={() => onAddFriendRelation(f.user_id, 'whitelist')}
              >
                加入白名单
              </button>
            </>
          ) : null}
        </div>
      </div>
    )
  }

  if (kind === 'groupchat') {
    const c = selection.conversation
    return (
      <div className="wxDetailPane">
        <div className="wxDetailPane__hero">
          <Avatar src={c.avatar} />
          <div className="wxDetailPane__heroText">
            <div className="wxDetailPane__title">{c.name || '群聊'}</div>
            <div className="wxDetailPane__sub">群聊 · 会话 ID {c.conversation_id}</div>
          </div>
        </div>
        <dl className="wxDetailPane__dl">
          <dt>说明</dt>
          <dd>此处仅展示群资料摘要，不包含消息与输入框。</dd>
        </dl>
        <div className="wxDetailPane__actions">
          <Link className="wxBtn wxBtn--primary" to={`/groups/${c.conversation_id}?from=contacts`}>
            群资料与管理
          </Link>
          <Link className="wxBtnLink" to={`/chat?open=${c.conversation_id}`}>
            进入聊天
          </Link>
        </div>
      </div>
    )
  }

  if (kind === 'friendgroup') {
    const { group, members } = selection
    const gid = group.group_id
    const canManage = gid !== null && gid !== undefined
    return (
      <div className="wxDetailPane">
        <div className="wxDetailPane__hero">
          <div className="wxDetailPane__avatarPh wxDetailPane__avatarPh--folder" aria-hidden>
            #
          </div>
          <div className="wxDetailPane__heroText">
            <div className="wxDetailPane__title">{group.name}</div>
            <div className="wxDetailPane__sub">
              {members.length === 0 ? '暂无成员' : `共 ${members.length} 位好友`}
            </div>
          </div>
        </div>

        <div className="wxDetailPane__sectionLabel">我的分组</div>
        <div className="wxDetailPane__tags wxDetailPane__tags--groups">
          {allGroups.map((g) => (
            <span
              key={String(g.group_id)}
              className={`wxDetailPane__tag wxDetailPane__tag--group${String(g.group_id) === String(group.group_id) ? ' is-active' : ''}`}
            >
              {g.name}
              <span className="wxDetailPane__tagCount wxDetailPane__tagCount--pill">{g.friend_count ?? 0}</span>
            </span>
          ))}
        </div>

        <div className="wxDetailPane__sectionLabel">组内好友</div>
        {members.length === 0 ? (
          <p className="wxDetailPane__muted">该分组下暂无好友</p>
        ) : (
          <ul className="wxDetailPane__memberList">
            {members.map((m) => (
              <li key={m.user_id} className="wxDetailPane__memberRow">
                <Avatar src={m.avatar} />
                <div className="wxDetailPane__memberMain">
                  <div className="wxDetailPane__memberName">{getFriendDisplayName(m)}</div>
                  <div className="wxDetailPane__memberMeta">
                    账号 {m.username} · 当前所在组 {m.group_name || '未分组'}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}

        {canManage && onRenameFriendGroup && onDeleteFriendGroup ? (
          <div className="wxDetailPane__groupActions">
            <button
              type="button"
              className="wxBtn wxBtn--ghost"
              onClick={() => {
                const name = window.prompt('新的分组名称', group.name)
                if (name == null) return
                const trimmed = name.trim()
                if (!trimmed) return
                onRenameFriendGroup(gid, trimmed)
              }}
            >
              重命名
            </button>
            <button
              type="button"
              className="wxBtn wxBtn--danger"
              onClick={() => {
                if (!window.confirm(`确认删除分组「${group.name}」？好友将移至未分组。`)) return
                onDeleteFriendGroup(gid)
              }}
            >
              删除分组
            </button>
          </div>
        ) : null}
      </div>
    )
  }

  return null
}
