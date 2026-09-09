from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from chat.models import User


class SimpleBearerAuthentication(BaseAuthentication):
    """
    轻量 Bearer 认证（用于课程项目联调）：
    token 格式: access-<user_id>-<random>
    """

    def authenticate(self, request):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        token = auth.split(" ", 1)[1].strip()
        # 仅处理课程联调格式 access-<user_id>-<random>；其余交给 JWT 等认证类
        if not token.startswith("access-"):
            return None

        parts = token.split("-")
        if len(parts) < 3:
            return None

        try:
            user_id = int(parts[1])
        except ValueError:
            return None

        user = User.objects.filter(id=user_id).first()
        if not user:
            raise AuthenticationFailed("User not found")

        return (user, token)

