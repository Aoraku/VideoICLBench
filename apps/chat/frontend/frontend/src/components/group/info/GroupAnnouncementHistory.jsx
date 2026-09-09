/**
 * @param {{ announcements: import('../../../types/group.js').GroupAnnouncement[] }} props
 */
export default function GroupAnnouncementHistory({ announcements }) {
  return (
    <section className="groupCard groupAnnHistory">
      <h2 className="groupCard__title">历史群公告</h2>
      {announcements.length === 0 ? (
        <p className="groupMuted">暂无公告</p>
      ) : (
        <ol className="groupAnnHistory__ol">
          {announcements.map((a) => (
            <li key={a.id} className="groupAnnHistory__item">
              <div className="groupAnnHistory__meta">
                <span className="groupAnnHistory__who">{a.publisherName || '—'}</span>
                <time className="groupAnnHistory__time" dateTime={a.createdAt}>
                  {formatTime(a.createdAt)}
                </time>
              </div>
              <p className="groupAnnHistory__content">{a.content}</p>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

function formatTime(iso) {
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleString('zh-CN')
  } catch {
    return iso
  }
}
