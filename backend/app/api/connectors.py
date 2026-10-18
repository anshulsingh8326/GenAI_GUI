"""Connector routes: connection tests + engine memory actions.

Engine actions are safe by construction: /free only releases memory, the Ollama
unload only ever targets models that are already loaded, and /launch starts the
user's own ComfyUI launcher on an explicit click - nothing runs automatically.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.connectors import service

router = APIRouter(tags=["connectors"])


@router.post("/connectors/{kind}/test")
async def test_connection(kind: Literal["comfyui", "ollama"]) -> dict:
    return await service.test_connection(kind)


@router.post("/engine/comfyui/free")
async def free_comfyui() -> dict:
    return await service.free_comfyui()


@router.post("/engine/comfyui/launch")
def launch_comfyui() -> dict:
    """Start the launcher saved in Settings (`comfyuiLauncher`) in its own window."""
    return service.launch_comfyui()


class UnloadRequest(BaseModel):
    model: str | None = None


@router.post("/engine/ollama/unload")
async def unload_ollama(req: UnloadRequest) -> dict:
    return await service.unload_ollama(req.model)
