/**
 * @param {{ count: number }} props
 */
export default function SelectedFriendBar({ count }) {
  return (
    <div className="groupSelectedBar">
      已选择 <strong>{count}</strong> 位好友（不含自己）；创建群聊至少需 <strong>2</strong> 人。
    </div>
  )
}
