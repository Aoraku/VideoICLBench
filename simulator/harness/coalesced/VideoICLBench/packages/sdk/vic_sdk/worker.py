import httpx


class WorkerClient:
    """Private lifecycle client; excluded from the model's action tools."""

    def __init__(self, url, token):
        self.http = httpx.Client(
            base_url=url, headers={"Authorization": "Bearer " + token}, timeout=180
        )

    def request(self, method, path, body=None):
        r = self.http.request(method, path, json=body)
        r.raise_for_status()
        return r.json()

    def health(self):
        return self.request("GET", "/healthz")

    def create(self, profile):
        return self.request("POST", "/instances", {"profile": profile})

    def reset(self, instance_id):
        return self.request("POST", f"/instances/{instance_id}/reset")

    def destroy(self, instance_id):
        return self.request("DELETE", f"/instances/{instance_id}")
