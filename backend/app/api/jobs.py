"""Job routes - create, inspect and progress pipeline run records.

`mock-complete` is mock-phase scaffolding (see app/jobs/service.py); it goes
away when the real ComfyUI runner lands, and nothing else changes.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.jobs import service

router = APIRouter(tags=["jobs"])


class MockCompleteRequest(BaseModel):
    count: int = 1
    width: int = 1024
    height: int = 1024


@router.get("/jobs")
def list_jobs(limit: int = 80) -> list[dict]:
    return service.list_jobs(limit=limit)


@router.post("/jobs")
def create_job(payload: dict) -> dict:
    return service.create_job(payload)


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.patch("/jobs/{job_id}")
def update_job(job_id: str, patch: dict) -> dict:
    job = service.update_job(job_id, patch)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/mock-complete")
def complete_mock(job_id: str, req: MockCompleteRequest | None = None) -> dict:
    req = req or MockCompleteRequest()
    result = service.complete_mock(job_id, count=req.count, width=req.width, height=req.height)
    if result is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return result
