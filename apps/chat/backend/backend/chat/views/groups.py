"""
chat/views/groups.py
群聊管理模块：群信息、群头像、群成员、管理员、群主、邀请、公告、解散

对应接口：6.1 - 6.16
负责人：同学 B
"""

import os

from django.conf import settings as django_settings
from django.db import transaction
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser
from rest_framework import status

from chat.models import (
    Conversation,
    ConversationMember,
    Friendship,
    GroupAnnouncement,
    GroupInvitation,
    Message,
)
from chat.realtime import send_to_conversation, send_to_user


def _err(code, message):
    return {'error': {'code': code, 'message': message}}


def _get_group_and_member(user, conv_id):
    conv = Conversation.objects.filter(pk=conv_id, type='group', is_dissolved=False).first()
    if not conv:
        return None, None, Response(
            _err('CONVERSATION_NOT_FOUND', '会话不存在或不是群聊'), status=404
        )

    member = ConversationMember.objects.filter(
        user=user,
        conversation=conv,
        is_removed=False,
    ).first()
    if not member:
        return conv, None, Response(
            _err('NOT_MEMBER', '不是群成员'), status=403
        )

    return conv, member, None


def _status_payload(user):
    return {
        'presence': user.presence,
        'status_text': user.status_text,
        'status_emoji': user.status_emoji,
    }


def _parse_pagination(request, default_size=20):
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


# ---- 群基本信息 (6.1 - 6.3) ----

class GroupInfoView(APIView):
    """
    6.1  获取群信息 — GET /api/conversations/{conv_id}/group
    6.2  修改群信息 — PUT /api/conversations/{conv_id}/group
    6.16 解散群聊   — DELETE /api/conversations/{conv_id}/group
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, conv_id):
        conv, member, error_response = _get_group_and_member(request.user, conv_id)
        if error_response:
            return error_response

        owner = conv.owner
        latest_announcement = GroupAnnouncement.objects.filter(
            conversation=conv
        ).select_related('publisher').order_by('-created_at').first()

        return Response({
            'conversation_id': conv.id,
            'type': conv.type,
            'name': conv.name or None,
            'avatar': conv.avatar or None,
            'owner': {
                'user_id': owner.id,
                'username': owner.username,
                'avatar': owner.avatar or None,
            } if owner else None,
            'member_count': ConversationMember.objects.filter(
                conversation=conv,
                is_removed=False,
            ).count(),
            'my_group_nickname': member.nickname or None,
            'admin_count': ConversationMember.objects.filter(
                conversation=conv,
                role='admin',
                is_removed=False,
            ).count(),
            'latest_announcement': {
                'announcement_id': latest_announcement.id,
                'content': latest_announcement.content,
                'publisher': {
                    'user_id': latest_announcement.publisher_id,
                    'username': latest_announcement.publisher.username if latest_announcement.publisher else '[已注销用户]',
                },
                'created_at': latest_announcement.created_at.isoformat(),
            } if latest_announcement else None,
            'created_at': conv.created_at.isoformat(),
            'updated_at': conv.updated_at.isoformat(),
        })

    def put(self, request, conv_id):
        conv, member, error_response = _get_group_and_member(request.user, conv_id)
        if error_response:
            return error_response

        if member.role not in ('owner', 'admin'):
            return Response(_err('PERMISSION_DENIED', '非群主或管理员'), status=403)

        if 'name' not in request.data:
            return Response(_err('INVALID_PARAMS', '至少传入一个可更新字段'), status=400)

        name = str(request.data.get('name') or '').strip()
        if not name:
            return Response(_err('INVALID_PARAMS', '群名称不能为空'), status=400)
        if len(name) > 50:
            return Response(_err('INVALID_PARAMS', '群名称长度不能超过 50'), status=400)

        conv.name = name
        conv.save(update_fields=['name', 'updated_at'])

        Message.objects.create(
            conversation=conv,
            sender=request.user,
            type='system',
            content={
                'action': 'group_name_changed',
                'text': f'{request.user.username} 修改了群名称为 {name}',
            },
        )

        return Response({
            'conversation_id': conv.id,
            'name': conv.name,
            'updated_at': conv.updated_at.isoformat(),
        })

    def delete(self, request, conv_id):
        conv, member, error_response = _get_group_and_member(request.user, conv_id)
        if error_response:
            return error_response

        if member.role != 'owner':
            return Response(_err('NOT_OWNER', '非群主'), status=403)

        if request.data.get('confirm') is not True:
            return Response(_err('CONFIRM_REQUIRED', '必须传 confirm=true'), status=400)

        with transaction.atomic():
            Message.objects.create(
                conversation=conv,
                sender=request.user,
                type='system',
                content={
                    'action': 'group_dissolved',
                    'text': f'群主 {request.user.username} 解散了群聊',
                },
            )
            conv.is_dissolved = True
            conv.save(update_fields=['is_dissolved', 'updated_at'])
        send_to_conversation(conv.id, 'group_dissolved', {
            'conversation_id': conv.id,
            'conversation_name': conv.name,
            'dissolved_by': {'user_id': request.user.id, 'username': request.user.username},
            'timestamp': timezone.now().isoformat(),
        })

        return Response(status=204)


class GroupAvatarView(APIView):
    """6.3 上传群头像 — POST /api/conversations/{conv_id}/group/avatar"""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    ALLOWED_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
    MAX_SIZE = 5 * 1024 * 1024  # 5MB

    def post(self, request, conv_id):
        conv, member, error_response = _get_group_and_member(request.user, conv_id)
        if error_response:
            return error_response

        if member.role not in ('owner', 'admin'):
            return Response(_err('PERMISSION_DENIED', '非群主或管理员'), status=403)

        file = request.FILES.get('file')
        if not file:
            return Response(_err('INVALID_PARAMS', '缺少文件'), status=400)

        if file.content_type not in self.ALLOWED_TYPES:
            return Response(_err('INVALID_FILE_TYPE', '仅支持 jpg/png/gif/webp'), status=400)

        if file.size > self.MAX_SIZE:
            return Response(_err('FILE_TOO_LARGE', '文件不能超过 5MB'), status=400)

        ext = os.path.splitext(file.name)[1].lower() or '.jpg'
        filename = f'groups/{conv.id}{ext}'
        save_path = os.path.join(django_settings.MEDIA_ROOT, filename)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, 'wb') as f:
            for chunk in file.chunks():
                f.write(chunk)

        avatar_url = request.build_absolute_uri(django_settings.MEDIA_URL + filename)
        conv.avatar = avatar_url
        conv.save(update_fields=['avatar', 'updated_at'])
        return Response({'avatar': avatar_url})


# ---- 群成员 (6.4 - 6.5) ----

class GroupMemberListView(APIView):
    """6.4 获取群成员列表 — GET /api/conversations/{conv_id}/group/members"""
    permission_classes = [IsAuthenticated]

    def get(self, request, conv_id):
        conv, _, error_response = _get_group_and_member(request.user, conv_id)
        if error_response:
            return error_response

        page, page_size = _parse_pagination(request, default_size=50)
        qs = ConversationMember.objects.filter(
            conversation=conv,
            is_removed=False,
        ).select_related('user').order_by('joined_at')

        total = qs.count()
        offset = (page - 1) * page_size
        members = list(qs[offset:offset + page_size])

        member_user_ids = [item.user_id for item in members]
        remark_map = {
            fs.friend_id: fs.remark
            for fs in Friendship.objects.filter(
                user=request.user,
                friend_id__in=member_user_ids,
            )
        }

        results = []
        for item in members:
            user = item.user
            results.append({
                'user_id': user.id,
                'username': user.username,
                'avatar': user.avatar or None,
                'role': item.role,
                'group_nickname': item.nickname or None,
                'remark': remark_map.get(user.id) or None,
                'status': _status_payload(user),
                'joined_at': item.joined_at.isoformat(),
            })

        return Response({
            'total': total,
            'page': page,
            'page_size': page_size,
            'results': results,
        })


class GroupNicknameView(APIView):
    """6.5 设置群昵称 — PUT /api/conversations/{conv_id}/group/my-nickname"""
    permission_classes = [IsAuthenticated]

    def put(self, request, conv_id):
        _, member, error_response = _get_group_and_member(request.user, conv_id)
        if error_response:
            return error_response

        if 'nickname' not in request.data:
            return Response(_err('INVALID_PARAMS', '缺少 nickname'), status=400)

        nickname = str(request.data.get('nickname') or '').strip()
        if len(nickname) > 30:
            return Response(_err('INVALID_PARAMS', '群昵称长度不能超过 30'), status=400)

        member.nickname = nickname
        member.save(update_fields=['nickname'])
        return Response({
            'conversation_id': member.conversation_id,
            'user_id': request.user.id,
            'nickname': member.nickname,
            'updated_at': timezone.now().isoformat(),
        })


# ---- 管理员与群主 (6.6 - 6.8) ----

class GroupAdminView(APIView):
    """6.6 设置管理员 — POST /api/conversations/{conv_id}/group/admins"""
    permission_classes = [IsAuthenticated]

    def post(self, request, conv_id):
        conv, member, error_response = _get_group_and_member(request.user, conv_id)
        if error_response:
            return error_response

        if member.role != 'owner':
            return Response(_err('NOT_OWNER', '非群主'), status=403)

        raw_user_id = request.data.get('user_id')
        try:
            target_user_id = int(raw_user_id)
        except (TypeError, ValueError):
            return Response(_err('INVALID_PARAMS', 'user_id 必须为整数'), status=400)

        target_member = ConversationMember.objects.filter(
            conversation=conv,
            user_id=target_user_id,
            is_removed=False,
        ).select_related('user').first()
        if not target_member:
            return Response(_err('MEMBER_NOT_FOUND', '不是群成员'), status=404)

        if target_member.role == 'admin':
            return Response(_err('ALREADY_ADMIN', '已是管理员'), status=409)
        if target_member.role == 'owner':
            return Response(_err('INVALID_PARAMS', '群主无需设置为管理员'), status=400)

        target_member.role = 'admin'
        target_member.save(update_fields=['role'])

        Message.objects.create(
            conversation=conv,
            sender=request.user,
            type='system',
            content={
                'action': 'admin_set',
                'text': f'{target_member.user.username} 被设置为管理员',
            },
        )
        send_to_conversation(conv.id, 'group_member_change', {
            'conversation_id': conv.id,
            'action': 'role_changed',
            'user': {'user_id': target_member.user_id, 'username': target_member.user.username},
            'timestamp': timezone.now().isoformat(),
        })

        return Response({
            'user_id': target_member.user_id,
            'username': target_member.user.username,
            'role': target_member.role,
            'updated_at': timezone.now().isoformat(),
        })


class GroupAdminRemoveView(APIView):
    """6.7 取消管理员 — DELETE /api/conversations/{conv_id}/group/admins/{user_id}"""
    permission_classes = [IsAuthenticated]

    def delete(self, request, conv_id, user_id):
        conv, member, error_response = _get_group_and_member(request.user, conv_id)
        if error_response:
            return error_response

        if member.role != 'owner':
            return Response(_err('NOT_OWNER', '非群主'), status=403)

        target_member = ConversationMember.objects.filter(
            conversation=conv,
            user_id=user_id,
            is_removed=False,
        ).select_related('user').first()
        if not target_member:
            return Response(_err('MEMBER_NOT_FOUND', '不是群成员'), status=404)

        if target_member.role != 'admin':
            return Response(_err('NOT_ADMIN', '不是管理员'), status=409)

        target_member.role = 'member'
        target_member.save(update_fields=['role'])

        Message.objects.create(
            conversation=conv,
            sender=request.user,
            type='system',
            content={
                'action': 'admin_removed',
                'text': f'{target_member.user.username} 被取消管理员身份',
            },
        )
        send_to_conversation(conv.id, 'group_member_change', {
            'conversation_id': conv.id,
            'action': 'role_changed',
            'user': {'user_id': target_member.user_id, 'username': target_member.user.username},
            'timestamp': timezone.now().isoformat(),
        })
        return Response(status=204)


class GroupOwnerTransferView(APIView):
    """6.8 转让群主 — PUT /api/conversations/{conv_id}/group/owner"""
    permission_classes = [IsAuthenticated]

    def put(self, request, conv_id):
        conv, member, error_response = _get_group_and_member(request.user, conv_id)
        if error_response:
            return error_response

        if member.role != 'owner':
            return Response(_err('NOT_OWNER', '非群主'), status=403)

        raw_new_owner_id = request.data.get('new_owner_id')
        try:
            new_owner_id = int(raw_new_owner_id)
        except (TypeError, ValueError):
            return Response(_err('INVALID_PARAMS', 'new_owner_id 必须为整数'), status=400)

        new_owner_member = ConversationMember.objects.filter(
            conversation=conv,
            user_id=new_owner_id,
            is_removed=False,
        ).select_related('user').first()
        if not new_owner_member:
            return Response(_err('MEMBER_NOT_FOUND', '目标不是群成员'), status=404)

        if new_owner_member.user_id == request.user.id:
            return Response(_err('INVALID_PARAMS', 'new_owner_id 不能是自己'), status=400)

        with transaction.atomic():
            old_owner_id = request.user.id
            new_owner_member.role = 'owner'
            new_owner_member.save(update_fields=['role'])

            member.role = 'member'
            member.save(update_fields=['role'])

            conv.owner = new_owner_member.user
            conv.save(update_fields=['owner', 'updated_at'])

            Message.objects.create(
                conversation=conv,
                sender=request.user,
                type='system',
                content={
                    'action': 'owner_transferred',
                    'text': f'群主已转让给 {new_owner_member.user.username}',
                },
            )
        send_to_conversation(conv.id, 'group_member_change', {
            'conversation_id': conv.id,
            'action': 'role_changed',
            'user': {'user_id': new_owner_member.user_id, 'username': new_owner_member.user.username},
            'timestamp': timezone.now().isoformat(),
        })

        return Response({
            'conversation_id': conv.id,
            'old_owner_id': old_owner_id,
            'new_owner_id': new_owner_member.user_id,
            'updated_at': conv.updated_at.isoformat(),
        })


# ---- 成员移除与退出 (6.9 - 6.10) ----

class GroupMemberRemoveView(APIView):
    """6.9 移除群成员 — DELETE /api/conversations/{conv_id}/group/members/{user_id}"""
    permission_classes = [IsAuthenticated]

    def delete(self, request, conv_id, user_id):
        conv, member, error_response = _get_group_and_member(request.user, conv_id)
        if error_response:
            return error_response

        if user_id == request.user.id:
            return Response(_err('CANNOT_REMOVE_SELF', '不可移除自己，请使用退出接口'), status=403)

        target_member = ConversationMember.objects.filter(
            conversation=conv,
            user_id=user_id,
            is_removed=False,
        ).select_related('user').first()
        if not target_member:
            return Response(_err('MEMBER_NOT_FOUND', '不是群成员'), status=404)

        can_remove = False
        if member.role == 'owner':
            can_remove = target_member.role in ('admin', 'member')
        elif member.role == 'admin':
            can_remove = target_member.role == 'member'
        if not can_remove:
            return Response(_err('PERMISSION_DENIED', '无权移除该成员'), status=403)

        target_member.is_removed = True
        target_member.is_deleted = True
        target_member.save(update_fields=['is_removed', 'is_deleted'])

        Message.objects.create(
            conversation=conv,
            sender=request.user,
            type='system',
            content={
                'action': 'member_removed',
                'text': f'{target_member.user.username} 被移出了群聊',
            },
        )
        send_to_conversation(conv.id, 'group_member_change', {
            'conversation_id': conv.id,
            'action': 'removed',
            'user': {'user_id': target_member.user_id, 'username': target_member.user.username},
            'timestamp': timezone.now().isoformat(),
        })
        return Response(status=204)


class GroupLeaveView(APIView):
    """6.10 退出群聊 — POST /api/conversations/{conv_id}/group/leave"""
    permission_classes = [IsAuthenticated]

    def post(self, request, conv_id):
        conv, member, error_response = _get_group_and_member(request.user, conv_id)
        if error_response:
            return error_response

        if member.role == 'owner':
            return Response(_err('OWNER_CANNOT_LEAVE', '群主需先转让群主'), status=403)

        member.is_removed = True
        member.is_deleted = True
        member.save(update_fields=['is_removed', 'is_deleted'])

        Message.objects.create(
            conversation=conv,
            sender=request.user,
            type='system',
            content={
                'action': 'member_left',
                'text': f'{request.user.username} 退出了群聊',
            },
        )
        send_to_conversation(conv.id, 'group_member_change', {
            'conversation_id': conv.id,
            'action': 'left',
            'user': {'user_id': request.user.id, 'username': request.user.username},
            'timestamp': timezone.now().isoformat(),
        })
        return Response(status=204)


# ---- 入群邀请 (6.11 - 6.13) ----

class GroupInvitationListView(APIView):
    """
    6.11 邀请好友入群     — POST /api/conversations/{conv_id}/group/invitations
    6.12 获取入群申请列表 — GET /api/conversations/{conv_id}/group/invitations
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, conv_id):
        conv, _, error_response = _get_group_and_member(request.user, conv_id)
        if error_response:
            return error_response

        user_ids = request.data.get('user_ids')
        if not isinstance(user_ids, list) or not user_ids:
            return Response(_err('INVALID_PARAMS', 'user_ids 不能为空'), status=400)

        normalized_ids = []
        seen = set()
        for raw_id in user_ids:
            try:
                uid = int(raw_id)
            except (TypeError, ValueError):
                return Response(_err('INVALID_PARAMS', 'user_ids 包含无效用户 ID'), status=400)
            if uid <= 0 or uid == request.user.id or uid in seen:
                continue
            seen.add(uid)
            normalized_ids.append(uid)

        if not normalized_ids:
            return Response(_err('INVALID_PARAMS', 'user_ids 不能为空'), status=400)

        friend_ids = set(Friendship.objects.filter(
            user=request.user,
            friend_id__in=normalized_ids,
        ).values_list('friend_id', flat=True))

        for uid in normalized_ids:
            if uid not in friend_ids:
                return Response(_err('NOT_FRIEND', '被邀请者不是你的好友'), status=403)

            if ConversationMember.objects.filter(
                conversation=conv,
                user_id=uid,
                is_removed=False,
            ).exists():
                return Response(_err('ALREADY_MEMBER', '已是群成员'), status=409)

            if GroupInvitation.objects.filter(
                conversation=conv,
                invitee_id=uid,
                status='pending',
            ).exists():
                return Response(_err('INVITATION_EXISTS', '已有待处理邀请'), status=409)

        created = []
        invitee_map = {}
        for uid in normalized_ids:
            invitation = GroupInvitation.objects.create(
                conversation=conv,
                invitee_id=uid,
                inviter=request.user,
                status='pending',
            )
            created.append(invitation)
            invitee_map[uid] = invitation.invitee
        reviewer_ids = ConversationMember.objects.filter(
            conversation=conv,
            role__in=['owner', 'admin'],
            is_removed=False,
        ).values_list('user_id', flat=True)
        for invitation in created:
            event = {
                'invitation_id': invitation.id,
                'conversation_id': conv.id,
                'conversation_name': conv.name,
                'invitee': {
                    'user_id': invitation.invitee_id,
                    'username': invitee_map[invitation.invitee_id].username,
                },
                'inviter': {'user_id': request.user.id, 'username': request.user.username},
                'created_at': invitation.created_at.isoformat(),
            }
            for reviewer_id in reviewer_ids:
                send_to_user(reviewer_id, 'group_invitation', event)

        return Response({
            'invitations': [
                {
                    'invitation_id': item.id,
                    'conversation_id': item.conversation_id,
                    'user_id': item.invitee_id,
                    'username': invitee_map[item.invitee_id].username,
                    'invitee_id': item.invitee_id,
                    'inviter_id': item.inviter_id,
                    'status': item.status,
                    'created_at': item.created_at.isoformat(),
                }
                for item in created
            ],
        }, status=201)

    def get(self, request, conv_id):
        conv, member, error_response = _get_group_and_member(request.user, conv_id)
        if error_response:
            return error_response

        if member.role not in ('owner', 'admin'):
            return Response(_err('PERMISSION_DENIED', '非群主或管理员'), status=403)

        status_filter = (request.query_params.get('status') or 'pending').strip()
        valid_status = {'pending', 'approved', 'rejected', 'all'}
        if status_filter not in valid_status:
            return Response(_err('INVALID_PARAMS', 'status 仅支持 pending/approved/rejected/all'), status=400)

        page, page_size = _parse_pagination(request, default_size=20)
        qs = GroupInvitation.objects.filter(
            conversation=conv,
        ).select_related('inviter', 'invitee', 'reviewed_by').order_by('-created_at')
        if status_filter != 'all':
            qs = qs.filter(status=status_filter)

        total = qs.count()
        offset = (page - 1) * page_size
        invitations = qs[offset:offset + page_size]

        return Response({
            'total': total,
            'page': page,
            'page_size': page_size,
            'results': [
                {
                    'invitation_id': item.id,
                    'conversation_id': item.conversation_id,
                    'status': item.status,
                    'inviter': {
                        'user_id': item.inviter_id,
                        'username': item.inviter.username,
                    },
                    'invitee': {
                        'user_id': item.invitee_id,
                        'username': item.invitee.username,
                        'avatar': item.invitee.avatar or None,
                    },
                    'reviewed_by': {
                        'user_id': item.reviewed_by_id,
                        'username': item.reviewed_by.username,
                    } if item.reviewed_by else None,
                    'created_at': item.created_at.isoformat(),
                    'updated_at': item.updated_at.isoformat(),
                }
                for item in invitations
            ],
        })


class GroupInvitationHandleView(APIView):
    """6.13 审核入群申请 — PUT /api/conversations/{conv_id}/group/invitations/{invitation_id}"""
    permission_classes = [IsAuthenticated]

    def put(self, request, conv_id, invitation_id):
        conv, member, error_response = _get_group_and_member(request.user, conv_id)
        if error_response:
            return error_response

        if member.role not in ('owner', 'admin'):
            return Response(_err('PERMISSION_DENIED', '非群主或管理员'), status=403)

        invitation = GroupInvitation.objects.filter(
            pk=invitation_id,
            conversation=conv,
        ).select_related('inviter', 'invitee').first()
        if not invitation:
            return Response(_err('INVITATION_NOT_FOUND', '邀请不存在'), status=404)

        if invitation.status != 'pending':
            return Response(_err('INVITATION_ALREADY_HANDLED', '邀请已处理'), status=409)

        action = (request.data.get('action') or '').strip()
        if action not in ('approve', 'reject'):
            return Response(_err('INVALID_PARAMS', 'action 仅支持 approve/reject'), status=400)

        with transaction.atomic():
            if action == 'approve':
                membership = ConversationMember.objects.filter(
                    conversation=conv,
                    user=invitation.invitee,
                ).first()
                if membership:
                    membership.is_deleted = False
                    membership.is_removed = False
                    membership.role = 'member'
                    membership.save(update_fields=['is_deleted', 'is_removed', 'role'])
                else:
                    ConversationMember.objects.create(
                        conversation=conv,
                        user=invitation.invitee,
                        role='member',
                    )

                invitation.status = 'approved'
                invitation.reviewed_by = request.user
                invitation.save(update_fields=['status', 'reviewed_by', 'updated_at'])

                Message.objects.create(
                    conversation=conv,
                    sender=request.user,
                    type='system',
                    content={
                        'action': 'member_joined',
                        'text': f'{invitation.invitee.username} 通过 {invitation.inviter.username} 的邀请加入了群聊',
                    },
                )
                send_to_conversation(conv.id, 'group_member_change', {
                    'conversation_id': conv.id,
                    'action': 'joined',
                    'user': {'user_id': invitation.invitee_id, 'username': invitation.invitee.username},
                    'timestamp': timezone.now().isoformat(),
                })
            else:
                invitation.status = 'rejected'
                invitation.reviewed_by = request.user
                invitation.save(update_fields=['status', 'reviewed_by', 'updated_at'])
        send_to_user(invitation.invitee_id, 'group_invitation_result', {
            'invitation_id': invitation.id,
            'conversation_id': conv.id,
            'conversation_name': conv.name,
            'status': invitation.status,
            'updated_at': invitation.updated_at.isoformat(),
        })

        return Response({
            'invitation_id': invitation.id,
            'status': invitation.status,
            'reviewed_by': {
                'user_id': request.user.id,
                'username': request.user.username,
            },
            'updated_at': invitation.updated_at.isoformat(),
        })


# ---- 群公告 (6.14 - 6.15) ----

class GroupAnnouncementListView(APIView):
    """
    6.14 发布群公告     — POST /api/conversations/{conv_id}/group/announcements
    6.15 获取历史群公告 — GET /api/conversations/{conv_id}/group/announcements
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, conv_id):
        conv, member, error_response = _get_group_and_member(request.user, conv_id)
        if error_response:
            return error_response

        if member.role not in ('owner', 'admin'):
            return Response(_err('PERMISSION_DENIED', '非群主或管理员'), status=403)

        content = str(request.data.get('content') or '').strip()
        if not content:
            return Response(_err('EMPTY_CONTENT', '公告内容不能为空'), status=400)
        if len(content) > 2000:
            return Response(_err('INVALID_PARAMS', '公告长度不能超过 2000'), status=400)

        announcement = GroupAnnouncement.objects.create(
            conversation=conv,
            publisher=request.user,
            content=content,
        )
        send_to_conversation(conv.id, 'group_announcement', {
            'conversation_id': conv.id,
            'announcement_id': announcement.id,
            'content': announcement.content,
            'publisher': {'user_id': request.user.id, 'username': request.user.username},
            'created_at': announcement.created_at.isoformat(),
        })
        return Response({
            'announcement_id': announcement.id,
            'conversation_id': announcement.conversation_id,
            'content': announcement.content,
            'publisher': {
                'user_id': request.user.id,
                'username': request.user.username,
            },
            'created_at': announcement.created_at.isoformat(),
        }, status=201)

    def get(self, request, conv_id):
        conv, _, error_response = _get_group_and_member(request.user, conv_id)
        if error_response:
            return error_response

        page, page_size = _parse_pagination(request, default_size=10)
        qs = GroupAnnouncement.objects.filter(
            conversation=conv,
        ).select_related('publisher').order_by('-created_at')

        total = qs.count()
        offset = (page - 1) * page_size
        announcements = qs[offset:offset + page_size]

        return Response({
            'total': total,
            'page': page,
            'page_size': page_size,
            'results': [
                {
                    'announcement_id': item.id,
                    'content': item.content,
                    'publisher': {
                        'user_id': item.publisher_id,
                        'username': item.publisher.username if item.publisher else '[已注销用户]',
                    },
                    'created_at': item.created_at.isoformat(),
                }
                for item in announcements
            ],
        })
