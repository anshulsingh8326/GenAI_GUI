"""Connector service - the app's view of ComfyUI and Ollama.

Responsibilities:
- resolve the ACTIVE connection profile from settings (url + auth);
- probe both engines read-only and produce the status snapshot the GUI polls;
- engine memory actions (free VRAM / unload models) with safety rules.

Safety rule for Ollama: unload only ever targets models that are currently in
memory (`/api/ps`), so calling it can never cause a model to be loaded.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
import psutil

from app.common import settings_store

from .comfyui import ComfyUIClient, clean_device_name
from .ollama import OllamaClient

KINDS = ("comfyui", "ollama")


def _short(err: Exception) -> str:
    if isinstance(err, (httpx.ConnectError, httpx.ConnectTimeout)):
        return "Not reachable - is it running?"
    if isinstance(err, httpx.HTTPStatusError):
        return f"HTTP {err.response.status_code} from the engine"
    if isinstance(err, httpx.TimeoutException):
        return "Timed out waiting for a response"
    return str(err)[:140]


def _gb(value) -> float | None:
    if isinstance(value, (int, float)) and value > 0:
        return round(float(value) / 1e9, 1)
    return None


def active_connection(kind: str) -> tuple[str, str]:
    """(url, auth) of the active profile for this engine; falls back to connections.url."""
    if kind not in KINDS:
        raise ValueError(f"Unknown connector '{kind}'")
    values, _ = settings_store.load()
    profiles = values.get("profiles") or []
    active_id = (values.get("activeProfiles") or {}).get(kind)
    for profile in profiles:
        if profile.get("id") == active_id and profile.get("kind") == kind:
            return str(profile.get("url") or ""), str(profile.get("auth") or "")
    fallback = ((values.get("connections") or {}).get(kind) or {}).get("url") or ""
    return str(fallback), ""


def comfy_client() -> ComfyUIClient:
    url, auth = active_connection("comfyui")
    return ComfyUIClient(url, auth)


def ollama_client() -> OllamaClient:
    url, _ = active_connection("ollama")
    return OllamaClient(url)


def _minutes_until(expires_at: str | None) -> int | None:
    if not expires_at:
        return None
    try:
        when = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    delta = (when - datetime.now(timezone.utc)).total_seconds()
    return max(0, round(delta / 60))


async def comfy_status() -> dict:
    client = comfy_client()
    offline = {
        "connected": False,
        "url": client.base_url,
        "detail": "",
        "version": None,
        "gpuName": None,
        "vramTotalGb": None,
        "vramFreeGb": None,
        "queue": {"running": 0, "pending": 0},
        # ComfyUI exposes no "loaded models" API - the app tracks its own jobs
        # (added with the generation modules) and clears this after /free.
        "loaded": [],
    }
    try:
        stats = await client.system_stats()
    except Exception as err:  # noqa: BLE001 - any transport failure means offline
        offline["detail"] = _short(err)
        return offline

    system = stats.get("system") or {}
    devices = stats.get("devices") or []
    device = devices[0] if devices else {}
    version = system.get("comfyui_version")
    gpu_name = clean_device_name(str(device.get("name") or ""))
    vram_total = _gb(device.get("vram_total"))
    vram_free = _gb(device.get("vram_free"))

    running = pending = 0
    try:
        queue = await client.queue()
        running = len(queue.get("queue_running") or [])
        pending = len(queue.get("queue_pending") or [])
    except Exception:  # noqa: BLE001 - queue is best-effort
        pass

    parts = []
    if version:
        parts.append(f"v{version}")
    if gpu_name:
        parts.append(gpu_name)
    if vram_total:
        parts.append(f"{vram_total:.0f} GB VRAM")
    if running or pending:
        parts.append(f"queue {running + pending}")

    return {
        "connected": True,
        "url": client.base_url,
        "detail": " - ".join(parts) or "Reachable",
        "version": version,
        "gpuName": gpu_name or None,
        "vramTotalGb": vram_total,
        "vramFreeGb": vram_free,
        "queue": {"running": running, "pending": pending},
        "loaded": [],
    }


async def ollama_status() -> dict:
    client = ollama_client()
    offline = {
        "connected": False,
        "url": client.base_url,
        "detail": "",
        "installed": [],
        "loaded": [],
    }
    try:
        tags = await client.tags()
    except Exception as err:  # noqa: BLE001
        offline["detail"] = _short(err)
        return offline

    installed = [
        {"name": m.get("name") or m.get("model") or "?", "sizeGb": _gb(m.get("size")) or 0.0}
        for m in tags
    ]

    loaded: list[dict] = []
    try:
        for m in await client.ps():
            name = m.get("name") or m.get("model") or "?"
            loaded.append(
                {
                    "id": name,
                    "name": name,
                    "sizeGb": _gb(m.get("size")) or 0.0,
                    "expiresInMin": _minutes_until(m.get("expires_at")),
                }
            )
    except Exception:  # noqa: BLE001 - ps is best-effort
        pass

    detail = f"{len(installed)} models installed"
    if loaded:
        detail += f" - {len(loaded)} loaded"
    return {
        "connected": True,
        "url": client.base_url,
        "detail": detail,
        "installed": installed,
        "loaded": loaded,
    }


def ram_stats() -> dict:
    vm = psutil.virtual_memory()
    return {"ramUsedGb": round(vm.used / 1e9, 1), "ramTotalGb": round(vm.total / 1e9, 1)}


async def status_snapshot() -> dict:
    """Everything the top bar + Resources popover need, in one round-trip."""
    comfy, ollama = await asyncio.gather(comfy_status(), ollama_status())

    vram_used = None
    if comfy["connected"] and comfy["vramTotalGb"] and comfy["vramFreeGb"] is not None:
        vram_used = max(0.0, round(comfy["vramTotalGb"] - comfy["vramFreeGb"], 1))

    return {
        "comfyui": comfy,
        "ollama": ollama,
        "resources": {
            "vramUsedGb": vram_used,
            "vramTotalGb": comfy["vramTotalGb"],
            **ram_stats(),
        },
    }


async def test_connection(kind: str) -> dict:
    status = await comfy_status() if kind == "comfyui" else await ollama_status()
    return {"connected": status["connected"], "detail": status["detail"]}


async def free_comfyui() -> dict:
    client = comfy_client()
    try:
        await client.free(unload_models=True)
    except Exception as err:  # noqa: BLE001
        return {"ok": False, "message": f"Could not free ComfyUI memory: {_short(err)}"}
    return {"ok": True, "message": "ComfyUI cache freed - models unloaded"}


async def unload_ollama(model: str | None = None) -> dict:
    client = ollama_client()
    try:
        in_memory = [m.get("name") or m.get("model") for m in await client.ps()]
    except Exception as err:  # noqa: BLE001
        return {"ok": False, "message": f"Could not read loaded models: {_short(err)}"}

    if model:
        if model not in in_memory:
            return {"ok": True, "message": f"{model} is not loaded - nothing to unload"}
        targets = [model]
    else:
        targets = in_memory

    if not targets:
        return {"ok": True, "message": "Nothing to unload - no models in memory"}

    try:
        for name in targets:
            await client.unload(name)
    except Exception as err:  # noqa: BLE001
        return {"ok": False, "message": f"Unload failed: {_short(err)}"}

    if len(targets) == 1:
        return {"ok": True, "message": f"{targets[0]} unloaded from memory"}
    return {"ok": True, "message": f"{len(targets)} Ollama models unloaded"}
