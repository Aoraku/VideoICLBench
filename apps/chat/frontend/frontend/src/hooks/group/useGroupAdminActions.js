import { useState } from 'react'
import {
  leaveGroup,
  publishGroupAnnouncement,
  removeGroupMember,
  setGroupAdmin,
  transferGroupOwner,
  unsetGroupAdmin,
} from '../../api/groupApi.js'
import { userFacingError } from '../../utils/userFacingError.js'

export function useGroupAdminActions() {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function run(task, fallbackMessage) {
    if (submitting) return false
    setSubmitting(true)
    setError('')
    try {
      await task()
      return true
    } catch (e) {
      setError(userFacingError(e, fallbackMessage))
      return false
    } finally {
      setSubmitting(false)
    }
  }

  return {
    submitting,
    error,
    clearError: () => setError(''),
    setAdmin: (groupId, userId) => run(() => setGroupAdmin(groupId, userId), '设置管理员失败'),
    unsetAdmin: (groupId, userId) => run(() => unsetGroupAdmin(groupId, userId), '取消管理员失败'),
    transferOwner: (groupId, userId) => run(() => transferGroupOwner(groupId, userId), '转让群主失败'),
    publishAnnouncement: (groupId, content) =>
      run(() => publishGroupAnnouncement({ groupId, content }), '发布公告失败'),
    removeMember: (groupId, memberId) => run(() => removeGroupMember(groupId, memberId), '移除成员失败'),
    leaveCurrentGroup: (groupId) => run(() => leaveGroup(groupId), '退出群聊失败'),
  }
}
