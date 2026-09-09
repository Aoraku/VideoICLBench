import { useCallback, useEffect, useMemo, useState } from 'react'
import { listConversationMessages } from '../api/messages.js'
import { normalizeMessageFromApi } from '../utils/normalizeMessage.js'
import { getMessagePlainText } from '../utils/messageText.js'
import { userFacingError } from '../utils/userFacingError.js'

const PAGE_SIZE = 50

/** @param {string} a @param {string} b */
function pickEarlierIso(a, b) {
  const ta = Date.parse(a)
  const tb = Date.parse(b)
  if (!Number.isFinite(ta)) return b
  if (!Number.isFinite(tb)) return a
  return ta <= tb ? a : b
}

/**
 * 将筛选项规范为稳定结构（供 `listConversationMessages` 与 effect 依赖）
 * @param {Record<string, unknown>|null|undefined} raw
 */
function normalizeFilterOpts(raw) {
  if (!raw || typeof raw !== 'object') {
    return { senderId: null, keyword: null, rangeAfter: null, rangeBefore: null }
  }
  const o = /** @type {Record<string, unknown>} */ (raw)
  const sid = o.senderId
  let senderId = null
  if (sid != null && sid !== '') {
    const n = typeof sid === 'number' ? sid : Number(sid)
    if (Number.isFinite(n)) senderId = n
  }
  const kw = o.keyword
  const keyword = typeof kw === 'string' && kw.trim() ? kw.trim() : null
  const ra = o.rangeAfter
  const rangeAfter = typeof ra === 'string' && ra.trim() ? ra.trim() : null
  const rb = o.rangeBefore
  const rangeBefore = typeof rb === 'string' && rb.trim() ? rb.trim() : null
  return { senderId, keyword, rangeAfter, rangeBefore }
}

function stripKeywordParam(params) {
  if (!params || typeof params !== 'object') return params
  const next = { ...params }
  delete next.keyword
  return next
}

function localKeywordMatch(row, keyword) {
  const kw = String(keyword || '').trim().toLowerCase()
  if (!kw) return true
  if (!row || typeof row !== 'object') return false
  const type = typeof row.type === 'string' ? row.type : 'text'
  const contentText = getMessagePlainText(row.content, type).toLowerCase()
  const sender = row.sender && typeof row.sender === 'object' ? row.sender : null
  const senderName = String(sender?.group_nickname || sender?.username || row.sender_name || '').toLowerCase()
  return contentText.includes(kw) || senderName.includes(kw)
}

async function withKeywordFallback(conversationId, params, keyword) {
  const data = await listConversationMessages(conversationId, params)
  const rows = Array.isArray(data?.results) ? data.results : []
  const normalized = rows.map((row) => normalizeMessageFromApi(row)).filter(Boolean)
  if (!keyword || normalized.length > 0) {
    return { data, normalized }
  }
  const fallbackData = await listConversationMessages(conversationId, stripKeywordParam(params))
  const fallbackRows = Array.isArray(fallbackData?.results) ? fallbackData.results : []
  const normalizedFallback = fallbackRows.map((row) => normalizeMessageFromApi(row)).filter(Boolean)
  return {
    data: fallbackData,
    normalized: normalizedFallback.filter((row) => localKeywordMatch(row, keyword)),
  }
}

/**
 * @param {number|string|null} conversationId
 * @param {Record<string, unknown>} [filterOpts] 传给后端的筛选：`senderId` | `keyword` | `rangeAfter`/`rangeBefore`（ISO）
 */
export function useConversationMessages(conversationId, filterOpts = undefined) {
  const opts = useMemo(() => normalizeFilterOpts(filterOpts), [filterOpts])

  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [loadingOlder, setLoadingOlder] = useState(false)
  const [hasMoreOlder, setHasMoreOlder] = useState(false)
  const [error, setError] = useState('')

  /**
   * @param {{ page?: number, pageSize?: number, cursorBefore?: string|null }} extra
   * `cursorBefore`：向上翻页时取「当前列表首条」的 created_at，与筛选 `rangeBefore` 取更早者合并为查询上界
   */
  const buildListParams = useCallback(
    (extra = {}) => {
      const page = extra.page ?? 1
      const pageSize = extra.pageSize ?? PAGE_SIZE
      const cursorBefore = extra.cursorBefore ?? null
      /** @type {Parameters<typeof listConversationMessages>[1]} */
      const p = { page, pageSize }
      if (opts.senderId != null) p.senderId = opts.senderId
      if (opts.keyword) p.keyword = opts.keyword
      if (opts.rangeAfter) p.after = opts.rangeAfter
      let upperBefore = opts.rangeBefore ?? null
      if (cursorBefore) {
        upperBefore = upperBefore != null ? pickEarlierIso(cursorBefore, upperBefore) : cursorBefore
      }
      if (upperBefore) p.before = upperBefore
      return p
    },
    [opts],
  )

  useEffect(() => {
    if (conversationId == null || conversationId === '') {
      setMessages([])
      setHasMoreOlder(false)
      setError('')
      setLoading(false)
      return undefined
    }

    let cancelled = false
    setLoading(true)
    setError('')
    ;(async () => {
      try {
        const firstParams = buildListParams({ page: 1, pageSize: PAGE_SIZE })
        const probeWrap = await withKeywordFallback(conversationId, firstParams, opts.keyword)
        const probe = probeWrap.data
        if (cancelled) return
        const total = typeof probe?.total === 'number' ? probe.total : 0
        const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE) || 1)
        let normalized = probeWrap.normalized
        if (lastPage > 1) {
          const pageWrap = await withKeywordFallback(
            conversationId,
            buildListParams({ page: lastPage, pageSize: PAGE_SIZE }),
            opts.keyword,
          )
          normalized = pageWrap.normalized
        }
        if (cancelled) return
        setMessages(normalized)
        setHasMoreOlder(lastPage > 1)
      } catch (e) {
        if (!cancelled) {
          setMessages([])
          setHasMoreOlder(false)
          setError(userFacingError(e, '加载消息失败'))
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [conversationId, buildListParams, opts.keyword])

  const loadOlder = useCallback(async () => {
    if (conversationId == null || conversationId === '') return
    if (loadingOlder || loading) return
    if (!hasMoreOlder) return
    const first = messages[0]
    let beforeIso = null
    if (first && typeof first.created_at === 'string') beforeIso = first.created_at
    else if (first && first.created_at instanceof Date) beforeIso = first.created_at.toISOString()
    if (!beforeIso) return

    const scrollEl =
      typeof document !== 'undefined' ? document.querySelector('.chatBody[data-chat-scroll="1"]') : null
    const prevScrollHeight = scrollEl?.scrollHeight ?? 0

    setLoadingOlder(true)
    try {
      const params = buildListParams({
        cursorBefore: beforeIso,
        page: 1,
        pageSize: PAGE_SIZE,
      })
      const wrap = await withKeywordFallback(
        conversationId,
        params,
        opts.keyword,
      )
      const normalized = wrap.normalized
      setMessages((prev) => [...normalized, ...prev])
      setHasMoreOlder(Boolean(wrap.data?.has_more))
      requestAnimationFrame(() => {
        const el =
          typeof document !== 'undefined'
            ? document.querySelector('.chatBody[data-chat-scroll="1"]')
            : null
        if (el && prevScrollHeight > 0) {
          el.scrollTop += el.scrollHeight - prevScrollHeight
        }
      })
    } catch (e) {
      setError(userFacingError(e, '加载更早消息失败'))
    } finally {
      setLoadingOlder(false)
    }
  }, [conversationId, buildListParams, hasMoreOlder, loading, loadingOlder, messages, opts.keyword])

  const refetch = useCallback(async () => {
    if (conversationId == null || conversationId === '') return
    try {
      const firstParams = buildListParams({ page: 1, pageSize: PAGE_SIZE })
      const probeWrap = await withKeywordFallback(conversationId, firstParams, opts.keyword)
      const probe = probeWrap.data
      const total = typeof probe?.total === 'number' ? probe.total : 0
      const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE) || 1)
      let normalized = probeWrap.normalized
      if (lastPage > 1) {
        const pageWrap = await withKeywordFallback(
          conversationId,
          buildListParams({ page: lastPage, pageSize: PAGE_SIZE }),
          opts.keyword,
        )
        normalized = pageWrap.normalized
      }
      setMessages(normalized)
      setHasMoreOlder(lastPage > 1)
      setError('')
    } catch (e) {
      setError(userFacingError(e, '刷新消息失败'))
    }
  }, [conversationId, buildListParams, opts.keyword])

  return {
    messages,
    loading,
    loadingOlder,
    hasMoreOlder,
    error,
    refetch,
    loadOlder,
  }
}
