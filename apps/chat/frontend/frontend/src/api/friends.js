import { apiFetch } from './client.js'

export function sendFriendRequest({ targetUserId, message = '', source = 'search' }) {
  const id = Number(targetUserId)
  return apiFetch('/friends/request', {
    method: 'POST',
    json: {
      target_user_id: Number.isFinite(id) ? id : targetUserId,
      message,
      source,
    },
  })
}

export function listFriendRequests({ type = 'received', status = 'pending', page = 1, pageSize = 20 }) {
  const q = new URLSearchParams({
    type,
    status,
    page: String(page),
    page_size: String(pageSize),
  })
  return apiFetch(`/friends/requests?${q}`)
}

export function handleFriendRequest(requestId, action) {
  return apiFetch(`/friends/requests/${requestId}`, {
    method: 'PUT',
    json: { action },
  })
}

export function listFriends({ page = 1, pageSize = 50 }) {
  const q = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  return apiFetch(`/friends?${q}`)
}

export function deleteFriend(friendUserId) {
  return apiFetch(`/friends/${friendUserId}`, { method: 'DELETE' })
}

export function updateFriendRemark(friendUserId, remark) {
  return apiFetch(`/friends/${friendUserId}/remark`, {
    method: 'PUT',
    json: { remark },
  })
}

export function listFriendGroups() {
  return apiFetch('/friends/groups')
}

export function createFriendGroup(name) {
  return apiFetch('/friends/groups', { method: 'POST', json: { name } })
}

export function updateFriendGroup(groupId, body) {
  return apiFetch(`/friends/groups/${groupId}`, { method: 'PUT', json: body })
}

export function deleteFriendGroup(groupId) {
  return apiFetch(`/friends/groups/${groupId}`, { method: 'DELETE' })
}

export function listBlacklist({ page = 1, pageSize = 50 } = {}) {
  const q = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  return apiFetch(`/friends/blacklist?${q}`)
}

export function addBlacklist(userId) {
  return apiFetch('/friends/blacklist', {
    method: 'POST',
    json: { user_id: Number(userId) },
  })
}

export function removeBlacklist(userId) {
  return apiFetch(`/friends/blacklist/${userId}`, { method: 'DELETE' })
}

export function listWhitelist({ page = 1, pageSize = 50 } = {}) {
  const q = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  return apiFetch(`/friends/whitelist?${q}`)
}

export function addWhitelist(userId) {
  return apiFetch('/friends/whitelist', {
    method: 'POST',
    json: { user_id: Number(userId) },
  })
}

export function removeWhitelist(userId) {
  return apiFetch(`/friends/whitelist/${userId}`, { method: 'DELETE' })
}
