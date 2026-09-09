import { ACCESS_TOKEN_KEY } from '../constants/storage.js'

function parseJwtPayload(token) {
  if (!token || typeof token !== 'string') return null
  const parts = token.split('.')
  if (parts.length < 2) return null
  try {
    const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const padded = b64.padEnd(Math.ceil(b64.length / 4) * 4, '=')
    const json = window.atob(padded)
    return JSON.parse(json)
  } catch {
    return null
  }
}

/**
 * 尝试从 access token 中解析当前用户 ID。
 * 常见字段：user_id / uid / sub。
 * @returns {number|null}
 */
export function getCurrentUserIdFromToken() {
  try {
    const token = localStorage.getItem(ACCESS_TOKEN_KEY)
    const payload = parseJwtPayload(token)
    const raw = payload?.user_id ?? payload?.uid ?? payload?.sub
    const id = Number(raw)
    return Number.isFinite(id) ? id : null
  } catch {
    return null
  }
}
