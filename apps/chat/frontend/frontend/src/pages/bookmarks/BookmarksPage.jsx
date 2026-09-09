import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { addBookmark, deleteBookmark, listBookmarks, reorderBookmarks, updateBookmark } from '../../api/messages.js'
import { summarizeMessageContent } from '../../utils/messageContent.js'
import { userFacingError } from '../../utils/userFacingError.js'

const PAGE_SIZE = 100

function formatTime(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      month: 'numeric',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
}

function messageSummary(row) {
  if (row?.title) return String(row.title)
  const message = row?.message && typeof row.message === 'object' ? row.message : {}
  const type = typeof message.type === 'string' ? message.type : 'text'
  const content = message.content && typeof message.content === 'object' ? message.content : {}
  return summarizeMessageContent(type, content) || '[消息]'
}

export default function BookmarksPage() {
  const [items, setItems] = useState([])
  const [archivedItems, setArchivedItems] = useState([])
  const [tab, setTab] = useState('active')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [pendingId, setPendingId] = useState(null)
  const [draggingId, setDraggingId] = useState(null)
  const [manualTitle, setManualTitle] = useState('')
  const [manualNote, setManualNote] = useState('')
  const [manualSaving, setManualSaving] = useState(false)
  const navigate = useNavigate()

  const loadPage = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [activeData, archivedData] = await Promise.all([
        listBookmarks({ page: 1, pageSize: PAGE_SIZE, archived: false }),
        listBookmarks({ page: 1, pageSize: PAGE_SIZE, archived: true }),
      ])
      setItems(Array.isArray(activeData?.results) ? activeData.results : [])
      setArchivedItems(Array.isArray(archivedData?.results) ? archivedData.results : [])
    } catch (err) {
      setError(userFacingError(err, '加载待办失败'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadPage()
  }, [loadPage])

  async function onDelete(bookmarkId) {
    if (!bookmarkId) return
    setPendingId(bookmarkId)
    setError('')
    try {
      await deleteBookmark(bookmarkId)
      setItems((prev) => prev.filter((item) => item.bookmark_id !== bookmarkId))
      setArchivedItems((prev) => prev.filter((item) => item.bookmark_id !== bookmarkId))
    } catch (err) {
      setError(userFacingError(err, '删除待办失败'))
    } finally {
      setPendingId(null)
    }
  }

  async function onArchive(row, archived) {
    const bookmarkId = row?.bookmark_id
    if (!bookmarkId) return
    setPendingId(bookmarkId)
    setError('')
    try {
      const updated = await updateBookmark(bookmarkId, { is_archived: archived })
      if (archived) {
        setItems((prev) => prev.filter((item) => item.bookmark_id !== bookmarkId))
        setArchivedItems((prev) => [updated, ...prev])
      } else {
        setArchivedItems((prev) => prev.filter((item) => item.bookmark_id !== bookmarkId))
        setItems((prev) => [...prev, updated].sort((a, b) => Number(a.position) - Number(b.position)))
      }
    } catch (err) {
      setError(userFacingError(err, archived ? '归档待办失败' : '恢复待办失败'))
    } finally {
      setPendingId(null)
    }
  }

  async function onManualAdd(event) {
    event.preventDefault()
    const title = manualTitle.trim()
    if (!title) {
      setError('请输入待办标题')
      return
    }
    setManualSaving(true)
    setError('')
    try {
      const created = await addBookmark({ title, note: manualNote.trim() })
      setItems((prev) => [...prev, created].sort((a, b) => Number(a.position) - Number(b.position)))
      setManualTitle('')
      setManualNote('')
      setTab('active')
    } catch (err) {
      setError(userFacingError(err, '新增待办失败'))
    } finally {
      setManualSaving(false)
    }
  }

  function openTodo(row) {
    const convId = Number(row?.conversation_id)
    const msgId = Number(row?.msg_id)
    if (!Number.isFinite(convId) || convId <= 0) return
    const query = new URLSearchParams({ open: String(convId) })
    if (Number.isFinite(msgId) && msgId > 0) query.set('msg', String(msgId))
    navigate(`/chat?${query.toString()}`)
  }

  async function onDropOn(targetId) {
    if (!draggingId || draggingId === targetId) {
      setDraggingId(null)
      return
    }
    const fromIdx = items.findIndex((item) => String(item.bookmark_id) === String(draggingId))
    const toIdx = items.findIndex((item) => String(item.bookmark_id) === String(targetId))
    if (fromIdx < 0 || toIdx < 0) {
      setDraggingId(null)
      return
    }
    const next = [...items]
    const [moved] = next.splice(fromIdx, 1)
    next.splice(toIdx, 0, moved)
    const reordered = next.map((item, idx) => ({ ...item, position: idx + 1 }))
    setItems(reordered)
    setDraggingId(null)
    try {
      await reorderBookmarks(reordered.map((item) => item.bookmark_id))
    } catch (err) {
      setError(userFacingError(err, '保存排序失败'))
      void loadPage()
    }
  }

  const rows = tab === 'active' ? items : archivedItems

  return (
    <div className="wxPage">
      <div className="wxHeader">
        <div className="wxHeader__left">
          <Link className="wxBack" to="/chat" aria-label="返回">
            ‹
          </Link>
          <div>
            <div className="wxTitle">我的待办</div>
            <div className="wxSub">{items.length ? `${items.length} 项待办` : '从消息菜单加入待办'}</div>
          </div>
        </div>
        <div className="wxActions">
          <button type="button" className="wxBtn" onClick={() => void loadPage()} disabled={loading}>
            {loading ? '刷新中…' : '刷新'}
          </button>
        </div>
      </div>

      <div className="wxCard">
        <form className="wxTodoComposer" onSubmit={onManualAdd}>
          <input
            className="wxSearchInput"
            value={manualTitle}
            onChange={(e) => setManualTitle(e.target.value)}
            placeholder="手动添加待办"
          />
          <input
            className="wxSearchInput"
            value={manualNote}
            onChange={(e) => setManualNote(e.target.value)}
            placeholder="备注，可留空"
          />
          <button type="submit" className="wxBtn wxBtn--primary" disabled={manualSaving}>
            {manualSaving ? '添加中…' : '添加'}
          </button>
        </form>
        <div className="wxTabs">
          <button type="button" className={`wxTab${tab === 'active' ? ' is-active' : ''}`} onClick={() => setTab('active')}>
            待办
          </button>
          <button type="button" className={`wxTab${tab === 'archived' ? ' is-active' : ''}`} onClick={() => setTab('archived')}>
            已归档
          </button>
        </div>
        {error ? <div className="wxNotice is-err">{error}</div> : null}
        {loading && rows.length === 0 ? <div className="wxNotice">加载中…</div> : null}
        {!loading && rows.length === 0 ? <div className="wxNotice">{tab === 'active' ? '暂无待办' : '暂无已归档待办'}</div> : null}

        <ul className="wxList">
          {rows.map((item) => {
            const message = item?.message && typeof item.message === 'object' ? item.message : {}
            const bookmarkId = item.bookmark_id
            return (
              <li
                key={bookmarkId}
                className={`wxItem wxBookmarkItem${draggingId === bookmarkId ? ' is-dragging' : ''}`}
                draggable={tab === 'active'}
                onDragStart={() => setDraggingId(bookmarkId)}
                onDragEnd={() => setDraggingId(null)}
                onDragOver={(e) => {
                  if (tab === 'active') e.preventDefault()
                }}
                onDrop={() => void onDropOn(bookmarkId)}
              >
                <span className="wxBookmarkItem__drag" aria-hidden>{tab === 'active' ? '☰' : ''}</span>
                <button type="button" className="wxBookmarkItem__main" onClick={() => openTodo(item)}>
                  <span className="wxBookmarkItem__title">{item.conversation_name || (item.conversation_id ? '聊天消息' : '待办')}</span>
                  <span className="wxBookmarkItem__summary">{messageSummary(item)}</span>
                  {item.note ? <span className="wxBookmarkItem__note">{item.note}</span> : null}
                  <span className="wxBookmarkItem__meta">
                    {item.message ? `${message.sender_name || '未知用户'} · ` : '手动添加 · '}
                    {formatTime(message.created_at || item.created_at)}
                  </span>
                </button>
                <div className="wxActions">
                  {tab === 'active' ? (
                    <button type="button" className="wxBtn wxBtn--primary" onClick={() => void onArchive(item, true)} disabled={pendingId === bookmarkId}>
                      完成
                    </button>
                  ) : (
                    <button type="button" className="wxBtn" onClick={() => void onArchive(item, false)} disabled={pendingId === bookmarkId}>
                      恢复
                    </button>
                  )}
                  <button type="button" className="wxBtn wxBtn--danger" onClick={() => void onDelete(bookmarkId)} disabled={pendingId === bookmarkId}>
                    删除
                  </button>
                </div>
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}
