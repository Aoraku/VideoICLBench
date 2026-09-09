"""
ASGI config for Backend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/asgi/
"""

import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Backend.settings')

from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()
from accounts.ws import chat_ws_app


async def application(scope, receive, send):
    if scope["type"] == "websocket" and scope.get("path", "") == "/ws/":
        await chat_ws_app(scope, receive, send)
        return
    await django_asgi_app(scope, receive, send)
