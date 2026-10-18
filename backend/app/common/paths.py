"""Filesystem paths: where the app keeps its data.

The data dir defaults to `<repo>/data` (dev-friendly, easy to inspect) and can
be overridden with the GENAI_DATA_DIR environment variable. Everything else -
settings.json, the SQLite db, the default library folders - lives under it.
"""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]  # backend/app/common/paths.py -> repo root

DATA_DIR = Path(os.environ.get("GENAI_DATA_DIR", _REPO_ROOT / "data")).expanduser().resolve()

SETTINGS_FILE = DATA_DIR / "settings.json"
DB_FILE = DATA_DIR / "app.db"
THUMBS_DIR = DATA_DIR / "thumbnails"
TRASH_DIR = DATA_DIR / "trash"


def default_folders() -> dict[str, Path]:
    """Default asset folders - used by settings defaults and on first run."""
    return {
        "library": DATA_DIR / "library",
        "exports": DATA_DIR / "exports",
        "imports": DATA_DIR / "imports",
        "agentInbox": DATA_DIR / "agent-inbox",
    }


def ensure_base_dirs() -> None:
    """Create the data dir and the default folders. Never deletes anything."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for folder in default_folders().values():
        folder.mkdir(parents=True, exist_ok=True)
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
