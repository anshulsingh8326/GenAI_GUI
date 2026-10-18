"""settings.json service - load / merge / save with atomic writes.

Rules:
- the file only ever holds the *persisted* settings (no runtime state like
  "connected" or "checking");
- every load is merged over the shipped defaults, so a partial or older file
  can never break the app;
- writes are atomic (tmp file + os.replace) and never delete anything.
"""

from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from typing import Any

from . import paths
from .defaults import default_settings

_lock = threading.Lock()


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge `override` into a copy of `base` (dicts merge, lists/scalars replace)."""
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def load() -> tuple[dict[str, Any], bool]:
    """Return (settings, initialized).

    `initialized` is False when settings.json does not exist (or is unreadable) -
    the GUI uses that to decide whether to push its current browser settings
    into the backend on first connect.
    """
    with _lock:
        if not paths.SETTINGS_FILE.exists():
            return default_settings(), False
        try:
            raw = json.loads(paths.SETTINGS_FILE.read_text(encoding="utf-8") or "{}")
        except (OSError, json.JSONDecodeError):
            return default_settings(), False
        if not isinstance(raw, dict):
            return default_settings(), False
        return _deep_merge(default_settings(), raw), True


def save(values: dict[str, Any]) -> dict[str, Any]:
    """Merge over defaults, write atomically, return the merged result."""
    merged = _deep_merge(default_settings(), values)
    with _lock:
        paths.DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = paths.SETTINGS_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, paths.SETTINGS_FILE)
    return merged


def merge_and_save(updates: dict[str, Any]) -> dict[str, Any]:
    """Apply a partial update on top of the current settings and save."""
    current, _ = load()
    return save(_deep_merge(current, updates))


def defaults() -> dict[str, Any]:
    return default_settings()


def reset() -> dict[str, Any]:
    """Write the shipped defaults to settings.json (files/folders are not deleted)."""
    return save(default_settings())
