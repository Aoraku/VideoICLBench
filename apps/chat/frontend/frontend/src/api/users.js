import { apiFetch } from './client.js'

export function searchUsers({ keyword, page = 1, pageSize = 20 }) {
  const q = new URLSearchParams({
    keyword,
    page: String(page),
    page_size: String(pageSize),
  })
  return apiFetch(`/users/search?${q}`)
}

export function getUser(userId) {
  return apiFetch(`/users/${userId}`)
}

export function getMe() {
  return apiFetch('/users/me')
}

export function updateMe(payload) {
  // payload: username/phone/email/password/old_password
  return apiFetch('/users/me', { method: 'PUT', json: payload })
}

export function uploadAvatar(file) {
  const form = new FormData()
  form.append('file', file)
  return apiFetch('/users/me/avatar', { method: 'POST', body: form })
}

export function getPrivacy() {
  return apiFetch('/users/me/privacy')
}

export function updatePrivacy(payload) {
  return apiFetch('/users/me/privacy', { method: 'PUT', json: payload })
}

export function updateStatus(payload) {
  return apiFetch('/users/me/status', { method: 'PUT', json: payload })
}

export function getAiKeySettings() {
  return apiFetch('/users/me/ai-key')
}

export function updateAiKey(apiKey) {
  return apiFetch('/users/me/ai-key', { method: 'PUT', json: { api_key: apiKey } })
}

export function clearAiKey() {
  return apiFetch('/users/me/ai-key', { method: 'DELETE' })
}
