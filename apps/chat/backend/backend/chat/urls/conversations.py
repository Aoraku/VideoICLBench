# chat/urls/conversations.py
from django.urls import path
from chat.views.conversations import (
    ConversationListView,
    ConversationDetailView,
    ConversationReadView,
    ConversationSearchView,
)
from chat.views.messages import (
    MessageListView,
    MessageReplyListView,
    MessageReadStatusView,
    MessageDeleteView,
    MessageRecallView,
    ReactionView,
    ReactionRemoveView,
)
from chat.views.groups import (
    GroupInfoView,
    GroupAvatarView,
    GroupMemberListView,
    GroupNicknameView,
    GroupAdminView,
    GroupAdminRemoveView,
    GroupOwnerTransferView,
    GroupMemberRemoveView,
    GroupLeaveView,
    GroupInvitationListView,
    GroupInvitationHandleView,
    GroupAnnouncementListView,
)

urlpatterns = [
    # ---- 会话级别 ----
    path('', ConversationListView.as_view()),                          # 4.1 GET, 4.2 POST
    path('search', ConversationSearchView.as_view()),                  # 4.7 GET 【拓展】
    path('<int:conv_id>', ConversationDetailView.as_view()),           # 4.3 GET, 4.4 PUT, 4.5 DELETE
    path('<int:conv_id>/read', ConversationReadView.as_view()),        # 4.6 PUT

    # ---- 消息级别 ----
    path('<int:conv_id>/messages', MessageListView.as_view()),                              # 5.1 POST, 5.2 GET
    path('<int:conv_id>/messages/<int:msg_id>', MessageDeleteView.as_view()),                # 5.5 DELETE
    path('<int:conv_id>/messages/<int:msg_id>/replies', MessageReplyListView.as_view()),     # 5.3 GET
    path('<int:conv_id>/messages/<int:msg_id>/read-status', MessageReadStatusView.as_view()), # 5.4 GET
    path('<int:conv_id>/messages/<int:msg_id>/recall', MessageRecallView.as_view()),          # 5.6 POST 【拓展】
    path('<int:conv_id>/messages/<int:msg_id>/reactions', ReactionView.as_view()),             # 5.8a POST 【拓展】
    path('<int:conv_id>/messages/<int:msg_id>/reactions/<str:emoji>', ReactionRemoveView.as_view()), # 5.8b DELETE

    # ---- 群聊管理 ----
    path('<int:conv_id>/group', GroupInfoView.as_view()),                                     # 6.1 GET, 6.2 PUT, 6.16 DELETE
    path('<int:conv_id>/group/avatar', GroupAvatarView.as_view()),                            # 6.3 POST
    path('<int:conv_id>/group/members', GroupMemberListView.as_view()),                       # 6.4 GET
    path('<int:conv_id>/group/members/<int:user_id>', GroupMemberRemoveView.as_view()),       # 6.9 DELETE
    path('<int:conv_id>/group/my-nickname', GroupNicknameView.as_view()),                     # 6.5 PUT
    path('<int:conv_id>/group/admins', GroupAdminView.as_view()),                             # 6.6 POST
    path('<int:conv_id>/group/admins/<int:user_id>', GroupAdminRemoveView.as_view()),         # 6.7 DELETE
    path('<int:conv_id>/group/owner', GroupOwnerTransferView.as_view()),                      # 6.8 PUT
    path('<int:conv_id>/group/leave', GroupLeaveView.as_view()),                              # 6.10 POST
    path('<int:conv_id>/group/invitations', GroupInvitationListView.as_view()),                # 6.11 POST, 6.12 GET
    path('<int:conv_id>/group/invitations/<int:invitation_id>', GroupInvitationHandleView.as_view()), # 6.13 PUT
    path('<int:conv_id>/group/announcements', GroupAnnouncementListView.as_view()),            # 6.14 POST, 6.15 GET
]
