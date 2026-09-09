import { useEffect, useMemo, useState } from 'react'
import RichMarkdown, { CodeBlock } from './RichMarkdown.jsx'

function fileName(file) {
  return String(file?.filename || file?.name || '文件')
}

function fileUrl(file) {
  return String(file?.url || file?.file_url || file?.download_url || file?.src || '')
}

function absoluteUrl(raw) {
  if (!raw) return ''
  try {
    return new URL(raw, window.location.origin).href
  } catch {
    return raw
  }
}

function isTextLike(file) {
  const mime = String(file?.mime_type || file?.type || '').toLowerCase()
  const name = fileName(file).toLowerCase()
  return (
    mime.startsWith('text/') ||
    ['application/json', 'application/xml', 'application/javascript', 'application/typescript'].includes(mime) ||
    /\.(txt|md|markdown|csv|tsv|json|xml|yaml|yml|py|js|jsx|ts|tsx|java|c|cpp|h|go|rs|sh|sql|css|html)$/.test(name)
  )
}

function isPdf(file) {
  const mime = String(file?.mime_type || file?.type || '').toLowerCase()
  const name = fileName(file).toLowerCase()
  return mime === 'application/pdf' || name.endsWith('.pdf')
}

function isOffice(file) {
  const mime = String(file?.mime_type || file?.type || '').toLowerCase()
  const name = fileName(file).toLowerCase()
  return (
    mime.includes('spreadsheet') ||
    mime.includes('excel') ||
    mime.includes('word') ||
    mime.includes('presentation') ||
    mime.includes('powerpoint') ||
    /\.(doc|docx|xls|xlsx|ppt|pptx|ods)$/.test(name)
  )
}

function isMarkdown(file) {
  return /\.(md|markdown)$/i.test(fileName(file))
}

function codeLanguage(file) {
  const name = fileName(file).toLowerCase()
  const ext = name.split('.').pop()
  const map = {
    c: 'cpp',
    h: 'cpp',
    cpp: 'cpp',
    cc: 'cpp',
    cxx: 'cpp',
    js: 'javascript',
    jsx: 'javascript',
    ts: 'typescript',
    tsx: 'typescript',
    py: 'python',
    java: 'java',
    go: 'go',
    rs: 'rust',
    md: 'markdown',
    markdown: 'markdown',
    json: 'json',
    css: 'css',
    html: 'html',
    sh: 'bash',
    sql: 'sql',
  }
  return map[ext] || ''
}

function officePreviewUrl(url) {
  const absolute = absoluteUrl(url)
  if (!/^https?:\/\//i.test(absolute)) return ''
  try {
    const u = new URL(absolute)
    if (['localhost', '127.0.0.1', '::1'].includes(u.hostname)) return ''
    return `https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(absolute)}`
  } catch {
    return ''
  }
}

export default function FilePreviewModal({ file, onClose }) {
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const url = fileUrl(file)
  const previewUrl = absoluteUrl(url)
  const textMode = useMemo(() => isTextLike(file), [file])
  const pdfMode = useMemo(() => isPdf(file), [file])
  const officeMode = useMemo(() => isOffice(file), [file])
  const officeUrl = useMemo(() => officePreviewUrl(url), [url])
  const language = useMemo(() => codeLanguage(file), [file])

  useEffect(() => {
    let cancelled = false
    if (!file || !url || !textMode) return undefined
    Promise.resolve()
      .then(() => {
        if (cancelled) return null
        setLoading(true)
        setError('')
        return fetch(previewUrl, { credentials: 'include' })
      })
      .then((res) => {
        if (!res) return null
        if (!res.ok) throw new Error('文件读取失败')
        return res.text()
      })
      .then((body) => {
        if (!cancelled && body != null) setText(body)
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || '文件读取失败')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [file, previewUrl, textMode, url])

  if (!file) return null

  return (
    <div className="modalBackdrop" role="presentation" onMouseDown={onClose}>
      <div className="filePreviewModal" role="dialog" aria-modal="true" aria-label="文件预览" onMouseDown={(e) => e.stopPropagation()}>
        <div className="filePreviewModal__head">
          <div>
            <div className="filePreviewModal__title">{fileName(file)}</div>
            <div className="filePreviewModal__sub">{file.mime_type || file.type || '未知类型'}</div>
          </div>
          <div className="filePreviewModal__actions">
            {officeUrl ? <a className="wxBtnLink" href={officeUrl} target="_blank" rel="noreferrer">在线预览</a> : null}
            {url ? <a className="wxBtnLink" href={previewUrl} target="_blank" rel="noreferrer">新窗口</a> : null}
            {url ? <a className="wxBtnLink" href={previewUrl} download>下载</a> : null}
            <button type="button" className="wxBtn" onClick={onClose}>关闭</button>
          </div>
        </div>
        <div className="filePreviewModal__body">
          {textMode ? (
            loading ? (
              <div className="wxNotice">正在读取文件…</div>
            ) : error ? (
              <div className="wxNotice is-err">{error}</div>
            ) : isMarkdown(file) ? (
              <RichMarkdown text={text} />
            ) : language ? (
              <CodeBlock code={text} language={language} />
            ) : (
              <pre className="filePreviewModal__text">{text}</pre>
            )
          ) : pdfMode && url ? (
            <iframe className="filePreviewModal__frame" src={previewUrl} title={fileName(file)} />
          ) : officeMode && officeUrl ? (
            <iframe className="filePreviewModal__frame" src={officeUrl} title={fileName(file)} />
          ) : officeMode && url ? (
            <div className="filePreviewModal__fallback">
              <div className="filePreviewModal__fileIcon">DOC</div>
              <div>
                <div className="filePreviewModal__fallbackTitle">Office 文件</div>
                <div className="filePreviewModal__fallbackText">当前文件地址不是公网 HTTP(S)，无法调用 Office 在线预览；可下载后查看。</div>
              </div>
            </div>
          ) : url ? (
            <iframe className="filePreviewModal__frame" src={previewUrl} title={fileName(file)} />
          ) : (
            <div className="wxNotice">该文件没有可访问地址</div>
          )}
        </div>
      </div>
    </div>
  )
}
