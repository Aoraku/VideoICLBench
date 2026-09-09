import json
import re
import time

from django.contrib.auth.models import User
from django.http import JsonResponse

from .jwt_utils import decode_jwt
from .models import RevokedToken, UserProfile

USERNAME_RE = re.compile(r"^\w{1,50}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def json_body(request):
    if not request.body:
        return {}
    
    body_str = request.body.decode('utf-8')
    
    max_depth = 600
    current_depth = 0
    for char in body_str:
        if char in '[{':
            current_depth += 1
        elif char in ']}':
            current_depth -= 1
        if current_depth > max_depth:
            raise ValueError("JSON nesting too deep")

    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError("Invalid JSON")
        return data
    except (json.JSONDecodeError, ValueError):
        raise ValueError("Invalid JSON")

def error_response(code, info, status):
    return JsonResponse({"code": code, "info": info}, status=status)

def success_response(data=None, status=200):
    payload = {"code": 0, "info": "Succeed"}
    if data:
        payload.update(data)
    return JsonResponse(payload, status=status)

def bad_method_response():
    return error_response(-3, "Bad method", 405)

def invalid_field_response(field_name):
    return error_response(-2, f"Invalid field: {field_name}", 400)

def get_bearer_token(request):
    header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not header.startswith(prefix):
        return None
    return header[len(prefix):].strip()

def authenticate_request(request):
    token = get_bearer_token(request)
    if not token:
        return None
    try:
        payload = decode_jwt(token)
    except ValueError:
        return None

    if RevokedToken.objects.filter(jti=payload["jti"]).exists():
        return None

    try:
        user = User.objects.get(id=payload["sub"])
    except User.DoesNotExist:
        return None

    request.auth_token = token
    request.auth_payload = payload
    request.user = user
    return user

def auth_error_response():
    return error_response(-1, "Invalid or expired JWT", 401)

def ensure_profile(user):
    profile, _ = UserProfile.objects.get_or_create(
        user=user,
        defaults={"created_at": time.time()},
    )
    return profile

def validate_username(username):
    if not isinstance(username, str):
        return False
    # Explicitly reject any whitespace to keep validation behavior deterministic.
    if any(ch.isspace() for ch in username):
        return False
    return bool(USERNAME_RE.fullmatch(username))

def validate_password(password):
    return isinstance(password, str) and 6 <= len(password) <= 20

def validate_email(email):
    return isinstance(email, str) and bool(EMAIL_RE.fullmatch(email))

def validate_phone(phone):
    return isinstance(phone, str) and len(phone) <= 20

def validate_avatar(avatar):
    return isinstance(avatar, str)

# Group name validation: alphanumeric, chinese characters, spaces, and hyphens/underscores (1-30 chars)
GROUP_NAME_RE = re.compile(r"^[\w\u4e00-\u9fa5\s\-]{1,30}$")

def validate_group_name(name):
    if not isinstance(name, str):
        return False
    name = name.strip()
    return bool(GROUP_NAME_RE.fullmatch(name))
