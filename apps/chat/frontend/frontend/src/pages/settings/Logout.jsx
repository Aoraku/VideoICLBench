import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { logout } from '../../api/auth.js'
import { userFacingError } from '../../utils/userFacingError.js'
import { ACCESS_TOKEN_KEY, LAST_SYNC_KEY, REFRESH_TOKEN_KEY } from '../../constants/storage.js'

export default function LogoutPage() {
  const nav = useNavigate()
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState('')

  const doLogout = async () => {
    setMsg('')
    setLoading(true)
    try {
      const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY)
      if (refreshToken) {
        await logout({ refresh_token: refreshToken })
      }
      setMsg('已退出登录')
    } catch (err) {
      // 登出失败也强制清理本地登录态，避免“卡死在旧 token”
      setMsg(userFacingError(err, '已结束会话'))
    } finally {
      localStorage.removeItem(ACCESS_TOKEN_KEY)
      localStorage.removeItem(REFRESH_TOKEN_KEY)
      localStorage.removeItem(LAST_SYNC_KEY)
      setLoading(false)
      nav('/login', { replace: true })
    }
  }

  return (
    <main style={{ maxWidth: 520, margin: '0 auto', padding: 24, textAlign: 'left' }}>
      <h1 style={{ marginTop: 0 }}>退出登录</h1>
      <p style={{ color: '#666' }}>退出后将清除本机的登录状态。</p>

      {msg ? <div style={{ marginTop: 10 }}>{msg}</div> : null}

      <button type="button" onClick={doLogout} disabled={loading} style={{ marginTop: 14, width: '100%' }}>
        {loading ? '处理中...' : '确认退出'}
      </button>
    </main>
  )
}

