"""Folder & path routes: validate a user-typed path, and OS-native pick dialogs.

The GUI's folder fields call this to tell the user immediately whether a path
is usable - long before any library/job touches it. Creation is opt-in via
`create: true`; nothing is ever deleted.

`/folders/pick` opens a native file/folder dialog **on the machine running the
backend** (local-first: that is the user's machine) and returns the chosen
absolute path, or null when cancelled. Browsers cannot hand out real file
paths, so the dialog lives on the backend (tkinter - stdlib only).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
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


class PickRequest(BaseModel):
    mode: Literal["file", "folder"] = "file"
    title: str = "Select"
    start: str = ""
    extensions: list[str] = []


@router.post("/folders/pick")
def pick_path(req: PickRequest) -> dict:
    """Open the OS-native dialog and return {"path": str | None} (None = cancelled).

    `start` is the current value of the field: a folder opens there directly, a
    file path opens its parent. `extensions` ([".bat", "cmd"]) filters the file
    mode; folder mode ignores it.
    """
    import tkinter as tk
    from tkinter import filedialog

    start = req.start.strip()
    initialdir = ""
    if start:
        p = Path(start).expanduser()
        if p.is_dir():
            initialdir = str(p)
        elif p.parent.is_dir():
            initialdir = str(p.parent)

    extensions = [e.strip().lstrip("*").lstrip(".") for e in req.extensions if e.strip()]
    filetypes = [("All files", "*.*")]
    if extensions:
        pattern = " ".join(f"*.{e}" for e in extensions)
        label = " / ".join(e.upper() for e in extensions)
        filetypes = [(f"{label} files", pattern), ("All files", "*.*")]

    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            if req.mode == "folder":
                picked = filedialog.askdirectory(
                    parent=root, title=req.title, initialdir=initialdir or None, mustexist=True
                )
            else:
                picked = filedialog.askopenfilename(
                    parent=root, title=req.title, initialdir=initialdir or None, filetypes=filetypes
                )
        finally:
            root.destroy()
    except Exception as err:  # noqa: BLE001 - any tk failure becomes a clean error
        raise HTTPException(status_code=500, detail=f"Could not open the file dialog: {err}") from err

    return {"path": picked or None}
