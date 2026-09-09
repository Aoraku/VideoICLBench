# chat/urls/extra.py
# 不属于 /conversations 嵌套路径的独立接口
from django.urls import path
from chat.views.messages import (
    MessageForwardView,
    BookmarkListView,
    BookmarkReorderView,
    BookmarkDeleteView,
)
from chat.views.upload import FileUploadView
from chat.views.sync import SyncMessagesView
from chat.views.ai import AIConversationCreateView, AIMessageView
from chat.views.manual import ManualView
from chat.views.calendar import (
    CalendarAvailabilityView,
    CalendarEventDetailView,
    CalendarEventListView,
    CalendarInvitationHandleView,
)

# 转发消息 (5.7)
message_patterns = [
    path('messages/forward', MessageForwardView.as_view()),  # 5.7 POST 【拓展】
]

# 收藏 (5.9)
bookmark_patterns = [
    path('bookmarks', BookmarkListView.as_view()),                    # 5.9a POST, 5.9b GET
    path('bookmarks/reorder', BookmarkReorderView.as_view()),          # 5.9d POST 【拓展】
    path('bookmarks/<int:bookmark_id>', BookmarkDeleteView.as_view()), # 5.9c DELETE
]

# 文件上传 (7.1)
upload_patterns = [
    path('upload', FileUploadView.as_view()),  # 7.1 POST
]

manual_patterns = [
    path('manual', ManualView.as_view()),
]

# 消息同步 (8.1)
sync_patterns = [
    path('sync/messages', SyncMessagesView.as_view()),  # 8.1 GET
]

# AI 对话 (9.1 - 9.2) 【拓展】
ai_patterns = [
    path('ai/conversations', AIConversationCreateView.as_view()),                    # 9.1 POST
    path('ai/conversations/<int:conv_id>/messages', AIMessageView.as_view()),        # 9.2 POST
]

# 日程
calendar_patterns = [
    path('calendar/events', CalendarEventListView.as_view()),
    path('calendar/events/<int:event_id>', CalendarEventDetailView.as_view()),
    path('calendar/invitations/<int:participant_id>', CalendarInvitationHandleView.as_view()),
    path('calendar/availability', CalendarAvailabilityView.as_view()),
]
