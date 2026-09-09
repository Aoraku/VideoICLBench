import { Outlet } from 'react-router-dom'

export default function AuthLayout() {
  return (
    <div className="auth-shell">
      <div className="auth-hero" aria-hidden="true" />
      <div className="auth-card">
        <Outlet />
      </div>
    </div>
  )
}

