"""ComfyUI HTTP client - probe, queue, submit, history and image download.

Read-only calls (system_stats, queue, object_info, history, view) are safe at any
time. `free()` only releases memory; `submit_prompt()` is the single call that
starts work, and it is only used by a GenModule after its own validation.
"""

from __future__ import annotations

import re
from urllib.parse import quote

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

    async def _request(self, method: str, path: str, timeout: float | None = None, **kwargs) -> httpx.Response:
        if not self.base_url:
            raise httpx.ConnectError("No URL configured")
        request_timeout = httpx.Timeout(timeout, connect=min(2.0, timeout)) if timeout else self.timeout
        async with httpx.AsyncClient(timeout=request_timeout) as client:
            res = await client.request(method, f"{self.base_url}{path}", headers=self.headers, **kwargs)
            res.raise_for_status()
            return res

    async def system_stats(self) -> dict:
        return (await self._request("GET", "/system_stats")).json()

    async def queue(self) -> dict:
        return (await self._request("GET", "/queue")).json()

    async def object_info(self, timeout: float = 30.0) -> dict:
        """Full node schema map (GET /object_info). Large; use object_info_node when possible."""
        return (await self._request("GET", "/object_info", timeout=timeout)).json()

    async def object_info_node(self, node_class: str, timeout: float = 15.0) -> dict:
        """Schema for one node class, e.g. `KSampler` or `UnetLoaderGGUF`."""
        encoded = quote(node_class, safe="")
        return (await self._request("GET", f"/object_info/{encoded}", timeout=timeout)).json()

    async def submit_prompt(self, prompt: dict, client_id: str | None = None, timeout: float = 60.0) -> dict:
        """POST /prompt. Raises RuntimeError with ComfyUI's node errors when rejected."""
        payload: dict = {"prompt": prompt}
        if client_id:
            payload["client_id"] = client_id
        try:
            res = await self._request("POST", "/prompt", json=payload, timeout=timeout)
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:1600] if exc.response is not None else str(exc)
            raise RuntimeError(f"ComfyUI rejected the prompt: {detail}") from exc
        data = res.json()
        if data.get("node_errors"):
            raise RuntimeError(f"ComfyUI node errors: {data['node_errors']}")
        if data.get("error"):
            raise RuntimeError(f"ComfyUI error: {data['error']}")
        return data

    async def history(self, prompt_id: str, timeout: float = 15.0) -> dict:
        """GET /history/{prompt_id}; returns {} while the prompt is still running."""
        return (await self._request("GET", f"/history/{quote(str(prompt_id), safe='')}", timeout=timeout)).json()

    async def view(self, filename: str, subfolder: str = "", type: str = "output", timeout: float = 120.0) -> bytes:
        """GET /view - download one output file. Never writes anything by itself."""
        params = {"filename": filename, "subfolder": subfolder, "type": type}
        return (await self._request("GET", "/view", params=params, timeout=timeout)).content

    async def queue_delete(self, prompt_id: str) -> None:
        """Remove a pending prompt from the queue (best effort)."""
        await self._request("POST", "/queue", json={"delete": [str(prompt_id)]}, timeout=10.0)

    async def free(self, unload_models: bool = True) -> None:
        """POST /free - releases the model cache. Never loads anything."""
        await self._request(
            "POST", "/free", json={"unload_models": unload_models, "free_memory": True}, timeout=10.0
        )

    async def interrupt(self) -> None:
        """POST /interrupt - cancels the current run (wired with job cancel later)."""
        await self._request("POST", "/interrupt", timeout=10.0)
