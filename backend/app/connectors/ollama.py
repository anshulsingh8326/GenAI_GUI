"""Ollama HTTP client - model listing, generation and memory control.

`tags()` and `ps()` are read-only. `generate()` is explicitly called only by a
GenModule after validation. `unload()` uses the documented keep_alive:0 call -
the service layer only ever calls it for models that are ALREADY in memory (see
connectors/service.py), so it can never trigger a model load.
"""

from __future__ import annotations

import httpx


class OllamaClient:
    def __init__(self, base_url: str, timeout: float = 4.0):
        self.base_url = (base_url or "").rstrip("/")
        self.timeout = httpx.Timeout(timeout, connect=min(2.0, timeout))

    async def _request(self, method: str, path: str, timeout: float | None = None, **kwargs) -> httpx.Response:
        if not self.base_url:
            raise httpx.ConnectError("No URL configured")
        request_timeout = httpx.Timeout(timeout, connect=min(2.0, timeout)) if timeout else self.timeout
        async with httpx.AsyncClient(timeout=request_timeout) as client:
            res = await client.request(method, f"{self.base_url}{path}", **kwargs)
            res.raise_for_status()
            return res

    async def tags(self) -> list[dict]:
        """Installed models (GET /api/tags)."""
        return (await self._request("GET", "/api/tags")).json().get("models") or []

    async def ps(self) -> list[dict]:
        """Models currently in memory (GET /api/ps)."""
        return (await self._request("GET", "/api/ps")).json().get("models") or []

    async def generate(
        self,
        model: str,
        prompt: str,
        *,
        system: str = "",
        options: dict | None = None,
        timeout: float = 240.0,
    ) -> dict:
        """Non-streaming POST /api/generate. Returns the full Ollama response."""
        payload: dict = {"model": model, "prompt": prompt, "stream": False}
        if system:
            payload["system"] = system
        if options:
            payload["options"] = options
        return (await self._request("POST", "/api/generate", json=payload, timeout=timeout)).json()

    async def unload(self, name: str) -> None:
        """Release a LOADED model (keep_alive 0). Caller must check ps() first."""
        await self._request("POST", "/api/generate", json={"model": name, "keep_alive": 0})
