"""Library service - the asset store.

Assets are files on disk + rows in SQLite:
- the library folder (settings `folders.library`) is the source of truth for
  files - a scan imports anything dropped in there;
- rows add metadata: favorite, tags, prompt/model, seed, dimensions, hash.

Thumbnails are generated on demand (Pillow) into `data/thumbnails/` and never
live inside the library folder, so scans can't pick them up. SVG files have no
raster thumbnail - the thumb endpoint falls back to the original file.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from time import time

from PIL import Image, ImageOps

from app.common import db, paths, settings_store

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".svg"}
IMAGE_MEDIA = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
}
SKIP_DIRS = {"trash", "thumbnails"}

THUMB_MAX = 512
MAX_IMPORT_BYTES = 128 * 1024 * 1024  # local single-user guard


def now_ms() -> int:
    return int(time() * 1000)


def library_dir() -> Path:
    """The configured library folder (created on demand)."""
    values, _ = settings_store.load()
    raw = ((values.get("folders") or {}).get("library") or "").strip()
    folder = Path(raw) if raw else paths.default_folders()["library"]
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def media_type_for(path: Path) -> str:
    return IMAGE_MEDIA.get(path.suffix.lower(), "application/octet-stream")


# --------------------------------------------------------------------------- row helpers


def _row_to_asset(row) -> dict:
    path = Path(row["path"]) if row["path"] else None
    thumb = Path(row["thumb_path"]) if row["thumb_path"] else None
    return {
        "id": row["id"],
        "kind": row["kind"],
        "url": f"/api/assets/{row['id']}/file",
        "thumbUrl": f"/api/assets/{row['id']}/thumb",
        "label": row["label"] or "",
        "prompt": row["prompt"] or "",
        "model": row["model"] or "",
        "seed": row["seed"] or 0,
        "createdAt": row["created_at"] or 0,
        "favorite": bool(row["favorite"]),
        "tags": _load_tags(row["tags_json"]),
        "nsfw": bool(row["nsfw"]),
        "width": row["width"],
        "height": row["height"],
        "bytes": row["bytes"],
        "originJob": row["origin_job"],
        "_path": str(path) if path else None,
        "_thumb": str(thumb) if thumb else None,
    }


def _load_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        import json

        tags = json.loads(raw)
        return [str(t) for t in tags] if isinstance(tags, list) else []
    except ValueError:
        return []


def _public(asset: dict) -> dict:
    """Strip internal keys before returning to the API."""
    return {k: v for k, v in asset.items() if not k.startswith("_")}


def _unique_path(folder: Path, filename: str) -> Path:
    safe = re.sub(r"[^\w.\- ]+", "_", filename).strip() or "image.png"
    candidate = folder / safe
    stem, suffix = candidate.stem, candidate.suffix
    n = 1
    while candidate.exists():
        candidate = folder / f"{stem}-{n}{suffix}"
        n += 1
    return candidate


# --------------------------------------------------------------------------- queries


def list_assets(limit: int = 500) -> list[dict]:
    scan_library()
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT * FROM assets ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_public(_row_to_asset(r)) for r in rows]


def get_asset(asset_id: str) -> dict | None:
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    return _row_to_asset(row) if row else None


def count_assets() -> int:
    """Row count only - no folder scan, so it stays cheap for status surfaces."""
    with db.connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM assets").fetchone()
    return int(row["n"])


def file_path(asset_id: str) -> tuple[Path, dict] | None:
    asset = get_asset(asset_id)
    if not asset or not asset["_path"]:
        return None
    path = Path(asset["_path"])
    if not path.is_file():
        return None
    return path, asset


# --------------------------------------------------------------------------- mutations


def add_file(
    path: Path,
    *,
    label: str | None = None,
    prompt: str = "",
    model: str = "",
    seed: int = 0,
    tags: list[str] | None = None,
    origin_job: str | None = None,
) -> dict:
    """Register a file that already exists on disk (scan, mock outputs, engine outputs)."""
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    width = height = None
    if path.suffix.lower() != ".svg":
        try:
            with Image.open(path) as img:
                width, height = img.size
        except Exception:  # noqa: BLE001 - metadata is best-effort
            pass

    asset_id = f"a-{uuid.uuid4().hex[:10]}"
    row = {
        "id": asset_id,
        "kind": "image",
        "path": str(path),
        "thumb_path": None,
        "label": label or path.stem[:60],
        "prompt": prompt,
        "model": model,
        "seed": int(seed or 0),
        "created_at": now_ms(),
        "favorite": 0,
        "tags_json": _dump_tags(tags),
        "nsfw": 0,
        "width": width,
        "height": height,
        "bytes": len(data),
        "sha256": digest,
        "origin_job": origin_job,
    }
    with db.connection() as conn:
        conn.execute(
            """
            INSERT INTO assets (id, kind, path, thumb_path, label, prompt, model, seed,
                                created_at, favorite, tags_json, nsfw, width, height, bytes,
                                sha256, origin_job)
            VALUES (:id, :kind, :path, :thumb_path, :label, :prompt, :model, :seed,
                    :created_at, :favorite, :tags_json, :nsfw, :width, :height, :bytes,
                    :sha256, :origin_job)
            """,
            row,
        )
    return _public(_row_to_asset({**row, "path": str(path)}))


def add_bytes(
    data: bytes,
    filename: str,
    *,
    label: str | None = None,
    prompt: str = "",
    model: str = "",
    seed: int = 0,
    tags: list[str] | None = None,
    origin_job: str | None = None,
) -> dict:
    """Save bytes into the library folder and register them."""
    if len(data) > MAX_IMPORT_BYTES:
        raise ValueError("File is too large for the library (128 MB limit)")
    folder = library_dir()
    suffix = Path(filename).suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        raise ValueError(f"Unsupported file type '{suffix or filename}'")
    target = _unique_path(folder, filename)
    target.write_bytes(data)
    return add_file(
        target,
        label=label,
        prompt=prompt,
        model=model,
        seed=seed,
        tags=tags,
        origin_job=origin_job,
    )


def set_fields(asset_id: str, patch: dict) -> dict | None:
    """Update editable metadata: favorite, label, tags, nsfw."""
    fields: dict = {}
    if "favorite" in patch:
        fields["favorite"] = 1 if patch["favorite"] else 0
    if "label" in patch:
        fields["label"] = str(patch["label"])[:120]
    if "tags" in patch:
        fields["tags_json"] = _dump_tags(patch["tags"])
    if "nsfw" in patch:
        fields["nsfw"] = 1 if patch["nsfw"] else 0
    if not fields:
        return get_asset(asset_id)
    assignments = ", ".join(f"{k} = :{k}" for k in fields)
    with db.connection() as conn:
        conn.execute(
            f"UPDATE assets SET {assignments} WHERE id = :id", {**fields, "id": asset_id}
        )
    return get_asset(asset_id)


def trash_asset(asset_id: str) -> dict | None:
    """Move the file into data/trash (recoverable) and drop the row.

    Restoring = copy the file back into the library folder; the next scan
    re-imports it. Nothing is ever hard-deleted.
    """
    asset = get_asset(asset_id)
    if not asset:
        return None
    moved_to = None
    if asset["_path"]:
        source = Path(asset["_path"])
        if source.is_file():
            paths.TRASH_DIR.mkdir(parents=True, exist_ok=True)
            target = _unique_path(paths.TRASH_DIR, source.name)
            source.replace(target)
            moved_to = str(target)
    thumb = asset["_thumb"]
    if thumb and Path(thumb).is_file():
        Path(thumb).unlink(missing_ok=True)
    with db.connection() as conn:
        conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
    return {"id": asset_id, "movedTo": moved_to}


# --------------------------------------------------------------------------- scan


def scan_library() -> int:
    """Import image files found in the library folder but not yet in the DB."""
    folder = library_dir()
    with db.connection() as conn:
        known = {row["path"] for row in conn.execute("SELECT path FROM assets").fetchall()}
    imported = 0
    for file in _walk_images(folder):
        if str(file) not in known:
            try:
                add_file(file)
                imported += 1
            except OSError:
                continue
    return imported


def _walk_images(folder: Path):
    for entry in sorted(folder.rglob("*")):
        if entry.is_dir():
            continue
        if entry.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if any(part.lower() in SKIP_DIRS for part in entry.parts):
            continue
        yield entry


# --------------------------------------------------------------------------- thumbnails


def ensure_thumb(asset_id: str) -> tuple[Path, dict] | None:
    """Return (thumb_path, asset) - generating the thumbnail on first request."""
    found = file_path(asset_id)
    if not found:
        return None
    source, asset = found
    if source.suffix.lower() == ".svg":
        return source, asset  # browsers render SVG directly
    if asset["_thumb"] and Path(asset["_thumb"]).is_file():
        return Path(asset["_thumb"]), asset

    paths.THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    target = paths.THUMBS_DIR / f"{asset_id}.jpg"
    try:
        with Image.open(source) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            img.thumbnail((THUMB_MAX, THUMB_MAX))
            img.save(target, "JPEG", quality=82)
    except Exception:  # noqa: BLE001 - fall back to the original file
        return source, asset

    with db.connection() as conn:
        conn.execute("UPDATE assets SET thumb_path = ? WHERE id = ?", (str(target), asset_id))
    return target, asset


def _dump_tags(tags: list[str] | None) -> str:
    import json

    return json.dumps([str(t) for t in (tags or [])])
