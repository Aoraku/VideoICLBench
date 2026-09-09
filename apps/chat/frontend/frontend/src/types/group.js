/**
 * 群聊域 UI 契约（与作业约定 + API-document 第六章对照；字段变更请先同步）。
 *
 * @typedef {'owner'|'admin'|'member'} GroupRole
 */

/**
 * 群摘要（列表 / 创建返回映射）
 * @typedef {Object} Group
 * @property {string} id 会话 ID（与路由 :groupId 一致，字符串形式）
 * @property {string} name
 * @property {string} ownerId
 * @property {number} memberCount
 * @property {string} createdAt ISO
 * @property {string} [avatar]
 * @property {string} [ownerUsername] GET /group 的 owner.username，成员列表未到时用于展示群主
 */

/**
 * @typedef {Object} GroupMember
 * @property {string} id user_id 字符串
 * @property {string} name 展示名（备注 > 群昵称 > 用户名）
 * @property {string} [avatar]
 * @property {GroupRole} role
 * @property {string} [username]
 * @property {string|null} [remark]
 * @property {string|null} [groupNickname]
 */

/**
 * @typedef {Object} GroupAnnouncement
 * @property {string} id
 * @property {string} groupId
 * @property {string} content
 * @property {string} publisherId
 * @property {string} publisherName
 * @property {string} createdAt
 */

/**
 * @typedef {Object} GroupInviteRequest
 * @property {string} id
 * @property {string} groupId
 * @property {string} inviterId
 * @property {string} inviterName
 * @property {string} inviteeId
 * @property {string} inviteeName
 * @property {'pending'|'approved'|'rejected'} status
 * @property {string} createdAt
 */

/**
 * 群详情聚合（GET …/group + 成员里推导当前用户角色）
 * @typedef {Object} GroupDetailBundle
 * @property {Group} group
 * @property {GroupMember[]} members
 * @property {GroupAnnouncement[]} announcements
 * @property {GroupRole|null} currentUserRole
 * @property {string|null} [myGroupNickname]
 * @property {GroupAnnouncement|null} [latestAnnouncement] GET /group 的 latest_announcement（可与 announcements 合并展示）
 */

export {}
