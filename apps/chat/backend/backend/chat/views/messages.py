"""
chat/views/messages.py
消息模块：发送、聊天记录、回复、已读、删除、撤回、转发、Reaction、收藏

对应接口：5.1 - 5.9
负责人：同学 B
"""

import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from chat.models import (
    Blacklist,
    Bookmark,
    Conversation,
    ConversationMember,
    Friendship,
    Message,
    MessageDeletion,
    Reaction,
    ReactionEvent,
    User,
)
from chat.realtime import send_to_conversation


def _err(code, message):
    return {'error': {'code': code, 'message': message}}


def _parse_pagination(request, default_size=20):
    """
    处理分页参数，返回 (page, page_size)，并进行基本的验证和限制
    """
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


def _conversation_display_name(conversation, user):
    if not conversation:
        return None
    if conversation.type == 'group':
        return f"{conversation.name or '群聊'} 群聊"
    if conversation.type == 'ai':
        return conversation.name or 'AI 助手'
    peer_member = ConversationMember.objects.filter(
        conversation=conversation,
        is_removed=False,
    ).exclude(user=user).select_related('user').first()
    if peer_member and peer_member.user:
        fs = Friendship.objects.filter(user=user, friend=peer_member.user).first()
        name = fs.remark if fs and fs.remark else peer_member.user.username
        return f"{name} 私聊"
    return conversation.name or '私聊'


def _bookmark_payload(bookmark, user=None):
    msg = bookmark.message
    message_payload = None
    if msg:
        message_payload = {
            'msg_id': msg.id,
            'sender_id': msg.sender_id,
            'sender_name': msg.sender.username if msg.sender else '[已注销用户]',
            'type': msg.type,
            'content': msg.content,
            'is_recalled': msg.is_recalled,
            'created_at': msg.created_at.isoformat(),
        }
    return {
        'bookmark_id': bookmark.id,
        'msg_id': bookmark.message_id,
        'conversation_id': bookmark.conversation_id,
        'conversation_name': _conversation_display_name(bookmark.conversation, user or bookmark.user),
        'title': bookmark.title,
        'note': bookmark.note,
        'position': bookmark.position,
        'is_archived': bookmark.is_archived,
        'archived_at': bookmark.archived_at.isoformat() if bookmark.archived_at else None,
        'message': message_payload,
        'created_at': bookmark.created_at.isoformat(),
    }


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


def _is_dissolved_group(conversation):
    return conversation.type == 'group' and conversation.is_dissolved


def _parse_dt_or_none(raw_value):
    if not raw_value:
        return None
    parsed = parse_datetime(raw_value)
    if not parsed:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _content_summary(message):
    if message.is_recalled:
        return '消息已撤回'

    content = message.content or {}
    msg_type = message.type
    if msg_type == 'text':
        return str(content.get('text', ''))
    if msg_type == 'image':
        return '[图片]'
    if msg_type == 'video':
        return '[视频]'
    if msg_type == 'audio':
        return '[语音]'
    if msg_type == 'file':
        filename = content.get('filename')
        return f"[文件] {filename}" if filename else '[文件]'
    if msg_type == 'code':
        return '[代码]'
    if msg_type == 'contact_card':
        return '[名片]'
    if msg_type == 'forward':
        return '[聊天记录]'
    if msg_type == 'system':
        return str(content.get('text', '系统消息'))
    return '[消息]'


def _build_reply_data(message):
    if not message or message.is_recalled:
        return None
    return {
        'msg_id': message.id,
        'sender_id': message.sender_id,
        'sender_name': message.sender.username if message.sender else '[已注销用户]',
        'type': message.type,
        'content_summary': _content_summary(message),
    }


def _serialize_message(message, read_by_count=0, reply_to=None, reactions=None, group_nickname=''):
    content = {} if message.is_recalled else message.content
    sender_payload = {
        'user_id': message.sender_id,
        'username': message.sender.username if message.sender else '[已注销用户]',
        'avatar': message.sender.avatar if message.sender and message.sender.avatar else None,
        'group_nickname': group_nickname,
    }
    reply_count = getattr(message, 'reply_count', None)
    if reply_count is None:
        reply_count = message.replies.count() if message.id else 0

    return {
        'msg_id': message.id,
        'conversation_id': message.conversation_id,
        'sender': sender_payload,
        'sender_id': message.sender_id,
        'sender_name': message.sender.username if message.sender else '[已注销用户]',
        'sender_avatar': message.sender.avatar if message.sender and message.sender.avatar else None,
        'group_nickname': group_nickname,
        'type': message.type,
        'content': content,
        'reply_to': reply_to,
        'reply_count': reply_count,
        'mentions': list(message.mentions.values_list('id', flat=True)) if message.id else [],
        'is_recalled': message.is_recalled,
        'created_at': message.created_at.isoformat(),
        'reactions': reactions or [],
        'read_by_count': read_by_count,
    }


def _push_message_created(message, reply_to=None):
    sender = message.sender
    send_to_conversation(message.conversation_id, 'new_message', {
        'conversation_id': message.conversation_id,
        'msg_id': message.id,
        'sender': {
            'user_id': sender.id if sender else None,
            'username': sender.username if sender else '[已注销用户]',
            'avatar': sender.avatar if sender and sender.avatar else None,
            'group_nickname': None,
        },
        'type': message.type,
        'content': message.content,
        'reply_to': reply_to,
        'mentions': list(message.mentions.values_list('id', flat=True)),
        'created_at': message.created_at.isoformat(),
    })


def _collect_reactions(message_ids, current_user_id):
    rows = Reaction.objects.filter(
        message_id__in=message_ids,
    ).values('message_id', 'emoji').annotate(count=Count('id'))

    user_rows = Reaction.objects.filter(
        message_id__in=message_ids,
    ).values_list('message_id', 'emoji', 'user_id')
    user_map = {}
    for msg_id, emoji, user_id in user_rows:
        user_map.setdefault((msg_id, emoji), []).append(user_id)

    mine_rows = Reaction.objects.filter(
        message_id__in=message_ids,
        user_id=current_user_id,
    ).values_list('message_id', 'emoji')
    mine_set = set(mine_rows)

    aggregated = {msg_id: [] for msg_id in message_ids}
    for row in rows:
        msg_id = row['message_id']
        emoji = row['emoji']
        users = user_map.get((msg_id, emoji), [])
        aggregated[msg_id].append({
            'emoji': emoji,
            'count': row['count'],
            'users': users,
            'is_me': current_user_id in users,
            'reacted_by_me': (msg_id, emoji) in mine_set,
        })
    return aggregated


class MessageListView(APIView):
    """
    5.1 发送消息   — POST /api/conversations/{conv_id}/messages
    5.2 获取聊天记录 — GET /api/conversations/{conv_id}/messages（cursor 分页）
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, conv_id):
        conv, _, error_response = _get_conversation_and_member(request.user, conv_id)
        if error_response:
            return error_response
        if _is_dissolved_group(conv):
            return Response(_err('CONVERSATION_NOT_FOUND', '群聊已解散'), status=404)

        if conv.type == 'private':
            peer = ConversationMember.objects.filter(
                conversation=conv,
                is_deleted=False,
                is_removed=False,
            ).exclude(user=request.user).select_related('user').first()
            if peer and Blacklist.objects.filter(user=peer.user, blocked_user=request.user).exists():
                return Response(_err('BLOCKED_BY_USER', '消息发送失败'), status=403)

        msg_type = request.data.get('type')
        valid_types = {choice[0] for choice in Message.TYPE_CHOICES}
        if msg_type not in valid_types:
            return Response(_err('INVALID_MESSAGE_TYPE', '不支持的消息类型'), status=400)

        content = request.data.get('content')
        if not isinstance(content, dict) or not content:
            return Response(_err('EMPTY_CONTENT', '消息内容为空'), status=400)

        required_fields = {
            'text': ['text'],
            'image': ['url'],
            'video': ['url'],
            'audio': ['url'],
            'file': ['url', 'filename'],
            'code': ['language', 'code'],
            'contact_card': ['user_id'],
            'calendar_invite': ['calendar_event_id', 'participant_id', 'title', 'start_at', 'end_at'],
            'forward': ['title', 'summary', 'msg_list'],
            'system': ['action', 'text'],
        }
        missing = [k for k in required_fields.get(msg_type, []) if k not in content]
        if missing:
            return Response(_err('INVALID_PARAMS', f'content 缺少字段: {", ".join(missing)}'), status=400)

        if msg_type == 'text' and len(str(content.get('text', ''))) > 5000:
            return Response(_err('CONTENT_TOO_LONG', '文本消息过长'), status=400)
        if msg_type == 'code' and len(str(content.get('code', ''))) > 50000:
            return Response(_err('CONTENT_TOO_LONG', '代码消息过长'), status=400)

        client_msg_id = request.data.get('client_msg_id')
        if client_msg_id:
            try:
                client_msg_id = uuid.UUID(str(client_msg_id))
            except (ValueError, TypeError):
                return Response(_err('INVALID_PARAMS', 'client_msg_id 不是合法 UUID'), status=400)

            existed = Message.objects.filter(
                conversation=conv,
                sender=request.user,
                client_msg_id=client_msg_id,
            ).select_related('sender', 'reply_to', 'reply_to__sender').first()
            if existed:
                return Response(
                    _serialize_message(
                        existed,
                        read_by_count=0,
                        reply_to=_build_reply_data(existed.reply_to),
                        reactions=[],
                        group_nickname=(None if conv.type == 'private' else ''),
                    ),
                    status=200,
                )

        reply_to_msg_id = request.data.get('reply_to_msg_id')
        reply_to = None
        if reply_to_msg_id is not None:
            try:
                reply_to_msg_id = int(reply_to_msg_id)
            except (TypeError, ValueError):
                return Response(_err('INVALID_PARAMS', 'reply_to_msg_id 必须为整数'), status=400)

            reply_to = Message.objects.filter(
                conversation=conv,
                id=reply_to_msg_id,
            ).select_related('sender').first()
            if not reply_to:
                return Response(_err('REPLY_MSG_NOT_FOUND', '被回复消息不存在'), status=404)

        mentions = request.data.get('mentions') or []
        if not isinstance(mentions, list):
            return Response(_err('INVALID_PARAMS', 'mentions 必须为数组'), status=400)

        mention_user_ids = []
        mention_seen = set()
        for raw_uid in mentions:
            try:
                uid = int(raw_uid)
            except (TypeError, ValueError):
                return Response(_err('INVALID_PARAMS', 'mentions 包含无效用户 ID'), status=400)
            if uid in mention_seen:
                continue
            mention_seen.add(uid)
            mention_user_ids.append(uid)

        if conv.type != 'group' and mention_user_ids:
            return Response(_err('INVALID_PARAMS', '仅群聊支持 mentions'), status=400)

        ai_user = None
        ai_mentioned = False
        text_mentions_ai = False
        if conv.type == 'group' and msg_type == 'text':
            text_body = str(content.get('text', ''))
            text_mentions_ai = '@AI' in text_body or '@ai_assistant' in text_body
        if conv.type == 'group' and (mention_user_ids or text_mentions_ai):
            from chat.views.ai import _get_ai_user
            ai_user = _get_ai_user()
            ai_mentioned = text_mentions_ai or ai_user.id in mention_user_ids
            if ai_mentioned and not (request.user.ai_api_key or '').strip():
                return Response(_err('AI_API_KEY_REQUIRED', '请先在个人设置中配置 AI API Key'), status=403)

        if mention_user_ids:
            member_mention_ids = [
                uid for uid in mention_user_ids
                if not (ai_mentioned and uid == ai_user.id)
            ]
            member_count = ConversationMember.objects.filter(
                conversation=conv,
                user_id__in=member_mention_ids,
                is_removed=False,
            ).count()
            if member_count != len(member_mention_ids):
                return Response(_err('INVALID_PARAMS', 'mentions 中包含非会话成员'), status=400)

        if msg_type == 'contact_card':
            card_user_id = content.get('user_id')
            try:
                card_user_id = int(card_user_id)
            except (TypeError, ValueError):
                return Response(_err('INVALID_PARAMS', '名片消息 user_id 必须为整数'), status=400)

            exists = User.objects.filter(id=card_user_id, is_active=True).exists()
            if not exists:
                return Response(_err('USER_NOT_FOUND', '名片用户不存在'), status=404)

            is_friend = Friendship.objects.filter(
                user=request.user,
                friend_id=card_user_id,
            ).exists()
            if not is_friend:
                return Response(_err('INVALID_PARAMS', '仅可发送好友名片'), status=400)

        with transaction.atomic():
            message = Message.objects.create(
                conversation=conv,
                sender=request.user,
                client_msg_id=client_msg_id or uuid.uuid4(),
                type=msg_type,
                content=content,
                reply_to=reply_to,
            )

            if mention_user_ids:
                message.mentions.add(*mention_user_ids)

            conv.updated_at = timezone.now()
            conv.save(update_fields=['updated_at'])

            ConversationMember.objects.filter(
                conversation=conv,
                is_deleted=True,
                is_removed=False,
            ).update(is_deleted=False)
            reply_payload = _build_reply_data(reply_to)

        if ai_mentioned:
            from chat.views.ai import _build_context, _call_llm, _get_user_ai_api_key, _looks_like_manual_question
            try:
                context = _build_context(conv, include_manual=_looks_like_manual_question(text_body))
                answer = _call_llm(context, _get_user_ai_api_key(request.user))
                ai_message = Message.objects.create(
                    conversation=conv,
                    sender=ai_user,
                    type='text',
                    content={'text': answer},
                )
                conv.updated_at = timezone.now()
                conv.save(update_fields=['updated_at'])
                _push_message_created(ai_message)
            except RuntimeError:
                pass
        _push_message_created(message, reply_to=reply_payload)

        return Response(
            _serialize_message(
                message,
                read_by_count=1,
                reply_to=reply_payload,
                reactions=[],
                    group_nickname=(None if conv.type == 'private' else ''),
            ),
            status=201,
        )

    def get(self, request, conv_id):
        conv, _, error_response = _get_conversation_and_member(request.user, conv_id)
        if error_response:
            return error_response

        page, page_size = _parse_pagination(request, default_size=50)
        before = request.query_params.get('before')
        after = request.query_params.get('after')
        sender_id = request.query_params.get('sender_id')
        keyword = (request.query_params.get('keyword') or '').strip()
        msg_type = request.query_params.get('type')

        before_dt = _parse_dt_or_none(before)
        after_dt = _parse_dt_or_none(after)
        if before and not before_dt:
            return Response(_err('INVALID_PARAMS', 'before 时间格式不合法'), status=400)
        if after and not after_dt:
            return Response(_err('INVALID_PARAMS', 'after 时间格式不合法'), status=400)

        qs = Message.objects.filter(conversation=conv).select_related(
            'sender', 'reply_to', 'reply_to__sender'
        ).annotate(reply_count=Count('replies'))

        hidden_msg_ids = MessageDeletion.objects.filter(
            user=request.user,
        ).values_list('message_id', flat=True)
        qs = qs.exclude(id__in=hidden_msg_ids)

        if before_dt:
            qs = qs.filter(created_at__lt=before_dt)
        if after_dt:
            qs = qs.filter(created_at__gt=after_dt)

        if sender_id is not None:
            try:
                sender_id = int(sender_id)
            except (TypeError, ValueError):
                return Response(_err('INVALID_PARAMS', 'sender_id 必须为整数'), status=400)
            qs = qs.filter(sender_id=sender_id)

        if msg_type:
            valid_types = {choice[0] for choice in Message.TYPE_CHOICES}
            if msg_type not in valid_types:
                return Response(_err('INVALID_PARAMS', 'type 过滤值不合法'), status=400)
            qs = qs.filter(type=msg_type)

        if keyword:
            qs = qs.filter(content__icontains=keyword)

        qs = qs.order_by('created_at', 'id')

        total = qs.count()
        offset = (page - 1) * page_size
        messages = list(qs[offset:offset + page_size])
        has_more = offset + len(messages) < total

        message_ids = [m.id for m in messages]
        reaction_map = _collect_reactions(message_ids, request.user.id) if message_ids else {}

        member_read_indexes = list(
            ConversationMember.objects.filter(
                conversation=conv,
                is_deleted=False,
                is_removed=False,
            ).values_list('read_index', flat=True)
        )

        nickname_map = {}
        if conv.type == 'group':
            nickname_map = {
                row['user_id']: row['nickname']
                for row in ConversationMember.objects.filter(
                    conversation=conv,
                    user_id__in=[m.sender_id for m in messages if m.sender_id],
                ).values('user_id', 'nickname')
            }

        results = []
        for msg in messages:
            read_by_count = sum(1 for read_index in member_read_indexes if read_index >= msg.id)
            results.append(
                _serialize_message(
                    msg,
                    read_by_count=read_by_count,
                    reply_to=_build_reply_data(msg.reply_to),
                    reactions=reaction_map.get(msg.id, []),
                    group_nickname=(None if conv.type == 'private' else nickname_map.get(msg.sender_id, '')),
                )
            )

        return Response({
            'total': total,
            'page': page,
            'page_size': page_size,
            'has_more': has_more,
            'results': results,
        })


class MessageReplyListView(APIView):
    """5.3 获取消息的回复列表 — GET /api/conversations/{conv_id}/messages/{msg_id}/replies"""
    permission_classes = [IsAuthenticated]

    def get(self, request, conv_id, msg_id):
        conv, _, error_response = _get_conversation_and_member(request.user, conv_id)
        if error_response:
            return error_response

        original_msg = Message.objects.filter(
            conversation=conv,
            id=msg_id,
        ).select_related('sender').first()
        if not original_msg:
            return Response(_err('MESSAGE_NOT_FOUND', '消息不存在'), status=404)

        page, page_size = _parse_pagination(request, default_size=20)

        deleted_msg_ids = MessageDeletion.objects.filter(
            user=request.user,
        ).values_list('message_id', flat=True)

        qs = Message.objects.filter(
            conversation=conv,
            reply_to_id=msg_id,
        ).exclude(id__in=deleted_msg_ids).select_related('sender').order_by('created_at', 'id')

        total = qs.count()
        offset = (page - 1) * page_size
        replies = list(qs[offset:offset + page_size])

        reply_ids = [m.id for m in replies]
        reaction_map = _collect_reactions(reply_ids, request.user.id) if reply_ids else {}

        member_read_indexes = list(
            ConversationMember.objects.filter(
                conversation=conv,
                is_deleted=False,
                is_removed=False,
            ).values_list('read_index', flat=True)
        )

        nickname_map = {}
        if conv.type == 'group':
            sender_ids = [m.sender_id for m in replies if m.sender_id]
            if original_msg.sender_id:
                sender_ids.append(original_msg.sender_id)
            nickname_map = {
                row['user_id']: row['nickname']
                for row in ConversationMember.objects.filter(
                    conversation=conv,
                    user_id__in=sender_ids,
                ).values('user_id', 'nickname')
            }

        reply_results = []
        for msg in replies:
            read_by_count = sum(1 for read_index in member_read_indexes if read_index >= msg.id)
            reply_results.append(
                _serialize_message(
                    msg,
                    read_by_count=read_by_count,
                    reply_to=_build_reply_data(original_msg),
                    reactions=reaction_map.get(msg.id, []),
                    group_nickname=(None if conv.type == 'private' else nickname_map.get(msg.sender_id, '')),
                )
            )

        return Response({
            'original_msg': _serialize_message(
                original_msg,
                read_by_count=sum(1 for read_index in member_read_indexes if read_index >= original_msg.id),
                reply_to=_build_reply_data(original_msg.reply_to),
                reactions=[],
                group_nickname=(None if conv.type == 'private' else nickname_map.get(original_msg.sender_id, '')),
            ),
            'total': total,
            'page': page,
            'page_size': page_size,
            'replies': reply_results,
        })


class MessageReadStatusView(APIView):
    """5.4 获取消息已读详情 — GET /api/conversations/{conv_id}/messages/{msg_id}/read-status"""
    permission_classes = [IsAuthenticated]

    def get(self, request, conv_id, msg_id):
        conv, member, error_response = _get_conversation_and_member(request.user, conv_id)
        if error_response:
            return error_response

        message = Message.objects.filter(conversation=conv, id=msg_id).first()
        if not message:
            return Response(_err('MESSAGE_NOT_FOUND', '消息不存在'), status=404)

        members = list(
            ConversationMember.objects.filter(
                conversation=conv,
                is_deleted=False,
                is_removed=False,
            ).select_related('user')
        )

        read_members = []
        unread_members = []
        for item in members:
            payload = {
                'user_id': item.user_id,
                'username': item.user.username,
                'avatar': item.user.avatar or None,
                'role': item.role,
            }
            if item.read_index >= message.id:
                read_members.append(payload)
            else:
                unread_members.append(payload)

        read_count = len(read_members)
        unread_count = len(unread_members)

        if conv.type == 'group' and member.role not in ('owner', 'admin'):
            return Response({
                'msg_id': message.id,
                'conversation_id': conv.id,
                'read_count': read_count,
                'unread_count': unread_count,
                'read_members': None,
                'unread_members': None,
            })

        if conv.type == 'private':
            peer_member = None
            for item in members:
                if item.user_id != request.user.id:
                    peer_member = item
                    break

            peer_read = bool(peer_member and peer_member.read_index >= message.id)
            return Response({
                'msg_id': message.id,
                'conversation_id': conv.id,
                'peer_is_read': peer_read,
                'read_count': read_count,
                'unread_count': unread_count,
                'read_members': read_members,
                'unread_members': unread_members,
            })

        return Response({
            'msg_id': message.id,
            'conversation_id': conv.id,
            'read_count': read_count,
            'unread_count': unread_count,
            'read_members': read_members,
            'unread_members': unread_members,
        })


class MessageDeleteView(APIView):
    """5.5 删除消息 — DELETE /api/conversations/{conv_id}/messages/{msg_id}"""
    permission_classes = [IsAuthenticated]

    def delete(self, request, conv_id, msg_id):
        conv, _, error_response = _get_conversation_and_member(request.user, conv_id)
        if error_response:
            return error_response

        message = Message.objects.filter(conversation=conv, id=msg_id).first()
        if not message:
            return Response(_err('MESSAGE_NOT_FOUND', '消息不存在'), status=404)

        MessageDeletion.objects.get_or_create(
            user=request.user,
            message=message,
        )
        return Response(status=204)


class MessageRecallView(APIView):
    """5.6 撤回消息 — POST /api/conversations/{conv_id}/messages/{msg_id}/recall【拓展功能】"""
    permission_classes = [IsAuthenticated]

    def post(self, request, conv_id, msg_id):
        conv, member, error_response = _get_conversation_and_member(request.user, conv_id)
        if error_response:
            return error_response

        message = Message.objects.filter(
            conversation=conv,
            id=msg_id,
        ).select_related('sender').first()
        if not message:
            return Response(_err('MESSAGE_NOT_FOUND', '消息不存在'), status=404)

        if message.is_recalled:
            return Response(_err('ALREADY_RECALLED', '消息已被撤回'), status=409)

        can_recall = message.sender_id == request.user.id
        if not can_recall and conv.type == 'group' and member.role in ('owner', 'admin'):
            can_recall = True
        if not can_recall:
            return Response(_err('NOT_SENDER', '仅发送者可撤回该消息'), status=403)

        if timezone.now() - message.created_at > timedelta(minutes=2):
            return Response(_err('RECALL_TIMEOUT', '超过可撤回时间窗口'), status=403)

        message.is_recalled = True
        message.recalled_at = timezone.now()
        message.recalled_by = request.user
        message.save(update_fields=['is_recalled', 'recalled_at', 'recalled_by'])
        send_to_conversation(conv.id, 'message_recalled', {
            'conversation_id': conv.id,
            'msg_id': message.id,
            'recalled_by': {'user_id': request.user.id, 'username': request.user.username},
            'recalled_at': message.recalled_at.isoformat() if message.recalled_at else None,
        })

        return Response({
            'msg_id': message.id,
            'is_recalled': message.is_recalled,
            'recalled_at': message.recalled_at.isoformat() if message.recalled_at else None,
        })


class MessageForwardView(APIView):
    """5.7 转发消息 — POST /api/messages/forward【拓展功能】"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        mode = request.data.get('mode')
        if mode not in ('individual', 'merged'):
            return Response(_err('INVALID_PARAMS', 'mode 须为 individual 或 merged'), status=400)

        msg_ids = request.data.get('msg_ids') or []
        target_conv_ids = request.data.get('target_conv_ids') or []
        source_conv_id = request.data.get('source_conv_id')

        if not isinstance(msg_ids, list) or not msg_ids:
            return Response(_err('INVALID_PARAMS', 'msg_ids 不能为空'), status=400)
        if not isinstance(target_conv_ids, list) or not target_conv_ids:
            return Response(_err('INVALID_PARAMS', 'target_conv_ids 不能为空'), status=400)
        if len(msg_ids) > 30:
            return Response(_err('TOO_MANY_MESSAGES', '单次最多转发 30 条消息'), status=400)
        if len(target_conv_ids) > 5:
            return Response(_err('TOO_MANY_TARGETS', '单次最多转发到 5 个会话'), status=400)

        try:
            source_conv_id = int(source_conv_id)
            msg_ids = [int(mid) for mid in msg_ids]
            target_conv_ids = [int(cid) for cid in target_conv_ids]
        except (TypeError, ValueError):
            return Response(_err('INVALID_PARAMS', 'source_conv_id/msg_ids/target_conv_ids 必须为整数'), status=400)

        if len(set(msg_ids)) != len(msg_ids):
            return Response(_err('INVALID_PARAMS', 'msg_ids 不可重复'), status=400)

        source_conv, _, source_error = _get_conversation_and_member(request.user, source_conv_id)
        if source_error:
            return source_error

        target_memberships = ConversationMember.objects.filter(
            user=request.user,
            conversation_id__in=target_conv_ids,
            is_deleted=False,
            is_removed=False,
        ).select_related('conversation')
        existing_conv_ids = set(Conversation.objects.filter(id__in=target_conv_ids).values_list('id', flat=True))
        if len(existing_conv_ids) != len(set(target_conv_ids)):
            return Response(_err('CONVERSATION_NOT_FOUND', '目标会话不存在'), status=404)

        target_map = {m.conversation_id: m.conversation for m in target_memberships}
        if len(target_map) != len(set(target_conv_ids)):
            return Response(_err('NOT_MEMBER', '不是目标会话成员'), status=403)
        if any(_is_dissolved_group(conv) for conv in target_map.values()):
            return Response(_err('CONVERSATION_NOT_FOUND', '目标群聊已解散'), status=404)

        source_messages = list(
            Message.objects.filter(
                conversation=source_conv,
                id__in=msg_ids,
            ).select_related('sender').order_by('created_at', 'id')
        )
        if len(source_messages) != len(msg_ids):
            return Response(_err('MESSAGE_NOT_FOUND', '存在不存在的来源消息'), status=404)

        target_conversations = []
        forwarded_count = 0
        created_messages = []

        with transaction.atomic():
            for conv_id in target_conv_ids:
                target_conv = target_map[conv_id]
                created_ids = []

                if mode == 'individual':
                    for src in source_messages:
                        forwarded_message = Message.objects.create(
                            conversation=target_conv,
                            sender=request.user,
                            type=src.type,
                            content=src.content,
                        )
                        created_ids.append(forwarded_message.id)
                        created_messages.append(forwarded_message)
                    forwarded_count += len(created_ids)
                else:
                    summary = []
                    for src in source_messages[:3]:
                        sender_name = src.sender.username if src.sender else '[已注销用户]'
                        summary.append(f'{sender_name}: {_content_summary(src)}')

                    merged_payload = {
                        'title': f'{request.user.username} 的聊天记录转发',
                        'summary': summary,
                        'msg_list': [
                            {
                                'msg_id': src.id,
                                'sender_id': src.sender_id,
                                'sender_name': src.sender.username if src.sender else '[已注销用户]',
                                'type': src.type,
                                'content': src.content,
                                'created_at': src.created_at.isoformat(),
                            }
                            for src in source_messages
                        ],
                    }
                    forwarded_message = Message.objects.create(
                        conversation=target_conv,
                        sender=request.user,
                        type='forward',
                        content=merged_payload,
                    )
                    created_ids.append(forwarded_message.id)
                    created_messages.append(forwarded_message)
                    forwarded_count += 1

                target_conv.updated_at = timezone.now()
                target_conv.save(update_fields=['updated_at'])
                ConversationMember.objects.filter(
                    conversation=target_conv,
                    is_deleted=True,
                    is_removed=False,
                ).update(is_deleted=False)
                target_conversations.append({
                    'conversation_id': conv_id,
                    'msg_ids': created_ids,
                })

        for message in created_messages:
            _push_message_created(message)

        return Response({
            'forwarded_count': forwarded_count,
            'target_conversations': target_conversations,
            'target_conv_ids': [item['conversation_id'] for item in target_conversations],
        }, status=201)


class ReactionView(APIView):
    """
    5.8a 添加 Reaction — POST /api/conversations/{conv_id}/messages/{msg_id}/reactions
    【拓展功能】
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, conv_id, msg_id):
        conv, _, error_response = _get_conversation_and_member(request.user, conv_id)
        if error_response:
            return error_response

        message = Message.objects.filter(conversation=conv, id=msg_id).first()
        if not message:
            return Response(_err('MESSAGE_NOT_FOUND', '消息不存在'), status=404)

        emoji = (request.data.get('emoji') or '').strip()
        if not emoji:
            return Response(_err('INVALID_PARAMS', '缺少 emoji'), status=400)

        existed = Reaction.objects.filter(
            message=message,
            user=request.user,
            emoji=emoji,
        ).first()
        if existed:
            return Response(_err('REACTION_EXISTS', '已添加过该表情'), status=409)

        reaction = Reaction.objects.create(
            message=message,
            user=request.user,
            emoji=emoji,
        )
        current_count = Reaction.objects.filter(message=message, emoji=emoji).count()
        ReactionEvent.objects.create(
            message=message,
            user=request.user,
            emoji=emoji,
            action='add',
            current_count=current_count,
        )
        send_to_conversation(conv.id, 'reaction_update', {
            'conversation_id': conv.id,
            'msg_id': message.id,
            'emoji': emoji,
            'action': 'add',
            'user': {'user_id': request.user.id, 'username': request.user.username},
            'current_count': current_count,
        })
        return Response({
            'msg_id': message.id,
            'emoji': reaction.emoji,
            'user_id': request.user.id,
            'created_at': reaction.created_at.isoformat(),
        }, status=201)


class ReactionRemoveView(APIView):
    """
    5.8b 取消 Reaction — DELETE /api/conversations/{conv_id}/messages/{msg_id}/reactions/{emoji}
    【拓展功能】
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, conv_id, msg_id, emoji):
        conv, _, error_response = _get_conversation_and_member(request.user, conv_id)
        if error_response:
            return error_response

        message = Message.objects.filter(conversation=conv, id=msg_id).first()
        if not message:
            return Response(_err('MESSAGE_NOT_FOUND', '消息不存在'), status=404)

        deleted_count, _ = Reaction.objects.filter(
            message=message,
            user=request.user,
            emoji=emoji,
        ).delete()
        if deleted_count:
            current_count = Reaction.objects.filter(message=message, emoji=emoji).count()
            ReactionEvent.objects.create(
                message=message,
                user=request.user,
                emoji=emoji,
                action='remove',
                current_count=current_count,
            )
            send_to_conversation(conv.id, 'reaction_update', {
                'conversation_id': conv.id,
                'msg_id': message.id,
                'emoji': emoji,
                'action': 'remove',
                'user': {'user_id': request.user.id, 'username': request.user.username},
                'current_count': current_count,
            })
        return Response(status=204)


class BookmarkListView(APIView):
    """
    5.9a 添加收藏   — POST /api/bookmarks
    5.9b 获取收藏列表 — GET /api/bookmarks
    【拓展功能】
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        page, page_size = _parse_pagination(request, default_size=20)

        archived_raw = str(request.query_params.get('archived', 'false')).lower()
        archived = archived_raw in ('1', 'true', 'yes', 'archived')

        qs = Bookmark.objects.filter(
            user=request.user,
            is_archived=archived,
        ).select_related(
            'message', 'message__sender', 'conversation'
        )
        if archived:
            qs = qs.order_by('-archived_at', '-created_at')
        else:
            qs = qs.order_by('position', '-created_at')

        total = qs.count()
        offset = (page - 1) * page_size
        bookmarks = qs[offset:offset + page_size]

        results = [_bookmark_payload(bm, request.user) for bm in bookmarks]

        return Response({
            'total': total,
            'page': page,
            'page_size': page_size,
            'results': results,
        })

    def post(self, request):
        msg_id = request.data.get('msg_id')
        conversation_id = request.data.get('conversation_id')
        title = str(request.data.get('title') or '').strip()
        note = (request.data.get('note') or '').strip()

        next_position = (Bookmark.objects.filter(user=request.user, is_archived=False).aggregate(
            max_position=Max('position')
        )['max_position'] or 0) + 1

        if msg_id is None and conversation_id is None:
            if not title:
                return Response(_err('INVALID_PARAMS', '缺少待办标题'), status=400)
            if len(title) > 200:
                return Response(_err('INVALID_PARAMS', '待办标题不能超过 200 字'), status=400)
            bookmark = Bookmark.objects.create(
                user=request.user,
                message=None,
                conversation=None,
                title=title,
                note=note,
                position=next_position,
            )
            return Response(_bookmark_payload(bookmark, request.user), status=201)

        if msg_id is None or conversation_id is None:
            return Response(_err('INVALID_PARAMS', '缺少 msg_id 或 conversation_id'), status=400)

        try:
            msg_id = int(msg_id)
            conversation_id = int(conversation_id)
        except (TypeError, ValueError):
            return Response(_err('INVALID_PARAMS', 'msg_id 和 conversation_id 必须为整数'), status=400)

        conv, _, error_response = _get_conversation_and_member(request.user, conversation_id)
        if error_response:
            return error_response

        message = Message.objects.filter(
            id=msg_id,
            conversation=conv,
        ).select_related('sender').first()
        if not message:
            return Response(_err('MESSAGE_NOT_FOUND', '消息不存在'), status=404)

        bookmark, created = Bookmark.objects.get_or_create(
            user=request.user,
            message=message,
            defaults={
                'conversation': conv,
                'note': note,
                'position': next_position,
            },
        )
        if not created:
            if note and note != bookmark.note:
                bookmark.note = note
                bookmark.save(update_fields=['note'])
            return Response(_err('BOOKMARK_EXISTS', '该消息已收藏'), status=409)

        return Response(_bookmark_payload(bookmark, request.user), status=201)


class BookmarkReorderView(APIView):
    """5.9d 待办排序 — POST /api/bookmarks/reorder【拓展功能】"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ids = request.data.get('bookmark_ids')
        if not isinstance(ids, list):
            return Response(_err('INVALID_PARAMS', 'bookmark_ids 必须为数组'), status=400)

        parsed_ids = []
        seen = set()
        for raw_id in ids:
            try:
                bookmark_id = int(raw_id)
            except (TypeError, ValueError):
                return Response(_err('INVALID_PARAMS', 'bookmark_ids 包含无效 ID'), status=400)
            if bookmark_id <= 0 or bookmark_id in seen:
                continue
            seen.add(bookmark_id)
            parsed_ids.append(bookmark_id)

        qs = Bookmark.objects.filter(
            user=request.user,
            is_archived=False,
            id__in=parsed_ids,
        )
        existing_ids = set(qs.values_list('id', flat=True))
        if len(existing_ids) != len(parsed_ids):
            return Response(_err('BOOKMARK_NOT_FOUND', '待办不存在或已归档'), status=404)

        with transaction.atomic():
            for position, bookmark_id in enumerate(parsed_ids, start=1):
                Bookmark.objects.filter(
                    user=request.user,
                    id=bookmark_id,
                    is_archived=False,
                ).update(position=position)

        return Response({'bookmark_ids': parsed_ids})


class BookmarkDeleteView(APIView):
    """5.9c 待办详情 — PUT/DELETE /api/bookmarks/{bookmark_id}【拓展功能】"""
    permission_classes = [IsAuthenticated]

    def put(self, request, bookmark_id):
        bookmark = Bookmark.objects.filter(
            id=bookmark_id,
            user=request.user,
        ).select_related('message', 'message__sender', 'conversation').first()
        if not bookmark:
            return Response(_err('BOOKMARK_NOT_FOUND', '待办不存在'), status=404)

        update_fields = []

        if 'title' in request.data:
            title = str(request.data.get('title') or '').strip()
            if len(title) > 200:
                return Response(_err('INVALID_PARAMS', '待办标题不能超过 200 字'), status=400)
            bookmark.title = title
            update_fields.append('title')

        if 'note' in request.data:
            note = str(request.data.get('note') or '').strip()
            if len(note) > 200:
                return Response(_err('INVALID_PARAMS', '备注不能超过 200 字'), status=400)
            bookmark.note = note
            update_fields.append('note')

        if 'position' in request.data:
            try:
                position = int(request.data.get('position'))
            except (TypeError, ValueError):
                return Response(_err('INVALID_PARAMS', 'position 必须为整数'), status=400)
            bookmark.position = max(0, position)
            update_fields.append('position')

        if 'is_archived' in request.data:
            is_archived = bool(request.data.get('is_archived'))
            if is_archived != bookmark.is_archived:
                bookmark.is_archived = is_archived
                bookmark.archived_at = timezone.now() if is_archived else None
                update_fields.extend(['is_archived', 'archived_at'])
                if not is_archived and 'position' not in request.data:
                    bookmark.position = (Bookmark.objects.filter(user=request.user, is_archived=False).aggregate(
                        max_position=Max('position')
                    )['max_position'] or 0) + 1
                    update_fields.append('position')

        if update_fields:
            bookmark.save(update_fields=list(dict.fromkeys(update_fields)))

        return Response(_bookmark_payload(bookmark, request.user))

    def delete(self, request, bookmark_id):
        bookmark = Bookmark.objects.filter(
            id=bookmark_id,
            user=request.user,
        ).first()
        if not bookmark:
            return Response(_err('BOOKMARK_NOT_FOUND', '收藏不存在'), status=404)

        bookmark.delete()
        return Response(status=204)
