import time
from django.db import transaction
from django.db.models import Count, F
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import Conversation, ConversationMember, Friend, Message, DeletedMessage
from .utils import (
    authenticate_request,
    bad_method_response,
    error_response,
    ensure_profile,
    invalid_field_response,
    json_body,
    success_response,
)

@csrf_exempt
def messages_view(request, conversation_id):
    if request.method not in {"GET", "POST"}:
        return bad_method_response()

    user = authenticate_request(request)
    if not user:
        return error_response(-1, "Invalid or expired JWT", 401)

    # Validate conversation membership to authorize access
    membership = ConversationMember.objects.filter(conversation_id=conversation_id, user=user).first()
    
    if request.method == "POST":
        try:
            data = json_body(request)
        except ValueError:
            return invalid_field_response("body")

        reply_to_id = data.get("reply_to_id")
        if reply_to_id is not None:
            if not isinstance(reply_to_id, int):
                return invalid_field_response("reply_to_id")
            
            # Ensuring the message exists within the exact same conversation context FIRST
            if not Message.objects.filter(id=reply_to_id, conversation_id=conversation_id).exists():
                return error_response(2, "Replied message not found", 404)
        
        # Now validate membership since reply_to logic takes precedence in error responses
        if not membership:
            return error_response(1, "Conversation not found", 404)

        content = data.get("content")
        if not isinstance(content, str) or not content.strip():
            return invalid_field_response("content")

        # For private conversations, verify the other party is still a friend (not deleted/deactivated)
        conversation = membership.conversation
        if conversation.type == "private":
            other_member = ConversationMember.objects.filter(
                conversation_id=conversation_id
            ).exclude(user=user).select_related("user").first()
            if other_member is None or not other_member.user.is_active:
                return error_response(4, "对方账号已注销，无法发送消息", 403)
            if not Friend.objects.filter(user=user, friend_user=other_member.user).exists():
                return error_response(3, "对方已不是你的好友，无法发送消息", 403)

        now = time.time()
        
        # Enterprise Grade: Ensure atomicity of the message sending process
        with transaction.atomic():
            msg = Message.objects.create(
                conversation_id=conversation_id,
                sender=user,
                content=content.strip(),
                reply_to_id=reply_to_id,
                created_at=now
            )
            
            # 1. Update the parent conversation heartbeat
            Conversation.objects.filter(id=conversation_id).update(updated_at=now)
            
            # 2. Push unread states to other members natively at DB level
            ConversationMember.objects.filter(
                conversation_id=conversation_id
            ).exclude(user=user).update(unread_count=F("unread_count") + 1)

        return success_response({"msg_id": msg.id, "created_at": msg.created_at})

    else:
        if not membership:
            return error_response(1, "Conversation not found", 404)
            
        # Pagination & Filtering extraction
        if "limit" in request.GET:
            try:
                limit = int(request.GET["limit"])
            except ValueError:
                return error_response(-2, "Invalid limit", 400)
        else:
            limit = 50
            
        limit = max(1, min(limit, 100))

        before_id = request.GET.get("before_id")
        sender_id = request.GET.get("sender_id")
        sender_ids_raw = request.GET.getlist("sender_ids")
        start_time = request.GET.get("start_time")
        end_time = request.GET.get("end_time")

        qs = Message.objects.filter(conversation_id=conversation_id)

        # High-performance exclusion using Subquery/OuterRef conceptually,
        # but in Django the reverse relationship exclude accomplishes an efficient LEFT JOIN WHERE NULL.
        qs = qs.exclude(deleted_by_users__user=user)

        if before_id:
            try:
                qs = qs.filter(id__lt=int(before_id))
            except ValueError:
                return error_response(-2, "Invalid before_id", 400)
        
        sender_filters = set()
        if sender_id:
            try:
                sender_filters.add(int(sender_id))
            except ValueError:
                return error_response(-2, "Invalid sender_id", 400)

        if sender_ids_raw:
            try:
                for raw in sender_ids_raw:
                    for part in str(raw).split(","):
                        part = part.strip()
                        if not part:
                            continue
                        sender_filters.add(int(part))
            except ValueError:
                return error_response(-2, "Invalid sender_ids", 400)

        if sender_filters:
            member_ids = set(
                ConversationMember.objects.filter(conversation_id=conversation_id).values_list("user_id", flat=True)
            )
            if not sender_filters.issubset(member_ids):
                return error_response(-2, "Invalid sender_ids", 400)
            qs = qs.filter(sender_id__in=sender_filters)
                
        if start_time:
            try:
                qs = qs.filter(created_at__gte=float(start_time))
            except ValueError:
                return error_response(-2, "Invalid start_time", 400)
                
        if end_time:
            try:
                qs = qs.filter(created_at__lte=float(end_time))
            except ValueError:
                return error_response(-2, "Invalid end_time", 400)

        # Optimize DB access via select_related
        qs = qs.select_related("sender", "sender__profile", "reply_to", "reply_to__sender")
        qs = qs.annotate(reply_count_val=Count("replies"))
        qs = qs.order_by("-id")[:limit]

        messages_payload = []
        for msg in qs:
            sender_profile = getattr(msg.sender, "profile", None)
            avatar_url = sender_profile.avatar if sender_profile else ""

            reply_to_payload = None
            if msg.reply_to:
                reply_to_payload = {
                    "msg_id": msg.reply_to.id,
                    "sender_name": msg.reply_to.sender.username,
                    "content": msg.reply_to.content
                }

            messages_payload.append({
                "msg_id": msg.id,
                "sender_id": msg.sender_id,
                "sender_name": msg.sender.username,
                "sender_avatar": avatar_url,
                "content": msg.content,
                "created_at": msg.created_at,
                "reply_to": reply_to_payload,
                "reply_count": msg.reply_count_val
            })

        return success_response({"messages": messages_payload})

@csrf_exempt
def message_detail(request, conversation_id, msg_id):
    if request.method != "DELETE":
        return bad_method_response()

    user = authenticate_request(request)
    if not user:
        return error_response(-1, "Invalid or expired JWT", 401)
        
    membership = ConversationMember.objects.filter(conversation_id=conversation_id, user=user).first()
    if not membership:
        return error_response(1, "Conversation not found", 404)

    try:
        msg_id_val = int(msg_id)
    except ValueError:
        return invalid_field_response("msg_id")

    # The spec dictates: Message not found 404 -> Code 1
    if not Message.objects.filter(id=msg_id_val, conversation_id=conversation_id).exists():
        return error_response(1, "Message not found", 404)
        
    if DeletedMessage.objects.filter(message_id=msg_id_val, user=user).exists():
        return error_response(1, "Message not found", 404)

    # Logical isolation deletion: Insert a soft delete pointer for just this user instance
    DeletedMessage.objects.create(message_id=msg_id_val, user=user)

    return success_response()

@csrf_exempt
def read_messages(request, conversation_id):
    if request.method != "POST":
        return bad_method_response()

    user = authenticate_request(request)
    if not user:
        return error_response(-1, "Invalid or expired JWT", 401)

    membership = ConversationMember.objects.filter(conversation_id=conversation_id, user=user).first()
    if not membership:
        return error_response(1, "Conversation not found", 404)

    try:
        data = json_body(request)
    except ValueError:
        return invalid_field_response("body")

    last_read_id = data.get("last_read_id")
    if not isinstance(last_read_id, int):
        return invalid_field_response("last_read_id")

    # Fast calculation for remaining unread count dynamically
    unread = Message.objects.filter(
        conversation_id=conversation_id,
        id__gt=last_read_id
    ).exclude(sender=user).exclude(deleted_by_users__user=user).count()

    updated = ConversationMember.objects.filter(
        conversation_id=conversation_id, 
        user=user
    ).update(unread_count=unread)
    
    # Optional logic protection: If `updated == 0`, potentially the user isn't in the conversation.
    # The requirement is strictly to apply successfully if all is alright.
    
    return success_response()
