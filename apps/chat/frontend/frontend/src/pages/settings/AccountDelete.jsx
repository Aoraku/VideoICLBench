import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { deleteAccount } from '../../api/auth.js'
import { userFacingError } from '../../utils/userFacingError.js'
import { ACCESS_TOKEN_KEY, LAST_SYNC_KEY, REFRESH_TOKEN_KEY } from '../../constants/storage.js'

export default function AccountDeletePage() {
  const nav = useNavigate()
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState('')

  const onSubmit = async (e) => {
    e.preventDefault()
    setMsg('')
    if (!password) {
      setMsg('请输入密码')
      return
    }
    const ok = window.confirm('确认注销账号？该操作不可撤销。')
    if (!ok) return

    setLoading(true)
    try {
      await deleteAccount({ password })
      localStorage.removeItem(ACCESS_TOKEN_KEY)
      localStorage.removeItem(REFRESH_TOKEN_KEY)
      localStorage.removeItem(LAST_SYNC_KEY)
      setMsg('注销成功')
      nav('/login', { replace: true })
    } catch (err) {
      setMsg(userFacingError(err, '注销失败'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <main style={{ maxWidth: 520, margin: '0 auto', padding: 24, textAlign: 'left' }}>
      <h1 style={{ marginTop: 0, color: '#FF4D4F' }}>注销账号</h1>
      <p style={{ color: '#666' }}>需要输入密码确认。注销后会清除本地登录态。</p>

      <form onSubmit={onSubmit} style={{ marginTop: 16 }}>
        <label style={{ display: 'block' }}>
          <div>密码</div>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="输入密码"
            style={{ width: '100%', padding: 10, marginTop: 6 }}
          />
        </label>

        {msg ? <div style={{ marginTop: 10, color: msg.includes('成功') ? '#52C41A' : '#FF4D4F' }}>{msg}</div> : null}

        <button type="submit" disabled={loading} style={{ marginTop: 14, width: '100%' }}>
          {loading ? '处理中...' : '确认注销'}
        </button>
      </form>
    </main>
  )
}

