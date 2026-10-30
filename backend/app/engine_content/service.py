"""Inspect a ComfyUI install + audit per-module node/model requirements.

Phase A is strictly read-only (docs/COMFYUI_CONTENT.md):
- `inspect()` validates the configured folder, detects portable/venv installs,
  finds the Python that would run pip, lists custom nodes and model files.
  Model files carry a best-effort `kind` (image / video / lora / vae / ...)
  inferred from the safetensors / GGUF header - header bytes only, never a
  full read.
- `requirements()` checks the shared core baseline plus every installed
  GenModule's `requirements.json` against that install.

No writes, no downloads and no execution happen here - installs arrive in later
phases behind explicit user clicks.
"""

from __future__ import annotations

import json
import shutil
import struct
from pathlib import Path

from app.common import capabilities, settings_store
from app.common.model_aliases import alias_score, best_alias_match

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
MAX_MODEL_FILES = 400  # entries returned to the GUI
MAX_CUSTOM_NODES = 500
ST_HEADER_LIMIT = 4 * 1024 * 1024  # safetensors headers are KBs; skip monsters
GGUF_MAX_KEYS = 64

# Intrinsic category -> kind. Diffusion categories (checkpoints, unet, ...) are
# inferred per file from the header/filename instead.
CATEGORY_KINDS = {
    "loras": "lora",
    "vae": "vae",
    "text_encoders": "text_encoder",
    "clip": "text_encoder",
    "clip_vision": "clip_vision",
    "controlnet": "controlnet",
    "upscale_models": "upscaler",
    "embeddings": "embedding",
    "model_patches": "model_patch",
}

# Where a kind is allowed to live. A mismatch is reported as a suggestion
# (`suggestedCategory`) - the app never moves files by itself.
ALLOWED_CATEGORIES = {
    "image": {"checkpoints", "diffusion_models", "unet"},
    "video": {"checkpoints", "diffusion_models", "unet"},
    "text_encoder": {"text_encoders", "clip"},
    "vae": {"vae"},
    "lora": {"loras"},
    "upscaler": {"upscale_models"},
    "clip_vision": {"clip_vision"},
    "controlnet": {"controlnet"},
}
CANONICAL_CATEGORY = {
    "image": "diffusion_models",
    "video": "diffusion_models",
    "text_encoder": "text_encoders",
    "vae": "vae",
    "lora": "loras",
    "upscaler": "upscale_models",
    "clip_vision": "clip_vision",
    "controlnet": "controlnet",
}

# Parsed header cache: (path, mtime_ns, size) -> compact info. Keeps repeated
# audits cheap without caching file contents.
_HEADER_CACHE: dict[tuple[str, int, int], dict] = {}


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


def _source_folder_suggestion(selected: Path) -> str | None:
    """Best candidate when the user picked a launcher, parent, or subfolder.

    Selecting `...\\ComfyUI_windows_portable` (or a file inside it) is a common
    mistake. The app never changes the saved setting by itself; it only returns
    a candidate that the GUI can apply with one click.
    """
    try:
        base = selected.parent if selected.is_file() else selected
    except OSError:
        base = selected

    candidates: list[Path] = []
    current = base
    for _ in range(3):
        candidates.extend((current / "ComfyUI", current))
        try:
            current = current.parent
        except OSError:
            break
        if current == current.parent:
            break

    seen: set[str] = set()
    for candidate in candidates:
        try:
            key = str(candidate).lower()
            if key in seen:
                continue
            seen.add(key)
            if (candidate / "main.py").is_file():
                return str(candidate)
        except OSError:
            continue
    return None


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
        "models": [],  # [{ category, files, bytes, items[] }]
        "extraModelPathsFile": False,
        "suggestions": suggest_folder() if not configured else [],
        "suggestedFolder": None,
        "gitAvailable": shutil.which("git") is not None,
        "error": None,
    }
    if not target:
        report["error"] = "No ComfyUI folder configured yet."
        return report

    root = Path(target)
    try:
        is_file = root.is_file()
        is_dir = root.is_dir()
    except OSError:
        is_file = False
        is_dir = False
    if not is_dir:
        report["suggestedFolder"] = _source_folder_suggestion(root)
        report["error"] = (
            "That is a file - pick the ComfyUI source folder."
            if is_file
            else "That folder does not exist."
        )
        return report

    report["path"] = str(root)
    report["mainPy"] = (root / "main.py").is_file()
    if not report["mainPy"]:
        report["suggestedFolder"] = _source_folder_suggestion(root)
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
        report["models"] = _model_inventory(models_dir)
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


def _model_inventory(models_dir: Path) -> list[dict]:
    """Per-category model files with a best-effort kind/architecture.

    Header parsing is read-only and bounded (safetensors: 8-byte length + the
    JSON header; GGUF: scalar metadata keys). Unknown files simply stay
    `kind: unknown` - never guessed from extension alone.
    """
    stats: list[dict] = []
    budget = MAX_MODEL_FILES
    for category in MODEL_CATEGORIES:
        folder = models_dir / category
        if not folder.is_dir():
            continue
        files = 0
        total = 0
        items: list[dict] = []
        truncated = False
        try:
            entries = sorted(folder.rglob("*"))
        except OSError:
            continue
        for entry in entries:
            if files >= MAX_FILES_PER_CATEGORY:
                truncated = True
                break
            if not entry.is_file() or entry.name.startswith("."):
                continue
            try:
                size = entry.stat().st_size
            except OSError:
                continue
            if size <= 0:
                continue  # stock "put_*_here" placeholders
            files += 1
            total += size
            if budget <= 0:
                truncated = True
                continue
            budget -= 1
            items.append(_model_item(entry, category, entry.relative_to(folder).as_posix(), size))
        if files:
            stats.append(
                {
                    "category": category,
                    "files": files,
                    "bytes": total,
                    "items": items,
                    "truncated": truncated,
                }
            )
    return stats


def _model_item(path: Path, category: str, rel_name: str, size: int) -> dict:
    suffix = path.suffix.lower()
    info: dict = {}
    if suffix == ".safetensors":
        info = _inspect_safetensors(path, size)
    elif suffix == ".gguf":
        info = _inspect_gguf(path, size)

    arch = str(info.get("arch") or "")
    kind = CATEGORY_KINDS.get(category) or _kind_from_arch(arch, path.name)
    return {
        "name": rel_name,
        "sizeBytes": size,
        "kind": kind,
        "arch": arch or None,
        "base": info.get("base"),
        "triggers": info.get("triggers") or [],
        "suggestedCategory": _suggest_category(kind, category),
    }


def _kind_from_arch(arch: str, filename: str) -> str:
    """Classify a diffusion file: image / video / text encoder / unknown."""
    text = f"{arch} {filename}".lower()
    if any(
        token in text
        for token in (
            "minimax",
            "wan2",
            "wan_",
            "wan-",
            "ltx",
            "hunyuanvideo",
            "hunyuan_video",
            "mochi",
            "cogvideo",
            "svd",
        )
    ):
        return "video"
    if "audio" in text:
        return "audio"
    if any(token in text for token in ("qwen3vl", "qwen3", "llama", "gemma", "t5", "llm", "text_encoder")):
        return "text_encoder"
    if any(
        token in text
        for token in (
            "qwen_image",
            "qwen-image",
            "flux",
            "krea",
            "sdxl",
            "sd15",
            "sd3",
            "z_image",
            "chroma",
            "hidream",
            "pixart",
            "kolors",
        )
    ):
        return "image"
    return "unknown"


def _suggest_category(kind: str, category: str) -> str | None:
    allowed = ALLOWED_CATEGORIES.get(kind)
    if allowed and category not in allowed:
        return CANONICAL_CATEGORY.get(kind)
    return None


def _cached_header(key: tuple[str, int, int]) -> dict | None:
    return _HEADER_CACHE.get(key)


def _store_header(key: tuple[str, int, int], info: dict) -> dict:
    if len(_HEADER_CACHE) > 4000:
        _HEADER_CACHE.clear()
    _HEADER_CACHE[key] = info
    return info


def _inspect_safetensors(path: Path, size: int) -> dict:
    try:
        key = (str(path), path.stat().st_mtime_ns, size)
    except OSError:
        return {}
    cached = _cached_header(key)
    if cached is not None:
        return cached

    info: dict = {}
    try:
        with open(path, "rb") as fh:
            raw = fh.read(8)
            if len(raw) == 8:
                header_len = struct.unpack("<Q", raw)[0]
                if 0 < header_len <= ST_HEADER_LIMIT:
                    header = json.loads(fh.read(header_len).decode("utf-8", errors="replace"))
                    if isinstance(header, dict):
                        meta = header.get("__metadata__") or {}
                        if not isinstance(meta, dict):
                            meta = {}
                        keys = [k for k in header.keys() if k != "__metadata__"]
                        info = {
                            "arch": _guess_arch(keys, meta),
                            "base": _lora_base(meta),
                            "triggers": _lora_triggers(meta),
                        }
    except (OSError, ValueError, struct.error):
        info = {}
    return _store_header(key, info)


def _guess_arch(keys: list[str], meta: dict) -> str:
    """Short architecture tag from metadata / tensor naming."""
    spec = str(meta.get("modelspec.architecture") or "").strip().lower()
    if spec:
        return spec
    joined = "\n".join(keys[:500]).lower()
    if "lora_" in joined or "lora_down" in joined or "lora_a" in joined or "lora_up" in joined:
        return "lora"
    if "joint_blocks." in joined:
        return "sd3"
    if "double_blocks." in joined and "single_blocks." in joined:
        return "mmdit"
    if "model.diffusion_model." in joined:
        return "sd"
    if "encoder.down_blocks" in joined and "decoder.up_blocks" in joined:
        return "vae"
    if "control_model." in joined:
        return "controlnet"
    if "vision_model." in joined:
        return "clip_vision"
    if "model.layers." in joined and "embed_tokens" in joined:
        return "llm"
    if "text_model." in joined or "cond_stage_model." in joined:
        return "text_encoder"
    if "patch_embedding" in joined and "blocks." in joined:
        return "transformer"
    if "down_blocks" in joined and "up_blocks" in joined:
        return "unet"
    return ""


def _lora_base(meta: dict) -> str | None:
    base = str(meta.get("ss_base_model_version") or "").strip()
    if base:
        return base
    spec = str(meta.get("modelspec.architecture") or "").strip().lower()
    if "/" in spec:
        prefix = spec.split("/", 1)[0].strip()
        return prefix or None
    return None


def _lora_triggers(meta: dict) -> list[str]:
    """Top trigger words from kohya's `ss_tag_frequency` metadata."""
    raw = meta.get("ss_tag_frequency")
    if not raw:
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return []
    if not isinstance(data, dict):
        return []
    counts: dict[str, int] = {}
    for words in data.values():
        if not isinstance(words, dict):
            continue
        for word, count in words.items():
            if not isinstance(word, str) or not word.strip():
                continue
            try:
                n = int(count)
            except (TypeError, ValueError):
                n = 0
            counts[word.strip()] = counts.get(word.strip(), 0) + n
    return [word for word, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:8]]


def _inspect_gguf(path: Path, size: int) -> dict:
    """Read scalar GGUF metadata keys (architecture/name) - no tensor data."""
    try:
        key = (str(path), path.stat().st_mtime_ns, size)
    except OSError:
        return {}
    cached = _cached_header(key)
    if cached is not None:
        return cached

    info: dict = {}
    interesting = {"general.architecture", "general.name", "general.size_label", "general.type"}
    scalar_sizes = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
    try:
        with open(path, "rb") as fh:
            if fh.read(4) != b"GGUF":
                return _store_header(key, info)
            fh.read(4)  # version
            fh.read(8)  # tensor count
            kv_count = struct.unpack("<Q", fh.read(8))[0]

            def read_str() -> str:
                length = struct.unpack("<Q", fh.read(8))[0]
                if length > 1_000_000:  # corrupt/hostile guard
                    fh.seek(length, 1)
                    return ""
                return fh.read(length).decode("utf-8", errors="replace")

            for _ in range(min(kv_count, GGUF_MAX_KEYS)):
                name = read_str()
                vtype = struct.unpack("<I", fh.read(4))[0]
                if vtype == 8:
                    value = read_str()
                    if name in interesting:
                        info[name] = value
                elif vtype in scalar_sizes:
                    raw = fh.read(scalar_sizes[vtype])
                    if name in interesting:
                        if vtype == 7:
                            info[name] = raw != b"\x00"
                        elif vtype in (6, 12):
                            info[name] = struct.unpack("<f" if vtype == 6 else "<d", raw)[0]
                        else:
                            info[name] = int.from_bytes(raw, "little", signed=vtype in (1, 3, 5, 11))
                elif vtype == 9:
                    subtype = struct.unpack("<I", fh.read(4))[0]
                    count = struct.unpack("<Q", fh.read(8))[0]
                    if subtype == 8:
                        for _i in range(count):
                            length = struct.unpack("<Q", fh.read(8))[0]
                            fh.seek(length, 1)
                    elif subtype in scalar_sizes:
                        fh.seek(scalar_sizes[subtype] * count, 1)
                    else:
                        break
                else:
                    break
    except (OSError, struct.error):
        info = {}

    result = {
        "arch": str(info.get("general.architecture") or ""),
        "name": str(info.get("general.name") or ""),
    }
    return _store_header(key, result)


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


CORE_REQUIREMENTS_FILE = Path(__file__).with_name("core_requirements.json")


def _load_core() -> dict:
    try:
        raw = json.loads(CORE_REQUIREMENTS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def load_requirements(module_id: str) -> tuple[str, dict]:
    """Requirement block for `core` or an installed GenModule, by id.

    Used by the installer: the server only installs entries that a shipped
    requirements.json declares - the GUI can never ask for an arbitrary repo.
    """
    if module_id == "core":
        return "Core requirements", _load_core()

    base = capabilities.GENMODULES_DIR
    if not base.is_dir() or not module_id or module_id.startswith("."):
        raise ValueError("Unknown module id")
    try:
        folder = (base / module_id).resolve()
        root = base.resolve()
    except OSError as exc:
        raise ValueError("Unknown module id") from exc
    if folder.parent != root or not folder.is_dir() or not (folder / "manifest.json").is_file():
        raise LookupError(f"Unknown module: {module_id}")
    try:
        raw = json.loads((folder / "requirements.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Module {module_id} has no valid requirements.json") from exc
    return _module_name(folder), raw if isinstance(raw, dict) else {}


def _audit_block(
    raw: object,
    valid: bool,
    installed_nodes: list[dict],
    models_dir: Path | None,
    package_dirs: list[Path] | None = None,
) -> tuple[list[dict], list[dict], list[dict], int, int]:
    raw_nodes = raw.get("nodes") if isinstance(raw, dict) else None
    raw_models = raw.get("models") if isinstance(raw, dict) else None
    raw_groups = raw.get("groups") if isinstance(raw, dict) else None
    nodes = [_check_node(item) for item in raw_nodes] if isinstance(raw_nodes, list) else []
    models = [_check_model(item) for item in raw_models] if isinstance(raw_models, list) else []

    # Fill install state now that we have the engine's content.
    for node in nodes:
        if valid:
            _match_node(node, installed_nodes, package_dirs)
    for model in models:
        if models_dir is not None:
            _match_model(model, models_dir)

    groups: list[dict] = []
    grouped_ids: set[str] = set()
    for raw_group in raw_groups if isinstance(raw_groups, list) else []:
        if not isinstance(raw_group, dict) or not raw_group.get("id"):
            continue
        group_id = str(raw_group["id"])
        members = [model for model in models if model.get("group") == group_id]
        if not members:
            continue
        grouped_ids.update(model["id"] for model in members)
        present_count = sum(1 for model in members if model["installed"] is True)
        matched_file = ""
        if models_dir is not None:
            targets = {model["target"] for model in members if model.get("target")}
            for target in targets:
                found = _find_file_for_aliases(models_dir / target, list(raw_group.get("aliases") or []))
                if found:
                    matched_file = found.name
                    break
        if models_dir is None or not valid:
            satisfied: bool | None = None
        else:
            satisfied = present_count > 0 or bool(matched_file)
        groups.append(
            {
                "id": group_id,
                "label": str(raw_group.get("label") or group_id),
                "pack": str(raw_group.get("pack") or ""),
                "mode": str(raw_group.get("mode") or "oneOf"),
                "required": bool(raw_group.get("required", True)),
                "satisfied": satisfied,
                "presentCount": present_count,
                "matchedFile": matched_file,
                "items": [model["id"] for model in members],
                "why": str(raw_group.get("why") or ""),
            }
        )

    missing_nodes = sum(1 for node in nodes if node["installed"] is False and not node["optional"])
    missing_models = sum(
        1
        for model in models
        if model["id"] not in grouped_ids and model["installed"] is False and not model["optional"]
    )
    missing_models += sum(1 for group in groups if group["required"] and group["satisfied"] is False)
    return nodes, models, groups, missing_nodes, missing_models


def requirements() -> dict:
    """Audit the core baseline + every installed module's requirements."""
    report = inspect()
    valid = bool(report["valid"])
    installed_nodes = report["customNodes"] if valid else []
    models_dir = Path(report["modelsDir"]) if report.get("modelsDir") else None
    package_dirs = _site_packages_dirs(report.get("pythonPath"))

    core_nodes, core_models, core_groups, core_missing_nodes, core_missing_models = _audit_block(
        _load_core(), valid, installed_nodes, models_dir, package_dirs
    )
    core = {
        "nodes": core_nodes,
        "models": core_models,
        "groups": core_groups,
        "missingNodes": core_missing_nodes,
        "missingModels": core_missing_models,
        "checked": valid,
        "ready": valid and core_missing_nodes == 0 and core_missing_models == 0,
    }

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
                    "groups": [],
                    "missingNodes": 0,
                    "missingModels": 0,
                    "checked": valid,
                    "ready": False,
                    "error": "requirements.json is not valid JSON",
                }
            )
            continue

        nodes, models, groups, missing_nodes, missing_models = _audit_block(
            raw, valid, installed_nodes, models_dir, package_dirs
        )
        modules.append(
            {
                "id": folder.name,
                "name": _module_name(folder),
                "nodes": nodes,
                "models": models,
                "groups": groups,
                "missingNodes": missing_nodes,
                "missingModels": missing_models,
                "checked": valid,
                "ready": valid and missing_nodes == 0 and missing_models == 0,
                "error": None,
            }
        )

    return {"inspect": report, "core": core, "modules": modules}


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
        "why": str(item.get("why") or ""),
        "package": str(item.get("package") or ""),
        "pip": str(item.get("pip") or ""),
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


def _match_node(node: dict, installed: list[dict], package_dirs: list[Path] | None = None) -> None:
    wanted_repo = _normalize_repo(node["repo"]) if node["repo"] else ""
    wanted_name = node["name"].lower()
    for entry in installed:
        entry_repo = _normalize_repo(entry.get("source") or "")
        if (wanted_repo and entry_repo == wanted_repo) or entry["name"].lower() == wanted_name:
            node["installed"] = not entry["disabled"]
            node["installedPath"] = entry["name"]
            node["installedCommit"] = entry.get("commit")
            return

    # ComfyUI 0.30+ ships Manager as a Python package (`comfyui_manager`), not a
    # custom_nodes folder. An optional `package` field covers that install style.
    package = node.get("package") or ""
    if package and package_dirs:
        for site in package_dirs:
            if (site / package / "__init__.py").is_file():
                node["installed"] = True
                node["installedPath"] = str(site / package)
                return
            if any(site.glob(f"{package}-*.dist-info")):
                node["installed"] = True
                node["installedPath"] = str(site)
                return

    node["installed"] = False


def _site_packages_dirs(python_path: str | None) -> list[Path]:
    """site-packages candidates for both portable and venv layouts (read-only)."""
    if not python_path:
        return []
    exe = Path(python_path)
    roots = {exe.parent, exe.parent.parent}
    candidates: list[Path] = [root / "Lib" / "site-packages" for root in roots]
    for root in roots:
        try:
            candidates.extend(root.glob("lib/python*/site-packages"))
        except OSError:
            continue

    result: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_dir():
            result.append(candidate)
    return result


def _check_model(raw: object) -> dict:
    item = raw if isinstance(raw, dict) else {}
    name = str(item.get("name") or item.get("file") or "").strip()
    target = str(item.get("target") or "checkpoints").strip()
    size = item.get("size", item.get("sizeBytes"))
    required = bool(item["required"]) if "required" in item else not bool(item.get("optional"))
    aliases = [str(alias).strip() for alias in (item.get("aliases") or []) if str(alias).strip()]
    return {
        "id": str(item.get("id") or name),
        "label": str(item.get("label") or name),
        "name": name,
        "target": target,
        "role": str(item.get("role") or ""),
        "pack": str(item.get("pack") or ""),
        "group": str(item.get("group") or ""),
        "aliases": aliases,
        "sizeBytes": int(size) if isinstance(size, (int, float)) and size > 0 else None,
        "required": required,
        "optional": not required,
        "tested": bool(item.get("tested")),
        "nsfw": bool(item.get("nsfw")),
        "url": str(item.get("url") or ""),
        "pageUrl": str(item.get("pageUrl") or ""),
        "sha256": str(item.get("sha256") or ""),
        "why": str(item.get("why") or ""),
        "installed": None,
        "path": None,
        "resolvedName": None,
        "sizeMatches": None,
    }


def _find_file_for_aliases(folder: Path, aliases: list[str]) -> Path | None:
    if not aliases or not folder.is_dir():
        return None
    best: Path | None = None
    best_score = 0
    try:
        for candidate in folder.rglob("*"):
            if not candidate.is_file():
                continue
            score = alias_score(candidate.name, aliases)
            if score > best_score:
                best = candidate
                best_score = score
    except OSError:
        return None
    return best


def _match_model(model: dict, models_dir: Path) -> None:
    if not model["name"]:
        model["installed"] = False
        return
    folder = models_dir / model["target"]
    model["installed"] = False
    if not folder.is_dir():
        return
    wanted = model["name"].replace("\\", "/").casefold()
    aliases = [*model.get("aliases", []), model["name"]]
    found: Path | None = None
    fallback: Path | None = None
    fallback_score = 0
    try:
        for candidate in folder.rglob("*"):
            if not candidate.is_file():
                continue
            relative = candidate.relative_to(folder).as_posix().casefold()
            if relative == wanted or candidate.name.casefold() == wanted:
                found = candidate
                break
            score = alias_score(candidate.name, aliases)
            if score > fallback_score:
                fallback = candidate
                fallback_score = score
    except OSError:
        return
    found = found or fallback
    if found is None:
        return
    model["installed"] = True
    model["path"] = str(found)
    try:
        model["resolvedName"] = found.relative_to(folder).as_posix()
    except ValueError:
        model["resolvedName"] = found.name
    if model["sizeBytes"]:
        try:
            model["sizeMatches"] = found.stat().st_size == model["sizeBytes"]
        except OSError:
            model["sizeMatches"] = None
