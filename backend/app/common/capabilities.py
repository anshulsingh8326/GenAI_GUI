"""Capability registry - which generation modules exist, and what the roadmap plans.

`installed()` is manifest-driven: every `app/GenModules/<module-id>/manifest.json`
that parses is a live capability. It stays empty until the first GenModule lands -
callers report that honestly instead of inventing capabilities.

`PLANNED` mirrors docs/PLAN.md §8 and the GUI nav (frontend/src/lib/nav.ts):
"mock" = the GUI page exists but generation is still simulated, "soon" = not
built yet. Keep in sync with nav.ts when the feature ladder moves.
"""

from __future__ import annotations

import json
from pathlib import Path

GENMODULES_DIR = Path(__file__).resolve().parent.parent / "GenModules"

PLANNED: list[dict] = [
    {"id": "text-to-image", "name": "Text -> Image", "group": "image", "status": "mock"},
    {"id": "image-to-image", "name": "Image -> Image", "group": "image", "status": "soon"},
    {"id": "edit-image", "name": "Edit Image", "group": "image", "status": "soon"},
    {"id": "face-swap", "name": "Face Swap", "group": "image", "status": "soon"},
    {"id": "characters", "name": "Characters", "group": "image", "status": "mock"},
    {"id": "influencer", "name": "Influencer", "group": "image", "status": "soon"},
    {"id": "game-assets", "name": "Game Assets", "group": "image", "status": "mock"},
    {"id": "image-to-video", "name": "Image -> Video", "group": "video", "status": "soon"},
    {"id": "text-to-video", "name": "Text -> Video", "group": "video", "status": "soon"},
    {"id": "video-to-video", "name": "Video -> Video", "group": "video", "status": "soon"},
    {"id": "text-to-speech", "name": "Text to Speech", "group": "audio", "status": "soon"},
    {"id": "music", "name": "Music", "group": "audio", "status": "soon"},
    {"id": "sfx-foley", "name": "SFX & Foley", "group": "audio", "status": "soon"},
]


def installed() -> list[dict]:
    """GenModules present on disk (folder + parsable manifest.json)."""
    found: list[dict] = []
    if not GENMODULES_DIR.is_dir():
        return found
    for folder in sorted(p for p in GENMODULES_DIR.iterdir() if p.is_dir()):
        if folder.name.startswith("_"):
            continue  # _template and friends are scaffolding, not capabilities
        manifest_file = folder / "manifest.json"
        if not manifest_file.is_file():
            continue
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue  # broken manifest = not a capability; pack validation reports it later
        found.append(
            {
                "id": folder.name,
                "name": str(manifest.get("name") or folder.name),
                "group": manifest.get("group"),
                "status": "installed",
            }
        )
    return found


def snapshot() -> dict:
    """Both halves, for the API/MCP surfaces."""
    return {"installed": installed(), "planned": PLANNED}
