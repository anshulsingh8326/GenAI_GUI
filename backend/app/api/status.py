"""Status route - one snapshot endpoint for the top bar and Resources popover.

The GUI polls this on a short interval. When real-time job progress lands, this
snapshot becomes the initial state of a push channel - the shape stays.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.connectors import service

router = APIRouter(tags=["status"])


@router.get("/status")
async def get_status() -> dict:
    return await service.status_snapshot()
