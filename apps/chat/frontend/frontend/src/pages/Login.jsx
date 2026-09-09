import { useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { login } from '../api/auth.js'
import { syncMessages } from '../api/sync.js'
import { userFacingError } from '../utils/userFacingError.js'
import { ACCESS_TOKEN_KEY, LAST_SYNC_KEY, REFRESH_TOKEN_KEY } from '../constants/storage.js'

function detectLoginType(identifier) {
  const v = String(identifier || '').trim()
  if (/^\d{11}$/.test(v)) return 'phone'
  if (/^\S+@\S+\.\S+$/.test(v)) return 'email'
  return 'username'
}

function validateIdentifier(v) {
  if (!v) return 'Please enter a valid email address format.'
  const t = detectLoginType(v)
  if (t === 'username' && !/^[a-zA-Z0-9_]{3,20}$/.test(v)) return '用户名需为 3-20 位字母/数字/下划线'
  if (t === 'phone' && !/^\d{11}$/.test(v)) return '手机号格式应为 11 位数字'
  if (t === 'email' && !/^\S+@\S+\.\S+$/.test(v)) return '邮箱格式不合法'
  return ''
}

function validatePassword(v) {
  if (!v) return '请输入密码'
  if (v.length < 8 || v.length > 32) return '密码长度需为 8-32 位'
  return ''
}

export default function LoginPage() {
  const nav = useNavigate()
  const loc = useLocation()
  const registered = Boolean(loc.state?.registered)

  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState({})
  const [serverError, setServerError] = useState('')
  const [loading, setLoading] = useState(false)

  const canSubmit = useMemo(() => !loading, [loading])

  const onSubmit = async (e) => {
    e.preventDefault()
    setServerError('')
    const idErr = validateIdentifier(identifier)
    const pwErr = validatePassword(password)
    const next = {}
    if (idErr) next.identifier = idErr
    if (pwErr) next.password = pwErr
    setErrors(next)
    if (Object.keys(next).length) return

    setLoading(true)
    try {
      const login_type = detectLoginType(identifier)
      const data = await login({ login_type, identifier: identifier.trim(), password })
      if (data?.access_token) localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token)
      if (data?.refresh_token) localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token)

      // 登录后拉取离线增量消息
      try {
        const since = localStorage.getItem(LAST_SYNC_KEY) || new Date(0).toISOString()
        const sync = await syncMessages({ since, limit: 200 })
        if (sync?.sync_timestamp) localStorage.setItem(LAST_SYNC_KEY, sync.sync_timestamp)
      } catch {
        // 同步失败不阻塞登录（避免后端未接入时卡死）
      }

      nav('/contacts', { replace: true })
    } catch (err) {
      const code = err?.code
      if (code === 'INVALID_CREDENTIALS' || code === 'ACCOUNT_NOT_FOUND') setServerError('账号或密码错误')
      else setServerError(userFacingError(err, '登录失败'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-content">
      <div className="auth-title">Welcome Back</div>
      {registered ? <div className="auth-hint auth-hint--ok">注册成功，请登录。</div> : null}

      <form onSubmit={onSubmit} className="auth-form">
        <label className="auth-field">
          <div className="auth-label">Email/Username</div>
          <input
            value={identifier}
            onChange={(e) => {
              setIdentifier(e.target.value)
              setErrors((prev) => ({ ...prev, identifier: undefined }))
            }}
            placeholder=" "
          />
          {errors.identifier ? <div className="auth-error">{errors.identifier}</div> : null}
        </label>

        <label className="auth-field">
          <div className="auth-label">Password</div>
          <input
            type="password"
            value={password}
            onChange={(e) => {
              setPassword(e.target.value)
              setErrors((prev) => ({ ...prev, password: undefined }))
            }}
            placeholder=" "
          />
          {errors.password ? <div className="auth-error">{errors.password}</div> : null}
        </label>

        {serverError ? <div className="auth-error" style={{ marginTop: 4 }}>{serverError}</div> : null}

        <button type="submit" disabled={!canSubmit} className="auth-primary">
          {loading ? 'Log In...' : 'Log In'}
        </button>
      </form>

      <div className="auth-footer">
        <Link to="/register">Create an Account</Link>
      </div>
    </div>
  )
}

