from django.urls import path

from . import views
from . import conversations_views
from . import friends_views
from . import messages_views
from . import sync_views

urlpatterns = [
    path("auth/register/code", views.send_register_code),
    path("auth/register", views.register),
    path("auth/login", views.login),
    path("auth/logout", views.logout),
    path("auth/delete", views.delete_account),
    path("user/profile", views.profile),
    path("user/search", views.search_users),
    path("user/<int:user_id>", views.user_detail),
    
    path("friends", friends_views.friends_view),
    path("friends/groups", friends_views.manage_groups),
    path("friends/request", friends_views.manage_requests),
    path("friends/<int:friend_id>", friends_views.delete_friend),

    path("conversations", conversations_views.conversations),
    path("conversations/<int:conversation_id>/settings", conversations_views.conversation_settings),
    path("conversations/<int:conversation_id>/group", conversations_views.group_info),
    path("conversations/<int:conversation_id>/group/admin", conversations_views.group_admin),
    path("conversations/<int:conversation_id>/group/members", conversations_views.group_members),
    path("conversations/<int:conversation_id>/group/invite", conversations_views.group_invite),
    path("conversations/<int:conversation_id>/group/leave", conversations_views.group_leave),
    path("conversations/<int:conversation_id>/group/announcement", conversations_views.group_announcement),
    
    path("conversations/<int:conversation_id>/messages", messages_views.messages_view),
    path("conversations/<int:conversation_id>/messages/<int:msg_id>", messages_views.message_detail),
    path("conversations/<int:conversation_id>/read", messages_views.read_messages),
    path("sync", sync_views.sync_messages),
]
