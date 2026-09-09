# chat/urls/root.py
"""
chat app 的顶层路由汇总。
在项目的 backend_app/urls.py 中只需要一行：
    path('api/', include('chat.urls.root'))
"""

from django.urls import path, include
from chat.urls.extra import (
    message_patterns,
    bookmark_patterns,
    upload_patterns,
    manual_patterns,
    sync_patterns,
    ai_patterns,
    calendar_patterns,
)

urlpatterns = [
    # /api/auth/*
    path('auth/', include('chat.urls.auth')),

    # /api/users/*
    path('users/', include('chat.urls.users')),

    # /api/friends/*
    path('friends/', include('chat.urls.friends')),

    # /api/conversations/*  (含嵌套的 messages/* 和 group/*)
    path('conversations/', include('chat.urls.conversations')),

    # /api/messages/*  (转发等不属于特定会话的消息操作)
    *message_patterns,

    # /api/bookmarks/*
    *bookmark_patterns,

    # /api/upload
    *upload_patterns,

    # /api/manual
    *manual_patterns,

    # /api/sync/*
    *sync_patterns,

    # /api/ai/*
    *ai_patterns,

    # /api/calendar/*
    *calendar_patterns,
]
