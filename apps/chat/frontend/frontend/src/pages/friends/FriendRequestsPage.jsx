import { useEffect, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { createPrivateConversation } from '../../api/conversations.js'
import { handleFriendRequest, listFriendRequests } from '../../api/friends.js'
import { CHAT_EVENT_CONVERSATION_REFRESH } from '../../constants/chatEvents.js'
import { mockFriendRequests } from '../../mock/friends.js'
import { resolveAvatarSrc } from '../../utils/avatarUrl.js'
import { userFacingError } from '../../utils/userFacingError.js'

export default function FriendRequestsPage() {
  const [activeType, setActiveType] = useState('received')
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [pendingId, setPendingId] = useState(null)
  const navigate = useNavigate()
  const emptyText =
    activeType === 'received' ? '暂无收到的好友申请' : '暂无发出的好友申请'

  useEffect(() => {
    fetchRequests(activeType)
  }, [activeType])

  async function fetchRequests(type) {
    setLoading(true)
    setError('')
    try {
      const data = await listFriendRequests({ type, status: 'all', page: 1, pageSize: 20 })
      setItems(Array.isArray(data?.results) ? data.results : [])
    } catch (err) {
      setItems(mockFriendRequests[type]?.results || [])
      setError(userFacingError(err, '暂时无法加载好友申请'))
    } finally {
      setLoading(false)
    }
  }

  async function onHandle(requestId, action) {
    setPendingId(requestId)
    setError('')
    const rowSnapshot = items.find((it) => it.request_id === requestId)
    try {
      await handleFriendRequest(requestId, action)
      setItems((prev) =>
        prev.map((item) =>
          item.request_id === requestId
            ? { ...item, status: action === 'accept' ? 'accepted' : 'rejected' }
            : item,
        ),
      )

      if (action === 'accept' && activeType === 'received') {
        const peerId = rowSnapshot?.from_user_id ?? rowSnapshot?.from_user?.user_id
        if (peerId != null) {
          try {
            await createPrivateConversation(Number(peerId))
          } catch {
            /* 409 已有会话等可忽略 */
          }
        }
        window.dispatchEvent(new CustomEvent(CHAT_EVENT_CONVERSATION_REFRESH))
        navigate('/contacts?refresh=1', { replace: true })
      }
    } catch (err) {
      setError(userFacingError(err, '处理失败'))
    } finally {
      setPendingId(null)
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
            <div className="wxTitle">好友申请</div>
            <div className="wxSub">{activeType === 'received' ? '处理收到的请求' : '查看已发送的请求状态'}</div>
          </div>
        </div>
      </div>

      <div className="wxCard">
        <div className="wxToolbar">
          <div className="wxSearchRow" aria-label="tabs">
            <button className={activeType === 'received' ? 'wxBtn wxBtn--primary' : 'wxBtn'} onClick={() => setActiveType('received')} disabled={loading}>
              收到的
            </button>
            <button className={activeType === 'sent' ? 'wxBtn wxBtn--primary' : 'wxBtn'} onClick={() => setActiveType('sent')} disabled={loading}>
              发出的
            </button>
          </div>
        </div>

        {loading ? <div className="wxNotice">加载中...</div> : null}
        {error ? <div className="wxNotice is-err">{error}</div> : null}

        <ul className="wxList">
          {items.map((item) => {
            const peer =
              activeType === 'received'
                ? { user_id: item.from_user_id, username: item.from_username, avatar: item.from_avatar || item.from_user?.avatar }
                : { user_id: item.to_user_id, username: item.to_username, avatar: item.to_avatar || item.to_user?.avatar }
            const avatarSrc = resolveAvatarSrc(peer.avatar)
            const canHandle = activeType === 'received' && item.status === 'pending'
            const statusText =
              item.status === 'pending' ? '待处理' : item.status === 'accepted' ? '已同意' : '已拒绝'
            return (
              <li key={item.request_id} className="wxItem">
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
                    <div className="wxName">{peer?.username || '未知用户'}</div>
                  </div>
                  <div className="wxMeta">
                    来源：{item.source || 'search'} · {statusText}
                  </div>
                  <div className="wxMeta">留言：{item.message || '-'}</div>
                </div>
                <div className="wxActions">
                  {canHandle ? (
                    <>
                      <button className="wxBtn wxBtn--primary" onClick={() => onHandle(item.request_id, 'accept')} disabled={pendingId === item.request_id}>
                        同意
                      </button>
                      <button className="wxBtn" onClick={() => onHandle(item.request_id, 'reject')} disabled={pendingId === item.request_id}>
                        拒绝
                      </button>
                    </>
                  ) : (
                    <span className="wxMeta">{statusText}</span>
                  )}
                </div>
              </li>
            )
          })}
        </ul>

        {!loading && items.length === 0 ? <div className="wxNotice">{emptyText}</div> : null}
      </div>
    </div>
  )
}
