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
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import psutil

from app.common import paths, settings_store

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


# ------------------------------------------------------------------- launcher


LAUNCHABLE_SUFFIXES = {".bat", ".cmd", ".exe"}


def launch_comfyui() -> dict:
    """Start the user's ComfyUI launcher in a NEW console window (like a double-click).

    Runs from the explicit GUI action, or once at backend boot when the user
    enabled auto-start (see `maybe_autostart_comfyui`). Never from probes or
    agent tools. The path comes from Settings (`comfyuiLauncher`); nothing is
    installed or downloaded, we literally start the file the user chose, with
    its own folder as the working directory.
    """
    values, _ = settings_store.load()
    raw = str(values.get("comfyuiLauncher") or "").strip()
    if not raw:
        return {
            "started": False,
            "path": "",
            "detail": "No launcher set - pick your ComfyUI .bat in Settings > Connections.",
        }

    path = Path(raw).expanduser()
    if not path.is_file():
        return {
            "started": False,
            "path": str(path),
            "detail": "The launcher file does not exist (did it move?).",
        }
    if path.suffix.lower() not in LAUNCHABLE_SUFFIXES:
        return {
            "started": False,
            "path": str(path),
            "detail": "Only .bat / .cmd / .exe launchers can be started.",
        }

    try:
        # `start ""` opens the target in its own console window; cwd = the
        # launcher's folder - the same thing double-clicking the file does.
        subprocess.Popen(["cmd.exe", "/c", "start", "", str(path)], cwd=str(path.parent))
    except OSError as err:
        return {"started": False, "path": str(path), "detail": f"Could not start it: {err}"}

    return {
        "started": True,
        "path": str(path),
        "detail": "Launched in a new window - ComfyUI takes a moment to come up.",
    }


# ----------------------------------------------------------------- auto-start

_AUTOSTART_STAMP = paths.DATA_DIR / "comfyui_autostart.stamp"
AUTOSTART_DEBOUNCE_SECONDS = 180


def _host_port(url: str) -> tuple[str, int] | None:
    try:
        parsed = httpx.URL(url)
    except Exception:  # noqa: BLE001 - malformed URL simply means "cannot probe"
        return None
    if not parsed.host:
        return None
    return parsed.host, parsed.port or (443 if parsed.scheme == "https" else 80)


def comfyui_reachable(timeout: float = 0.4) -> bool:
    """Cheap TCP check against the active ComfyUI profile - no HTTP request involved."""
    address = _host_port(active_connection("comfyui")[0])
    if not address:
        return False
    try:
        with socket.create_connection(address, timeout=timeout):
            return True
    except OSError:
        return False


def maybe_autostart_comfyui() -> dict | None:
    """Boot-time opt-in: start the saved launcher when `comfyuiLauncherAutoStart` is on.

    Guarded so it can never spam windows: skipped when ComfyUI is already
    reachable, and a fresh spawn stamp debounces quick restarts (uvicorn
    --reload boots the app again on every code change). Returns None when the
    setting is off, otherwise the launch result - main.py logs the detail.
    """
    values, _ = settings_store.load()
    if not values.get("comfyuiLauncherAutoStart"):
        return None

    raw = str(values.get("comfyuiLauncher") or "").strip()
    if not raw:
        return {"started": False, "path": "", "detail": "auto-start is on, but no launcher path is set."}

    if comfyui_reachable():
        return {"started": False, "path": raw, "detail": "ComfyUI is already running - skipped."}

    try:
        stamp_age: float | None = time.time() - _AUTOSTART_STAMP.stat().st_mtime
    except OSError:
        stamp_age = None
    if stamp_age is not None and stamp_age < AUTOSTART_DEBOUNCE_SECONDS:
        return {
            "started": False,
            "path": raw,
            "detail": f"launcher was started {int(stamp_age)}s ago - skipped (debounce).",
        }

    result = launch_comfyui()
    if result["started"]:
        try:
            _AUTOSTART_STAMP.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
        except OSError:
            pass  # stamp is best-effort - never fail the launch because of it
    return result
