"""Runner credentials must never be supplied to the model process."""

import httpx
import uuid


class Client:
    def __init__(self, base_url, token):
        self.http = httpx.Client(
            base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=120
        )

    def _call(self, method, path, **kwargs):
        response = self.http.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    def create(self, task_id, variant, seed, mode="eval", runtime="web-dev"):
        return self._call(
            "POST",
            "/v1/runs",
            json=dict(
                task_id=task_id, variant=variant, seed=seed, mode=mode, runtime=runtime
            ),
        )

    def observation(self, run_id):
        return self._call("GET", f"/v1/runs/{run_id}/observation")

    def act(self, run_id, epoch, frame, kind, **kwargs):
        return self._call(
            "POST",
            f"/v1/runs/{run_id}/actions",
            json=dict(
                epoch=epoch,
                frame=frame,
                action_id=uuid.uuid4().hex,
                kind=kind,
                **kwargs,
            ),
        )

    def evaluate(self, run_id):
        return self._call("POST", f"/v1/runs/{run_id}/evaluate")

    def reset(self, run_id):
        return self._call("POST", f"/v1/runs/{run_id}/reset")

    def close(self):
        self.http.close()
