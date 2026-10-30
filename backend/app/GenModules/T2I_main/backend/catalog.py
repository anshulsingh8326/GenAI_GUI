"""T2I_main pack registry + catalog merge.

The module owns one or more tracked packs under ``backend/pack``. The registry
(``registry.json``) lists them; each pack directory is authoritative for:

- per-model bindings, workflow, composer and ranges (models.json)
- per-LoRA ranges / triggers / exclusions (loras.json)
- upscale paths (upscalers.json)
- prompt-enhancement models (text_models.json)
- recipe defaults, ratios, sizes, sampler lists (options.json)
- the ComfyUI API workflow(s) under its own ``workflows/`` directory

A model always resolves through its pack. Separate families keep separate
workflows; a model may override its pack's default workflow/composer when its
loader or graph really differs. No model is added to another family's graph.

The user-owned ``data/model_catalog.json`` (app.engine_content.catalog) is used
only for installed-file presence and user-edited trigger words. It never
overrides the module's T2I ranges: a pro user edits the tracked pack to widen
ranges (up to the hard limits declared next to each range).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from app.common.model_aliases import best_alias_match
from app.engine_content import catalog as user_catalog

PACK_DIR = Path(__file__).resolve().parent / "pack"
REGISTRY_FILE = PACK_DIR / "registry.json"

MODEL_RANGE_KEYS = ("steps", "cfg", "denoise", "width", "height", "batch", "seed")
REFINE_RANGE_KEYS = ("steps", "cfg", "denoise", "scale")


class PackError(Exception):
    """The tracked T2I pack is missing or invalid."""


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PACK_DIR.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def _read_json(base: Path, name: str) -> dict:
    path = (base / name).resolve()
    try:
        path.relative_to(base.resolve())
    except ValueError as exc:
        raise PackError(f"T2I pack: `{name}` escapes its pack directory.") from exc
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PackError(f"Missing T2I pack file: {_display_path(path)}") from exc
    except ValueError as exc:
        raise PackError(f"T2I pack file is not valid JSON: {_display_path(path)}: {exc}") from exc
    if not isinstance(raw, dict):
        raise PackError(f"T2I pack file must contain a JSON object: {_display_path(path)}")
    return raw


def _text(value: Any, field: str, *, required: bool = True, default: str = "") -> str:
    text = str(value or "").strip()
    if required and not text:
        raise PackError(f"T2I pack: `{field}` is required.")
    return text or default


def _bool(value: Any, default: bool = False) -> bool:
    return bool(default if value is None else value)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _number(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise PackError(f"T2I pack: `{field}` must be a number.") from exc
    if not math.isfinite(number):
        raise PackError(f"T2I pack: `{field}` must be finite.")
    return number


def _precision(step: float) -> int:
    if step >= 1:
        return 0
    if step >= 0.1:
        return 1
    if step >= 0.01:
        return 2
    return 3


def clean_range(raw: Any, field: str) -> dict:
    """Validate one range and return the complete GUI/backend contract."""
    if not isinstance(raw, dict):
        raise PackError(f"T2I pack: `{field}` must be an object.")
    minimum = _number(raw.get("min"), f"{field}.min")
    maximum = _number(raw.get("max"), f"{field}.max")
    default = _number(raw.get("default"), f"{field}.default")
    step = _number(raw.get("step"), f"{field}.step")
    hard_min = _number(raw.get("hardMin", minimum), f"{field}.hardMin")
    hard_max = _number(raw.get("hardMax", maximum), f"{field}.hardMax")
    recommended_min = _number(raw.get("recommendedMin", minimum), f"{field}.recommendedMin")
    recommended_max = _number(raw.get("recommendedMax", maximum), f"{field}.recommendedMax")

    if step <= 0:
        raise PackError(f"T2I pack: `{field}.step` must be greater than zero.")
    if not (hard_min <= minimum <= maximum <= hard_max):
        raise PackError(
            f"T2I pack: `{field}` must satisfy hardMin <= min <= max <= hardMax "
            f"({hard_min} <= {minimum} <= {maximum} <= {hard_max})."
        )
    if not (minimum <= default <= maximum):
        raise PackError(f"T2I pack: `{field}.default` must be inside min..max.")
    if not (minimum <= recommended_min <= recommended_max <= maximum):
        raise PackError(f"T2I pack: `{field}` recommended range must be inside min..max.")

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


def _clean_model(raw: Any, options: dict, pack: dict) -> dict:
    if not isinstance(raw, dict):
        raise PackError("T2I pack: every models[] item must be an object.")
    model_id = _text(raw.get("id"), "models[].id")
    loader = _text(raw.get("loader"), f"models.{model_id}.loader")
    ranges_raw = raw.get("ranges")
    if not isinstance(ranges_raw, dict):
        raise PackError(f"T2I pack: `models.{model_id}.ranges` is required.")
    ranges = {key: clean_range(ranges_raw.get(key), f"models.{model_id}.ranges.{key}") for key in MODEL_RANGE_KEYS}
    refine_raw = ranges_raw.get("refine")
    if not isinstance(refine_raw, dict):
        raise PackError(f"T2I pack: `models.{model_id}.ranges.refine` is required.")
    ranges["refine"] = {
        key: clean_range(refine_raw.get(key), f"models.{model_id}.ranges.refine.{key}")
        for key in REFINE_RANGE_KEYS
    }

    defaults_raw = raw.get("defaults") or {}
    if not isinstance(defaults_raw, dict):
        raise PackError(f"T2I pack: `models.{model_id}.defaults` must be an object.")
    defaults = {
        "steps": int(defaults_raw.get("steps", ranges["steps"]["default"])),
        "cfg": float(defaults_raw.get("cfg", ranges["cfg"]["default"])),
        "sampler": str(defaults_raw.get("sampler") or "euler"),
        "scheduler": str(defaults_raw.get("scheduler") or "simple"),
        "denoise": float(defaults_raw.get("denoise", ranges["denoise"]["default"])),
    }
    sampler_ids = {item["id"] for item in options["samplers"]}
    scheduler_ids = {item["id"] for item in options["schedulers"]}
    if defaults["sampler"] not in sampler_ids:
        raise PackError(f"T2I pack: model {model_id} default sampler `{defaults['sampler']}` is not in options.samplers.")
    if defaults["scheduler"] not in scheduler_ids:
        raise PackError(
            f"T2I pack: model {model_id} default scheduler `{defaults['scheduler']}` is not in options.schedulers."
        )

    default_workflow = options["recipe"]["workflow"]
    default_composer = options["recipe"]["composer"]
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
        "loader": loader,
        "file": _text(raw.get("file"), f"models.{model_id}.file"),
        "target": _text(raw.get("target"), f"models.{model_id}.target"),
        "aliases": _string_list(raw.get("aliases")),
        "fallbackAliases": _string_list(raw.get("fallbackAliases")),
        "baseGroup": str(raw.get("baseGroup") or ""),
        "baseGroupLabel": str(raw.get("baseGroupLabel") or ""),
        "required": _bool(raw.get("required"), True),
        "nsfw": _bool(raw.get("nsfw"), False),
        "downloadUrl": str(raw.get("downloadUrl") or ""),
        "pageUrl": str(raw.get("pageUrl") or ""),
        "size": int(raw["size"]) if isinstance(raw.get("size"), (int, float)) and raw["size"] > 0 else None,
        "sha256": str(raw.get("sha256") or ""),
        "weightDtype": raw.get("weightDtype"),
        "textEncoder": _text(raw.get("textEncoder"), f"models.{model_id}.textEncoder"),
        "textEncoderAliases": _string_list(raw.get("textEncoderAliases")),
        "textEncoderTarget": str(raw.get("textEncoderTarget") or "text_encoders"),
        "clipType": _text(raw.get("clipType"), f"models.{model_id}.clipType"),
        "vae": _text(raw.get("vae"), f"models.{model_id}.vae"),
        "vaeAliases": _string_list(raw.get("vaeAliases")),
        "vaeTarget": str(raw.get("vaeTarget") or "vae"),
        "workflow": _text(
            raw.get("workflow"),
            f"models.{model_id}.workflow",
            required=False,
            default=default_workflow,
        ),
        "composer": _text(
            raw.get("composer"),
            f"models.{model_id}.composer",
            required=False,
            default=default_composer,
        ),
        "vram": str(raw.get("vram") or ""),
        "capabilities": [str(item) for item in (raw.get("capabilities") or [])],
        "verified": _bool(raw.get("verified"), False),
        "tested": _bool(raw.get("tested"), False),
        "notes": str(raw.get("notes") or ""),
        "defaults": defaults,
        "ranges": ranges,
    }


def _clean_lora(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise PackError("T2I pack: every loras[] item must be an object.")
    lora_id = _text(raw.get("id"), "loras[].id")
    base = _text(raw.get("base"), f"loras.{lora_id}.base")
    triggers: list[str] = []
    seen: set[str] = set()
    for value in raw.get("triggers") or []:
        text = str(value).strip()
        if not text:
            continue
        key = " ".join(text.lower().split())
        if key in seen:
            continue
        seen.add(key)
        triggers.append(text)
    return {
        "id": lora_id,
        "label": _text(raw.get("label"), f"loras.{lora_id}.label"),
        "file": _text(raw.get("file"), f"loras.{lora_id}.file"),
        "aliases": _string_list(raw.get("aliases")),
        "nsfw": _bool(raw.get("nsfw"), False),
        "base": base,
        "compatibleBases": [str(item) for item in (raw.get("compatibleBases") or [base])],
        "family": str(raw.get("family") or ""),
        "type": str(raw.get("type") or "style"),
        "t2i": _bool(raw.get("t2i"), True),
        "excludeReason": str(raw.get("excludeReason") or ""),
        "verified": _bool(raw.get("verified"), False),
        "tested": _bool(raw.get("tested"), False),
        "defaultOrder": int(raw.get("defaultOrder") or 0),
        "triggers": triggers,
        "strength": clean_range(raw.get("strength"), f"loras.{lora_id}.strength"),
        "notes": str(raw.get("notes") or ""),
    }


def _clean_upscaler(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise PackError("T2I pack: every upscalers[] item must be an object.")
    upscaler_id = _text(raw.get("id"), "upscalers[].id")
    kind = _text(raw.get("kind"), f"upscalers.{upscaler_id}.kind")
    if kind not in {"none", "latent", "esrgan"}:
        raise PackError(f"T2I pack: unsupported upscaler kind `{kind}`.")
    value_range = raw.get("valueRange")
    return {
        "id": upscaler_id,
        "label": _text(raw.get("label"), f"upscalers.{upscaler_id}.label"),
        "shortLabel": str(raw.get("shortLabel") or raw.get("label") or upscaler_id),
        "kind": kind,
        "file": raw.get("file"),
        "target": raw.get("target"),
        "aliases": _string_list(raw.get("aliases")),
        "scaleFactor": int(raw.get("scaleFactor") or 1),
        "enabledByDefault": _bool(raw.get("enabledByDefault"), False),
        "defaultValue": raw.get("defaultValue"),
        "valueRange": clean_range(value_range, f"upscalers.{upscaler_id}.valueRange") if value_range else None,
        "t2i": _bool(raw.get("t2i"), True),
        "verified": _bool(raw.get("verified"), False),
        "tested": _bool(raw.get("tested"), False),
        "notes": str(raw.get("notes") or ""),
    }


def _clean_text_model(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise PackError("T2I pack: every text_models.comfyui[] item must be an object.")
    text_id = _text(raw.get("id"), "text_models.comfyui[].id")
    return {
        "id": text_id,
        "label": _text(raw.get("label"), f"text_models.{text_id}.label"),
        "provider": "comfyui",
        "file": _text(raw.get("file"), f"text_models.{text_id}.file"),
        "target": str(raw.get("target") or "text_encoders"),
        "clipType": _text(raw.get("clipType"), f"text_models.{text_id}.clipType"),
        "node": str(raw.get("node") or "TextGenerate"),
        "maxLength": int(raw.get("maxLength") or 512),
        "verified": _bool(raw.get("verified"), False),
        "tested": _bool(raw.get("tested"), False),
        "vram": str(raw.get("vram") or ""),
        "notes": str(raw.get("notes") or ""),
    }


def _validate_workflow(workflow: Any, path: str) -> dict:
    if not isinstance(workflow, dict) or not workflow:
        raise PackError(f"T2I pack: workflow `{path}` must be a non-empty API-format object.")
    for node_id, node in workflow.items():
        if not isinstance(node, dict) or not isinstance(node.get("class_type"), str):
            raise PackError(f"T2I pack: workflow `{path}` node {node_id} has no class_type.")
        if not isinstance(node.get("inputs"), dict):
            raise PackError(f"T2I pack: workflow `{path}` node {node_id} has no inputs object.")
        class_type = node["class_type"]
        if "IAMCCS" in class_type or "Switch" in class_type:
            raise PackError(
                f"T2I pack: workflow `{path}` node {node_id} uses `{class_type}`. "
                "T2I_main forbids switch nodes; prune the graph instead."
            )
    return workflow


def _clean_options(raw: dict) -> dict:
    recipe = raw.get("recipe") or {}
    defaults = raw.get("defaults") or {}
    size = raw.get("size") or {}
    limits = raw.get("limits") or {}
    enhance = raw.get("enhance") or {}
    if not isinstance(recipe, dict) or not isinstance(defaults, dict):
        raise PackError("T2I pack: options.recipe/defaults must be objects.")

    ratios: list[dict] = []
    seen_ratios: set[str] = set()
    for item in raw.get("ratios") or []:
        if not isinstance(item, dict):
            raise PackError("T2I pack: options.ratios[] items must be objects.")
        ratio_id = _text(item.get("id"), "options.ratios[].id")
        if ratio_id in seen_ratios:
            raise PackError(f"T2I pack: duplicate ratio id `{ratio_id}`.")
        seen_ratios.add(ratio_id)
        w = _number(item.get("w"), f"options.ratios.{ratio_id}.w")
        h = _number(item.get("h"), f"options.ratios.{ratio_id}.h")
        if w <= 0 or h <= 0:
            raise PackError(f"T2I pack: ratio `{ratio_id}` needs positive w/h.")
        ratios.append({"id": ratio_id, "label": str(item.get("label") or ratio_id), "w": w, "h": h, "value": w / h})

    samplers = []
    for item in raw.get("samplers") or []:
        if not isinstance(item, dict):
            raise PackError("T2I pack: options.samplers[] items must be objects.")
        samplers.append({"id": _text(item.get("id"), "options.samplers[].id"), "label": str(item.get("label") or item.get("id"))})
    schedulers = []
    for item in raw.get("schedulers") or []:
        if not isinstance(item, dict):
            raise PackError("T2I pack: options.schedulers[] items must be objects.")
        schedulers.append(
            {"id": _text(item.get("id"), "options.schedulers[].id"), "label": str(item.get("label") or item.get("id"))}
        )
    if not ratios or not samplers or not schedulers:
        raise PackError("T2I pack: options.ratios, options.samplers and options.schedulers are required.")

    values = [int(value) for value in (size.get("values") or [])]
    step = int(size.get("step") or 64)
    if step <= 0 or not values:
        raise PackError("T2I pack: options.size.values and a positive step are required.")

    return {
        "version": int(raw.get("version") or 1),
        "recipe": {
            "id": _text(recipe.get("id"), "options.recipe.id"),
            "label": _text(recipe.get("label"), "options.recipe.label"),
            "workflow": _text(recipe.get("workflow"), "options.recipe.workflow"),
            "composer": _text(recipe.get("composer"), "options.recipe.composer", required=False, default="krea2"),
            "engine": str(recipe.get("engine") or "comfyui"),
            "description": str(recipe.get("description") or ""),
        },
        "defaults": defaults,
        "ratios": ratios,
        "size": {
            "label": str(size.get("label") or "Size"),
            "longSideDefault": int(size.get("longSideDefault") or 1024),
            "step": step,
            "values": sorted(set(values)),
            "description": str(size.get("description") or ""),
        },
        "samplers": samplers,
        "schedulers": schedulers,
        "limits": {
            "promptMaxChars": int(limits.get("promptMaxChars") or 8000),
            "negativePromptMaxChars": int(limits.get("negativePromptMaxChars") or 4000),
            "maxLoras": int(limits.get("maxLoras") or 8),
            "jobTimeoutSeconds": int(limits.get("jobTimeoutSeconds") or 1800),
            "pollIntervalSeconds": float(limits.get("pollIntervalSeconds") or 1.0),
            "historyTimeoutSeconds": float(limits.get("historyTimeoutSeconds") or 15),
            "enhanceTimeoutSeconds": float(limits.get("enhanceTimeoutSeconds") or 240),
            "downloadTimeoutSeconds": float(limits.get("downloadTimeoutSeconds") or 120),
            "downloadRetries": int(limits.get("downloadRetries") or 3),
        },
        "enhance": {
            "systemPromptKey": str(enhance.get("systemPromptKey") or "enhance"),
            "defaultProvider": str(enhance.get("defaultProvider") or "ollama"),
            "ollama": {
                "temperature": float((enhance.get("ollama") or {}).get("temperature") or 0.7),
                "numPredict": int((enhance.get("ollama") or {}).get("numPredict") or 512),
                "timeoutSeconds": float((enhance.get("ollama") or {}).get("timeoutSeconds") or 240),
            },
            "comfyui": {
                "maxLength": int((enhance.get("comfyui") or {}).get("maxLength") or 512),
                "temperature": float((enhance.get("comfyui") or {}).get("temperature") or 0.7),
                "topK": int((enhance.get("comfyui") or {}).get("topK") or 64),
                "topP": float((enhance.get("comfyui") or {}).get("topP") or 0.95),
                "minP": float((enhance.get("comfyui") or {}).get("minP") or 0.05),
                "repetitionPenalty": float((enhance.get("comfyui") or {}).get("repetitionPenalty") or 1.05),
                "presencePenalty": float((enhance.get("comfyui") or {}).get("presencePenalty") or 0.0),
                "timeoutSeconds": float((enhance.get("comfyui") or {}).get("timeoutSeconds") or 240),
            },
        },
    }


def _load_registry() -> list[dict]:
    """Read the pack registry, with a legacy single-pack fallback."""
    if not REGISTRY_FILE.is_file():
        return [{"id": "default", "label": "Default", "path": ".", "default": True}]

    raw = _read_json(PACK_DIR, "registry.json")
    entries = raw.get("packs")
    if not isinstance(entries, list) or not entries:
        raise PackError("T2I pack registry: `packs` must be a non-empty array.")

    default_id = str(raw.get("defaultPack") or "").strip()
    packs: list[dict] = []
    seen: set[str] = set()
    for item in entries:
        if not isinstance(item, dict):
            raise PackError("T2I pack registry: every packs[] item must be an object.")
        pack_id = _text(item.get("id"), "registry.packs[].id")
        if pack_id in seen:
            raise PackError(f"T2I pack registry: duplicate pack id `{pack_id}`.")
        seen.add(pack_id)
        path = str(item.get("path") or ".").strip().replace("\\", "/")
        if not path:
            raise PackError(f"T2I pack registry: pack `{pack_id}` has an empty path.")
        packs.append(
            {
                "id": pack_id,
                "label": str(item.get("label") or pack_id),
                "path": path,
                "default": pack_id == default_id,
            }
        )

    if default_id and default_id not in seen:
        raise PackError(f"T2I pack registry: defaultPack `{default_id}` is not a registered pack.")
    if not any(pack["default"] for pack in packs):
        packs[0]["default"] = True
    return packs


def _pack_root(entry: dict) -> Path:
    root = (PACK_DIR / str(entry["path"])).resolve()
    try:
        root.relative_to(PACK_DIR.resolve())
    except ValueError as exc:
        raise PackError(f"T2I pack registry: pack `{entry['id']}` path escapes `backend/pack`.") from exc
    if not root.is_dir():
        raise PackError(f"T2I pack registry: pack `{entry['id']}` directory is missing: {entry['path']}")
    return root


def _load_pack_entry(entry: dict) -> dict:
    """Load one pack directory and validate its internal references."""
    root = _pack_root(entry)
    pack_meta = _read_json(root, "pack.json") if (root / "pack.json").is_file() else {}
    if not isinstance(pack_meta, dict):
        raise PackError(f"T2I pack `{entry['id']}`: pack.json must contain a JSON object.")
    pack = {
        "id": entry["id"],
        "label": str(pack_meta.get("label") or entry["label"]),
        "path": entry["path"],
        "description": str(pack_meta.get("description") or ""),
        "nsfw": _bool(pack_meta.get("nsfw"), False),
        "order": int(pack_meta.get("order") or 0),
    }
    options = _clean_options(_read_json(root, "options.json"))
    models_raw = _read_json(root, "models.json")
    loras_raw = _read_json(root, "loras.json")
    upscalers_raw = _read_json(root, "upscalers.json")
    text_raw = _read_json(root, "text_models.json")

    models: dict[str, dict] = {}
    for item in models_raw.get("models") or []:
        model = _clean_model(item, options, pack)
        if model["id"] in models:
            raise PackError(f"T2I pack `{pack['id']}`: duplicate model id `{model['id']}`.")
        models[model["id"]] = model

    loras: dict[str, dict] = {}
    for item in loras_raw.get("loras") or []:
        lora = _clean_lora(item)
        if lora["id"] in loras:
            raise PackError(f"T2I pack `{pack['id']}`: duplicate LoRA id `{lora['id']}`.")
        loras[lora["id"]] = lora

    upscalers: dict[str, dict] = {}
    for item in upscalers_raw.get("upscalers") or []:
        upscaler = _clean_upscaler(item)
        if upscaler["id"] in upscalers:
            raise PackError(f"T2I pack `{pack['id']}`: duplicate upscaler id `{upscaler['id']}`.")
        upscalers[upscaler["id"]] = upscaler

    comfy_text_models: dict[str, dict] = {}
    for item in text_raw.get("comfyui") or []:
        text_model = _clean_text_model(item)
        if text_model["id"] in comfy_text_models:
            raise PackError(
                f"T2I pack `{pack['id']}`: duplicate ComfyUI text model id `{text_model['id']}`."
            )
        comfy_text_models[text_model["id"]] = text_model

    ollama_raw = text_raw.get("ollama") or {}
    if not isinstance(ollama_raw, dict):
        raise PackError(f"T2I pack `{pack['id']}`: text_models.ollama must be an object.")
    ollama_text = {
        "autoDiscover": _bool(ollama_raw.get("autoDiscover"), True),
        "preferred": [str(item).strip() for item in (ollama_raw.get("preferred") or []) if str(item).strip()],
        "notes": str(ollama_raw.get("notes") or ""),
    }

    workflow_paths = {str(model["workflow"]) for model in models.values()}
    workflow_paths.add(str(options["recipe"]["workflow"]))
    workflows = {
        path: _validate_workflow(_read_json(root, path), path)
        for path in sorted(workflow_paths)
    }
    default_workflow = workflows[str(options["recipe"]["workflow"])]

    defaults = options["defaults"]
    if defaults.get("modelId") not in models:
        raise PackError(
            f"T2I pack `{pack['id']}`: options.defaults.modelId "
            f"`{defaults.get('modelId')}` is not a model."
        )
    upscaler_default = defaults.get("upscaler") or {}
    if upscaler_default.get("id") not in upscalers:
        raise PackError(f"T2I pack `{pack['id']}`: options.defaults.upscaler.id is not a known upscaler.")
    for ref in defaults.get("loraChain") or []:
        if not isinstance(ref, dict) or ref.get("id") not in loras:
            raise PackError(
                f"T2I pack `{pack['id']}`: default LoRA chain references unknown id `{ref}`."
            )

    return {
        **pack,
        "version": int(options["version"]),
        "default": bool(entry.get("default")),
        "options": options,
        "recipe": options["recipe"],
        "models": models,
        "loras": loras,
        "upscalers": upscalers,
        "comfyTextModels": comfy_text_models,
        "ollamaText": ollama_text,
        "workflow": default_workflow,
        "workflows": workflows,
    }


def load_packs() -> dict[str, dict]:
    """Load every registered pack. Model ids are global inside the module."""
    packs: dict[str, dict] = {}
    seen_models: set[str] = set()
    for entry in _load_registry():
        pack = _load_pack_entry(entry)
        if pack["id"] in packs:
            raise PackError(f"T2I pack registry: duplicate pack id `{pack['id']}`.")
        overlap = seen_models.intersection(pack["models"])
        if overlap:
            raise PackError(
                f"T2I pack registry: model id(s) `{', '.join(sorted(overlap))}` are declared by more than one pack."
            )
        seen_models.update(pack["models"])
        packs[pack["id"]] = pack
    return packs


def load_pack(pack_id: str | None = None) -> dict:
    """Load one pack by id, or the registry's default pack."""
    packs = load_packs()
    if pack_id:
        pack = packs.get(pack_id)
        if pack is None:
            raise PackError(f"T2I pack registry: unknown pack `{pack_id}`.")
        return pack
    return next((pack for pack in packs.values() if pack.get("default")), next(iter(packs.values())))


def pack_for_model(model_id: str | None) -> dict | None:
    """Resolve the pack that owns a model id, or None for an unknown model."""
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
    except Exception as exc:  # noqa: BLE001 - a broken user catalog must not break T2I
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
    loras = cat.get("loras") or {}
    model_entries = [entry for entry in models.values() if isinstance(entry, dict)]
    lora_entries = [entry for entry in loras.values() if isinstance(entry, dict)]
    return {
        "modelEntries": model_entries,
        "loraEntries": lora_entries,
        "modelsById": {str(entry.get("id")): entry for entry in model_entries},
        "modelsByKey": {
            (str(entry.get("target") or ""), str(entry.get("name") or "")): entry
            for entry in model_entries
        },
        "modelsByName": {str(entry.get("name")): entry for entry in model_entries},
        "lorasById": {str(entry.get("id")): entry for entry in lora_entries},
        "lorasByKey": {
            (str(entry.get("target") or ""), str(entry.get("name") or "")): entry
            for entry in lora_entries
        },
        "lorasByName": {str(entry.get("name")): entry for entry in lora_entries},
    }


def _entry_key(entry: dict) -> str:
    return (
        str(entry.get("id") or "")
        or f"{str(entry.get('target') or '').casefold()}::{str(entry.get('name') or '').casefold()}"
    )


def _find_entry(
    index: dict,
    catalog_id: str,
    file: str,
    target: str,
    *,
    loras: bool = False,
) -> dict | None:
    prefix = "loras" if loras else "models"
    if catalog_id and catalog_id in index[f"{prefix}ById"]:
        entry = index[f"{prefix}ById"][catalog_id]
        if entry.get("present") is not False:
            return entry
    entry = (
        index[f"{prefix}ByKey"].get((target, file))
        or index[f"{prefix}ByName"].get(file)
    )
    return entry if entry is not None and entry.get("present") is not False else None


def _find_model(index: dict, catalog_id: str, file: str, target: str) -> dict | None:
    return _find_entry(index, catalog_id, file, target)


def _find_lora(index: dict, lora_id: str, file: str) -> dict | None:
    return _find_entry(index, lora_id, file, "loras", loras=True)


def _model_entries(pack: dict, index: dict) -> dict[str, dict | None]:
    """Resolve each model's base file, preferring specific aliases.

    A specific alias always wins. `fallbackAliases` (for example a generic
    `krea2`) only claims a catalog file that no sibling model claimed by a
    specific alias. This keeps a Q5-only install from marking SNOFS present,
    while still accepting an official/generic Krea 2 base file.
    """
    claimed: set[str] = set()
    resolved: dict[str, dict | None] = {}
    for model in pack["models"].values():
        entry = _find_model(index, model.get("catalogId", ""), model["file"], model["target"])
        if entry is None:
            aliases = [*model.get("aliases", []), model["file"]]
            entry = best_alias_match(
                [item for item in index["modelEntries"] if _entry_key(item) not in claimed],
                aliases,
                target=model["target"],
            )
        resolved[model["id"]] = entry
        if entry is not None:
            claimed.add(_entry_key(entry))

    for model in pack["models"].values():
        if resolved.get(model["id"]) is not None or not model.get("fallbackAliases"):
            continue
        entry = best_alias_match(
            [item for item in index["modelEntries"] if _entry_key(item) not in claimed],
            model["fallbackAliases"],
            target=model["target"],
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
) -> dict:
    if entry is None:
        entry = _find_entry(index, catalog_id, name, target)
    if entry is None:
        entry = best_alias_match(
            index["modelEntries"],
            [*(aliases or []), name],
            target=target,
        )
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


def _lora_state(lora: dict, index: dict, available: bool) -> dict:
    entry = _find_lora(index, lora["id"], lora["file"])
    if entry is None:
        entry = best_alias_match(
            index["loraEntries"],
            [*(lora.get("aliases") or []), lora["file"]],
            target="loras",
        )
    if entry is not None:
        present = bool(entry.get("present"))
        triggers = [str(item) for item in (entry.get("triggers") or [])]
        resolved_file = str(entry.get("name") or lora["file"])
    elif available:
        present = False
        triggers = list(lora["triggers"])
        resolved_file = lora["file"]
    else:
        present = None
        triggers = list(lora["triggers"])
        resolved_file = lora["file"]
    return {
        **lora,
        "file": resolved_file,
        "declaredFile": lora["file"],
        "present": present,
        "triggers": triggers,
        "catalogId": str(entry.get("id") or "") if entry else "",
        "catalogLabel": str(entry.get("label") or "") if entry else "",
    }


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
    )
    text_encoder = _component(
        index,
        model["textEncoder"],
        model["textEncoderTarget"],
        "text_encoder",
        available=available,
        aliases=model.get("textEncoderAliases") or [],
    )
    vae = _component(
        index,
        model["vae"],
        model["vaeTarget"],
        "vae",
        available=available,
        aliases=model.get("vaeAliases") or [],
    )
    components = [base, text_encoder, vae]
    missing = [item["name"] for item in components if item["present"] is False]
    return {
        **model,
        "file": base["name"],
        "declaredFile": model["file"],
        "textEncoder": text_encoder["name"],
        "declaredTextEncoder": model["textEncoder"],
        "vae": vae["name"],
        "declaredVae": model["vae"],
        "present": base["present"],
        "ready": not missing,
        "missing": missing,
        "components": components,
        "catalogIdFound": base["catalogId"],
    }


def _upscaler_state(upscaler: dict, index: dict, available: bool) -> dict:
    if not upscaler.get("file"):
        return {**upscaler, "present": True, "missing": [], "components": []}
    component = _component(
        index,
        str(upscaler["file"]),
        str(upscaler.get("target") or ""),
        "upscaler",
        available=available,
        aliases=upscaler.get("aliases") or [],
    )
    return {
        **upscaler,
        "file": component["name"],
        "declaredFile": upscaler["file"],
        "present": component["present"],
        "missing": [] if component["present"] is not False else [component["name"]],
        "components": [component],
    }


def _apply_base_groups(models: list[dict]) -> None:
    groups: dict[str, list[dict]] = {}
    for model in models:
        group = str(model.get("baseGroup") or "").strip()
        if group:
            groups.setdefault(group, []).append(model)

    for group, members in groups.items():
        values = [member.get("present") for member in members]
        if any(value is True for value in values):
            satisfied: bool | None = True
        elif values and all(value is False for value in values):
            satisfied = False
        else:
            satisfied = None
        label = next((str(member.get("baseGroupLabel") or "") for member in members if member.get("baseGroupLabel")), group)
        for member in members:
            member["baseGroupSatisfied"] = satisfied
            member["baseGroupLabel"] = label


def build_snapshot(
    pack: dict,
    user: dict | None = None,
    *,
    model_id: str | None = None,
    engine: dict | None = None,
    text_models: list[dict] | None = None,
    defaults_extra: dict | None = None,
) -> dict:
    """Merge pack + user catalog + live engine status into the GUI contract."""
    user = user or load_user_catalog()
    index = _index_catalog(user)
    available = bool(user.get("available"))
    base_entries = _model_entries(pack, index)
    models = [
        _model_state(model, index, available, base_entry=base_entries.get(model["id"]))
        for model in pack["models"].values()
    ]
    _apply_base_groups(models)
    loras = [_lora_state(lora, index, available) for lora in pack["loras"].values()]
    upscalers = [_upscaler_state(item, index, available) for item in pack["upscalers"].values()]

    for model in models:
        model["compatibleLoras"] = [
            lora["id"]
            for lora in loras
            if lora["t2i"] and (model["base"] in lora["compatibleBases"] or lora["base"] == model["base"])
        ]
        model["samplers"] = pack["options"]["samplers"]
        model["schedulers"] = pack["options"]["schedulers"]

    for lora in loras:
        lora["compatibleModels"] = [
            model["id"]
            for model in models
            if model["base"] in lora["compatibleBases"] or lora["base"] == model["base"]
        ]
        lora["available"] = bool(lora["t2i"] and lora["compatibleModels"])

    default_chain = []
    for ref in pack["options"]["defaults"].get("loraChain") or []:
        lora = next((item for item in loras if item["id"] == ref.get("id")), None)
        if not lora:
            continue
        default_chain.append(
            {
                "id": lora["id"],
                "label": lora["label"],
                "strength": float(ref.get("strength", lora["strength"]["default"])),
                "on": bool(ref.get("on", True)),
                "triggers": lora["triggers"],
                "present": lora["present"],
            }
        )

    selected_model = None
    if model_id:
        selected_model = next((item for item in models if item["id"] == model_id), None)
        if selected_model is None:
            raise KeyError(f"Unknown model `{model_id}`.")
    if selected_model is None:
        default_id = pack["options"]["defaults"].get("modelId")
        selected_model = next((item for item in models if item["id"] == default_id), models[0] if models else None)
        # A configured default may be absent on disk. Prefer an installed model
        # from the same one-of base group, then any installed model.
        if selected_model and selected_model.get("present") is False:
            alternatives = [
                item
                for item in models
                if item["id"] != selected_model["id"] and item.get("present") is True
            ]
            same_group = [
                item
                for item in alternatives
                if selected_model.get("baseGroup")
                and item.get("baseGroup") == selected_model.get("baseGroup")
            ]
            selected_model = (same_group or alternatives or [selected_model])[0]

    if text_models is None:
        text_models = []
        for item in pack["comfyTextModels"].values():
            state = _component(index, item["file"], item["target"], "text_encoder", available=available)
            text_models.append({**item, "present": state["present"], "catalogId": state["catalogId"]})

    defaults = dict(pack["options"]["defaults"])
    defaults["loraChain"] = default_chain
    if selected_model:
        defaults["modelId"] = selected_model["id"]
        defaults["steps"] = selected_model["defaults"]["steps"]
        defaults["cfg"] = selected_model["defaults"]["cfg"]
        defaults["sampler"] = selected_model["defaults"]["sampler"]
        defaults["scheduler"] = selected_model["defaults"]["scheduler"]
        defaults["denoise"] = selected_model["defaults"]["denoise"]
        defaults["refine"] = {
            key: selected_model["ranges"]["refine"][key]["default"] for key in REFINE_RANGE_KEYS
        }
    if defaults_extra:
        defaults.update(defaults_extra)

    warnings: list[dict] = []
    if user.get("error"):
        warnings.append(
            {
                "code": "user_catalog_error",
                "message": f"Model catalog could not be read; presence checks are unknown. {user['error']}",
            }
        )
    elif not available:
        warnings.append(
            {
                "code": "user_catalog_empty",
                "message": "No model catalog yet. Presence is unknown; build it in Settings -> Model catalog for accurate checks.",
            }
        )
    missing_groups: set[str] = set()
    for model in models:
        group = str(model.get("baseGroup") or "").strip()
        if group:
            if model.get("baseGroupSatisfied") is False and group not in missing_groups:
                missing_groups.add(group)
                options = ", ".join(
                    f"{item['label']} ({', '.join(item['missing'])})"
                    for item in models
                    if item.get("baseGroup") == group
                )
                warnings.append(
                    {
                        "code": "model_group_missing",
                        "baseGroup": group,
                        "message": f"{model.get('baseGroupLabel') or group}: install one base model. Missing: {options}",
                    }
                )
            if model["present"] is False:
                continue
        elif model["present"] is False and model.get("required", True):
            warnings.append(
                {
                    "code": "model_missing",
                    "modelId": model["id"],
                    "message": f"{model['label']} is missing: {', '.join(model['missing'])}",
                }
            )
        if model["present"] is not False and not model["tested"]:
            warnings.append(
                {
                    "code": "model_untested",
                    "modelId": model["id"],
                    "message": f"{model['label']} is implemented but not yet live-tested.",
                }
            )
    for lora in loras:
        if lora["t2i"] and lora["present"] is False:
            warnings.append(
                {
                    "code": "lora_missing",
                    "loraId": lora["id"],
                    "message": f"LoRA file is missing: {lora['file']}",
                }
            )

    workflow_path = selected_model["workflow"] if selected_model else pack["recipe"]["workflow"]
    workflow_graph = (pack.get("workflows") or {}).get(workflow_path, pack["workflow"])
    return {
        "ok": True,
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
        },
        "models": models,
        "selectedModelId": selected_model["id"] if selected_model else None,
        "loras": sorted(loras, key=lambda item: (item["defaultOrder"], item["label"].lower())),
        "upscalers": upscalers,
        "textModels": text_models,
        "ratios": pack["options"]["ratios"],
        "size": pack["options"]["size"],
        "samplers": pack["options"]["samplers"],
        "schedulers": pack["options"]["schedulers"],
        "limits": pack["options"]["limits"],
        "defaults": defaults,
        "engine": engine or {},
        "catalog": {
            "available": available,
            "updatedAt": user.get("updatedAt"),
            "createdAt": user.get("createdAt"),
            "source": user.get("source") or {},
            "error": user.get("error"),
        },
        "warnings": warnings,
    }
