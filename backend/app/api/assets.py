"""Asset routes - the library (list, import, edit, serve files + thumbnails)."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.library import service

router = APIRouter(tags=["library"])


@router.get("/assets")
def list_assets(favorites: bool = False, q: str | None = None, limit: int = 500) -> list[dict]:
    assets = service.list_assets(limit=limit)
    if favorites:
        assets = [a for a in assets if a["favorite"]]
    if q:
        needle = q.lower()
        assets = [
            a
            for a in assets
            if needle in (a["prompt"] or "").lower() or needle in (a["label"] or "").lower()
        ]
    return assets


@router.post("/assets/import")
async def import_asset(
    file: UploadFile = File(...),
    label: str | None = Form(None),
    tags: str | None = Form(None),
) -> dict:
    data = await file.read()
    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    try:
        return service.add_bytes(data, file.filename or "upload.png", label=label, tags=tag_list)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@router.patch("/assets/{asset_id}")
def update_asset(asset_id: str, patch: dict) -> dict:
    asset = service.set_fields(asset_id, patch)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


@router.delete("/assets/{asset_id}")
def trash_asset(asset_id: str) -> dict:
    result = service.trash_asset(asset_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return result


@router.get("/assets/{asset_id}/file")
def asset_file(asset_id: str) -> FileResponse:
    found = service.file_path(asset_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Asset file not found")
    path, _asset = found
    return FileResponse(
        path,
        media_type=service.media_type_for(path),
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/assets/{asset_id}/thumb")
def asset_thumb(asset_id: str) -> FileResponse:
    found = service.ensure_thumb(asset_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Asset file not found")
    path, _asset = found
    media_type = "image/jpeg" if path.suffix.lower() == ".jpg" else service.media_type_for(path)
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "public, max-age=3600"})
