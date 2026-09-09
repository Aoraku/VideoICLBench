"""
日程模块：日程 CRUD、参与者邀请、冲突查询。
"""

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from chat.models import (
    CalendarEvent,
    CalendarParticipant,
    Conversation,
    ConversationMember,
    Friendship,
    Message,
    User,
)
from chat.views.messages import _push_message_created


def _err(code, message):
    return {'error': {'code': code, 'message': message}}


def _parse_datetime_param(raw, field):
    value = parse_datetime(str(raw or '').strip())
    if not value:
        raise ValueError(f'{field} 时间格式不合法')
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value


def _parse_page(request, default_size=100):
    try:
        page = max(1, int(request.query_params.get('page', 1)))
        page_size = min(200, max(1, int(request.query_params.get('page_size', default_size))))
    except (TypeError, ValueError):
        raise ValueError('page/page_size 必须为整数')
    return page, page_size


def _serialize_participant(participant):
    user = participant.user
    return {
        'participant_id': participant.id,
        'user_id': user.id,
        'username': user.username,
        'avatar': user.avatar or None,
        'role': participant.role,
        'status': participant.status,
        'responded_at': participant.responded_at.isoformat() if participant.responded_at else None,
    }


def _serialize_event(event, current_user):
    participants = list(event.participants.select_related('user').order_by('id'))
    mine = next((p for p in participants if p.user_id == current_user.id), None)
    return {
        'event_id': event.id,
        'title': event.title,
        'description': event.description,
        'start_at': event.start_at.isoformat(),
        'end_at': event.end_at.isoformat(),
        'creator': {
            'user_id': event.creator_id,
            'username': event.creator.username if event.creator else '',
            'avatar': event.creator.avatar if event.creator and event.creator.avatar else None,
        },
        'my_role': mine.role if mine else None,
        'my_status': mine.status if mine else None,
        'participants': [_serialize_participant(p) for p in participants],
        'created_at': event.created_at.isoformat(),
        'updated_at': event.updated_at.isoformat(),
    }


def _private_conversation_for(user, peer):
    my_conv_ids = ConversationMember.objects.filter(
        user=user,
        conversation__type='private',
        is_removed=False,
    ).values_list('conversation_id', flat=True)
    peer_member = ConversationMember.objects.filter(
        user=peer,
        conversation_id__in=my_conv_ids,
        conversation__type='private',
        is_removed=False,
    ).select_related('conversation').first()
    if peer_member:
        return peer_member.conversation

    conv = Conversation.objects.create(type='private', name='')
    ConversationMember.objects.create(conversation=conv, user=user, role='member')
    ConversationMember.objects.create(conversation=conv, user=peer, role='member')
    return conv


def _send_calendar_invite(inviter, invitee, participant):
    event = participant.event
    conv = _private_conversation_for(inviter, invitee)
    content = {
        'calendar_event_id': event.id,
        'participant_id': participant.id,
        'title': event.title,
        'description': event.description,
        'start_at': event.start_at.isoformat(),
        'end_at': event.end_at.isoformat(),
        'status': participant.status,
        'inviter': {
            'user_id': inviter.id,
            'username': inviter.username,
            'avatar': inviter.avatar or None,
        },
    }
    message = Message.objects.create(
        conversation=conv,
        sender=inviter,
        type='calendar_invite',
        content=content,
    )
    conv.updated_at = timezone.now()
    conv.save(update_fields=['updated_at'])
    _push_message_created(message)


def _update_invite_messages(participant):
    qs = Message.objects.filter(type='calendar_invite')
    for message in qs:
        content = message.content if isinstance(message.content, dict) else {}
        if int(content.get('participant_id') or 0) != participant.id:
            continue
        next_content = {
            **content,
            'status': participant.status,
            'responded_at': participant.responded_at.isoformat() if participant.responded_at else None,
        }
        Message.objects.filter(pk=message.pk).update(content=next_content)


def _validate_event_payload(data, partial=False):
    title = data.get('title')
    description = data.get('description', '')
    start_raw = data.get('start_at')
    end_raw = data.get('end_at')

    result = {}
    if title is not None or not partial:
        title = str(title or '').strip()
        if not title:
            raise ValueError('日程名称不能为空')
        if len(title) > 100:
            raise ValueError('日程名称不能超过 100 字')
        result['title'] = title
    if 'description' in data or not partial:
        result['description'] = str(description or '').strip()
    if start_raw is not None or not partial:
        result['start_at'] = _parse_datetime_param(start_raw, 'start_at')
    if end_raw is not None or not partial:
        result['end_at'] = _parse_datetime_param(end_raw, 'end_at')
    if 'start_at' in result and 'end_at' in result and result['end_at'] <= result['start_at']:
        raise ValueError('结束时间必须晚于开始时间')
    return result


class CalendarEventListView(APIView):
    """GET/POST /api/calendar/events"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            page, page_size = _parse_page(request)
            start_at = _parse_datetime_param(request.query_params.get('start_at'), 'start_at')
            end_at = _parse_datetime_param(request.query_params.get('end_at'), 'end_at')
        except ValueError as exc:
            return Response(_err('INVALID_PARAMS', str(exc)), status=400)
        if end_at <= start_at:
            return Response(_err('INVALID_PARAMS', '结束时间必须晚于开始时间'), status=400)

        qs = CalendarEvent.objects.filter(
            participants__user=request.user,
            participants__status='accepted',
            start_at__lt=end_at,
            end_at__gt=start_at,
        ).select_related('creator').prefetch_related('participants__user').distinct().order_by('start_at', 'id')
        total = qs.count()
        offset = (page - 1) * page_size
        return Response({
            'total': total,
            'page': page,
            'page_size': page_size,
            'results': [_serialize_event(event, request.user) for event in qs[offset:offset + page_size]],
        })

    def post(self, request):
        try:
            payload = _validate_event_payload(request.data)
        except ValueError as exc:
            return Response(_err('INVALID_PARAMS', str(exc)), status=400)

        raw_invitees = request.data.get('invitee_ids') or []
        if not isinstance(raw_invitees, list):
            return Response(_err('INVALID_PARAMS', 'invitee_ids 必须为数组'), status=400)
        invitee_ids = []
        seen = {request.user.id}
        for raw_id in raw_invitees:
            try:
                uid = int(raw_id)
            except (TypeError, ValueError):
                return Response(_err('INVALID_PARAMS', 'invitee_ids 包含无效用户 ID'), status=400)
            if uid > 0 and uid not in seen:
                seen.add(uid)
                invitee_ids.append(uid)

        friend_ids = set(Friendship.objects.filter(
            user=request.user,
            friend_id__in=invitee_ids,
        ).values_list('friend_id', flat=True))
        missing = [uid for uid in invitee_ids if uid not in friend_ids]
        if missing:
            return Response(_err('NOT_FRIEND', f'以下用户不是你的好友：{missing}'), status=403)

        invitees = list(User.objects.filter(id__in=invitee_ids, is_active=True))
        if len(invitees) != len(invitee_ids):
            return Response(_err('USER_NOT_FOUND', '存在不存在的受邀用户'), status=404)

        with transaction.atomic():
            event = CalendarEvent.objects.create(creator=request.user, **payload)
            CalendarParticipant.objects.create(
                event=event,
                user=request.user,
                role='creator',
                status='accepted',
                responded_at=timezone.now(),
            )
            participants = [
                CalendarParticipant.objects.create(
                    event=event,
                    user=invitee,
                    role='invitee',
                    status='pending',
                )
                for invitee in invitees
            ]

        for participant in participants:
            _send_calendar_invite(request.user, participant.user, participant)

        event = CalendarEvent.objects.select_related('creator').prefetch_related('participants__user').get(pk=event.pk)
        return Response(_serialize_event(event, request.user), status=201)


class CalendarEventDetailView(APIView):
    """PUT/DELETE /api/calendar/events/{event_id}"""
    permission_classes = [IsAuthenticated]

    def _get_event(self, request, event_id):
        event = CalendarEvent.objects.filter(pk=event_id).select_related('creator').prefetch_related('participants__user').first()
        if not event:
            return None, Response(_err('EVENT_NOT_FOUND', '日程不存在'), status=404)
        if not CalendarParticipant.objects.filter(event=event, user=request.user).exists():
            return None, Response(_err('EVENT_NOT_FOUND', '日程不存在'), status=404)
        return event, None

    def put(self, request, event_id):
        event, error = self._get_event(request, event_id)
        if error:
            return error
        if event.creator_id != request.user.id:
            return Response(_err('PERMISSION_DENIED', '只有创建者可以修改日程'), status=403)

        try:
            payload = _validate_event_payload(request.data, partial=True)
        except ValueError as exc:
            return Response(_err('INVALID_PARAMS', str(exc)), status=400)
        start_at = payload.get('start_at', event.start_at)
        end_at = payload.get('end_at', event.end_at)
        if end_at <= start_at:
            return Response(_err('INVALID_PARAMS', '结束时间必须晚于开始时间'), status=400)

        for field, value in payload.items():
            setattr(event, field, value)
        event.save(update_fields=list(payload.keys()) + ['updated_at'] if payload else ['updated_at'])

        messages = Message.objects.filter(type='calendar_invite')
        for message in messages:
            content = message.content if isinstance(message.content, dict) else {}
            if int(content.get('calendar_event_id') or 0) != event.id:
                continue
            next_content = {
                **content,
                'title': event.title,
                'description': event.description,
                'start_at': event.start_at.isoformat(),
                'end_at': event.end_at.isoformat(),
            }
            Message.objects.filter(pk=message.pk).update(content=next_content)

        event = CalendarEvent.objects.select_related('creator').prefetch_related('participants__user').get(pk=event.pk)
        return Response(_serialize_event(event, request.user))

    def delete(self, request, event_id):
        event, error = self._get_event(request, event_id)
        if error:
            return error
        participant = CalendarParticipant.objects.filter(event=event, user=request.user).first()
        if event.creator_id == request.user.id:
            event.delete()
            return Response(status=204)
        participant.delete()
        return Response(status=204)


class CalendarInvitationHandleView(APIView):
    """PUT /api/calendar/invitations/{participant_id}"""
    permission_classes = [IsAuthenticated]

    def put(self, request, participant_id):
        action = request.data.get('action')
        if action not in ('accept', 'reject'):
            return Response(_err('INVALID_PARAMS', 'action 仅支持 accept/reject'), status=400)
        participant = CalendarParticipant.objects.filter(
            pk=participant_id,
            user=request.user,
            role='invitee',
        ).select_related('event', 'event__creator').first()
        if not participant:
            return Response(_err('INVITATION_NOT_FOUND', '日程邀请不存在'), status=404)
        participant.status = 'accepted' if action == 'accept' else 'rejected'
        participant.responded_at = timezone.now()
        participant.save(update_fields=['status', 'responded_at'])
        _update_invite_messages(participant)
        event = CalendarEvent.objects.select_related('creator').prefetch_related('participants__user').get(pk=participant.event_id)
        return Response(_serialize_event(event, request.user))


class CalendarAvailabilityView(APIView):
    """GET /api/calendar/availability"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            start_at = _parse_datetime_param(request.query_params.get('start_at'), 'start_at')
            end_at = _parse_datetime_param(request.query_params.get('end_at'), 'end_at')
        except ValueError as exc:
            return Response(_err('INVALID_PARAMS', str(exc)), status=400)
        if end_at <= start_at:
            return Response(_err('INVALID_PARAMS', '结束时间必须晚于开始时间'), status=400)

        raw_ids = str(request.query_params.get('user_ids') or '').split(',')
        user_ids = []
        for raw_id in raw_ids:
            if not raw_id.strip():
                continue
            try:
                uid = int(raw_id)
            except (TypeError, ValueError):
                return Response(_err('INVALID_PARAMS', 'user_ids 包含无效用户 ID'), status=400)
            if uid > 0 and uid not in user_ids:
                user_ids.append(uid)
        if not user_ids:
            user_ids = [request.user.id]

        allowed_ids = set(Friendship.objects.filter(user=request.user).values_list('friend_id', flat=True))
        allowed_ids.add(request.user.id)
        if any(uid not in allowed_ids for uid in user_ids):
            return Response(_err('PERMISSION_DENIED', '只能查询自己或好友的日程冲突'), status=403)

        users = User.objects.filter(id__in=user_ids, is_active=True)
        user_map = {u.id: u for u in users}
        results = []
        for uid in user_ids:
            user = user_map.get(uid)
            if not user:
                continue
            conflicts = CalendarEvent.objects.filter(
                participants__user_id=uid,
                participants__status='accepted',
                start_at__lt=end_at,
                end_at__gt=start_at,
            ).distinct().order_by('start_at')
            results.append({
                'user_id': uid,
                'username': user.username,
                'has_conflict': conflicts.exists(),
                'events': [
                    {
                        'event_id': event.id,
                        'title': event.title,
                        'start_at': event.start_at.isoformat(),
                        'end_at': event.end_at.isoformat(),
                    }
                    for event in conflicts[:5]
                ],
            })
        return Response({'results': results})
