import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { updateStatus } from '../../api/users.js'
import { useCurrentUserId } from '../../hooks/useCurrentUserId.js'
import { resolveAvatarSrc } from '../../utils/avatarUrl.js'
import { getPresenceLabel, presenceClass } from '../../utils/friends.js'

const iconItems = [
  { to: '/chat', label: '会话', icon: 'chat' },
  { to: '/contacts', label: '通讯录', icon: 'contacts' },
  { to: '/groups', label: '群聊', icon: 'groups' },
  { to: '/bookmarks', label: '待办', icon: 'todo' },
  { to: '/calendar', label: '日历', icon: 'calendar' },
  { to: '/settings/profile', label: '设置', icon: 'settings' },
]

const presenceOptions = [
  ['online', '在线'],
  ['busy', '忙碌'],
  ['invisible', '隐身'],
  ['offline', '离线'],
]

function NavIcon({ type }) {
  if (type === 'chat') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden>
        <path d="M5 6.5h14v9H9l-4 3v-12Z" />
      </svg>
    )
  }
  if (type === 'contacts') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden>
        <circle cx="9" cy="9" r="3" />
        <path d="M4.5 18c.7-3 2.3-4.5 4.5-4.5S12.8 15 13.5 18" />
        <path d="M15 7.5a2.5 2.5 0 1 1 0 5" />
        <path d="M15.5 14c2 .4 3.3 1.7 4 4" />
      </svg>
    )
  }
  if (type === 'groups') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden>
        <circle cx="8" cy="8" r="2.5" />
        <circle cx="16" cy="8" r="2.5" />
        <circle cx="12" cy="15" r="2.8" />
        <path d="M4 18c.6-2 2-3.2 4-3.4" />
        <path d="M20 18c-.6-2-2-3.2-4-3.4" />
      </svg>
    )
  }
  if (type === 'todo') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden>
        <path d="M6 7h12" />
        <path d="M6 12h8" />
        <path d="m6 17 2 2 4-5" />
      </svg>
    )
  }
  if (type === 'calendar') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden>
        <rect x="5" y="6" width="14" height="13" rx="2" />
        <path d="M8 4v4M16 4v4M5 10h14" />
      </svg>
    )
  }
  if (type === 'help') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden>
        <circle cx="12" cy="12" r="8" />
        <path d="M9.7 9.5a2.4 2.4 0 0 1 4.6.9c0 1.8-2.3 2.1-2.3 4" />
        <path d="M12 17.2h.01" />
      </svg>
    )
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 3v3M12 18v3M4.2 7.5l2.6 1.5M17.2 15l2.6 1.5M4.2 16.5 6.8 15M17.2 9l2.6-1.5" />
    </svg>
  )
}

export default function MainLayout() {
  const { username, avatar, status } = useCurrentUserId()
  const avatarSrc = resolveAvatarSrc(avatar)
  const [brokenAvatarSrc, setBrokenAvatarSrc] = useState(null)
  const [presence, setPresence] = useState(status?.presence || 'offline')
  const [menuOpen, setMenuOpen] = useState(false)
  const [savingPresence, setSavingPresence] = useState('')
  const avatarBroken = avatarSrc && brokenAvatarSrc === avatarSrc

  useEffect(() => {
    setPresence(status?.presence || 'offline')
  }, [status?.presence])

  async function savePresence(nextPresence) {
    setSavingPresence(nextPresence)
    try {
      const data = await updateStatus({
        presence: nextPresence,
        status_text: '',
        status_emoji: '',
      })
      setPresence(data?.presence || nextPresence)
      setMenuOpen(false)
    } finally {
      setSavingPresence('')
    }
  }

  return (
    <div className="main-shell">
      <aside className="iconbar" aria-label="导航">
        <div className="iconbar__top">
          <button className="iconbar__avatar" title={username || '我'} type="button" onClick={() => setMenuOpen((v) => !v)}>
            {avatarSrc && !avatarBroken ? (
              <img className="iconbar__avatarImg" src={avatarSrc} alt="" onError={() => setBrokenAvatarSrc(avatarSrc)} />
            ) : (
              <svg viewBox="0 0 24 24" className="iconbar__avatarDefaultIcon" aria-hidden>
                <circle cx="12" cy="8" r="4" />
                <path d="M4 20c0-4 3.6-6 8-6s8 2 8 6" />
              </svg>
            )}
            <span className={`presenceDot presenceDot--avatar ${presenceClass(presence)}`} aria-label={getPresenceLabel(presence)} />
          </button>
          {menuOpen ? (
            <div className="presenceMenu">
              {presenceOptions.map(([value, label]) => (
                <button
                  type="button"
                  key={value}
                  className={`presenceMenu__item${presence === value ? ' is-active' : ''}`}
                  disabled={Boolean(savingPresence)}
                  onClick={() => void savePresence(value)}
                >
                  <span className={`presenceDot ${presenceClass(value)}`} aria-hidden />
                  <span>{label}</span>
                </button>
              ))}
            </div>
          ) : null}
        </div>
        <nav className="iconbar__nav">
          {iconItems.map((it) => (
            <NavLink
              key={it.to + it.label}
              to={it.to}
              title={it.label}
              className={({ isActive }) => (isActive ? 'iconbar__item is-active' : 'iconbar__item')}
            >
              <NavIcon type={it.icon} />
            </NavLink>
          ))}
        </nav>
        <div className="iconbar__bottom">
          <NavLink
            to="/help"
            title="帮助文档"
            className={({ isActive }) => (isActive ? 'iconbar__item is-active' : 'iconbar__item')}
          >
            <NavIcon type="help" />
          </NavLink>
          <NavLink
            to="/settings/logout"
            title="退出登录"
            className={({ isActive }) => (isActive ? 'iconbar__item is-active' : 'iconbar__item')}
          >
            <svg viewBox="0 0 24 24" aria-hidden>
              <path d="M10 5H6v14h4" />
              <path d="M13 8l4 4-4 4" />
              <path d="M8 12h9" />
            </svg>
          </NavLink>
        </div>
      </aside>

      <main className="main-content" aria-label="内容区">
        <Outlet />
      </main>
    </div>
  )
}
