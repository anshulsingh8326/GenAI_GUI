"""ComfyUI content routes - inspect the install, audit requirements, install nodes.

Inspection and audits are read-only. Installs only accept a module id + node
name that a shipped requirements.json declares; writes are explicit user
clicks (docs/COMFYUI_CONTENT.md).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.engine_content import installer, service

router = APIRouter(tags=["engine-content"])


class InstallNodeBody(BaseModel):
    moduleId: str
    nodeName: str


@router.get("/comfyui/inspect")
def inspect_comfyui(path: str | None = Query(default=None)) -> dict:
    """Inspect the configured ComfyUI folder - or preview a candidate via ?path=."""
    return service.inspect(path)


@router.get("/comfyui/requirements")
def comfyui_requirements() -> dict:
    """Core baseline + per-module node/model audit against the configured folder."""
    return service.requirements()


@router.post("/comfyui/nodes/install", status_code=202)
def install_comfyui_node(body: InstallNodeBody) -> dict:
    """Start installing one required custom node / package (returns a task)."""
    try:
        return installer.start_install(body.moduleId, body.nodeName)
    except installer.InstallBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, installer.InstallError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/comfyui/nodes/tasks")
def comfyui_install_tasks() -> list[dict]:
    """Recent install tasks, newest first (in-memory; cleared on restart)."""
    return installer.list_tasks()


@router.get("/comfyui/nodes/tasks/{task_id}")
def comfyui_install_task(task_id: str) -> dict:
    task = installer.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Unknown install task.")
    return task


@router.post("/comfyui/restart")
def restart_comfyui() -> dict:
    """Ask ComfyUI-Manager to reboot; otherwise return relaunch instructions."""
    return installer.restart_comfyui()
