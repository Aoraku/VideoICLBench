export default function TextBubble({ content }) {
  const text = typeof content === 'string' ? content : content?.text
  return <span>{text || ''}</span>
}
