import random
import time

from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .jwt_utils import generate_jwt
from .models import EmailVerificationCode, RevokedToken
from .utils import (
    auth_error_response,
    authenticate_request,
    bad_method_response,
    ensure_profile,
    error_response,
    invalid_field_response,
    json_body,
    success_response,
    validate_avatar,
    validate_email,
    validate_password,
    validate_phone,
    validate_username,
)

VERIFICATION_EXPIRE_SECONDS = 10 * 60

@transaction.atomic
def _register_user(username, password, email):
    user = User.objects.create_user(username=username, password=password, email=email)
    ensure_profile(user)
    token = generate_jwt(user.id)
    
    return success_response({
        "token": token,
        "user_id": user.id,
        "username": user.username,
    })


def _create_and_send_register_code(email):
    code = f"{random.randint(0, 999999):06d}"
    now = time.time()
    EmailVerificationCode.objects.create(
        email=email,
        code=code,
        purpose="register",
        expires_at=now + VERIFICATION_EXPIRE_SECONDS,
    )
    send_mail(
        subject="Your registration verification code",
        message=f"Your verification code is: {code}. It will expire in 10 minutes.",
        from_email=None,
        recipient_list=[email],
        fail_silently=False,
    )


def _verify_register_code(email, code):
    now = time.time()
    record = (
        EmailVerificationCode.objects.filter(
            email=email,
            code=code,
            purpose="register",
            used_at__isnull=True,
            expires_at__gt=now,
        )
        .order_by("-id")
        .first()
    )
    if not record:
        return False

    record.used_at = now
    record.save(update_fields=["used_at"])
    return True


@csrf_exempt
def send_register_code(request):
    if request.method != "POST":
        return bad_method_response()

    try:
        data = json_body(request)
    except ValueError:
        return invalid_field_response("body")

    email = data.get("email")
    if not validate_email(email):
        return invalid_field_response("email")
    if User.objects.filter(email=email).exists():
        return error_response(2, "Email already exists", 409)

    try:
        _create_and_send_register_code(email)
    except Exception:
        return error_response(3, "Failed to send verification email", 500)

    return success_response()

@csrf_exempt
def register(request):
    if request.method != "POST":
        return bad_method_response()

    try:
        data = json_body(request)
    except ValueError:
        return invalid_field_response("body")

    username = data.get("username")
    password = data.get("password")
    email = data.get("email")
    verification_code = data.get("verification_code")

    if not validate_username(username):
        return invalid_field_response("username")
    if not validate_password(password):
        return invalid_field_response("password")
    if not validate_email(email):
        return invalid_field_response("email")
    if not isinstance(verification_code, str) or len(verification_code) != 6 or not verification_code.isdigit():
        return invalid_field_response("verification_code")
    if User.objects.filter(username=username).exists():
        return error_response(1, "Username already exists", 409)
    if User.objects.filter(email=email).exists():
        return error_response(2, "Email already exists", 409)
    if not _verify_register_code(email, verification_code):
        return error_response(3, "Invalid or expired verification code", 400)

    return _register_user(username, password, email)

@csrf_exempt
def login(request):
    if request.method != "POST":
        return bad_method_response()

    try:
        data = json_body(request)
    except ValueError:
        return invalid_field_response("body")

    username = data.get("username")
    password = data.get("password")
    if not isinstance(username, str) or username == "":
        return invalid_field_response("username")
    if not isinstance(password, str) or password == "":
        return invalid_field_response("password")

    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return error_response(1, "User not found", 404)

    if not user.check_password(password):
        return error_response(2, "Wrong password", 401)

    ensure_profile(user)
    token = generate_jwt(user.id)
    return success_response(
        {
            "token": token,
            "user_id": user.id,
            "username": user.username,
        }
    )

@csrf_exempt
def logout(request):
    if request.method != "POST":
        return bad_method_response()
    user = authenticate_request(request)
    if not user:
        return auth_error_response()

    RevokedToken.objects.get_or_create(
        jti=request.auth_payload["jti"],
        defaults={"user": user, "expires_at": request.auth_payload["exp"]},
    )
    return success_response()

@csrf_exempt
def delete_account(request):
    if request.method != "DELETE":
        return bad_method_response()
    user = authenticate_request(request)
    if not user:
        return auth_error_response()

    try:
        data = json_body(request)
    except ValueError:
        return invalid_field_response("body")

    password = data.get("password")
    if not isinstance(password, str) or password == "":
        return invalid_field_response("password")
    if not user.check_password(password):
        return error_response(2, "Wrong password", 401)

    user.delete()
    return success_response()

@csrf_exempt
def profile(request):
    if request.method not in {"GET", "PUT"}:
        return bad_method_response()

    user = authenticate_request(request)
    if not user:
        return auth_error_response()

    if request.method == "GET":
        profile_obj = ensure_profile(user)
        return success_response(
            {
                "user_id": user.id,
                "username": user.username,
                "email": user.email,
                "phone": profile_obj.phone,
                "avatar": profile_obj.avatar,
                "created_at": profile_obj.created_at,
            }
        )

    try:
        data = json_body(request)
    except ValueError:
        return invalid_field_response("body")

    allowed_fields = {
        "username",
        "email",
        "phone",
        "avatar",
        "old_password",
        "new_password",
        "verification_code",
    }
    for field_name in data:
        if field_name not in allowed_fields:
            return invalid_field_response(field_name)

    profile_obj = ensure_profile(user)
    requires_password = any(field in data for field in ("email", "phone", "new_password"))
    old_password = data.get("old_password")
    if requires_password and (not isinstance(old_password, str) or not user.check_password(old_password)):
        return error_response(2, "Wrong password", 401)

    username = data.get("username")
    if "username" in data:
        if not validate_username(username):
            return invalid_field_response("username")
        if User.objects.exclude(id=user.id).filter(username=username).exists():
            return error_response(1, "Username already exists", 409)
        user.username = username

    email = data.get("email")
    if "email" in data:
        verification_code = data.get("verification_code")
        if not isinstance(verification_code, str) or len(verification_code) != 6 or not verification_code.isdigit():
            return invalid_field_response("verification_code")
        if not validate_email(email):
            return invalid_field_response("email")
        if User.objects.exclude(id=user.id).filter(email=email).exists():
            return error_response(2, "Email already exists", 409)
        if not _verify_register_code(email, verification_code):
            return error_response(3, "Invalid or expired verification code", 400)
        user.email = email

    phone = data.get("phone")
    if "phone" in data:
        if not validate_phone(phone):
            return invalid_field_response("phone")
        profile_obj.phone = phone

    avatar = data.get("avatar")
    if "avatar" in data:
        if not validate_avatar(avatar):
            return invalid_field_response("avatar")
        profile_obj.avatar = avatar

    new_password = data.get("new_password")
    if "new_password" in data:
        if not validate_password(new_password):
            return invalid_field_response("new_password")
        user.set_password(new_password)

    with transaction.atomic():
        user.save()
        profile_obj.save()

    return success_response()

def user_detail(request, user_id):
    if request.method != "GET":
        return bad_method_response()
    if not authenticate_request(request):
        return auth_error_response()

    try:
        target_user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return error_response(1, "User not found", 404)

    profile_obj = ensure_profile(target_user)
    return success_response(
        {
            "user_id": target_user.id,
            "username": target_user.username,
            "avatar": profile_obj.avatar,
        }
    )


def search_users(request):
    if request.method != "GET":
        return bad_method_response()
    if not authenticate_request(request):
        return auth_error_response()

    keyword = request.GET.get("keyword")
    page = request.GET.get("page", "1")
    page_size = request.GET.get("page_size", "20")

    if not isinstance(keyword, str) or keyword.strip() == "":
        return invalid_field_response("keyword")
    try:
        page = int(page)
        page_size = int(page_size)
    except ValueError:
        return invalid_field_response("page")
    if page < 1:
        return invalid_field_response("page")
    if page_size < 1:
        return invalid_field_response("page_size")

    queryset = User.objects.filter(Q(username__icontains=keyword)).order_by("id")
    total = queryset.count()
    offset = (page - 1) * page_size
    users = []
    for target_user in queryset[offset:offset + page_size]:
        profile_obj = ensure_profile(target_user)
        users.append(
            {
                "user_id": target_user.id,
                "username": target_user.username,
                "avatar": profile_obj.avatar,
            }
        )

    return JsonResponse({"code": 0, "info": "Succeed", "total": total, "users": users})
