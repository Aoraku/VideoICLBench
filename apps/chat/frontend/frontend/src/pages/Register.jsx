import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { register } from '../api/auth.js'
import { userFacingError } from '../utils/userFacingError.js'

function validateUsername(v) {
  if (!v) return '请输入用户名'
  if (!/^[a-zA-Z0-9_]{3,20}$/.test(v)) return '用户名需为 3-20 位字母/数字/下划线'
  return ''
}

function validatePassword(v) {
  if (!v) return '请输入密码'
  if (v.length < 8 || v.length > 32) return '密码长度需为 8-32 位'
  const kinds = Number(/[a-z]/.test(v)) + Number(/[A-Z]/.test(v)) + Number(/[0-9]/.test(v))
  if (kinds < 2) return '密码需包含至少两类：大写/小写/数字'
  return ''
}

function validateEmail(v) {
  if (!v) return ''
  if (!/^\S+@\S+\.\S+$/.test(v)) return '邮箱格式不合法'
  return ''
}

function validatePhone(v) {
  if (!v) return ''
  if (!/^\d{11}$/.test(v)) return '手机号格式应为 11 位数字'
  return ''
}

export default function RegisterPage() {
  const nav = useNavigate()
  const [form, setForm] = useState({ username: '', password: '', email: '', phone: '' })
  const [errors, setErrors] = useState({})
  const [serverError, setServerError] = useState('')
  const [loading, setLoading] = useState(false)

  const canSubmit = useMemo(() => !loading, [loading])

  const validateAll = () => {
    const next = {}
    const u = validateUsername(form.username)
    if (u) next.username = u
    const p = validatePassword(form.password)
    if (p) next.password = p
    const e = validateEmail(form.email)
    if (e) next.email = e
    const ph = validatePhone(form.phone)
    if (ph) next.phone = ph
    return next
  }

  const onSubmit = async (e) => {
    e.preventDefault()
    setServerError('')
    const nextErrors = validateAll()
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length) return

    setLoading(true)
    try {
      await register({
        username: form.username,
        password: form.password,
        email: form.email || undefined,
        phone: form.phone || undefined,
      })
      nav('/login', { replace: true, state: { registered: true } })
    } catch (err) {
      setServerError(userFacingError(err, '注册失败'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-content">
      <div className="auth-title">Create an Account</div>

      <form onSubmit={onSubmit} className="auth-form">
        <label className="auth-field">
          <div className="auth-label">Username</div>
          <input
            value={form.username}
            onChange={(e) => {
              setForm((prev) => ({ ...prev, username: e.target.value }))
              setErrors((prev) => ({ ...prev, username: undefined }))
            }}
            placeholder="3-20 letters/numbers/_"
          />
          {errors.username ? <div className="auth-error">{errors.username}</div> : null}
        </label>

        <label className="auth-field">
          <div className="auth-label">Password</div>
          <input
            type="password"
            value={form.password}
            onChange={(e) => {
              setForm((prev) => ({ ...prev, password: e.target.value }))
              setErrors((prev) => ({ ...prev, password: undefined }))
            }}
            placeholder="8-32 chars, 2 kinds"
          />
          {errors.password ? <div className="auth-error">{errors.password}</div> : null}
        </label>

        <label className="auth-field">
          <div className="auth-label">Email (optional)</div>
          <input
            value={form.email}
            onChange={(e) => {
              setForm((prev) => ({ ...prev, email: e.target.value }))
              setErrors((prev) => ({ ...prev, email: undefined }))
            }}
            placeholder="alice@example.com"
          />
          {errors.email ? <div className="auth-error">{errors.email}</div> : null}
        </label>

        <label className="auth-field">
          <div className="auth-label">Phone (optional)</div>
          <input
            value={form.phone}
            onChange={(e) => {
              setForm((prev) => ({ ...prev, phone: e.target.value }))
              setErrors((prev) => ({ ...prev, phone: undefined }))
            }}
            placeholder="11 digits"
          />
          {errors.phone ? <div className="auth-error">{errors.phone}</div> : null}
        </label>

        {serverError ? <div className="auth-error" style={{ marginTop: 4 }}>{serverError}</div> : null}

        <button type="submit" disabled={!canSubmit} className="auth-primary">
          {loading ? 'Creating...' : 'Create'}
        </button>
      </form>

      <div className="auth-footer">
        <Link to="/login">Back to Login</Link>
      </div>
    </div>
  )
}

