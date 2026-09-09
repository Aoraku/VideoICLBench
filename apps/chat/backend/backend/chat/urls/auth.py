# chat/urls/auth.py
from django.urls import path
from chat.views.auth import (
    RegisterView,
    LoginView,
    RefreshTokenView,
    LogoutView,
    DeleteAccountView,
)

urlpatterns = [
    path('register', RegisterView.as_view()),              # 1.1 POST
    path('login', LoginView.as_view()),                    # 1.2 POST
    path('refresh', RefreshTokenView.as_view()),            # 1.3 POST
    path('logout', LogoutView.as_view()),                  # 1.4 POST
    path('account', DeleteAccountView.as_view()),          # 1.5 DELETE
]
