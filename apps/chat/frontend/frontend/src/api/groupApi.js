import { apiFetch } from './client.js'
import { listConversations } from './conversations.js'
import * as groupMock from '../mock/groupMock.js'

function groupApiMockEnabled() {
  return import.meta.env.VITE_GROUP_API_MOCK === '1'
}

/**
 * @param {Record<string, unknown>} row
 * @param {'owner'|'admin'|'member'} role
 */
function mapMemberRow(row, role) {
  const userId = row.user_id != null ? String(row.user_id) : ''
  const remark = row.remark != null && row.remark !== '' ? String(row.remark) : null
  const gn = row.group_nickname != null && row.group_nickname !== '' ? String(row.group_nickname) : null
  const username = typeof row.username === 'string' ? row.username : ''
  const name = remark || gn || username || `用户 ${userId}`
  return {
    id: userId,
    name,
    username,
    avatar: row.avatar != null ? String(row.avatar) : undefined,
    role,
    remark,
    groupNickname: gn,
  }
}

/**
 * @param {string} convId
 * @param {unknown} data
 */
function mapAnnouncementsPage(convId, data) {
  const results = Array.isArray(data?.results) ? data.results : []
  return results.map((row) => ({
    id: String(row.announcement_id ?? row.id ?? ''),
    groupId: convId,
    content: String(row.content ?? ''),
    publisherId: String(row.publisher?.user_id ?? ''),
    publisherName: String(row.publisher?.username ?? ''),
    createdAt: String(row.created_at ?? ''),
  }))
}

/**
 * 会话列表中的群聊项 → Group 摘要（部分字段列表接口可能缺失，用占位）
 * @param {Record<string, unknown>} row
 */
function conversationRowToGroup(row) {
  const id = String(row.conversation_id ?? '')
  return {
    id,
    name: typeof row.name === 'string' && row.name ? row.name : '群聊',
    ownerId: '',
    memberCount: typeof row.member_count === 'number' ? row.member_count : 0,
    createdAt: typeof row.created_at === 'string' ? row.created_at : '',
    avatar: row.avatar != null ? String(row.avatar) : undefined,
  }
}

/** @typedef {import('../types/group.js').Group} Group */
/** @typedef {import('../types/group.js').GroupMember} GroupMember */
/** @typedef {import('../types/group.js').GroupAnnouncement} GroupAnnouncement */
/** @typedef {import('../types/group.js').GroupInviteRequest} GroupInviteRequest */

/**
 * @returns {Promise<Group[]>}
 */
export async function getGroupList() {
  if (groupApiMockEnabled()) return groupMock.mockGetGroupList()
  const data = await listConversations({ page: 1, pageSize: 50 })
  const rows = Array.isArray(data?.results) ? data.results : []
  return rows.filter((r) => r.type === 'group').map((r) => conversationRowToGroup(r))
}

/**
 * @param {{ name: string, memberIds: string[] }} params
 * @returns {Promise<Group>}
 */
export async function createGroup(params) {
  const member_ids = params.memberIds.map((x) => Number(x)).filter((n) => Number.isFinite(n) && n > 0)
  const name = typeof params.name === 'string' ? params.name.trim() : ''
  if (member_ids.length < 2) {
    const err = new Error('请至少选择 2 位好友')
    err.status = 400
    err.code = 'INVALID_PARAMS'
    throw err
  }
  if (groupApiMockEnabled()) return groupMock.mockCreateGroup({ name, memberIds: params.memberIds })

  const payload = {
    type: 'group',
    name: name || '群聊',
    member_ids,
  }
  const data = await apiFetch('/conversations/', { method: 'POST', json: payload })
  const convId = String(data?.conversation_id ?? '')
  const members = Array.isArray(data?.members) ? data.members : []
  const ownerRow = members.find((m) => m.role === 'owner')
  const ownerId = ownerRow?.user_id != null ? String(ownerRow.user_id) : ''
  return {
    id: convId,
    name: String(data?.name ?? payload.name),
    ownerId,
    memberCount: members.length || member_ids.length + 1,
    createdAt: String(data?.created_at ?? new Date().toISOString()),
    avatar: data?.avatar != null ? String(data.avatar) : undefined,
  }
}

/**
 * GET /conversations/{conv_id}/group — 返回原始 JSON + 归一化 group 摘要字段
 * @param {string|number} groupId
 */
export async function getGroupDetailRaw(groupId) {
  if (groupApiMockEnabled()) {
    const b = groupMock.getMockGroupDetailBundle(String(groupId))
    const firstAnn = b.announcements[0]
    return {
      conversation_id: Number(groupId) || 2002,
      name: b.group.name,
      avatar: b.group.avatar ?? null,
      owner: { user_id: Number(b.group.ownerId), username: 'alice' },
      member_count: b.group.memberCount,
      my_group_nickname: 'Alice PM',
      created_at: b.group.createdAt,
      latest_announcement: firstAnn
        ? {
            announcement_id: Number(firstAnn.id) || 301,
            content: firstAnn.content,
            publisher: { user_id: Number(firstAnn.publisherId), username: firstAnn.publisherName },
            created_at: firstAnn.createdAt,
          }
        : null,
    }
  }
  return apiFetch(`/conversations/${groupId}/group`)
}

/**
 * 解析 GET …/group 响应中的群摘要、我的群昵称与最新公告（与 API-document 6.1 对齐）
 * @param {Record<string, unknown>} raw
 * @param {string|number} groupId
 */
export function parseGroupDetailPayload(raw, groupId) {
  const convId = String(raw.conversation_id ?? groupId)
  const owner = raw.owner && typeof raw.owner === 'object' ? raw.owner : {}
  const ownerUsername = typeof owner.username === 'string' && owner.username ? String(owner.username) : ''
  /** @type {import('../types/group.js').Group} */
  const group = {
    id: convId,
    name: String(raw.name ?? '群聊'),
    ownerId: String(owner.user_id ?? ''),
    memberCount: typeof raw.member_count === 'number' ? raw.member_count : 0,
    createdAt: String(raw.created_at ?? ''),
    avatar: raw.avatar != null ? String(raw.avatar) : undefined,
    ...(ownerUsername ? { ownerUsername } : {}),
  }
  const myNn = raw.my_group_nickname
  const myGroupNickname =
    typeof myNn === 'string' && myNn.trim() !== '' ? myNn.trim() : null

  /** @type {import('../types/group.js').GroupAnnouncement|null} */
  let latestAnnouncement = null
  const la = raw.latest_announcement
  if (la && typeof la === 'object') {
    const aid = la.announcement_id != null ? String(la.announcement_id) : ''
    const pub = la.publisher && typeof la.publisher === 'object' ? la.publisher : {}
    const content = String(la.content ?? '')
    if (aid || content) {
      latestAnnouncement = {
        id: aid || 'latest',
        groupId: convId,
        content,
        publisherId: String(pub.user_id ?? ''),
        publisherName: String(pub.username ?? ''),
        createdAt: String(la.created_at ?? ''),
      }
    }
  }
  return { group, myGroupNickname, latestAnnouncement }
}

/**
 * 若 latest 不在历史列表中，则插在列表前（避免详情区与历史区重复展示同一条）
 * @param {import('../types/group.js').GroupAnnouncement|null} latest
 * @param {import('../types/group.js').GroupAnnouncement[]} list
 */
export function mergeAnnouncementsWithLatest(latest, list) {
  const rows = Array.isArray(list) ? [...list] : []
  if (!latest || !latest.id) return rows
  if (rows.some((a) => a.id === latest.id)) return rows
  return [latest, ...rows]
}

/**
 * @param {string|number} groupId
 * @returns {Promise<Group>}
 */
export async function getGroupDetail(groupId) {
  const raw = await getGroupDetailRaw(groupId)
  return parseGroupDetailPayload(raw, groupId).group
}

/**
 * @param {string|number} groupId
 * @returns {Promise<GroupMember[]>}
 */
export async function getGroupMembers(groupId) {
  if (groupApiMockEnabled()) return groupMock.getMockGroupDetailBundle(String(groupId)).members
  const q = new URLSearchParams({ page: '1', page_size: '100' })
  const data = await apiFetch(`/conversations/${groupId}/group/members?${q}`)
  const results = Array.isArray(data?.results) ? data.results : []
  return results.map((row) => {
    const r = row.role
    const role = r === 'owner' || r === 'admin' ? r : 'member'
    return mapMemberRow(row, role)
  })
}

/**
 * @param {string|number} groupId
 * @param {{ page?: number, pageSize?: number }} [opts]
 * @returns {Promise<GroupAnnouncement[]>}
 */
export async function getGroupAnnouncements(groupId, opts = {}) {
  const page = opts.page ?? 1
  const pageSize = opts.pageSize ?? 20
  if (groupApiMockEnabled()) return groupMock.getMockGroupDetailBundle(String(groupId)).announcements
  const q = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  const data = await apiFetch(`/conversations/${groupId}/group/announcements?${q}`)
  return mapAnnouncementsPage(String(groupId), data)
}

/**
 * @param {string|number} groupId
 * @param {string|number} userId
 */
export function setGroupAdmin(groupId, userId) {
  if (groupApiMockEnabled()) return Promise.resolve(null)
  const id = Number(userId)
  return apiFetch(`/conversations/${groupId}/group/admins`, {
    method: 'POST',
    json: { user_id: Number.isFinite(id) ? id : userId },
  })
}

/**
 * @param {string|number} groupId
 * @param {string|number} userId
 */
export function unsetGroupAdmin(groupId, userId) {
  if (groupApiMockEnabled()) return Promise.resolve(null)
  return apiFetch(`/conversations/${groupId}/group/admins/${userId}`, { method: 'DELETE' })
}

/**
 * @param {string|number} groupId
 * @param {string|number} newOwnerId
 */
export function transferGroupOwner(groupId, newOwnerId) {
  if (groupApiMockEnabled()) return Promise.resolve(null)
  const id = Number(newOwnerId)
  return apiFetch(`/conversations/${groupId}/group/owner`, {
    method: 'PUT',
    json: { new_owner_id: Number.isFinite(id) ? id : newOwnerId },
  })
}

/**
 * @param {{ groupId: string|number, content: string }} params
 */
export function publishGroupAnnouncement(params) {
  if (groupApiMockEnabled()) {
    return Promise.resolve({
      announcement_id: 999,
      content: params.content,
      publisher: { user_id: 1, username: 'mock' },
      created_at: new Date().toISOString(),
    })
  }
  return apiFetch(`/conversations/${params.groupId}/group/announcements`, {
    method: 'POST',
    json: { content: params.content },
  })
}

/**
 * @param {string|number} groupId
 * @param {string|number} memberId
 */
export function removeGroupMember(groupId, memberId) {
  if (groupApiMockEnabled()) return Promise.resolve(null)
  return apiFetch(`/conversations/${groupId}/group/members/${memberId}`, { method: 'DELETE' })
}

/**
 * 文档为 user_ids 数组；此处封装单个好友 ID。
 * @param {string|number} groupId
 * @param {string|number} friendId
 */
export function inviteFriendToGroup(groupId, friendId) {
  if (groupApiMockEnabled()) return Promise.resolve(null)
  const id = Number(friendId)
  return apiFetch(`/conversations/${groupId}/group/invitations`, {
    method: 'POST',
    json: { user_ids: [Number.isFinite(id) ? id : friendId] },
  })
}

/**
 * @param {string|number} groupId
 * @param {{ status?: string, page?: number, pageSize?: number }} [opts]
 * @returns {Promise<GroupInviteRequest[]>}
 */
export async function getGroupJoinRequests(groupId, opts = {}) {
  const status = opts.status ?? 'pending'
  const page = opts.page ?? 1
  const pageSize = opts.pageSize ?? 20
  if (groupApiMockEnabled()) return groupMock.mockJoinRequests.map((r) => ({ ...r, groupId: String(groupId) }))
  const q = new URLSearchParams({
    status: String(status),
    page: String(page),
    page_size: String(pageSize),
  })
  const data = await apiFetch(`/conversations/${groupId}/group/invitations?${q}`)
  const results = Array.isArray(data?.results) ? data.results : []
  return results.map((row) => ({
    id: String(row.invitation_id ?? ''),
    groupId: String(groupId),
    inviterId: String(row.inviter?.user_id ?? ''),
    inviterName: String(row.inviter?.username ?? ''),
    inviteeId: String(row.invitee?.user_id ?? ''),
    inviteeName: String(row.invitee?.username ?? ''),
    status: row.status === 'approved' || row.status === 'rejected' ? row.status : 'pending',
    createdAt: String(row.created_at ?? ''),
  }))
}

/**
 * @param {string|number} groupId
 * @param {string|number} invitationId
 */
export function approveGroupJoinRequest(groupId, invitationId) {
  if (groupApiMockEnabled()) return Promise.resolve(null)
  return apiFetch(`/conversations/${groupId}/group/invitations/${invitationId}`, {
    method: 'PUT',
    json: { action: 'approve' },
  })
}

/**
 * @param {string|number} groupId
 * @param {string|number} invitationId
 */
export function rejectGroupJoinRequest(groupId, invitationId) {
  if (groupApiMockEnabled()) return Promise.resolve(null)
  return apiFetch(`/conversations/${groupId}/group/invitations/${invitationId}`, {
    method: 'PUT',
    json: { action: 'reject' },
  })
}

/**
 * PUT /api/conversations/{conv_id}/group — 修改群名称（群主/管理员）
 * @param {string|number} groupId
 * @param {{ name: string }} body
 */
export function updateGroupInfo(groupId, body) {
  const name = typeof body.name === 'string' ? body.name.trim() : ''
  if (groupApiMockEnabled()) {
    return Promise.resolve({
      conversation_id: Number(groupId) || 2002,
      name: name || '群聊',
      updated_at: new Date().toISOString(),
    })
  }
  return apiFetch(`/conversations/${groupId}/group`, {
    method: 'PUT',
    json: { name },
  })
}

/**
 * POST /api/conversations/{conv_id}/group/avatar
 * @param {string|number} groupId
 * @param {File} file
 */
export function uploadGroupAvatar(groupId, file) {
  if (groupApiMockEnabled()) return Promise.resolve({ avatar: URL.createObjectURL(file) })
  const form = new FormData()
  form.append('file', file)
  return apiFetch(`/conversations/${groupId}/group/avatar`, {
    method: 'POST',
    body: form,
  })
}

/**
 * DELETE /api/conversations/{conv_id}/group
 * @param {string|number} groupId
 */
export function dissolveGroup(groupId) {
  if (groupApiMockEnabled()) return Promise.resolve(null)
  return apiFetch(`/conversations/${groupId}/group`, {
    method: 'DELETE',
    json: { confirm: true },
  })
}

/**
 * PUT /api/conversations/{conv_id}/group/my-nickname — 设置本人在群昵称
 * @param {string|number} groupId
 * @param {string} nickname 空字符串表示清除
 */
export function setMyGroupNickname(groupId, nickname) {
  const nn = typeof nickname === 'string' ? nickname : String(nickname ?? '')
  if (groupApiMockEnabled()) {
    return Promise.resolve({
      conversation_id: Number(groupId) || 2002,
      user_id: 1001,
      nickname: nn,
      updated_at: new Date().toISOString(),
    })
  }
  return apiFetch(`/conversations/${groupId}/group/my-nickname`, {
    method: 'PUT',
    json: { nickname: nn },
  })
}

/**
 * @param {string|number} groupId
 */
export function leaveGroup(groupId) {
  if (groupApiMockEnabled()) return Promise.resolve(null)
  return apiFetch(`/conversations/${groupId}/group/leave`, { method: 'POST' })
}
