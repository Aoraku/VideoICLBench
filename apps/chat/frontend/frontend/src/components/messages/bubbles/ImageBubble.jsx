export default function ImageBubble({ content }) {
  const url = content?.thumbnail_url || content?.url
  if (!url) return null
  return (
    <a href={content?.url || url} target="_blank" rel="noreferrer" className="msgMediaLink">
      <img className="msgImage" src={url} alt={content?.filename || 'image'} />
    </a>
  )
}
