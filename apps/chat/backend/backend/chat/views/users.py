"""
chat/views/users.py
用户信息模块：个人信息、隐私设置、自定义状态、搜索用户

对应接口：2.1 - 2.8
负责人：同学 A
"""

import os

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone
from django.conf import settings as django_settings

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser
from rest_framework import status

from chat.models import User, UserPrivacy, Blacklist, Friendship
from chat.realtime import send_to_user


def _err(code, message):
    return {'error': {'code': code, 'message': message}}


def _push_presence(user):
    event = {
        'user_id': user.id,
        'presence': user.presence,
        'status_text': user.status_text or '',
        'status_emoji': user.status_emoji or '',
        'last_seen': user.last_seen.isoformat() if user.last_seen else None,
    }
    for friend_id in Friendship.objects.filter(user=user).values_list('friend_id', flat=True):
        send_to_user(friend_id, 'presence_change', event)


def _is_valid_username(username):
    if not (3 <= len(username) <= 20):
        return False
    return all(ch.isalnum() or ch == '_' for ch in username)


def _is_valid_cn_phone(phone):
    if len(phone) != 11 or not phone.isdigit():
        return False
    return phone[0] == '1' and phone[1] in '3456789'


def _is_valid_email(email):
    try:
        validate_email(email)
        return True
    except ValidationError:
        return False


def _has_password_complexity(password):
    has_upper = any(ch.isupper() for ch in password)
    has_lower = any(ch.islower() for ch in password)
    has_digit = any(ch.isdigit() for ch in password)
    return sum([has_upper, has_lower, has_digit]) >= 2


def _user_data(user):
    privacy, _ = UserPrivacy.objects.get_or_create(user=user)
    return {
        'user_id': user.id,
        'username': user.username,
        'email': user.email,
        'phone': user.phone,
        'avatar': user.avatar or None,
        'status': {
            'presence': user.presence,
            'status_text': user.status_text or '',
            'status_emoji': user.status_emoji or '',
        },
        'privacy': {
            'allow_search_by_username': privacy.allow_search_by_username,
            'allow_search_by_email': privacy.allow_search_by_email,
            'allow_search_by_phone': privacy.allow_search_by_phone,
            'allow_add_from_group': privacy.allow_add_from_group,
        },
        'ai_api_key_configured': bool((user.ai_api_key or '').strip()),
        'created_at': user.date_joined.isoformat(),
    }


def _mask_ai_key(api_key):
    api_key = str(api_key or '').strip()
    if not api_key:
        return ''
    if len(api_key) <= 10:
        return f'{api_key[:2]}***{api_key[-2:]}'
    return f'{api_key[:5]}...{api_key[-4:]}'


class CurrentUserView(APIView):
    """
    2.1 获取当前用户信息 — GET /api/users/me
    2.2 修改个人信息    — PUT /api/users/me
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(_user_data(request.user))

    def put(self, request):
        user = request.user
        data = request.data
        update_fields = []

        # 修改用户名（无需额外验证）
        if 'username' in data:
            if not isinstance(data['username'], str):
                return Response(_err('INVALID_PARAMS', 'username 须为字符串'), status=400)
            username = data['username'].strip()
            if not _is_valid_username(username):
                return Response(_err('INVALID_PARAMS', '用户名须为 3-20 位字母、数字或下划线'), status=400)
            if User.objects.exclude(pk=user.pk).filter(username=username).exists():
                return Response(_err('USERNAME_EXISTS', '用户名已被占用'), status=409)
            user.username = username
            update_fields.append('username')

        # 解析敏感字段（手机、邮箱、密码），判断是否有实质性变更
        if 'phone' in data and not isinstance(data['phone'], str):
            return Response(_err('INVALID_PARAMS', 'phone 须为字符串'), status=400)
        if 'email' in data and not isinstance(data['email'], str):
            return Response(_err('INVALID_PARAMS', 'email 须为字符串'), status=400)

        new_phone = data['phone'].strip() if 'phone' in data else None
        new_email = data['email'].strip() if 'email' in data else None
        new_password = None
        if 'new_password' in data or 'password' in data:
            raw_password = data.get('new_password') if 'new_password' in data else data.get('password')
            if raw_password in (None, ''):
                new_password = ''
            elif not isinstance(raw_password, str):
                return Response(_err('INVALID_PARAMS', 'password 须为字符串'), status=400)
            else:
                new_password = raw_password

        phone_changing    = new_phone    is not None and new_phone    != (user.phone or '')
        email_changing    = new_email    is not None and new_email    != (user.email or '')
        password_changing = new_password is not None and new_password != ''

        # 格式校验（优先于鉴权，尽早返回错误）
        if phone_changing and new_phone and not _is_valid_cn_phone(new_phone):
            return Response(_err('INVALID_PARAMS', '手机号格式不合法'), status=400)
        if email_changing and new_email and not _is_valid_email(new_email):
            return Response(_err('INVALID_PARAMS', '邮箱格式不合法'), status=400)
        if password_changing:
            if not (8 <= len(new_password) <= 32):
                return Response(_err('INVALID_PARAMS', '密码须为 8-32 位'), status=400)
            if not _has_password_complexity(new_password):
                return Response(_err('INVALID_PARAMS', '密码须包含大写字母、小写字母、数字中至少两种'), status=400)

        if phone_changing and new_phone and User.objects.exclude(pk=user.pk).filter(phone=new_phone).exists():
            return Response(_err('PHONE_EXISTS', '手机号已被占用'), status=409)
        if email_changing and new_email and User.objects.exclude(pk=user.pk).filter(email=new_email).exists():
            return Response(_err('EMAIL_EXISTS', '邮箱已被占用'), status=409)

        # 修改邮箱、手机号或密码时，只验证当前密码。
        if phone_changing or email_changing or password_changing:
            old_password = data.get('old_password', '')
            if 'old_password' in data and not isinstance(old_password, str):
                return Response(_err('INVALID_PARAMS', 'old_password 须为字符串'), status=400)
            if not old_password:
                return Response(_err('OLD_PASSWORD_REQUIRED', '修改敏感信息须提供当前密码'), status=403)
            if not user.check_password(old_password):
                return Response(_err('WRONG_PASSWORD', '旧密码错误'), status=403)

        # 应用变更
        if phone_changing:
            user.phone = new_phone
            update_fields.append('phone')

        if email_changing:
            user.email = new_email
            update_fields.append('email')

        if password_changing:
            user.set_password(new_password)
            update_fields.append('password')

        if update_fields:
            user.save(update_fields=update_fields)
        return Response(_user_data(user))


class UserAIKeyView(APIView):
    """用户个人 AI API Key 设置 — GET/PUT/DELETE /api/users/me/ai-key"""
    permission_classes = [IsAuthenticated]

    def _payload(self, user):
        api_key = (user.ai_api_key or '').strip()
        return {
            'configured': bool(api_key),
            'masked_key': _mask_ai_key(api_key),
            'ai_base_url': django_settings.AI_BASE_URL,
            'ai_model': django_settings.AI_MODEL,
        }

    def get(self, request):
        return Response(self._payload(request.user))

    def put(self, request):
        api_key = request.data.get('api_key')
        if not isinstance(api_key, str):
            return Response(_err('INVALID_PARAMS', 'api_key 须为字符串'), status=400)
        api_key = api_key.strip()
        if not (8 <= len(api_key) <= 500):
            return Response(_err('INVALID_PARAMS', 'api_key 长度须为 8-500 位'), status=400)
        request.user.ai_api_key = api_key
        request.user.save(update_fields=['ai_api_key'])
        return Response(self._payload(request.user))

    def delete(self, request):
        request.user.ai_api_key = ''
        request.user.save(update_fields=['ai_api_key'])
        return Response(self._payload(request.user))


class AvatarUploadView(APIView):
    """2.3 上传头像 — POST /api/users/me/avatar"""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    ALLOWED_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
    MAX_SIZE = 5 * 1024 * 1024  # 5MB

    def post(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response(_err('INVALID_PARAMS', '缺少文件'), status=400)

        if file.content_type not in self.ALLOWED_TYPES:
            return Response(_err('INVALID_FILE_TYPE', '仅支持 jpg/png/gif/webp'), status=400)

        if file.size > self.MAX_SIZE:
            return Response(_err('FILE_TOO_LARGE', '文件不能超过 5MB'), status=400)

        ext = os.path.splitext(file.name)[1].lower() or '.jpg'
        filename = f'avatars/{request.user.id}{ext}'
        save_path = os.path.join(django_settings.MEDIA_ROOT, filename)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, 'wb') as f:
            for chunk in file.chunks():
                f.write(chunk)

        avatar_url = request.build_absolute_uri(django_settings.MEDIA_URL + filename)
        request.user.avatar = avatar_url
        request.user.save(update_fields=['avatar'])
        return Response({'avatar': avatar_url})


class UserSearchView(APIView):
    """2.4 搜索用户 — GET /api/users/search"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        keyword = request.query_params.get('keyword', '').strip()
        if not keyword:
            return Response(_err('INVALID_PARAMS', '缺少 keyword'), status=400)

        page = max(1, int(request.query_params.get('page', 1)))
        page_size = min(100, max(1, int(request.query_params.get('page_size', 20))))

        from django.db.models import Q
        from chat.models import UserPrivacy

        # 按隐私设置构建查询条件
        qs = User.objects.filter(is_active=True).exclude(pk=request.user.pk)

        # 用户名、邮箱、手机号均按用户隐私开关过滤。
        username_qs = qs.filter(
            username__icontains=keyword,
            privacy__allow_search_by_username=True,
        )

        # 邮箱搜索（受隐私设置限制）
        email_qs = qs.filter(
            email__icontains=keyword,
            privacy__allow_search_by_email=True,
        )

        # 手机号搜索（受隐私设置限制）
        phone_qs = qs.filter(
            phone__icontains=keyword,
            privacy__allow_search_by_phone=True,
        )

        combined = (username_qs | email_qs | phone_qs).distinct()
        total = combined.count()
        offset = (page - 1) * page_size
        results = combined[offset:offset + page_size]

        return Response({
            'total': total,
            'page': page,
            'page_size': page_size,
            'results': [
                {
                    'user_id': u.id,
                    'username': u.username,
                    'avatar': u.avatar or None,
                    'status': {
                        'presence': u.presence,
                        'status_text': u.status_text or '',
                        'status_emoji': u.status_emoji or '',
                    },
                }
                for u in results
            ],
        })


class UserDetailView(APIView):
    """2.5 获取指定用户公开信息 — GET /api/users/{user_id}"""
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        try:
            target = User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            return Response(_err('USER_NOT_FOUND', '用户不存在或已注销'), status=404)

        from chat.models import Friendship
        is_friend = Friendship.objects.filter(
            user=request.user, friend=target
        ).exists()
        is_blocked = Blacklist.objects.filter(
            user=request.user, blocked_user=target
        ).exists()
        friendship = Friendship.objects.filter(
            user=request.user, friend=target
        ).first()

        return Response({
            'user_id': target.id,
            'username': target.username,
            'avatar': target.avatar or None,
            'is_friend': is_friend,
            'is_blocked': is_blocked,
            'status': {
                'presence': target.presence,
                'status_text': target.status_text or '',
                'status_emoji': target.status_emoji or '',
            },
            'remark': friendship.remark if friendship else None,
            'created_at': target.date_joined.isoformat(),
        })


class PrivacySettingsView(APIView):
    """
    2.6 修改隐私设置 — PUT /api/users/me/privacy
    2.7 获取隐私设置 — GET /api/users/me/privacy
    """
    permission_classes = [IsAuthenticated]

    def _privacy_data(self, privacy):
        return {
            'allow_search_by_username': privacy.allow_search_by_username,
            'allow_search_by_email': privacy.allow_search_by_email,
            'allow_search_by_phone': privacy.allow_search_by_phone,
            'allow_add_from_group': privacy.allow_add_from_group,
            'updated_at': timezone.now().isoformat(),
        }

    def get(self, request):
        privacy, _ = UserPrivacy.objects.get_or_create(user=request.user)
        return Response(self._privacy_data(privacy))

    def put(self, request):
        privacy, _ = UserPrivacy.objects.get_or_create(user=request.user)
        fields = [
            'allow_search_by_username',
            'allow_search_by_email',
            'allow_search_by_phone',
            'allow_add_from_group',
        ]
        update_fields = []
        for field in fields:
            if field in request.data:
                val = request.data[field]
                if not isinstance(val, bool):
                    return Response(_err('INVALID_PARAMS', f'{field} 须为布尔值'), status=400)
                setattr(privacy, field, val)
                update_fields.append(field)
        if update_fields:
            privacy.save(update_fields=update_fields)
        return Response(self._privacy_data(privacy))


class UserStatusView(APIView):
    """2.8 设置自定义状态 — PUT /api/users/me/status"""
    permission_classes = [IsAuthenticated]

    VALID_PRESENCE = {'online', 'offline', 'busy', 'invisible'}

    def put(self, request):
        user = request.user
        update_fields = []

        if 'presence' in request.data:
            presence = request.data['presence']
            if not isinstance(presence, str) or presence not in self.VALID_PRESENCE:
                return Response(
                    _err('INVALID_PARAMS', f'presence 须为 {self.VALID_PRESENCE}'), status=400
                )
            user.presence = presence
            update_fields.append('presence')

        if 'status_text' in request.data:
            text = request.data['status_text']
            if not isinstance(text, str):
                return Response(_err('INVALID_PARAMS', 'status_text 须为字符串'), status=400)
            if len(text) > 100:
                return Response(_err('INVALID_PARAMS', 'status_text 不超过 100 字'), status=400)
            user.status_text = text
            update_fields.append('status_text')

        if 'status_emoji' in request.data:
            emoji = request.data['status_emoji']
            if not isinstance(emoji, str):
                return Response(_err('INVALID_PARAMS', 'status_emoji 须为字符串'), status=400)
            if len(emoji) > 10:
                return Response(_err('INVALID_PARAMS', 'status_emoji 过长'), status=400)
            user.status_emoji = emoji
            update_fields.append('status_emoji')

        if update_fields:
            user.save(update_fields=update_fields)
            _push_presence(user)

        return Response({
            'presence': user.presence,
            'status_text': user.status_text,
            'status_emoji': user.status_emoji,
            'updated_at': timezone.now().isoformat(),
        })
