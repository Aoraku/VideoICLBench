import { useMemo, useState } from 'react'
import './App.css'
import { register } from './api/auth.js'
import { userFacingError } from './utils/userFacingError.js'

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

function App() {
  const [form, setForm] = useState({ username: '', password: '', email: '', phone: '' })
  const [errors, setErrors] = useState({})
  const [serverError, setServerError] = useState('')
  const [okMsg, setOkMsg] = useState('')
  const [loading, setLoading] = useState(false)

  const canSubmit = useMemo(() => {
    if (loading) return false
    return true
  }, [loading])

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
    setOkMsg('')
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
      setOkMsg('注册成功')
      setForm({ username: '', password: '', email: '', phone: '' })
    } catch (err) {
      setServerError(userFacingError(err, '注册失败'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <main style={{ maxWidth: 520, margin: '0 auto', padding: 24, textAlign: 'left' }}>
      <h1 style={{ marginTop: 0 }}>用户注册</h1>

      <form onSubmit={onSubmit} className="card" style={{ textAlign: 'left' }}>
        <label style={{ display: 'block', marginBottom: 12 }}>
          <div>用户名 *</div>
          <input
            value={form.username}
            onChange={(e) => {
              setForm((prev) => ({ ...prev, username: e.target.value }))
              setErrors((prev) => ({ ...prev, username: undefined }))
            }}
            placeholder="3-20 位字母/数字/下划线"
            style={{ width: '100%', padding: 10, marginTop: 6 }}
          />
          {errors.username ? <div style={{ color: '#FF4D4F', fontSize: 12, marginTop: 6 }}>{errors.username}</div> : null}
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div>密码 *</div>
          <input
            type="password"
            value={form.password}
            onChange={(e) => {
              setForm((prev) => ({ ...prev, password: e.target.value }))
              setErrors((prev) => ({ ...prev, password: undefined }))
            }}
            placeholder="8-32 位，至少两类"
            style={{ width: '100%', padding: 10, marginTop: 6 }}
          />
          {errors.password ? <div style={{ color: '#FF4D4F', fontSize: 12, marginTop: 6 }}>{errors.password}</div> : null}
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div>邮箱（可选）</div>
          <input
            value={form.email}
            onChange={(e) => {
              setForm((prev) => ({ ...prev, email: e.target.value }))
              setErrors((prev) => ({ ...prev, email: undefined }))
            }}
            placeholder="alice@example.com"
            style={{ width: '100%', padding: 10, marginTop: 6 }}
          />
          {errors.email ? <div style={{ color: '#FF4D4F', fontSize: 12, marginTop: 6 }}>{errors.email}</div> : null}
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div>手机号（可选）</div>
          <input
            value={form.phone}
            onChange={(e) => {
              setForm((prev) => ({ ...prev, phone: e.target.value }))
              setErrors((prev) => ({ ...prev, phone: undefined }))
            }}
            placeholder="11 位数字"
            style={{ width: '100%', padding: 10, marginTop: 6 }}
          />
          {errors.phone ? <div style={{ color: '#FF4D4F', fontSize: 12, marginTop: 6 }}>{errors.phone}</div> : null}
        </label>

        {serverError ? <div style={{ color: '#FF4D4F', marginTop: 8 }}>{serverError}</div> : null}
        {okMsg ? <div style={{ color: '#52C41A', marginTop: 8 }}>{okMsg}</div> : null}

        <button type="submit" disabled={!canSubmit} style={{ marginTop: 14, width: '100%' }}>
          {loading ? '注册中...' : '注册'}
        </button>
      </form>
    </main>
  )
}

export default App
