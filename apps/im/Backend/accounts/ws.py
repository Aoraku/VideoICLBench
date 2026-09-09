import json
import time
from urllib.parse import parse_qs

from asgiref.sync import sync_to_async
from django.db.models import F

from .jwt_utils import decode_jwt
from .models import Conversation, ConversationMember, Message


class ChatWebSocketApp:
    def __init__(self):
        self._connections = {}
        self._user_connections = {}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "websocket":
            await send({"type": "websocket.close"})
            return

        user = await self._authenticate(scope)
        if not user:
            await send({"type": "websocket.close", "code": 4401})
            return

        await send({"type": "websocket.accept"})
        conn_id = id(send)
        self._connections[conn_id] = send
        self._user_connections.setdefault(user.id, set()).add(conn_id)

        try:
            while True:
                event = await receive()
                if event["type"] == "websocket.disconnect":
                    break
                if event["type"] != "websocket.receive":
                    continue

                raw_text = event.get("text")
                if raw_text is None:
                    continue

                try:
                    payload = json.loads(raw_text)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue

                await self._handle_message(user, payload, send)
        finally:
            self._connections.pop(conn_id, None)
            user_conns = self._user_connections.get(user.id)
            if user_conns:
                user_conns.discard(conn_id)
                if not user_conns:
                    self._user_connections.pop(user.id, None)

    async def _authenticate(self, scope):
        from django.contrib.auth.models import User

        raw_qs = scope.get("query_string", b"").decode("utf-8")
        token = parse_qs(raw_qs).get("token", [None])[0]
        if not token:
            return None
        try:
            payload = decode_jwt(token)
        except ValueError:
            return None
        return await sync_to_async(User.objects.filter(id=payload["sub"]).first)()

    async def _handle_message(self, user, payload, send):
        msg_type = payload.get("type")
        if msg_type == "ping":
            await self._send_json(send, {"type": "pong"})
            return
        if msg_type == "chat_message":
            await self._handle_chat_message(user, payload, send)
            return
        if msg_type == "read_receipt":
            await self._handle_read_receipt(user, payload)

    async def _handle_chat_message(self, user, payload, send):
        conversation_id = payload.get("conversation_id")
        content = payload.get("content")
        reply_to_id = payload.get("reply_to_id")
        client_msg_id = payload.get("client_msg_id")

        if not isinstance(conversation_id, int):
            return
        if not isinstance(content, str) or not content.strip():
            return
        if reply_to_id is not None and not isinstance(reply_to_id, int):
            return
        if not isinstance(client_msg_id, str) or not client_msg_id:
            return

        can_send = await sync_to_async(
            ConversationMember.objects.filter(conversation_id=conversation_id, user=user).exists
        )()
        if not can_send:
            return

        now = time.time()

        if reply_to_id is not None:
            reply_exists = await sync_to_async(
                Message.objects.filter(id=reply_to_id, conversation_id=conversation_id).exists
            )()
            if not reply_exists:
                return

        msg = await sync_to_async(Message.objects.create)(
            conversation_id=conversation_id,
            sender=user,
            content=content.strip(),
            reply_to_id=reply_to_id,
            created_at=now,
        )
        await sync_to_async(Conversation.objects.filter(id=conversation_id).update)(updated_at=now)
        await sync_to_async(
            ConversationMember.objects.filter(conversation_id=conversation_id).exclude(user=user).update
        )(unread_count=F("unread_count") + 1)

        msg = await sync_to_async(
            lambda: Message.objects.select_related("sender", "sender__profile", "reply_to", "reply_to__sender").get(
                id=msg.id
            )
        )()
        sender_avatar = getattr(getattr(msg.sender, "profile", None), "avatar", "")
        reply_to_payload = None
        if msg.reply_to:
            reply_to_payload = {
                "msg_id": msg.reply_to.id,
                "sender_name": msg.reply_to.sender.username,
                "content": msg.reply_to.content,
            }

        chat_payload = {
            "type": "chat_message",
            "conversation_id": conversation_id,
            "msg_id": msg.id,
            "sender_id": msg.sender_id,
            "sender_name": msg.sender.username,
            "sender_avatar": sender_avatar,
            "content": msg.content,
            "created_at": msg.created_at,
            "reply_to": reply_to_payload,
            "reply_count": await sync_to_async(msg.replies.count)(),
        }
        await self._broadcast_conversation(conversation_id, chat_payload)
        await self._send_json(
            send,
            {
                "type": "message_ack",
                "client_msg_id": client_msg_id,
                "msg_id": msg.id,
                "created_at": msg.created_at,
            },
        )

    async def _handle_read_receipt(self, user, payload):
        conversation_id = payload.get("conversation_id")
        last_read_id = payload.get("last_read_id")
        if not isinstance(conversation_id, int) or not isinstance(last_read_id, int):
            return
        membership_exists = await sync_to_async(
            ConversationMember.objects.filter(conversation_id=conversation_id, user=user).exists
        )()
        if not membership_exists:
            return
        unread = await sync_to_async(
            lambda: Message.objects.filter(conversation_id=conversation_id, id__gt=last_read_id)
            .exclude(sender=user)
            .count()
        )()
        await sync_to_async(
            ConversationMember.objects.filter(conversation_id=conversation_id, user=user).update
        )(unread_count=unread)

    async def _broadcast_conversation(self, conversation_id, payload):
        user_ids = await sync_to_async(
            lambda: list(
                ConversationMember.objects.filter(conversation_id=conversation_id).values_list("user_id", flat=True)
            )
        )()
        for user_id in user_ids:
            for conn_id in self._user_connections.get(user_id, set()):
                send = self._connections.get(conn_id)
                if send:
                    await self._send_json(send, payload)

    async def _send_json(self, send, payload):
        await send({"type": "websocket.send", "text": json.dumps(payload, ensure_ascii=False)})


chat_ws_app = ChatWebSocketApp()
