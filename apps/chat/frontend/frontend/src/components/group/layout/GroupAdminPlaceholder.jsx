/**
 * 群管理操作区占位：队友接入后替换为实际管理组件树。
 */
export default function GroupAdminPlaceholder() {
  return (
    <div id="group-admin-action-slot" className="groupAdminSlot">
      <div className="groupAdminSlot__inner">
        <span className="groupAdminSlot__title">管理操作区</span>
        <p className="groupAdminSlot__hint">群主/管理员相关操作由队友在此接入（发布公告、移除成员、邀请审核等）。</p>
      </div>
    </div>
  )
}
