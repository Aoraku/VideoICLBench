import time

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import Conversation, ConversationMember, Friend, GroupAnnouncement, GroupInvitation, Message
from .utils import (
    auth_error_response,
    authenticate_request,
    bad_method_response,
    error_response,
    ensure_profile,
    invalid_field_response,
    json_body,
    success_response,
    validate_avatar,
    validate_group_name,
)


def _serialize_last_message(conversation):
    last_message = conversation.messages.select_related("sender").order_by("-created_at", "-id").first()
    if not last_message:
        return None
    return {
        "msg_id": last_message.id,
        "content": last_message.content,
        "sender_id": last_message.sender_id,
        "sender_name": last_message.sender.username,
        "created_at": last_message.created_at,
    }


def _conversation_display_for_user(conversation, current_user):
    if conversation.type == "group":
        return conversation.name, conversation.avatar

    other_member = conversation.members.exclude(user_id=current_user.id).select_related("user").first()
    if not other_member:
        # 对方已注销，用占位名称而非当前用户自己，避免显示混乱
        return "（已注销用户）", ""

    profile = ensure_profile(other_member.user)
    return other_member.user.username, profile.avatar


def _permission_denied_response():
    return error_response(3, "Permission denied", 403)


def _get_group_and_membership(conversation_id, user):
    try:
        membership = ConversationMember.objects.select_related("conversation").get(
            conversation_id=conversation_id, user=user
        )
    except ConversationMember.DoesNotExist:
        return None, None
    if membership.conversation.type != "group":
        return None, None
    return membership.conversation, membership


def _group_owner_id(conversation):
    return conversation.owner_id or conversation.created_by_id


@csrf_exempt
def conversations(request):
    if request.method not in {"GET", "POST"}:
        return bad_method_response()

    user = authenticate_request(request)
    if not user:
        return auth_error_response()

    if request.method == "GET":
        memberships = (
            ConversationMember.objects.filter(user=user)
            .select_related("conversation")
            .order_by("-is_pinned", "-conversation__updated_at", "-conversation_id")
        )

        conversations_payload = []
        for membership in memberships:
            conversation = membership.conversation
            name, avatar = _conversation_display_for_user(conversation, user)
            payload = {
                "conversation_id": conversation.id,
                "type": conversation.type,
                "name": name,
                "avatar": avatar,
                "last_message": _serialize_last_message(conversation),
                "unread_count": membership.unread_count,
                "is_pinned": membership.is_pinned,
                "is_muted": membership.is_muted,
                "updated_at": conversation.updated_at,
            }
            if conversation.type == "private":
                other = conversation.members.exclude(user_id=user.id).only("user_id").first()
                if other:
                    payload["target_user_id"] = other.user_id
            conversations_payload.append(payload)
        return JsonResponse({"code": 0, "info": "Succeed", "conversations": conversations_payload})

    try:
        data = json_body(request)
    except ValueError:
        return invalid_field_response("body")

    allowed_fields = {"name", "member_ids"}
    for field_name in data:
        if field_name not in allowed_fields:
            return invalid_field_response(field_name)

    name = data.get("name")
    member_ids = data.get("member_ids")

    if not isinstance(name, str) or name.strip() == "":
        return invalid_field_response("name")
    if not isinstance(member_ids, list):
        return invalid_field_response("member_ids")

    unique_member_ids = []
    seen = set()
    for member_id in member_ids:
        if not isinstance(member_id, int):
            return invalid_field_response("member_ids")
        if member_id == user.id:
            continue
        if member_id not in seen:
            seen.add(member_id)
            unique_member_ids.append(member_id)

    if len(unique_member_ids) < 1:
        return error_response(-2, "At least 1 member", 400)

    friend_ids = set(
        Friend.objects.filter(user=user, friend_user_id__in=unique_member_ids).values_list("friend_user_id", flat=True)
    )
    for member_id in unique_member_ids:
        if member_id not in friend_ids:
            return error_response(-2, f"User [{member_id}] is not your friend", 400)

    # 单成员 = 私聊：去重，已存在则直接返回原会话
    if len(unique_member_ids) == 1:
        target_user_id = unique_member_ids[0]
        candidate_ids = ConversationMember.objects.filter(
            user=user, conversation__type="private"
        ).values_list("conversation_id", flat=True)
        existing = Conversation.objects.filter(
            id__in=list(candidate_ids),
            type="private",
            members__user_id=target_user_id,
        ).first()
        if existing is not None:
            return success_response({"conversation_id": existing.id})

        with transaction.atomic():
            conversation = Conversation.objects.create(
                type="private",
                name="",
                created_by=user,
                owner=None,
            )
            ConversationMember.objects.bulk_create([
                ConversationMember(conversation=conversation, user=user),
                ConversationMember(conversation=conversation, user_id=target_user_id),
            ])
        return success_response({"conversation_id": conversation.id})

    with transaction.atomic():
        conversation = Conversation.objects.create(
            type="group",
            name=name.strip(),
            created_by=user,
            owner=user,
        )
        ConversationMember.objects.create(conversation=conversation, user=user)
        ConversationMember.objects.bulk_create(
            [ConversationMember(conversation=conversation, user_id=member_id) for member_id in unique_member_ids]
        )

    return success_response({"conversation_id": conversation.id})


@csrf_exempt
def conversation_settings(request, conversation_id):
    if request.method != "PUT":
        return bad_method_response()

    user = authenticate_request(request)
    if not user:
        return auth_error_response()

    try:
        data = json_body(request)
    except ValueError:
        return invalid_field_response("body")

    allowed_fields = {"is_pinned", "is_muted"}
    for field_name in data:
        if field_name not in allowed_fields:
            return invalid_field_response(field_name)

    try:
        membership = ConversationMember.objects.get(conversation_id=conversation_id, user=user)
    except ConversationMember.DoesNotExist:
        return error_response(1, "Conversation not found", 404)

    if "is_pinned" in data:
        if not isinstance(data["is_pinned"], bool):
            return invalid_field_response("is_pinned")
        membership.is_pinned = data["is_pinned"]
    if "is_muted" in data:
        if not isinstance(data["is_muted"], bool):
            return invalid_field_response("is_muted")
        membership.is_muted = data["is_muted"]

    membership.save()
    return success_response()


@csrf_exempt
def group_info(request, conversation_id):
    if request.method not in {"GET", "PUT"}:
        return bad_method_response()

    user = authenticate_request(request)
    if not user:
        return auth_error_response()

    conversation, membership = _get_group_and_membership(conversation_id, user)
    if not conversation:
        return error_response(1, "Conversation not found", 404)

    owner_id = _group_owner_id(conversation)

    if request.method == "PUT":
        if membership.user_id != owner_id and not membership.is_admin:
            return _permission_denied_response()

        try:
            data = json_body(request)
        except ValueError:
            return invalid_field_response("body")

        allowed_fields = {"name", "avatar"}
        for field_name in data:
            if field_name not in allowed_fields:
                return invalid_field_response(field_name)

        update_fields = []
        if "name" in data:
            name = data.get("name")
            if not validate_group_name(name):
                return invalid_field_response("name")
            conversation.name = name.strip()
            update_fields.append("name")

        if "avatar" in data:
            avatar = data.get("avatar")
            if not validate_avatar(avatar):
                return invalid_field_response("avatar")
            conversation.avatar = avatar
            update_fields.append("avatar")

        if not update_fields:
            return invalid_field_response("name")

        conversation.updated_at = time.time()
        update_fields.append("updated_at")
        conversation.save(update_fields=update_fields)
        return success_response()

    members_qs = conversation.members.select_related("user", "user__profile").order_by("joined_at", "id")
    admins = []
    members = []
    for member in members_qs:
        profile = ensure_profile(member.user)
        role = "member"
        if member.user_id == owner_id:
            role = "owner"
        elif member.is_admin:
            role = "admin"
            admins.append(member.user_id)
        members.append(
            {
                "user_id": member.user_id,
                "username": member.user.username,
                "avatar": profile.avatar,
                "role": role,
                "joined_at": member.joined_at,
            }
        )

    announcements = []
    for announcement in conversation.group_announcements.select_related("publisher").order_by("-created_at", "-id"):
        announcements.append(
            {
                "id": announcement.id,
                "content": announcement.content,
                "publisher_id": announcement.publisher_id,
                "publisher_name": announcement.publisher.username,
                "created_at": announcement.created_at,
            }
        )

    return success_response(
        {
            "conversation_id": conversation.id,
            "name": conversation.name,
            "avatar": conversation.avatar or "",
            "owner_id": owner_id,
            "admins": admins,
            "members": members,
            "announcements": announcements,
            "created_at": conversation.created_at,
        }
    )


@csrf_exempt
def group_admin(request, conversation_id):
    if request.method != "PUT":
        return bad_method_response()

    user = authenticate_request(request)
    if not user:
        return auth_error_response()

    conversation, membership = _get_group_and_membership(conversation_id, user)
    if not conversation:
        return error_response(1, "Conversation not found", 404)

    owner_id = _group_owner_id(conversation)
    if membership.user_id != owner_id:
        return _permission_denied_response()

    try:
        data = json_body(request)
    except ValueError:
        return invalid_field_response("body")

    allowed_fields = {"user_id", "action"}
    for field_name in data:
        if field_name not in allowed_fields:
            return invalid_field_response(field_name)

    user_id = data.get("user_id")
    action = data.get("action")
    if not isinstance(user_id, int):
        return invalid_field_response("user_id")
    if action not in {"set_admin", "remove_admin", "transfer_owner"}:
        return invalid_field_response("action")

    try:
        target_membership = ConversationMember.objects.get(conversation_id=conversation_id, user_id=user_id)
    except ConversationMember.DoesNotExist:
        return error_response(1, "User not in group", 404)

    if action == "set_admin":
        if user_id != owner_id and not target_membership.is_admin:
            target_membership.is_admin = True
            target_membership.save(update_fields=["is_admin"])
        return success_response()

    if action == "remove_admin":
        if user_id == owner_id:
            return _permission_denied_response()
        if target_membership.is_admin:
            target_membership.is_admin = False
            target_membership.save(update_fields=["is_admin"])
        return success_response()

    old_owner_id = owner_id
    if user_id == old_owner_id:
        return success_response()

    conversation.owner_id = user_id
    conversation.updated_at = time.time()
    conversation.save(update_fields=["owner", "updated_at"])
    ConversationMember.objects.filter(conversation_id=conversation_id, user_id=user_id).update(is_admin=False)
    ConversationMember.objects.filter(conversation_id=conversation_id, user_id=old_owner_id).update(is_admin=False)
    return success_response()


@csrf_exempt
def group_members(request, conversation_id):
    if request.method != "DELETE":
        return bad_method_response()

    user = authenticate_request(request)
    if not user:
        return auth_error_response()

    conversation, membership = _get_group_and_membership(conversation_id, user)
    if not conversation:
        return error_response(1, "Conversation not found", 404)

    try:
        data = json_body(request)
    except ValueError:
        return invalid_field_response("body")

    allowed_fields = {"user_id"}
    for field_name in data:
        if field_name not in allowed_fields:
            return invalid_field_response(field_name)

    target_user_id = data.get("user_id")
    if not isinstance(target_user_id, int):
        return invalid_field_response("user_id")

    try:
        target_membership = ConversationMember.objects.get(conversation_id=conversation_id, user_id=target_user_id)
    except ConversationMember.DoesNotExist:
        return error_response(1, "User not in group", 404)

    owner_id = _group_owner_id(conversation)

    if membership.user_id == owner_id:
        if target_user_id == owner_id:
            return _permission_denied_response()
    elif membership.is_admin:
        if target_user_id == owner_id or target_membership.is_admin:
            return _permission_denied_response()
    else:
        return _permission_denied_response()

    target_membership.delete()
    GroupInvitation.objects.filter(
        conversation_id=conversation_id,
        invitee_id=target_user_id,
        status="pending",
    ).update(status="rejected")
    return success_response()


@csrf_exempt
def group_invite(request, conversation_id):
    if request.method not in {"GET", "POST", "PUT"}:
        return bad_method_response()

    user = authenticate_request(request)
    if not user:
        return auth_error_response()

    conversation, membership = _get_group_and_membership(conversation_id, user)
    if not conversation:
        return error_response(1, "Conversation not found", 404)

    owner_id = _group_owner_id(conversation)

    if request.method == "GET":
        if membership.user_id != owner_id and not membership.is_admin:
            return _permission_denied_response()

        invitations_payload = []
        invitations = (
            GroupInvitation.objects.filter(conversation_id=conversation_id, status="pending")
            .select_related("inviter", "invitee")
            .order_by("-created_at", "-id")
        )
        for invitation in invitations:
            invitations_payload.append(
                {
                    "invitation_id": invitation.id,
                    "inviter": {
                        "user_id": invitation.inviter_id,
                        "username": invitation.inviter.username,
                    },
                    "invitee": {
                        "user_id": invitation.invitee_id,
                        "username": invitation.invitee.username,
                    },
                    "created_at": invitation.created_at,
                }
            )
        return success_response({"invitations": invitations_payload})

    if request.method == "POST":
        try:
            data = json_body(request)
        except ValueError:
            return invalid_field_response("body")

        allowed_fields = {"user_id"}
        for field_name in data:
            if field_name not in allowed_fields:
                return invalid_field_response(field_name)

        invitee_id = data.get("user_id")
        if not isinstance(invitee_id, int):
            return invalid_field_response("user_id")

        if not Friend.objects.filter(user=user, friend_user_id=invitee_id).exists():
            return error_response(-2, "User is not your friend", 400)

        if ConversationMember.objects.filter(conversation_id=conversation_id, user_id=invitee_id).exists():
            return error_response(1, "User already in group", 409)

        if GroupInvitation.objects.filter(
            conversation_id=conversation_id,
            inviter=user,
            invitee_id=invitee_id,
            status="pending",
        ).exists():
            return success_response()

        GroupInvitation.objects.create(
            conversation_id=conversation_id,
            inviter=user,
            invitee_id=invitee_id,
            status="pending",
        )
        return success_response()

    if membership.user_id != owner_id and not membership.is_admin:
        return _permission_denied_response()

    try:
        data = json_body(request)
    except ValueError:
        return invalid_field_response("body")

    allowed_fields = {"invitation_id", "action"}
    for field_name in data:
        if field_name not in allowed_fields:
            return invalid_field_response(field_name)

    invitation_id = data.get("invitation_id")
    action = data.get("action")
    if not isinstance(invitation_id, int):
        return invalid_field_response("invitation_id")
    if action not in {"accept", "reject"}:
        return invalid_field_response("action")

    try:
        invitation = GroupInvitation.objects.get(id=invitation_id, conversation_id=conversation_id)
    except GroupInvitation.DoesNotExist:
        return error_response(1, "Invitation not found", 404)

    if invitation.status != "pending":
        return success_response()

    if action == "accept":
        if not ConversationMember.objects.filter(
            conversation_id=conversation_id, user_id=invitation.invitee_id
        ).exists():
            ConversationMember.objects.create(
                conversation_id=conversation_id,
                user_id=invitation.invitee_id,
            )
        invitation.status = "accepted"
    else:
        invitation.status = "rejected"
    invitation.save(update_fields=["status"])
    return success_response()


@csrf_exempt
def group_leave(request, conversation_id):
    if request.method != "POST":
        return bad_method_response()

    user = authenticate_request(request)
    if not user:
        return auth_error_response()

    conversation, membership = _get_group_and_membership(conversation_id, user)
    if not conversation:
        return error_response(1, "Conversation not found", 404)

    owner_id = _group_owner_id(conversation)
    if membership.user_id == owner_id:
        return error_response(3, "Owner must transfer ownership before leaving", 403)

    membership.delete()
    return success_response()


@csrf_exempt
def group_announcement(request, conversation_id):
    if request.method != "POST":
        return bad_method_response()

    user = authenticate_request(request)
    if not user:
        return auth_error_response()

    conversation, membership = _get_group_and_membership(conversation_id, user)
    if not conversation:
        return error_response(1, "Conversation not found", 404)

    owner_id = _group_owner_id(conversation)
    if membership.user_id != owner_id and not membership.is_admin:
        return _permission_denied_response()

    try:
        data = json_body(request)
    except ValueError:
        return invalid_field_response("body")

    allowed_fields = {"content"}
    for field_name in data:
        if field_name not in allowed_fields:
            return invalid_field_response(field_name)

    content = data.get("content")
    if not isinstance(content, str) or not content.strip():
        return invalid_field_response("content")

    now = time.time()
    announcement = GroupAnnouncement.objects.create(
        conversation_id=conversation_id,
        publisher=user,
        content=content.strip(),
        created_at=now,
    )
    Conversation.objects.filter(id=conversation_id).update(updated_at=now)
    return success_response({"announcement_id": announcement.id, "created_at": announcement.created_at})
