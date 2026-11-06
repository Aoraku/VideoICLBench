"""Auth-only forwarding guard used when an existing Codex session retains its previous key."""
import json
from urllib.parse import urlsplit


def forward_options(method, destination, kwargs, *, base_url, api_key):
    expected, target = urlsplit(base_url), urlsplit(destination)
    if (expected.scheme != "https" or not expected.hostname or expected.username is not None
            or expected.password is not None or expected.query or expected.fragment
            or expected.path.rstrip("/") != "/v1" or target.scheme != "https"
            or target.netloc != expected.netloc or target.query or target.fragment):
        raise ValueError("Unexpected provider destination")
    routes = {"GET": {"/v1/models"}, "POST": {"/v1/responses", "/v1/responses/compact"}}
    if target.path not in routes.get(method.upper(), set()):
        raise ValueError("Unexpected provider route")
    if method.upper() == "POST":
        body = kwargs.get("content")
        if not isinstance(body, (str, bytes)):
            raise ValueError("Expected buffered original request")
        payload = json.loads(body)
        if not isinstance(payload, dict) or payload.get("model") != "gpt-6-astra":
            raise ValueError("Evaluation model mismatch")
    headers = {k: v for k, v in kwargs.get("headers", {}).items()
               if k.lower() not in {"authorization", "x-api-key"}}
    headers["Authorization"] = "Bearer " + api_key
    return dict(kwargs, headers=headers)
