"""Qwen Image 2.1 Turbo i2i pack registry + catalog merge.

The module owns one tracked pack under ``backend/pack``. The pack is the single
source of truth for:

- filenames, aliases and ranges (models.json)
- the one editable defaults file (defaults.json)
- sampler/resolution/source limits and recipe metadata (options.json)
- the API-format graph (workflows/qwen_i2i.api.json)

The user model catalog supplies installed-file presence and the *real* filename.
Aliases never rename or move a file; the resolved filename is bound into the
graph.

The catalog here is intentionally stricter than a plain alias search: the
user's Qwen3-VL text encoder may sit in ``models/unet`` and carry a filename
that looks like the diffusion model. It is never bound in that location because
ComfyUI's CLIPLoader only reads ``models/text_encoders``; instead it is reported
as misplaced so the setup/preflight text can explain the move.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.engine_content import catalog as user_catalog
from app.common.model_aliases import best_alias_match, normalize_token

logger = logging.getLogger("uvicorn.error")

MODULE_ID = "i2i_main"
BACKEND_DIR = Path(__file__).resolve().parent
MODULE_DIR = BACKEND_DIR.parent
PACK_DIR = BACKEND_DIR / "pack"
REQUIREMENTS_FILE = MODULE_DIR / "requirements.json"
MANIFEST_FILE = MODULE_DIR / "manifest.json"

MODEL_RANGE_KEYS = ("steps", "cfg", "denoise", "batch", "seed")


class PackError(Exception):
    pass


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(MODULE_DIR))
    except ValueError:
        return path.name


def _read_json(base: Path, name: str) -> dict:
    path = base / name
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PackError(f"i2i pack: cannot read `{_display_path(path)}`: {exc}") from exc
    except ValueError as exc:
        raise PackError(f"i2i pack: `{_display_path(path)}` is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise PackError(f"i2i pack: `{_display_path(path)}` must contain a JSON object.")
    return raw


def _read_workflow(base: Path, name: str) -> dict:
    path = (base / name).resolve()
    try:
        path.relative_to(PACK_DIR.resolve())
    except ValueError as exc:
        raise PackError(f"i2i pack: workflow `{name}` escapes `backend/pack`.") from exc
    return _read_json(base, name)


def _text(value: Any, field: str, *, required: bool = True, default: str = "") -> str:
    text = str(value or "").strip()
    if required and not text:
        raise PackError(f"i2i pack: `{field}` is required.")
    return text or default


def _bool(value: Any, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _number(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise PackError(f"i2i pack: `{field}` must be a number.") from exc


def _precision(step: float) -> int:
    text = f"{step:.6f}".rstrip("0").rstrip(".")
    return len(text.split(".")[1]) if "." in text else 0


def clean_range(raw: Any, field: str, fallback_default: Any = None) -> dict:
    """Validate one numeric range and return the GUI/backend contract."""
    if not isinstance(raw, dict):
        raise PackError(f"i2i pack: `{field}` must be an object.")
    minimum = _number(raw.get("min"), f"{field}.min")
    maximum = _number(raw.get("max"), f"{field}.max")
    if "default" in raw:
        default = _number(raw.get("default"), f"{field}.default")
    elif fallback_default is not None:
        default = _number(fallback_default, f"{field}.default")
    else:
        raise PackError(f"i2i pack: `{field}.default` is required when defaults.json is absent.")
    step = _number(raw.get("step"), f"{field}.step")
    hard_min = _number(raw.get("hardMin", minimum), f"{field}.hardMin")
    hard_max = _number(raw.get("hardMax", maximum), f"{field}.hardMax")
    recommended_min = _number(raw.get("recommendedMin", minimum), f"{field}.recommendedMin")
    recommended_max = _number(raw.get("recommendedMax", maximum), f"{field}.recommendedMax")

    if step <= 0:
        raise PackError(f"i2i pack: `{field}.step` must be greater than zero.")
    if not (hard_min <= minimum <= maximum <= hard_max):
        raise PackError(
            f"i2i pack: `{field}` must satisfy hardMin <= min <= max <= hardMax "
            f"({hard_min} <= {minimum} <= {maximum} <= {hard_max})."
        )
    if not (minimum <= default <= maximum):
        raise PackError(f"i2i pack: `{field}.default` must be inside min..max.")
    if not (minimum <= recommended_min <= recommended_max <= maximum):
        raise PackError(f"i2i pack: `{field}` recommended range must be inside min..max.")

    return {
        "label": str(raw.get("label") or field),
        "min": minimum,
        "max": maximum,
        "default": default,
        "step": step,
        "recommendedMin": recommended_min,
        "recommendedMax": recommended_max,
        "hardMin": hard_min,
        "hardMax": hard_max,
        "unit": str(raw.get("unit") or ""),
        "description": str(raw.get("description") or ""),
        "precision": _precision(step),
    }


def _clean_model(raw: Any, options: dict, pack: dict, defaults: dict) -> dict:
    if not isinstance(raw, dict):
        raise PackError("i2i pack: every models[] item must be an object.")
    model_id = _text(raw.get("id"), "models[].id")
    ranges_raw = raw.get("ranges")
    if not isinstance(ranges_raw, dict):
        raise PackError(f"i2i pack: `models.{model_id}.ranges` is required.")

    sampling = defaults["sampling"]
    fallback = {
        "steps": sampling["steps"],
        "cfg": sampling["cfg"],
        "denoise": sampling["denoise"],
        "batch": defaults["batch"],
        "seed": defaults["seed"],
    }
    ranges = {
        key: clean_range(ranges_raw.get(key), f"models.{model_id}.ranges.{key}", fallback[key])
        for key in MODEL_RANGE_KEYS
    }
    if int(ranges["batch"]["max"]) > int(options["limits"]["maxBatch"]):
        raise PackError(
            f"i2i pack: `models.{model_id}.ranges.batch.max` exceeds options.limits.maxBatch."
        )

    sampler_ids = {item["id"] for item in options["samplers"]}
    if sampling["sampler"] not in sampler_ids:
        raise PackError(
            f"i2i pack: defaults.sampling.sampler `{sampling['sampler']}` is not in options.samplers."
        )

    return {
        "id": model_id,
        "catalogId": str(raw.get("catalogId") or ""),
        "label": _text(raw.get("label"), f"models.{model_id}.label"),
        "shortLabel": str(raw.get("shortLabel") or raw.get("label") or model_id),
        "family": str(raw.get("family") or ""),
        "base": _text(raw.get("base"), f"models.{model_id}.base"),
        "description": str(raw.get("description") or ""),
        "packId": pack["id"],
        "packLabel": pack["label"],
        "loader": _text(raw.get("loader"), f"models.{model_id}.loader"),
        "file": _text(raw.get("file"), f"models.{model_id}.file"),
        "target": _text(raw.get("target"), f"models.{model_id}.target"),
        "aliases": _string_list(raw.get("aliases")),
        "fallbackAliases": _string_list(raw.get("fallbackAliases")),
        "excludeAliases": _string_list(raw.get("excludeAliases")),
        "baseGroup": str(raw.get("baseGroup") or ""),
        "baseGroupLabel": str(raw.get("baseGroupLabel") or ""),
        "required": _bool(raw.get("required"), True),
        "nsfw": _bool(raw.get("nsfw"), False),
        "pageUrl": str(raw.get("pageUrl") or ""),
        "textEncoder": _text(raw.get("textEncoder"), f"models.{model_id}.textEncoder"),
        "textEncoderAliases": _string_list(raw.get("textEncoderAliases")),
        "textEncoderExcludeAliases": _string_list(raw.get("textEncoderExcludeAliases")),
        "textEncoderTarget": str(raw.get("textEncoderTarget") or "text_encoders"),
        "clipType": _text(raw.get("clipType"), f"models.{model_id}.clipType"),
        "vae": _text(raw.get("vae"), f"models.{model_id}.vae"),
        "vaeAliases": _string_list(raw.get("vaeAliases")),
        "vaeExcludeAliases": _string_list(raw.get("vaeExcludeAliases")),
        "vaeTarget": str(raw.get("vaeTarget") or "vae"),
        "workflow": _text(
            raw.get("workflow"),
            f"models.{model_id}.workflow",
            required=False,
            default=options["recipe"]["workflow"],
        ),
        "composer": _text(
            raw.get("composer"),
            f"models.{model_id}.composer",
            required=False,
            default=options["recipe"]["composer"],
        ),
        "vram": str(raw.get("vram") or ""),
        "capabilities": [str(item) for item in (raw.get("capabilities") or [])],
        "verified": _bool(raw.get("verified"), False),
        "tested": _bool(raw.get("tested"), False),
        "notes": str(raw.get("notes") or ""),
        "defaults": {
            "steps": int(sampling["steps"]),
            "cfg": float(sampling["cfg"]),
            "sampler": str(sampling["sampler"]),
            "scheduler": str(sampling["scheduler"]),
            "denoise": float(sampling["denoise"]),
        },
        "ranges": ranges,
    }


def _validate_workflow(workflow: Any, path: str) -> dict:
    if not isinstance(workflow, dict) or not workflow:
        raise PackError(f"i2i pack: workflow `{path}` must be a non-empty API-format object.")
    for node_id, node in workflow.items():
        if not isinstance(node, dict) or not isinstance(node.get("class_type"), str):
            raise PackError(f"i2i pack: workflow `{path}` node {node_id} has no class_type.")
        if not isinstance(node.get("inputs"), dict):
            raise PackError(f"i2i pack: workflow `{path}` node {node_id} has no inputs object.")
        class_type = node["class_type"]
        if "IAMCCS" in class_type or "Switch" in class_type:
            raise PackError(
                f"i2i pack: workflow `{path}` node {node_id} uses `{class_type}`. "
                "i2i_main forbids switch nodes; the composer prunes the graph instead."
            )
    return workflow


def _clean_options(raw: dict) -> dict:
    recipe = raw.get("recipe") or {}
    limits = raw.get("limits") or {}
    source = raw.get("source") or {}
    if not isinstance(recipe, dict) or not isinstance(limits, dict) or not isinstance(source, dict):
        raise PackError("i2i pack: options.recipe, options.limits and options.source must be objects.")

    samplers: list[dict] = []
    for item in raw.get("samplers") or []:
        if not isinstance(item, dict):
            raise PackError("i2i pack: options.samplers[] items must be objects.")
        samplers.append(
            {
                "id": _text(item.get("id"), "options.samplers[].id"),
                "label": str(item.get("label") or item.get("id")),
            }
        )
    if not samplers:
        raise PackError("i2i pack: options.samplers is required.")

    resolutions: list[dict] = []
    seen_values: set[int] = set()
    for item in raw.get("resolutions") or []:
        if not isinstance(item, dict):
            raise PackError("i2i pack: options.resolutions[] items must be objects.")
        value = int(_number(item.get("value"), "options.resolutions[].value"))
        if value < 0 or value > 4096:
            raise PackError("i2i pack: resolution values must be 0..4096.")
        if value in seen_values:
            raise PackError(f"i2i pack: duplicate resolution value `{value}`.")
        seen_values.add(value)
        resolutions.append({"value": value, "label": str(item.get("label") or f"{value} px")})
    if not resolutions:
        raise PackError("i2i pack: options.resolutions is required.")

    devices = [str(item) for item in (raw.get("cacheDevices") or []) if str(item).strip()]
    dtypes = [str(item) for item in (raw.get("cacheDtypes") or []) if str(item).strip()]
    if not devices or not dtypes:
        raise PackError("i2i pack: options.cacheDevices and options.cacheDtypes are required.")

    return {
        "version": int(raw.get("version") or 1),
        "recipe": {
            "id": _text(recipe.get("id"), "options.recipe.id"),
            "label": _text(recipe.get("label"), "options.recipe.label"),
            "workflow": _text(recipe.get("workflow"), "options.recipe.workflow"),
            "composer": _text(
                recipe.get("composer"),
                "options.recipe.composer",
                required=False,
                default="qwen21_i2i",
            ),
            "engine": str(recipe.get("engine") or "comfyui"),
            "description": str(recipe.get("description") or ""),
        },
        "samplers": samplers,
        "resolutions": sorted(resolutions, key=lambda item: item["value"]),
        "cacheDevices": devices,
        "cacheDtypes": dtypes,
        "limits": {
            "promptMaxChars": int(limits.get("promptMaxChars") or 8000),
            "negativePromptMaxChars": int(limits.get("negativePromptMaxChars") or 4000),
            "maxBatch": int(limits.get("maxBatch") or 4),
            "jobTimeoutSeconds": int(limits.get("jobTimeoutSeconds") or 1800),
            "pollIntervalSeconds": float(limits.get("pollIntervalSeconds") or 1.0),
            "historyTimeoutSeconds": float(limits.get("historyTimeoutSeconds") or 15),
            "downloadTimeoutSeconds": float(limits.get("downloadTimeoutSeconds") or 120),
            "downloadRetries": int(limits.get("downloadRetries") or 3),
        },
        "source": {
            "maxBytes": int(source.get("maxBytes") or 20 * 1024 * 1024),
            "maxSide": int(source.get("maxSide") or 4096),
            "maxPixels": int(source.get("maxPixels") or 80_000_000),
            "mimeTypes": _string_list(source.get("mimeTypes"))
            or ["image/png", "image/jpeg", "image/webp", "image/bmp"],
            "maxDataUrlChars": int(source.get("maxDataUrlChars") or 28_000_000),
            "thumbSize": int(source.get("thumbSize") or 384),
            "persistMaxChars": int(source.get("persistMaxChars") or 2_500_000),
            "maxImages": max(1, min(3, int(source.get("maxImages") or 3))),
        },
    }


def _clean_defaults(raw: Any, options: dict) -> dict:
    if not isinstance(raw, dict):
        raise PackError("i2i pack: defaults.json must contain a JSON object.")
    sampling_raw = raw.get("sampling") or {}
    cache_raw = raw.get("cache") or {}
    if not isinstance(sampling_raw, dict) or not isinstance(cache_raw, dict):
        raise PackError("i2i pack: defaults.sampling and defaults.cache must be objects.")

    resolution = int(_number(raw.get("resolution", 0), "defaults.resolution"))
    if resolution not in {item["value"] for item in options["resolutions"]}:
        raise PackError(f"i2i pack: defaults.resolution `{resolution}` is not in options.resolutions.")

    batch = int(_number(raw.get("batch", 1), "defaults.batch"))
    seed = int(_number(raw.get("seed", 0), "defaults.seed"))
    if batch < 1 or batch > int(options["limits"]["maxBatch"]):
        raise PackError(
            f"i2i pack: defaults.batch must be 1..{options['limits']['maxBatch']}."
        )
    if seed < 0:
        raise PackError("i2i pack: defaults.seed must be zero or greater.")

    sampling = {
        "steps": int(_number(sampling_raw.get("steps"), "defaults.sampling.steps")),
        "cfg": float(_number(sampling_raw.get("cfg"), "defaults.sampling.cfg")),
        "sampler": _text(sampling_raw.get("sampler"), "defaults.sampling.sampler"),
        "scheduler": _text(sampling_raw.get("scheduler"), "defaults.sampling.scheduler"),
        "denoise": float(_number(sampling_raw.get("denoise", 1.0), "defaults.sampling.denoise")),
    }
    if sampling["steps"] < 1:
        raise PackError("i2i pack: defaults.sampling.steps must be at least 1.")
    if sampling["sampler"] not in {item["id"] for item in options["samplers"]}:
        raise PackError("i2i pack: defaults.sampling.sampler is not in options.samplers.")
    if not (0.0 < sampling["denoise"] <= 1.0):
        raise PackError("i2i pack: defaults.sampling.denoise must be in (0, 1].")

    cache = {
        "device": _text(cache_raw.get("device"), "defaults.cache.device"),
        "dtype": _text(cache_raw.get("dtype"), "defaults.cache.dtype"),
    }
    if cache["device"] not in options["cacheDevices"]:
        raise PackError("i2i pack: defaults.cache.device is not in options.cacheDevices.")
    if cache["dtype"] not in options["cacheDtypes"]:
        raise PackError("i2i pack: defaults.cache.dtype is not in options.cacheDtypes.")

    return {
        "modelId": _text(raw.get("modelId"), "defaults.modelId"),
        "prompt": str(raw.get("prompt") or ""),
        "negativePrompt": str(raw.get("negativePrompt") or ""),
        "resolution": resolution,
        "batch": batch,
        "seed": seed,
        "lockSeed": _bool(raw.get("lockSeed"), False),
        "sampling": sampling,
        "cache": cache,
    }


def _load_registry() -> list[dict]:
    raw = _read_json(PACK_DIR, "registry.json")
    entries = raw.get("packs")
    if not isinstance(entries, list) or not entries:
        raise PackError("i2i pack registry: `packs` must be a non-empty array.")
    default_id = str(raw.get("defaultPack") or "").strip()
    packs: list[dict] = []
    seen: set[str] = set()
    for item in entries:
        if not isinstance(item, dict):
            raise PackError("i2i pack registry: every packs[] item must be an object.")
        pack_id = _text(item.get("id"), "registry.packs[].id")
        if pack_id in seen:
            raise PackError(f"i2i pack registry: duplicate pack id `{pack_id}`.")
        seen.add(pack_id)
        path = str(item.get("path") or ".").strip().replace("\\", "/")
        if not path:
            raise PackError(f"i2i pack registry: pack `{pack_id}` has an empty path.")
        packs.append(
            {
                "id": pack_id,
                "label": str(item.get("label") or pack_id),
                "path": path,
                "default": pack_id == default_id,
            }
        )
    if default_id and default_id not in seen:
        raise PackError(f"i2i pack registry: defaultPack `{default_id}` is not a registered pack.")
    if not any(pack["default"] for pack in packs):
        packs[0]["default"] = True
    return packs


def _pack_root(entry: dict) -> Path:
    root = (PACK_DIR / str(entry["path"])).resolve()
    try:
        root.relative_to(PACK_DIR.resolve())
    except ValueError as exc:
        raise PackError(f"i2i pack registry: pack `{entry['id']}` path escapes `backend/pack`.") from exc
    if not root.is_dir():
        raise PackError(f"i2i pack registry: pack `{entry['id']}` directory is missing: {entry['path']}")
    return root


def _load_pack_entry(entry: dict) -> dict:
    root = _pack_root(entry)
    pack_meta = _read_json(root, "pack.json") if (root / "pack.json").is_file() else {}
    pack = {
        "id": entry["id"],
        "label": str(pack_meta.get("label") or entry["label"]),
        "path": entry["path"],
        "description": str(pack_meta.get("description") or ""),
        "nsfw": _bool(pack_meta.get("nsfw"), False),
        "order": int(pack_meta.get("order") or 0),
    }
    options = _clean_options(_read_json(root, "options.json"))
    defaults = _clean_defaults(_read_json(root, "defaults.json"), options)
    models_raw = _read_json(root, "models.json")

    models: dict[str, dict] = {}
    for item in models_raw.get("models") or []:
        model = _clean_model(item, options, pack, defaults)
        if model["id"] in models:
            raise PackError(f"i2i pack `{pack['id']}`: duplicate model id `{model['id']}`.")
        models[model["id"]] = model
    if not models:
        raise PackError(f"i2i pack `{pack['id']}`: models.json has no models.")

    workflow_paths = {str(model["workflow"]) for model in models.values()}
    workflow_paths.add(str(options["recipe"]["workflow"]))
    workflows = {
        path: _validate_workflow(_read_workflow(root, path), path) for path in sorted(workflow_paths)
    }
    default_workflow = workflows[str(options["recipe"]["workflow"])]

    if defaults.get("modelId") not in models:
        raise PackError(
            f"i2i pack `{pack['id']}`: defaults.modelId `{defaults.get('modelId')}` is not a model."
        )

    return {
        **pack,
        "version": int(options["version"]),
        "default": bool(entry.get("default")),
        "options": options,
        "defaults": defaults,
        "recipe": options["recipe"],
        "models": models,
        "workflow": default_workflow,
        "workflows": workflows,
    }


_registry_cache: dict[str, dict] | None = None
_registry_cache_mtime: float | None = None


def _pack_mtime() -> float:
    latest = 0.0
    for path in PACK_DIR.rglob("*.json"):
        try:
            latest = max(latest, path.stat().st_mtime)
        except OSError:
            continue
    return latest


def load_packs(*, fresh: bool = True) -> dict[str, dict]:
    """Load every registered pack. The registry is small enough to reload per request."""
    global _registry_cache, _registry_cache_mtime
    mtime = _pack_mtime()
    if not fresh and _registry_cache is not None and _registry_cache_mtime == mtime:
        return _registry_cache
    packs: dict[str, dict] = {}
    seen_models: set[str] = set()
    for entry in _load_registry():
        pack = _load_pack_entry(entry)
        if pack["id"] in packs:
            raise PackError(f"i2i pack registry: duplicate pack id `{pack['id']}`.")
        overlap = seen_models.intersection(pack["models"])
        if overlap:
            raise PackError(
                f"i2i pack registry: model id(s) `{', '.join(sorted(overlap))}` are declared by more than one pack."
            )
        seen_models.update(pack["models"])
        packs[pack["id"]] = pack
    _registry_cache = packs
    _registry_cache_mtime = mtime
    return packs


def load_pack(pack_id: str | None = None) -> dict:
    packs = load_packs()
    if pack_id:
        pack = packs.get(pack_id)
        if pack is None:
            raise PackError(f"i2i pack registry: unknown pack `{pack_id}`.")
        return pack
    return next((pack for pack in packs.values() if pack.get("default")), next(iter(packs.values())))


def pack_for_model(model_id: str | None) -> dict | None:
    wanted = str(model_id or "").strip()
    if not wanted:
        return None
    for pack in load_packs().values():
        if wanted in pack["models"]:
            return pack
    return None


# -- user catalog merge ---------------------------------------------------------


def load_user_catalog() -> dict:
    """Read the user-owned catalog for presence/triggers; never raise."""
    try:
        raw = user_catalog.load_catalog()
        models = raw.get("models") if isinstance(raw.get("models"), dict) else {}
        loras = raw.get("loras") if isinstance(raw.get("loras"), dict) else {}
        return {
            "available": bool(models or loras),
            "models": models,
            "loras": loras,
            "createdAt": raw.get("createdAt"),
            "updatedAt": raw.get("updatedAt"),
            "source": raw.get("source") if isinstance(raw.get("source"), dict) else {},
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - a broken catalog must not break the module
        return {
            "available": False,
            "models": {},
            "loras": {},
            "createdAt": None,
            "updatedAt": None,
            "source": {},
            "error": str(exc),
        }


def _index_catalog(cat: dict) -> dict:
    models = cat.get("models") or {}
    model_entries = [entry for entry in models.values() if isinstance(entry, dict)]
    return {
        "modelEntries": model_entries,
        "modelsById": {str(entry.get("id")): entry for entry in model_entries},
        "modelsByKey": {
            (str(entry.get("target") or ""), str(entry.get("name") or "")): entry
            for entry in model_entries
        },
        "modelsByName": {str(entry.get("name")): entry for entry in model_entries},
    }


def _entry_key(entry: dict) -> str:
    return (
        str(entry.get("id") or "")
        or f"{str(entry.get('target') or '').casefold()}::{str(entry.get('name') or '').casefold()}"
    )


def _entry_arch(entry: dict) -> str:
    """Header architecture, read from both live and saved catalog shapes."""
    return str(entry.get("architecture") or entry.get("arch") or "").strip().casefold()


def _is_text_encoder_entry(entry: dict | None) -> bool:
    """True when catalog metadata identifies a Qwen3-VL text encoder.

    Filenames are unreliable: the user's encoder was once shipped as
    ``Qwen-Image-2.1-Turbo-Uncensored-Q8_0.gguf`` inside ``models/unet``. The
    header metadata is authoritative, so a Qwen3-VL file can never bind as the
    diffusion model even when an alias happens to match its name.
    """
    if not isinstance(entry, dict):
        return False
    if str(entry.get("kind") or "").strip().casefold() in {"text_encoder", "clip"}:
        return True
    if _entry_arch(entry) in {"qwen3vl", "qwen3-vl", "qwen3_vl"}:
        return True
    return "qwen3vl" in normalize_token(entry.get("name"))


def _excluded(entry: dict, exclude_aliases: list[str] | None) -> bool:
    """Strict exclusion: the normalized alias must appear in the filename.

    ``name_has_alias`` also matches when every alias word appears separately,
    so excluding ``qwen_image_vae`` would reject ``qwen_image_2.1_vae_bf16``
    because it contains qwen, image and vae. Exclusions must be exact tokens.
    """
    if not exclude_aliases:
        return False
    token = normalize_token(entry.get("name"))
    return any(
        needle and needle in token
        for needle in (normalize_token(alias) for alias in exclude_aliases)
    )


def _best_match(
    entries: list[dict],
    aliases: list[str] | None,
    *,
    target: str | None = None,
    exclude_aliases: list[str] | None = None,
) -> dict | None:
    candidates = [
        entry
        for entry in entries
        if isinstance(entry, dict) and not _excluded(entry, exclude_aliases)
    ]
    return best_alias_match(candidates, aliases, target=target)


def _allowed(
    entry: dict | None,
    exclude_aliases: list[str] | None = None,
    *,
    reject_text_encoder: bool = False,
) -> bool:
    if entry is None or entry.get("present") is False:
        return False
    if _excluded(entry, exclude_aliases):
        return False
    if reject_text_encoder and _is_text_encoder_entry(entry):
        return False
    return True


def _find_entry(
    index: dict,
    catalog_id: str,
    file: str,
    target: str,
    *,
    exclude_aliases: list[str] | None = None,
    reject_text_encoder: bool = False,
) -> dict | None:
    if catalog_id and catalog_id in index["modelsById"]:
        entry = index["modelsById"][catalog_id]
        if _allowed(entry, exclude_aliases, reject_text_encoder=reject_text_encoder):
            return entry
    entry = index["modelsByKey"].get((target, file)) or index["modelsByName"].get(file)
    return (
        entry
        if _allowed(entry, exclude_aliases, reject_text_encoder=reject_text_encoder)
        else None
    )


def _model_entries(pack: dict, index: dict) -> dict[str, dict | None]:
    """Resolve the diffusion file, preferring specific aliases over fallbacks."""
    claimed: set[str] = set()
    resolved: dict[str, dict | None] = {}
    for model in pack["models"].values():
        exclude = model.get("excludeAliases") or []
        entry = _find_entry(
            index,
            model.get("catalogId", ""),
            model["file"],
            model["target"],
            exclude_aliases=exclude,
            reject_text_encoder=True,
        )
        if entry is None:
            entry = _best_match(
                [
                    item
                    for item in index["modelEntries"]
                    if _entry_key(item) not in claimed
                    and not _is_text_encoder_entry(item)
                ],
                [*model.get("aliases", []), model["file"]],
                target=model["target"],
                exclude_aliases=exclude,
            )
        resolved[model["id"]] = entry
        if entry is not None:
            claimed.add(_entry_key(entry))

    for model in pack["models"].values():
        if resolved.get(model["id"]) is not None or not model.get("fallbackAliases"):
            continue
        entry = _best_match(
            [
                item
                for item in index["modelEntries"]
                if _entry_key(item) not in claimed
                and not _is_text_encoder_entry(item)
            ],
            model["fallbackAliases"],
            target=model["target"],
            exclude_aliases=model.get("excludeAliases") or [],
        )
        if entry is not None:
            resolved[model["id"]] = entry
            claimed.add(_entry_key(entry))
    return resolved


def _component(
    index: dict,
    name: str,
    target: str,
    role: str,
    *,
    available: bool,
    aliases: list[str] | None = None,
    catalog_id: str = "",
    entry: dict | None = None,
    exclude_aliases: list[str] | None = None,
    metadata: str | None = None,
) -> dict:
    reject_text_encoder = role == "diffusion"
    if entry is None:
        entry = _find_entry(
            index,
            catalog_id,
            name,
            target,
            exclude_aliases=exclude_aliases,
            reject_text_encoder=reject_text_encoder,
        )
    if entry is None:
        candidates = index["modelEntries"]
        if reject_text_encoder:
            candidates = [item for item in candidates if not _is_text_encoder_entry(item)]
        entry = _best_match(
            candidates,
            [*(aliases or []), name],
            target=target,
            exclude_aliases=exclude_aliases,
        )
    if entry is None and metadata == "vae":
        entry = _find_vae_by_metadata(index, target=target, exclude_aliases=exclude_aliases)
    if entry is not None:
        present = bool(entry.get("present"))
        catalog_id = str(entry.get("id") or "")
        resolved_name = str(entry.get("name") or name)
    elif available:
        present = False
        catalog_id = ""
        resolved_name = name
    else:
        present = None
        catalog_id = ""
        resolved_name = name
    return {
        "role": role,
        "name": resolved_name,
        "declaredName": name,
        "target": target,
        "present": present,
        "catalogId": catalog_id,
    }


def _text_encoder_score(entry: dict) -> int:
    """Recognise a Qwen3-VL 8B encoder even when the filename is unconventional.

    Qwen Image 2.1 expects the 8B encoder. Larger (32B) and smaller (4B)
    Qwen3-VL models are installed in many catalogs for other modules, so they
    must not be bound here just because the architecture matches.

    The user's ``Qwen-Image-2.1-Turbo-Uncensored-Q8_0.gguf`` is catalogued as a
    Qwen3-VL text encoder even though its name looks like the diffusion model.
    Architecture metadata is the reliable signal when no size token exists.
    """
    name = str(entry.get("name") or "")
    arch = str(entry.get("architecture") or entry.get("arch") or "").casefold()
    normalized = name.casefold().replace("-", "_").replace(".", "_")
    tokens = re.split(r"[^a-z0-9]+", normalized)
    joined = "".join(tokens)

    is_vl = arch in {"qwen3vl", "qwen3-vl", "qwen3_vl"} or "qwen3vl" in joined
    if not is_vl:
        return 0
    if any(token in {"32b", "72b", "30b", "14b", "7b", "4b", "2b", "3b"} for token in tokens):
        return 0
    if "32b" in joined or "72b" in joined or "4b" in joined:
        return 0
    if "8b" in tokens or "8b" in joined:
        return 900
    # A Qwen3-VL filename without a size token (for example the user's
    # uncensored Q8 GGUF) is still accepted from catalog architecture metadata.
    return 760


def _find_by_metadata(index: dict, *, target: str | None) -> dict | None:
    candidates: list[tuple[int, dict]] = []
    for entry in index["modelEntries"]:
        if target and str(entry.get("target") or "").casefold() != target.casefold():
            continue
        if entry.get("present") is False:
            continue
        score = _text_encoder_score(entry)
        if score > 0:
            candidates.append((score, entry))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _vae_score(entry: dict) -> int:
    """Recognise the Qwen Image 2.1 VAE from header metadata after a rename.

    The 2.1 VAE declares ``qwen_image_2.1_vae`` in its safetensors header. The
    older ``qwen_image_vae.safetensors`` has no architecture metadata and must
    never satisfy this check, however it is renamed.
    """
    if _is_text_encoder_entry(entry):
        return 0
    arch = _entry_arch(entry).replace("-", "_")
    if arch.startswith("qwen_image_2.1") or arch.startswith("qwen_image_2_1"):
        return 900
    return 0


def _find_vae_by_metadata(
    index: dict,
    *,
    target: str | None,
    exclude_aliases: list[str] | None = None,
) -> dict | None:
    best: tuple[int, dict] | None = None
    for entry in index["modelEntries"]:
        if target and str(entry.get("target") or "").casefold() != target.casefold():
            continue
        if not _allowed(entry, exclude_aliases):
            continue
        score = _vae_score(entry)
        if score > 0 and (best is None or score > best[0]):
            best = (score, entry)
    return best[1] if best else None


def _text_encoder_component(index: dict, model: dict, available: bool) -> tuple[dict, dict | None]:
    target = model["textEncoderTarget"]
    entry = _find_entry(
        index,
        "",
        model["textEncoder"],
        target,
        exclude_aliases=model.get("textEncoderExcludeAliases") or [],
    )
    if entry is None:
        entry = _best_match(
            index["modelEntries"],
            [*(model.get("textEncoderAliases") or []), model["textEncoder"]],
            target=target,
            exclude_aliases=model.get("textEncoderExcludeAliases") or [],
        )
    if entry is None:
        entry = _find_by_metadata(index, target=target)

    misplaced: dict | None = None
    if entry is None:
        misplaced = _find_by_metadata(index, target=None)
        if misplaced is None:
            misplaced = _best_match(
                index["modelEntries"],
                [*(model.get("textEncoderAliases") or []), model["textEncoder"]],
                target=None,
                exclude_aliases=model.get("textEncoderExcludeAliases") or [],
            )

    if entry is not None:
        present = bool(entry.get("present"))
        resolved_name = str(entry.get("name") or model["textEncoder"])
        catalog_id = str(entry.get("id") or "")
    elif available:
        present = False
        resolved_name = model["textEncoder"]
        catalog_id = ""
    else:
        present = None
        resolved_name = model["textEncoder"]
        catalog_id = ""
    suffix = resolved_name.casefold()
    loader = "CLIPLoaderGGUF" if suffix.endswith(".gguf") else "CLIPLoader"
    component = {
        "role": "text_encoder",
        "name": resolved_name,
        "declaredName": model["textEncoder"],
        "target": target,
        "present": present,
        "catalogId": catalog_id,
        "loader": loader,
    }
    location = None
    if misplaced is not None:
        location = {
            "name": str(misplaced.get("name") or ""),
            "target": str(misplaced.get("target") or ""),
            "catalogId": str(misplaced.get("id") or ""),
        }
    return component, location


def _find_old_vae(index: dict) -> dict | None:
    """The pre-2.1 Qwen Image VAE, matched by exact normalized stem.

    Loose alias matching would also hit ``qwen_image_2.1_vae_bf16`` because it
    contains the words qwen, image and vae, so this check stays strict.
    """
    for entry in index["modelEntries"]:
        if str(entry.get("target") or "").casefold() != "vae":
            continue
        if entry.get("present") is False:
            continue
        if "qwenimagevae" in normalize_token(entry.get("name")):
            return entry
    return None


def _model_state(
    model: dict,
    index: dict,
    available: bool,
    *,
    base_entry: dict | None = None,
) -> dict:
    base = _component(
        index,
        model["file"],
        model["target"],
        "diffusion",
        available=available,
        aliases=model.get("aliases") or [],
        catalog_id=model.get("catalogId", ""),
        entry=base_entry,
        exclude_aliases=model.get("excludeAliases") or [],
    )
    text_encoder, text_encoder_location = _text_encoder_component(index, model, available)
    vae = _component(
        index,
        model["vae"],
        model["vaeTarget"],
        "vae",
        available=available,
        aliases=model.get("vaeAliases") or [],
        exclude_aliases=model.get("vaeExcludeAliases") or [],
        metadata="vae",
    )
    old_vae = _find_old_vae(index)
    components = [base, text_encoder, vae]
    missing = [item["name"] for item in components if item["present"] is False]

    resolved_name = str(base["name"] or "")
    loader = str(model["loader"])
    if resolved_name.casefold().endswith(".gguf"):
        loader = "UnetLoaderGGUF"
    elif resolved_name.casefold().endswith((".safetensors", ".sft", ".ckpt")):
        loader = "UNETLoader"

    return {
        **model,
        "loader": loader,
        "file": base["name"],
        "declaredFile": model["file"],
        "textEncoder": text_encoder["name"],
        "declaredTextEncoder": model["textEncoder"],
        "textEncoderLoader": text_encoder["loader"],
        "textEncoderLocation": text_encoder_location,
        "vae": vae["name"],
        "declaredVae": model["vae"],
        "oldVaePresent": old_vae is not None,
        "oldVaeName": str(old_vae.get("name") or "") if old_vae else "",
        "present": base["present"],
        "ready": not missing,
        "missing": missing,
        "components": components + ([{**vae, "role": "old_vae", "name": str(old_vae.get("name") or ""), "present": True}] if old_vae and vae["present"] is False else []),
        "catalogIdFound": base["catalogId"],
    }


def _issue(code: str, message: str, field: str | None = None, severity: str = "warning", **extra: Any) -> dict:
    return {"code": code, "message": message, "field": field, "severity": severity, **extra}


def build_snapshot(
    pack: dict,
    user: dict | None = None,
    *,
    model_id: str | None = None,
    engine: dict | None = None,
    node_report: dict[str, bool | None] | None = None,
) -> dict:
    """Merge pack + user catalog + live engine/node checks into the GUI contract."""
    user = user or load_user_catalog()
    index = _index_catalog(user)
    available = bool(user.get("available"))
    base_entries = _model_entries(pack, index)
    models = [
        _model_state(model, index, available, base_entry=base_entries.get(model["id"]))
        for model in pack["models"].values()
    ]

    selected_model = None
    if model_id:
        selected_model = next((item for item in models if item["id"] == model_id), None)
        if selected_model is None:
            raise KeyError(f"Unknown model `{model_id}`.")
    if selected_model is None:
        selected_model = next(
            (item for item in models if item["id"] == pack["defaults"].get("modelId")),
            models[0],
        )

    warnings: list[dict] = []
    errors: list[dict] = []
    if user.get("error"):
        warnings.append(
            _issue(
                "user_catalog_error",
                f"Model catalog could not be read; presence checks are unknown. {user['error']}",
            )
        )
    elif not available:
        warnings.append(
            _issue(
                "user_catalog_empty",
                "No model catalog yet. Presence is unknown; build it in Settings -> Model catalog for accurate checks.",
            )
        )

    for model in models:
        if model["present"] is False and model.get("required", True):
            errors.append(
                _issue(
                    "model_missing",
                    f"{model['label']} is missing: {', '.join(model['missing'])}",
                    "modelId",
                    "error",
                    modelId=model["id"],
                )
            )
        if model["present"] is not False and not model["tested"]:
            warnings.append(
                _issue(
                    "model_untested",
                    f"{model['label']} is implemented but not yet live-tested.",
                    "modelId",
                    "warning",
                    modelId=model["id"],
                )
            )
        if model.get("textEncoderLocation"):
            location = model["textEncoderLocation"]
            errors.append(
                _issue(
                    "text_encoder_misplaced",
                    f"Found a Qwen3-VL text encoder at `{location['target']}/{location['name']}`. "
                    "ComfyUI's CLIPLoader only reads `models/text_encoders`, so move the file there "
                    "(this app never moves it) and refresh the model catalog.",
                    "textEncoder",
                    "error",
                    found=location,
                )
            )
        if model.get("oldVaePresent") and model.get("vae") and not model["ready"]:
            warnings.append(
                _issue(
                    "old_vae_not_compatible",
                    f"`{model['oldVaeName']}` is the older Qwen Image VAE. It is not compatible "
                    "with Qwen Image 2.1; install `qwen_image_2.1_vae_bf16.safetensors`.",
                    "vae",
                )
            )

    comfy = (engine or {}).get("comfyui") or {}
    if engine is not None and not comfy.get("connected"):
        warnings.append(
            _issue(
                "comfyui_offline",
                "ComfyUI is offline. Generation is unavailable until it is running.",
            )
        )

    report = node_report or {}
    required_nodes = [
        "TextEncodeQwenImage21",
        "QwenImage21Cache",
        "RepeatLatentBatch",
        "ManualSigmas",
        "KSamplerSelect",
        "SamplerCustom",
    ]
    if selected_model and selected_model.get("loader") == "UnetLoaderGGUF":
        required_nodes.append("UnetLoaderGGUF")
    if selected_model and selected_model.get("textEncoderLoader") == "CLIPLoaderGGUF":
        required_nodes.append("CLIPLoaderGGUF")
    for node in required_nodes:
        state = report.get(node)
        if state is False:
            errors.append(
                _issue(
                    "node_missing",
                    f"ComfyUI node `{node}` is not installed. Update ComfyUI (Qwen Image 2.1 "
                    "nodes are built in) or install the required custom node.",
                    "nodes",
                    "error",
                    node=node,
                )
            )

    ready = bool(selected_model and selected_model.get("ready")) and not any(
        item.get("severity") == "error" for item in errors
    )

    defaults = {
        "modelId": selected_model["id"] if selected_model else pack["defaults"]["modelId"],
        "prompt": pack["defaults"]["prompt"],
        "negativePrompt": pack["defaults"]["negativePrompt"],
        "resolution": pack["defaults"]["resolution"],
        "batch": pack["defaults"]["batch"],
        "seed": pack["defaults"]["seed"],
        "lockSeed": pack["defaults"]["lockSeed"],
        "steps": pack["defaults"]["sampling"]["steps"],
        "cfg": pack["defaults"]["sampling"]["cfg"],
        "sampler": pack["defaults"]["sampling"]["sampler"],
        "scheduler": pack["defaults"]["sampling"]["scheduler"],
        "denoise": pack["defaults"]["sampling"]["denoise"],
        "cacheDevice": pack["defaults"]["cache"]["device"],
        "cacheDtype": pack["defaults"]["cache"]["dtype"],
        "recipeId": pack["recipe"]["id"],
    }

    workflow_path = selected_model["workflow"] if selected_model else pack["recipe"]["workflow"]
    workflow_graph = (pack.get("workflows") or {}).get(workflow_path, pack["workflow"])
    return {
        "ok": True,
        "moduleId": MODULE_ID,
        "pack": {
            "id": pack.get("id"),
            "label": pack.get("label"),
            "description": pack.get("description") or "",
            "nsfw": bool(pack.get("nsfw")),
            "order": int(pack.get("order") or 0),
        },
        "recipe": pack["recipe"],
        "workflow": {
            "path": workflow_path,
            "nodeCount": len(workflow_graph),
            "format": "comfyui-api",
            "referenceSlots": int(pack["options"]["source"]["maxImages"]),
        },
        "model": selected_model,
        "models": models,
        "selectedModelId": selected_model["id"] if selected_model else None,
        "defaults": defaults,
        "ranges": selected_model["ranges"] if selected_model else {},
        "samplers": pack["options"]["samplers"],
        "resolutions": pack["options"]["resolutions"],
        "cacheDevices": pack["options"]["cacheDevices"],
        "cacheDtypes": pack["options"]["cacheDtypes"],
        "limits": pack["options"]["limits"],
        "source": pack["options"]["source"],
        "engine": engine
        or {
            "comfyui": {"connected": False, "detail": "Not checked", "queue": {"running": 0, "pending": 0}},
            "ready": False,
        },
        "ready": ready,
        "preflight": {"errors": errors, "warnings": warnings},
        "warnings": errors + warnings,
    }
