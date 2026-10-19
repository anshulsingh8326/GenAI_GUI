"""GenAI GUI backend - FastAPI app.

Dev:  uv run uvicorn app.main:app --reload --port 8766   (frontend runs on vite, proxies /api)
Prod: uv run uvicorn app.main:app --port 8766            (serves the built SPA from frontend/dist)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import APP_NAME, __version__
from .api import api
from .common import db, paths
from .connectors.service import maybe_autostart_comfyui

SPA_DIST = paths._REPO_ROOT / "frontend" / "dist"

# Explicit types for the built SPA. Windows' registry makes Python's mimetypes
# report .js as text/plain, which browsers refuse to execute as a module.
SPA_MEDIA_TYPES = {
    ".html": "text/html",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".map": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".wasm": "application/wasm",
    ".txt": "text/plain",
}


def spa_media_type(path: Path) -> str:
    return SPA_MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")


logger = logging.getLogger("uvicorn.error")  # uvicorn's configured logger - lands in the launch terminal


def _autostart_comfyui() -> None:
    """Opt-in boot step: run the user's ComfyUI launcher when the setting is enabled.

    The service guards everything (skips when ComfyUI is already reachable,
    debounces repeat spawns from --reload restarts). A failure here must never
    stop the backend from booting.
    """
    try:
        result = maybe_autostart_comfyui()
        if result is not None:
            logger.info("[comfyui] auto-start: %s", result["detail"])
    except Exception as err:  # noqa: BLE001 - boot continues no matter what
        logger.warning("[comfyui] auto-start failed: %s", err)


@asynccontextmanager
async def lifespan(_: FastAPI):
    _autostart_comfyui()
    yield


def create_app() -> FastAPI:
    paths.ensure_base_dirs()
    db.init_db()

    app = FastAPI(title=f"{APP_NAME} backend", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api)

    register_spa(app)
    return app


def register_spa(app: FastAPI) -> None:
    """Serve the built frontend (single process for users). No-op in dev when dist is missing."""

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if not SPA_DIST.exists():
            return JSONResponse(
                {"detail": "Frontend not built. Run `npm run build` in frontend/ or use vite dev server."},
                status_code=404,
            )
        candidate: Path = (SPA_DIST / full_path).resolve()
        if candidate.is_file() and str(candidate).startswith(str(SPA_DIST.resolve())):
            # Hashed asset names - safe to cache hard.
            return FileResponse(
                candidate,
                media_type=spa_media_type(candidate),
                headers={"Cache-Control": "public, max-age=31536000, immutable"},
            )
        # index.html (and SPA routes) must always revalidate so rebuilds show up.
        index = SPA_DIST / "index.html"
        return FileResponse(index, media_type=spa_media_type(index), headers={"Cache-Control": "no-store"})


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8766, reload=True)
