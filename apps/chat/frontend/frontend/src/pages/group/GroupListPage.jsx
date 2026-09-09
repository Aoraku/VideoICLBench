import { Link } from 'react-router-dom'
import { resolveAvatarSrc } from '../../utils/avatarUrl.js'
import { useGroupList } from '../../hooks/group/useGroupList.js'

export default function GroupListPage() {
  const { groups, loading, error, refetch } = useGroupList()

  return (
    <div className="wxPage groupPage">
      <div className="wxHeader">
        <div className="wxHeader__left">
          <Link className="wxBack" to="/contacts" aria-label="返回通讯录">
            ‹
          </Link>
          <div>
            <div className="wxTitle">群聊</div>
            <div className="wxSub">从会话中筛选的群聊列表；可创建新群或进入群资料页。</div>
          </div>
        </div>
        <div className="wxActions">
          <Link className="wxBtn wxBtn--primary" to="/groups/create">
            创建群聊
          </Link>
          <button type="button" className="wxBtn" onClick={() => refetch()} disabled={loading}>
            {loading ? '刷新中…' : '刷新'}
          </button>
        </div>
      </div>

      {error ? <div className="wxNotice is-err">{error}</div> : null}

      {loading && groups.length === 0 ? (
        <div className="wxNotice">加载中…</div>
      ) : groups.length === 0 ? (
        <div className="wxNotice">暂无群聊，可先创建群聊或从聊天里加入群。</div>
      ) : (
        <ul className="wxList groupListPage__list">
          {groups.map((g) => {
            const src = resolveAvatarSrc(g.avatar)
            return (
              <li key={g.id}>
                <div className="groupListPage__row">
                  <div
                    className="wxAvatar"
                    style={src ? { backgroundImage: `url(${src})`, backgroundSize: 'cover' } : undefined}
                  >
                    {!src ? (
                      <svg viewBox="0 0 24 24" className="wxAvatarDefaultIcon" aria-hidden>
                        <circle cx="12" cy="8" r="4" />
                        <path d="M4 20c0-4 3.6-6 8-6s8 2 8 6" />
                      </svg>
                    ) : null}
                  </div>
                  <div className="groupListPage__rowMain">
                    <div className="wxName">{g.name}</div>
                    <div className="wxMeta">
                      会话 ID {g.id}
                      {g.memberCount ? ` · ${g.memberCount} 人` : ''}
                    </div>
                  </div>
                  <Link className="wxBtnLink" to={`/groups/${g.id}`}>
                    群资料
                  </Link>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
