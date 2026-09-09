import { useState } from 'react'
import { Link } from 'react-router-dom'
import { searchUsers } from '../../api/users.js'
import { sendFriendRequest } from '../../api/friends.js'
import { mockSearchUsers } from '../../mock/friends.js'
import { resolveAvatarSrc } from '../../utils/avatarUrl.js'
import { getPresenceLabel, presenceClass } from '../../utils/friends.js'
import { userFacingError } from '../../utils/userFacingError.js'

export default function SearchPage() {
  const [keyword, setKeyword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [results, setResults] = useState([])
  const [pendingMap, setPendingMap] = useState({})
  const [notice, setNotice] = useState('')

  async function onSearch(event) {
    event.preventDefault()
    if (!keyword.trim()) {
      setError('请输入关键词')
      setResults([])
      return
    }
    setError('')
    setNotice('')
    setLoading(true)
    try {
      const data = await searchUsers({ keyword: keyword.trim(), page: 1, pageSize: 20 })
      setResults(Array.isArray(data?.results) ? data.results : [])
    } catch (err) {
      // 联调前允许使用 mock 回退，避免阻塞页面开发
      const mockResults = mockSearchUsers.results.filter((item) =>
        item.username.toLowerCase().includes(keyword.trim().toLowerCase()),
      )
      setResults(mockResults)
      setError(userFacingError(err, '搜索失败'))
    } finally {
      setLoading(false)
    }
  }

  async function onSendRequest(targetUserId) {
    setPendingMap((prev) => ({ ...prev, [targetUserId]: true }))
    setNotice('')
    try {
      await sendFriendRequest({ targetUserId, source: 'search', message: '你好，想加你为好友' })
      setNotice('好友申请已发送')
    } catch (err) {
      setNotice(userFacingError(err, '发送失败'))
    } finally {
      setPendingMap((prev) => ({ ...prev, [targetUserId]: false }))
    }
  }

  return (
    <div className="wxPage">
      <div className="wxHeader">
        <div className="wxHeader__left">
          <Link className="wxBack" to="/contacts" aria-label="返回">
            ←
          </Link>
          <div>
            <div className="wxTitle">搜索用户</div>
          </div>
        </div>
      </div>

      <div className="wxCard">
        <div className="wxToolbar">
          <form onSubmit={onSearch} className="wxSearchRow">
            <input
              className="wxSearchInput"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="输入用户名关键词"
            />
            <button className="wxBtn wxBtn--primary" type="submit" disabled={loading}>
              {loading ? '搜索中...' : '搜索'}
            </button>
          </form>
        </div>

        {error ? <div className="wxNotice is-err">{error}</div> : null}
        {notice ? <div className={notice.includes('已发送') ? 'wxNotice is-ok' : 'wxNotice is-err'}>{notice}</div> : null}

        <ul className="wxList">
          {results.map((item) => {
            const avatarSrc = resolveAvatarSrc(item.avatar)
            return (
              <li key={item.user_id} className="wxItem">
                <div
                  className="wxAvatar"
                  style={
                    avatarSrc
                      ? { backgroundImage: `url(${avatarSrc})`, backgroundSize: 'cover', backgroundPosition: 'center' }
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
              <div className="wxMain">
                <div className="wxNameRow">
                  <div className="wxName">{item.username}</div>
                </div>
                <div className="wxMeta">
                  <span className="wxPresenceInline">
                    <span className={`presenceDot ${presenceClass(item.status?.presence)}`} aria-hidden />
                    {getPresenceLabel(item.status?.presence)}
                    {item.status?.status_emoji ? ` · ${item.status.status_emoji}` : ''}
                  </span>
                </div>
              </div>
              <div className="wxActions">
                <button className="wxBtn wxBtn--primary" onClick={() => onSendRequest(item.user_id)} disabled={Boolean(pendingMap[item.user_id])}>
                  {pendingMap[item.user_id] ? '发送中...' : '加好友'}
                </button>
                <Link className="wxBtnLink" to={`/user/${item.user_id}`}>
                  详情
                </Link>
              </div>
              </li>
            )
          })}
        </ul>

        {!loading && results.length === 0 ? <div className="wxNotice">暂无结果</div> : null}
      </div>
    </div>
  )
}
