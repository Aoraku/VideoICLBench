function formatFileSize(size) {
  const n = Number(size)
  if (!Number.isFinite(n) || n <= 0) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

export default function FileBubble({ content }) {
  const url = content?.url
  const name = content?.filename || 'file'
  const body = (
    <>
      <span className="msgFileCard__icon" aria-hidden>FILE</span>
      <span className="msgFileCard__main">
        <span className="msgFileCard__name">{name}</span>
        <span className="msgFileCard__meta">{formatFileSize(content?.size)}</span>
      </span>
    </>
  )
  return url ? (
    <a href={url} target="_blank" rel="noreferrer" className="msgFileCard">{body}</a>
  ) : (
    <span className="msgFileCard">{body}</span>
  )
}
