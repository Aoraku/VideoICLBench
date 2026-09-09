export default function AudioBubble({ content }) {
  if (!content?.url) return null
  return <audio className="msgAudio" src={content.url} controls />
}
