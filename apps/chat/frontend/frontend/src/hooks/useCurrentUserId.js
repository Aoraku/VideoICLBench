import { useEffect, useState } from 'react'
import { getMe } from '../api/users.js'

/**
 * 从 GET /users/me 取当前用户，用于聊天区「己方」样式与乐观消息展示。
 */
export function useCurrentUserId() {
  const [userId, setUserId] = useState(null)
  const [username, setUsername] = useState('')
  const [avatar, setAvatar] = useState(/** @type {string|null} */ (null))
  const [status, setStatus] = useState({ presence: '', status_text: '', status_emoji: '' })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const me = await getMe()
        const id = me?.user_id ?? me?.id
        if (!cancelled && id != null) setUserId(Number(id))
        if (!cancelled) {
          setUsername(typeof me?.username === 'string' ? me.username : '')
          setAvatar(me?.avatar != null ? String(me.avatar) : null)
          setStatus(me?.status && typeof me.status === 'object' ? me.status : { presence: '', status_text: '', status_emoji: '' })
        }
      } catch {
        if (!cancelled) {
          setUserId(null)
          setUsername('')
          setAvatar(null)
          setStatus({ presence: '', status_text: '', status_emoji: '' })
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  return { userId, username, avatar, status, loading }
}
