"""Settings routes - GET/PUT/reset + defaults for the field-level reset buttons."""

from __future__ import annotations

from fastapi import APIRouter

from app.settings import service
from app.settings.models import SettingsPayload

router = APIRouter(tags=["settings"])


@router.get("/settings")
def get_settings() -> dict:
    values, initialized = service.get()
    return {"values": values, "initialized": initialized}


@router.get("/settings/defaults")
def get_settings_defaults() -> dict:
    """The shipped defaults - the GUI uses these for per-field reset buttons."""
    return service.get_defaults()


@router.put("/settings")
def put_settings(payload: SettingsPayload) -> dict:
    """Partial update: deep-merged over current settings, then saved.

    exclude_unset (not just exclude_none) is essential: a nested partial like
    {"defaults": {"upscaler": "x"}} must not blank the sibling fields.
    """
    updates = payload.model_dump(exclude_unset=True, exclude_none=True)
    return service.update(updates)


@router.post("/settings/reset")
def reset_settings() -> dict:
    """Write shipped defaults to settings.json. Files and folders are untouched."""
    return service.reset()
