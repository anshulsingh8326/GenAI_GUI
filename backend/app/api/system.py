"""System routes: health + info for the GUI diagnostics footer."""

from __future__ import annotations

import platform
import sys

from fastapi import APIRouter

from app import APP_NAME, __version__
from app.common import db, paths, settings_store

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    return {"ok": True, "app": APP_NAME, "version": __version__}


@router.get("/system/info")
def system_info() -> dict:
    _, initialized = settings_store.load()
    return {
        "app": APP_NAME,
        "version": __version__,
        "python": platform.python_version(),
        "platform": sys.platform,
        "dataDir": str(paths.DATA_DIR),
        "settingsFile": str(paths.SETTINGS_FILE),
        "settingsInitialized": initialized,
        "dbFile": str(paths.DB_FILE),
        "dbTables": db.table_names(),
    }
