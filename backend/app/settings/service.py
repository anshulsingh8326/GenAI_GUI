"""Settings service: the app's own configuration (settings.json).

Thin facade over `app.common.settings_store` - kept as its own folder because
later groups add per-provider configuration (text providers, probe results)
that is not part of the raw store.
"""

from __future__ import annotations

from typing import Any

from app.common import settings_store


def get() -> tuple[dict[str, Any], bool]:
    """(values, initialized)"""
    return settings_store.load()


def get_defaults() -> dict[str, Any]:
    return settings_store.defaults()


def update(updates: dict[str, Any]) -> dict[str, Any]:
    return settings_store.merge_and_save(updates)


def reset() -> dict[str, Any]:
    return settings_store.reset()
