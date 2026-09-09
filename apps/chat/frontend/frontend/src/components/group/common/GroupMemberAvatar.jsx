import { resolveAvatarSrc } from '../../../utils/avatarUrl.js'

/**
 * @param {{ name: string, avatar?: string }} props
 */
export default function GroupMemberAvatar({ name, avatar }) {
  const src = resolveAvatarSrc(avatar)
  if (src) {
    return <img className="groupMemberAvatar__img" src={src} alt="" />
  }
  const initial = (name && name[0]) || '?'
  return (
    <div className="groupMemberAvatar__ph" aria-hidden>
      {initial}
    </div>
  )
}
