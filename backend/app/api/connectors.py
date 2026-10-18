"""Connector routes: connection tests + engine memory actions.

Engine actions are safe by construction: /free only releases memory, and the
Ollama unload only ever targets models that are already loaded.
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


class UnloadRequest(BaseModel):
    model: str | None = None


@router.post("/engine/ollama/unload")
async def unload_ollama(req: UnloadRequest) -> dict:
    return await service.unload_ollama(req.model)
