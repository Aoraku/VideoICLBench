export default function ForwardBubble({ content }) {
  const summary = Array.isArray(content?.summary) ? content.summary : []
  return (
    <div className="msgForwardCard">
      <div className="msgForwardCard__title">{content?.title || 'Chat history'}</div>
      {summary.slice(0, 3).map((line, idx) => (
        <div key={`${line}-${idx}`} className="msgForwardCard__line">{String(line)}</div>
      ))}
    </div>
  )
}
