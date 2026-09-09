"""
chat/views/friends.py
好友关系模块：好友申请、好友列表、分组、备注、黑名单、白名单

对应接口：3.1 - 3.16
负责人：同学 A
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db.models import Count

from chat.models import (
    User, UserPrivacy, Friendship, FriendRequest, FriendGroup,
    Blacklist, Whitelist, ConversationMember,
)
from chat.realtime import send_to_user


def _err(code, message):
    return {'error': {'code': code, 'message': message}}


def _normalize_group_name(raw_name):
    return str(raw_name or '').strip()


def _parse_id_list(value):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError('必须是数组')

    ids = []
    for item in value:
        try:
            fid = int(item)
        except (TypeError, ValueError):
            raise ValueError('数组元素必须是整数')
        if fid > 0:
            ids.append(fid)

    # 去重并保持原顺序
    seen = set()
    deduped = []
    for fid in ids:
        if fid not in seen:
            seen.add(fid)
            deduped.append(fid)
    return deduped


# ---- 好友申请 (3.1 - 3.3) ----

class FriendRequestSendView(APIView):
    """3.1 发送好友申请 — POST /api/friends/request"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        target_id = request.data.get('target_user_id')
        if not target_id:
            return Response(_err('INVALID_PARAMS', '缺少 target_user_id'), status=400)

        try:
            target = User.objects.get(pk=target_id, is_active=True)
        except User.DoesNotExist:
            return Response(_err('USER_NOT_FOUND', '用户不存在'), status=404)

        me = request.user
        if target == me:
            return Response(_err('SELF_REQUEST', '不能添加自己为好友'), status=400)

        # 黑名单检查
        if Blacklist.objects.filter(user=target, blocked_user=me).exists():
            return Response(_err('USER_BLOCKED', '你已被对方拉黑'), status=403)

        source = request.data.get('source', 'search') or 'search'
        is_whitelisted = Whitelist.objects.filter(user=target, whitelisted_user=me).exists()
        if not is_whitelisted and source.startswith('group:'):
            try:
                conversation_id = int(source.split(':', 1)[1])
            except (IndexError, TypeError, ValueError):
                return Response(_err('INVALID_PARAMS', '群聊来源格式不合法'), status=400)
            both_in_group = ConversationMember.objects.filter(
                conversation_id=conversation_id,
                user__in=[me, target],
                conversation__type='group',
                conversation__is_dissolved=False,
                is_removed=False,
            ).count() == 2
            if not both_in_group:
                return Response(_err('PRIVACY_DENIED', '无法通过该群聊添加好友'), status=403)
            privacy, _ = UserPrivacy.objects.get_or_create(user=target)
            if not privacy.allow_add_from_group:
                return Response(_err('PRIVACY_DENIED', '对方不允许通过群聊添加好友'), status=403)

        # 已是好友
        if Friendship.objects.filter(user=me, friend=target).exists():
            return Response(_err('ALREADY_FRIENDS', '已经是好友了'), status=409)

        # 已有 pending 申请
        if FriendRequest.objects.filter(from_user=me, to_user=target, status='pending').exists():
            return Response(_err('REQUEST_EXISTS', '申请已发送，等待对方处理'), status=409)

        message = request.data.get('message', '')
        freq = FriendRequest.objects.create(
            from_user=me,
            to_user=target,
            message=message,
            source=source,
        )
        send_to_user(target.id, 'friend_request', {
            'request_id': freq.id,
            'from_user': {
                'user_id': me.id,
                'username': me.username,
                'avatar': me.avatar or None,
            },
            'message': freq.message,
            'source': freq.source,
            'created_at': freq.created_at.isoformat(),
        })
        return Response({
            'request_id': freq.id,
            'from_user_id': me.id,
            'to_user_id': target.id,
            'message': freq.message,
            'source': freq.source,
            'status': freq.status,
            'created_at': freq.created_at.isoformat(),
        }, status=201)


class FriendRequestListView(APIView):
    """3.2 获取好友申请列表 — GET /api/friends/requests"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        req_type = request.query_params.get('type', 'received')  # received / sent
        req_status = request.query_params.get('status', 'pending')  # pending/accepted/rejected/all
        if req_type not in ('received', 'sent'):
            return Response(_err('INVALID_PARAMS', 'type 须为 received 或 sent'), status=400)
        if req_status not in ('pending', 'accepted', 'rejected', 'all'):
            return Response(_err('INVALID_PARAMS', 'status 参数不合法'), status=400)

        try:
            page = max(1, int(request.query_params.get('page', 1)))
            page_size = min(100, max(1, int(request.query_params.get('page_size', 20))))
        except (TypeError, ValueError):
            return Response(_err('INVALID_PARAMS', 'page/page_size 必须为整数'), status=400)

        if req_type == 'received':
            qs = FriendRequest.objects.filter(to_user=request.user)
        else:
            qs = FriendRequest.objects.filter(from_user=request.user)

        if req_status != 'all':
            qs = qs.filter(status=req_status)

        qs = qs.order_by('-created_at')
        total = qs.count()
        offset = (page - 1) * page_size
        results = qs.select_related('from_user', 'to_user')[offset:offset + page_size]

        return Response({
            'total': total,
            'page': page,
            'page_size': page_size,
            'results': [
                {
                    'request_id': r.id,
                    'from_user': {
                        'user_id': r.from_user_id,
                        'username': r.from_user.username,
                        'avatar': r.from_user.avatar or None,
                    },
                    'to_user': {
                        'user_id': r.to_user_id,
                        'username': r.to_user.username,
                        'avatar': r.to_user.avatar or None,
                    },
                    'from_user_id': r.from_user_id,
                    'from_username': r.from_user.username,
                    'from_avatar': r.from_user.avatar or None,
                    'to_user_id': r.to_user_id,
                    'to_username': r.to_user.username,
                    'to_avatar': r.to_user.avatar or None,
                    'source': r.source,
                    'message': r.message,
                    'status': r.status,
                    'created_at': r.created_at.isoformat(),
                }
                for r in results
            ],
        })


class FriendRequestHandleView(APIView):
    """3.3 处理好友申请 — PUT /api/friends/requests/{request_id}"""
    permission_classes = [IsAuthenticated]

    def put(self, request, request_id):
        action = request.data.get('action', '')  # accept / reject
        if action not in ('accept', 'reject'):
            return Response(_err('INVALID_PARAMS', 'action 须为 accept 或 reject'), status=400)

        try:
            freq = FriendRequest.objects.select_related('from_user', 'to_user').get(pk=request_id)
        except FriendRequest.DoesNotExist:
            return Response(_err('REQUEST_NOT_FOUND', '申请不存在'), status=404)

        if freq.to_user_id != request.user.id:
            return Response(_err('NOT_RECIPIENT', '只有接收方可以处理'), status=403)
        if freq.status != 'pending':
            return Response(_err('REQUEST_ALREADY_HANDLED', '申请已处理过'), status=409)

        if action == 'accept':
            freq.status = 'accepted'
            freq.save(update_fields=['status'])
            # 创建双向好友关系
            Friendship.objects.get_or_create(user=freq.from_user, friend=freq.to_user)
            Friendship.objects.get_or_create(user=freq.to_user, friend=freq.from_user)
        else:
            freq.status = 'rejected'
            freq.save(update_fields=['status'])
        event = {
            'request_id': freq.id,
            'status': freq.status,
            'friend': {
                'user_id': freq.to_user_id,
                'username': freq.to_user.username,
                'avatar': freq.to_user.avatar or None,
            },
            'updated_at': freq.updated_at.isoformat(),
        }
        send_to_user(freq.from_user_id, 'friend_request_result', event)
        send_to_user(freq.to_user_id, 'friend_request_result', event)

        return Response({
            'request_id': freq.id,
            'status': freq.status,
            'updated_at': freq.updated_at.isoformat(),
        })


# ---- 好友列表与删除 (3.4 - 3.5) ----

class FriendListView(APIView):
    """3.4 获取好友列表 — GET /api/friends"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        page = max(1, int(request.query_params.get('page', 1)))
        page_size = min(100, max(1, int(request.query_params.get('page_size', 20))))

        qs = Friendship.objects.filter(user=request.user).select_related('friend', 'group')
        total = qs.count()
        offset = (page - 1) * page_size
        results = qs[offset:offset + page_size]
        blocked_friend_ids = set(Blacklist.objects.filter(
            user=request.user,
            blocked_user_id__in=[fs.friend_id for fs in results],
        ).values_list('blocked_user_id', flat=True))

        return Response({
            'total': total,
            'page': page,
            'page_size': page_size,
            'results': [
                {
                    'user_id': fs.friend.id,
                    'username': fs.friend.username,
                    'avatar': fs.friend.avatar or None,
                    'remark': fs.remark,
                    'group_id': fs.group_id,
                    'group_name': fs.group.name if fs.group else None,
                    'is_blocked': fs.friend_id in blocked_friend_ids,
                    'added_at': fs.created_at.isoformat(),
                    'status': {
                        'presence': fs.friend.presence,
                        'status_text': fs.friend.status_text or '',
                        'status_emoji': fs.friend.status_emoji or '',
                    },
                }
                for fs in results
            ],
        })


class FriendDeleteView(APIView):
    """3.5 删除好友 — DELETE /api/friends/{friend_user_id}"""
    permission_classes = [IsAuthenticated]

    def delete(self, request, friend_user_id):
        deleted, _ = Friendship.objects.filter(
            user=request.user, friend_id=friend_user_id
        ).delete()
        if not deleted:
            return Response(_err('NOT_FOUND', '好友关系不存在'), status=404)
        # 删除反向关系
        Friendship.objects.filter(user_id=friend_user_id, friend=request.user).delete()
        return Response(status=204)


# ---- 好友分组 (3.6 - 3.9) ----

class FriendGroupListView(APIView):
    """
    3.6 获取好友分组列表 — GET /api/friends/groups
    3.7 创建好友分组     — POST /api/friends/groups
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        groups = FriendGroup.objects.filter(user=request.user).order_by('name')
        friend_counts = {
            row['group_id']: row['cnt']
            for row in Friendship.objects.filter(user=request.user).values('group_id').annotate(cnt=Count('id'))
        }
        ungrouped_count = friend_counts.get(None, 0)
        return Response({
            'groups': [
                {
                    'group_id': g.id,
                    'name': g.name,
                    'friend_count': friend_counts.get(g.id, 0),
                }
                for g in groups
            ],
            'ungrouped_count': ungrouped_count,
        })

    def post(self, request):
        name = _normalize_group_name(request.data.get('name'))
        if not name:
            return Response(_err('INVALID_PARAMS', '缺少分组名'), status=400)
        if len(name) > 50:
            return Response(_err('INVALID_PARAMS', '分组名不能超过 50 字'), status=400)

        if FriendGroup.objects.filter(user=request.user, name__iexact=name).exists():
            return Response(_err('GROUP_NAME_EXISTS', '分组名已存在'), status=409)

        group = FriendGroup.objects.create(user=request.user, name=name)
        return Response({'group_id': group.id, 'name': group.name, 'friend_count': 0}, status=201)


class FriendGroupDetailView(APIView):
    """
    3.8 修改好友分组 — PUT /api/friends/groups/{group_id}
    3.9 删除好友分组 — DELETE /api/friends/groups/{group_id}
    """
    permission_classes = [IsAuthenticated]

    def put(self, request, group_id):
        try:
            group = FriendGroup.objects.get(pk=group_id, user=request.user)
        except FriendGroup.DoesNotExist:
            return Response(_err('GROUP_NOT_FOUND', '分组不存在'), status=404)

        if 'name' in request.data:
            new_name = _normalize_group_name(request.data.get('name'))
            if not new_name:
                return Response(_err('INVALID_PARAMS', '分组名不能为空'), status=400)
            if len(new_name) > 50:
                return Response(_err('INVALID_PARAMS', '分组名不能超过 50 字'), status=400)
            if FriendGroup.objects.exclude(pk=group.pk).filter(user=request.user, name__iexact=new_name).exists():
                return Response(_err('GROUP_NAME_EXISTS', '分组名已存在'), status=409)
            group.name = new_name
            group.save(update_fields=['name'])

        try:
            add_friend_ids = _parse_id_list(request.data.get('add_friend_ids'))
            remove_friend_ids = _parse_id_list(request.data.get('remove_friend_ids'))
        except ValueError as exc:
            return Response(_err('INVALID_PARAMS', f'分组好友列表参数错误：{exc}'), status=400)

        # add/remove 同时出现时，add 优先
        remove_friend_ids = [fid for fid in remove_friend_ids if fid not in set(add_friend_ids)]

        # 将好友加入分组
        if add_friend_ids:
            my_friend_ids = set(
                Friendship.objects.filter(user=request.user, friend_id__in=add_friend_ids)
                .values_list('friend_id', flat=True)
            )
            missing = [fid for fid in add_friend_ids if fid not in my_friend_ids]
            if missing:
                return Response(_err('FRIEND_NOT_FOUND', f'以下用户不是你的好友：{missing}'), status=404)

            Friendship.objects.filter(user=request.user, friend_id__in=add_friend_ids).update(group=group)

        # 将好友移出分组（设为未分组）
        if remove_friend_ids:
            my_friend_ids = set(
                Friendship.objects.filter(user=request.user, friend_id__in=remove_friend_ids)
                .values_list('friend_id', flat=True)
            )
            missing = [fid for fid in remove_friend_ids if fid not in my_friend_ids]
            if missing:
                return Response(_err('FRIEND_NOT_FOUND', f'以下用户不是你的好友：{missing}'), status=404)

            Friendship.objects.filter(user=request.user, friend_id__in=remove_friend_ids, group=group).update(group=None)

        friend_count = Friendship.objects.filter(user=request.user, group=group).count()
        return Response({'group_id': group.id, 'name': group.name, 'friend_count': friend_count})

    def delete(self, request, group_id):
        try:
            group = FriendGroup.objects.get(pk=group_id, user=request.user)
        except FriendGroup.DoesNotExist:
            return Response(_err('GROUP_NOT_FOUND', '分组不存在'), status=404)

        # 该分组下的好友变为未分组
        Friendship.objects.filter(user=request.user, group=group).update(group=None)
        group.delete()
        return Response(status=204)


# ---- 好友备注 (3.10) ----

class FriendRemarkView(APIView):
    """3.10 设置好友备注 — PUT /api/friends/{friend_user_id}/remark"""
    permission_classes = [IsAuthenticated]

    def put(self, request, friend_user_id):
        try:
            fs = Friendship.objects.get(user=request.user, friend_id=friend_user_id)
        except Friendship.DoesNotExist:
            return Response(_err('NOT_FOUND', '好友关系不存在'), status=404)

        remark = request.data.get('remark', '').strip()
        if len(remark) > 30:
            return Response(_err('INVALID_PARAMS', '备注不超过 30 字'), status=400)

        fs.remark = remark
        fs.save(update_fields=['remark'])
        return Response({'friend_user_id': friend_user_id, 'remark': fs.remark})


# ---- 黑名单 (3.11 - 3.13) ----

class BlacklistView(APIView):
    """
    3.11 拉入黑名单   — POST /api/friends/blacklist
    3.13 获取黑名单列表 — GET /api/friends/blacklist
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        page = max(1, int(request.query_params.get('page', 1)))
        page_size = min(100, max(1, int(request.query_params.get('page_size', 20))))
        qs = Blacklist.objects.filter(user=request.user).select_related('blocked_user')
        total = qs.count()
        offset = (page - 1) * page_size
        results = qs[offset:offset + page_size]
        return Response({
            'total': total,
            'page': page,
            'page_size': page_size,
            'results': [
                {
                    'user_id': b.blocked_user.id,
                    'username': b.blocked_user.username,
                    'avatar': b.blocked_user.avatar or None,
                    'blocked_at': b.created_at.isoformat(),
                }
                for b in results
            ],
        })

    def post(self, request):
        target_id = request.data.get('user_id')
        if not target_id:
            return Response(_err('INVALID_PARAMS', '缺少 user_id'), status=400)

        try:
            target = User.objects.get(pk=target_id, is_active=True)
        except User.DoesNotExist:
            return Response(_err('USER_NOT_FOUND', '用户不存在'), status=404)

        if target == request.user:
            return Response(_err('SELF_BLOCK', '不能拉黑自己'), status=400)

        item, created = Blacklist.objects.get_or_create(
            user=request.user, blocked_user=target
        )
        if not created:
            return Response(_err('ALREADY_BLOCKED', '已在黑名单'), status=409)

        return Response({
            'user_id': target.id,
            'username': target.username,
            'blocked_at': item.created_at.isoformat(),
        }, status=201)


class BlacklistRemoveView(APIView):
    """3.12 解除黑名单 — DELETE /api/friends/blacklist/{user_id}"""
    permission_classes = [IsAuthenticated]

    def delete(self, request, user_id):
        deleted, _ = Blacklist.objects.filter(
            user=request.user, blocked_user_id=user_id
        ).delete()
        if not deleted:
            return Response(_err('NOT_IN_BLACKLIST', '该用户不在黑名单中'), status=404)
        return Response(status=204)


# ---- 白名单 (3.14 - 3.16) ----

class WhitelistView(APIView):
    """
    3.14 添加白名单   — POST /api/friends/whitelist
    3.16 获取白名单列表 — GET /api/friends/whitelist
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        page = max(1, int(request.query_params.get('page', 1)))
        page_size = min(100, max(1, int(request.query_params.get('page_size', 20))))
        qs = Whitelist.objects.filter(user=request.user).select_related('whitelisted_user')
        total = qs.count()
        offset = (page - 1) * page_size
        results = qs[offset:offset + page_size]
        return Response({
            'total': total,
            'page': page,
            'page_size': page_size,
            'results': [
                {
                    'user_id': w.whitelisted_user.id,
                    'username': w.whitelisted_user.username,
                    'avatar': w.whitelisted_user.avatar or None,
                    'added_at': w.created_at.isoformat(),
                }
                for w in results
            ],
        })

    def post(self, request):
        target_id = request.data.get('user_id')
        if not target_id:
            return Response(_err('INVALID_PARAMS', '缺少 user_id'), status=400)

        try:
            target = User.objects.get(pk=target_id, is_active=True)
        except User.DoesNotExist:
            return Response(_err('USER_NOT_FOUND', '用户不存在'), status=404)

        if target == request.user:
            return Response(_err('INVALID_PARAMS', '不能将自己加入白名单'), status=400)

        item, created = Whitelist.objects.get_or_create(
            user=request.user, whitelisted_user=target
        )
        return Response({
            'user_id': target.id,
            'username': target.username,
            'added_at': item.created_at.isoformat(),
        }, status=201 if created else 200)


class WhitelistRemoveView(APIView):
    """3.15 移除白名单 — DELETE /api/friends/whitelist/{user_id}"""
    permission_classes = [IsAuthenticated]

    def delete(self, request, user_id):
        deleted, _ = Whitelist.objects.filter(
            user=request.user, whitelisted_user_id=user_id
        ).delete()
        if not deleted:
            return Response(_err('NOT_FOUND', '该用户不在白名单中'), status=404)
        return Response(status=204)
