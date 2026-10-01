import GroupMemberAvatar from '../common/GroupMemberAvatar.jsx'
import {Link} from 'react-router-dom'
import PermissionTag from '../common/PermissionTag.jsx'

/**
 * @param {{ members: import('../../../types/group.js').GroupMember[] }} props
 */
export default function GroupMemberList({ members }) {
  return (
    <section className="groupCard groupMemberList">
      <h2 className="groupCard__title">群成员</h2>
      {members.length === 0 ? (
        <p className="groupMuted">暂无成员数据</p>
      ) : (
        <ul className="groupMemberList__ul">
          {members.map((m) => (
            <li key={m.id} className="groupMemberList__row">
              <GroupMemberAvatar name={m.name} avatar={m.avatar} />
              <div className="groupMemberList__main">
                <Link className="groupMemberList__name" to={`/user/${m.id}`}>{m.name}</Link>
                {m.username ? <div className="groupMemberList__sub">@{m.username}</div> : null}
              </div>
              <PermissionTag role={m.role} />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
