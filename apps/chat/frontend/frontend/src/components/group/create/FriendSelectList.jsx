import { resolveAvatarSrc } from '../../../utils/avatarUrl.js'
import { getFriendDisplayName } from '../../../utils/friends.js'

/**
 * @param {{
 *   friends: Array<Record<string, unknown>>,
 *   selectedIds: Set<string>,
 *   onToggle: (userId: string) => void,
 * }} props
 */
export default function FriendSelectList({ friends, selectedIds, onToggle }) {
  return (
    <ul className="groupFriendPick__list">
      {friends.map((f) => {
        const id = String(f.user_id ?? '')
        const checked = selectedIds.has(id)
        const name = getFriendDisplayName(f)
        const src = resolveAvatarSrc(f.avatar)
        return (
          <li key={id || `row-${name}`} className="groupFriendPick__row">
            <label className="groupFriendPick__label">
              <input type="checkbox" checked={checked} onChange={() => onToggle(id)} disabled={!id} />
              <span
                className="groupFriendPick__avatar"
                style={src ? { backgroundImage: `url(${src})`, backgroundSize: 'cover' } : undefined}
              >
                {!src ? (
                  <svg viewBox="0 0 24 24" className="wxAvatarDefaultIcon" aria-hidden>
                    <circle cx="12" cy="8" r="4" />
                    <path d="M4 20c0-4 3.6-6 8-6s8 2 8 6" />
                  </svg>
                ) : null}
              </span>
              <span className="groupFriendPick__name">{name}</span>
            </label>
          </li>
        )
      })}
    </ul>
  )
}
