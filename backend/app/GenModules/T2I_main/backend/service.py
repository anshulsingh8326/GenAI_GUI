"""T2I_main service - validation, prompt enhancement, job runner, collection.

This is the only place that turns a T2I request into a ComfyUI prompt. It is
intentionally strict:

- the tracked pack is reloaded per request, so a pro user's range edit applies
  without a restart;
- every numeric input is checked against the model/LoRA/upscaler pack range and
  against the engine hard limit;
- the same graph composer is used by /validate and /jobs, so a request that
  validates cannot silently become a different graph;
- ComfyUI/iAMCCS switches are never used - the graph composer prunes blocks.

Jobs are persisted through app.jobs.service. The runner polls ComfyUI history,
downloads output bytes and registers them through app.library.service. If the
backend restarts, `resume_pending_jobs()` reattaches to the stored prompt id.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from pathlib import Path
from typing import Any

import httpx

from app.common import module_setup, settings_store
from app.connectors import service as connectors
from app.jobs import service as jobs
from app.library import service as library

from . import catalog, workflows
from .schema import T2IEnhanceRequest, T2IJobRequest

logger = logging.getLogger("uvicorn.error")

MODULE_ID = "T2I_main"
TAB_ID = "text-to-image"
MODULE_DIR = Path(__file__).resolve().parent.parent
REQUIREMENTS_FILE = MODULE_DIR / "requirements.json"
MANIFEST_FILE = MODULE_DIR / "manifest.json"
STAGE_DEFS = (
    ("enhance", "Enhance prompt"),
    ("compose", "Compose workflow"),
    ("submit", "Submit to ComfyUI"),
    ("generate", "Generate image"),
    ("collect", "Collect results"),
)

_TASKS: dict[str, asyncio.Task] = {}
_CANCEL: dict[str, asyncio.Event] = {}


class ValidationError(Exception):
    def __init__(self, errors: list[dict], warnings: list[dict] | None = None):
        self.errors = errors
        self.warnings = warnings or []
        first = errors[0]["message"] if errors else "Invalid T2I request"
        super().__init__(first)


class EngineError(Exception):
    """ComfyUI/Ollama is unavailable or rejected/failed the request."""


class JobCancelled(Exception):
    pass


def _issue(code: str, message: str, field: str | None = None, **extra: Any) -> dict:
    item: dict[str, Any] = {"code": code, "message": message}
    if field:
        item["field"] = field
    item.update(extra)
    return item


def _fmt(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:g}"


def _err_text(err: BaseException) -> str:
    """httpx timeouts stringify to '', which makes job errors useless."""
    text = str(err).strip()
    return text or type(err).__name__


def _engine_error(engine: str, url: str, err: BaseException) -> str:
    where = url or "the configured URL"
    if isinstance(err, (httpx.ConnectError, httpx.ConnectTimeout)):
        return f"{engine} is not reachable at {where}. Start it and try again."
    if isinstance(err, httpx.TimeoutException):
        return f"{engine} timed out at {where} while sending the request."
    if isinstance(err, httpx.HTTPStatusError):
        detail = err.response.text[:600] if err.response is not None else ""
        return f"{engine} returned HTTP {err.response.status_code}: {detail or _err_text(err)}"
    if isinstance(err, RuntimeError) and str(err).strip():
        return str(err).strip()
    return f"{engine} request failed at {where}: {_err_text(err)}"


def _range_value(
    rng: dict,
    raw: Any,
    field: str,
    errors: list[dict],
    warnings: list[dict],
    *,
    integer: bool = False,
    align_step: bool = False,
    warn_align: bool = True,
) -> float | int:
    """Validate one value against a pack range and return the normalized value."""
    label = str(rng.get("label") or field)
    value = rng["default"] if raw is None else raw
    try:
        number = float(value)
    except (TypeError, ValueError):
        errors.append(_issue("not_a_number", f"{label} must be a number.", field))
        return rng["default"]
    if number != number or number in (float("inf"), float("-inf")):
        errors.append(_issue("not_a_number", f"{label} must be a finite number.", field))
        return rng["default"]

    if integer:
        rounded = int(round(number))
        if abs(rounded - number) > 1e-6:
            warnings.append(_issue("normalized_integer", f"{label} was rounded to {rounded}.", field))
        number = rounded

    hard_min, hard_max = float(rng["hardMin"]), float(rng["hardMax"])
    raw_in_range = True
    if number < hard_min or number > hard_max:
        raw_in_range = False
        errors.append(
            _issue(
                "out_of_hard_range",
                f"{label} {_fmt(number)} is outside the engine hard range {_fmt(hard_min)}-{_fmt(hard_max)}.",
                field,
                min=hard_min,
                max=hard_max,
            )
        )
        number = max(hard_min, min(hard_max, number))

    safe_min, safe_max = float(rng["min"]), float(rng["max"])
    if number < safe_min or number > safe_max:
        raw_in_range = False
        errors.append(
            _issue(
                "out_of_safe_range",
                f"{label} {_fmt(number)} is outside this model's safe range {_fmt(safe_min)}-{_fmt(safe_max)}. "
                "A pro user can widen the safe range in the T2I pack JSON, up to the hard limit.",
                field,
                min=safe_min,
                max=safe_max,
            )
        )

    # Align after the raw check, then re-check the aligned output. Rounding must
    # never move a value outside the safe/hard range without being reported.
    if align_step:
        step = float(rng["step"])
        if step > 0:
            aligned = round(number / step) * step
            if abs(aligned - number) > 1e-9:
                if warn_align:
                    warnings.append(
                        _issue(
                            "normalized_step",
                            f"{label} was aligned to the {_fmt(step)} step ({_fmt(aligned)}).",
                            field,
                        )
                    )
                number = aligned
                if raw_in_range:
                    if number < hard_min or number > hard_max:
                        errors.append(
                            _issue(
                                "out_of_hard_range",
                                f"{label} aligns to {_fmt(number)}, outside the engine hard range "
                                f"{_fmt(hard_min)}-{_fmt(hard_max)}.",
                                field,
                                min=hard_min,
                                max=hard_max,
                            )
                        )
                    elif number < safe_min or number > safe_max:
                        errors.append(
                            _issue(
                                "out_of_safe_range",
                                f"{label} aligns to {_fmt(number)}, outside this model's safe range "
                                f"{_fmt(safe_min)}-{_fmt(safe_max)}. "
                                "A pro user can widen the safe range in the T2I pack JSON, up to the hard limit.",
                                field,
                                min=safe_min,
                                max=safe_max,
                            )
                        )

    if raw_in_range and safe_min <= number <= safe_max:
        if number < float(rng["recommendedMin"]) or number > float(rng["recommendedMax"]):
            warnings.append(
                _issue(
                    "outside_recommended",
                    f"{label} {_fmt(number)} is safe but outside the recommended "
                    f"{_fmt(rng['recommendedMin'])}-{_fmt(rng['recommendedMax'])}.",
                    field,
                    recommendedMin=rng["recommendedMin"],
                    recommendedMax=rng["recommendedMax"],
                )
            )

    return int(number) if integer else round(number, 6)


def _ratio_map(pack: dict) -> dict[str, dict]:
    return {str(item["id"]): item for item in pack["options"]["ratios"]}


def _resolve_model(pack: dict, model_id: str) -> dict:
    wanted = (model_id or "").strip() or str(pack["options"]["defaults"].get("modelId") or "")
    model = pack["models"].get(wanted)
    if model is None:
        raise ValidationError(
            [
                _issue(
                    "unknown_model",
                    f"Unknown T2I model `{wanted}`. Available: {', '.join(pack['models'])}.",
                    "modelId",
                )
            ]
        )
    return model


def _resolve_size(
    payload: T2IJobRequest,
    model: dict,
    pack: dict,
    errors: list[dict],
    warnings: list[dict],
) -> tuple[int, int, str, int]:
    """Resolve explicit width/height or ratio+long-side to a 64-px-aligned size."""
    options = pack["options"]
    ratios = _ratio_map(pack)
    width_range = model["ranges"]["width"]
    height_range = model["ranges"]["height"]

    explicit = payload.width is not None or payload.height is not None
    if explicit and payload.width is not None and payload.height is not None:
        width = _range_value(width_range, payload.width, "width", errors, warnings, integer=True, align_step=True)
        height = _range_value(height_range, payload.height, "height", errors, warnings, integer=True, align_step=True)
        ratio_id = (payload.ratio or "").strip() or "custom"
        if payload.ratio:
            ratio = ratios.get(str(payload.ratio))
            if ratio is None:
                errors.append(_issue("unknown_ratio", f"Unknown aspect ratio `{payload.ratio}`.", "ratio"))
            else:
                actual = width / max(1, height)
                if abs(actual - float(ratio["value"])) > 0.02:
                    warnings.append(
                        _issue(
                            "ratio_mismatch",
                            f"Width/height ({width}x{height}) does not match ratio {payload.ratio}; the explicit size wins.",
                            "ratio",
                        )
                    )
        size = max(int(width), int(height))
        return int(width), int(height), ratio_id, size

    if explicit:
        errors.append(
            _issue(
                "incomplete_size",
                "Provide both width and height, or use ratio + size.",
                "width" if payload.width is None else "height",
            )
        )
        # If ratio+size is also present, fall through and use it. Otherwise use
        # the model defaults so the error response still has a usable shape.
        if payload.ratio is None and payload.size is None:
            width = int(width_range["default"])
            height = int(height_range["default"])
            return width, height, "1:1", max(width, height)

    ratio_id = (payload.ratio or str(options["defaults"].get("ratio") or "1:1")).strip() or "1:1"
    ratio = ratios.get(ratio_id)
    if ratio is None:
        errors.append(
            _issue(
                "unknown_ratio",
                f"Unknown aspect ratio `{ratio_id}`. Available: {', '.join(ratios)}.",
                "ratio",
            )
        )
        ratio_id = "1:1"
        ratio = ratios["1:1"]

    long_range = width_range if float(ratio["w"]) >= float(ratio["h"]) else height_range
    size_raw = payload.size if payload.size is not None else options["defaults"].get("size") or options["size"]["longSideDefault"]
    size = _range_value(long_range, size_raw, "size", errors, warnings, integer=True, align_step=True)

    if float(ratio["w"]) >= float(ratio["h"]):
        width = int(size)
        height = int(round(size * float(ratio["h"]) / max(1.0, float(ratio["w"]))))
    else:
        height = int(size)
        width = int(round(size * float(ratio["w"]) / max(1.0, float(ratio["h"]))))

    # Ratio-derived dimensions are aligned every time (16:9 at 1152 becomes
    # 1152x640). The UI now shows that derived size, so only explicit
    # width/height requests should flag 64-step normalization as a warning.
    width = _range_value(
        width_range,
        width,
        "width",
        errors,
        warnings,
        integer=True,
        align_step=True,
        warn_align=False,
    )
    height = _range_value(
        height_range,
        height,
        "height",
        errors,
        warnings,
        integer=True,
        align_step=True,
        warn_align=False,
    )
    return int(width), int(height), ratio_id, max(int(width), int(height))


def _resolve_loras(
    payload: T2IJobRequest,
    snapshot: dict,
    model: dict,
    pack: dict,
    errors: list[dict],
    warnings: list[dict],
) -> list[dict]:
    lora_map = {str(item["id"]): item for item in snapshot.get("loras") or []}
    refs = list(payload.loras or [])
    max_loras = int(pack["options"]["limits"]["maxLoras"])
    ordered: list[tuple[int, Any]] = list(enumerate(refs))
    if any(ref.order is not None for _, ref in ordered):
        ordered.sort(key=lambda pair: (pair[1].order if pair[1].order is not None else pair[0], pair[0]))

    selected: list[dict] = []
    seen: set[str] = set()
    for _, ref in ordered:
        if not ref.on:
            continue
        lora = lora_map.get(str(ref.id))
        if lora is None:
            errors.append(_issue("unknown_lora", f"Unknown LoRA `{ref.id}`.", "loras"))
            continue
        if lora["id"] in seen:
            errors.append(_issue("duplicate_lora", f"LoRA `{lora['label']}` appears more than once.", "loras"))
            continue
        seen.add(lora["id"])
        if not lora.get("t2i", True):
            reason = lora.get("excludeReason") or "not part of strict Text -> Image."
            errors.append(_issue("lora_excluded", f"{lora['label']} is not available here: {reason}", "loras"))
            continue
        if model["base"] not in (lora.get("compatibleBases") or [lora.get("base")]) and lora.get("base") != model["base"]:
            errors.append(
                _issue(
                    "lora_incompatible",
                    f"{lora['label']} targets {lora.get('base')}, not {model['base']}.",
                    "loras",
                )
            )
            continue
        if lora.get("present") is False:
            errors.append(_issue("lora_missing", f"{lora['label']} is missing: {lora['file']}", "loras"))
            continue
        if len(selected) >= max_loras:
            errors.append(_issue("too_many_loras", f"At most {max_loras} LoRAs can be chained.", "loras"))
            break
        strength = _range_value(
            lora["strength"],
            ref.strength,
            f"loras.{lora['id']}.strength",
            errors,
            warnings,
        )
        if lora.get("present") is None:
            warnings.append(
                _issue(
                    "lora_presence_unknown",
                    f"{lora['label']}: file presence is unknown until the model catalog is built.",
                    "loras",
                )
            )
        if not lora.get("tested", False):
            warnings.append(
                _issue("lora_untested", f"{lora['label']} is available but not yet live-tested.", "loras")
            )
        selected.append(
            {
                "id": lora["id"],
                "label": lora["label"],
                "file": lora["file"],
                "base": lora["base"],
                "strength": strength,
                "triggers": list(lora.get("triggers") or []),
                "present": lora.get("present"),
            }
        )
    return selected


def _resolve_upscaler(
    payload: T2IJobRequest,
    model: dict,
    snapshot: dict,
    pack: dict,
    errors: list[dict],
    warnings: list[dict],
) -> dict:
    options = pack["options"]
    defaults = options["defaults"].get("upscaler") or {}
    requested = payload.advanced.upscaler if payload.advanced else None
    upscaler_id = (requested.id if requested and requested.id else defaults.get("id")) or "none"
    snapshot_upscalers = {str(item["id"]): item for item in snapshot.get("upscalers") or []}
    upscaler = snapshot_upscalers.get(str(upscaler_id)) or pack["upscalers"].get(str(upscaler_id))
    if upscaler is None:
        errors.append(
            _issue(
                "unknown_upscaler",
                f"Unknown upscaler `{upscaler_id}`. Available: {', '.join(pack['upscalers'])}.",
                "advanced.upscaler.id",
            )
        )
        upscaler_id = str(defaults.get("id") or "none")
        upscaler = pack["upscalers"][upscaler_id]
    if not upscaler.get("t2i", True):
        errors.append(_issue("upscaler_excluded", f"{upscaler['label']} is not available for T2I.", "advanced.upscaler.id"))

    if requested and requested.enabled is not None:
        enabled = bool(requested.enabled)
    elif requested and requested.id and str(requested.id) != str(defaults.get("id")):
        # Explicitly picking a non-default path means "use it" unless the
        # caller also sent enabled: false.
        enabled = True
    elif str(upscaler_id) == str(defaults.get("id")):
        enabled = bool(defaults.get("enabled", upscaler.get("enabledByDefault", False)))
    else:
        enabled = bool(upscaler.get("enabledByDefault", False))

    kind = upscaler["kind"]
    if kind == "none":
        enabled = False

    value = None
    if kind in {"latent", "esrgan"}:
        value_range = model["ranges"]["refine"]["scale"] if kind == "latent" else upscaler.get("valueRange")
        if not value_range:
            errors.append(_issue("upscaler_range_missing", f"{upscaler['label']} has no value range."))
            value_range = model["ranges"]["refine"]["scale"]
        if kind == "esrgan" and upscaler.get("present") is False:
            errors.append(
                _issue(
                    "upscaler_missing",
                    f"{upscaler['label']} is missing: {upscaler.get('file')}",
                    "advanced.upscaler.id",
                )
            )
        elif kind == "esrgan" and upscaler.get("present") is None:
            warnings.append(
                _issue(
                    "upscaler_presence_unknown",
                    f"{upscaler['label']}: file presence is unknown until the model catalog is built.",
                    "advanced.upscaler.id",
                )
            )
        if enabled:
            raw_value = requested.value if requested and requested.value is not None else None
            if raw_value is None:
                if str(upscaler_id) == str(defaults.get("id")):
                    raw_value = defaults.get("value")
                raw_value = raw_value if raw_value is not None else upscaler.get("defaultValue") or value_range["default"]
            value = _range_value(
                value_range,
                raw_value,
                "advanced.upscaler.value",
                errors,
                warnings,
                integer=True,
                align_step=True,
            )
        else:
            # A disabled block must not reject a stale value from another path.
            value = value_range["default"]

    return {
        "id": upscaler["id"],
        "label": upscaler["label"],
        "shortLabel": upscaler["shortLabel"],
        "kind": kind,
        "enabled": enabled,
        "value": value,
        "file": upscaler.get("file"),
        "target": upscaler.get("target"),
        "tested": upscaler.get("tested", False),
        "notes": upscaler.get("notes", ""),
    }


# Ollama's /api/tags also lists embedding-only models. They are valid for
# embeddings but cannot rewrite a prompt, so never offer them as enhancers.
_EMBEDDING_MARKERS = (
    "embed",
    "nomic-embed",
    "mxbai-embed",
    "bge-",
    "snowflake-arctic-embed",
    "all-minilm",
)


def _is_ollama_text_model(name: str) -> bool:
    lowered = (name or "").casefold()
    return bool(lowered) and not any(marker in lowered for marker in _EMBEDDING_MARKERS)


def _ollama_text_names(installed: list[dict]) -> list[str]:
    return [
        str(item.get("name"))
        for item in installed or []
        if item.get("name") and _is_ollama_text_model(str(item.get("name")))
    ]


def _match_installed(name: str, installed: list[str]) -> str:
    wanted = (name or "").strip()
    if not wanted:
        return ""
    names = [str(item) for item in installed]
    if wanted in names:
        return wanted
    if f"{wanted}:latest" in names:
        return f"{wanted}:latest"
    if wanted.endswith(":latest") and wanted[:-7] in names:
        return wanted[:-7]
    return ""


def _ollama_model_score(name: str) -> int:
    lowered = name.casefold()
    score = 0
    if "abliterated" in lowered or "uncensored" in lowered:
        score += 6
    if any(token in lowered for token in ("qwen", "gemma", "llama", "mistral", "phi", "deepseek", "gpt-oss", "nemotron")):
        score += 3
    if "instruct" in lowered or "chat" in lowered:
        score += 1
    if "code" in lowered or "coder" in lowered:
        score -= 3
    if "vision" in lowered or "-vl" in lowered:
        score -= 1
    if "cloud" in lowered:
        score -= 2
    return score


def _pick_ollama_model(settings: dict, pack: dict, installed: list[str]) -> str:
    names = [name for name in installed if _is_ollama_text_model(name)]
    if not names:
        return ""
    defaults = settings.get("defaults") or {}
    desired = str(defaults.get("enhanceModel") or "").strip()
    match = _match_installed(desired, names) if desired else ""
    if match:
        return match
    for preferred in pack.get("ollamaText", {}).get("preferred") or []:
        match = _match_installed(str(preferred), names)
        if match:
            return match
    # No configured/preferred model is installed. Pick the most plausible
    # local chat model instead of an embedding or cloud-only one.
    return sorted(names, key=lambda name: (-_ollama_model_score(name), name.casefold()))[0]


def _find_comfy_text_model(pack: dict, requested: str) -> dict | None:
    models = pack.get("comfyTextModels") or {}
    wanted = (requested or "").strip()
    if not wanted:
        return next((item for item in models.values() if item.get("verified")), None)
    if wanted in models:
        return models[wanted]
    return next(
        (item for item in models.values() if wanted in {item.get("file"), item.get("label"), item.get("id")}),
        None,
    )


def _resolve_enhance(
    payload: T2IJobRequest,
    pack: dict,
    settings: dict,
    errors: list[dict],
    warnings: list[dict],
) -> dict:
    options = pack["options"]
    cfg = options["enhance"]
    defaults = options["defaults"]
    raw = payload.enhance
    enabled = (
        bool(raw.enabled)
        if raw is not None and raw.enabled is not None
        else bool(defaults.get("enhanceEnabled"))
    )
    provider = (
        (raw.provider if raw is not None else None)
        or (settings.get("defaults") or {}).get("textProvider")
        or cfg.get("defaultProvider")
        or "ollama"
    )
    if provider not in {"ollama", "comfyui"}:
        errors.append(_issue("unknown_text_provider", f"Unknown enhancement provider `{provider}`.", "enhance.provider"))
        provider = "ollama"

    mode = "off"
    if payload.enhancedPrompt and payload.enhancedPrompt.strip():
        mode = "approved"
    elif enabled:
        mode = "pending"

    requested_model = (raw.model if raw is not None else None) or ""
    model = str(requested_model).strip()
    if provider == "ollama":
        if model.startswith("ollama:"):
            model = model[7:]
        if not model:
            model = str((settings.get("defaults") or {}).get("enhanceModel") or "").strip()
        if model and not _is_ollama_text_model(model):
            if requested_model and mode == "pending":
                errors.append(
                    _issue(
                        "embedding_model",
                        f"`{model}` is an embedding model, not a prompt-generation model.",
                        "enhance.model",
                    )
                )
            # The settings default may be stale (e.g. an embedding model). Let
            # the runtime pick an installed chat model instead of failing.
            model = ""
    else:
        text_model = _find_comfy_text_model(pack, model)
        if text_model is not None:
            model = text_model["id"]
        elif model:
            # A stale model name only matters when enhancement is actually
            # requested; an off/approved request keeps the value for metadata.
            if mode == "pending":
                errors.append(
                    _issue(
                        "unknown_text_model",
                        f"Unknown ComfyUI text model `{model}`. "
                        f"Available: {', '.join(pack.get('comfyTextModels') or {})}.",
                        "enhance.model",
                    )
                )
            model = next((item["id"] for item in (pack.get("comfyTextModels") or {}).values() if item.get("verified")), "")

    if mode == "pending" and provider == "comfyui" and not model:
        errors.append(
            _issue(
                "no_text_model",
                "No ComfyUI text-generation model is configured. Edit text_models.json or choose Ollama.",
                "enhance.model",
            )
        )
    if mode == "pending" and provider == "ollama" and not model:
        warnings.append(
            _issue(
                "no_default_text_model",
                "No default Ollama enhancement model is set; the best installed chat model will be used.",
                "enhance.model",
            )
        )

    system_prompt = (
        raw.systemPrompt
        if raw is not None and raw.systemPrompt is not None
        else (settings.get("prompts") or {}).get(cfg.get("systemPromptKey") or "enhance") or ""
    )
    return {
        "enabled": enabled,
        "mode": mode,
        "provider": provider,
        "model": model,
        "modelExplicit": bool(str(requested_model).strip()),
        "systemPrompt": str(system_prompt or ""),
        "fallbackToOriginal": bool(raw.fallbackToOriginal) if raw is not None else False,
        "unloadAfter": bool(raw.unloadAfter) if raw is not None else True,
    }


async def _unload_ollama_text_model(model: str) -> tuple[bool, str]:
    """Best-effort VRAM handoff: unload only a model that is already resident.

    ``connectors.unload_ollama`` checks ``/api/ps`` first, so this can never
    cause a model load. Failure is non-fatal: the prompt was already enhanced
    and the image job should still run. The caller turns the returned error into
    a job warning.
    """
    if not model:
        return False, "No prompt-enhancement model was reported."
    try:
        result = await connectors.unload_ollama(model)
    except Exception as err:  # noqa: BLE001 - an unload must never fail a job
        return False, _err_text(err)
    ok = bool(result.get("ok"))
    return ok, "" if ok else str(result.get("message") or "Unload failed.")


def _all_triggers(loras: list[dict]) -> list[str]:
    triggers: list[str] = []
    seen: set[str] = set()
    for lora in loras:
        for trigger in lora.get("triggers") or []:
            text = str(trigger).strip()
            key = " ".join(text.casefold().split())
            if text and key not in seen:
                seen.add(key)
                triggers.append(text)
    return triggers


def _inject_triggers(prompt: str, loras: list[dict], auto: bool) -> str:
    if not auto or not prompt:
        return prompt
    prefix: list[str] = []
    haystack = f" {prompt.casefold()} "
    for trigger in _all_triggers(loras):
        key = " ".join(trigger.casefold().split())
        if key and key not in haystack:
            prefix.append(trigger)
            haystack += f" {key} "
    if not prefix:
        return prompt.strip()
    return ", ".join(prefix + [prompt.strip()])


def _normalize_request(payload: T2IJobRequest, pack: dict) -> dict:
    """Validate a request against the tracked pack and return a normalized view."""
    settings, _ = settings_store.load()
    options = pack["options"]
    limits = options["limits"]
    errors: list[dict] = []
    warnings: list[dict] = []

    prompt = (payload.prompt or "").strip()
    negative = (payload.negativePrompt or "").strip()
    if not prompt:
        errors.append(_issue("prompt_required", "A prompt is required.", "prompt"))
    if len(prompt) > limits["promptMaxChars"]:
        errors.append(
            _issue(
                "prompt_too_long",
                f"Prompt is {len(prompt)} characters; the limit is {limits['promptMaxChars']}.",
                "prompt",
            )
        )
    if len(negative) > limits["negativePromptMaxChars"]:
        errors.append(
            _issue(
                "negative_prompt_too_long",
                f"Negative prompt is {len(negative)} characters; the limit is {limits['negativePromptMaxChars']}.",
                "negativePrompt",
            )
        )

    model = _resolve_model(pack, payload.modelId)
    user = catalog.load_user_catalog()
    try:
        snapshot = catalog.build_snapshot(pack, user, model_id=model["id"])
    except KeyError as exc:
        raise ValidationError([_issue("unknown_model", str(exc), "modelId")]) from exc
    model_view = next((item for item in snapshot["models"] if item["id"] == model["id"]), None)
    if model_view is None:
        raise ValidationError([_issue("unknown_model", f"Model `{model['id']}` disappeared from the pack.", "modelId")])
    if model_view.get("missing"):
        errors.append(
            _issue(
                "model_missing",
                f"{model_view['label']} is missing required files: {', '.join(model_view['missing'])}.",
                "modelId",
            )
        )
    elif model_view.get("present") is None:
        warnings.append(
            _issue(
                "model_presence_unknown",
                f"{model_view['label']}: file presence is unknown until the model catalog is built.",
                "modelId",
            )
        )

    width, height, ratio_id, size = _resolve_size(payload, model_view, pack, errors, warnings)
    loras = _resolve_loras(payload, snapshot, model_view, pack, errors, warnings)
    upscaler = _resolve_upscaler(payload, model_view, snapshot, pack, errors, warnings)

    adv = payload.advanced
    steps_raw = adv.steps if adv else None
    cfg_raw = adv.cfg if adv else None
    denoise_raw = adv.denoise if adv else None
    sampler_raw = adv.sampler if adv else None
    scheduler_raw = adv.scheduler if adv else None
    refine_raw = adv.refine if adv else None

    steps = _range_value(model_view["ranges"]["steps"], steps_raw, "advanced.steps", errors, warnings, integer=True)
    cfg = _range_value(model_view["ranges"]["cfg"], cfg_raw, "advanced.cfg", errors, warnings)
    denoise = _range_value(model_view["ranges"]["denoise"], denoise_raw, "advanced.denoise", errors, warnings)
    batch = _range_value(model_view["ranges"]["batch"], payload.batch, "batch", errors, warnings, integer=True)

    sampler_ids = {item["id"] for item in options["samplers"]}
    scheduler_ids = {item["id"] for item in options["schedulers"]}
    sampler = str(sampler_raw or model_view["defaults"]["sampler"]).strip()
    scheduler = str(scheduler_raw or model_view["defaults"]["scheduler"]).strip()
    if sampler not in sampler_ids:
        errors.append(
            _issue(
                "unknown_sampler",
                f"Unknown sampler `{sampler}`. Available: {', '.join(sorted(sampler_ids))}.",
                "advanced.sampler",
            )
        )
        sampler = model_view["defaults"]["sampler"]
    if scheduler not in scheduler_ids:
        errors.append(
            _issue(
                "unknown_scheduler",
                f"Unknown scheduler `{scheduler}`. Available: {', '.join(sorted(scheduler_ids))}.",
                "advanced.scheduler",
            )
        )
        scheduler = model_view["defaults"]["scheduler"]

    seed_range = model_view["ranges"]["seed"]
    if payload.lockSeed:
        seed = _range_value(
            seed_range,
            payload.seed if payload.seed is not None else 0,
            "seed",
            errors,
            warnings,
            integer=True,
        )
        seed_randomized = False
    else:
        seed = secrets.randbelow(2**32)
        seed_randomized = True

    refine_enabled = upscaler["kind"] == "latent" and bool(upscaler["enabled"])
    refine_steps = model_view["ranges"]["refine"]["steps"]["default"]
    refine_cfg = model_view["ranges"]["refine"]["cfg"]["default"]
    refine_denoise = model_view["ranges"]["refine"]["denoise"]["default"]
    if refine_enabled:
        refine_steps = _range_value(
            model_view["ranges"]["refine"]["steps"],
            refine_raw.steps if refine_raw else None,
            "advanced.refine.steps",
            errors,
            warnings,
            integer=True,
        )
        refine_cfg = _range_value(
            model_view["ranges"]["refine"]["cfg"],
            refine_raw.cfg if refine_raw else None,
            "advanced.refine.cfg",
            errors,
            warnings,
        )
        refine_denoise = _range_value(
            model_view["ranges"]["refine"]["denoise"],
            refine_raw.denoise if refine_raw else None,
            "advanced.refine.denoise",
            errors,
            warnings,
        )

    base_prompt = (payload.enhancedPrompt or "").strip() or prompt
    if len(base_prompt) > limits["promptMaxChars"]:
        errors.append(
            _issue(
                "prompt_too_long",
                f"The prompt (including the approved enhancement) is {len(base_prompt)} characters; "
                f"the limit is {limits['promptMaxChars']}.",
                "enhancedPrompt",
            )
        )
    prompt_used = _inject_triggers(base_prompt, loras, bool(payload.autoTriggers))
    if len(prompt_used) > limits["promptMaxChars"]:
        errors.append(
            _issue(
                "prompt_too_long",
                f"Prompt plus LoRA trigger words is {len(prompt_used)} characters; the limit is "
                f"{limits['promptMaxChars']}. Shorten the prompt or disable autoTriggers.",
                "prompt",
            )
        )

    enhance = _resolve_enhance(payload, pack, settings, errors, warnings)

    recipe_id = (payload.recipeId or "").strip() or pack["recipe"]["id"]
    if recipe_id != pack["recipe"]["id"]:
        errors.append(
            _issue(
                "unknown_recipe",
                f"Unknown recipe `{recipe_id}`. This module serves `{pack['recipe']['id']}`.",
                "recipeId",
            )
        )
        recipe_id = pack["recipe"]["id"]

    normalized = {
        "prompt": prompt,
        "basePrompt": base_prompt,
        "promptUsed": prompt_used,
        "negativePrompt": negative,
        "autoTriggers": bool(payload.autoTriggers),
        "triggers": _all_triggers(loras),
        "model": model_view,
        "width": int(width),
        "height": int(height),
        "ratioId": ratio_id,
        "size": int(size),
        "batch": int(batch),
        "seed": int(seed),
        "lockSeed": bool(payload.lockSeed),
        "seedRandomized": seed_randomized,
        "steps": int(steps),
        "cfg": float(cfg),
        "denoise": float(denoise),
        "sampler": sampler,
        "scheduler": scheduler,
        "refineEnabled": refine_enabled,
        "refineSteps": int(refine_steps),
        "refineCfg": float(refine_cfg),
        "refineDenoise": float(refine_denoise),
        "upscaler": upscaler,
        "loras": loras,
        "enhance": enhance,
        "recipeId": recipe_id,
        "tab": (payload.tab or TAB_ID).strip() or TAB_ID,
        "warnings": warnings,
    }
    if errors:
        raise ValidationError(errors, warnings)
    return normalized


def _public_normalized(normalized: dict) -> dict:
    upscaler = normalized["upscaler"]
    return {
        "modelId": normalized["model"]["id"],
        "modelName": normalized["model"]["label"],
        "width": normalized["width"],
        "height": normalized["height"],
        "ratio": normalized["ratioId"],
        "size": normalized["size"],
        "batch": normalized["batch"],
        "seed": normalized["seed"],
        "lockSeed": normalized["lockSeed"],
        "seedRandomized": normalized["seedRandomized"],
        "steps": normalized["steps"],
        "cfg": normalized["cfg"],
        "sampler": normalized["sampler"],
        "scheduler": normalized["scheduler"],
        "denoise": normalized["denoise"],
        "refine": {
            "on": normalized["refineEnabled"],
            "steps": normalized["refineSteps"],
            "cfg": normalized["refineCfg"],
            "denoise": normalized["refineDenoise"],
            "scale": upscaler.get("value") if upscaler["kind"] == "latent" else None,
        },
        "upscaler": {
            "id": upscaler["id"],
            "label": upscaler["label"],
            "kind": upscaler["kind"],
            "enabled": upscaler["enabled"],
            "value": upscaler["value"],
        },
        "loras": [
            {
                "id": item["id"],
                "label": item["label"],
                "strength": item["strength"],
                "triggers": item["triggers"],
            }
            for item in normalized["loras"]
        ],
        "prompt": normalized["prompt"],
        "basePrompt": normalized["basePrompt"],
        "promptUsed": normalized["promptUsed"],
        "negativePrompt": normalized["negativePrompt"],
        "triggers": normalized["triggers"],
        "autoTriggers": normalized["autoTriggers"],
        "enhance": normalized["enhance"],
        "recipeId": normalized["recipeId"],
        "tab": normalized["tab"],
    }


def _job_params(
    normalized: dict,
    meta: dict | None,
    *,
    engine_prompt_id: str | None = None,
    warnings: list[dict] | None = None,
) -> dict:
    upscaler = normalized["upscaler"]
    refine_on = bool(normalized["refineEnabled"])
    final_width = None
    final_height = None
    refine_seed = (int(normalized["seed"]) + 1) & 0xFFFFFFFF if refine_on else None
    refine_width = None
    refine_height = None
    if meta:
        final_width = meta["upscaler"]["outputWidth"]
        final_height = meta["upscaler"]["outputHeight"]
        refine_seed = meta["refine"]["seed"]
        refine_width = meta["refine"]["width"]
        refine_height = meta["refine"]["height"]
    return {
        # AdvancedParams-compatible fields (the generic job UI reads these).
        "recipe": normalized["recipeId"],
        "seed": normalized["seed"],
        "lockSeed": normalized["lockSeed"],
        "steps": normalized["steps"],
        "cfg": normalized["cfg"],
        "sampler": normalized["sampler"],
        "scheduler": normalized["scheduler"],
        "denoise": normalized["denoise"],
        "refine": {
            "on": refine_on,
            "steps": normalized["refineSteps"],
            "cfg": normalized["refineCfg"],
            "denoise": normalized["refineDenoise"],
            "scale": upscaler.get("value") if upscaler["kind"] == "latent" else None,
            "seed": refine_seed,
            "width": refine_width,
            "height": refine_height,
        },
        # Module-specific metadata.
        "recipeId": normalized["recipeId"],
        "packId": normalized["model"].get("packId"),
        "composer": normalized["model"].get("composer"),
        "workflow": normalized["model"].get("workflow"),
        "modelId": normalized["model"]["id"],
        "modelName": normalized["model"]["label"],
        "modelShortLabel": normalized["model"].get("shortLabel") or normalized["model"]["label"],
        "modelBase": normalized["model"]["base"],
        "width": normalized["width"],
        "height": normalized["height"],
        "ratio": normalized["ratioId"],
        "size": normalized["size"],
        "batch": normalized["batch"],
        "seedRandomized": normalized["seedRandomized"],
        "loras": [
            {
                "id": item["id"],
                "label": item["label"],
                "file": item["file"],
                "strength": item["strength"],
                "triggers": item["triggers"],
            }
            for item in normalized["loras"]
        ],
        "triggers": normalized["triggers"],
        "autoTriggers": normalized["autoTriggers"],
        "basePrompt": normalized["basePrompt"],
        "promptUsed": normalized["promptUsed"],
        "negativePrompt": normalized["negativePrompt"],
        "enhance": normalized["enhance"],
        "upscaler": {
            "id": upscaler["id"],
            "label": upscaler["label"],
            "kind": upscaler["kind"],
            "enabled": upscaler["enabled"],
            "value": upscaler["value"],
            "outputWidth": final_width,
            "outputHeight": final_height,
        },
        "upscalerId": upscaler["id"],
        "finalWidth": final_width,
        "finalHeight": final_height,
        "engine": "comfyui",
        "enginePromptId": engine_prompt_id,
        "workflowNodeCount": meta["nodeCount"] if meta else None,
        "warnings": warnings or [],
    }


def _initial_stages() -> list[dict]:
    return [
        {"id": stage_id, "label": label, "status": "pending", "detail": ""}
        for stage_id, label in STAGE_DEFS
    ]


class _StageTracker:
    def __init__(self, job_id: str, stages: list[dict] | None = None):
        self.job_id = job_id
        self.stages = [dict(item) for item in (stages or _initial_stages())]
        self.active: str | None = None
        self.progress_value = 0

    def _find(self, stage_id: str) -> dict:
        for stage in self.stages:
            if stage.get("id") == stage_id:
                return stage
        stage = {"id": stage_id, "label": stage_id, "status": "pending", "detail": ""}
        self.stages.append(stage)
        return stage

    def _save(self) -> None:
        jobs.update_job(self.job_id, {"stages": self.stages, "progress": self.progress_value})

    def start(self, stage_id: str, detail: str = "") -> None:
        stage = self._find(stage_id)
        stage["status"] = "running"
        stage["startedAt"] = jobs.now_ms()
        stage.pop("finishedAt", None)
        stage.pop("durationMs", None)
        if detail:
            stage["detail"] = detail
        self.active = stage_id
        self._save()

    def done(self, stage_id: str, detail: str = "") -> None:
        stage = self._find(stage_id)
        finished = jobs.now_ms()
        stage["status"] = "done"
        stage["finishedAt"] = finished
        stage["durationMs"] = max(0, finished - int(stage.get("startedAt") or finished))
        if detail:
            stage["detail"] = detail
        if self.active == stage_id:
            self.active = None
        self._save()

    def skip(self, stage_id: str, detail: str = "") -> None:
        stage = self._find(stage_id)
        stage["status"] = "skipped"
        stage["finishedAt"] = jobs.now_ms()
        stage["durationMs"] = 0
        if detail:
            stage["detail"] = detail
        if self.active == stage_id:
            self.active = None
        self._save()

    def fail(self, stage_id: str, detail: str) -> None:
        stage = self._find(stage_id)
        finished = jobs.now_ms()
        stage["status"] = "error"
        stage["finishedAt"] = finished
        stage["durationMs"] = max(0, finished - int(stage.get("startedAt") or finished))
        stage["detail"] = detail[:1000]
        if self.active == stage_id:
            self.active = None
        self._save()

    def progress(self, value: int) -> None:
        self.progress_value = max(0, min(100, int(value)))
        self._save()


def _check_cancel(event: asyncio.Event) -> None:
    if event.is_set():
        raise JobCancelled()


def _queue_prompt_ids(queue: dict, key: str) -> set[str]:
    ids: set[str] = set()
    for item in (queue or {}).get(key) or []:
        if isinstance(item, (list, tuple)) and len(item) > 1:
            ids.add(str(item[1]))
    return ids


async def _cancel_engine(client, prompt_id: str | None) -> None:
    """Best-effort cancel. `interrupt` is global, so only call it when our prompt is running."""
    if not prompt_id:
        return
    running: set[str] = set()
    pending: set[str] = set()
    try:
        queue = await client.queue()
        running = _queue_prompt_ids(queue, "queue_running")
        pending = _queue_prompt_ids(queue, "queue_pending")
    except Exception:  # noqa: BLE001 - if the queue is unreadable, be conservative
        pass
    if prompt_id in running:
        try:
            await client.interrupt()
        except Exception:  # noqa: BLE001
            pass
        return
    if prompt_id in pending or not running and not pending:
        # Pending prompts can be removed without touching the running job.
        try:
            await client.queue_delete(prompt_id)
        except Exception:  # noqa: BLE001
            pass


async def _wait_for_history(
    client,
    prompt_id: str,
    job_id: str,
    cancel_event: asyncio.Event,
    tracker: _StageTracker,
    limits: dict,
    *,
    timeout_seconds: float | None = None,
    max_connection_failures: int = 6,
) -> dict:
    interval = max(0.25, float(limits.get("pollIntervalSeconds") or 1.0))
    timeout = float(timeout_seconds if timeout_seconds is not None else limits.get("jobTimeoutSeconds") or 1800)
    deadline = time.monotonic() + timeout
    started = time.monotonic()
    failures = 0
    last_error = ""
    while True:
        _check_cancel(cancel_event)
        try:
            history = await client.history(prompt_id)
            failures = 0
        except Exception as err:  # noqa: BLE001 - transient engine hiccups are retried
            failures += 1
            last_error = _err_text(err)[:240]
            if failures >= max_connection_failures:
                raise EngineError(
                    f"Lost connection to ComfyUI while waiting for {prompt_id}: {last_error}"
                ) from err
            await asyncio.sleep(min(5.0, interval * 2))
            continue

        done, status = workflows.history_completed(history, prompt_id)
        if done:
            if status == "error":
                raise EngineError(workflows.history_error(history, prompt_id))
            return history

        if time.monotonic() >= deadline:
            raise EngineError(
                f"Timed out after {int(timeout)}s waiting for ComfyUI prompt {prompt_id}. "
                "The job may still be running in ComfyUI."
            )
        elapsed = time.monotonic() - started
        tracker.progress(min(90, 35 + int(elapsed / 2)))
        await asyncio.sleep(interval)


async def _download_image(client, image: dict, limits: dict) -> bytes:
    retries = max(0, int(limits.get("downloadRetries") or 3))
    timeout = float(limits.get("downloadTimeoutSeconds") or 120)
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return await client.view(
                image["filename"],
                image.get("subfolder", ""),
                image.get("type", "output"),
                timeout=timeout,
            )
        except Exception as err:  # noqa: BLE001 - the output file can appear a moment late
            last_error = err
            if attempt < retries:
                await asyncio.sleep(1.0)
    raise EngineError(
        f"Could not download `{image['filename']}` from ComfyUI: "
        f"{_err_text(last_error) if last_error else 'unknown error'}"
    )


def _asset_tags(job_params: dict) -> list[str]:
    tags = ["text-to-image", MODULE_ID]
    recipe = str(job_params.get("recipeId") or "").strip()
    if recipe:
        tags.append(recipe)
    upscaler = job_params.get("upscaler") or {}
    if isinstance(upscaler, dict):
        if upscaler.get("enabled") and upscaler.get("id") not in {None, "", "none"}:
            tags.append(str(upscaler["id"]))
        if upscaler.get("kind") == "latent" and upscaler.get("enabled"):
            tags.append("refined")
        if upscaler.get("kind") == "esrgan" and upscaler.get("enabled"):
            tags.append("upscaled")
    return tags


async def _collect_assets(
    client,
    job: dict,
    job_params: dict,
    images: list[dict],
    limits: dict,
    *,
    cancel_event: asyncio.Event | None = None,
) -> list[dict]:
    model_name = str(job_params.get("modelName") or job.get("modelName") or "")
    prompt = str(job_params.get("promptUsed") or job.get("prompt") or "")
    seed = int(job_params.get("seed") or job.get("seed") or 0)
    label = (prompt.split(",")[0] or "image").strip()[:60]
    tags = _asset_tags(job_params)
    assets: list[dict] = []
    for index, image in enumerate(images):
        if cancel_event is not None and cancel_event.is_set():
            raise JobCancelled()
        data = await _download_image(client, image, limits)
        try:
            asset = await asyncio.to_thread(
                library.add_bytes,
                data,
                image["filename"],
                label=label,
                prompt=prompt,
                model=model_name,
                seed=(seed + index) & 0xFFFFFFFF,
                tags=tags,
                origin_job=job["id"],
            )
        except Exception as err:  # noqa: BLE001 - file/DB problem is a job failure
            raise EngineError(f"Could not add `{image['filename']}` to the library: {err}") from err
        assets.append(asset)
    return assets


async def _run_job(
    job_id: str,
    pack: dict,
    normalized: dict,
    cancel_event: asyncio.Event,
) -> None:
    tracker = _StageTracker(job_id, _initial_stages())
    tracker.progress(2)
    client = None
    prompt_id: str | None = None
    completed = False
    try:
        enhance = normalized["enhance"]
        if enhance.get("mode") == "pending":
            tracker.start("enhance", "Calling the enhancement provider...")
            tracker.progress(5)
            try:
                result = await enhance_prompt(
                    T2IEnhanceRequest(
                        prompt=normalized["prompt"],
                        provider=enhance.get("provider"),
                        # A settings-derived default may be stale; only pass the
                        # model when the caller explicitly chose it.
                        model=(enhance.get("model") or None) if enhance.get("modelExplicit") else None,
                        systemPrompt=enhance.get("systemPrompt") or None,
                        unloadAfter=bool(enhance.get("unloadAfter", True)),
                    )
                )
                warnings = normalized["warnings"]
                enhanced = {
                    **enhance,
                    "mode": "applied",
                    "provider": result["provider"],
                    "model": result["model"],
                }
                if result.get("unloadError"):
                    enhanced["unloadError"] = result["unloadError"]
                    warnings = warnings + [
                        _issue(
                            "enhance_unload_failed",
                            "Prompt enhancement succeeded, but the enhancement model could not be "
                            "unloaded; ComfyUI may have less VRAM available. "
                            f"{result['unloadError']}",
                            "enhance.unloadAfter",
                        )
                    ]
                normalized = {
                    **normalized,
                    "basePrompt": result["prompt"],
                    "promptUsed": _inject_triggers(result["prompt"], normalized["loras"], normalized["autoTriggers"]),
                    "enhance": enhanced,
                    "warnings": warnings,
                }
                jobs.update_job(
                    job_id,
                    {
                        "enhancedPrompt": result["prompt"],
                        "params": _job_params(normalized, None, warnings=warnings),
                    },
                )
                detail = f"{result['provider']} / {result['model']} in {result['durationMs']} ms"
                if result.get("unloaded"):
                    detail += " · text model unloaded"
                elif result.get("unloadError"):
                    detail += " · unload failed"
                tracker.done("enhance", detail)
            except Exception as err:  # noqa: BLE001 - fallback is an explicit user choice
                if enhance.get("fallbackToOriginal"):
                    normalized = {
                        **normalized,
                        "basePrompt": normalized["prompt"],
                        "promptUsed": _inject_triggers(
                            normalized["prompt"], normalized["loras"], normalized["autoTriggers"]
                        ),
                        "enhance": {**enhance, "mode": "fallback", "error": _err_text(err)[:500]},
                        "warnings": normalized["warnings"]
                        + [
                            _issue(
                                "enhance_failed",
                                f"Prompt enhancement failed; using the original prompt. {_err_text(err)}",
                            )
                        ],
                    }
                    jobs.update_job(
                        job_id,
                        {"params": _job_params(normalized, None, warnings=normalized["warnings"])},
                    )
                    tracker.done("enhance", f"Enhancement failed; using original prompt. {_err_text(err)[:300]}")
                else:
                    raise
        elif enhance.get("mode") == "approved":
            tracker.skip("enhance", "Using approved enhanced prompt")
        else:
            tracker.skip("enhance", "Prompt enhancement off")

        tracker.start("compose", "Building the ComfyUI API graph...")
        _check_cancel(cancel_event)

        # Enhancement is free text; re-check the same limit the request used so
        # a verbose model cannot bypass the prompt guard after validation.
        prompt_limit = int(pack["options"]["limits"]["promptMaxChars"])
        if len(normalized["promptUsed"]) > prompt_limit:
            raise EngineError(
                f"Enhanced prompt plus LoRA triggers is {len(normalized['promptUsed'])} characters; "
                f"the limit is {prompt_limit}. Shorten the prompt or disable autoTriggers."
            )

        graph, meta = workflows.compose_t2i(pack, normalized["model"], normalized, job_id=job_id)
        jobs.update_job(job_id, {"params": _job_params(normalized, meta, warnings=normalized["warnings"])})
        tracker.done("compose", f"{meta['nodeCount']} nodes")
        tracker.progress(20)

        tracker.start("submit", "Submitting to ComfyUI...")
        _check_cancel(cancel_event)
        client = connectors.comfy_client()
        try:
            submitted = await client.submit_prompt(graph, client_id=f"{MODULE_ID}:{job_id}")
        except Exception as err:  # noqa: BLE001 - turn transport errors into readable job errors
            raise EngineError(_engine_error("ComfyUI", client.base_url, err)) from err
        prompt_id = str(submitted.get("prompt_id") or "")
        if not prompt_id:
            raise EngineError("ComfyUI accepted the request but returned no prompt_id.")
        jobs.update_job(
            job_id,
            {"params": _job_params(normalized, meta, engine_prompt_id=prompt_id, warnings=normalized["warnings"])},
        )
        tracker.done("submit", f"prompt {prompt_id}")
        tracker.progress(30)

        tracker.start("generate", "Waiting for ComfyUI history...")
        history = await _wait_for_history(
            client, prompt_id, job_id, cancel_event, tracker, pack["options"]["limits"]
        )
        completed = True
        tracker.done("generate", "ComfyUI finished")
        tracker.progress(94)

        tracker.start("collect", "Downloading outputs into the library...")
        images = workflows.find_output_images(history, prompt_id)
        if not images:
            raise EngineError("ComfyUI finished without output images.")
        job = jobs.get_job(job_id)
        if job is None:
            raise EngineError("The job record disappeared before its outputs could be collected.")
        params = job.get("params") or {}
        assets = await _collect_assets(
            client,
            job,
            params,
            images,
            pack["options"]["limits"],
            cancel_event=cancel_event,
        )
        tracker.done("collect", f"{len(assets)} image(s)")
        jobs.update_job(
            job_id,
            {
                "status": "done",
                "progress": 100,
                "resultIds": [asset["id"] for asset in assets],
            },
        )
        logger.info("[t2i] job %s done: %s image(s)", job_id, len(assets))
    except JobCancelled:
        tracker.fail(tracker.active or "generate", "Cancelled by user")
        jobs.update_job(job_id, {"status": "error", "error": "Cancelled by user"})
        if not completed:
            await _cancel_engine(client, prompt_id)
        logger.info("[t2i] job %s cancelled", job_id)
    except Exception as err:  # noqa: BLE001 - every failure must land on the job record
        if isinstance(err, (EngineError, ValidationError)):
            logger.warning("[t2i] job %s stopped: %s", job_id, err)
        else:
            logger.exception("[t2i] job %s failed", job_id)
        message = _err_text(err)[:1200] or "T2I job failed."
        tracker.fail(tracker.active or "generate", message)
        jobs.update_job(job_id, {"status": "error", "error": message})
        if not completed:
            await _cancel_engine(client, prompt_id)
    finally:
        _TASKS.pop(job_id, None)
        _CANCEL.pop(job_id, None)


def _resume_stages(job: dict) -> list[dict]:
    stages = _initial_stages()
    by_id = {item["id"]: item for item in stages}
    enhance_mode = str((job.get("params") or {}).get("enhance", {}).get("mode") or "")
    by_id["enhance"]["status"] = "done" if enhance_mode in {"applied", "approved"} else "skipped"
    by_id["enhance"]["detail"] = "Resumed from persisted job metadata."
    by_id["compose"]["status"] = "done"
    by_id["submit"]["status"] = "done"
    by_id["generate"]["status"] = "running"
    by_id["generate"]["detail"] = "Reattached after backend restart."
    return stages


async def _resume_job(job: dict, prompt_id: str, cancel_event: asyncio.Event, limits: dict) -> None:
    job_id = job["id"]
    tracker = _StageTracker(job_id, _resume_stages(job))
    tracker.progress(max(35, int(job.get("progress") or 0)))
    client = None
    completed = False
    try:
        client = connectors.comfy_client()
        history = await _wait_for_history(
            client,
            prompt_id,
            job_id,
            cancel_event,
            tracker,
            limits,
            timeout_seconds=min(600.0, float(limits.get("jobTimeoutSeconds") or 1800)),
            max_connection_failures=30,
        )
        completed = True
        tracker.done("generate", "ComfyUI finished")
        tracker.progress(94)
        tracker.start("collect", "Downloading outputs into the library...")
        images = workflows.find_output_images(history, prompt_id)
        if not images:
            raise EngineError("ComfyUI finished without output images.")
        refreshed = jobs.get_job(job_id) or job
        params = refreshed.get("params") or job.get("params") or {}
        assets = await _collect_assets(
            client,
            refreshed,
            params,
            images,
            limits,
            cancel_event=cancel_event,
        )
        tracker.done("collect", f"{len(assets)} image(s)")
        jobs.update_job(
            job_id,
            {
                "status": "done",
                "progress": 100,
                "resultIds": [asset["id"] for asset in assets],
            },
        )
        logger.info("[t2i] resumed job %s done: %s image(s)", job_id, len(assets))
    except JobCancelled:
        tracker.fail(tracker.active or "generate", "Cancelled by user")
        jobs.update_job(job_id, {"status": "error", "error": "Cancelled by user"})
        if not completed:
            await _cancel_engine(client, prompt_id)
    except Exception as err:  # noqa: BLE001
        if isinstance(err, EngineError):
            logger.warning("[t2i] resumed job %s engine error: %s", job_id, err)
        else:
            logger.exception("[t2i] resumed job %s failed", job_id)
        message = _err_text(err)[:1200] or "T2I resume failed."
        tracker.fail(tracker.active or "generate", message)
        jobs.update_job(job_id, {"status": "error", "error": message})
        if not completed:
            await _cancel_engine(client, prompt_id)
    finally:
        _TASKS.pop(job_id, None)
        _CANCEL.pop(job_id, None)


# -- public service API ---------------------------------------------------------


def _pack_for_request(model_id: str | None) -> dict:
    """Resolve the pack that owns the selected model; fall back to the default."""
    if model_id:
        pack = catalog.pack_for_model(model_id)
        if pack is not None:
            return pack
    return catalog.load_pack()


async def catalog_snapshot(model_id: str | None = None) -> dict:
    pack = _pack_for_request(model_id)
    user = catalog.load_user_catalog()
    if model_id and model_id not in pack["models"]:
        raise ValidationError(
            [_issue("unknown_model", f"Unknown T2I model `{model_id}`.", "modelId")]
        )
    probes = await asyncio.gather(
        connectors.comfy_status(),
        connectors.ollama_status(),
        return_exceptions=True,
    )
    comfy = probes[0] if isinstance(probes[0], dict) else {
        "connected": False,
        "detail": str(probes[0])[:240],
        "installed": [],
    }
    ollama = probes[1] if isinstance(probes[1], dict) else {
        "connected": False,
        "detail": str(probes[1])[:240],
        "installed": [],
    }
    engine = {
        "comfyui": comfy,
        "ollama": ollama,
        "ready": bool(comfy.get("connected")),
    }
    try:
        snapshot = catalog.build_snapshot(
            pack,
            user,
            model_id=model_id,
            engine=engine,
        )
    except KeyError as exc:
        raise ValidationError([_issue("unknown_model", str(exc), "modelId")]) from exc

    settings, _ = settings_store.load()
    text_models = list(snapshot.get("textModels") or [])
    ollama_sizes = {
        str(item.get("name")): float(item.get("sizeGb") or 0.0)
        for item in (ollama.get("installed") or [])
        if item.get("name")
    }
    ollama_models = [
        {
            "id": f"ollama:{name}",
            "label": name,
            "provider": "ollama",
            "model": name,
            "present": True,
            "verified": True,
            "tested": True,
            "sizeGb": ollama_sizes.get(name, 0.0),
            "preferred": name in (pack.get("ollamaText", {}).get("preferred") or []),
            "notes": "Installed Ollama chat model. Unloads independently from ComfyUI.",
        }
        for name in _ollama_text_names(ollama.get("installed") or [])
    ]
    text_models.extend(ollama_models)
    snapshot["textModels"] = text_models

    default_enhance = _default_enhance(pack, settings, comfy, ollama, text_models)
    snapshot["defaults"]["enhance"] = default_enhance

    warnings = list(snapshot.get("warnings") or [])
    if not comfy.get("connected"):
        warnings.append(
            _issue(
                "comfyui_offline",
                "ComfyUI is offline. Generation is unavailable until it is running.",
            )
        )
    if not ollama.get("connected"):
        warnings.append(
            _issue(
                "ollama_offline",
                "Ollama is offline. Prompt enhancement via Ollama is unavailable.",
            )
        )
    elif not ollama_models and default_enhance.get("provider") == "ollama":
        warnings.append(
            _issue(
                "no_ollama_models",
                "No Ollama chat/text models are installed (embedding-only models are ignored). "
                "Install one or choose a ComfyUI text model.",
            )
        )
    if default_enhance.get("provider") == "comfyui" and not default_enhance.get("model"):
        warnings.append(
            _issue(
                "no_comfy_text_model",
                "No ComfyUI text-generation model is available for enhancement.",
            )
        )
    snapshot["warnings"] = warnings
    return snapshot


def _default_enhance(pack: dict, settings: dict, comfy: dict, ollama: dict, text_models: list[dict]) -> dict:
    cfg = pack["options"]["enhance"]
    defaults = settings.get("defaults") or {}
    provider = str(defaults.get("textProvider") or cfg.get("defaultProvider") or "ollama")
    if provider not in {"ollama", "comfyui"}:
        provider = "ollama"
    model = ""
    if provider == "ollama":
        installed = [str(item.get("name")) for item in (ollama.get("installed") or []) if item.get("name")]
        model = _pick_ollama_model(settings, pack, installed)
    else:
        comfy_models = [
            item
            for item in text_models
            if item.get("provider") == "comfyui" and item.get("verified") and item.get("present") is not False
        ]
        model = str(comfy_models[0]["id"]) if comfy_models else ""
    return {
        "enabled": bool(pack["options"]["defaults"].get("enhanceEnabled")),
        "provider": provider,
        "model": model,
        "systemPrompt": str((settings.get("prompts") or {}).get(cfg.get("systemPromptKey") or "enhance") or ""),
        "fallbackToOriginal": False,
    }


def pack_info() -> dict:
    pack = catalog.load_pack()
    return {
        "ok": True,
        "version": pack["version"],
        "pack": {"id": pack["id"], "label": pack["label"]},
        "recipe": pack["recipe"],
        "models": [
            {
                "id": item["id"],
                "label": item["label"],
                "base": item["base"],
                "packId": item["packId"],
                "composer": item["composer"],
                "workflow": item["workflow"],
                "loader": item["loader"],
                "verified": item["verified"],
                "tested": item["tested"],
            }
            for item in pack["models"].values()
        ],
        "loras": [
            {
                "id": item["id"],
                "label": item["label"],
                "t2i": item["t2i"],
                "base": item["base"],
                "excludeReason": item["excludeReason"],
            }
            for item in pack["loras"].values()
        ],
        "upscalers": [
            {"id": item["id"], "label": item["label"], "kind": item["kind"]}
            for item in pack["upscalers"].values()
        ],
        "textModels": [
            {"id": item["id"], "label": item["label"], "provider": "comfyui"}
            for item in pack["comfyTextModels"].values()
        ],
        "workflow": {
            "path": pack["recipe"]["workflow"],
            "nodeCount": len(pack["workflow"]),
            "format": "comfyui-api",
        },
    }


def setup_info() -> dict:
    """Standardized first-open setup payload for the shared requirements modal.

    It reports missing required files and source links only. There is no
    download, install, move or delete action here or in the frontend.
    """
    try:
        manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {}
    pack_meta = [
        {
            "id": pack["id"],
            "label": pack["label"],
            "description": pack.get("description") or "",
            "nsfw": bool(pack.get("nsfw")),
            "order": int(pack.get("order") or 0),
        }
        for pack in catalog.load_packs().values()
    ]
    return module_setup.build_setup_payload(
        requirements=module_setup.load_requirements(REQUIREMENTS_FILE),
        packs=pack_meta,
        catalog=catalog.load_user_catalog(),
        module_id=MODULE_ID,
        module_label=str(manifest.get("name") or MODULE_ID),
        module_description=str(manifest.get("description") or ""),
        module_nsfw=any(pack["nsfw"] for pack in pack_meta),
    )


def validate_payload(payload: T2IJobRequest) -> dict:
    pack = _pack_for_request(payload.modelId)
    normalized = _normalize_request(payload, pack)
    graph, meta = workflows.compose_t2i(pack, normalized["model"], normalized, job_id="preview")
    return {
        "valid": True,
        "normalized": _public_normalized(normalized),
        "warnings": normalized["warnings"],
        "graph": {
            "recipeId": meta["recipeId"],
            "nodeCount": meta["nodeCount"],
            "width": meta["width"],
            "height": meta["height"],
            "finalWidth": meta["upscaler"]["outputWidth"],
            "finalHeight": meta["upscaler"]["outputHeight"],
            "refine": meta["refine"],
            "upscaler": meta["upscaler"],
            "loras": meta["loras"],
        },
    }


async def enhance_prompt(payload: T2IEnhanceRequest) -> dict:
    prompt = (payload.prompt or "").strip()
    if not prompt:
        raise ValidationError([_issue("prompt_required", "A prompt is required.", "prompt")])
    pack = catalog.load_pack()
    limits = pack["options"]["limits"]
    if len(prompt) > limits["promptMaxChars"]:
        raise ValidationError(
            [
                _issue(
                    "prompt_too_long",
                    f"Prompt is {len(prompt)} characters; the limit is {limits['promptMaxChars']}.",
                    "prompt",
                )
            ]
        )
    settings, _ = settings_store.load()
    cfg = pack["options"]["enhance"]
    provider = payload.provider or (settings.get("defaults") or {}).get("textProvider") or cfg.get("defaultProvider") or "ollama"
    if provider not in {"ollama", "comfyui"}:
        raise ValidationError([_issue("unknown_text_provider", f"Unknown provider `{provider}`.", "provider")])
    if payload.temperature is not None and not 0.0 <= float(payload.temperature) <= 2.0:
        raise ValidationError(
            [
                _issue(
                    "temperature_out_of_range",
                    "Enhancement temperature must be between 0.0 and 2.0.",
                    "temperature",
                    min=0.0,
                    max=2.0,
                )
            ]
        )
    system_prompt = (
        payload.systemPrompt
        if payload.systemPrompt is not None
        else (settings.get("prompts") or {}).get(cfg.get("systemPromptKey") or "enhance") or ""
    )
    started = time.monotonic()

    if provider == "ollama":
        status = await connectors.ollama_status()
        if not status.get("connected"):
            raise EngineError(
                f"Ollama is not reachable at {status.get('url') or 'the configured URL'}: "
                f"{status.get('detail') or 'connection failed'}"
            )
        requested = (payload.model or "").strip()
        if requested.startswith("ollama:"):
            requested = requested[7:]
        if requested and not _is_ollama_text_model(requested):
            raise ValidationError(
                [
                    _issue(
                        "embedding_model",
                        f"`{requested}` is an embedding model, not a prompt-generation model.",
                        "model",
                    )
                ]
            )
        installed = _ollama_text_names(status.get("installed") or [])
        model = _match_installed(requested, installed)
        if requested and not model:
            raise ValidationError(
                [
                    _issue(
                        "text_model_not_installed",
                        f"Ollama model `{requested}` is not installed. "
                        f"Installed chat models: {', '.join(installed) or 'none'}.",
                        "model",
                    )
                ]
            )
        if not model:
            model = _pick_ollama_model(settings, pack, installed)
        if not model:
            raise EngineError(
                "No Ollama chat/text models are installed (embedding-only models are ignored). "
                "Install one or use a ComfyUI text model."
            )
        num_predict = int(cfg["ollama"]["numPredict"])
        if payload.maxLength is not None:
            if not 1 <= int(payload.maxLength) <= num_predict:
                raise ValidationError(
                    [
                        _issue(
                            "max_length_out_of_range",
                            f"Enhancement max length must be between 1 and {num_predict}.",
                            "maxLength",
                            min=1,
                            max=num_predict,
                        )
                    ]
                )
            num_predict = int(payload.maxLength)
        options = {
            "temperature": float(
                payload.temperature if payload.temperature is not None else cfg["ollama"]["temperature"]
            ),
            "num_predict": num_predict,
        }
        try:
            data = await connectors.ollama_client().generate(
                model,
                prompt,
                system=str(system_prompt or ""),
                options=options,
                timeout=float(cfg["ollama"]["timeoutSeconds"]),
                # Enhancement needs the final rewrite, not a reasoning trace.
                # Without this a thinking model can spend the whole num_predict
                # budget in `thinking` and return an empty `response`.
                think=False,
            )
        except Exception as err:  # noqa: BLE001 - report a useful engine error
            if payload.unloadAfter:
                _, unload_error = await _unload_ollama_text_model(model)
                if unload_error:
                    logger.warning("T2I enhancement model unload failed (%s): %s", model, unload_error)
            raise EngineError(f"Ollama enhancement failed ({model}): {_err_text(err)}") from err
        unloaded = False
        unload_error = ""
        if payload.unloadAfter:
            unloaded, unload_error = await _unload_ollama_text_model(model)
            if unload_error:
                logger.warning("T2I enhancement model unload failed (%s): %s", model, unload_error)
        text = str(data.get("response") or "").strip()
        if not text:
            raise EngineError(f"Ollama returned an empty enhancement from {model}.")
        return {
            "prompt": text,
            "originalPrompt": prompt,
            "provider": "ollama",
            "model": model,
            "durationMs": int((time.monotonic() - started) * 1000),
            "unloaded": unloaded,
            "unloadError": unload_error or None,
        }

    # ComfyUI enhancement
    text_model = _find_comfy_text_model(pack, payload.model or "")
    if text_model is None:
        available = ", ".join((pack.get("comfyTextModels") or {}).keys()) or "none"
        raise ValidationError(
            [
                _issue(
                    "unknown_text_model",
                    f"Unknown ComfyUI text model `{payload.model}`. Available: {available}.",
                    "model",
                )
            ]
        )
    if text_model.get("present") is False:
        raise ValidationError(
            [
                _issue(
                    "text_model_missing",
                    f"{text_model['label']} is missing: {text_model.get('file')}.",
                    "model",
                )
            ]
        )
    if payload.maxLength is not None:
        max_allowed = int(text_model.get("maxLength") or cfg["comfyui"].get("maxLength") or 512)
        if not 1 <= int(payload.maxLength) <= max_allowed:
            raise ValidationError(
                [
                    _issue(
                        "max_length_out_of_range",
                        f"Enhancement max length must be between 1 and {max_allowed}.",
                        "maxLength",
                        min=1,
                        max=max_allowed,
                    )
                ]
            )
    status = await connectors.comfy_status()
    if not status.get("connected"):
        raise EngineError(
            f"ComfyUI is not reachable at {status.get('url') or 'the configured URL'}: "
            f"{status.get('detail') or 'connection failed'}"
        )
    graph = workflows.compose_enhance(
        pack,
        text_model,
        prompt,
        system_prompt=str(system_prompt or ""),
        max_length=payload.maxLength,
        temperature=payload.temperature,
    )
    client = connectors.comfy_client()
    try:
        submitted = await client.submit_prompt(graph, client_id=f"{MODULE_ID}:enhance")
    except Exception as err:  # noqa: BLE001
        raise EngineError(_engine_error("ComfyUI", client.base_url, err)) from err
    prompt_id = str(submitted.get("prompt_id") or "")
    if not prompt_id:
        raise EngineError("ComfyUI accepted the enhancement graph but returned no prompt_id.")
    timeout = float(cfg["comfyui"]["timeoutSeconds"])
    deadline = time.monotonic() + timeout
    failures = 0
    while True:
        if time.monotonic() >= deadline:
            # Never interrupt blindly: `interrupt` is global in ComfyUI and
            # could kill an unrelated generation. This checks the queue first.
            await _cancel_engine(client, prompt_id)
            raise EngineError(f"Timed out after {int(timeout)}s waiting for ComfyUI enhancement.")
        try:
            history = await client.history(prompt_id)
            failures = 0
        except Exception as err:  # noqa: BLE001 - transient hiccup
            failures += 1
            if failures >= 6:
                raise EngineError(
                    f"Lost connection to ComfyUI during enhancement: {_err_text(err)}"
                ) from err
            await asyncio.sleep(1.0)
            continue
        done, status_str = workflows.history_completed(history, prompt_id)
        if not done:
            await asyncio.sleep(1.0)
            continue
        if status_str == "error":
            raise EngineError(workflows.history_error(history, prompt_id))
        try:
            text = workflows.extract_enhance_text(history, prompt_id)
        except workflows.WorkflowError as err:
            raise EngineError(str(err)) from err
        return {
            "prompt": text,
            "originalPrompt": prompt,
            "provider": "comfyui",
            "model": text_model["id"],
            "durationMs": int((time.monotonic() - started) * 1000),
        }


async def start_job(payload: T2IJobRequest) -> dict:
    pack = _pack_for_request(payload.modelId)
    normalized = _normalize_request(payload, pack)
    # Compose once with a temporary prefix so graph errors surface before a job
    # exists. The real prefix is set after the job id is allocated.
    _, meta = workflows.compose_t2i(pack, normalized["model"], normalized, job_id="preview")
    params = _job_params(normalized, meta, warnings=normalized["warnings"])
    job = jobs.create_job(
        {
            "tab": normalized["tab"],
            "module": MODULE_ID,
            "modelId": normalized["model"]["id"],
            "modelName": normalized["model"]["label"],
            "recipe": normalized["recipeId"],
            "prompt": normalized["prompt"],
            "seed": normalized["seed"],
            "params": params,
            "stages": _initial_stages(),
        }
    )
    if normalized["basePrompt"] and normalized["basePrompt"] != normalized["prompt"]:
        jobs.update_job(job["id"], {"enhancedPrompt": normalized["basePrompt"]})
    cancel_event = asyncio.Event()
    _CANCEL[job["id"]] = cancel_event
    _TASKS[job["id"]] = asyncio.create_task(
        _run_job(job["id"], pack, normalized, cancel_event),
        name=f"t2i-{job['id']}",
    )
    return jobs.get_job(job["id"]) or job


def _is_t2i_job(job: dict | None) -> bool:
    return bool(job) and job.get("module") == MODULE_ID


def get_job(job_id: str) -> dict | None:
    job = jobs.get_job(job_id)
    return job if _is_t2i_job(job) else None


def list_jobs(limit: int = 80) -> list[dict]:
    return jobs.list_jobs(limit=limit, module=MODULE_ID)


async def cancel_job(job_id: str) -> dict | None:
    job = jobs.get_job(job_id)
    if not _is_t2i_job(job):
        return None
    if job["status"] in {"done", "error"}:
        return job
    event = _CANCEL.get(job_id)
    if event is not None:
        event.set()
    if job_id in _TASKS:
        # The live runner owns the engine cancellation. Doing it here too could
        # interrupt an unrelated prompt that started in the meantime.
        return jobs.get_job(job_id) or job

    # No live task (e.g. backend restarted before resume started): mark it and
    # make one best-effort attempt at the persisted ComfyUI prompt.
    client = connectors.comfy_client()
    params = job.get("params") or {}
    prompt_id = params.get("enginePromptId")
    if prompt_id:
        await _cancel_engine(client, str(prompt_id))
    stages = job.get("stages") or _initial_stages()
    for stage in stages:
        if stage.get("status") == "running":
            stage["status"] = "error"
            stage["detail"] = "Cancelled by user"
            stage["finishedAt"] = jobs.now_ms()
            break
    jobs.update_job(job_id, {"status": "error", "error": "Cancelled by user", "stages": stages})
    return jobs.get_job(job_id) or job


def delete_job(job_id: str, *, delete_assets: bool = True) -> dict | None:
    """Remove a terminal job from history.

    Job rows are soft-deleted so the audit trail survives; when `delete_assets`
    is true, each result asset is moved to the library trash using the same
    restore path as a manual library delete. Running jobs must be cancelled
    first, which keeps the runner from writing to a hidden record.
    """
    job = get_job(job_id)
    if job is None:
        return None
    if job["status"] in {"queued", "running"}:
        raise ValidationError(
            [_issue("job_running", "Cancel this job before deleting it.", "jobId")]
        )

    trashed, missing = _trash_job_assets(job) if delete_assets else ([], [])
    if not jobs.delete_job(job_id):
        return None
    _CANCEL.pop(job_id, None)
    _TASKS.pop(job_id, None)
    return {
        "id": job_id,
        "deleted": True,
        "assetsTrashed": trashed,
        "assetsMissing": missing,
    }


def _trash_job_assets(job: dict) -> tuple[list[str], list[str]]:
    trashed: list[str] = []
    missing: list[str] = []
    for asset_id in job.get("resultIds") or []:
        asset = library.trash_asset(str(asset_id))
        if asset is None:
            missing.append(str(asset_id))
        else:
            trashed.append(str(asset["id"]))
    return trashed, missing


def clear_history(*, delete_assets: bool = False) -> dict:
    """Clear this module's chat history without touching any other GenModule.

    Running jobs are deliberately rejected rather than silently cancelled: the
    caller may still want the result, and deleting a live record would let the
    runner finish against a hidden job. With ``delete_assets`` the result files
    are moved through the library trash path, so they stay recoverable.
    """
    current = jobs.list_jobs(limit=10_000, module=MODULE_ID)
    active = [
        str(job["id"])
        for job in current
        if job.get("status") in {"queued", "running"}
    ]
    if active:
        raise ValidationError(
            [
                _issue(
                    "job_running",
                    "Cancel the active generation before clearing this chat.",
                    "jobId",
                    jobIds=active,
                )
            ]
        )

    job_ids: list[str] = []
    trashed: list[str] = []
    missing: list[str] = []
    seen_assets: set[str] = set()
    for job in current:
        job_id = str(job["id"])
        if delete_assets:
            job_trashed, job_missing = _trash_job_assets(job)
            for asset_id in job_trashed:
                if asset_id not in seen_assets:
                    seen_assets.add(asset_id)
                    trashed.append(asset_id)
            for asset_id in job_missing:
                if asset_id not in seen_assets:
                    seen_assets.add(asset_id)
                    missing.append(asset_id)
        if jobs.delete_job(job_id):
            job_ids.append(job_id)
            _CANCEL.pop(job_id, None)
            _TASKS.pop(job_id, None)

    return {
        "deleted": len(job_ids),
        "jobIds": job_ids,
        "assetsTrashed": trashed,
        "assetsMissing": missing,
    }


async def resume_pending_jobs() -> None:
    """Reattach to ComfyUI prompts persisted in running jobs (best effort)."""
    try:
        pack = catalog.load_pack()
        limits = pack["options"]["limits"]
    except Exception as err:  # noqa: BLE001 - a broken pack must not break app boot
        logger.warning("[t2i] cannot resume jobs: %s", err)
        return
    for job in jobs.list_jobs(limit=100, module=MODULE_ID):
        if job.get("status") != "running":
            continue
        if job["id"] in _TASKS:
            continue
        params = job.get("params") or {}
        prompt_id = str(params.get("enginePromptId") or "")
        if not prompt_id:
            jobs.update_job(
                job["id"],
                {
                    "status": "error",
                    "error": "Backend restarted before the job was submitted. Start a new job.",
                },
            )
            continue
        event = asyncio.Event()
        _CANCEL[job["id"]] = event
        _TASKS[job["id"]] = asyncio.create_task(
            _resume_job(job, prompt_id, event, limits),
            name=f"t2i-resume-{job['id']}",
        )
        logger.info("[t2i] resuming job %s (prompt %s)", job["id"], prompt_id)


def shutdown() -> None:
    for task in list(_TASKS.values()):
        task.cancel()
    _TASKS.clear()
    _CANCEL.clear()
