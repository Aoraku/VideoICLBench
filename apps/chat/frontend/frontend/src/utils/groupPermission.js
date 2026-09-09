/**
 * @typedef {'owner'|'admin'|'member'} GroupRole
 */

/** @param {GroupRole|null|undefined} role */
export function canPublishAnnouncement(role) {
  return role === 'owner' || role === 'admin'
}

/** @param {GroupRole|null|undefined} role */
export function canManageRole(role) {
  return role === 'owner'
}

/** @param {GroupRole|null|undefined} role */
export function canReviewInvite(role) {
  return role === 'owner' || role === 'admin'
}

/**
 * @param {GroupRole|null|undefined} currentUserRole
 * @param {GroupRole|null|undefined} targetUserRole
 * @param {boolean} isSelf
 */
export function canRemoveMember(currentUserRole, targetUserRole, isSelf) {
  if (isSelf) return false
  if (currentUserRole === 'owner') return true
  if (currentUserRole === 'admin') return targetUserRole === 'member'
  return false
}

/**
 * 群主需先转让后退出
 * @param {GroupRole|null|undefined} role
 */
export function canLeaveGroupDirectly(role) {
  return role === 'admin' || role === 'member'
}
