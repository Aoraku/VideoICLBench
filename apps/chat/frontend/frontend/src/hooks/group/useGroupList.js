import { useCallback, useEffect, useState } from 'react'
import * as groupApi from '../../api/groupApi.js'
import { userFacingError } from '../../utils/userFacingError.js'

/**
 * @typedef {import('../../types/group.js').Group} Group
 */

export function useGroupList() {
  /** @type {[Group[], Function]} */
  const [groups, setGroups] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refetch = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const rows = await groupApi.getGroupList()
      setGroups(rows)
    } catch (e) {
      setError(userFacingError(e, '加载群列表失败'))
      setGroups([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refetch()
  }, [refetch])

  return { groups, loading, error, refetch }
}
