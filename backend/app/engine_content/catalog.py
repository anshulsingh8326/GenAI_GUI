"""User-facing model + LoRA catalog (data/model_catalog.json).

Phase A already reads model headers for the inventory (kind / arch / base /
triggers). This module turns that read-only inventory into a stable, editable
catalog:

- entries are matched by file (target + name), so refreshes never duplicate;
- user edits (label, base, linked models, triggers, ranges, notes) are kept;
- files that are temporarily missing stay in the catalog with `present: false`;
- LoRA -> model links are explicit (`loras[].models`) and auto-filled by base
  until the user takes them over (`modelsAuto: false`);
- triggers are applied by modules/composer when the LoRA is active.

Writing happens only on an explicit "Build / Refresh" click or an entry edit.
The catalog never moves, deletes or loads a model file.
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
from datetime import datetime, timezone
from typing import Any

from app.common import paths
from app.engine_content import service

CATALOG_FILE = paths.DATA_DIR / "model_catalog.json"
CATALOG_VERSION = 1

DEFAULT_STRENGTH = {"default": 0.8, "min": 0.0, "max": 1.5, "step": 0.05}
DEFAULT_CLIP_STRENGTH = {**DEFAULT_STRENGTH, "enabled": False}

BASE_KINDS = {"image", "video", "audio"}

_LOCK = threading.RLock()


class CatalogError(Exception):
    """User-facing catalog problem (invalid file, unknown entry, bad range)."""


# -- naming / families ----------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return value[:80] or "entry"


def _norm_name(name: str) -> str:
    return str(name).replace("\\", "/").strip().lower()


def _file_key(target: str, name: str) -> tuple[str, str]:
    return str(target).lower(), _norm_name(name)


# (base id, pattern, display label). Order matters: krea2 is a qwen-image
# finetune, so it must be detected before the generic qwen-image rule.
_FAMILIES: list[tuple[str, re.Pattern[str], str]] = [
    ("krea2", re.compile(r"krea[\s_.-]?2", re.I), "Krea 2"),
    ("flux2-klein", re.compile(r"flux[\s_.-]?2[\s_.-]?klein", re.I), "FLUX.2 Klein"),
    ("minimax-h3", re.compile(r"minimax[\s_.-]?h3", re.I), "MiniMax H3"),
    ("qwen3vl", re.compile(r"qwen[\s_.-]?3[\s_.-]?vl", re.I), "Qwen3-VL"),
    ("qwen3", re.compile(r"qwen[\s_.-]?3", re.I), "Qwen 3"),
    ("qwen-image", re.compile(r"qwen[\s_.-]?image", re.I), "Qwen Image"),
    ("wan2", re.compile(r"wan[\s_.-]?2", re.I), "Wan 2"),
    ("hunyuan-video", re.compile(r"hunyuan[\s_.-]*(video|1[\s_.-]?5)", re.I), "Hunyuan Video"),
    ("ltxv", re.compile(r"\bltx[\s_.-]?v?", re.I), "LTXV"),
    ("sdxl", re.compile(r"\bsdxl\b", re.I), "SDXL"),
    ("sd15", re.compile(r"\bsd[\s_.-]?1[\s_.-]?5\b", re.I), "SD 1.5"),
    ("sd3", re.compile(r"\bsd[\s_.-]?3\b", re.I), "SD 3"),
    ("chroma", re.compile(r"chroma|kroma", re.I), "Chroma"),
    ("z-image", re.compile(r"\bz[\s_.-]?image", re.I), "Z-Image"),
    ("ace-step", re.compile(r"ace[\s_.-]?step", re.I), "ACE-Step"),
]


def _family_from_text(text: str | None) -> str | None:
    value = str(text or "").strip()
    if not value:
        return None
    for base, pattern, _ in _FAMILIES:
        if pattern.search(value):
            return base
    return None


def base_label(base: str | None) -> str:
    if not base:
        return "Unassigned"
    for known, _, label in _FAMILIES:
        if known == base:
            return label
    return base.replace("-", " ").replace("_", " ").title()


def _infer_base(name: str, arch: str | None, raw_base: str | None = None) -> str | None:
    """Best-effort model family. Filename wins over the header architecture."""
    for candidate in (name, arch, raw_base):
        known = _family_from_text(candidate)
        if known:
            return known
    if raw_base:
        return _slug(raw_base)
    return None


def _is_base_model(item: dict) -> bool:
    return str(item.get("kind") or "") in BASE_KINDS


def _new_model_id(stem: str, used: set[str]) -> str:
    base = f"model-{_slug(stem)}"
    if base not in used:
        return base
    index = 2
    while f"{base}-{index}" in used:
        index += 1
    return f"{base}-{index}"


def _new_lora_id(stem: str, used: set[str]) -> str:
    base = f"lora-{_slug(stem)}"
    if base not in used:
        return base
    index = 2
    while f"{base}-{index}" in used:
        index += 1
    return f"{base}-{index}"


def _stem(name: str) -> str:
    leaf = _norm_name(name).rsplit("/", 1)[-1]
    return leaf.rsplit(".", 1)[0] or leaf


def _file_size(item: dict) -> int:
    try:
        return max(0, int(item.get("sizeBytes") or 0))
    except (TypeError, ValueError):
        return 0


# -- file load / save -----------------------------------------------------------


def _empty_catalog() -> dict:
    return {
        "version": CATALOG_VERSION,
        "createdAt": None,
        "updatedAt": None,
        "source": {"comfyuiFolder": "", "flavor": None, "version": None},
        "models": {},
        "loras": {},
    }


def load_catalog() -> dict:
    """Read the catalog without creating anything. Raises on a corrupt file."""
    with _LOCK:
        if not CATALOG_FILE.is_file():
            return _empty_catalog()
        try:
            raw = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CatalogError(f"model_catalog.json is not readable: {exc}") from exc
        if not isinstance(raw, dict):
            raise CatalogError("model_catalog.json must contain a JSON object.")
        if not isinstance(raw.get("models"), dict) or not isinstance(raw.get("loras"), dict):
            raise CatalogError("model_catalog.json needs `models` and `loras` objects.")
        raw.setdefault("version", CATALOG_VERSION)
        raw.setdefault("createdAt", None)
        raw.setdefault("updatedAt", None)
        raw.setdefault("source", {})
        return raw


def _save_catalog(catalog: dict) -> None:
    CATALOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = CATALOG_FILE.with_suffix(".json.tmp")
    text = json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, CATALOG_FILE)


def _default_models(base: str | None, models: dict) -> list[str]:
    if not base:
        return []
    return sorted(
        str(entry.get("id"))
        for entry in models.values()
        if entry.get("role") == "base" and entry.get("base") == base
    )


def _relink_auto(catalog: dict) -> None:
    models = catalog.get("models") if isinstance(catalog.get("models"), dict) else {}
    for lora in (catalog.get("loras") or {}).values():
        if lora.get("modelsAuto", True):
            lora["models"] = _default_models(lora.get("base"), models)


# -- build / merge --------------------------------------------------------------


def build_catalog() -> dict:
    """Scan the configured ComfyUI install and merge the inventory into the catalog.

    Read-only for ComfyUI; writes only `data/model_catalog.json`. Existing edits
    are preserved, and entries whose files are gone remain with `present: false`.
    """
    report = service.inspect()
    if not report.get("valid"):
        raise CatalogError(str(report.get("error") or "Configure a valid ComfyUI folder first."))

    with _LOCK:
        catalog = load_catalog()
        models: dict = catalog["models"]
        loras: dict = catalog["loras"]

        # Match by file key so refreshes keep ids and user edits.
        model_by_file: dict[tuple[str, str], str] = {}
        lora_by_file: dict[tuple[str, str], str] = {}
        for entry_id, entry in models.items():
            if isinstance(entry, dict):
                model_by_file[_file_key(str(entry.get("target") or ""), str(entry.get("name") or ""))] = entry_id
        for entry_id, entry in loras.items():
            if isinstance(entry, dict):
                lora_by_file[_file_key(str(entry.get("target") or ""), str(entry.get("name") or ""))] = entry_id

        for entry in models.values():
            if isinstance(entry, dict):
                entry["present"] = False
        for entry in loras.values():
            if isinstance(entry, dict):
                entry["present"] = False

        used_model_ids = {str(key) for key in models}
        used_lora_ids = {str(key) for key in loras}

        for stat in report.get("models") or []:
            target = str(stat.get("category") or "")
            for item in stat.get("items") or []:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "")
                if not name:
                    continue
                kind = str(item.get("kind") or "unknown")
                key = _file_key(target, name)
                is_lora = kind == "lora" or target.lower() in {"loras", "lora"}
                if is_lora:
                    existing_id = lora_by_file.get(key)
                    existing = loras.get(existing_id) if existing_id else None
                    entry = dict(existing) if isinstance(existing, dict) else {}
                    if not entry:
                        entry = {
                            "id": _new_lora_id(_stem(name), used_lora_ids),
                            "label": _stem(name),
                            "base": None,
                            "triggers": [str(t) for t in item.get("triggers") or []],
                            "models": [],
                            "modelsAuto": True,
                            "strength": dict(DEFAULT_STRENGTH),
                            "clipStrength": dict(DEFAULT_CLIP_STRENGTH),
                            "otherRanges": {},
                            "notes": "",
                        }
                        used_lora_ids.add(str(entry["id"]))
                    entry_id = str(entry["id"])
                    inferred_base = _infer_base(name, item.get("arch"), item.get("base"))
                    if not entry.get("base"):
                        entry["base"] = inferred_base
                    entry.update(
                        {
                            "id": entry_id,
                            "name": name,
                            "target": target,
                            "kind": "lora",
                            "base": entry.get("base") or inferred_base,
                            "family": base_label(entry.get("base")),
                            "size": _file_size(item),
                            "present": True,
                        }
                    )
                    entry.setdefault("label", _stem(name))
                    entry.setdefault("models", [])
                    entry.setdefault("modelsAuto", True)
                    entry.setdefault("strength", dict(DEFAULT_STRENGTH))
                    entry.setdefault("clipStrength", dict(DEFAULT_CLIP_STRENGTH))
                    entry.setdefault("otherRanges", {})
                    entry.setdefault("notes", "")
                    loras[entry_id] = entry
                else:
                    existing_id = model_by_file.get(key)
                    existing = models.get(existing_id) if existing_id else None
                    entry = dict(existing) if isinstance(existing, dict) else {}
                    if not entry:
                        entry = {
                            "id": _new_model_id(_stem(name), used_model_ids),
                            "label": _stem(name),
                            "base": None,
                            "notes": "",
                        }
                        used_model_ids.add(str(entry["id"]))
                    entry_id = str(entry["id"])
                    inferred_base = _infer_base(name, item.get("arch"), item.get("base"))
                    if not entry.get("base"):
                        entry["base"] = inferred_base
                    entry.update(
                        {
                            "id": entry_id,
                            "name": name,
                            "target": target,
                            "kind": kind,
                            "role": "base" if _is_base_model(item) else "companion",
                            "architecture": item.get("arch"),
                            "base": entry.get("base") or inferred_base,
                            "family": base_label(entry.get("base")) if entry.get("base") else None,
                            "size": _file_size(item),
                            "suggestedTarget": item.get("suggestedCategory"),
                            "present": True,
                        }
                    )
                    entry.setdefault("label", _stem(name))
                    entry.setdefault("notes", "")
                    models[entry_id] = entry

        _relink_auto(catalog)
        catalog.update(
            {
                "version": CATALOG_VERSION,
                "updatedAt": _now(),
                "source": {
                    "comfyuiFolder": report.get("path") or "",
                    "flavor": report.get("flavor"),
                    "version": report.get("version"),
                },
            }
        )
        if not catalog.get("createdAt"):
            catalog["createdAt"] = catalog["updatedAt"]
        _save_catalog(catalog)
        return _response(catalog)


# -- response -------------------------------------------------------------------


def _decorate_model(entry: dict) -> dict:
    item = dict(entry)
    item.setdefault("label", _stem(str(item.get("name") or "")))
    item.setdefault("target", "")
    item.setdefault("kind", "unknown")
    item.setdefault("role", "companion")
    item.setdefault("architecture", None)
    item.setdefault("base", None)
    item.setdefault("family", base_label(item.get("base")) if item.get("base") else None)
    item.setdefault("size", 0)
    item.setdefault("present", False)
    item.setdefault("notes", "")
    item.setdefault("suggestedTarget", None)
    item["loras"] = []
    return item


def _decorate_lora(entry: dict) -> dict:
    item = dict(entry)
    item.setdefault("label", _stem(str(item.get("name") or "")))
    item.setdefault("target", "loras")
    item.setdefault("kind", "lora")
    item.setdefault("base", None)
    item.setdefault("family", base_label(item.get("base")) if item.get("base") else None)
    item.setdefault("size", 0)
    item.setdefault("present", False)
    item.setdefault("triggers", [])
    item.setdefault("models", [])
    item.setdefault("modelsAuto", True)
    strength = item.get("strength")
    item["strength"] = {**DEFAULT_STRENGTH, **(strength if isinstance(strength, dict) else {})}
    clip = item.get("clipStrength")
    item["clipStrength"] = {**DEFAULT_CLIP_STRENGTH, **(clip if isinstance(clip, dict) else {})}
    item["clipStrength"]["enabled"] = bool(item["clipStrength"].get("enabled"))
    if not isinstance(item.get("otherRanges"), dict):
        item["otherRanges"] = {}
    item.setdefault("notes", "")
    return item


def _response(catalog: dict) -> dict:
    models = {
        str(entry.get("id")): _decorate_model(entry)
        for entry in (catalog.get("models") or {}).values()
        if isinstance(entry, dict) and entry.get("id")
    }
    loras = {
        str(entry.get("id")): _decorate_lora(entry)
        for entry in (catalog.get("loras") or {}).values()
        if isinstance(entry, dict) and entry.get("id")
    }

    for lora in loras.values():
        for model_id in lora.get("models") or []:
            if model_id in models:
                models[model_id]["loras"].append(lora["id"])

    bases: dict[str, dict] = {}
    for model in models.values():
        if model.get("role") == "base" and model.get("base"):
            base = str(model["base"])
            slot = bases.setdefault(
                base,
                {"id": base, "label": base_label(base), "kind": model.get("kind"), "models": 0, "loras": 0},
            )
            slot["models"] += 1
            slot["kind"] = slot.get("kind") or model.get("kind")
    for lora in loras.values():
        base = lora.get("base")
        if base:
            slot = bases.setdefault(
                str(base),
                {"id": str(base), "label": base_label(str(base)), "kind": "lora", "models": 0, "loras": 0},
            )
            slot["loras"] += 1

    model_list = sorted(
        models.values(),
        key=lambda item: (
            item.get("role") != "base",
            str(item.get("base") or ""),
            str(item.get("label") or "").lower(),
        ),
    )
    for model in model_list:
        model["loras"] = sorted(model["loras"], key=lambda value: value.lower())
    lora_list = sorted(
        loras.values(),
        key=lambda item: (str(item.get("base") or ""), str(item.get("label") or "").lower()),
    )

    return {
        "version": catalog.get("version", CATALOG_VERSION),
        "createdAt": catalog.get("createdAt"),
        "updatedAt": catalog.get("updatedAt"),
        "source": catalog.get("source") or {},
        "bases": sorted(bases.values(), key=lambda item: str(item.get("label") or "").lower()),
        "models": model_list,
        "loras": lora_list,
        "stats": {
            "models": len(model_list),
            "baseModels": sum(1 for item in model_list if item.get("role") == "base"),
            "loras": len(lora_list),
            "missing": sum(1 for item in [*model_list, *lora_list] if not item.get("present")),
            "withTriggers": sum(1 for item in lora_list if item.get("triggers")),
        },
    }


def catalog_response() -> dict:
    return _response(load_catalog())


# -- edits ----------------------------------------------------------------------


def _clean_triggers(values: Any) -> list[str]:
    if not isinstance(values, list):
        raise CatalogError("`triggers` must be a list of words.")
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        key = " ".join(text.lower().split())
        if key in seen:
            continue
        seen.add(key)
        if len(text) > 200:
            raise CatalogError("A trigger word is longer than 200 characters.")
        result.append(text)
    if len(result) > 100:
        raise CatalogError("A LoRA can have at most 100 trigger words.")
    return result


def _finite(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CatalogError(f"{field} must be a number.") from exc
    if not math.isfinite(number):
        raise CatalogError(f"{field} must be a finite number.")
    return number


def _clean_range(raw: Any, field: str) -> dict:
    if not isinstance(raw, dict):
        raise CatalogError(f"{field} must be a range object.")
    minimum = _finite(raw.get("min"), f"{field}.min")
    maximum = _finite(raw.get("max"), f"{field}.max")
    default = _finite(raw.get("default"), f"{field}.default")
    step = _finite(raw.get("step"), f"{field}.step")
    if maximum <= minimum:
        raise CatalogError(f"{field}.max must be greater than min.")
    if default < minimum or default > maximum:
        raise CatalogError(f"{field}.default must be inside min..max.")
    if step <= 0:
        raise CatalogError(f"{field}.step must be greater than zero.")
    return {"default": default, "min": minimum, "max": maximum, "step": step}


def _clean_other_ranges(raw: Any) -> dict:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise CatalogError("`otherRanges` must be an object of named ranges.")
    if len(raw) > 30:
        raise CatalogError("At most 30 extra ranges are supported.")
    result: dict[str, dict] = {}
    for key, value in raw.items():
        name = str(key).strip()
        if not name or len(name) > 40 or not re.match(r"^[A-Za-z0-9_.-]+$", name):
            raise CatalogError(f"Invalid range name: {key!r}")
        result[name] = _clean_range(value, f"otherRanges.{name}")
    return result


def _clean_models(raw: Any, models: dict) -> list[str]:
    if not isinstance(raw, list):
        raise CatalogError("`models` must be a list of model ids.")
    result: list[str] = []
    seen: set[str] = set()
    for value in raw:
        model_id = str(value)
        if model_id in seen:
            continue
        entry = models.get(model_id)
        if not isinstance(entry, dict):
            raise CatalogError(f"Unknown model id: {model_id}")
        if entry.get("role") != "base":
            raise CatalogError(f"{model_id} is not a base model.")
        seen.add(model_id)
        result.append(model_id)
    return result


def update_lora(lora_id: str, patch: dict) -> dict:
    with _LOCK:
        catalog = load_catalog()
        loras = catalog.get("loras") or {}
        models = catalog.get("models") or {}
        entry = loras.get(lora_id)
        if not isinstance(entry, dict):
            raise KeyError(f"Unknown LoRA: {lora_id}")

        if "label" in patch:
            label = str(patch.get("label") or "").strip()
            entry["label"] = label[:120] or _stem(str(entry.get("name") or ""))
        if "base" in patch:
            base = str(patch.get("base") or "").strip()
            entry["base"] = _slug(base) if base else None
            entry["family"] = base_label(entry["base"]) if entry["base"] else None
        if "triggers" in patch:
            entry["triggers"] = _clean_triggers(patch.get("triggers"))
        if "models" in patch:
            entry["models"] = _clean_models(patch.get("models"), models)
            entry["modelsAuto"] = False
        if "modelsAuto" in patch:
            entry["modelsAuto"] = bool(patch.get("modelsAuto"))
        if "strength" in patch:
            entry["strength"] = _clean_range(patch.get("strength"), "strength")
        if "clipStrength" in patch:
            raw = patch.get("clipStrength")
            strength = _clean_range(raw, "clipStrength")
            strength["enabled"] = bool((raw or {}).get("enabled")) if isinstance(raw, dict) else False
            entry["clipStrength"] = strength
        if "otherRanges" in patch:
            entry["otherRanges"] = _clean_other_ranges(patch.get("otherRanges"))
        if "notes" in patch:
            entry["notes"] = str(patch.get("notes") or "").strip()[:2000]

        if entry.get("modelsAuto", True):
            entry["models"] = _default_models(entry.get("base"), models)
        else:
            # Keep links valid if a base/model edit renamed the entry.
            entry["models"] = [mid for mid in entry.get("models") or [] if mid in models]

        loras[lora_id] = entry
        catalog["loras"] = loras
        catalog["updatedAt"] = _now()
        _save_catalog(catalog)
        return _response(catalog)


def update_model(model_id: str, patch: dict) -> dict:
    with _LOCK:
        catalog = load_catalog()
        models = catalog.get("models") or {}
        entry = models.get(model_id)
        if not isinstance(entry, dict):
            raise KeyError(f"Unknown model: {model_id}")

        if "label" in patch:
            label = str(patch.get("label") or "").strip()
            entry["label"] = label[:120] or _stem(str(entry.get("name") or ""))
        if "base" in patch:
            base = str(patch.get("base") or "").strip()
            entry["base"] = _slug(base) if base else None
            entry["family"] = base_label(entry["base"]) if entry["base"] else None
        if "notes" in patch:
            entry["notes"] = str(patch.get("notes") or "").strip()[:2000]

        models[model_id] = entry
        catalog["models"] = models
        _relink_auto(catalog)
        catalog["updatedAt"] = _now()
        _save_catalog(catalog)
        return _response(catalog)


# -- trigger application (modules / composer) -----------------------------------


def _contains_word(text: str, word: str) -> bool:
    if not word:
        return True
    return re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", text, flags=re.IGNORECASE) is not None


def trigger_words(catalog: dict, lora_ids: list[str] | tuple[str, ...]) -> list[str]:
    """Trigger words for active LoRAs, in chain order, without duplicates."""
    loras = catalog.get("loras") if isinstance(catalog.get("loras"), dict) else {}
    result: list[str] = []
    seen: set[str] = set()
    for lora_id in lora_ids:
        entry = loras.get(str(lora_id))
        if not isinstance(entry, dict):
            continue
        for value in entry.get("triggers") or []:
            text = str(value).strip()
            key = " ".join(text.lower().split())
            if text and key not in seen:
                seen.add(key)
                result.append(text)
    return result


def prompt_with_triggers(catalog: dict, prompt: str, lora_ids: list[str] | tuple[str, ...]) -> str:
    """Append missing trigger words to a prompt; never duplicates one already there."""
    text = str(prompt or "").strip()
    missing = [word for word in trigger_words(catalog, lora_ids) if not _contains_word(text, word)]
    if not missing:
        return text
    return ", ".join([text, *missing]) if text else ", ".join(missing)
