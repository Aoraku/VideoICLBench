import base64
import hashlib
import hmac
import json
import time
import uuid

from django.conf import settings

def _b64url_encode(raw_bytes):
    return base64.urlsafe_b64encode(raw_bytes).rstrip(b"=").decode("ascii")

def _b64url_decode(raw_text):
    padding = "=" * (-len(raw_text) % 4)
    return base64.urlsafe_b64decode((raw_text + padding).encode("ascii"))

def _sign(message):
    return hmac.new(
        settings.JWT_SECRET_KEY.encode("utf-8"),
        message.encode("ascii"),
        hashlib.sha256,
    ).digest()

def generate_jwt(user_id):
    now = int(time.time())
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + settings.JWT_EXPIRATION_SECONDS,
        "jti": uuid.uuid4().hex,
    }
    header = {"alg": settings.JWT_ALGORITHM, "typ": "JWT"}
    encoded_header = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}"
    signature = _b64url_encode(_sign(signing_input))
    return f"{signing_input}.{signature}"

def decode_jwt(token):
    try:
        header_segment, payload_segment, signature_segment = token.split(".")
    except ValueError as exc:
        raise ValueError("Malformed token") from exc

    signing_input = f"{header_segment}.{payload_segment}"
    expected_signature = _b64url_encode(_sign(signing_input))
    if not hmac.compare_digest(expected_signature, signature_segment):
        raise ValueError("Invalid signature")

    try:
        header = json.loads(_b64url_decode(header_segment))
        payload = json.loads(_b64url_decode(payload_segment))
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("Malformed token") from exc

    if header.get("alg") != settings.JWT_ALGORITHM or header.get("typ") != "JWT":
        raise ValueError("Invalid header")

    exp = payload.get("exp")
    sub = payload.get("sub")
    jti = payload.get("jti")
    if not isinstance(exp, int) or not isinstance(sub, int) or not isinstance(jti, str):
        raise ValueError("Invalid payload")
    if exp < int(time.time()):
        raise ValueError("Expired token")
    return payload
