import os
from urllib.parse import urlsplit
import hmac
import httpx


class ApplicationClient:
    def __init__(self, manager_secret):
        self.base = os.environ.get(
            "VIC_APPLICATION_BASE", "http://127.0.0.1:8771"
        ).rstrip("/")
        self.secret = (
            os.environ.get("VIC_APP_RUNTIME_TOKEN")
            or hmac.new(
                manager_secret.encode(), b"application-worker", "sha256"
            ).hexdigest()
        )

    def call(self, method, path, body=None):
        with httpx.Client(timeout=30) as c:
            response = c.request(
                method,
                self.base + path,
                headers={"Authorization": "Bearer " + self.secret},
                json=body,
            )
            response.raise_for_status()
            return response.json()

    def prepare(self, run, token):
        return self.call(
            "POST",
            "/internal/prepare",
            dict(
                run_id=run.id,
                app=run.initial["app"],
                token=token,
                epoch=run.epoch,
                state=run.initial,
            ),
        )

    def snapshot(self, id_):
        return self.call("GET", f"/internal/runs/{id_}")

    def seal(self, id_):
        return self.call("POST", f"/internal/runs/{id_}/seal")

    def destroy(self, id_):
        return self.call("DELETE", f"/internal/runs/{id_}")

    def url(self, run, token):
        origin = urlsplit(self.base)
        base = self.base
        if origin.scheme == "http" and origin.hostname not in (
            "localhost",
            "127.0.0.1",
            "::1",
        ):
            base = base.replace(
                origin.netloc, f"application.localhost:{origin.port or 80}", 1
            )
        return f"{base}/apps/{run.initial['app']}/{run.id}#{token}"
