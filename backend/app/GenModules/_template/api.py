"""REST router for this GenModule - thin: validate, call the service, return.

Mount it in `backend/app/api/__init__.py`:

    from app.GenModules.<module-id> import api as <module>_api
    router.include_router(<module>_api.router)

Then add the row to the endpoint table in backend/README.md.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/template", tags=["template"])

# @router.post("/jobs")
# def create(payload: TemplateJobRequest) -> dict:
#     """Compose + submit; returns the job record (id owned by the backend)."""
#     return service.start(payload)
