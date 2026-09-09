import GroupRoleManager from '../admin/GroupRoleManager.jsx'
import LeaveGroupButton from '../actions/LeaveGroupButton.jsx'
import PublishAnnouncementDialog from '../actions/PublishAnnouncementDialog.jsx'
import RemoveMemberDialog from '../actions/RemoveMemberDialog.jsx'
import InviteMemberDialog from '../invite/InviteMemberDialog.jsx'
import InviteReviewPanel from '../invite/InviteReviewPanel.jsx'

/**
 * @param {{
 *   groupId: string,
 *   currentUserRole: import('../../../types/group.js').GroupRole | null,
 *   members: import('../../../types/group.js').GroupMember[],
 *   isGroupMember?: boolean,
 *   onChanged?: () => Promise<void> | void,
 * }} props
 */
export default function GroupAdminActionArea({ groupId, currentUserRole, members, isGroupMember = false, onChanged }) {
  return (
    <div id="group-admin-action-slot" className="groupAdminActionArea">
      <GroupRoleManager groupId={groupId} currentUserRole={currentUserRole} members={members} onChanged={onChanged} />
      <PublishAnnouncementDialog groupId={groupId} currentUserRole={currentUserRole} onChanged={onChanged} />
      <RemoveMemberDialog groupId={groupId} currentUserRole={currentUserRole} members={members} onChanged={onChanged} />
      <InviteMemberDialog
        groupId={groupId}
        currentUserRole={currentUserRole}
        members={members}
        isGroupMember={isGroupMember}
      />
      <InviteReviewPanel groupId={groupId} currentUserRole={currentUserRole} onChanged={onChanged} />
      <LeaveGroupButton groupId={groupId} currentUserRole={currentUserRole} />
    </div>
  )
}
