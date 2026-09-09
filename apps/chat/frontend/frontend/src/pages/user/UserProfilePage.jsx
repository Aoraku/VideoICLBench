import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { getUser } from '../../api/users.js'
import { deleteFriend, sendFriendRequest, updateFriendRemark } from '../../api/friends.js'
import { mockUserProfiles } from '../../mock/friends.js'
import { resolveAvatarSrc } from '../../utils/avatarUrl.js'
import { getPresenceLabel, MAX_REMARK_LENGTH, presenceClass, validateRemark } from '../../utils/friends.js'
import { userFacingError } from '../../utils/userFacingError.js'

export default function UserProfilePage() {
  const { userId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [requesting, setRequesting] = useState(false)
  const [requestMsg, setRequestMsg] = useState('')
  const [deleting, setDeleting] = useState(false)

  const [remarkDraft, setRemarkDraft] = useState('')
  const [remarkSaving, setRemarkSaving] = useState(false)
  const [remarkMsg, setRemarkMsg] = useState('')
  const [remarkError, setRemarkError] = useState('')

  const [requestSource, setRequestSource] = useState('search')
  const [requestMessage, setRequestMessage] = useState('你好，想加你为好友')

  useEffect(() => {
    const params = new URLSearchParams(location.search)
    const source = params.get('source')
    const message = params.get('message')
    setRequestSource(source || 'search')
    setRequestMessage(message || '你好，想加你为好友')
  }, [location.search])

  useEffect(() => {
    let mounted = true
    async function fetchProfile() {
      setLoading(true)
      setError('')
      try {
        const data = await getUser(userId)
        if (mounted) {
          setProfile(data)
          setRemarkDraft(data?.remark || '')
        }
      } catch (err) {
        if (mounted) {
          const mock = mockUserProfiles[userId] || null
          setProfile(mock)
          setRemarkDraft(mock?.remark || '')
          setError(userFacingError(err, '暂时无法加载用户资料'))
        }
      } finally {
        if (mounted) setLoading(false)
      }
    }
    fetchProfile()
    return () => {
      mounted = false
    }
  }, [userId])

  async function onSendRequest() {
    if (!profile) return
    setRequesting(true)
    setRequestMsg('')
    try {
      await sendFriendRequest({
        targetUserId: profile.user_id,
        source: requestSource,
        message: requestMessage,
      })
      setRequestMsg('好友申请已发送')
    } catch (err) {
      setRequestMsg(userFacingError(err, '发送失败'))
    } finally {
      setRequesting(false)
    }
  }

  async function onDeleteFriend() {
    if (!profile?.is_friend) return
    const friendUserId = profile.user_id
    const confirmed = window.confirm('确认删除该好友吗？')
    if (!confirmed) return

    setDeleting(true)
    setRequestMsg('')
    try {
      await deleteFriend(friendUserId)
      setProfile((prev) => (prev ? { ...prev, is_friend: false, remark: null } : prev))
      setRequestMsg('已删除好友')
      navigate(`/contacts?deleted=${friendUserId}`)
    } catch (err) {
      setRequestMsg(userFacingError(err, '删除失败'))
      setProfile((prev) => (prev ? { ...prev, is_friend: false, remark: null } : prev))
      navigate(`/contacts?deleted=${friendUserId}`)
    } finally {
      setDeleting(false)
    }
  }

  async function onSaveRemark() {
    if (!profile?.is_friend) return
    setRemarkError('')
    setRemarkSaving(true)
    setRemarkMsg('')
    const validation = validateRemark(remarkDraft)
    if (!validation.ok) {
      setRemarkError(validation.message)
      setRemarkSaving(false)
      return
    }
    const nextRemark = validation.value
    try {
      const updated = await updateFriendRemark(profile.user_id, nextRemark)
      const remark = updated?.remark ?? nextRemark
      const friendUserId = profile.user_id
      setProfile((prev) => (prev ? { ...prev, remark } : prev))
      setRemarkMsg('备注已更新')
      // 同步通讯录页：ContactsPage 统一处理 remarkUpdated 参数
      navigate(`/contacts?remarkUpdated=${friendUserId}&remark=${encodeURIComponent(remark)}`)
    } catch (err) {
      setRemarkError(userFacingError(err, '保存备注失败'))
      setProfile((prev) => (prev ? { ...prev, remark: nextRemark } : prev))
    } finally {
      setRemarkSaving(false)
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
            <div className="wxTitle">用户详情</div>
          </div>
        </div>
      </div>

      {loading ? <div className="wxNotice">加载中...</div> : null}
      {!loading && !profile ? <div className="wxNotice">用户不存在</div> : null}
      {error ? <div className="wxNotice is-err">{error}</div> : null}

      {profile ? (
        <div className="wxCard">
          <div className="wxItem">
            <div
              className="wxAvatar"
              style={
                resolveAvatarSrc(profile.avatar)
                  ? {
                    backgroundImage: `url(${resolveAvatarSrc(profile.avatar)})`,
                    backgroundSize: 'cover',
                    backgroundPosition: 'center',
                  }
                  : undefined
              }
            >
              {!resolveAvatarSrc(profile.avatar) ? (
                <svg viewBox="0 0 24 24" className="wxAvatarDefaultIcon" aria-hidden>
                  <circle cx="12" cy="8" r="4" />
                  <path d="M4 20c0-4 3.6-6 8-6s8 2 8 6" />
                </svg>
              ) : null}
            </div>
            <div className="wxMain">
              <div className="wxNameRow">
                <div className="wxName">{profile.username}</div>
              </div>
              <div className="wxMeta">用户 ID：{profile.user_id}</div>
              <div className="wxMeta">
                在线状态：
                <span className="wxPresenceInline">
                  <span className={`presenceDot ${presenceClass(profile.status?.presence || profile.online_status)}`} aria-hidden />
                  {getPresenceLabel(profile.status?.presence || profile.online_status)}
                </span>
              </div>
              <div className="wxMeta">好友关系：{profile.is_friend ? '已是好友' : '还不是好友'}</div>
              {profile.is_friend ? <div className="wxMeta">备注：{profile.remark || '-'}</div> : null}
            </div>
            <div className="wxActions">
              {!profile.is_friend ? (
                <button className="wxBtn wxBtn--primary" onClick={onSendRequest} disabled={requesting}>
                  {requesting ? '发送中...' : '加为好友'}
                </button>
              ) : (
                <button className="wxBtn" onClick={onDeleteFriend} disabled={deleting}>
                  {deleting ? '删除中...' : '删除好友'}
                </button>
              )}
            </div>
          </div>

          {profile.is_friend ? (
            <div className="wxToolbar">
              <div className="wxSub" style={{ marginBottom: 8 }}>
                编辑备注
              </div>
              <div className="wxSearchRow">
                <input
                  className="wxSearchInput"
                  value={remarkDraft}
                  onChange={(e) => setRemarkDraft(e.target.value)}
                  placeholder="无备注则留空"
                  disabled={remarkSaving}
                />
                <button className="wxBtn wxBtn--primary" type="button" onClick={onSaveRemark} disabled={remarkSaving}>
                  {remarkSaving ? '保存中...' : '保存'}
                </button>
                <button
                  className="wxBtn"
                  type="button"
                  onClick={() => {
                    setRemarkError('')
                    setRemarkMsg('')
                    setRemarkDraft(profile.remark || '')
                  }}
                  disabled={remarkSaving}
                >
                  重置
                </button>
              </div>
              <div className="wxSub" style={{ marginTop: 8 }}>
                {remarkDraft.length}/{MAX_REMARK_LENGTH}
              </div>
              {remarkMsg ? <div className="wxNotice is-ok">{remarkMsg}</div> : null}
              {remarkError ? <div className="wxNotice is-err">{remarkError}</div> : null}
            </div>
          ) : null}

          {requestMsg ? (
            <div className={requestMsg.includes('已') ? 'wxNotice is-ok' : 'wxNotice is-err'}>{requestMsg}</div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
