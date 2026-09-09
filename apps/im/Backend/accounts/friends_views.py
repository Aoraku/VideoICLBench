import json
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
from .models import Friend, FriendGroup, FriendRequest
from .utils import (
    authenticate_request,
    auth_error_response,
    invalid_field_response,
    bad_method_response,
    error_response,
    invalid_field_response,
    success_response,
    json_body,
    ensure_profile,
    validate_group_name,
)
import time

@csrf_exempt
def friends_view(request):
    if request.method != "GET":
        return bad_method_response()
    user = authenticate_request(request)
    if not user:
        return auth_error_response()
    
    friends = Friend.objects.filter(user=user)
    friends_list = []
    for f in friends:
        friend_user = f.friend_user
        profile = ensure_profile(friend_user)
        friends_list.append({
            "user_id": friend_user.id,
            "username": friend_user.username,
            "avatar": profile.avatar if profile else "",
            "group": f.group.name if f.group else "默认分组",
            "online": True  # mock
        })
    return success_response({"friends": friends_list})

@csrf_exempt
def manage_groups(request):
    user = authenticate_request(request)
    if not user:
        return auth_error_response()
        
    if request.method == "GET":
        groups = FriendGroup.objects.filter(user=user)
        return success_response({"groups": ["默认分组"] + [g.name for g in groups]})
        
    elif request.method == "POST":
        try:
            data = json_body(request)
        except ValueError:
            return error_response(-2, "Invalid JSON", 400)
        name = data.get("group_name")
        if not validate_group_name(name): return invalid_field_response("group_name")
        name = name.strip()
        
        if name == "默认分组" or FriendGroup.objects.filter(user=user, name=name).exists():
            return error_response(1, "Group already exists", 409)
            
        FriendGroup.objects.create(user=user, name=name)
        return success_response({})
        
    elif request.method == "PUT":
        try:
            data = json_body(request)
        except ValueError:
            return error_response(-2, "Invalid JSON", 400)
        friend_id = data.get("friend_id")
        name = data.get("group_name")
        if not isinstance(friend_id, int): return invalid_field_response("friend_id")
        if not validate_group_name(name): return invalid_field_response("group_name")
        name = name.strip()

        try:
            friend_record = Friend.objects.get(user=user, friend_user_id=friend_id)
        except Friend.DoesNotExist:
            return error_response(1, "Friend not found", 404)
            
        if name == "默认分组":
            friend_record.group = None
        else:
            try:
                group = FriendGroup.objects.get(user=user, name=name)
                friend_record.group = group
            except FriendGroup.DoesNotExist:
                return error_response(2, "Group not found", 404)
                
        friend_record.save()
        return success_response({})
        
    elif request.method == "DELETE":
        try:
            data = json_body(request)
        except ValueError:
            return error_response(-2, "Invalid JSON", 400)
        name = data.get("group_name")
        if not validate_group_name(name): return invalid_field_response("group_name")
        name = name.strip()
        if name == "默认分组":
            return error_response(-2, "Cannot delete default group", 400)
            
        try:
            group = FriendGroup.objects.get(user=user, name=name)
            # friends in this group will have group set to NULL (default)
            group.delete()
            return success_response({})
        except FriendGroup.DoesNotExist:
            return error_response(3, "Group not found", 404)
            
    return bad_method_response()

@csrf_exempt
def manage_requests(request):
    user = authenticate_request(request)
    if not user:
        return auth_error_response()
        
    if request.method == "GET":
        received_reqs = FriendRequest.objects.filter(to_user=user, status="pending")
        sent_reqs = FriendRequest.objects.filter(
            from_user=user,
            status__in=["pending", "accepted", "rejected"],
        ).order_by("-created_at", "-id")

        received_list = []
        for r in received_reqs:
            from_profile = ensure_profile(r.from_user)
            received_list.append({
                "request_id": r.id,
                "from_user": {
                    "user_id": r.from_user.id,
                    "username": r.from_user.username,
                    "avatar": from_profile.avatar if from_profile else ""
                },
                "to_user": {
                    "user_id": r.to_user.id,
                    "username": r.to_user.username,
                },
                "message": r.message,
                "source": r.source,
                "status": r.status,
                "direction": "received",
                "created_at": r.created_at
            })

        sent_list = []
        for r in sent_reqs:
            to_profile = ensure_profile(r.to_user)
            sent_list.append({
                "request_id": r.id,
                "from_user": {
                    "user_id": r.from_user.id,
                    "username": r.from_user.username,
                },
                "to_user": {
                    "user_id": r.to_user.id,
                    "username": r.to_user.username,
                    "avatar": to_profile.avatar if to_profile else ""
                },
                "message": r.message,
                "source": r.source,
                "status": r.status,
                "direction": "sent",
                "created_at": r.created_at
            })

        # Keep "requests" for backward compatibility (same as previous incoming pending list).
        return success_response({
            "requests": received_list,
            "received_requests": received_list,
            "sent_requests": sent_list,
        })
        
    elif request.method == "POST":
        try:
            data = json_body(request)
        except ValueError:
            return error_response(-2, "Invalid JSON", 400)
        to_user_id = data.get("to_user_id")
        message = data.get("message", "")
        source = data.get("source", "search")

        if not isinstance(to_user_id, int): return invalid_field_response("to_user_id")
        if not isinstance(message, str): message = ""
        if source not in ("search", "group"): source = "search"

        if to_user_id == user.id:
            return error_response(-2, "Cannot add yourself", 400)

        try:
            to_user = User.objects.get(id=to_user_id)
        except User.DoesNotExist:
            return error_response(1, "User not found", 404)
            
        if Friend.objects.filter(user=user, friend_user=to_user).exists():
            return error_response(2, "Already friends", 409)
            
        if FriendRequest.objects.filter(from_user=user, to_user=to_user, status="pending").exists():
            return error_response(3, "Request already sent", 409)
            
        FriendRequest.objects.create(
            from_user=user, 
            to_user=to_user, 
            message=message, 
            source=source, 
            status="pending",
            created_at=time.time()
        )
        return success_response({})
        
    elif request.method == "PUT":
        try:
            data = json_body(request)
        except ValueError:
            return error_response(-2, "Invalid JSON", 400)
        req_id = data.get("request_id")
        action = data.get("action")

        if not isinstance(req_id, int): return invalid_field_response("request_id")
        if action not in ("accept", "reject"): return error_response(-2, "Invalid action", 400)

        try:
            freq = FriendRequest.objects.get(id=req_id, to_user=user, status="pending")
        except FriendRequest.DoesNotExist:
            return error_response(1, "Request not found", 404)

        if action == "accept":
            freq.status = "accepted"
            Friend.objects.get_or_create(user=user, friend_user=freq.from_user)
            Friend.objects.get_or_create(user=freq.from_user, friend_user=user)
        else:
            freq.status = "rejected"

        freq.save()
        return success_response({})
        
    return bad_method_response()

@csrf_exempt
def delete_friend(request, friend_id):
    if request.method != "DELETE":
        return bad_method_response()
        
    user = authenticate_request(request)
    if not user:
        return auth_error_response()
        
    deleted, _ = Friend.objects.filter(user=user, friend_user_id=friend_id).delete()
    if not deleted:
        return error_response(1, "Friend not found", 404)

    Friend.objects.filter(user_id=friend_id, friend_user=user).delete()
    
    return success_response({})
