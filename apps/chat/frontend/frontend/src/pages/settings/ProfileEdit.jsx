import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  clearAiKey,
  getAiKeySettings,
  getMe,
  getPrivacy,
  updateAiKey,
  updateMe,
  updatePrivacy,
  uploadAvatar,
} from '../../api/users.js'
import { resolveAvatarSrc } from '../../utils/avatarUrl.js'
import { userFacingError } from '../../utils/userFacingError.js'

function shortName(name) {
  const v = String(name || '').trim()
  return v ? v.slice(0, 1).toUpperCase() : '?'
}

const mockMe = {
  user_id: 1001,
  username: 'James Camille',
  avatar: null,
  email: 'jmt24@mails.tsinghua.edu.cn',
  phone: '15504625108',
  created_at: '2026-03-14T10:00:00Z',
}

export default function ProfileEditPage() {
  const [me, setMe] = useState(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const [privacy, setPrivacy] = useState(null)
  const [privacySavingKey, setPrivacySavingKey] = useState('')
  const [aiKeyInfo, setAiKeyInfo] = useState(null)
  const [aiKeyInput, setAiKeyInput] = useState('')
  const [aiKeySaving, setAiKeySaving] = useState(false)

  /** 本地上传预览（不改后端时服务端 /media 可能不可达，用 blob URL 保证当次会话能显示） */
  const [avatarPreviewUrl, setAvatarPreviewUrl] = useState(null)
  const avatarPreviewRef = useRef(null)

  const replaceAvatarPreview = (nextUrl) => {
    if (avatarPreviewRef.current) {
      URL.revokeObjectURL(avatarPreviewRef.current)
      avatarPreviewRef.current = null
    }
    if (nextUrl) avatarPreviewRef.current = nextUrl
    setAvatarPreviewUrl(nextUrl)
  }

  const [form, setForm] = useState({
    username: '',
    phone: '',
    email: '',
    password: '',
    old_password: '',
  })
  // 浏览器可能会自动把登录密码塞进任意 password 输入框：只有用户真的改动过密码框，才计入“已修改”
  const [passwordTouched, setPasswordTouched] = useState(false)
  const [oldPasswordTouched, setOldPasswordTouched] = useState(false)
  const newPasswordRef = useRef(null)
  const oldPasswordRef = useRef(null)

  const emailChanged = useMemo(() => {
    if (!me) return false
    return (form.email || '') !== (me.email || '')
  }, [form.email, me])

  const phoneChanged = useMemo(() => {
    if (!me) return false
    return (form.phone || '') !== (me.phone || '')
  }, [form.phone, me])

  const passwordChanged = Boolean(form.password)
  const sensitiveChanged = emailChanged || phoneChanged || passwordChanged

  /** 仅这五类字段变更时才允许点「保存修改」；头像单独上传不走此按钮 */
  const profileFieldsDirty = useMemo(() => {
    if (!me) return false
    const usernameSame = (form.username || '') === (me.username ?? '')
    const phoneSame = (form.phone || '') === (me.phone ?? '')
    const emailSame = (form.email || '') === (me.email ?? '')
    // 未 touched 时忽略密码框（防止自动填充导致按钮一直是“已修改”）
    const passwordEmpty = !passwordTouched || !form.password
    const oldPasswordEmpty = !sensitiveChanged || !oldPasswordTouched || !form.old_password
    return !(usernameSame && phoneSame && emailSame && passwordEmpty && oldPasswordEmpty)
  }, [
    form.username,
    form.phone,
    form.email,
    form.password,
    form.old_password,
    me,
    passwordTouched,
    oldPasswordTouched,
    sensitiveChanged,
  ])

  const loadAccountControls = useCallback(async (baseMe = null) => {
    try {
      const data = await getPrivacy()
      setPrivacy(data)
    } catch {
      if (baseMe?.privacy) setPrivacy(baseMe.privacy)
    }

    try {
      const data = await getAiKeySettings()
      setAiKeyInfo(data)
    } catch {
      setAiKeyInfo(baseMe?.ai_api_key_configured ? { configured: true, masked_key: '已配置' } : { configured: false, masked_key: '' })
    }
  }, [])

  const loadMe = useCallback(async () => {
    setLoading(true)
    setMsg('')
    try {
      const data = await getMe()
      setMe(data)
      setPrivacy(data?.privacy || null)
      setForm((prev) => ({
        ...prev,
        username: data?.username ?? '',
        phone: data?.phone ?? '',
        email: data?.email ?? '',
        password: '',
        old_password: '',
      }))
      setPasswordTouched(false)
      setOldPasswordTouched(false)
      await loadAccountControls(data)
    } catch (err) {
      // 纯前端调 UI：后端未启动时使用 mock，避免页面“卡住”
      setMe(mockMe)
      setPrivacy({
        allow_search_by_username: true,
        allow_search_by_email: true,
        allow_search_by_phone: true,
        allow_add_from_group: true,
      })
      setAiKeyInfo({ configured: false, masked_key: '' })
      setForm((prev) => ({
        ...prev,
        username: mockMe.username,
        phone: mockMe.phone,
        email: mockMe.email,
        password: '',
        old_password: '',
      }))
      setPasswordTouched(false)
      setOldPasswordTouched(false)
      setMsg(userFacingError(err, '暂时无法同步资料'))
    } finally {
      setLoading(false)
    }
  }, [loadAccountControls])

  useEffect(() => {
    loadMe()
  }, [loadMe])

  // 某些浏览器会在页面渲染后异步自动填充 password 输入框：
  // 这里强制清空 DOM value + state，并且不把它计入 dirty。
  useEffect(() => {
    if (!me) return
    const clear = () => {
      if (newPasswordRef.current) newPasswordRef.current.value = ''
      if (oldPasswordRef.current) oldPasswordRef.current.value = ''
      setForm((p) => ({ ...p, password: '', old_password: '' }))
      setPasswordTouched(false)
      setOldPasswordTouched(false)
    }
    // rAF 两次，覆盖“渲染后填充”的时机
    let id2 = 0
    const id1 = requestAnimationFrame(() => {
      id2 = requestAnimationFrame(clear)
    })
    // 额外再延迟一次，覆盖少数浏览器更晚的 autofill
    const t = setTimeout(clear, 120)
    return () => {
      cancelAnimationFrame(id1)
      if (id2) cancelAnimationFrame(id2)
      clearTimeout(t)
    }
  }, [me])

  useEffect(() => {
    return () => {
      if (avatarPreviewRef.current) URL.revokeObjectURL(avatarPreviewRef.current)
    }
  }, [])

  const onSave = async (e) => {
    e.preventDefault()
    setMsg('')

    if (sensitiveChanged && !form.old_password) {
      setMsg('修改手机号、邮箱或密码需要填写当前密码')
      return
    }

    // 邮箱清空视为“不改动”，避免传空串触发后端校验错误
    const emailPayload = form.email === '' ? undefined : form.email

    const payload = {
      username: form.username || undefined,
      phone: form.phone || undefined,
      email: emailPayload,
      password: passwordChanged ? form.password : undefined,
      old_password: sensitiveChanged ? form.old_password : undefined,
    }

    setSaving(true)
    try {
      await updateMe(payload)
      setMsg('保存成功')
      setForm((prev) => ({ ...prev, password: '', old_password: '' }))
      await loadMe()
    } catch (err) {
      setMsg(userFacingError(err, '保存失败'))
    } finally {
      setSaving(false)
    }
  }

  const onTogglePrivacy = async (field, value) => {
    setMsg('')
    setPrivacySavingKey(field)
    try {
      const data = await updatePrivacy({ [field]: value })
      setPrivacy(data)
      setMsg('隐私设置已保存')
    } catch (err) {
      setMsg(userFacingError(err, '隐私设置保存失败'))
    } finally {
      setPrivacySavingKey('')
    }
  }

  const onSaveAiKey = async () => {
    const apiKey = aiKeyInput.trim()
    if (!apiKey) {
      setMsg('请输入 AI API Key')
      return
    }
    setMsg('')
    setAiKeySaving(true)
    try {
      const data = await updateAiKey(apiKey)
      setAiKeyInfo(data)
      setAiKeyInput('')
      setMsg('AI API Key 保存成功')
    } catch (err) {
      setMsg(userFacingError(err, 'AI API Key 保存失败'))
    } finally {
      setAiKeySaving(false)
    }
  }

  const onClearAiKey = async () => {
    setMsg('')
    setAiKeySaving(true)
    try {
      const data = await clearAiKey()
      setAiKeyInfo(data)
      setAiKeyInput('')
      setMsg('AI API Key 已清除')
    } catch (err) {
      setMsg(userFacingError(err, 'AI API Key 清除失败'))
    } finally {
      setAiKeySaving(false)
    }
  }

  return (
    <div className="profilePage">
      <div className="profileHeader">
        <div>
          <div className="profileTitle">个人信息</div>
        </div>

        <div className="profileAvatarWrap">
          {avatarPreviewUrl || me?.avatar ? (
            <img
              className="profileAvatarImg"
              src={avatarPreviewUrl || resolveAvatarSrc(me.avatar)}
              alt="avatar"
            />
          ) : (
            <div className="profileAvatarFallback" aria-label="avatar">
              {shortName(me?.username)}
            </div>
          )}
        </div>
      </div>

      {loading ? <div className="profileHint">加载中...</div> : null}
      {msg ? (
        <div className={msg.includes('成功') ? 'profileHint is-ok' : 'profileHint is-err'}>{msg}</div>
      ) : null}

      <form onSubmit={onSave} className="profileCard" autoComplete="off">
        {/* 诱饵字段：吸走浏览器的账号/密码自动填充，避免污染下面的“新密码/旧密码” */}
        <div style={{ position: 'absolute', left: -99999, width: 1, height: 1, overflow: 'hidden' }} aria-hidden>
          <input type="text" name="username" autoComplete="username" tabIndex={-1} />
          <input type="password" name="password" autoComplete="current-password" tabIndex={-1} />
        </div>

        <div className="profileRow">
          <div className="profileRow__label">个人资料照片</div>
          <div className="profileRow__value">
            <input
              type="file"
              accept="image/*"
              onChange={async (e) => {
                const file = e.target.files?.[0]
                if (!file) return
                setMsg('')
                replaceAvatarPreview(URL.createObjectURL(file))
                try {
                  await uploadAvatar(file)
                  await loadMe()
                  setMsg('头像已更新')
                } catch (err) {
                  replaceAvatarPreview(null)
                  setMsg(userFacingError(err, '上传失败'))
                } finally {
                  e.target.value = ''
                }
              }}
            />
          </div>
        </div>

        <div className="profileRow">
          <div className="profileRow__label">用户名</div>
          <div className="profileRow__value">
            <input value={form.username} onChange={(e) => setForm((p) => ({ ...p, username: e.target.value }))} />
          </div>
        </div>

        <div className="profileRow">
          <div className="profileRow__label">手机号</div>
          <div className="profileRow__value">
            <input value={form.phone} onChange={(e) => setForm((p) => ({ ...p, phone: e.target.value }))} />
          </div>
        </div>

        <div className="profileRow">
          <div className="profileRow__label">邮箱</div>
          <div className="profileRow__value">
            <input
              value={form.email}
              onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))}
              placeholder="邮箱"
            />
          </div>
        </div>

        <div className="profileRow">
          <div className="profileRow__label">新密码</div>
          <div className="profileRow__value">
            <input
              type="password"
              ref={newPasswordRef}
              autoComplete="new-password"
              value={form.password}
              onChange={(e) => {
                setPasswordTouched(true)
                setForm((p) => ({ ...p, password: e.target.value }))
              }}
              placeholder="不修改请留空"
            />
          </div>
        </div>

        <div className="profileRow">
          <div className="profileRow__label">旧密码</div>
          <div className="profileRow__value">
            <input
              type="password"
              ref={oldPasswordRef}
              autoComplete="current-password"
              value={form.old_password}
              onChange={(e) => {
                setOldPasswordTouched(true)
                setForm((p) => ({ ...p, old_password: e.target.value }))
              }}
              placeholder="修改手机号、邮箱或密码时必填"
            />
          </div>
        </div>

        <div className="profileActions">
          <button type="submit" className="profileSaveBtn" disabled={saving || !profileFieldsDirty}>
            {saving ? '保存中...' : '保存修改'}
          </button>
        </div>
      </form>

      <div className="profileCard" style={{ marginTop: 14 }}>
        <div className="profileRow">
          <div className="profileRow__label">AI API Key</div>
          <div className="profileRow__value profileRow__value--stack">
            <div className={aiKeyInfo?.configured ? 'profileHint is-ok' : 'profileHint'}>
              {aiKeyInfo?.configured ? `已配置 ${aiKeyInfo.masked_key || ''}` : '未配置'}
            </div>
            <input
              type="password"
              value={aiKeyInput}
              onChange={(e) => setAiKeyInput(e.target.value)}
              placeholder="输入新的 API Key"
              autoComplete="off"
            />
            <div className="profileRow__value--inline">
              <button type="button" className="profileSaveBtn" disabled={aiKeySaving} onClick={onSaveAiKey}>
                {aiKeySaving ? '保存中...' : '保存'}
              </button>
              <button
                type="button"
                disabled={aiKeySaving || !aiKeyInfo?.configured}
                onClick={onClearAiKey}
              >
                清除
              </button>
            </div>
            {aiKeyInfo?.ai_model || aiKeyInfo?.ai_base_url ? (
              <div className="profileHint">
                {aiKeyInfo?.ai_model || 'AI'} · {aiKeyInfo?.ai_base_url || ''}
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <div className="profileCard" style={{ marginTop: 14 }}>
        <div className="profileRow">
          <div className="profileRow__label">隐私权限</div>
          <div className="profileRow__value profileRow__value--stack">
            {[
              ['allow_search_by_username', '允许通过用户名搜索到我'],
              ['allow_search_by_email', '允许通过邮箱搜索到我'],
              ['allow_search_by_phone', '允许通过手机号搜索到我'],
              ['allow_add_from_group', '允许群成员添加我为好友'],
            ].map(([field, label]) => (
              <label key={field} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <input
                  type="checkbox"
                  checked={Boolean(privacy?.[field])}
                  disabled={!privacy || privacySavingKey === field}
                  onChange={(e) => onTogglePrivacy(field, e.target.checked)}
                />
                {label}
              </label>
            ))}
          </div>
        </div>
      </div>

      <div className="profileCard" style={{ marginTop: 14 }}>
        <div className="profileRow">
          <div className="profileRow__label">账号</div>
          <div className="profileRow__value profileRow__value--stack">
            <Link className="profileLinkBtn" to="/settings/logout">
              退出登录
            </Link>
            <Link className="profileLinkBtn profileLinkBtn--danger" to="/settings/account-delete">
              注销账号（不可撤销）
            </Link>
            <div className="profileHint" style={{ marginTop: 10 }}>注销账号后数据将永久删除且无法恢复。</div>
          </div>
        </div>
      </div>
    </div>
  )
}
