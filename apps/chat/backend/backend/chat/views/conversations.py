"""
chat/views/conversations.py
会话模块：会话列表、创建、详情、设置、已读标记、搜索

对应接口：4.1 - 4.7
负责人：同学 B
"""

import re

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from chat.models import Conversation, ConversationMember, Friendship, Message, User
from chat.realtime import send_to_conversation


def _err(code, message):
    return {'error': {'code': code, 'message': message}}


def _parse_pagination(request, default_size=20):
    '''
    处理分页参数，返回 (page, page_size)，并进行基本的验证和限制
    '''
    try:
        page = int(request.query_params.get('page', 1))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(request.query_params.get('page_size', default_size))
    except (TypeError, ValueError):
        page_size = default_size

    page = max(1, page)
    page_size = min(100, max(1, page_size))
    return page, page_size


def _build_last_message_data(message):
    if not message:
        return None
    
    # m: is_recalled 最好前端也处理一下
    if getattr(message, 'is_recalled', False):
        display_content = {"text": "消息已撤回"}
        msg_type = 'text'
    else:
        display_content = message.content
        msg_type = message.type

    sender_name = message.sender.username if message.sender else '[已注销用户]'
    
    return {
        'msg_id': message.id,
        'sender_id': message.sender_id,
        'sender_name': sender_name,
        'type': msg_type,
        'content': display_content,
        'created_at': message.created_at.isoformat(),
    }


def _build_peer_user_payload(peer, remark=''):
    return {
        'user_id': peer.id,
        'username': peer.username,
        'remark': remark or '',
        'avatar': peer.avatar or None,
        'status': {
            'presence': peer.presence,
            'status_text': peer.status_text,
            'status_emoji': peer.status_emoji,
        },
    }


def _build_peer_user_data(me, conversation):
    if conversation.type != 'private':
        return None

    peer_member = ConversationMember.objects.filter(
        conversation=conversation
    ).exclude(user=me).select_related('user').first()
    if not peer_member:
        return None

    fs = Friendship.objects.filter(user=me, friend=peer_member.user).first()
    return _build_peer_user_payload(peer_member.user, fs.remark if fs else '')


def _calculate_unread_count(conversation, user, read_index):
    return Message.objects.filter(
        conversation=conversation,
        id__gt=read_index,
    ).exclude(sender_id=user.id).count()


def _get_conversation_and_member(user, conv_id):
    conv = Conversation.objects.filter(pk=conv_id).first()
    if not conv:
        return None, None, Response(
            _err('CONVERSATION_NOT_FOUND', '会话不存在'), status=404
        )

    member = ConversationMember.objects.filter(
        user=user,
        conversation=conv,
        is_deleted=False,
        is_removed=False,
    ).first()
    if not member:
        return conv, None, Response(
            _err('NOT_MEMBER', '不是会话成员'), status=403
        )

    return conv, member, None


class ConversationListView(APIView):
    """
    4.1 获取会话列表 — GET /api/conversations
    4.2 创建会话     — POST /api/conversations
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        page, page_size = _parse_pagination(request, default_size=30)

        qs = ConversationMember.objects.filter(
            user=request.user,
            is_deleted=False,
            is_removed=False,
        ).select_related('conversation').order_by('-is_pinned', '-conversation__updated_at')
        # 取出当前用户未删除的聊天list，置顶会话排在最前（置顶内部按 `updated_at` 降序），其余按 `updated_at` 降序
        # select_related将conversation一起抓取

        total = qs.count()
        offset = (page - 1) * page_size
        memberships = qs[offset:offset + page_size]

        results = []
        for membership in memberships:
            conv = membership.conversation
            last_msg = Message.objects.filter(conversation=conv).select_related('sender').order_by('-id').first()
            unread_count = _calculate_unread_count(conv, request.user, membership.read_index)

            results.append({
                'conversation_id': conv.id,
                'type': conv.type,
                'name': conv.name or None,
                'avatar': conv.avatar or None,
                'peer_user': _build_peer_user_data(request.user, conv),
                'last_message': _build_last_message_data(last_msg),
                'unread_count': unread_count,
                'is_pinned': membership.is_pinned,
                'is_muted': membership.is_muted,
                'updated_at': conv.updated_at.isoformat(),
            })

        return Response({
            'total': total,
            'page': page,
            'page_size': page_size,
            'results': results,
        })

    def post(self, request):
        conv_type = request.data.get('type')
        if conv_type not in ('private', 'group'):
            return Response(_err('INVALID_PARAMS', 'type 须为 private 或 group'), status=400)

        if conv_type == 'private':
            peer_user_id = request.data.get('peer_user_id')
            if not peer_user_id:
                return Response(_err('INVALID_PARAMS', '缺少 peer_user_id'), status=400)
            try:
                peer_user_id = int(peer_user_id)
            except (TypeError, ValueError):
                return Response(_err('INVALID_PARAMS', 'peer_user_id 必须为整数'), status=400)

            if peer_user_id == request.user.id:
                return Response(_err('INVALID_PARAMS', '不能和自己创建私聊'), status=400)

            peer = User.objects.filter(pk=peer_user_id, is_active=True).first()
            if not peer:
                return Response(_err('USER_NOT_FOUND', '用户不存在'), status=404)

            is_friend = Friendship.objects.filter(user=request.user, friend=peer).exists()
            if not is_friend:
                return Response(_err('NOT_FRIEND', '仅可与好友创建私聊'), status=403)

            existing_member = ConversationMember.objects.filter(
                user=request.user,
                conversation__type='private',
            ).filter(conversation__members__user=peer).select_related('conversation').first()

            if existing_member:
                return Response({
                    'error': {
                        'code': 'CONVERSATION_EXISTS',
                        'message': '私聊已存在',
                    },
                    'conversation_id': existing_member.conversation_id,
                }, status=409)

            with transaction.atomic():
                conv = Conversation.objects.create(type='private', name='')
                ConversationMember.objects.create(conversation=conv, user=request.user, role='member')
                ConversationMember.objects.create(conversation=conv, user=peer, role='member')

            return Response({
                'conversation_id': conv.id,
                'type': conv.type,
                'name': None,
                'created_at': conv.created_at.isoformat(),
                'members': [
                    {'user_id': request.user.id, 'username': request.user.username, 'role': 'member'},
                    {'user_id': peer.id, 'username': peer.username, 'role': 'member'},
                ],
            }, status=201)

        name = (request.data.get('name') or '').strip()
        member_ids = request.data.get('member_ids') or []
        if not name:
            return Response(_err('INVALID_PARAMS', '群聊缺少 name'), status=400)
        if not isinstance(member_ids, list) or not member_ids:
            return Response(_err('INVALID_PARAMS', 'member_ids 不能为空'), status=400)

        unique_member_ids = []
        seen = set()
        for user_id in member_ids:
            try:
                uid = int(user_id)
            except (TypeError, ValueError):
                return Response(_err('INVALID_PARAMS', 'member_ids 包含无效用户 ID'), status=400)
            if uid == request.user.id or uid in seen:
                continue
            seen.add(uid)
            unique_member_ids.append(uid)

        if not unique_member_ids:
            return Response(_err('INVALID_PARAMS', 'member_ids 不能为空'), status=400)

        users = list(User.objects.filter(id__in=unique_member_ids, is_active=True))
        if len(users) != len(unique_member_ids):
            return Response(_err('USER_NOT_FOUND', '存在不存在的用户'), status=404)

        friend_count = Friendship.objects.filter(
            user=request.user,
            friend_id__in=unique_member_ids,
        ).count()
        if friend_count != len(unique_member_ids):
            return Response(_err('NOT_FRIEND', '仅可邀请好友创建群聊'), status=403)

        with transaction.atomic():
            conv = Conversation.objects.create(
                type='group',
                name=name,
                owner=request.user,
            )
            ConversationMember.objects.create(
                conversation=conv,
                user=request.user,
                role='owner',
            )
            members_to_create = [
                ConversationMember(conversation=conv, user=u, role='member')
                for u in users
            ]
            ConversationMember.objects.bulk_create(members_to_create)

            Message.objects.create(
                conversation=conv,
                sender=request.user,
                type='system',
                content={
                    'action': 'group_created',
                    'text': f'{request.user.username} 创建了群聊',
                },
            )

        response_members = [
            {'user_id': request.user.id, 'username': request.user.username, 'role': 'owner'}
        ] + [
            {'user_id': u.id, 'username': u.username, 'role': 'member'}
            for u in users
        ]

        return Response({
            'conversation_id': conv.id,
            'type': conv.type,
            'name': conv.name,
            'created_at': conv.created_at.isoformat(),
            'members': response_members,
        }, status=201)


class ConversationDetailView(APIView):
    """
    4.3 获取会话详情 — GET /api/conversations/{conv_id}
    4.4 更新会话设置 — PUT /api/conversations/{conv_id}（置顶/免打扰）
    4.5 删除会话     — DELETE /api/conversations/{conv_id}
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, conv_id):
        conv, member, error_response = _get_conversation_and_member(request.user, conv_id)
        if error_response:
            return error_response

        last_msg = Message.objects.filter(conversation=conv).select_related('sender').order_by('-id').first()
        unread_count = _calculate_unread_count(conv, request.user, member.read_index)
        members_qs = ConversationMember.objects.filter(
            conversation=conv,
            is_deleted=False,
            is_removed=False,
        ).select_related('user').order_by('joined_at')

        members = []
        for item in members_qs:
            members.append({
                'user_id': item.user_id,
                'username': item.user.username,
                'avatar': item.user.avatar or None,
                'role': item.role,
                'nickname': item.nickname or '',
            })

        return Response({
            'conversation_id': conv.id,
            'type': conv.type,
            'name': None if conv.type == 'private' else (conv.name or None),
            'avatar': conv.avatar or None,
            'peer_user': _build_peer_user_data(request.user, conv),
            'last_message': _build_last_message_data(last_msg),
            'is_pinned': member.is_pinned,
            'is_muted': member.is_muted,
            'unread_count': unread_count,
            'members': members,
            'created_at': conv.created_at.isoformat(),
            'updated_at': conv.updated_at.isoformat(),
        })

    def put(self, request, conv_id):
        _, member, error_response = _get_conversation_and_member(request.user, conv_id)
        if error_response:
            return error_response

        update_fields = []
        if 'is_pinned' in request.data:
            if not isinstance(request.data['is_pinned'], bool):
                return Response(_err('INVALID_PARAMS', 'is_pinned 须为布尔值'), status=400)
            member.is_pinned = request.data['is_pinned']
            update_fields.append('is_pinned')

        if 'is_muted' in request.data:
            if not isinstance(request.data['is_muted'], bool):
                return Response(_err('INVALID_PARAMS', 'is_muted 须为布尔值'), status=400)
            member.is_muted = request.data['is_muted']
            update_fields.append('is_muted')

        if not update_fields:
            return Response(_err('INVALID_PARAMS', '至少传入一个可更新字段'), status=400)

        member.save(update_fields=update_fields)
        return Response({
            'conversation_id': member.conversation_id,
            'is_pinned': member.is_pinned,
            'is_muted': member.is_muted,
            'updated_at': timezone.now().isoformat(),
        })

    def delete(self, request, conv_id):
        _, member, error_response = _get_conversation_and_member(request.user, conv_id)
        if error_response:
            return error_response

        member.is_deleted = True
        member.save(update_fields=['is_deleted'])
        return Response(status=204)


class ConversationReadView(APIView):
    """4.6 标记会话已读 — PUT /api/conversations/{conv_id}/read"""
    permission_classes = [IsAuthenticated]

    def put(self, request, conv_id):
        conv, member, error_response = _get_conversation_and_member(request.user, conv_id)
        if error_response:
            return error_response

        raw_last_read = request.data.get('last_read_msg_id')
        if raw_last_read is None:
            latest = Message.objects.filter(conversation=conv).order_by('-id').first()
            last_read_msg_id = latest.id if latest else 0
        else:
            try:
                last_read_msg_id = int(raw_last_read)
            except (TypeError, ValueError):
                return Response(_err('INVALID_PARAMS', 'last_read_msg_id 必须为整数'), status=400)
            if last_read_msg_id < 0:
                return Response(_err('INVALID_PARAMS', 'last_read_msg_id 不能为负数'), status=400)
            if last_read_msg_id > 0 and not Message.objects.filter(
                conversation=conv,
                id=last_read_msg_id,
            ).exists():
                return Response(_err('MESSAGE_NOT_FOUND', '消息不存在'), status=404)

        member.read_index = max(member.read_index, last_read_msg_id)
        member.read_at = timezone.now()
        member.save(update_fields=['read_index', 'read_at'])
        send_to_conversation(conv.id, 'read_receipt', {
            'conversation_id': conv.id,
            'user_id': request.user.id,
            'last_read_msg_id': member.read_index,
            'read_at': member.read_at.isoformat(),
        })
        return Response(status=204)


class ConversationSearchView(APIView):
    """4.7 搜索聊天记录 — GET /api/conversations/search【拓展功能】"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        keyword = (request.query_params.get('keyword') or '').strip()
        if not keyword:
            return Response(_err('INVALID_PARAMS', '缺少 keyword'), status=400)

        conversation_id = request.query_params.get('conversation_id')
        page, page_size = _parse_pagination(request)

        member_qs = ConversationMember.objects.filter(
            user=request.user,
            is_deleted=False,
            is_removed=False,
        )
        allowed_conv_ids = list(member_qs.values_list('conversation_id', flat=True))

        if conversation_id is not None:
            try:
                conversation_id = int(conversation_id)
            except (TypeError, ValueError):
                return Response(_err('INVALID_PARAMS', 'conversation_id 必须为整数'), status=400)

            if conversation_id not in allowed_conv_ids:
                conv_exists = Conversation.objects.filter(pk=conversation_id).exists()
                if not conv_exists:
                    return Response(_err('CONVERSATION_NOT_FOUND', '会话不存在'), status=404)
                return Response(_err('NOT_MEMBER', '不是会话成员'), status=403)
            allowed_conv_ids = [conversation_id]

        qs = Message.objects.filter(
            conversation_id__in=allowed_conv_ids,
            is_recalled=False,
            type__in=['text', 'code'],
        ).select_related('sender', 'conversation').filter(
            Q(type='text', content__text__icontains=keyword) |
            Q(type='code', content__code__icontains=keyword)
        ).order_by('-created_at')

        total = qs.count()
        offset = (page - 1) * page_size
        messages = qs[offset:offset + page_size]

        regex = re.compile(re.escape(keyword), flags=re.IGNORECASE)
        results = []
        for msg in messages:
            if msg.type == 'text':
                source_text = str(msg.content.get('text', ''))
            else:
                source_text = str(msg.content.get('code', ''))
            highlight = regex.sub(lambda m: f'<em>{m.group(0)}</em>', source_text)

            results.append({
                'msg_id': msg.id,
                'conversation_id': msg.conversation_id,
                'conversation_name': msg.conversation.name or None,
                'conversation_type': msg.conversation.type,
                'sender': {
                    'user_id': msg.sender_id,
                    'username': msg.sender.username if msg.sender else '[已注销用户]',
                },
                'type': msg.type,
                'content': msg.content,
                'created_at': msg.created_at.isoformat(),
                'highlight': highlight,
            })

        return Response({
            'total': total,
            'page': page,
            'page_size': page_size,
            'results': results,
        })
