"""Folder routes: validate (and optionally create) a user-typed path.

The GUI's folder fields call this to tell the user immediately whether a path
is usable - long before any library/job touches it. Creation is opt-in via
`create: true`; nothing is ever deleted.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["folders"])


class FolderCheck(BaseModel):
    path: str
    create: bool = False


@router.post("/folders/validate")
def validate_folder(req: FolderCheck) -> dict:
    raw = req.path.strip()
    result = {
        "ok": False,
        "path": raw,
        "resolved": "",
        "exists": False,
        "isDir": False,
        "writable": False,
        "created": False,
        "message": "",
    }

    if not raw:
        result["message"] = "Empty path."
        return result

    path = Path(raw).expanduser()
    if not path.is_absolute():
        result["message"] = "Use an absolute path, e.g. D:\\GenAI\\library."
        return result

    if path.exists() and not path.is_dir():
        result["exists"] = True
        result["message"] = "That path is a file, not a folder."
        return result

    if not path.exists():
        if not req.create:
            result["message"] = "Folder does not exist yet."
            return result
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            result["message"] = f"Could not create the folder: {exc}"
            return result
        result["created"] = True

    result["exists"] = True
    result["isDir"] = True
    result["resolved"] = str(path.resolve())

    if not os.access(path, os.W_OK):
        result["message"] = "Folder exists but is not writable."
        return result

    result["writable"] = True
    result["ok"] = True
    result["message"] = "Created and ready." if result["created"] else "Folder is ready."
    return result
