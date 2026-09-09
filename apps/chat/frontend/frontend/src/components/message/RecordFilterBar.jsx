import { useState } from 'react'

/**
 * @param {{
 *   onApply: (filter: { keyword?: string, sender_id?: string, before?: string, after?: string, type?: string }) => void,
 *   onReset: () => void,
 * }} props
 */
export default function RecordFilterBar({ onApply, onReset }) {
  const [open, setOpen] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [senderId, setSenderId] = useState('')
  const [before, setBefore] = useState('')
  const [after, setAfter] = useState('')
  const [type, setType] = useState('')

  const submit = () => {
    onApply({
      keyword: keyword.trim() || undefined,
      sender_id: senderId.trim() || undefined,
      before: before.trim() || undefined,
      after: after.trim() || undefined,
      type: type.trim() || undefined,
    })
    setOpen(false)
  }

  return (
    <>
      <button type="button" className="recordFilterBtn" onClick={() => setOpen(true)}>
        筛选记录
      </button>
      <button type="button" className="recordFilterBtn recordFilterBtn--ghost" onClick={onReset}>
        恢复默认
      </button>

      {open ? (
        <div className="msgSheetOverlay" role="dialog" aria-modal="true" aria-label="筛选聊天记录">
          <button type="button" className="msgSheetOverlay__backdrop" aria-label="关闭" onClick={() => setOpen(false)} />
          <div className="msgSheet msgSheet--narrow">
            <div className="msgSheet__head">
              <div className="msgSheet__title">筛选记录</div>
              <button type="button" className="msgSheet__close" onClick={() => setOpen(false)}>
                ×
              </button>
            </div>
            <div className="msgSheet__body msgSheet__form">
              <label className="msgField">
                <span>关键词</span>
                <input value={keyword} onChange={(e) => setKeyword(e.target.value)} placeholder="正文关键词" />
              </label>
              <label className="msgField">
                <span>发送者 user_id</span>
                <input value={senderId} onChange={(e) => setSenderId(e.target.value)} placeholder="群聊常用" />
              </label>
              <label className="msgField">
                <span>消息类型</span>
                <input value={type} onChange={(e) => setType(e.target.value)} placeholder="text / image / file" />
              </label>
              <label className="msgField">
                <span>before (ISO)</span>
                <input value={before} onChange={(e) => setBefore(e.target.value)} placeholder="2026-03-15T00:00:00Z" />
              </label>
              <label className="msgField">
                <span>after (ISO)</span>
                <input value={after} onChange={(e) => setAfter(e.target.value)} placeholder="2026-03-14T00:00:00Z" />
              </label>
              <div className="msgSheet__actions">
                <button type="button" className="wxBtn" onClick={() => setOpen(false)}>
                  取消
                </button>
                <button type="button" className="wxBtn wxBtn--primary" onClick={submit}>
                  应用
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}
