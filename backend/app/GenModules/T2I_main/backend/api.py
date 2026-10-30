"""T2I_main REST router - thin: validate transport, call the service, return.

Mounted under `/api/t2i` by `app/api/__init__.py`. Every execution route uses
the same service validation as the GUI, so an API/agent caller cannot bypass
the pack's safe ranges or the engine hard limits.

Error shape:
- 422 `{code: "validation_error", message, errors: [...], warnings: [...]}`
- 503 `{code: "engine_error", message}`
- 500 `{code: "pack_error" | "internal_error", message}`
"""

from __future__ import annotations

import inspect
import logging
from functools import wraps
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query

from . import catalog, service, workflows
from .schema import T2IEnhanceRequest, T2IJobRequest

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/t2i", tags=["t2i"])


def _mapped(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Map service exceptions to HTTP once, without leaking a stack trace."""

    @wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            result = fn(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            return result
        except HTTPException:
            raise
        except service.ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "validation_error",
                    "message": str(exc),
                    "errors": exc.errors,
                    "warnings": exc.warnings,
                },
            ) from exc
        except service.EngineError as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": "engine_error", "message": str(exc)},
            ) from exc
        except (catalog.PackError, workflows.WorkflowError) as exc:
            logger.exception("[t2i] pack/workflow error")
            raise HTTPException(
                status_code=500,
                detail={"code": "pack_error", "message": str(exc)},
            ) from exc
        except Exception as exc:  # noqa: BLE001 - always return JSON to the GUI
            logger.exception("[t2i] unhandled API error")
            raise HTTPException(
                status_code=500,
                detail={"code": "internal_error", "message": str(exc) or "T2I backend error."},
            ) from exc

    return wrapper


@router.get("/catalog")
@_mapped
async def get_catalog(modelId: str | None = Query(default=None)) -> dict:
    """Everything the GUI needs to render the T2I controls, plus engine status."""
    return await service.catalog_snapshot(model_id=modelId)


@router.get("/pack")
@_mapped
def get_pack() -> dict:
    """Small, secret-free summary of the tracked module pack (debug/ops)."""
    return service.pack_info()


@router.get("/setup")
@_mapped
def get_setup() -> dict:
    """Missing-file/setup payload for the shared first-open modal."""
    return service.setup_info()


@router.post("/validate")
@_mapped
def validate(payload: T2IJobRequest) -> dict:
    """Validate without creating a job. Returns the normalized request + graph summary."""
    return service.validate_payload(payload)


@router.post("/enhance")
@_mapped
async def enhance(payload: T2IEnhanceRequest) -> dict:
    """Generate a prompt enhancement through Ollama or ComfyUI. No job is created."""
    return await service.enhance_prompt(payload)


@router.post("/jobs")
@_mapped
async def create_job(payload: T2IJobRequest) -> dict:
    """Validate, create a persistent job and run it in the background."""
    return await service.start_job(payload)


@router.get("/jobs")
@_mapped
def list_jobs(limit: int = Query(default=80, ge=1, le=200)) -> list[dict]:
    return service.list_jobs(limit=limit)


@router.delete("/jobs")
@_mapped
def clear_history(
    delete_assets: bool = Query(default=False, alias="deleteAssets"),
) -> dict:
    """Clear only this module's chat history; optionally trash its result images."""
    return service.clear_history(delete_assets=delete_assets)


@router.get("/jobs/{job_id}")
@_mapped
def get_job(job_id: str) -> dict:
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.delete("/jobs/{job_id}")
@_mapped
def delete_job(
    job_id: str,
    delete_assets: bool = Query(default=True, alias="deleteAssets"),
) -> dict:
    """Hide a terminal job; optionally move its result images to the library trash."""
    result = service.delete_job(job_id, delete_assets=delete_assets)
    if result is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return result


@router.post("/jobs/{job_id}/cancel")
@_mapped
async def cancel_job(job_id: str) -> dict:
    job = await service.cancel_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
