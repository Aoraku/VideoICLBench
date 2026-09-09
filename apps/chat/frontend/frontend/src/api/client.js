import { ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY } from '../constants/storage.js'
import { refreshToken } from './auth.js'

function baseUrl() {
  const raw = import.meta.env.VITE_API_BASE_URL
  if (raw !== undefined && raw !== '') return String(raw).replace(/\/$/, '')

  // Secoder 线上兜底：从前端域名推导同团队后端域名，避免遗漏 CI 变量导致请求打到 /api。
  if (typeof window !== 'undefined') {
    const host = window.location?.host || ''
    if (host.endsWith('.app.spring26b.secoder.net') && host.includes('-frontend-')) {
      return `${window.location.protocol}//${host.replace('-frontend-', '-backend-')}/api`
    }
  }

  // 本地开发默认走同源 /api（由 Vite 代理转发）。
  return '/api'
}

export function apiUrl(path) {
  return `${baseUrl()}${path.startsWith('/') ? path : `/${path}`}`
}

export function authHeaders(initialHeaders) {
  const headers = new Headers(initialHeaders)
  const token = localStorage.getItem(ACCESS_TOKEN_KEY)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  return headers
}

/**
 * @param {string} path 以 / 开头，如 /friends
 * @param {RequestInit & { json?: unknown }} options
 */
export async function apiFetch(path, options = {}) {
  const url = apiUrl(path)
  const headers = authHeaders(options.headers)

  let body = options.body
  if (options.json !== undefined) {
    body = JSON.stringify(options.json)
    if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  } else if (body && !(body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const doFetch = () => fetch(url, { ...options, headers, body })
  let res = await doFetch()

  // 401：尝试用 refresh_token 刷新 access_token，然后重试一次
  // 注意：auth 类端点自身不重试，避免 refreshInFlight 死锁
  const isAuthPath = path.startsWith('/auth/')
  if (res.status === 401 && !isAuthPath) {
    const refreshed = await tryRefreshAccessToken()
    if (refreshed) {
      const nextHeaders = new Headers(headers)
      const nextToken = localStorage.getItem(ACCESS_TOKEN_KEY)
      if (nextToken) nextHeaders.set('Authorization', `Bearer ${nextToken}`)
      res = await fetch(url, { ...options, headers: nextHeaders, body })
    } else {
      clearSessionAndRedirect()
    }
  }
  if (res.status === 204) return null

  const text = await res.text()
  const data = text ? JSON.parse(text) : null
  if (!res.ok) {
    const err = new Error(data?.error?.message || res.statusText || '请求失败')
    err.status = res.status
    err.code = data?.error?.code
    err.body = data
    throw err
  }
  return data
}

let refreshInFlight = null

async function tryRefreshAccessToken() {
  const rt = localStorage.getItem(REFRESH_TOKEN_KEY)
  if (!rt) return false

  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const data = await refreshToken({ refresh_token: rt })
        if (data?.access_token) {
          localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token)
          return true
        }
        return false
      } catch {
        return false
      } finally {
        refreshInFlight = null
      }
    })()
  }

  return await refreshInFlight
}

function clearSessionAndRedirect() {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
  if (typeof window !== 'undefined') {
    const p = window.location?.pathname || ''
    if (p !== '/login') window.location.href = '/login'
  }
}
