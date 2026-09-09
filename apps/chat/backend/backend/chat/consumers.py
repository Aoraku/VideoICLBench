import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from chat.authentication import SimpleBearerAuthentication
from chat.models import ConversationMember, Friendship, Message, User
from chat.realtime import conversation_group, user_group


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        token = self.scope.get('query_string', b'').decode()
        token = dict(item.split('=', 1) for item in token.split('&') if '=' in item).get('token', '')
        self.user = await self._authenticate(token)
        if not self.user:
            await self.close(code=4001)
            return

        self.user_group_name = user_group(self.user.id)
        self.conversation_group_names = await self._conversation_groups(self.user.id)
        await self.channel_layer.group_add(self.user_group_name, self.channel_name)
        for group_name in self.conversation_group_names:
            await self.channel_layer.group_add(group_name, self.channel_name)

        await self.accept()
        presence_payload = await self._set_presence(self.user.id, 'online')
        await self._broadcast_presence_change(presence_payload)
        await self.send_json({
            'type': 'connection_established',
            'user_id': self.user.id,
            'timestamp': timezone.now().isoformat(),
        })

    async def disconnect(self, close_code):
        user = getattr(self, 'user', None)
        if not user:
            return
        await self.channel_layer.group_discard(self.user_group_name, self.channel_name)
        for group_name in getattr(self, 'conversation_group_names', []):
            await self.channel_layer.group_discard(group_name, self.channel_name)
        presence_payload = await self._set_presence(user.id, 'offline')
        await self._broadcast_presence_change(presence_payload)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            payload = json.loads(text_data or '{}')
        except json.JSONDecodeError:
            return
        msg_type = payload.get('type')
        if msg_type == 'ping':
            await self.send_json({'type': 'pong'})
        elif msg_type == 'typing':
            conversation_id = payload.get('conversation_id')
            if conversation_id and await self._is_member(self.user.id, conversation_id):
                await self.channel_layer.group_send(
                    conversation_group(conversation_id),
                    {
                        'type': 'push.event',
                        'event': {
                            'type': 'typing_indicator',
                            'data': {
                                'conversation_id': conversation_id,
                                'user_id': self.user.id,
                                'username': self.user.username,
                            },
                        },
                    },
                )
        elif msg_type == 'msg_ack':
            conversation_id = payload.get('conversation_id')
            msg_id = payload.get('msg_id')
            if conversation_id and msg_id:
                acknowledged = await self._ack_message(self.user.id, conversation_id, msg_id)
                if acknowledged:
                    await self.channel_layer.group_send(
                        conversation_group(conversation_id),
                        {
                            'type': 'push.event',
                            'event': {
                                'type': 'read_receipt',
                                'data': {
                                    'conversation_id': int(conversation_id),
                                    'user_id': self.user.id,
                                    'last_read_msg_id': int(msg_id),
                                    'read_at': acknowledged['read_at'],
                                },
                            },
                        },
                    )
                await self.send_json({
                    'type': 'msg_ack',
                    'conversation_id': conversation_id,
                    'msg_id': msg_id,
                    'status': 'ok' if acknowledged else 'ignored',
                    'timestamp': timezone.now().isoformat(),
                })

    async def push_event(self, event):
        payload = event['event']
        if payload.get('type') == 'force_disconnect':
            await self.send_json(payload)
            await self.close(code=4003)
            return
        await self.send_json(payload)

    async def send_json(self, payload):
        await self.send(text_data=json.dumps(payload, ensure_ascii=False))

    async def _broadcast_presence_change(self, payload):
        if not payload:
            return
        for friend_id in payload['friend_ids']:
            await self.channel_layer.group_send(
                user_group(friend_id),
                {
                    'type': 'push.event',
                    'event': {
                        'type': 'presence_change',
                        'data': payload['event'],
                    },
                },
            )

    @database_sync_to_async
    def _authenticate(self, token):
        if not token:
            return None
        fake_request = type('Request', (), {
            'headers': {'Authorization': f'Bearer {token}'},
            'META': {'HTTP_AUTHORIZATION': f'Bearer {token}'},
        })()
        try:
            result = SimpleBearerAuthentication().authenticate(fake_request)
        except AuthenticationFailed:
            return None
        if result:
            return result[0]
        try:
            result = JWTAuthentication().authenticate(fake_request)
        except AuthenticationFailed:
            return None
        return result[0] if result else None

    @database_sync_to_async
    def _conversation_groups(self, user_id):
        ids = ConversationMember.objects.filter(
            user_id=user_id,
            is_removed=False,
        ).values_list('conversation_id', flat=True)
        return [conversation_group(conversation_id) for conversation_id in ids]

    @database_sync_to_async
    def _is_member(self, user_id, conversation_id):
        return ConversationMember.objects.filter(
            user_id=user_id,
            conversation_id=conversation_id,
            is_removed=False,
        ).exists()

    @database_sync_to_async
    def _ack_message(self, user_id, conversation_id, msg_id):
        try:
            msg_id = int(msg_id)
            conversation_id = int(conversation_id)
        except (TypeError, ValueError):
            return False
        membership = ConversationMember.objects.filter(
            user_id=user_id,
            conversation_id=conversation_id,
            is_removed=False,
        ).first()
        if not membership:
            return False
        if not Message.objects.filter(id=msg_id, conversation_id=conversation_id).exists():
            return False
        if msg_id > membership.read_index:
            membership.read_index = msg_id
            membership.read_at = timezone.now()
            membership.save(update_fields=['read_index', 'read_at'])
        elif not membership.read_at:
            membership.read_at = timezone.now()
            membership.save(update_fields=['read_at'])
        return {'read_at': membership.read_at.isoformat()}

    @database_sync_to_async
    def _set_presence(self, user_id, presence):
        user = User.objects.filter(pk=user_id).first()
        if not user:
            return

        if presence == 'online' and user.presence in ('busy', 'invisible'):
            presence = user.presence
        user.presence = presence
        update_fields = ['presence']
        if presence == 'offline':
            user.last_seen = timezone.now()
            update_fields.append('last_seen')
        user.save(update_fields=update_fields)

        event = {
            'user_id': user.id,
            'presence': user.presence,
            'status_text': user.status_text or '',
            'status_emoji': user.status_emoji or '',
            'last_seen': user.last_seen.isoformat() if user.last_seen else None,
        }
        friend_ids = Friendship.objects.filter(user=user).values_list('friend_id', flat=True)
        return {'event': event, 'friend_ids': list(friend_ids)}
