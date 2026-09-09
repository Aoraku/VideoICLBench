import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom'
import AuthLayout from '../components/layout/AuthLayout.jsx'
import MainLayout from '../components/layout/MainLayout.jsx'
import ContactsPage from '../pages/contacts/ContactsPage.jsx'
import SearchPage from '../pages/contacts/SearchPage.jsx'
import FriendRequestsPage from '../pages/friends/FriendRequestsPage.jsx'
import UserProfilePage from '../pages/user/UserProfilePage.jsx'
import LoginPage from '../pages/Login.jsx'
import RegisterPage from '../pages/Register.jsx'
import ChatPage from '../pages/Chat/index.jsx'
import BookmarksPage from '../pages/bookmarks/BookmarksPage.jsx'
import CalendarPage from '../pages/calendar/CalendarPage.jsx'
import HelpPage from '../pages/help/HelpPage.jsx'
import AccountDeletePage from '../pages/settings/AccountDelete.jsx'
import LogoutPage from '../pages/settings/Logout.jsx'
import ProfileEditPage from '../pages/settings/ProfileEdit.jsx'
import GroupListPage from '../pages/group/GroupListPage.jsx'
import GroupCreatePage from '../pages/group/GroupCreatePage.jsx'
import GroupDetailPage from '../pages/group/GroupDetailPage.jsx'
import { ACCESS_TOKEN_KEY } from '../constants/storage.js'

function hasAccessToken() {
  // UI-only 调试：允许通过 ?ui=1 绕过登录（仅前端开发时用）
  try {
    const sp = new URLSearchParams(window.location.search || '')
    if (sp.get('ui') === '1') return true
  } catch {
    // ignore
  }
  return Boolean(localStorage.getItem(ACCESS_TOKEN_KEY))
}

function RequireAuth() {
  return hasAccessToken() ? <Outlet /> : <Navigate to="/login" replace />
}

function RedirectIfAuthed({ to, children }) {
  return hasAccessToken() ? <Navigate to={to} replace /> : children
}

/**
 * A 负责的路由（/login /register /settings）由 A 自行补充。
 * B 负责的路由在此注册：通讯录、搜索、好友申请、用户详情。
 */
export default function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        {/* 认证页：只显示登录/注册卡片，不带任何导航 */}
        <Route element={<AuthLayout />}>
          <Route
            path="/login"
            element={
              <RedirectIfAuthed to="/chat">
                <LoginPage />
              </RedirectIfAuthed>
            }
          />
          <Route
            path="/register"
            element={
              <RedirectIfAuthed to="/chat">
                <RegisterPage />
              </RedirectIfAuthed>
            }
          />
        </Route>

        {/* 登录后页面：主界面布局（必须登录） */}
        <Route element={<RequireAuth />}>
          <Route path="/" element={<MainLayout />}>
            {/* 默认进入聊天页（真实会话列表 + 消息区） */}
            <Route index element={<Navigate to="/chat" replace />} />
            <Route path="chat" element={<ChatPage />} />
            <Route path="bookmarks" element={<BookmarksPage />} />
            <Route path="calendar" element={<CalendarPage />} />
            <Route path="help" element={<HelpPage />} />

            {/* ===== 群聊：列表 / 创建 / 资料 ===== */}
            <Route path="groups" element={<GroupListPage />} />
            <Route path="groups/create" element={<GroupCreatePage />} />
            <Route path="groups/:groupId" element={<GroupDetailPage />} />

            {/* ===== B: 通讯录 & 搜索 ===== */}
            <Route path="contacts" element={<ContactsPage />} />
            <Route path="contacts/search" element={<SearchPage />} />

            {/* ===== B: 好友申请 ===== */}
            <Route path="friends/requests" element={<FriendRequestsPage />} />

            {/* ===== B: 用户详情 ===== */}
            <Route path="user/:userId" element={<UserProfilePage />} />

            {/* ===== A: 设置 ===== */}
            <Route path="settings/profile" element={<ProfileEditPage />} />
            <Route path="settings/logout" element={<LogoutPage />} />
            <Route path="settings/account-delete" element={<AccountDeletePage />} />
          </Route>
        </Route>

        <Route path="*" element={<div style={{ padding: 32, textAlign: 'center' }}>404 页面不存在</div>} />
      </Routes>
    </BrowserRouter>
  )
}
