import { useEffect, useMemo, useState } from 'react'
import { getManual } from '../../api/manual.js'
import { userFacingError } from '../../utils/userFacingError.js'

export default function HelpPage() {
  const [manual, setManual] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError('')
      try {
        const data = await getManual()
        if (!cancelled) setManual(data)
      } catch (err) {
        if (!cancelled) setError(userFacingError(err, '加载帮助文档失败'))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const sections = useMemo(() => (Array.isArray(manual?.sections) ? manual.sections : []), [manual])

  return (
    <div className="manualPage">
      <header className="manualHero">
        <div>
          <div className="manualHero__kicker">帮助中心</div>
          <h1>{manual?.title || 'ChatGLMJ 帮助文档'}</h1>
          <p>这里列出系统支持的功能和常用操作路径。AI 助手也会参考这份文档回答软件使用问题。</p>
        </div>
      </header>

      {error ? <div className="wxNotice is-err manualNotice">{error}</div> : null}
      {loading ? <div className="wxNotice manualNotice">加载帮助文档中…</div> : null}

      {!loading && sections.length > 0 ? (
        <main className="manualShell">
          <aside className="manualNav" aria-label="帮助目录">
            <div className="manualNav__title">目录</div>
            {sections.map((section) => (
              <a key={section.title} href={`#manual-${section.title}`}>
                {section.title}
              </a>
            ))}
          </aside>
          <article className="manualDoc">
            {sections.map((section, idx) => (
              <section key={section.title} id={`manual-${section.title}`} className="manualSection">
                <div className="manualSection__index">{String(idx + 1).padStart(2, '0')}</div>
                <div className="manualSection__body">
                  <h2>{section.title}</h2>
                  <ul>
                    {(Array.isArray(section.items) ? section.items : []).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              </section>
            ))}
          </article>
        </main>
      ) : null}
    </div>
  )
}

