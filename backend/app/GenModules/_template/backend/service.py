"""Template GenModule service - a complete, working scaffold.

This module deliberately renders a deterministic SVG card locally instead of
calling ComfyUI. That keeps the starter usable without a model or GPU while
still exercising every host connection a real module needs:

- shared job records and stage/progress persistence;
- shared library writes and result asset ids;
- module-scoped history, soft delete and library trash;
- the same validation used by `/validate` and `/jobs`.

Replace ``_render_svg`` with your engine pipeline. Keep the job creation,
stage tracker, library collection and deletion code - they are the portable
host contract. Engine-backed modules should also read the guide's
"engine-backed module" notes (live readiness, resume, cancel).
"""

from __future__ import annotations

import asyncio
import html
import json
import random
import textwrap
from pathlib import Path
from typing import Any

from app.jobs import service as jobs
from app.library import service as library

MODULE_ID = "template"
MODULE_NAME = "Template"
RECIPE_ID = "template-card-v1"
TAB_ID = "template"

_PACK_PATH = Path(__file__).resolve().parent / "pack" / "options.json"
PACK = json.loads(_PACK_PATH.read_text(encoding="utf-8"))
DEFAULTS = dict(PACK["defaults"])
SIZE = dict(PACK["size"])
BATCH = dict(PACK["batch"])
LIMITS = dict(PACK["limits"])
ACCENTS = tuple(PACK["accents"])

PROMPT_MAX_CHARS = int(LIMITS["promptMaxChars"])
MIN_BATCH = int(BATCH["min"])
MAX_BATCH = int(BATCH["max"])
BATCH_STEP = int(BATCH["step"])
MIN_SIZE = int(SIZE["min"])
MAX_SIZE = int(SIZE["max"])
SIZE_STEP = int(SIZE["step"])
SIZE_VALUES = tuple(
    sorted(
        {
            int(value)
            for value in SIZE["values"]
            if MIN_SIZE <= int(value) <= MAX_SIZE
        }
    )
)
_ACCENT_IDS = {item["id"] for item in ACCENTS}

STAGE_DEFS = (
    ("render", "Render canvas"),
    ("collect", "Collect results"),
)

_TASKS: dict[str, asyncio.Task] = {}
_CANCEL: dict[str, asyncio.Event] = {}


class ValidationError(Exception):
    def __init__(self, errors: list[dict], warnings: list[dict] | None = None):
        self.errors = errors
        self.warnings = warnings or []
        first = errors[0]["message"] if errors else "Invalid template request"
        super().__init__(first)


class EngineError(Exception):
    """The generation engine is unavailable or rejected the request."""


class JobCancelled(Exception):
    pass


def _issue(code: str, message: str, field: str | None = None, **extra: Any) -> dict:
    item: dict[str, Any] = {"code": code, "message": message}
    if field:
        item["field"] = field
    item.update(extra)
    return item


def _initial_stages() -> list[dict]:
    return [
        {
            "id": stage_id,
            "label": label,
            "status": "pending",
            "detail": "",
            "startedAt": None,
            "finishedAt": None,
            "durationMs": None,
        }
        for stage_id, label in STAGE_DEFS
    ]


def _read_size(raw: Any, field: str, errors: list[dict]) -> int:
    """Read an integer canvas dimension; reject outside the hard limits.

    The frontend may clamp a *restored* form to the current limits and tell the
    user, but API input is never silently clamped.
    """
    fallback = 1024
    try:
        value = int(raw if raw is not None else fallback)
    except (TypeError, ValueError):
        errors.append(_issue(f"invalid_{field}", f"{field.title()} must be a number.", field))
        return fallback
    if value < MIN_SIZE or value > MAX_SIZE:
        errors.append(
            _issue(
                f"{field}_out_of_range",
                f"{field.title()} must be between {MIN_SIZE} and {MAX_SIZE}.",
                field,
                min=MIN_SIZE,
                max=MAX_SIZE,
            )
        )
        return max(MIN_SIZE, min(MAX_SIZE, value))
    return value


def pack_snapshot() -> dict:
    """Secret-free starter pack summary for debug/ops."""
    return {
        "id": MODULE_ID,
        "name": MODULE_NAME,
        "version": "0.1.0",
        "packVersion": PACK.get("version", 1),
        "recipes": [{"id": RECIPE_ID, "label": "Template card"}],
        "defaults": dict(DEFAULTS),
        "size": dict(SIZE),
        "batch": dict(BATCH),
        "note": "Starter pack; replace with your tracked module pack.",
    }


def catalog_snapshot() -> dict:
    """Controls, defaults and ranges from the starter's tracked pack."""
    return {
        "ok": True,
        "moduleId": MODULE_ID,
        "defaults": dict(DEFAULTS),
        "limits": {
            "promptMaxChars": PROMPT_MAX_CHARS,
            "minBatch": MIN_BATCH,
            "maxBatch": MAX_BATCH,
            "batchStep": BATCH_STEP,
            "minSize": MIN_SIZE,
            "maxSize": MAX_SIZE,
            "sizeStep": SIZE_STEP,
            "sizeValues": list(SIZE_VALUES),
            "pollIntervalSeconds": float(LIMITS["pollIntervalSeconds"]),
        },
        "accents": [dict(item) for item in ACCENTS],
    }


def _normalize(payload: Any) -> dict:
    """Validate and normalize once; used by both /validate and /jobs."""
    prompt = str(getattr(payload, "prompt", "") or "").strip()
    accent = str(getattr(payload, "accent", "") or "lavender").strip()
    width_raw = getattr(payload, "width", None)
    height_raw = getattr(payload, "height", None)
    batch_raw = getattr(payload, "batch", None)
    seed_raw = getattr(payload, "seed", None)
    lock_seed = bool(getattr(payload, "lockSeed", False))

    errors: list[dict] = []
    warnings: list[dict] = []

    if not prompt:
        errors.append(_issue("prompt_required", "Write a prompt first.", "prompt"))
    elif len(prompt) > PROMPT_MAX_CHARS:
        errors.append(
            _issue(
                "prompt_too_long",
                f"Keep the prompt under {PROMPT_MAX_CHARS} characters.",
                "prompt",
                max=PROMPT_MAX_CHARS,
            )
        )

    width = _read_size(width_raw, "width", errors)
    height = _read_size(height_raw, "height", errors)

    try:
        batch = int(batch_raw if batch_raw is not None else MIN_BATCH)
    except (TypeError, ValueError):
        batch = MIN_BATCH
        errors.append(_issue("invalid_batch", "Batch must be a number.", "batch"))
    if batch < MIN_BATCH or batch > MAX_BATCH:
        errors.append(
            _issue(
                "batch_out_of_range",
                f"Batch must be between {MIN_BATCH} and {MAX_BATCH}.",
                "batch",
                min=MIN_BATCH,
                max=MAX_BATCH,
            )
        )
        batch = max(MIN_BATCH, min(MAX_BATCH, batch))

    if accent not in _ACCENT_IDS:
        errors.append(
            _issue(
                "unknown_accent",
                "Choose one of the listed accents.",
                "accent",
                options=sorted(_ACCENT_IDS),
            )
        )

    if seed_raw is None:
        seed = random.randint(0, 0xFFFFFFFF)
    else:
        try:
            seed = int(seed_raw) & 0xFFFFFFFF
        except (TypeError, ValueError):
            seed = random.randint(0, 0xFFFFFFFF)
            errors.append(_issue("invalid_seed", "Seed must be a number.", "seed"))

    if errors:
        raise ValidationError(errors, warnings)

    return {
        "prompt": prompt,
        "accent": accent,
        "width": width,
        "height": height,
        "batch": batch,
        "seed": seed,
        "lockSeed": lock_seed,
    }


def validate_payload(payload: Any) -> dict:
    normalized = _normalize(payload)
    return {"valid": True, "normalized": normalized, "warnings": []}


def _is_template_job(job: dict | None) -> bool:
    return bool(job) and job.get("module") == MODULE_ID


def _reconcile_restarted_job(job: dict) -> dict:
    """Mark a job that was left running by a backend restart.

    A real engine-backed module should resume a persisted engine prompt id
    instead. The starter has no engine, so it can only fail honestly.
    """
    if job.get("status") == "running" and job.get("id") not in _TASKS:
        updated = jobs.update_job(
            str(job["id"]),
            {
                "status": "error",
                "error": "The backend restarted before this render finished. Start a new job.",
            },
        )
        return updated or job
    return job


async def start_job(payload: Any) -> dict:
    normalized = _normalize(payload)
    params = {
        **normalized,
        "modelId": MODULE_ID,
        "modelName": MODULE_NAME,
        "recipeId": RECIPE_ID,
    }
    job = jobs.create_job(
        {
            "tab": TAB_ID,
            "module": MODULE_ID,
            "modelId": MODULE_ID,
            "modelName": MODULE_NAME,
            "recipe": RECIPE_ID,
            "prompt": normalized["prompt"],
            "seed": normalized["seed"],
            "params": params,
            "stages": _initial_stages(),
        }
    )
    cancel_event = asyncio.Event()
    _CANCEL[job["id"]] = cancel_event
    _TASKS[job["id"]] = asyncio.create_task(
        _run_job(job["id"], normalized, cancel_event),
        name=f"template-{job['id']}",
    )
    return jobs.get_job(job["id"]) or job


def get_job(job_id: str) -> dict | None:
    job = jobs.get_job(job_id)
    if not _is_template_job(job):
        return None
    return _reconcile_restarted_job(job or {})


def list_jobs(limit: int = 80) -> list[dict]:
    rows = jobs.list_jobs(limit=limit, module=MODULE_ID)
    return [_reconcile_restarted_job(job) for job in rows]


async def cancel_job(job_id: str) -> dict | None:
    job = get_job(job_id)
    if job is None:
        return None
    if job.get("status") in {"done", "error"}:
        return job
    event = _CANCEL.get(job_id)
    if event is not None:
        event.set()
    if job_id in _TASKS:
        # The runner owns the final status and will persist the cancellation.
        return jobs.get_job(job_id) or job

    stages = job.get("stages") or _initial_stages()
    for stage in stages:
        if stage.get("status") == "running":
            stage["status"] = "error"
            stage["detail"] = "Cancelled by user"
            stage["finishedAt"] = jobs.now_ms()
            break
    jobs.update_job(
        job_id,
        {"status": "error", "error": "Cancelled by user", "stages": stages},
    )
    return jobs.get_job(job_id) or job


def delete_job(job_id: str, *, delete_assets: bool = True) -> dict | None:
    job = get_job(job_id)
    if job is None:
        return None
    if job.get("status") in {"queued", "running"}:
        raise ValidationError(
            [_issue("job_running", "Cancel this job before deleting it.", "jobId")]
        )

    trashed, missing = _trash_job_assets(job) if delete_assets else ([], [])
    if not jobs.delete_job(job_id):
        return None
    _CANCEL.pop(job_id, None)
    _TASKS.pop(job_id, None)
    return {
        "id": job_id,
        "deleted": True,
        "assetsTrashed": trashed,
        "assetsMissing": missing,
    }


def _trash_job_assets(job: dict) -> tuple[list[str], list[str]]:
    trashed: list[str] = []
    missing: list[str] = []
    for asset_id in job.get("resultIds") or []:
        asset = library.trash_asset(str(asset_id))
        if asset is None:
            missing.append(str(asset_id))
        else:
            trashed.append(str(asset["id"]))
    return trashed, missing


def clear_history(*, delete_assets: bool = False) -> dict:
    # Use the module service, not jobs.list_jobs directly: it reconciles a job
    # left running by a backend restart before deciding whether clear is safe.
    current = list_jobs(limit=10_000)
    active = [
        str(job["id"]) for job in current if job.get("status") in {"queued", "running"}
    ]
    if active:
        raise ValidationError(
            [
                _issue(
                    "job_running",
                    "Cancel the active generation before clearing this chat.",
                    "jobId",
                    jobIds=active,
                )
            ]
        )

    job_ids: list[str] = []
    trashed: list[str] = []
    missing: list[str] = []
    seen_assets: set[str] = set()
    for job in current:
        job_id = str(job["id"])
        if delete_assets:
            job_trashed, job_missing = _trash_job_assets(job)
            for asset_id in job_trashed:
                if asset_id not in seen_assets:
                    seen_assets.add(asset_id)
                    trashed.append(asset_id)
            for asset_id in job_missing:
                if asset_id not in seen_assets:
                    seen_assets.add(asset_id)
                    missing.append(asset_id)
        if jobs.delete_job(job_id):
            job_ids.append(job_id)
            _CANCEL.pop(job_id, None)
            _TASKS.pop(job_id, None)

    return {
        "deleted": len(job_ids),
        "jobIds": job_ids,
        "assetsTrashed": trashed,
        "assetsMissing": missing,
    }


class _StageTracker:
    def __init__(self, job_id: str, stages: list[dict] | None = None):
        self.job_id = job_id
        self.stages = [dict(item) for item in (stages or _initial_stages())]
        self.active: str | None = None
        self.progress_value = 0

    def _find(self, stage_id: str) -> dict:
        for stage in self.stages:
            if stage.get("id") == stage_id:
                return stage
        stage = {"id": stage_id, "label": stage_id, "status": "pending", "detail": ""}
        self.stages.append(stage)
        return stage

    def _save(self) -> None:
        jobs.update_job(
            self.job_id, {"stages": self.stages, "progress": self.progress_value}
        )

    def start(self, stage_id: str, detail: str = "") -> None:
        stage = self._find(stage_id)
        stage["status"] = "running"
        stage["startedAt"] = jobs.now_ms()
        stage.pop("finishedAt", None)
        stage.pop("durationMs", None)
        if detail:
            stage["detail"] = detail
        self.active = stage_id
        self._save()

    def done(self, stage_id: str, detail: str = "") -> None:
        stage = self._find(stage_id)
        finished = jobs.now_ms()
        stage["status"] = "done"
        stage["finishedAt"] = finished
        stage["durationMs"] = max(0, finished - int(stage.get("startedAt") or finished))
        if detail:
            stage["detail"] = detail
        if self.active == stage_id:
            self.active = None
        self._save()

    def fail(self, stage_id: str, detail: str) -> None:
        stage = self._find(stage_id)
        finished = jobs.now_ms()
        stage["status"] = "error"
        stage["finishedAt"] = finished
        stage["durationMs"] = max(0, finished - int(stage.get("startedAt") or finished))
        stage["detail"] = detail[:1000]
        if self.active == stage_id:
            self.active = None
        self._save()

    def progress(self, value: int) -> None:
        self.progress_value = max(0, min(100, int(value)))
        self._save()


async def _run_job(
    job_id: str, normalized: dict, cancel_event: asyncio.Event
) -> None:
    tracker = _StageTracker(job_id)
    assets: list[dict] = []
    try:
        tracker.start("render", "Rendering the placeholder canvas...")
        batch = int(normalized["batch"])
        for index in range(batch):
            if cancel_event.is_set():
                raise JobCancelled()
            data = _render_svg(
                str(normalized["prompt"]),
                str(normalized["accent"]),
                int(normalized["width"]),
                int(normalized["height"]),
                int(normalized["seed"]) + index,
                index,
            )
            filename = f"template-{job_id.lstrip('#')}-{index + 1}.svg"
            asset = await asyncio.to_thread(
                library.add_bytes,
                data,
                filename,
                label=(str(normalized["prompt"]).split(",")[0] or "template")[:60],
                prompt=str(normalized["prompt"]),
                model=MODULE_NAME,
                seed=(int(normalized["seed"]) + index) & 0xFFFFFFFF,
                tags=["template", "placeholder", f"accent:{normalized['accent']}"],
                origin_job=job_id,
            )
            assets.append(asset)
            tracker.progress(20 + int(65 * (index + 1) / batch))

        if cancel_event.is_set():
            raise JobCancelled()
        tracker.done("render", f"{len(assets)} canvas(es)")
        tracker.start("collect", "Registering results in the library...")
        tracker.progress(100)
        tracker.done("collect", f"{len(assets)} asset(s) in the Library")
        jobs.update_job(
            job_id,
            {
                "status": "done",
                "progress": 100,
                "resultIds": [asset["id"] for asset in assets],
            },
        )
    except JobCancelled:
        stages = tracker.stages
        for stage in stages:
            if stage.get("status") == "running":
                stage["status"] = "error"
                stage["detail"] = "Cancelled by user"
                stage["finishedAt"] = jobs.now_ms()
        jobs.update_job(
            job_id,
            {
                "status": "error",
                "error": "Cancelled by user; any completed results were kept.",
                "stages": stages,
                # Keep partial results linked so delete/clear can trash them.
                "resultIds": [asset["id"] for asset in assets],
            },
        )
    except Exception as err:  # noqa: BLE001 - persist a readable failure
        message = f"Template render failed: {err}"
        stages = tracker.stages
        for stage in stages:
            if stage.get("status") == "running":
                stage["status"] = "error"
                stage["detail"] = message[:1000]
                stage["finishedAt"] = jobs.now_ms()
        jobs.update_job(
            job_id,
            {
                "status": "error",
                "error": message,
                "stages": stages,
                # Partial results must stay linked, not orphaned in the library.
                "resultIds": [asset["id"] for asset in assets],
            },
        )
    finally:
        _TASKS.pop(job_id, None)
        _CANCEL.pop(job_id, None)


def _render_svg(
    prompt: str,
    accent: str,
    width: int,
    height: int,
    seed: int,
    index: int,
) -> bytes:
    palette = {
        "lavender": ("#171525", "#b9a7f2", "#2a2440"),
        "mint": ("#10201d", "#8be0c2", "#19342d"),
        "peach": ("#241713", "#f5b38f", "#3a241b"),
        "sky": ("#101b26", "#8ec8f0", "#1a2d3e"),
    }
    bg, fg, panel = palette.get(accent, palette["lavender"])
    radius = max(18, min(width, height) // 28)
    chars = max(24, width // 30)
    lines = textwrap.wrap(prompt.strip(), width=chars)[:9] or ["(empty prompt)"]
    line_height = max(26, min(64, height // 13))
    block_height = line_height * len(lines)
    start_y = height // 2 - block_height // 2 + line_height // 2
    body = "".join(
        f'<text x="50%" y="{start_y + i * line_height}" text-anchor="middle" '
        f'dominant-baseline="middle" fill="{fg}" font-size="{max(16, line_height - 12)}" '
        f'font-family="Segoe UI, system-ui, sans-serif" font-weight="600">'
        f"{html.escape(line)}</text>"
        for i, line in enumerate(lines)
    )
    footer = (
        f"seed {seed}  |  {width}x{height}  |  {index + 1}"
    )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="{bg}"/>
  <rect x="{radius}" y="{radius}" width="{width - radius * 2}" height="{height - radius * 2}" rx="{radius * 2}" fill="{panel}" stroke="{fg}" stroke-opacity="0.35" stroke-width="2"/>
  <circle cx="{width - radius * 3}" cy="{radius * 3}" r="{max(8, radius // 2)}" fill="{fg}" fill-opacity="0.8"/>
  {body}
  <text x="50%" y="{height - radius * 2}" text-anchor="middle" fill="{fg}" fill-opacity="0.65" font-size="{max(12, radius)}" font-family="Segoe UI, system-ui, sans-serif">{html.escape(footer)}</text>
  <text x="{radius * 3}" y="{radius * 3}" fill="{fg}" fill-opacity="0.75" font-size="{max(12, radius)}" font-family="Segoe UI, system-ui, sans-serif" font-weight="700">TEMPLATE</text>
</svg>"""
    return svg.encode("utf-8")
