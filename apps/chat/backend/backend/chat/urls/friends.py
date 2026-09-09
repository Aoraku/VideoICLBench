# chat/urls/friends.py
from django.urls import path
from chat.views.friends import (
    FriendRequestSendView,
    FriendRequestListView,
    FriendRequestHandleView,
    FriendListView,
    FriendDeleteView,
    FriendGroupListView,
    FriendGroupDetailView,
    FriendRemarkView,
    BlacklistView,
    BlacklistRemoveView,
    WhitelistView,
    WhitelistRemoveView,
)

urlpatterns = [
    # 好友列表
    path('', FriendListView.as_view()),                                    # 3.4 GET

    # 好友申请
    path('request', FriendRequestSendView.as_view()),                      # 3.1 POST
    path('requests', FriendRequestListView.as_view()),                     # 3.2 GET
    path('requests/<int:request_id>', FriendRequestHandleView.as_view()),  # 3.3 PUT

    # 好友删除与备注
    path('<int:friend_user_id>', FriendDeleteView.as_view()),              # 3.5 DELETE
    path('<int:friend_user_id>/remark', FriendRemarkView.as_view()),       # 3.10 PUT

    # 好友分组
    path('groups', FriendGroupListView.as_view()),                         # 3.6 GET, 3.7 POST
    path('groups/<int:group_id>', FriendGroupDetailView.as_view()),        # 3.8 PUT, 3.9 DELETE

    # 黑名单
    path('blacklist', BlacklistView.as_view()),                            # 3.11 POST, 3.13 GET
    path('blacklist/<int:user_id>', BlacklistRemoveView.as_view()),        # 3.12 DELETE

    # 白名单
    path('whitelist', WhitelistView.as_view()),                            # 3.14 POST, 3.16 GET
    path('whitelist/<int:user_id>', WhitelistRemoveView.as_view()),        # 3.15 DELETE
]
