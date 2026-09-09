export default function CodeBubble({ content }) {
  return (
    <pre className="msgCodeBlock">
      <code>{content?.code || ''}</code>
    </pre>
  )
}
