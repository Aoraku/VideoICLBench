from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse

from .models import ConversationMember, Message
from .utils import auth_error_response, authenticate_request, bad_method_response, invalid_field_response, json_body


@csrf_exempt
def sync_messages(request):
    if request.method != "POST":
        return bad_method_response()

    user = authenticate_request(request)
    if not user:
        return auth_error_response()

    try:
        data = json_body(request)
    except ValueError:
        return invalid_field_response("body")

    last_msg_ids = data.get("last_msg_ids")
    if not isinstance(last_msg_ids, dict):
        return invalid_field_response("last_msg_ids")

    memberships = {
        str(cm.conversation_id): cm
        for cm in ConversationMember.objects.filter(user=user).select_related("conversation")
    }

    conversations_payload = {}
    for conv_id_str, membership in memberships.items():
        last_msg_id = last_msg_ids.get(conv_id_str, 0)
        if not isinstance(last_msg_id, int) or last_msg_id < 0:
            return invalid_field_response("last_msg_ids")

        qs = (
            Message.objects.filter(conversation_id=membership.conversation_id, id__gt=last_msg_id)
            .exclude(deleted_by_users__user=user)
            .select_related("sender", "reply_to", "reply_to__sender")
            .order_by("id")
        )

        messages = []
        for msg in qs:
            reply_to_payload = None
            if msg.reply_to:
                reply_to_payload = {
                    "msg_id": msg.reply_to.id,
                    "sender_name": msg.reply_to.sender.username,
                    "content": msg.reply_to.content,
                }
            messages.append(
                {
                    "msg_id": msg.id,
                    "sender_id": msg.sender_id,
                    "sender_name": msg.sender.username,
                    "content": msg.content,
                    "created_at": msg.created_at,
                    "reply_to": reply_to_payload,
                    "reply_count": msg.replies.count(),
                }
            )

        conversations_payload[conv_id_str] = {
            "messages": messages,
            "unread_count": membership.unread_count,
        }

    return JsonResponse({
        "code": 0,
        "info": "Succeed",
        "conversations": conversations_payload,
    })
