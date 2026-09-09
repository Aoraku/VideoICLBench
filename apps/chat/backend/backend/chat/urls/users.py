# chat/urls/users.py
from django.urls import path
from chat.views.users import (
    CurrentUserView,
    UserAIKeyView,
    AvatarUploadView,
    UserSearchView,
    UserDetailView,
    PrivacySettingsView,
    UserStatusView,
)

urlpatterns = [
    path('me', CurrentUserView.as_view()),               # 2.1 GET, 2.2 PUT
    path('me/ai-key', UserAIKeyView.as_view()),          # 用户个人 AI API Key 设置
    path('me/avatar', AvatarUploadView.as_view()),       # 2.3 POST
    path('me/privacy', PrivacySettingsView.as_view()),   # 2.6 PUT, 2.7 GET
    path('me/status', UserStatusView.as_view()),         # 2.8 PUT
    path('search', UserSearchView.as_view()),            # 2.4 GET
    path('<int:user_id>', UserDetailView.as_view()),     # 2.5 GET
]
