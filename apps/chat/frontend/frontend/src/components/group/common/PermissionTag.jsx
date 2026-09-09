/**
 * @param {{ role: 'owner'|'admin'|'member' }} props
 */
export default function PermissionTag({ role }) {
  const label = role === 'owner' ? '群主' : role === 'admin' ? '管理员' : '成员'
  const cls =
    role === 'owner' ? 'groupPermTag groupPermTag--owner' : role === 'admin' ? 'groupPermTag groupPermTag--admin' : 'groupPermTag groupPermTag--member'
  return (
    <span className={cls} title={label}>
      {label}
    </span>
  )
}
