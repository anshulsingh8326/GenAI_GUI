"""ComfyUI content routes - inspect the install + audit module requirements.

Read-only in Phase A: these endpoints only look at folders. Node installs and
model downloads arrive in later phases and stay behind explicit user clicks
(see docs/COMFYUI_CONTENT.md).
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.engine_content import service

router = APIRouter(tags=["engine-content"])


@router.get("/comfyui/inspect")
def inspect_comfyui(path: str | None = Query(default=None)) -> dict:
    """Inspect the configured ComfyUI folder - or preview a candidate via ?path=."""
    return service.inspect(path)


@router.get("/comfyui/requirements")
def comfyui_requirements() -> dict:
    """Per-module node/model audit against the configured ComfyUI folder."""
    return service.requirements()
