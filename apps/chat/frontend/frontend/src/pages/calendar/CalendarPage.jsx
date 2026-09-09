import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  createCalendarEvent,
  deleteCalendarEvent,
  getCalendarAvailability,
  listCalendarEvents,
  updateCalendarEvent,
} from '../../api/calendar.js'
import { listFriends } from '../../api/friends.js'
import { useCurrentUserId } from '../../hooks/useCurrentUserId.js'
import { resolveAvatarSrc } from '../../utils/avatarUrl.js'
import { getFriendDisplayName } from '../../utils/friends.js'
import { userFacingError } from '../../utils/userFacingError.js'

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日']
const MONTHS = ['一月', '二月', '三月', '四月', '五月', '六月', '七月', '八月', '九月', '十月', '十一月', '十二月']
const YEAR_WINDOW_SIZE = 12

function pad(n) {
  return String(n).padStart(2, '0')
}

const HOUR_OPTIONS = Array.from({ length: 24 }, (_, idx) => pad(idx))
const MINUTE_OPTIONS = Array.from({ length: 12 }, (_, idx) => pad(idx * 5))

function splitTime(value) {
  const [rawHour, rawMinute] = String(value || '00:00').split(':')
  const hour = Math.max(0, Math.min(23, Number(rawHour)))
  const minute = Math.max(0, Math.min(55, Math.round(Number(rawMinute) / 5) * 5))
  return {
    hour: pad(Number.isFinite(hour) ? hour : 0),
    minute: pad(Number.isFinite(minute) ? minute : 0),
  }
}

function buildTime(hour, minute) {
  return `${pad(Number(hour))}:${pad(Number(minute))}`
}

function TimePicker({ label, value, onChange }) {
  const time = splitTime(value)
  return (
    <div className="calendarTimeGroup">
      <div className="calendarTimeGroup__label">{label}</div>
      <div className="calendarTimeGroup__controls">
        <label className="calendarSelectWrap">
          <select
            value={time.hour}
            onChange={(e) => onChange(buildTime(e.target.value, time.minute))}
            aria-label={`${label}小时`}
          >
            {HOUR_OPTIONS.map((option) => (
              <option key={`${label}-hour-${option}`} value={option}>{option}</option>
            ))}
          </select>
          <span>时</span>
        </label>
        <label className="calendarSelectWrap">
          <select
            value={time.minute}
            onChange={(e) => onChange(buildTime(time.hour, e.target.value))}
            aria-label={`${label}分钟`}
          >
            {MINUTE_OPTIONS.map((option) => (
              <option key={`${label}-minute-${option}`} value={option}>{option}</option>
            ))}
          </select>
          <span>分</span>
        </label>
      </div>
    </div>
  )
}

function dateKey(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function timeValue(date) {
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function startOfMonth(date) {
  return new Date(date.getFullYear(), date.getMonth(), 1, 0, 0, 0, 0)
}

function addMonths(date, delta) {
  return new Date(date.getFullYear(), date.getMonth() + delta, 1, 0, 0, 0, 0)
}

function endOfMonthExclusive(date) {
  return new Date(date.getFullYear(), date.getMonth() + 1, 1, 0, 0, 0, 0)
}

function monthGrid(cursor) {
  const first = startOfMonth(cursor)
  const mondayOffset = (first.getDay() + 6) % 7
  const start = new Date(first)
  start.setDate(first.getDate() - mondayOffset)
  return Array.from({ length: 42 }, (_, idx) => {
    const d = new Date(start)
    d.setDate(start.getDate() + idx)
    return d
  })
}

function localDateTimeIso(day, time) {
  const [h, m] = String(time || '00:00').split(':').map((x) => Number(x))
  const d = new Date(day)
  d.setHours(Number.isFinite(h) ? h : 0, Number.isFinite(m) ? m : 0, 0, 0)
  return d.toISOString()
}

function formatRange(event) {
  try {
    const s = new Date(event.start_at)
    const e = new Date(event.end_at)
    return `${timeValue(s)} - ${timeValue(e)}`
  } catch {
    return ''
  }
}

function dayOverlap(event, selectedKey) {
  const s = new Date(event.start_at)
  const e = new Date(event.end_at)
  if (Number.isNaN(s.getTime()) || Number.isNaN(e.getTime())) return false
  const day = new Date(`${selectedKey}T00:00:00`)
  const next = new Date(day)
  next.setDate(day.getDate() + 1)
  return s < next && e > day
}

function emptyForm(day) {
  return {
    title: '',
    description: '',
    date: dateKey(day),
    startTime: '09:00',
    endTime: '10:00',
    inviteeIds: [],
  }
}

export default function CalendarPage() {
  const { userId } = useCurrentUserId()
  const [cursor, setCursor] = useState(() => startOfMonth(new Date()))
  const [mode, setMode] = useState('month')
  const [yearWindowStart, setYearWindowStart] = useState(() => new Date().getFullYear() - 5)
  const [selectedDay, setSelectedDay] = useState(() => new Date())
  const [events, setEvents] = useState([])
  const [friends, setFriends] = useState([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [editingEventId, setEditingEventId] = useState(null)
  const [form, setForm] = useState(() => emptyForm(new Date()))
  const [availability, setAvailability] = useState([])
  const [availabilityLoading, setAvailabilityLoading] = useState(false)

  const selectedKey = dateKey(selectedDay)
  const grid = useMemo(() => monthGrid(cursor), [cursor])
  const selectedEvents = useMemo(
    () => events.filter((event) => dayOverlap(event, selectedKey)).sort((a, b) => new Date(a.start_at) - new Date(b.start_at)),
    [events, selectedKey],
  )

  const loadMonth = useCallback(async (targetCursor = cursor) => {
    setLoading(true)
    setError('')
    try {
      const data = await listCalendarEvents({
        startAt: startOfMonth(targetCursor).toISOString(),
        endAt: endOfMonthExclusive(targetCursor).toISOString(),
        pageSize: 200,
      })
      setEvents(Array.isArray(data?.results) ? data.results : [])
    } catch (err) {
      setError(userFacingError(err, '加载日程失败'))
    } finally {
      setLoading(false)
    }
  }, [cursor])

  useEffect(() => {
    void loadMonth()
  }, [loadMonth])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const data = await listFriends({ page: 1, pageSize: 100 })
        if (!cancelled) setFriends(Array.isArray(data?.results) ? data.results : [])
      } catch {
        if (!cancelled) setFriends([])
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (editingEventId) return
    setForm((prev) => ({ ...prev, date: selectedKey }))
  }, [editingEventId, selectedKey])

  const checkAvailability = useCallback(async () => {
    if (!form.inviteeIds.length) {
      setAvailability([])
      return
    }
    const day = new Date(`${form.date}T00:00:00`)
    const startAt = localDateTimeIso(day, form.startTime)
    const endAt = localDateTimeIso(day, form.endTime)
    setAvailabilityLoading(true)
    try {
      const data = await getCalendarAvailability({ userIds: form.inviteeIds, startAt, endAt })
      setAvailability(Array.isArray(data?.results) ? data.results : [])
    } catch (err) {
      setError(userFacingError(err, '检查冲突失败'))
    } finally {
      setAvailabilityLoading(false)
    }
  }, [form.date, form.endTime, form.inviteeIds, form.startTime])

  useEffect(() => {
    if (!form.inviteeIds.length) {
      setAvailability([])
      return undefined
    }
    const timer = window.setTimeout(() => {
      void checkAvailability()
    }, 360)
    return () => window.clearTimeout(timer)
  }, [checkAvailability, form.inviteeIds.length])

  function selectDay(day) {
    setSelectedDay(day)
    setMode('month')
    if (!editingEventId) setForm((prev) => ({ ...prev, date: dateKey(day) }))
  }

  function editEvent(event) {
    const start = new Date(event.start_at)
    const end = new Date(event.end_at)
    setEditingEventId(event.event_id)
    setSelectedDay(start)
    setForm({
      title: event.title || '',
      description: event.description || '',
      date: dateKey(start),
      startTime: timeValue(start),
      endTime: timeValue(end),
      inviteeIds: [],
    })
  }

  async function submitEvent(event) {
    event.preventDefault()
    const title = form.title.trim()
    if (!title) {
      setError('请输入日程名称')
      return
    }
    const day = new Date(`${form.date}T00:00:00`)
    const startAt = localDateTimeIso(day, form.startTime)
    const endAt = localDateTimeIso(day, form.endTime)
    if (new Date(endAt) <= new Date(startAt)) {
      setError('结束时间必须晚于开始时间')
      return
    }
    setSaving(true)
    setError('')
    setNotice('')
    try {
      if (editingEventId) {
        await updateCalendarEvent(editingEventId, {
          title,
          description: form.description.trim(),
          startAt,
          endAt,
        })
        setNotice('日程已更新')
      } else {
        await createCalendarEvent({
          title,
          description: form.description.trim(),
          startAt,
          endAt,
          inviteeIds: form.inviteeIds,
        })
        setNotice('日程已创建')
      }
      setEditingEventId(null)
      setForm(emptyForm(day))
      setSelectedDay(day)
      const nextCursor = startOfMonth(day)
      setCursor(nextCursor)
      await loadMonth(nextCursor)
    } catch (err) {
      setError(userFacingError(err, editingEventId ? '更新日程失败' : '创建日程失败'))
    } finally {
      setSaving(false)
    }
  }

  async function removeEvent(event) {
    if (!event?.event_id) return
    setSaving(true)
    setError('')
    try {
      await deleteCalendarEvent(event.event_id)
      if (String(editingEventId) === String(event.event_id)) {
        setEditingEventId(null)
        setForm(emptyForm(selectedDay))
      }
      await loadMonth()
      setNotice('日程已删除')
    } catch (err) {
      setError(userFacingError(err, '删除日程失败'))
    } finally {
      setSaving(false)
    }
  }

  function toggleInvitee(userId) {
    const id = Number(userId)
    if (!Number.isFinite(id) || id <= 0) return
    setForm((prev) => ({
      ...prev,
      inviteeIds: prev.inviteeIds.includes(id)
        ? prev.inviteeIds.filter((x) => x !== id)
        : [...prev.inviteeIds, id],
    }))
  }

  const currentYear = cursor.getFullYear()
  const currentMonth = cursor.getMonth()
  const years = useMemo(
    () => Array.from({ length: YEAR_WINDOW_SIZE }, (_, idx) => yearWindowStart + idx),
    [yearWindowStart],
  )
  const heroTitle = mode === 'year'
    ? `${yearWindowStart} - ${yearWindowStart + YEAR_WINDOW_SIZE - 1}`
    : mode === 'monthPick'
      ? `${currentYear} 年`
      : `${currentYear} 年 ${currentMonth + 1} 月`

  return (
    <div className="calendarPage">
      <header className="calendarHero">
        <div>
          <div className="calendarHero__kicker">日历</div>
          <div className="calendarHero__title">{heroTitle}</div>
        </div>
        <div className="calendarHero__actions">
          <button
            type="button"
            className="calendarIconBtn"
            onClick={() => {
              if (mode === 'year') setYearWindowStart((year) => year - YEAR_WINDOW_SIZE)
              else if (mode === 'monthPick') setCursor((d) => new Date(d.getFullYear() - 1, d.getMonth(), 1))
              else setCursor((d) => addMonths(d, -1))
            }}
            aria-label="上一个"
          >
            ‹
          </button>
          <button type="button" className="calendarModeBtn" onClick={() => {
            setYearWindowStart(currentYear - 5)
            setMode('year')
          }}>
            年视图
          </button>
          <button type="button" className="calendarModeBtn" onClick={() => {
            const today = new Date()
            setCursor(startOfMonth(today))
            selectDay(today)
          }}>
            今天
          </button>
          <button
            type="button"
            className="calendarIconBtn"
            onClick={() => {
              if (mode === 'year') setYearWindowStart((year) => year + YEAR_WINDOW_SIZE)
              else if (mode === 'monthPick') setCursor((d) => new Date(d.getFullYear() + 1, d.getMonth(), 1))
              else setCursor((d) => addMonths(d, 1))
            }}
            aria-label="下一个"
          >
            ›
          </button>
        </div>
      </header>

      {error ? <div className="wxNotice is-err calendarNotice">{error}</div> : null}
      {notice ? <div className="wxNotice is-ok calendarNotice">{notice}</div> : null}

      <main className="calendarShell">
        <section className="calendarBoard" aria-label="日历">
          {mode === 'year' ? (
            <div className="calendarYearGrid">
              {years.map((year) => (
                <button
                  type="button"
                  key={year}
                  className={`calendarYearTile${year === currentYear ? ' is-active' : ''}`}
                  onClick={() => {
                    const next = new Date(year, currentMonth, 1)
                    setCursor(next)
                    setSelectedDay(next)
                    setForm((prev) => ({ ...prev, date: dateKey(next) }))
                    setMode('monthPick')
                  }}
                >
                  <span>{year}</span>
                  <small>选择月份</small>
                </button>
              ))}
            </div>
          ) : mode === 'monthPick' ? (
            <div className="calendarYearGrid">
              {MONTHS.map((label, idx) => (
                <button
                  type="button"
                  key={label}
                  className={`calendarMonthTile${idx === currentMonth ? ' is-active' : ''}`}
                  onClick={() => {
                    const next = new Date(currentYear, idx, 1)
                    setCursor(next)
                    setSelectedDay(next)
                    setForm((prev) => ({ ...prev, date: dateKey(next) }))
                    setMode('month')
                  }}
                >
                  <span>{label}</span>
                  <small>{currentYear}</small>
                </button>
              ))}
            </div>
          ) : (
            <>
              <div className="calendarWeekHead">
                {WEEKDAYS.map((w) => <span key={w}>{w}</span>)}
              </div>
              <div className="calendarGrid">
                {grid.map((day) => {
                  const key = dateKey(day)
                  const inMonth = day.getMonth() === currentMonth
                  const active = key === selectedKey
                  const today = key === dateKey(new Date())
                  const count = events.filter((event) => dayOverlap(event, key)).length
                  return (
                    <button
                      type="button"
                      key={key}
                      className={`calendarDay${inMonth ? '' : ' is-muted'}${active ? ' is-active' : ''}${today ? ' is-today' : ''}`}
                      onClick={() => selectDay(day)}
                    >
                      <span className="calendarDay__num">{day.getDate()}</span>
                      {count > 0 ? <span className="calendarDay__count">{count}</span> : null}
                    </button>
                  )
                })}
              </div>
            </>
          )}
          {loading ? <div className="calendarLoading">加载日程中…</div> : null}
        </section>

        <aside className="calendarSide">
          <section className="calendarPanel">
            <div className="calendarPanel__title">{selectedKey} 日程</div>
            <div className="calendarTimeline">
              {selectedEvents.length === 0 ? (
                <div className="calendarTimeline__empty">这一天没有日程</div>
              ) : selectedEvents.map((event) => (
                <article key={event.event_id} className="calendarEventCard">
                  <div className="calendarEventCard__time">{formatRange(event)}</div>
                  <div className="calendarEventCard__title">{event.title}</div>
                  {event.description ? <div className="calendarEventCard__desc">{event.description}</div> : null}
                  <div className="calendarEventCard__meta">
                    {event.participants?.length ? `${event.participants.length} 人参与` : '个人日程'}
                    {event.creator?.user_id === userId ? ' · 我创建的' : ''}
                  </div>
                  <div className="calendarEventCard__actions">
                    <button type="button" className="wxBtn" onClick={() => editEvent(event)}>
                      修改
                    </button>
                    <button type="button" className="wxBtn wxBtn--danger" disabled={saving} onClick={() => void removeEvent(event)}>
                      删除
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="calendarPanel">
            <div className="calendarPanel__title">{editingEventId ? '修改日程' : '添加日程'}</div>
            <form className="calendarForm" onSubmit={submitEvent}>
              <input value={form.title} onChange={(e) => setForm((p) => ({ ...p, title: e.target.value }))} placeholder="日程名称" />
              <div className="calendarForm__row calendarForm__row--date">
                <input type="date" value={form.date} onChange={(e) => setForm((p) => ({ ...p, date: e.target.value }))} />
              </div>
              <div className="calendarTimeRange">
                <TimePicker
                  label="开始"
                  value={form.startTime}
                  onChange={(value) => setForm((p) => ({ ...p, startTime: value }))}
                />
                <TimePicker
                  label="结束"
                  value={form.endTime}
                  onChange={(value) => setForm((p) => ({ ...p, endTime: value }))}
                />
              </div>
              <textarea value={form.description} onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))} placeholder="说明，可留空" rows={3} />

              {!editingEventId ? (
                <div className="calendarInviteBox">
                  <div className="calendarInviteBox__head">
                    <span>邀请好友</span>
                    <button type="button" onClick={() => void checkAvailability()} disabled={availabilityLoading || !form.inviteeIds.length}>
                      {availabilityLoading ? '检查中…' : '检查冲突'}
                    </button>
                  </div>
                  <div className="calendarFriendList">
                    {friends.length === 0 ? <div className="calendarFriendList__empty">暂无好友可邀请</div> : null}
                    {friends.map((friend) => {
                      const id = Number(friend.user_id)
                      const checked = form.inviteeIds.includes(id)
                      const avatarSrc = resolveAvatarSrc(friend.avatar)
                      const conflict = availability.find((row) => Number(row.user_id) === id)
                      return (
                        <label key={friend.user_id} className={`calendarFriend${checked ? ' is-selected' : ''}`}>
                          <input type="checkbox" checked={checked} onChange={() => toggleInvitee(id)} />
                          <span className="calendarFriend__avatar" style={avatarSrc ? { backgroundImage: `url(${avatarSrc})` } : undefined} aria-hidden>
                            {!avatarSrc ? getFriendDisplayName(friend).slice(0, 1).toUpperCase() : null}
                          </span>
                          <span className="calendarFriend__main">
                            <span>{getFriendDisplayName(friend)}</span>
                            <small className={conflict?.has_conflict ? 'is-busy' : ''}>
                              {conflict ? (conflict.has_conflict ? '该时间已有日程' : '该时间空闲') : '@' + (friend.username || friend.user_id)}
                            </small>
                          </span>
                        </label>
                      )
                    })}
                  </div>
                </div>
              ) : null}

              <div className="calendarForm__actions">
                {editingEventId ? (
                  <button type="button" className="wxBtn" onClick={() => {
                    setEditingEventId(null)
                    setForm(emptyForm(selectedDay))
                  }}>
                    取消修改
                  </button>
                ) : null}
                <button type="submit" className="wxBtn wxBtn--primary" disabled={saving}>
                  {saving ? '保存中…' : editingEventId ? '保存修改' : '创建日程'}
                </button>
              </div>
            </form>
          </section>
        </aside>
      </main>
    </div>
  )
}
