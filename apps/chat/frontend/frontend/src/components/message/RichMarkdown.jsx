import { Fragment } from 'react'

const KEYWORDS = {
  javascript: ['async', 'await', 'break', 'case', 'catch', 'class', 'const', 'continue', 'default', 'else', 'export', 'for', 'from', 'function', 'if', 'import', 'let', 'new', 'return', 'switch', 'throw', 'try', 'typeof', 'var', 'while'],
  typescript: ['async', 'await', 'break', 'case', 'catch', 'class', 'const', 'continue', 'default', 'else', 'export', 'for', 'from', 'function', 'if', 'import', 'interface', 'let', 'new', 'return', 'switch', 'throw', 'try', 'type', 'typeof', 'var', 'while'],
  python: ['and', 'as', 'async', 'await', 'break', 'class', 'continue', 'def', 'elif', 'else', 'except', 'False', 'for', 'from', 'if', 'import', 'in', 'is', 'lambda', 'None', 'not', 'or', 'pass', 'raise', 'return', 'True', 'try', 'while', 'with', 'yield'],
  java: ['abstract', 'boolean', 'break', 'case', 'catch', 'class', 'const', 'continue', 'default', 'else', 'extends', 'final', 'for', 'if', 'implements', 'import', 'int', 'interface', 'new', 'private', 'protected', 'public', 'return', 'static', 'switch', 'throw', 'try', 'void', 'while'],
  cpp: ['auto', 'bool', 'break', 'case', 'catch', 'class', 'const', 'continue', 'default', 'else', 'enum', 'for', 'if', 'include', 'int', 'namespace', 'new', 'private', 'protected', 'public', 'return', 'static', 'struct', 'switch', 'template', 'throw', 'try', 'void', 'while'],
  go: ['break', 'case', 'chan', 'const', 'continue', 'default', 'defer', 'else', 'fallthrough', 'for', 'func', 'go', 'if', 'import', 'interface', 'map', 'package', 'range', 'return', 'select', 'struct', 'switch', 'type', 'var'],
  rust: ['as', 'async', 'await', 'break', 'const', 'continue', 'crate', 'else', 'enum', 'false', 'fn', 'for', 'if', 'impl', 'in', 'let', 'loop', 'match', 'mod', 'move', 'mut', 'pub', 'ref', 'return', 'self', 'Self', 'static', 'struct', 'trait', 'true', 'type', 'unsafe', 'use', 'where', 'while'],
}

function normalizedLanguage(language) {
  const raw = String(language || 'text').toLowerCase()
  if (raw === 'js' || raw === 'jsx') return 'javascript'
  if (raw === 'ts' || raw === 'tsx') return 'typescript'
  if (raw === 'py') return 'python'
  if (raw === 'c++' || raw === 'cxx' || raw === 'c') return 'cpp'
  return raw
}

function tokenClass(token, language) {
  const lang = normalizedLanguage(language)
  if (lang === 'cpp' && /^#\s*(include|define|ifdef|ifndef|endif|pragma)\b/.test(token)) return 'tok-preprocessor'
  if (/^(['"`])[\s\S]*\1$/.test(token)) return 'tok-string'
  if (/^(\/\/|#|\/\*)/.test(token)) return 'tok-comment'
  if (/^\d+(\.\d+)?$/.test(token)) return 'tok-number'
  const words = KEYWORDS[lang] || []
  if (words.includes(token)) return 'tok-keyword'
  return ''
}

export function CodeBlock({ code, language = 'text' }) {
  const parts = String(code || '').match(/("(?:\\.|[^"])*"|'(?:\\.|[^'])*'|`(?:\\.|[^`])*`|\/\/.*|#.*|\/\*[\s\S]*?\*\/|\b\d+(?:\.\d+)?\b|\b[A-Za-z_][A-Za-z0-9_]*\b|\s+|.)/g) || []
  return (
    <pre className="msgCodeBlock">
      <code>
        {parts.map((part, idx) => {
          const cls = tokenClass(part, language)
          return cls ? <span key={`${idx}-${part}`} className={cls}>{part}</span> : <Fragment key={`${idx}-${part}`}>{part}</Fragment>
        })}
      </code>
    </pre>
  )
}

function inlineNodes(text) {
  const nodes = []
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g
  let last = 0
  let match
  while ((match = re.exec(text))) {
    if (match.index > last) nodes.push(text.slice(last, match.index))
    const token = match[0]
    if (token.startsWith('**')) {
      nodes.push(<strong key={`${match.index}-b`}>{token.slice(2, -2)}</strong>)
    } else if (token.startsWith('`')) {
      nodes.push(<code key={`${match.index}-c`} className="msgInlineCode">{token.slice(1, -1)}</code>)
    } else {
      const linkMatch = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/)
      const href = linkMatch?.[2] || '#'
      nodes.push(<a key={`${match.index}-a`} href={href} target="_blank" rel="noreferrer">{linkMatch?.[1] || href}</a>)
    }
    last = match.index + token.length
  }
  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}

export default function RichMarkdown({ text }) {
  const raw = String(text || '')
  if (!raw) return null

  const blocks = []
  const re = /```([A-Za-z0-9_+-]*)\n?([\s\S]*?)```/g
  let last = 0
  let match
  while ((match = re.exec(raw))) {
    if (match.index > last) blocks.push({ type: 'text', value: raw.slice(last, match.index) })
    blocks.push({ type: 'code', language: match[1] || 'text', value: match[2] || '' })
    last = match.index + match[0].length
  }
  if (last < raw.length) blocks.push({ type: 'text', value: raw.slice(last) })

  return (
    <div className="msgMarkdown">
      {blocks.map((block, blockIdx) => {
        if (block.type === 'code') {
          return <CodeBlock key={`code-${blockIdx}`} code={block.value} language={block.language} />
        }
        const lines = block.value.split(/\n/)
        return (
          <Fragment key={`text-${blockIdx}`}>
            {lines.map((line, idx) => {
              const trimmed = line.trim()
              if (!trimmed) return <div key={`${blockIdx}-${idx}`} className="msgMarkdown__gap" />
              const heading = trimmed.match(/^(#{1,3})\s+(.+)$/)
              if (heading) {
                const Tag = heading[1].length === 1 ? 'h4' : 'h5'
                return <Tag key={`${blockIdx}-${idx}`}>{inlineNodes(heading[2])}</Tag>
              }
              const list = trimmed.match(/^[-*]\s+(.+)$/)
              if (list) return <div key={`${blockIdx}-${idx}`} className="msgMarkdown__li">• {inlineNodes(list[1])}</div>
              return <p key={`${blockIdx}-${idx}`}>{inlineNodes(line)}</p>
            })}
          </Fragment>
        )
      })}
    </div>
  )
}
