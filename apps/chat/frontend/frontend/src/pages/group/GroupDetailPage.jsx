import { useMemo } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import GroupAnnouncementHistory from '../../components/group/info/GroupAnnouncementHistory.jsx'
import GroupInfoPanel from '../../components/group/info/GroupInfoPanel.jsx'
import GroupMemberList from '../../components/group/info/GroupMemberList.jsx'
import GroupAdminActionArea from '../../components/group/layout/GroupAdminActionArea.jsx'
import GroupDetailLayout from '../../components/group/layout/GroupDetailLayout.jsx'
import { useGroupDetail } from '../../hooks/group/useGroupDetail.js'
import { resolveAvatarSrc } from '../../utils/avatarUrl.js'

export default function GroupDetailPage() {
  const { groupId } = useParams()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const from = searchParams.get('from') || ''
  const backTo = useMemo(() => {
    const gid = groupId || ''
    if (!gid) return '/groups'
    if (from === 'chat') return `/chat?open=${encodeURIComponent(gid)}`
    if (from === 'contacts') return '/contacts'
    return '/groups'
  }, [from, groupId])
  const afterDissolveTo = useMemo(() => {
    if (from === 'chat') return '/chat'
    if (from === 'contacts') return '/contacts'
    return '/groups'
  }, [from])
  const {
    group,
    members,
    announcements,
    currentUserRole,
    myGroupNickname,
    latestAnnouncement,
    loading,
    error,
    refetch,
  } = useGroupDetail(groupId)

  const headerAvatar = resolveAvatarSrc(group?.avatar)

  /** 与历史列表去重：已在 announcements 中的最新公告不再在信息区重复展示 */
  const latestForInfoPanel = useMemo(() => {
    if (!latestAnnouncement?.content) return null
    if (announcements.some((a) => a.id === latestAnnouncement.id)) return null
    return latestAnnouncement
  }, [latestAnnouncement, announcements])

  return (
    <div className="wxPage groupPage">
      <div className="wxHeader">
        <div className="wxHeader__left">
          <Link className="wxBack" to={backTo} aria-label="返回">
            ‹
          </Link>
          {headerAvatar ? (
            <img className="groupPage__headerAvatar" src={headerAvatar} alt="" width={40} height={40} />
          ) : null}
          <div>
            <div className="wxTitle">{group?.name || '群资料'}</div>
            <div className="wxSub">会话 ID {groupId}</div>
          </div>
        </div>
        <div className="wxActions">
          <Link className="wxBtnLink" to={`/chat?open=${encodeURIComponent(groupId || '')}`}>
            进入聊天
          </Link>
          <button type="button" className="wxBtn" onClick={() => refetch()} disabled={loading}>
            {loading ? '刷新中…' : '刷新'}
          </button>
        </div>
      </div>

      {error ? <div className="wxNotice is-err">{error}</div> : null}
      {loading && !group ? <div className="wxNotice">加载中…</div> : null}

      {group ? (
        <GroupDetailLayout>
          <div className="groupDetailLayout__grid">
            <div className="groupDetailLayout__col groupDetailLayout__col--main">
              <GroupInfoPanel
                groupId={groupId || ''}
                group={group}
                members={members}
                currentUserRole={currentUserRole}
                myGroupNickname={myGroupNickname}
                latestAnnouncement={latestForInfoPanel}
                onRefresh={refetch}
                onDissolved={() => navigate(afterDissolveTo, { replace: true })}
              />
              <GroupMemberList members={members} />
              <GroupAnnouncementHistory announcements={announcements} />
            </div>
            <aside className="groupDetailLayout__col groupDetailLayout__col--side">
              <GroupAdminActionArea
                groupId={groupId || ''}
                currentUserRole={currentUserRole}
                members={members}
                isGroupMember
                onChanged={refetch}
              />
            </aside>
          </div>
        </GroupDetailLayout>
      ) : null}
    </div>
  )
}
