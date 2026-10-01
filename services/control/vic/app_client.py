import os
from urllib.parse import urlsplit
import hmac
import httpx
from .lessons import progress


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
                interaction=run.manifest.get("interaction", "agent"),
                lesson=progress(run.manifest.get("lesson")),
            ),
        )

    def snapshot(self, id_):
        return self.call("GET", f"/internal/runs/{id_}")

    def seal(self, id_):
        return self.call("POST", f"/internal/runs/{id_}/seal")

    def resume(self, id_):
        return self.call("POST", f"/internal/runs/{id_}/resume")

    def release(self, id_):
        return self.call("POST", f"/internal/runs/{id_}/release")

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
        if run.initial.get('workflow') in ('communications','music_projects'):
            from .lessons import native_path
            return f"{base}{native_path(run.initial['app'],run.id)}#{token}"
        if run.initial.get('workflow'):
            return f"{base}/native/product/{run.initial['app']}/{run.id}#{token}"
        return f"{base}/apps/{run.initial['app']}/{run.id}#{token}"
