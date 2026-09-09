export function toGroupKey(groupId) {
  return String(groupId)
}

export const MAX_REMARK_LENGTH = 30

export function normalizeRemark(remark) {
  // 备注允许为空字符串用于清空备注
  return String(remark ?? '')
}

export function validateRemark(remark) {
  const value = normalizeRemark(remark)
  if (value.length > MAX_REMARK_LENGTH) {
    return { ok: false, message: `备注最多 ${MAX_REMARK_LENGTH} 字符` }
  }
  return { ok: true, value }
}

export function buildGroupMap(groups, friends) {
  const map = new Map()
  groups.forEach((group) => {
    map.set(toGroupKey(group.group_id), [])
  })

  friends.forEach((friend) => {
    const key = toGroupKey(friend.group_id)
    if (!map.has(key)) {
      map.set(key, [])
    }
    map.get(key).push(friend)
  })

  return map
}

export function normalizeGroupList(groups) {
  // “未分组”是联系人状态，不应作为可管理分组出现在分组列表里。
  return groups.filter((group) => group.group_id != null)
}

export function getPresenceLabel(presence) {
  switch (presence) {
    case 'online':
      return '在线'
    case 'busy':
      return '忙碌'
    case 'invisible':
      return '隐身'
    case 'offline':
    default:
      return '离线'
  }
}

export function presenceClass(presence) {
  switch (presence) {
    case 'online':
      return 'is-online'
    case 'busy':
      return 'is-busy'
    case 'invisible':
      return 'is-invisible'
    case 'offline':
    default:
      return 'is-offline'
  }
}

export function getFriendDisplayName(friend) {
  return friend.remark || friend.username
}

export function groupExists(groups, groupId) {
  return groups.some((group) => group.group_id === groupId)
}

export function updateFriendGroupLocal(friends, friendUserId, targetGroupId) {
  return friends.map((friend) => {
    if (friend.user_id !== friendUserId) return friend

    return {
      ...friend,
      group_id: targetGroupId,
    }
  })
}

export function recalculateGroupCounts(groups, friends) {
  return groups.map((group) => {
    const friendCount = friends.filter((friend) => String(friend.group_id) === String(group.group_id)).length
    return { ...group, friend_count: friendCount }
  })
}
