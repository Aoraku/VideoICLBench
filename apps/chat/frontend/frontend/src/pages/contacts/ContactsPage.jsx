import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { createPrivateConversation, listConversations } from '../../api/conversations.js'
import {
  addBlacklist,
  addWhitelist,
  createFriendGroup,
  deleteFriendGroup,
  handleFriendRequest,
  listBlacklist,
  listFriendGroups,
  listFriendRequests,
  listFriends,
  listWhitelist,
  removeBlacklist,
  removeWhitelist,
  updateFriendGroup,
} from '../../api/friends.js'
import ContactsDetailPane from '../../components/contacts/ContactsDetailPane.jsx'
import { CHAT_EVENT_CONVERSATION_REFRESH } from '../../constants/chatEvents.js'
import { mockConversations, mockFriends, mockFriendRequests, mockGroups } from '../../mock/friends.js'
import {
  buildGroupMap,
  getFriendDisplayName,
  getPresenceLabel,
  normalizeGroupList,
  presenceClass,
  recalculateGroupCounts,
  toGroupKey,
  validateRemark,
} from '../../utils/friends.js'
import { resolveAvatarSrc } from '../../utils/avatarUrl.js'
import { userFacingError } from '../../utils/userFacingError.js'

/** @typedef {'newfriends' | 'contacts' | 'groupchats' | 'friendgroups' | 'blacklist' | 'whitelist'} OpenSection */

function getRequestPeer(item) {
  if (item.from_user && typeof item.from_user === 'object') return item.from_user
  return {
    user_id: item.from_user_id,
    username: item.from_username || '未知用户',
    avatar: item.from_avatar || '',
  }
}

export default function ContactsPage() {
  const [friends, setFriends] = useState([])
  const [groups, setGroups] = useState([])
  const [requests, setRequests] = useState([])
  const [groupChats, setGroupChats] = useState([])
  const [groupChatsLoaded, setGroupChatsLoaded] = useState(false)
  const [blacklist, setBlacklist] = useState([])
  const [whitelist, setWhitelist] = useState([])

  /** @type {[OpenSection | null, Function]} */
  const [openSection, setOpenSection] = useState(null)
  const [selection, setSelection] = useState(null)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [newGroupName, setNewGroupName] = useState('')
  const [actionLoading, setActionLoading] = useState(false)
  const [requestPendingId, setRequestPendingId] = useState(null)

  const location = useLocation()
  const navigate = useNavigate()

  const groupedFriends = useMemo(() => buildGroupMap(groups, friends), [friends, groups])
  const groupList = useMemo(() => normalizeGroupList(groups, friends), [groups, friends])

  useEffect(() => {
    fetchContacts({ resetUi: false })
  }, [])

  useEffect(() => {
    const params = new URLSearchParams(location.search)
    const deletedUserId = params.get('deleted')
    const remarkUpdatedUserId = params.get('remarkUpdated')
    const refresh = params.get('refresh')
    const remarkText = params.get('remark') || ''
    const shouldRefresh = refresh === '1'

    if (!deletedUserId && !remarkUpdatedUserId && !shouldRefresh) return

    if (deletedUserId) {
      setFriends((prev) => {
        const next = prev.filter((f) => String(f.user_id) !== String(deletedUserId))
        setGroups((prevGroups) => recalculateGroupCounts(prevGroups, next))
        return next
      })
    }

    if (remarkUpdatedUserId) {
      const validation = validateRemark(remarkText)
      if (!validation.ok) {
        setError(validation.message)
      } else {
        const nextRemark = validation.value
        setFriends((prev) => prev.map((f) => (String(f.user_id) === String(remarkUpdatedUserId) ? { ...f, remark: nextRemark } : f)))
      }
    }

    if (shouldRefresh) fetchContacts({ resetUi: true })
    navigate('/contacts', { replace: true })
  }, [location.search, navigate])

  useEffect(() => {
    if (openSection !== 'groupchats' || groupChatsLoaded) return
    let cancelled = false
    ;(async () => {
      try {
        const data = await listConversations({ page: 1, pageSize: 50 })
        const rows = Array.isArray(data?.results) ? data.results : []
        if (!cancelled) setGroupChats(rows.filter((c) => c.type === 'group'))
      } catch {
        if (!cancelled) setGroupChats(mockConversations.results.filter((c) => c.type === 'group'))
      } finally {
        if (!cancelled) setGroupChatsLoaded(true)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [openSection, groupChatsLoaded])

  /**
   * @param {{ resetUi?: boolean }} [opts]
   */
  async function fetchContacts(opts = {}) {
    const resetUi = opts.resetUi === true
    setLoading(true)
    setError('')
    if (resetUi) {
      setOpenSection(null)
      setSelection(null)
    }

    let nextFriends = []
    let nextGroups = []
    let nextRequests = []
    let nextBlacklist = []
    let nextWhitelist = []
    let errMsg = ''

    try {
      const fd = await listFriends({ page: 1, pageSize: 100 })
      nextFriends = Array.isArray(fd?.results) ? fd.results : []
    } catch (err) {
      nextFriends = mockFriends.results
      errMsg = userFacingError(err, '暂时无法同步好友列表')
    }

    try {
      const gd = await listFriendGroups()
      nextGroups = Array.isArray(gd?.groups) ? gd.groups : []
    } catch (err) {
      nextGroups = mockGroups.groups
      if (!errMsg) errMsg = userFacingError(err, '暂时无法同步分组')
    }

    try {
      const rd = await listFriendRequests({ type: 'received', status: 'pending', page: 1, pageSize: 50 })
      nextRequests = Array.isArray(rd?.results) ? rd.results : []
    } catch (err) {
      nextRequests = mockFriendRequests.received?.results || []
      if (!errMsg) errMsg = userFacingError(err, '暂时无法同步好友申请')
    }

    try {
      const bd = await listBlacklist({ page: 1, pageSize: 100 })
      nextBlacklist = Array.isArray(bd?.results) ? bd.results : []
    } catch (err) {
      nextBlacklist = []
      if (!errMsg) errMsg = userFacingError(err, '暂时无法同步黑名单')
    }

    try {
      const wd = await listWhitelist({ page: 1, pageSize: 100 })
      nextWhitelist = Array.isArray(wd?.results) ? wd.results : []
    } catch (err) {
      nextWhitelist = []
      if (!errMsg) errMsg = userFacingError(err, '暂时无法同步白名单')
    }

    setFriends(nextFriends)
    setGroups(recalculateGroupCounts(nextGroups, nextFriends))
    setRequests(nextRequests)
    setBlacklist(nextBlacklist)
    setWhitelist(nextWhitelist)

    try {
      const convData = await listConversations({ page: 1, pageSize: 50 })
      const convRows = Array.isArray(convData?.results) ? convData.results : []
      setGroupChats(convRows.filter((c) => c.type === 'group'))
    } catch {
      setGroupChats(mockConversations.results.filter((c) => c.type === 'group'))
    } finally {
      setGroupChatsLoaded(true)
    }

    if (errMsg) setError(errMsg)
    setLoading(false)
  }

  function toggleSection(id) {
    setOpenSection((prev) => (prev === id ? null : id))
    setSelection(null)
  }

  function selectRow(next) {
    setSelection(next)
  }

  async function onCreateGroup(event) {
    event.preventDefault()
    const name = newGroupName.trim()
    if (!name) return
    setActionLoading(true)
    setError('')
    try {
      await createFriendGroup(name)
      await fetchContacts({ resetUi: false })
      setNewGroupName('')
    } catch (err) {
      setError(userFacingError(err, '创建分组失败'))
    } finally {
      setActionLoading(false)
    }
  }

  async function onRenameFriendGroup(groupId, name) {
    if (!name) return
    setActionLoading(true)
    setError('')
    try {
      await updateFriendGroup(groupId, { name })
      await fetchContacts({ resetUi: false })
    } catch (err) {
      setError(userFacingError(err, '修改分组失败'))
    } finally {
      setActionLoading(false)
    }
  }

  async function onAssignFriendToGroup(friendUserId, targetGroupId) {
    const uid = Number(friendUserId)
    if (!Number.isFinite(uid)) return
    setActionLoading(true)
    setError('')
    const friend = friends.find((x) => String(x.user_id) === String(friendUserId))
    const prevGid = friend?.group_id != null && friend?.group_id !== undefined ? Number(friend.group_id) : null
    try {
      if (targetGroupId == null || Number.isNaN(Number(targetGroupId))) {
        if (prevGid != null) {
          await updateFriendGroup(prevGid, { remove_friend_ids: [uid] })
        }
      } else {
        const gid = Number(targetGroupId)
        await updateFriendGroup(gid, { add_friend_ids: [uid] })
      }
      await fetchContacts({ resetUi: false })
    } catch (err) {
      setError(userFacingError(err, '更新分组失败'))
    } finally {
      setActionLoading(false)
    }
  }

  async function onDeleteFriendGroup(groupId) {
    setActionLoading(true)
    setError('')
    try {
      await deleteFriendGroup(groupId)
      await fetchContacts({ resetUi: false })
      setSelection(null)
    } catch (err) {
      setError(userFacingError(err, '删除分组失败'))
    } finally {
      setActionLoading(false)
    }
  }

  async function onHandleRequest(requestId, action) {
    setRequestPendingId(requestId)
    setError('')
    const reqSnapshot = requests.find((r) => r.request_id === requestId)
    try {
      await handleFriendRequest(requestId, action)
      setRequests((prev) => prev.filter((r) => r.request_id !== requestId))
      setSelection(null)
      if (action === 'accept') {
        const peer = getRequestPeer(reqSnapshot || {})
        const peerId = peer?.user_id
        if (peerId != null) {
          try {
            await createPrivateConversation(Number(peerId))
          } catch {
            /* 忽略 */
          }
        }
        window.dispatchEvent(new CustomEvent(CHAT_EVENT_CONVERSATION_REFRESH))
        fetchContacts()
      }
    } catch (err) {
      setError(userFacingError(err, '处理失败'))
    } finally {
      setRequestPendingId(null)
    }
  }

  async function onStartChat(friendUserId) {
    const uid = Number(friendUserId)
    if (!Number.isFinite(uid)) return
    setActionLoading(true)
    setError('')
    try {
      const data = await createPrivateConversation(uid)
      const convId = Number(data?.conversation_id)
      if (!Number.isFinite(convId) || convId <= 0) {
        throw new Error('创建会话失败：未返回有效会话 ID')
      }
      navigate(`/chat?open=${convId}`)
    } catch (err) {
      setError(userFacingError(err, '创建会话失败'))
    } finally {
      setActionLoading(false)
    }
  }

  async function onAddFriendRelation(friendUserId, kind) {
    const uid = Number(friendUserId)
    if (!Number.isFinite(uid) || uid <= 0) return
    setActionLoading(true)
    setError('')
    try {
      if (kind === 'blacklist') {
        await addBlacklist(uid)
        setFriends((prev) => prev.map((f) => (Number(f.user_id) === uid ? { ...f, is_blocked: true } : f)))
      } else {
        await addWhitelist(uid)
      }
      await fetchContacts({ resetUi: false })
    } catch (err) {
      setError(userFacingError(err, kind === 'blacklist' ? '加入黑名单失败' : '加入白名单失败'))
    } finally {
      setActionLoading(false)
    }
  }

  async function onRemoveFriendRelation(friendUserId, kind) {
    const uid = Number(friendUserId)
    if (!Number.isFinite(uid) || uid <= 0) return
    setActionLoading(true)
    setError('')
    try {
      if (kind === 'blacklist') {
        await removeBlacklist(uid)
      } else {
        await removeWhitelist(uid)
      }
      await fetchContacts({ resetUi: false })
      setSelection(null)
    } catch (err) {
      setError(userFacingError(err, kind === 'blacklist' ? '移出黑名单失败' : '移出白名单失败'))
    } finally {
      setActionLoading(false)
    }
  }

  function relationName(item) {
    return item?.remark || item?.username || item?.blocked_username || item?.whitelisted_username || `用户 ${item?.user_id ?? ''}`
  }

  function relationUserId(item) {
    return item?.user_id ?? item?.blocked_user_id ?? item?.whitelisted_user_id
  }

  function statusLine(status) {
    const presence = status?.presence || 'offline'
    const suffix = status?.status_text || status?.status_emoji
      ? ` · ${[status?.status_emoji, status?.status_text].filter(Boolean).join(' ')}`
      : ''
    return (
      <span className="wxPresenceInline">
        <span className={`presenceDot ${presenceClass(presence)}`} aria-hidden />
        {getPresenceLabel(presence)}
        {suffix}
      </span>
    )
  }

  function sectionHead(id, label, count) {
    const open = openSection === id
    return (
      <button type="button" className={`wxAccHead${open ? ' is-open' : ''}`} onClick={() => toggleSection(id)} aria-expanded={open}>
        <span className="wxAccHead__label">{label}</span>
        <span className="wxAccHead__meta">{open ? '点击收起' : `${count} 项`}</span>
      </button>
    )
  }

  return (
    <div className="wxPage wxPage--contacts">
      <div className="wxHeader">
        <div className="wxHeader__left">
          <div>
            <div className="wxTitle">通讯录</div>
            <div className="wxSub">点击区块展开列表；仅展开一个区块。点选条目在右侧查看资料。</div>
          </div>
        </div>
        <div className="wxActions">
          <Link className="wxBtnLink" to="/groups">
            群聊列表
          </Link>
          <Link className="wxBtnLink" to="/groups/create">
            创建群聊
          </Link>
          <Link className="wxBtnLink" to="/contacts/search">
            搜索用户
          </Link>
          <Link className="wxBtnLink" to="/friends/requests">
            全部申请
          </Link>
        </div>
      </div>

      <div className="wxToolbar wxToolbar--contactsTop">
        <div className="wxContactsToolbarInner">
          <div className="wxContactsToolbarRow">
            <button className="wxBtn wxBtn--primary" type="button" onClick={() => fetchContacts({ resetUi: false })} disabled={loading}>
              {loading ? '刷新中...' : '刷新列表'}
            </button>
          </div>
          <div className="wxGroupCreate">
            <div className="wxGroupCreate__head">
              <span className="wxGroupCreate__title">新建好友分组</span>
              <span className="wxGroupCreate__desc">为联系人打标签，便于在「分组」里整理；也可点选某位好友，在右侧将其移入分组。</span>
            </div>
            <form onSubmit={onCreateGroup} className="wxGroupCreate__form">
              <input
                className="wxSearchInput"
                value={newGroupName}
                onChange={(e) => setNewGroupName(e.target.value)}
                placeholder="例如：同事、家人、球友…"
                aria-label="新分组名称"
              />
              <button className="wxBtn wxBtn--primary" type="submit" disabled={actionLoading}>
                {actionLoading ? '创建中…' : '创建分组'}
              </button>
            </form>
          </div>
        </div>
      </div>

      {error ? (
        <div className="wxNotice is-err" style={{ maxWidth: 1100, margin: '0 auto 10px' }}>
          {error}
        </div>
      ) : null}

      <div className="wxContactsSplit">
        <div className="wxCard wxAcc">
          {sectionHead('newfriends', '新的朋友', requests.length)}
          {openSection === 'newfriends' ? (
            <div className="wxAccBody">
              {loading ? (
                <div className="wxNotice">加载中...</div>
              ) : requests.length === 0 ? (
                <div className="wxNotice">暂无待处理申请</div>
              ) : (
                <ul className="wxList">
                  {requests.map((item) => {
                    const peer = getRequestPeer(item)
                    const avatarSrc = resolveAvatarSrc(peer.avatar)
                    const active = selection?.kind === 'request' && selection.item.request_id === item.request_id
                    return (
                      <li key={item.request_id}>
                        <button type="button" className={`wxAccRow${active ? ' is-active' : ''}`} onClick={() => selectRow({ kind: 'request', item, peer })}>
                          <div
                            className="wxAvatar"
                            style={
                              avatarSrc
                                ? { backgroundImage: `url(${avatarSrc})`, backgroundSize: 'cover' }
                                : undefined
                            }
                          >
                            {!avatarSrc ? (
                              <svg viewBox="0 0 24 24" className="wxAvatarDefaultIcon" aria-hidden>
                                <circle cx="12" cy="8" r="4" />
                                <path d="M4 20c0-4 3.6-6 8-6s8 2 8 6" />
                              </svg>
                            ) : null}
                          </div>
                          <div className="wxAccRow__main">
                            <div className="wxName">{peer.username}</div>
                            <div className="wxMeta">{item.message || '请求加你为好友'}</div>
                          </div>
                        </button>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          ) : null}

          {sectionHead('contacts', '联系人', friends.length)}
          {openSection === 'contacts' ? (
            <div className="wxAccBody">
              {loading ? (
                <div className="wxNotice">加载中...</div>
              ) : friends.length === 0 ? (
                <div className="wxNotice">暂无好友</div>
              ) : (
                <ul className="wxList">
                  {friends.map((f) => {
                    const avatarSrc = resolveAvatarSrc(f.avatar)
                    const active = selection?.kind === 'friend' && selection.friend.user_id === f.user_id
                    return (
                      <li key={f.user_id}>
                        <button type="button" className={`wxAccRow${active ? ' is-active' : ''}`} onClick={() => selectRow({ kind: 'friend', friend: f })}>
                          <div
                            className="wxAvatar"
                            style={
                              avatarSrc
                                ? { backgroundImage: `url(${avatarSrc})`, backgroundSize: 'cover' }
                                : undefined
                            }
                          >
                            {!avatarSrc ? (
                              <svg viewBox="0 0 24 24" className="wxAvatarDefaultIcon" aria-hidden>
                                <circle cx="12" cy="8" r="4" />
                                <path d="M4 20c0-4 3.6-6 8-6s8 2 8 6" />
                              </svg>
                            ) : null}
                          </div>
                          <div className="wxAccRow__main">
                            <div className="wxName">{getFriendDisplayName(f)}</div>
                            <div className="wxMeta">
                              {f.group_name || '未分组'}
                              {' · '}
                              {statusLine(f.status)}
                            </div>
                          </div>
                        </button>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          ) : null}

          {sectionHead('groupchats', '群聊', groupChats.length)}
          {openSection === 'groupchats' ? (
            <div className="wxAccBody">
              {!groupChatsLoaded ? (
                <div className="wxNotice">加载群聊...</div>
              ) : groupChats.length === 0 ? (
                <div className="wxNotice">暂无群聊会话</div>
              ) : (
                <ul className="wxList">
                  {groupChats.map((c) => {
                    const avatarSrc = resolveAvatarSrc(c.avatar)
                    const active = selection?.kind === 'groupchat' && selection.conversation.conversation_id === c.conversation_id
                    return (
                      <li key={c.conversation_id}>
                        <button type="button" className={`wxAccRow${active ? ' is-active' : ''}`} onClick={() => selectRow({ kind: 'groupchat', conversation: c })}>
                          <div
                            className="wxAvatar"
                            style={
                              avatarSrc
                                ? { backgroundImage: `url(${avatarSrc})`, backgroundSize: 'cover' }
                                : undefined
                            }
                          >
                            {!avatarSrc ? (
                              <svg viewBox="0 0 24 24" className="wxAvatarDefaultIcon" aria-hidden>
                                <circle cx="12" cy="8" r="4" />
                                <path d="M4 20c0-4 3.6-6 8-6s8 2 8 6" />
                              </svg>
                            ) : null}
                          </div>
                          <div className="wxAccRow__main">
                            <div className="wxName">{c.name || '群聊'}</div>
                            <div className="wxMeta">群会话 · {c.conversation_id}</div>
                          </div>
                        </button>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          ) : null}

          {sectionHead('friendgroups', '分组', groupList.length)}
          {openSection === 'friendgroups' ? (
            <div className="wxAccBody">
              {loading ? (
                <div className="wxNotice">加载中...</div>
              ) : groupList.length === 0 ? (
                <div className="wxNotice">暂无自定义分组</div>
              ) : (
                <ul className="wxList">
                  {groupList.map((group) => {
                    const key = toGroupKey(group.group_id)
                    const members = groupedFriends.get(key) || []
                    const active = selection?.kind === 'friendgroup' && String(selection.group.group_id) === String(group.group_id)
                    return (
                      <li key={key}>
                        <button type="button" className={`wxAccRow${active ? ' is-active' : ''}`} onClick={() => selectRow({ kind: 'friendgroup', group, members })}>
                          <div className="wxAvatar wxAvatar--folder" aria-hidden>
                            #
                          </div>
                          <div className="wxAccRow__main">
                            <div className="wxName">{group.name}</div>
                            <div className="wxMeta">{members.length} 人</div>
                          </div>
                        </button>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          ) : null}

          {sectionHead('blacklist', '黑名单', blacklist.length)}
          {openSection === 'blacklist' ? (
            <div className="wxAccBody">
              {loading ? (
                <div className="wxNotice">加载中...</div>
              ) : blacklist.length === 0 ? (
                <div className="wxNotice">暂无黑名单用户</div>
              ) : (
                <ul className="wxList">
                  {blacklist.map((item) => {
                    const uid = relationUserId(item)
                    const avatarSrc = resolveAvatarSrc(item.avatar)
                    return (
                      <li key={`black-${uid}`}>
                        <div className="wxAccRow wxAccRow--static">
                          <div
                            className="wxAvatar"
                            style={avatarSrc ? { backgroundImage: `url(${avatarSrc})`, backgroundSize: 'cover' } : undefined}
                          >
                            {!avatarSrc ? (
                              <svg viewBox="0 0 24 24" className="wxAvatarDefaultIcon" aria-hidden>
                                <circle cx="12" cy="8" r="4" />
                                <path d="M4 20c0-4 3.6-6 8-6s8 2 8 6" />
                              </svg>
                            ) : null}
                          </div>
                          <div className="wxAccRow__main">
                            <div className="wxName">{relationName(item)}</div>
                            <div className="wxMeta">已屏蔽消息与资料访问</div>
                          </div>
                          <button
                            type="button"
                            className="wxBtn wxBtn--ghost"
                            disabled={actionLoading}
                            onClick={() => void onRemoveFriendRelation(uid, 'blacklist')}
                          >
                            移出
                          </button>
                        </div>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          ) : null}

          {sectionHead('whitelist', '白名单', whitelist.length)}
          {openSection === 'whitelist' ? (
            <div className="wxAccBody">
              {loading ? (
                <div className="wxNotice">加载中...</div>
              ) : whitelist.length === 0 ? (
                <div className="wxNotice">暂无白名单用户</div>
              ) : (
                <ul className="wxList">
                  {whitelist.map((item) => {
                    const uid = relationUserId(item)
                    const avatarSrc = resolveAvatarSrc(item.avatar)
                    return (
                      <li key={`white-${uid}`}>
                        <div className="wxAccRow wxAccRow--static">
                          <div
                            className="wxAvatar"
                            style={avatarSrc ? { backgroundImage: `url(${avatarSrc})`, backgroundSize: 'cover' } : undefined}
                          >
                            {!avatarSrc ? (
                              <svg viewBox="0 0 24 24" className="wxAvatarDefaultIcon" aria-hidden>
                                <circle cx="12" cy="8" r="4" />
                                <path d="M4 20c0-4 3.6-6 8-6s8 2 8 6" />
                              </svg>
                            ) : null}
                          </div>
                          <div className="wxAccRow__main">
                            <div className="wxName">{relationName(item)}</div>
                            <div className="wxMeta">允许优先通过隐私规则</div>
                          </div>
                          <button
                            type="button"
                            className="wxBtn wxBtn--ghost"
                            disabled={actionLoading}
                            onClick={() => void onRemoveFriendRelation(uid, 'whitelist')}
                          >
                            移出
                          </button>
                        </div>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          ) : null}
        </div>

        <ContactsDetailPane
          selection={selection}
          allGroups={groupList}
          onHandleRequest={onHandleRequest}
          requestPendingId={requestPendingId}
          onRenameFriendGroup={onRenameFriendGroup}
          onDeleteFriendGroup={onDeleteFriendGroup}
          onAssignFriendToGroup={onAssignFriendToGroup}
          assignGroupLoading={actionLoading}
          onStartChat={onStartChat}
          onAddFriendRelation={onAddFriendRelation}
        />
      </div>
    </div>
  )
}
