import { useEffect, useState } from 'react'
import { listMessageReplies } from '../../services/message.js'
import { normalizeMessageFromApi } from '../../utils/normalizeMessage.js'
import { getMessagePlainText } from '../../utils/messageText.js'

/**
 * @param {{
 *   open: boolean,
 *   conversationId: number|string,
 *   anchorMsgId: number|null,
 *   onClose: () => void,
 * }} props
 */
export default function MessageRepliesSheet({ open, conversationId, anchorMsgId, onClose }) {
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')
  const [original, setOriginal] = useState(/** @type {Record<string, unknown>|null} */ (null))
  const [rows, setRows] = useState(/** @type {Record<string, unknown>[]} */ ([]))

  useEffect(() => {
    if (!open || anchorMsgId == null) return
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setErr('')
      try {
        const data = await listMessageReplies(conversationId, anchorMsgId, { page: 1, pageSize: 50 })
        if (cancelled) return
        setOriginal(data?.original_msg && typeof data.original_msg === 'object' ? data.original_msg : null)
        const list = Array.isArray(data?.results) ? data.results.map((r) => normalizeMessageFromApi(r)) : []
        setRows(list.filter(Boolean))
      } catch (e) {
        setErr(e?.message || '加载回复失败')
        setRows([])
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [open, conversationId, anchorMsgId])

  if (!open) return null

  return (
    <div className="msgSheetOverlay" role="dialog" aria-modal="true" aria-label="回复列表">
      <button type="button" className="msgSheetOverlay__backdrop" aria-label="关闭" onClick={onClose} />
      <div className="msgSheet">
        <div className="msgSheet__head">
          <div className="msgSheet__title">回复串</div>
          <button type="button" className="msgSheet__close" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="msgSheet__body">
          {original ? (
            <div className="msgSheet__orig">
              <div className="msgSheet__origTitle">原消息</div>
              <div className="msgSheet__origSub">
                {String(original.sender_name || '')} · {String(original.content_summary || '')}
              </div>
            </div>
          ) : null}
          {loading ? <div className="msgSheet__hint">加载中…</div> : null}
          {err ? <div className="msgSheet__err">{err}</div> : null}
          <ul className="msgSheet__list">
            {rows.map((r, i) => (
              <li key={String(r.msg_id ?? `r-${i}`)} className="msgSheet__row">
                <div className="msgSheet__who">
                  {(r.sender && r.sender.username) || '用户'} · {String(r.created_at || '')}
                </div>
                <div className="msgSheet__text">{getMessagePlainText(r.content, String(r.type || 'text'))}</div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
