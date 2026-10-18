"""ComfyUI HTTP client - probe, queue and cache control.

Read-only calls (system_stats, queue) are safe at any time. `free()` is the
only mutating call and merely *releases* memory - it never loads a model.
"""

from __future__ import annotations

import re

import httpx


def parse_auth(auth: str) -> dict[str, str]:
    """Turn the profile's auth string into headers.

    Accepts "Authorization: Bearer xxx" (header: value) or a bare value which
    is sent as the Authorization header.
    """
    auth = (auth or "").strip()
    if not auth:
        return {}
    if ":" in auth:
        name, _, value = auth.partition(":")
        return {name.strip(): value.strip()}
    return {"Authorization": auth}


def clean_device_name(raw: str) -> str:
    """'cuda:0 NVIDIA GeForce RTX 4070 : cudaMallocAsync' -> 'NVIDIA GeForce RTX 4070'."""
    name = (raw or "").split(" : ")[0].strip()
    return re.sub(r"^(cuda|rocm|cpu|mps):\d+\s+", "", name, flags=re.IGNORECASE)


class ComfyUIClient:
    def __init__(self, base_url: str, auth: str = "", timeout: float = 4.0):
        self.base_url = (base_url or "").rstrip("/")
        self.headers = parse_auth(auth)
        self.timeout = httpx.Timeout(timeout, connect=min(2.0, timeout))

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if not self.base_url:
            raise httpx.ConnectError("No URL configured")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.request(method, f"{self.base_url}{path}", headers=self.headers, **kwargs)
            res.raise_for_status()
            return res

    async def system_stats(self) -> dict:
        return (await self._request("GET", "/system_stats")).json()

    async def queue(self) -> dict:
        return (await self._request("GET", "/queue")).json()

    async def free(self, unload_models: bool = True) -> None:
        """POST /free - releases the model cache. Never loads anything."""
        await self._request("POST", "/free", json={"unload_models": unload_models, "free_memory": True})

    async def interrupt(self) -> None:
        """POST /interrupt - cancels the current run (wired with job cancel later)."""
        await self._request("POST", "/interrupt")
