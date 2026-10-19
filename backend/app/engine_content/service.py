"""Inspect a ComfyUI install + audit per-module node/model requirements.

Phase A is strictly read-only (docs/COMFYUI_CONTENT.md):
- `inspect()` validates the configured folder, detects portable/venv installs,
  finds the Python that would run pip, lists custom nodes and model stats.
- `requirements()` checks every installed GenModule's `requirements.json`
  against that install.

No writes, no downloads and no execution happen here - installs arrive in later
phases behind explicit user clicks.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.common import capabilities, settings_store

# Model categories the panel reports. Unknown/extra folders are ignored; the
# list covers everything our modules reference today.
MODEL_CATEGORIES = [
    "checkpoints",
    "diffusion_models",
    "unet",
    "loras",
    "vae",
    "text_encoders",
    "clip",
    "clip_vision",
    "controlnet",
    "ipadapter",
    "embeddings",
    "upscale_models",
    "style_models",
]

# Scan caps - a huge library must never make a status poll slow.
MAX_FILES_PER_CATEGORY = 2000
MAX_CUSTOM_NODES = 500


# -- settings -------------------------------------------------------------------


def _configured_folder() -> str:
    values, _ = settings_store.load()
    return str(values.get("comfyuiFolder") or "").strip()


def suggest_folder() -> list[str]:
    """Candidate ComfyUI source folders derived from the configured launcher.

    A portable install looks like `<root>\\Run...bat` + `<root>\\ComfyUI\\main.py`,
    so the launcher path is enough to suggest the right folder. Only existing
    source folders (ones with main.py) are returned.
    """
    values, _ = settings_store.load()
    launcher = str(values.get("comfyuiLauncher") or "").strip()
    if not launcher:
        return []

    launcher_path = Path(launcher)
    candidates = [
        launcher_path.parent / "ComfyUI",  # portable layout: <root>/ComfyUI
        launcher_path.parent,  # launcher already inside the source folder
        launcher_path.parent.parent / "ComfyUI",  # launcher in a scripts subfolder
    ]
    found: list[str] = []
    for candidate in candidates:
        try:
            if (candidate / "main.py").is_file() and str(candidate) not in found:
                found.append(str(candidate))
        except OSError:
            continue
    return found[:3]


# -- inspection -----------------------------------------------------------------


def inspect(folder: str | None = None) -> dict:
    """Read-only report for the configured (or given) ComfyUI source folder."""
    configured = _configured_folder()
    target = (folder or configured).strip()

    report: dict = {
        "configured": configured,
        "path": "",
        "valid": False,
        "mainPy": False,
        "flavor": None,  # portable | venv | unknown
        "pythonPath": None,
        "version": None,
        "customNodesDir": None,
        "modelsDir": None,
        "customNodes": [],
        "customNodesTruncated": False,
        "models": [],  # [{ category, files, bytes }]
        "extraModelPathsFile": False,
        "suggestions": suggest_folder() if not configured else [],
        "error": None,
    }
    if not target:
        report["error"] = "No ComfyUI folder configured yet."
        return report

    root = Path(target)
    try:
        is_dir = root.is_dir()
    except OSError:
        is_dir = False
    if not is_dir:
        report["error"] = "That folder does not exist."
        return report

    report["path"] = str(root)
    report["mainPy"] = (root / "main.py").is_file()
    if not report["mainPy"]:
        report["error"] = (
            "No main.py in this folder - pick the ComfyUI source folder "
            "(the one that contains custom_nodes/ and models/)."
        )
        return report

    # Flavor + the Python that later phases would run pip with.
    python_candidates = [
        (root.parent / "python_embeded" / "python.exe", "portable"),
        (root / "python_embeded" / "python.exe", "portable"),
        (root / ".venv" / "Scripts" / "python.exe", "venv"),
        (root / "venv" / "Scripts" / "python.exe", "venv"),
    ]
    report["flavor"] = "unknown"
    for python, flavor in python_candidates:
        try:
            if python.is_file():
                report["flavor"] = flavor
                report["pythonPath"] = str(python)
                break
        except OSError:
            continue

    report["version"] = _read_version(root)
    report["valid"] = True

    nodes_dir = root / "custom_nodes"
    models_dir = root / "models"
    if nodes_dir.is_dir():
        report["customNodesDir"] = str(nodes_dir)
        report["customNodes"], report["customNodesTruncated"] = _list_custom_nodes(nodes_dir)
    if models_dir.is_dir():
        report["modelsDir"] = str(models_dir)
        report["models"] = _model_stats(models_dir)
    report["extraModelPathsFile"] = (root / "extra_model_paths.yaml").is_file()
    return report


def _read_version(root: Path) -> str | None:
    """Best-effort version from comfyui_version.py (newer installs have it)."""
    try:
        text = (root / "comfyui_version.py").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("__version__"):
            _, _, value = stripped.partition("=")
            return value.strip().strip("'\"") or None
    return None


def _list_custom_nodes(nodes_dir: Path) -> tuple[list[dict], bool]:
    nodes: list[dict] = []
    try:
        entries = sorted(
            p for p in nodes_dir.iterdir() if p.is_dir() and not p.name.startswith((".", "__"))
        )
    except OSError:
        return nodes, False

    truncated = len(entries) > MAX_CUSTOM_NODES
    for entry in entries[:MAX_CUSTOM_NODES]:
        name = entry.name
        disabled = name.endswith(".disabled")
        if disabled:
            name = name[: -len(".disabled")]
        nodes.append(
            {
                "name": name,
                "source": _git_origin(entry),
                "commit": _git_commit(entry),
                "disabled": disabled,
            }
        )
    return nodes, truncated


def _git_origin(repo: Path) -> str | None:
    """Parse the origin URL from .git/config (no git process needed)."""
    try:
        text = (repo / ".git" / "config").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    in_origin = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("["):
            in_origin = line.replace(" ", "").lower() == '[remote"origin"]'
        elif in_origin and line.lower().startswith("url"):
            _, _, value = line.partition("=")
            return value.strip() or None
    return None


def _git_commit(repo: Path) -> str | None:
    """Short commit hash from .git/HEAD (packed refs are ignored - status only)."""
    try:
        head = (repo / ".git" / "HEAD").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if head.startswith("ref:"):
        ref = head.split(":", 1)[1].strip()
        try:
            return (repo / ".git" / ref).read_text(encoding="utf-8", errors="replace").strip()[:12] or None
        except OSError:
            return None
    return head[:12] or None


def _model_stats(models_dir: Path) -> list[dict]:
    stats: list[dict] = []
    for category in MODEL_CATEGORIES:
        folder = models_dir / category
        if not folder.is_dir():
            continue
        files = 0
        total = 0
        try:
            for entry in folder.rglob("*"):
                if files >= MAX_FILES_PER_CATEGORY:
                    break
                if entry.is_file():
                    files += 1
                    try:
                        total += entry.stat().st_size
                    except OSError:
                        continue
        except OSError:
            continue
        if files:
            stats.append({"category": category, "files": files, "bytes": total})
    return stats


# -- requirement audit ----------------------------------------------------------


def _module_folders() -> list[Path]:
    base = capabilities.GENMODULES_DIR
    if not base.is_dir():
        return []
    found: list[Path] = []
    for folder in sorted(p for p in base.iterdir() if p.is_dir()):
        if folder.name.startswith("_"):
            continue  # template + scaffolding
        if (folder / "manifest.json").is_file() and (folder / "requirements.json").is_file():
            found.append(folder)
    return found


def _module_name(folder: Path) -> str:
    try:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        name = manifest.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    except (OSError, ValueError):
        pass
    return folder.name


def requirements() -> dict:
    """Audit every installed module's requirements against the configured folder."""
    report = inspect()
    valid = bool(report["valid"])
    installed_nodes = report["customNodes"] if valid else []
    models_dir = Path(report["modelsDir"]) if report.get("modelsDir") else None

    modules: list[dict] = []
    for folder in _module_folders():
        try:
            raw = json.loads((folder / "requirements.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            modules.append(
                {
                    "id": folder.name,
                    "name": _module_name(folder),
                    "nodes": [],
                    "models": [],
                    "missingNodes": 0,
                    "missingModels": 0,
                    "checked": valid,
                    "ready": False,
                    "error": "requirements.json is not valid JSON",
                }
            )
            continue

        raw_nodes = raw.get("nodes") if isinstance(raw, dict) else None
        raw_models = raw.get("models") if isinstance(raw, dict) else None
        nodes = [_check_node(item) for item in raw_nodes] if isinstance(raw_nodes, list) else []
        models = [_check_model(item) for item in raw_models] if isinstance(raw_models, list) else []

        # Fill install state now that we have the engine's content.
        for node in nodes:
            if valid:
                _match_node(node, installed_nodes)
        for model in models:
            if models_dir is not None:
                _match_model(model, models_dir)

        missing_nodes = sum(1 for node in nodes if node["installed"] is False and not node["optional"])
        missing_models = sum(1 for model in models if model["installed"] is False and not model["optional"])
        modules.append(
            {
                "id": folder.name,
                "name": _module_name(folder),
                "nodes": nodes,
                "models": models,
                "missingNodes": missing_nodes,
                "missingModels": missing_models,
                "checked": valid,
                "ready": valid and missing_nodes == 0 and missing_models == 0,
                "error": None,
            }
        )

    return {"inspect": report, "modules": modules}


def _check_node(raw: object) -> dict:
    item = raw if isinstance(raw, dict) else {}
    name = str(item.get("name") or "").strip()
    repo = str(item.get("repo") or "").strip()
    commit = str(item.get("commit") or "").strip()
    return {
        "name": name or repo.rstrip("/").rsplit("/", 1)[-1] or "custom node",
        "repo": repo,
        "commit": commit,
        "optional": bool(item.get("optional")),
        "installed": None,
        "installedPath": None,
        "installedCommit": None,
    }


def _normalize_repo(url: str) -> str:
    """Compare git origins loosely: case, trailing slash, .git suffix, ssh form."""
    normalized = url.strip().lower().rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    if normalized.startswith("git@"):
        normalized = "https://" + normalized[4:].replace(":", "/", 1)
    return normalized


def _match_node(node: dict, installed: list[dict]) -> None:
    wanted_repo = _normalize_repo(node["repo"]) if node["repo"] else ""
    wanted_name = node["name"].lower()
    for entry in installed:
        entry_repo = _normalize_repo(entry.get("source") or "")
        if (wanted_repo and entry_repo == wanted_repo) or entry["name"].lower() == wanted_name:
            node["installed"] = not entry["disabled"]
            node["installedPath"] = entry["name"]
            node["installedCommit"] = entry.get("commit")
            return
    node["installed"] = False


def _check_model(raw: object) -> dict:
    item = raw if isinstance(raw, dict) else {}
    name = str(item.get("name") or item.get("file") or "").strip()
    target = str(item.get("target") or "checkpoints").strip()
    size = item.get("size")
    return {
        "name": name,
        "target": target,
        "sizeBytes": int(size) if isinstance(size, (int, float)) and size > 0 else None,
        "optional": bool(item.get("optional")),
        "installed": None,
        "path": None,
        "sizeMatches": None,
    }


def _match_model(model: dict, models_dir: Path) -> None:
    if not model["name"]:
        model["installed"] = False
        return
    folder = models_dir / model["target"]
    model["installed"] = False
    if not folder.is_dir():
        return
    wanted = model["name"].lower()
    try:
        for candidate in folder.rglob("*"):
            if candidate.is_file() and candidate.name.lower() == wanted:
                model["installed"] = True
                model["path"] = str(candidate)
                if model["sizeBytes"]:
                    try:
                        model["sizeMatches"] = candidate.stat().st_size == model["sizeBytes"]
                    except OSError:
                        model["sizeMatches"] = None
                return
    except OSError:
        return
