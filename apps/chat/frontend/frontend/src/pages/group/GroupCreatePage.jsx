import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { listFriends } from '../../api/friends.js'
import { createGroup } from '../../api/groupApi.js'
import CreateGroupForm from '../../components/group/create/CreateGroupForm.jsx'
import FriendSelectList from '../../components/group/create/FriendSelectList.jsx'
import SelectedFriendBar from '../../components/group/create/SelectedFriendBar.jsx'
import { useCurrentUserId } from '../../hooks/useCurrentUserId.js'
import { mockFriends } from '../../mock/friends.js'
import { getFriendDisplayName } from '../../utils/friends.js'
import { userFacingError } from '../../utils/userFacingError.js'

export default function GroupCreatePage() {
  const navigate = useNavigate()
  const { userId: currentUserId, username: meUsername } = useCurrentUserId()
  const [friends, setFriends] = useState([])
  const [loadingFriends, setLoadingFriends] = useState(true)
  /** @type {[Set<string>, Function]} */
  const [selectedIds, setSelectedIds] = useState(() => new Set())
  const [name, setName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoadingFriends(true)
      try {
        const data = await listFriends({ page: 1, pageSize: 200 })
        const rows = Array.isArray(data?.results) ? data.results : []
        if (!cancelled) setFriends(rows)
      } catch {
        if (!cancelled) setFriends(mockFriends.results || [])
      } finally {
        if (!cancelled) setLoadingFriends(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const selectedFriends = useMemo(
    () => friends.filter((f) => selectedIds.has(String(f.user_id ?? ''))),
    [friends, selectedIds],
  )

  const autoName = useMemo(() => {
    if (selectedFriends.length === 0) return '群聊'
    const selfLabel = (typeof meUsername === 'string' ? meUsername.trim() : '') || '我'
    const peerNames = selectedFriends
      .filter((f) => currentUserId == null || Number(f.user_id) !== Number(currentUserId))
      .map((f) => getFriendDisplayName(f))
      .filter(Boolean)
    const names = [selfLabel, ...peerNames]
    if (names.length <= 3) return `${names.join('、')}的群聊`
    return `${names.slice(0, 3).join('、')}等的群聊`
  }, [selectedFriends, currentUserId, meUsername])

  function toggleId(userId) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(userId)) next.delete(userId)
      else next.add(userId)
      return next
    })
  }

  const canSubmit = selectedIds.size >= 2 && !submitting

  async function onSubmit(e) {
    e.preventDefault()
    setError('')
    if (selectedIds.size < 2) {
      setError('请至少选择 2 位好友')
      return
    }
    const memberIds = [...selectedIds]
    const finalName = (name || '').trim() || autoName
    setSubmitting(true)
    try {
      const g = await createGroup({ name: finalName, memberIds })
      if (!g?.id) throw new Error('未返回群会话 ID')
      navigate(`/groups/${g.id}`)
    } catch (err) {
      setError(userFacingError(err, '创建群聊失败'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="wxPage groupPage">
      <div className="wxHeader">
        <div className="wxHeader__left">
          <Link className="wxBack" to="/groups" aria-label="返回群列表">
            ‹
          </Link>
          <div>
            <div className="wxTitle">创建群聊</div>
            <div className="wxSub">从好友中多选成员；创建者将默认为群主。</div>
          </div>
        </div>
      </div>

      {error ? <div className="wxNotice is-err">{error}</div> : null}

      <SelectedFriendBar count={selectedIds.size} />

      <CreateGroupForm
        name={name}
        onNameChange={setName}
        canSubmit={canSubmit}
        loading={submitting}
        onSubmit={onSubmit}
      />

      <section className="groupCard" style={{ marginTop: 16 }}>
        <h2 className="groupCard__title">选择好友</h2>
        {loadingFriends ? (
          <div className="wxNotice">加载好友列表…</div>
        ) : friends.length === 0 ? (
          <div className="wxNotice">暂无好友，无法创建群聊。</div>
        ) : (
          <FriendSelectList friends={friends} selectedIds={selectedIds} onToggle={toggleId} />
        )}
      </section>
    </div>
  )
}
