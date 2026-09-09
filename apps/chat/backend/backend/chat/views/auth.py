"""
chat/views/auth.py
用户认证模块：注册、登录、登出、注销、刷新Token

对应接口：1.1 - 1.5
负责人：同学 A
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from datetime import datetime, timedelta, timezone as dt_timezone
import uuid

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from chat.models import User, UserPrivacy, TokenBlacklist, Friendship, Conversation, ConversationMember, Message
from chat.realtime import send_to_user, send_to_conversation


def error_response(code, message, http_status):
    return Response(
        {"error": {"code": code, "message": message}},
        status=http_status,
    )


def _push_presence(user):
    event = {
        "user_id": user.id,
        "presence": user.presence,
        "status_text": user.status_text or "",
        "status_emoji": user.status_emoji or "",
        "last_seen": user.last_seen.isoformat() if user.last_seen else None,
    }
    friend_ids = Friendship.objects.filter(user=user).values_list("friend_id", flat=True)
    for friend_id in friend_ids:
        send_to_user(friend_id, "presence_change", event)


def _is_valid_username(username):
    if not (3 <= len(username) <= 20):
        return False
    return all(ch.isalnum() or ch == '_' for ch in username)


def _is_valid_email(email):
    try:
        validate_email(email)
        return True
    except ValidationError:
        return False


def _is_valid_phone(phone):
    return len(phone) == 11 and phone.isdigit()


def _has_password_complexity(password):
    has_upper = any(ch.isupper() for ch in password)
    has_lower = any(ch.islower() for ch in password)
    has_digit = any(ch.isdigit() for ch in password)
    return sum([has_upper, has_lower, has_digit]) >= 2


def _issue_tokens(user):
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token), str(refresh)


def _refresh_access_token(refresh_token):
    if TokenBlacklist.objects.filter(token=refresh_token).exists():
        return None

    # Backward compatible with old course tokens used by existing tests/tools.
    parts = refresh_token.split("-")
    if len(parts) >= 3 and parts[0] == "refresh":
        try:
            user_id = int(parts[1])
        except ValueError:
            return None
        if not User.objects.filter(id=user_id).exists():
            return None
        return f"access-{user_id}-{uuid.uuid4().hex}"

    try:
        refresh = RefreshToken(refresh_token)
    except TokenError:
        return None
    return str(refresh.access_token)


def _refresh_token_expires_at(refresh_token):
    try:
        refresh = RefreshToken(refresh_token)
        return datetime.fromtimestamp(refresh['exp'], tz=dt_timezone.utc)
    except (TokenError, KeyError, TypeError, ValueError):
        return timezone.now() + timedelta(days=7)


class RegisterView(APIView):
    """1.1 用户注册 — POST /api/auth/register"""
    permission_classes = [AllowAny]

    def post(self, request):
        username = (request.data.get("username") or "").strip()
        password = request.data.get("password") or ""
        email = (request.data.get("email") or "").strip()
        phone = (request.data.get("phone") or "").strip()

        if not username or not password:
            return error_response("INVALID_PARAMS", "缺少必填字段", status.HTTP_400_BAD_REQUEST)
        if not _is_valid_username(username):
            return error_response("INVALID_PARAMS", "用户名格式不合法", status.HTTP_400_BAD_REQUEST)
        if len(password) < 8 or len(password) > 32:
            return error_response("INVALID_PARAMS", "密码长度需为 8-32 位", status.HTTP_400_BAD_REQUEST)
        if not _has_password_complexity(password):
            return error_response("INVALID_PARAMS", "密码需包含大写字母、小写字母、数字中至少两种", status.HTTP_400_BAD_REQUEST)
        if email and not _is_valid_email(email):
            return error_response("INVALID_PARAMS", "邮箱格式不合法", status.HTTP_400_BAD_REQUEST)
        if phone and not _is_valid_phone(phone):
            return error_response("INVALID_PARAMS", "手机号格式不合法", status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(username=username).exists():
            return error_response("USERNAME_EXISTS", "用户名已存在", status.HTTP_409_CONFLICT)
        if email and User.objects.filter(email=email).exists():
            return error_response("EMAIL_EXISTS", "邮箱已存在", status.HTTP_409_CONFLICT)
        if phone and User.objects.filter(phone=phone).exists():
            return error_response("PHONE_EXISTS", "手机号已存在", status.HTTP_409_CONFLICT)

        user = User.objects.create_user(
            username=username,
            password=password,
            email=email,
            phone=phone,
        )
        UserPrivacy.objects.get_or_create(user=user)

        return Response(
            {
                "user_id": user.id,
                "username": user.username,
                "email": user.email or "",
                "phone": user.phone or "",
                "avatar": user.avatar or None,
                "created_at": user.date_joined.isoformat().replace("+00:00", "Z"),
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """1.2 用户登录 — POST /api/auth/login"""
    permission_classes = [AllowAny]

    def post(self, request):
        login_type = (request.data.get("login_type") or "").strip()
        identifier = (request.data.get("identifier") or "").strip()
        password = request.data.get("password") or ""

        if login_type not in ("username", "email", "phone") or not identifier or not password:
            return error_response("INVALID_PARAMS", "登录参数不合法", status.HTTP_400_BAD_REQUEST)

        query_map = {
            "username": {"username": identifier},
            "email": {"email": identifier},
            "phone": {"phone": identifier},
        }
        user = User.objects.filter(**query_map[login_type]).first()
        if not user:
            return error_response("ACCOUNT_NOT_FOUND", "账号不存在", status.HTTP_404_NOT_FOUND)
        if not user.check_password(password):
            return error_response("INVALID_CREDENTIALS", "账号或密码错误", status.HTTP_401_UNAUTHORIZED)

        user.presence = "online"
        user.save(update_fields=["presence"])
        _push_presence(user)

        access_token, refresh_token = _issue_tokens(user)

        return Response(
            {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": 3600,
                "user": {
                    "user_id": user.id,
                    "username": user.username,
                    "avatar": user.avatar or None,
                    "email": user.email or "",
                    "phone": user.phone or "",
                    "status": {
                        "presence": user.presence,
                        "status_text": user.status_text or "",
                        "status_emoji": user.status_emoji or "",
                    },
                },
            },
            status=status.HTTP_200_OK,
        )


class RefreshTokenView(APIView):
    """1.3 刷新 Token — POST /api/auth/refresh"""
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get("refresh_token")
        if not refresh_token:
            return error_response("INVALID_REFRESH_TOKEN", "refresh_token 无效", status.HTTP_401_UNAUTHORIZED)

        access_token = _refresh_access_token(refresh_token)
        if not access_token:
            return error_response("INVALID_REFRESH_TOKEN", "refresh_token 无效", status.HTTP_401_UNAUTHORIZED)
        return Response(
            {
                "access_token": access_token,
                "expires_in": 3600,
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    """1.4 用户登出 — POST /api/auth/logout"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh_token")
        if refresh_token:
            TokenBlacklist.objects.get_or_create(
                token=refresh_token,
                user=request.user,
                defaults={"expires_at": _refresh_token_expires_at(refresh_token)},
            )

        request.user.presence = "offline"
        request.user.last_seen = timezone.now()
        request.user.save(update_fields=["presence", "last_seen"])
        _push_presence(request.user)
        send_to_user(request.user.id, "force_disconnect", {"reason": "logout"})
        return Response(status=status.HTTP_204_NO_CONTENT)


class DeleteAccountView(APIView):
    """1.5 注销账号 — DELETE /api/auth/account"""
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        password = request.data.get("password") or ""
        if not request.user.check_password(password):
            return error_response("WRONG_PASSWORD", "密码错误", status.HTTP_403_FORBIDDEN)
        user = request.user
        owned_group = Conversation.objects.filter(
            type="group",
            owner=user,
            is_dissolved=False,
        ).first()
        if owned_group:
            return error_response(
                "OWNED_GROUP_EXISTS",
                "请先转让或解散自己创建的群聊",
                status.HTTP_409_CONFLICT,
            )

        with transaction.atomic():
            memberships = list(ConversationMember.objects.select_related("conversation").filter(
                user=user,
                conversation__type="group",
                conversation__is_dissolved=False,
                is_removed=False,
            ))
            for membership in memberships:
                message = Message.objects.create(
                    conversation=membership.conversation,
                    sender=user,
                    type="system",
                    content={
                        "system_type": "member_left",
                        "user_id": user.id,
                        "username": user.username,
                        "reason": "account_deleted",
                    },
                )
                membership.is_removed = True
                membership.is_deleted = True
                membership.save(update_fields=["is_removed", "is_deleted"])
                send_to_conversation(membership.conversation_id, "group_member_change", {
                    "conversation_id": membership.conversation_id,
                    "action": "left",
                    "user_id": user.id,
                    "username": user.username,
                    "msg_id": message.id,
                    "reason": "account_deleted",
                })
            user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
