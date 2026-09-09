"""
chat/views/sync.py
消息同步模块

对应接口：8.1
负责人：同学 B
"""

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.db.models import Q

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from chat.models import (
    Conversation,
    ConversationMember,
    FriendRequest,
    GroupAnnouncement,
    GroupInvitation,
    Message,
    ReactionEvent,
)


def _err(code, message):
    return {'error': {'code': code, 'message': message}}


def _parse_since(raw_since):
    if not raw_since:
        return None
    parsed = parse_datetime(raw_since)
    if not parsed:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _serialize_message(message):
    return {
        'conversation_id': message.conversation_id,
        'msg_id': message.id,
        'sender': {
            'user_id': message.sender_id,
            'username': message.sender.username if message.sender else '[已注销用户]',
        },
        'type': message.type,
        'content': {} if message.is_recalled else message.content,
        'reply_to_msg_id': message.reply_to_id,
        'mentions': list(message.mentions.values_list('id', flat=True)),
        'is_recalled': message.is_recalled,
        'created_at': message.created_at.isoformat(),
    }


def _serialize_user(user):
    return {
        'user_id': user.id,
        'username': user.username,
        'avatar': user.avatar or None,
    }


def _trim_rows(rows, limit):
    rows = list(rows[:limit + 1])
    return rows[:limit], len(rows) > limit


def _sync_events(user, since, conversation_ids, limit):
    events = []
    has_more = False
    friend_requests = FriendRequest.objects.filter(
        Q(from_user=user) | Q(to_user=user),
        updated_at__gt=since,
    ).select_related('from_user', 'to_user').order_by('updated_at', 'id')
    friend_requests, overflow = _trim_rows(friend_requests, limit)
    has_more = has_more or overflow
    for req in friend_requests:
        events.append({
            'type': 'friend_request',
            'id': req.id,
            'updated_at': req.updated_at.isoformat(),
            'data': {
                'request_id': req.id,
                'from_user': _serialize_user(req.from_user),
                'to_user': _serialize_user(req.to_user),
                'source': req.source,
                'message': req.message,
                'status': req.status,
                'created_at': req.created_at.isoformat(),
                'updated_at': req.updated_at.isoformat(),
            },
        })

    invitations = GroupInvitation.objects.filter(
        Q(inviter=user) | Q(invitee=user) | Q(reviewed_by=user) | Q(conversation_id__in=conversation_ids),
        updated_at__gt=since,
    ).select_related('conversation', 'inviter', 'invitee', 'reviewed_by').order_by('updated_at', 'id')
    invitations, overflow = _trim_rows(invitations, limit)
    has_more = has_more or overflow
    for invitation in invitations:
        events.append({
            'type': 'group_invitation',
            'id': invitation.id,
            'updated_at': invitation.updated_at.isoformat(),
            'data': {
                'invitation_id': invitation.id,
                'conversation_id': invitation.conversation_id,
                'group_name': invitation.conversation.name,
                'inviter': _serialize_user(invitation.inviter),
                'invitee': _serialize_user(invitation.invitee),
                'reviewed_by': _serialize_user(invitation.reviewed_by) if invitation.reviewed_by else None,
                'status': invitation.status,
                'created_at': invitation.created_at.isoformat(),
                'updated_at': invitation.updated_at.isoformat(),
            },
        })

    announcements = GroupAnnouncement.objects.filter(
        conversation_id__in=conversation_ids,
        created_at__gt=since,
    ).select_related('conversation', 'publisher').order_by('created_at', 'id')
    announcements, overflow = _trim_rows(announcements, limit)
    has_more = has_more or overflow
    for announcement in announcements:
        events.append({
            'type': 'group_announcement',
            'id': announcement.id,
            'updated_at': announcement.created_at.isoformat(),
            'data': {
                'announcement_id': announcement.id,
                'conversation_id': announcement.conversation_id,
                'group_name': announcement.conversation.name,
                'publisher': _serialize_user(announcement.publisher) if announcement.publisher else None,
                'content': announcement.content,
                'created_at': announcement.created_at.isoformat(),
            },
        })

    recalled_messages = Message.objects.filter(
        conversation_id__in=conversation_ids,
        is_recalled=True,
        recalled_at__gt=since,
    ).select_related('sender', 'recalled_by').order_by('recalled_at', 'id')
    recalled_messages, overflow = _trim_rows(recalled_messages, limit)
    has_more = has_more or overflow
    for message in recalled_messages:
        recalled_by = message.recalled_by or message.sender
        events.append({
            'type': 'message_recalled',
            'id': message.id,
            'updated_at': message.recalled_at.isoformat(),
            'data': {
                'conversation_id': message.conversation_id,
                'msg_id': message.id,
                'recalled_by': _serialize_user(recalled_by) if recalled_by else None,
                'recalled_at': message.recalled_at.isoformat(),
            },
        })

    reactions = ReactionEvent.objects.filter(
        message__conversation_id__in=conversation_ids,
        created_at__gt=since,
    ).select_related('message', 'user').order_by('created_at', 'id')
    reactions, overflow = _trim_rows(reactions, limit)
    has_more = has_more or overflow
    for reaction_event in reactions:
        events.append({
            'type': 'reaction_update',
            'id': reaction_event.id,
            'updated_at': reaction_event.created_at.isoformat(),
            'data': {
                'conversation_id': reaction_event.message.conversation_id,
                'msg_id': reaction_event.message_id,
                'emoji': reaction_event.emoji,
                'action': reaction_event.action,
                'user': _serialize_user(reaction_event.user) if reaction_event.user else None,
                'current_count': reaction_event.current_count,
            },
        })

    groups = Conversation.objects.filter(
        id__in=conversation_ids,
        type='group',
        updated_at__gt=since,
    ).select_related('owner').order_by('updated_at', 'id')
    groups, overflow = _trim_rows(groups, limit)
    has_more = has_more or overflow
    for group in groups:
        events.append({
            'type': 'group_updated',
            'id': group.id,
            'updated_at': group.updated_at.isoformat(),
            'data': {
                'conversation_id': group.id,
                'name': group.name,
                'avatar': group.avatar or None,
                'owner': _serialize_user(group.owner) if group.owner else None,
                'is_dissolved': group.is_dissolved,
                'updated_at': group.updated_at.isoformat(),
            },
        })

    events.sort(key=lambda event: (event['updated_at'], event['type'], event['id']))
    if len(events) > limit:
        has_more = True
    return events[:limit], has_more


class SyncMessagesView(APIView):
    """8.1 拉取离线增量消息 — GET /api/sync/messages"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        since = _parse_since(request.query_params.get('since'))
        if not since:
            return Response(_err('INVALID_PARAMS', 'since 必须为合法 ISO 8601 时间'), status=400)

        try:
            limit = int(request.query_params.get('limit', 200))
        except (TypeError, ValueError):
            return Response(_err('INVALID_PARAMS', 'limit 必须为整数'), status=400)
        limit = min(1000, max(1, limit))

        conversation_ids = list(
            ConversationMember.objects.filter(
                user=request.user,
                is_removed=False,
            ).values_list('conversation_id', flat=True)
        )

        qs = Message.objects.filter(
            conversation_id__in=conversation_ids,
            created_at__gt=since,
        ).select_related('sender').prefetch_related('mentions').order_by('created_at', 'id')

        rows = list(qs[:limit + 1])
        has_more = len(rows) > limit
        messages = rows[:limit]
        sync_timestamp = timezone.now()
        events, events_has_more = _sync_events(request.user, since, conversation_ids, limit)

        return Response({
            'messages': [_serialize_message(message) for message in messages],
            'events': events,
            'has_more': has_more or events_has_more,
            'sync_timestamp': sync_timestamp.isoformat(),
        })
