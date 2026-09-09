import { useCallback, useState } from 'react'
import {
  approveGroupJoinRequest,
  getGroupJoinRequests,
  inviteFriendToGroup,
  rejectGroupJoinRequest,
} from '../../api/groupApi.js'
import { userFacingError } from '../../utils/userFacingError.js'

export function useGroupInviteActions() {
  const [requests, setRequests] = useState([])
  const [loadingRequests, setLoadingRequests] = useState(false)
  const [sendingInviteId, setSendingInviteId] = useState('')
  const [actingRequestId, setActingRequestId] = useState('')
  const [error, setError] = useState('')

  const loadPendingRequests = useCallback(async (groupId) => {
    if (!groupId) {
      setRequests([])
      return
    }
    setLoadingRequests(true)
    setError('')
    try {
      const data = await getGroupJoinRequests(groupId, { status: 'pending', page: 1, pageSize: 50 })
      setRequests(Array.isArray(data) ? data : [])
    } catch (e) {
      setError(userFacingError(e, '加载待审核邀请失败'))
      setRequests([])
    } finally {
      setLoadingRequests(false)
    }
  }, [])

  const inviteFriend = useCallback(async (groupId, friendId) => {
    if (!groupId || !friendId || sendingInviteId) return false
    setSendingInviteId(friendId)
    setError('')
    try {
      await inviteFriendToGroup(groupId, friendId)
      return true
    } catch (e) {
      setError(userFacingError(e, '邀请发送失败'))
      return false
    } finally {
      setSendingInviteId('')
    }
  }, [sendingInviteId])

  const reviewRequest = useCallback(async (groupId, invitationId, action) => {
    if (!groupId || !invitationId || actingRequestId) return false
    setActingRequestId(invitationId)
    setError('')
    try {
      if (action === 'approve') await approveGroupJoinRequest(groupId, invitationId)
      else await rejectGroupJoinRequest(groupId, invitationId)
      return true
    } catch (e) {
      setError(userFacingError(e, action === 'approve' ? '通过失败' : '拒绝失败'))
      return false
    } finally {
      setActingRequestId('')
    }
  }, [actingRequestId])

  return {
    requests,
    loadingRequests,
    sendingInviteId,
    actingRequestId,
    error,
    clearError: useCallback(() => setError(''), []),
    loadPendingRequests,
    inviteFriend,
    approveRequest: useCallback((groupId, invitationId) => reviewRequest(groupId, invitationId, 'approve'), [reviewRequest]),
    rejectRequest: useCallback((groupId, invitationId) => reviewRequest(groupId, invitationId, 'reject'), [reviewRequest]),
  }
}
