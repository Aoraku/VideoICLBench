"""Check local native service routes and protocol gates without external messages."""

import json
from pathlib import Path
import httpx

checks = [
    ("chat-ui", 8811, "/", 200),
    ("chat-auth", 8811, "/api/conversations/", 403),
    ("im-ui", 8812, "/", 200),
    ("im-auth", 8812, "/api/conversations", 401),
    ("music", 8803, "/", 200),
    ("news", 8804, "/health", 200),
    ("code-ui", 8805, "/_stcore/health", 200),
    ("gomoku-vnc", 8806, "/vnc.html", 200),
]
results = []
with httpx.Client(timeout=20, follow_redirects=True) as c:
    for name, port, path, expected in checks:
        response = c.get(f"http://127.0.0.1:{port}{path}")
        assert response.status_code == expected, (name, response.status_code)
        results.append(dict(service=name, status=response.status_code))
    response = c.get("http://127.0.0.1:8804/api/news", params={"words": "Alpha"})
    response.raise_for_status()
    articles = response.json()["data"]
    assert len(articles) == 1 and articles[0]["title"] == "Alpha report 3"
    # ASGI rejects an unauthenticated Upgrade with 403; a missing WS proxy gives 404/502.
    for port, path in [(8811, "/ws/chat/"), (8812, "/ws/")]:
        response = c.get(
            f"http://127.0.0.1:{port}{path}",
            headers={
                "Connection": "Upgrade",
                "Upgrade": "websocket",
                "Sec-WebSocket-Version": "13",
                "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
            },
        )
        assert response.status_code == 403, (port, response.status_code)
        results.append(dict(service=f"websocket-{port}", status=response.status_code))
Path(".local/native-result.json").write_text(
    json.dumps(dict(results=results, official=False), indent=2)
)
print(
    "PASS: six native application surfaces, local news fixture, and both WebSocket authentication gates."
)
