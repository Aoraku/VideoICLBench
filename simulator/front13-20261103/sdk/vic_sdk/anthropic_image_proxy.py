"""Opt-in wire compatibility for gateways that drop images nested in tool_result.

Only moves image blocks to the same user message's top-level content. Image bytes,
tool IDs, text, history, model parameters and streamed responses are unchanged.
No model loop, retries, OCR, summarization or task information lives here.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit

import httpx


def lift_tool_images(payload):
    result = deepcopy(payload)
    count = 0
    for message in result.get("messages", []):
        if message.get("role") != "user" or not isinstance(message.get("content"), list):
            continue
        lifted = []
        for block in message["content"]:
            if block.get("type") != "tool_result" or not isinstance(block.get("content"), list):
                continue
            remaining = []
            for item in block["content"]:
                if item.get("type") == "image":
                    lifted.append(item)
                    count += 1
                else:
                    remaining.append(item)
            block["content"] = remaining
        # Keep all tool_result blocks first, as required by the Messages protocol.
        message["content"].extend(lifted)
    return result, count


@contextmanager
def image_compat_proxy(base_url: str, api_key: str, log: Path):
    local_token = secrets.token_hex(32)
    log_lock = threading.Lock()
    client = httpx.Client(timeout=httpx.Timeout(180, connect=30))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            if self.headers.get("Authorization") != "Bearer " + local_token:
                self.send_error(403)
                return
            path = urlsplit(self.path)
            if path.path not in ("/v1/messages", "/v1/messages/count_tokens"):
                self.send_error(404)
                return
            started = time.monotonic()
            status, count = 502, 0
            response_started, transport_error = False, False
            try:
                payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                payload, count = lift_tool_images(payload)
                headers = {k: v for k, v in self.headers.items() if k.lower() not in
                           {"host", "content-length", "connection", "transfer-encoding", "accept-encoding",
                            "authorization", "x-api-key"}}
                headers.update({"Authorization": "Bearer " + api_key, "x-api-key": api_key,
                                "accept-encoding": "identity"})
                root = base_url.rstrip("/")
                suffix = path.path[3:] if root.endswith("/v1") else path.path
                if path.query:
                    suffix += "?" + path.query
                with client.stream("POST", root + suffix, headers=headers, json=payload) as response:
                    status = response.status_code
                    self.send_response(status)
                    for key, value in response.headers.items():
                        if key.lower() not in {"connection", "transfer-encoding", "content-length"}:
                            self.send_header(key, value)
                    self.end_headers()
                    response_started = True
                    for chunk in response.iter_raw():
                        self.wfile.write(chunk)
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                transport_error = True
            except (httpx.HTTPError, ValueError):
                # Do not echo upstream exception strings, headers or model inputs.
                transport_error = True
                if not response_started:
                    self.send_error(502, "Image compatibility upstream request failed")
            finally:
                with log_lock, log.open("a") as out:
                    out.write(json.dumps({"path": path.path, "status": status, "images_lifted": count,
                                          "transport_error": transport_error,
                                          "seconds": round(time.monotonic() - started, 3)}) + "\n")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", local_token
    finally:
        server.shutdown()
        server.server_close()
        client.close()
        worker.join(timeout=2)
