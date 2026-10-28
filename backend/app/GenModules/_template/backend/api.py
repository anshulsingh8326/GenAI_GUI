"""Template GenModule REST router - thin: validate transport, call service, return.

Mounted under ``/api/template`` by ``app/api/__init__.py``. The starter keeps
the same route surface every module should expose so a future module can be
compared against it one-for-one.

Error shape:
- 422 ``{code: "validation_error", message, errors: [...], warnings: [...]}``
- 503 ``{code: "engine_error", message}``
- 500 ``{code: "internal_error", message}``
"""

from __future__ import annotations

import inspect
import logging
from functools import wraps
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query

from . import service
from .schema import TemplateJobRequest

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/template", tags=["template"])


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
        except Exception as exc:  # noqa: BLE001 - always return JSON to the GUI
            logger.exception("[template] unhandled API error")
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "internal_error",
                    # Never return a raw exception: it may include a local path.
                    "message": "Template backend error. Check the server log.",
                },
            ) from exc

    return wrapper


@router.get("/catalog")
@_mapped
def get_catalog() -> dict:
    """Controls, limits and defaults for the starter page."""
    return service.catalog_snapshot()


@router.get("/pack")
@_mapped
def get_pack() -> dict:
    """Secret-free starter pack summary."""
    return service.pack_snapshot()


@router.post("/validate")
@_mapped
def validate(payload: TemplateJobRequest) -> dict:
    """Validate without creating a job; the same normalizer powers /jobs."""
    return service.validate_payload(payload)


@router.post("/jobs")
@_mapped
async def create_job(payload: TemplateJobRequest) -> dict:
    """Validate, persist a job and run it in the background."""
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
    """Clear only this module's chat history; optionally trash its results."""
    return service.clear_history(delete_assets=delete_assets)


@router.get("/jobs/{job_id}")
@_mapped
def get_job(job_id: str) -> dict:
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/cancel")
@_mapped
async def cancel_job(job_id: str) -> dict:
    job = await service.cancel_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.delete("/jobs/{job_id}")
@_mapped
def delete_job(
    job_id: str,
    delete_assets: bool = Query(default=True, alias="deleteAssets"),
) -> dict:
    """Hide a terminal job; optionally move its results to the library trash."""
    result = service.delete_job(job_id, delete_assets=delete_assets)
    if result is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return result
