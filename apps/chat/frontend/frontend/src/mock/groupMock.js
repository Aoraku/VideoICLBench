/** @typedef {import('../types/group.js').Group} Group */
/** @typedef {import('../types/group.js').GroupMember} GroupMember */
/** @typedef {import('../types/group.js').GroupAnnouncement} GroupAnnouncement */
/** @typedef {import('../types/group.js').GroupInviteRequest} GroupInviteRequest */

const MOCK_OWNER_ID = '1001'
const MOCK_CONV_ID = '2002'

/** @type {Group} */
export const mockGroupSummary = {
  id: MOCK_CONV_ID,
  name: '项目讨论组（Mock）',
  ownerId: MOCK_OWNER_ID,
  memberCount: 4,
  createdAt: '2026-03-01T08:00:00.000Z',
  avatar: null,
}

/** @type {GroupMember[]} */
export const mockGroupMembers = [
  { id: '1001', name: 'Alice', username: 'alice', role: 'owner', avatar: null, remark: null, groupNickname: 'Alice PM' },
  { id: '1002', name: 'Bob同学', username: 'bob', role: 'admin', avatar: null, remark: 'Bob同学', groupNickname: null },
  { id: '1003', name: 'charlie', username: 'charlie', role: 'member', avatar: null, remark: null, groupNickname: null },
  { id: '1004', name: 'david', username: 'david', role: 'member', avatar: null, remark: null, groupNickname: null },
]

/** @type {GroupAnnouncement[]} */
export const mockAnnouncements = [
  {
    id: '301',
    groupId: MOCK_CONV_ID,
    content: '明天下午 3 点开项目评审会',
    publisherId: MOCK_OWNER_ID,
    publisherName: 'alice',
    createdAt: '2026-03-13T09:00:00.000Z',
  },
  {
    id: '302',
    groupId: MOCK_CONV_ID,
    content: '本周五线下站会改到线上。',
    publisherId: '1002',
    publisherName: 'bob',
    createdAt: '2026-03-12T10:00:00.000Z',
  },
]

/** @type {GroupInviteRequest[]} */
export const mockJoinRequests = [
  {
    id: '6001',
    groupId: MOCK_CONV_ID,
    inviterId: '1003',
    inviterName: 'charlie',
    inviteeId: '1005',
    inviteeName: 'eve',
    status: 'pending',
    createdAt: '2026-03-14T12:00:00.000Z',
  },
]

/**
 * @param {string} groupId
 */
export function getMockGroupDetailBundle(groupId) {
  const gid = String(groupId)
  return {
    group: { ...mockGroupSummary, id: gid },
    members: mockGroupMembers.map((m) => ({ ...m, id: m.id })),
    announcements: mockAnnouncements.map((a) => ({ ...a, groupId: gid })),
  }
}

/**
 * @param {{ name: string, memberIds: string[] }} params
 * @returns {Promise<Group>}
 */
export async function mockCreateGroup(params) {
  if (!Array.isArray(params.memberIds) || params.memberIds.length < 2) {
    const err = new Error('请至少选择 2 位好友')
    err.status = 400
    err.code = 'INVALID_PARAMS'
    throw err
  }
  const id = String(2000 + Math.floor(Math.random() * 900) + 1)
  return {
    id,
    name: params.name || '新群聊（Mock）',
    ownerId: MOCK_OWNER_ID,
    memberCount: params.memberIds.length + 1,
    createdAt: new Date().toISOString(),
    avatar: null,
  }
}

/**
 * @returns {Promise<Group[]>}
 */
export async function mockGetGroupList() {
  return [mockGroupSummary]
}
