"""Jobs service - persistent job records.

The GUI creates a job when a generation starts, streams stage/progress patches
into it, and marks it done/failed. Execution itself is still simulated in the
GUI (mock runner) until the ComfyUI pipeline lands - `complete_mock()` is the
mock-phase stand-in for "the engine wrote outputs into the library" and is
deleted when the real runner arrives.
"""

from __future__ import annotations

import json
from time import time

from app.common import db
from app.library import placeholders, service as library

SEQ_KEY = "job_seq"
SEQ_START = 140  # first issued id is #141 - keeps continuity with the mock era

_UPDATABLE = {
    "status": "status",
    "progress": "progress",
    "enhancedPrompt": "enhanced_prompt",
    "stages": "stages_json",
    "resultIds": "result_ids_json",
    "error": "error",
}


def now_ms() -> int:
    return int(time() * 1000)


def _row_to_job(row) -> dict:
    return {
        "id": row["id"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "status": row["status"],
        "progress": row["progress"] or 0,
        "tab": row["tab"] or "",
        "modelId": row["model_id"] or "",
        "modelName": row["model_name"] or "",
        "recipe": row["recipe"] or "",
        "prompt": row["prompt"] or "",
        "enhancedPrompt": row["enhanced_prompt"],
        "seed": row["seed"] or 0,
        "params": _load(row["params_json"], {}),
        "stages": _load(row["stages_json"], []),
        "resultIds": _load(row["result_ids_json"], []),
        "error": row["error"],
    }


def _load(raw: str | None, fallback):
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except ValueError:
        return fallback


def _dump(value) -> str:
    return json.dumps(value or [])


def _next_id(conn) -> str:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (SEQ_KEY,)).fetchone()
    n = int(row["value"]) if row else SEQ_START
    n += 1
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (SEQ_KEY, str(n)),
    )
    return f"#{n}"


def create_job(payload: dict) -> dict:
    with db.connection() as conn:
        job_id = _next_id(conn)
        conn.execute(
            """
            INSERT INTO jobs (id, created_at, updated_at, status, tab, module, model_id,
                              model_name, recipe, prompt, seed, params_json, stages_json,
                              result_ids_json)
            VALUES (:id, :now, :now, 'running', :tab, 'text-to-image', :model_id,
                    :model_name, :recipe, :prompt, :seed, :params, :stages, '[]')
            """,
            {
                "id": job_id,
                "now": now_ms(),
                "tab": payload.get("tab") or "",
                "model_id": payload.get("modelId") or "",
                "model_name": payload.get("modelName") or "",
                "recipe": payload.get("recipe") or "",
                "prompt": payload.get("prompt") or "",
                "seed": int(payload.get("seed") or 0),
                "params": _dump(payload.get("params") or {}),
                "stages": _dump(payload.get("stages") or []),
            },
        )
    job = get_job(job_id)
    assert job is not None
    return job


def get_job(job_id: str) -> dict | None:
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_job(row) if row else None


def list_jobs(limit: int = 80) -> list[dict]:
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_job(r) for r in rows]


def count_jobs(status: str | None = None) -> int:
    with db.connection() as conn:
        if status is None:
            row = conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM jobs WHERE status = ?", (status,)
            ).fetchone()
    return int(row["n"])


def update_job(job_id: str, patch: dict) -> dict | None:
    fields: dict = {}
    for key, column in _UPDATABLE.items():
        if key in patch:
            value = patch[key]
            if column.endswith("_json"):
                value = _dump(value)
            if column == "progress":
                value = max(0, min(100, int(value or 0)))
            fields[column] = value
    if not fields:
        return get_job(job_id)
    assignments = ", ".join(f"{col} = :{col}" for col in fields)
    with db.connection() as conn:
        conn.execute(
            f"UPDATE jobs SET {assignments}, updated_at = :updated WHERE id = :id",
            {**fields, "updated": now_ms(), "id": job_id},
        )
    return get_job(job_id)


# --------------------------------------------------------------------------- mock phase


def complete_mock(job_id: str, count: int = 1, width: int = 1024, height: int = 1024) -> dict | None:
    """MOCK PHASE: write placeholder PNGs into the library as this job's results.

    Stands in for "engine wrote outputs to the library + rows" until the real
    ComfyUI pipeline lands; the response shape stays the same afterwards.
    """
    job = get_job(job_id)
    if not job:
        return None

    count = max(1, min(int(count or 1), 8))
    assets = []
    for i in range(count):
        label = (job["prompt"].split(",")[0] or "image").strip()[:40]
        data = placeholders.make_placeholder_png(job["prompt"] or label, i, width, height)
        asset = library.add_bytes(
            data,
            f"mock-{job_id.strip('#')}-{i + 1}.png",
            label=label,
            prompt=job["prompt"],
            model=job["modelName"],
            seed=job["seed"] + i,
            tags=[job["tab"] or "t2i", "mock"],
            origin_job=job_id,
        )
        assets.append(asset)

    updated = update_job(
        job_id,
        {
            "status": "done",
            "progress": 100,
            "resultIds": [a["id"] for a in assets],
        },
    )
    return {"job": updated, "assets": assets}
