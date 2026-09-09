import { useCallback, useEffect, useState } from 'react'
import * as groupApi from '../../api/groupApi.js'
import { useCurrentUserId } from '../useCurrentUserId.js'
import { userFacingError } from '../../utils/userFacingError.js'

/**
 * @typedef {import('../../types/group.js').Group} Group
 * @typedef {import('../../types/group.js').GroupMember} GroupMember
 * @typedef {import('../../types/group.js').GroupAnnouncement} GroupAnnouncement
 * @typedef {import('../../types/group.js').GroupRole} GroupRole
 */

/**
 * @param {string|undefined} groupId
 */
export function useGroupDetail(groupId) {
  const { userId: currentUserId } = useCurrentUserId()
  /** @type {[Group|null, Function]} */
  const [group, setGroup] = useState(null)
  /** @type {[GroupMember[], Function]} */
  const [members, setMembers] = useState([])
  /** @type {[GroupAnnouncement[], Function]} */
  const [announcements, setAnnouncements] = useState([])
  /** @type {[GroupRole|null, Function]} */
  const [currentUserRole, setCurrentUserRole] = useState(null)
  /** @type {[string|null, Function]} */
  const [myGroupNickname, setMyGroupNickname] = useState(null)
  /** @type {[GroupAnnouncement|null, Function]} */
  const [latestAnnouncement, setLatestAnnouncement] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    if (!groupId) {
      setGroup(null)
      setMembers([])
      setAnnouncements([])
      setCurrentUserRole(null)
      setMyGroupNickname(null)
      setLatestAnnouncement(null)
      setLoading(false)
      setError('')
      return
    }
    setLoading(true)
    setError('')
    try {
      const [raw, mem, ann] = await Promise.all([
        groupApi.getGroupDetailRaw(groupId),
        groupApi.getGroupMembers(groupId),
        groupApi.getGroupAnnouncements(groupId),
      ])
      const parsed = groupApi.parseGroupDetailPayload(raw, groupId)
      setGroup(parsed.group)
      setMyGroupNickname(parsed.myGroupNickname)
      setLatestAnnouncement(parsed.latestAnnouncement)
      setMembers(mem)
      setAnnouncements(groupApi.mergeAnnouncementsWithLatest(parsed.latestAnnouncement, ann))
      const selfId = currentUserId != null ? String(currentUserId) : ''
      const row = selfId
        ? mem.find((m) => String(m.id) === selfId || Number(m.id) === Number(currentUserId))
        : null
      let role = row?.role ?? null
      if (!role && selfId && parsed.group?.ownerId && String(parsed.group.ownerId) === selfId) {
        role = 'owner'
      }
      if (!role && selfId && mem.length > 0 && parsed.group) {
        role = 'member'
      }
      setCurrentUserRole(role)
    } catch (e) {
      setError(userFacingError(e, '加载群资料失败'))
      setGroup(null)
      setMembers([])
      setAnnouncements([])
      setCurrentUserRole(null)
      setMyGroupNickname(null)
      setLatestAnnouncement(null)
    } finally {
      setLoading(false)
    }
  }, [groupId, currentUserId])

  useEffect(() => {
    load()
  }, [load])

  return {
    group,
    members,
    announcements,
    currentUserRole,
    myGroupNickname,
    latestAnnouncement,
    loading,
    error,
    refetch: load,
  }
}
