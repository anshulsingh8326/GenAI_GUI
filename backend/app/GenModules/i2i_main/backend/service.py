"""i2i_main service - validation, source image handling, job runner, collection.

This is the only place that turns an Image -> Image request into a ComfyUI
prompt. It is intentionally strict:

- the tracked pack is reloaded per request, so a pro user's range edit applies
  without a restart;
- every numeric input is checked against the model pack range and against the
  engine hard limit;
- the source image is decoded, size-checked and normalized server-side, then
  uploaded to ComfyUI's input folder once per job;
- the same graph composer is used by /validate and /jobs, so a request that
  validates cannot silently become a different graph;
- ComfyUI switches are never used - the composer prunes the unused branch.

Jobs are persisted through app.jobs.service. The runner polls ComfyUI history,
downloads output bytes and registers them through app.library.service. If the
backend restarts, `resume_pending_jobs()` reattaches to the stored prompt id.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import io
import json
import logging
import re
import secrets
import time
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageOps

from app.common import module_setup
from app.connectors import service as connectors
from app.jobs import service as jobs
from app.library import service as library

from . import catalog, workflows
from .schema import I2IJobRequest

logger = logging.getLogger("uvicorn.error")

MODULE_ID = "i2i_main"
TAB_ID = "image-to-image"
MODULE_DIR = Path(__file__).resolve().parent.parent
REQUIREMENTS_FILE = MODULE_DIR / "requirements.json"
MANIFEST_FILE = MODULE_DIR / "manifest.json"
STAGE_DEFS = (
    ("source", "Prepare reference images"),
    ("upload", "Upload references to ComfyUI"),
    ("compose", "Compose workflow"),
    ("submit", "Submit to ComfyUI"),
    ("generate", "Edit image"),
    ("collect", "Collect results"),
)
REQUIRED_NODES = (
    "TextEncodeQwenImage21",
    "QwenImage21Cache",
    "RepeatLatentBatch",
    "ManualSigmas",
    "KSamplerSelect",
    "SamplerCustom",
)

_DATA_URL_RE = re.compile(r"^data:(?P<mime>[\w.+-]+/[\w.+-]+);base64,(?P<data>.*)$", re.S)

_TASKS: dict[str, asyncio.Task] = {}
_CANCEL: dict[str, asyncio.Event] = {}


class ValidationError(Exception):
    def __init__(self, errors: list[dict], warnings: list[dict] | None = None):
        self.errors = errors
        self.warnings = warnings or []
        first = errors[0]["message"] if errors else "Invalid Image -> Image request"
        super().__init__(first)


class EngineError(Exception):
    """ComfyUI is unavailable or rejected/failed the request."""


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
                "A pro user can widen the safe range in the i2i pack JSON, up to the hard limit.",
                field,
                min=safe_min,
                max=safe_max,
            )
        )

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
                                f"{_fmt(safe_min)}-{_fmt(safe_max)}.",
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


# -- source image ---------------------------------------------------------------


def _thumbnail_data_url(image: Image.Image, max_side: int) -> str:
    thumb = image.copy()
    thumb.thumbnail((max_side, max_side), Image.LANCZOS)
    if thumb.mode in {"RGBA", "LA", "P"}:
        background = Image.new("RGB", thumb.size, (16, 16, 20))
        rgba = thumb.convert("RGBA")
        background.paste(rgba, mask=rgba.getchannel("A"))
        thumb = background
    else:
        thumb = thumb.convert("RGB")
    buffer = io.BytesIO()
    thumb.save(buffer, format="JPEG", quality=82, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _decode_source(
    raw: str,
    source_limits: dict,
    errors: list[dict],
    warnings: list[dict],
    *,
    label: str = "Image 1",
    field: str = "sourceImages",
) -> dict | None:
    text = (raw or "").strip()
    if not text:
        errors.append(
            _issue("source_required", f"{label} is required for Image -> Image.", field)
        )
        return None

    max_chars = int(source_limits.get("maxDataUrlChars") or 28_000_000)
    if len(text) > max_chars:
        errors.append(
            _issue(
                "source_too_large",
                f"{label} payload is {len(text)} characters; the limit is {max_chars}.",
                field,
            )
        )
        return None

    mime = ""
    data_part = text
    match = _DATA_URL_RE.match(text)
    if match:
        mime = str(match.group("mime") or "").lower()
        data_part = match.group("data")
    elif text.startswith("data:"):
        errors.append(
            _issue(
                "source_invalid",
                f"{label} data URL is malformed. Re-select the image.",
                field,
            )
        )
        return None

    allowed = {str(item).lower() for item in (source_limits.get("mimeTypes") or [])}
    if mime and allowed and mime not in allowed:
        errors.append(
            _issue(
                "source_type",
                f"`{mime}` is not a supported type for {label}. Use "
                f"{', '.join(sorted(allowed))}.",
                field,
            )
        )
        return None

    try:
        data = base64.b64decode(re.sub(r"\s+", "", data_part), validate=True)
    except (binascii.Error, ValueError) as exc:
        errors.append(
            _issue("source_invalid", f"{label} is not valid base64: {exc}", field)
        )
        return None
    if not data:
        errors.append(_issue("source_invalid", f"{label} is empty.", field))
        return None

    max_bytes = int(source_limits.get("maxBytes") or 20 * 1024 * 1024)
    if len(data) > max_bytes:
        errors.append(
            _issue(
                "source_too_large",
                f"{label} is {len(data)} bytes; the limit is {max_bytes} bytes.",
                field,
            )
        )
        return None

    max_side = int(source_limits.get("maxSide") or 4096)
    max_pixels = int(source_limits.get("maxPixels") or 80_000_000)
    try:
        with Image.open(io.BytesIO(data)) as opened:
            opened.load()
            width, height = opened.size
            if width < 16 or height < 16:
                errors.append(
                    _issue(
                        "source_too_small",
                        f"{label} is {width}x{height}; use at least 16x16.",
                        field,
                    )
                )
                return None
            if max(width, height) > max_side:
                errors.append(
                    _issue(
                        "source_dimensions",
                        f"{label} is {width}x{height}; the longest side may not exceed {max_side} px.",
                        field,
                    )
                )
                return None
            if width * height > max_pixels:
                errors.append(
                    _issue(
                        "source_dimensions",
                        f"{label} has {width * height} pixels; the limit is {max_pixels}.",
                        field,
                    )
                )
                return None
            image = ImageOps.exif_transpose(opened)
            if image.mode != "RGBA":
                image = image.convert("RGBA")
            normalized = Image.new("RGBA", image.size, (0, 0, 0, 0))
            normalized.alpha_composite(image)
            image = normalized
            encoded = io.BytesIO()
            image.save(encoded, format="PNG", optimize=True)
            png = encoded.getvalue()
            thumbnail = _thumbnail_data_url(image, int(source_limits.get("thumbSize") or 384))
    except Exception as exc:  # noqa: BLE001 - any decode failure is a user-facing validation error
        errors.append(
            _issue(
                "source_invalid",
                f"{label} could not be decoded: {exc}",
                field,
            )
        )
        return None

    if width > 2048 or height > 2048:
        warnings.append(
            _issue(
                "source_large",
                f"{label} is {width}x{height}. Large references take longer and use more VRAM; "
                "consider a 1024 or 1536 pixel budget.",
                field,
            )
        )

    return {
        "bytes": png,
        "mime": "image/png",
        "originalName": "source",
        "width": int(width),
        "height": int(height),
        "thumbnail": thumbnail,
        "declaredBytes": len(data),
    }


# -- request validation ---------------------------------------------------------


def _resolve_model(pack: dict, model_id: str | None) -> dict:
    wanted = str(model_id or "").strip() or str(pack["defaults"].get("modelId") or "")
    model = pack["models"].get(wanted)
    if model is None:
        raise ValidationError(
            [
                _issue(
                    "unknown_model",
                    f"Unknown Image -> Image model `{wanted}`. Available: "
                    f"{', '.join(sorted(pack['models']))}.",
                    "modelId",
                )
            ]
        )
    return model


def _normalize_request(payload: I2IJobRequest, pack: dict) -> dict:
    """Validate a request against the tracked pack and return a normalized view."""
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
                f"Negative prompt is {len(negative)} characters; the limit is "
                f"{limits['negativePromptMaxChars']}.",
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
        raise ValidationError(
            [_issue("unknown_model", f"Model `{model['id']}` disappeared from the pack.", "modelId")]
        )
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
    if model_view.get("textEncoderLocation"):
        location = model_view["textEncoderLocation"]
        errors.append(
            _issue(
                "text_encoder_misplaced",
                f"Found a Qwen3-VL text encoder at `{location['target']}/{location['name']}`. "
                "ComfyUI's CLIPLoader only reads `models/text_encoders`, so move the file there "
                "(this app never moves it) and refresh the model catalog.",
                "textEncoder",
                found=location,
            )
        )

    max_images = max(1, int(options["source"].get("maxImages") or 3))
    requested = [
        {"image": item.image, "name": item.name} for item in (payload.sourceImages or [])
    ]
    if not requested and (payload.sourceImage or payload.sourceName):
        requested = [{"image": payload.sourceImage, "name": payload.sourceName}]
    if not requested:
        errors.append(
            _issue(
                "source_required",
                "At least one reference image is required for Image -> Image.",
                "sourceImages",
            )
        )
    elif len(requested) > max_images:
        errors.append(
            _issue(
                "too_many_sources",
                f"This model accepts up to {max_images} reference image(s); "
                f"{len(requested)} were provided.",
                "sourceImages",
                max=max_images,
            )
        )
        requested = requested[:max_images]

    sources: list[dict] = []
    for index, item in enumerate(requested):
        decoded = _decode_source(
            item["image"],
            options["source"],
            errors,
            warnings,
            label=f"Image {index + 1}",
            field=f"sourceImages[{index}].image",
        )
        if decoded is None:
            continue
        supplied = Path(str(item.get("name") or "")).name[:120]
        decoded["originalName"] = supplied or f"image-{index + 1}"
        sources.append(decoded)
    source = sources[0] if sources else None

    resolution_values = {int(item["value"]) for item in options["resolutions"]}
    resolution = int(payload.resolution if payload.resolution is not None else pack["defaults"]["resolution"])
    if resolution not in resolution_values:
        errors.append(
            _issue(
                "unknown_resolution",
                f"Resolution `{resolution}` is not available. Choose one of "
                f"{', '.join(str(value) for value in sorted(resolution_values))}.",
                "resolution",
            )
        )
        resolution = int(pack["defaults"]["resolution"])

    batch = _range_value(
        model_view["ranges"]["batch"], payload.batch, "batch", errors, warnings, integer=True
    )
    steps = _range_value(
        model_view["ranges"]["steps"],
        payload.steps,
        "steps",
        errors,
        warnings,
        integer=True,
    )
    cfg = _range_value(
        model_view["ranges"]["cfg"],
        payload.cfg,
        "cfg",
        errors,
        warnings,
        align_step=True,
    )
    denoise = _range_value(
        model_view["ranges"]["denoise"],
        payload.denoise,
        "denoise",
        errors,
        warnings,
        align_step=True,
    )
    sampler_ids = {str(item["id"]) for item in options["samplers"]}
    sampler = str(payload.sampler or model_view["defaults"]["sampler"]).strip()
    if sampler not in sampler_ids:
        errors.append(
            _issue(
                "unknown_sampler",
                f"Unknown sampler `{sampler}`. Available: {', '.join(sorted(sampler_ids))}.",
                "sampler",
            )
        )
        sampler = model_view["defaults"]["sampler"]

    cache_device = str(payload.cacheDevice or pack["defaults"]["cache"]["device"]).strip()
    if cache_device not in options["cacheDevices"]:
        errors.append(
            _issue(
                "unknown_cache_device",
                f"Unknown cache device `{cache_device}`. Available: "
                f"{', '.join(options['cacheDevices'])}.",
                "cacheDevice",
            )
        )
        cache_device = pack["defaults"]["cache"]["device"]
    cache_dtype = str(payload.cacheDtype or pack["defaults"]["cache"]["dtype"]).strip()
    if cache_dtype not in options["cacheDtypes"]:
        errors.append(
            _issue(
                "unknown_cache_dtype",
                f"Unknown cache dtype `{cache_dtype}`. Available: "
                f"{', '.join(options['cacheDtypes'])}.",
                "cacheDtype",
            )
        )
        cache_dtype = pack["defaults"]["cache"]["dtype"]

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

    recipe_id = str(payload.recipeId or "").strip() or pack["recipe"]["id"]
    if recipe_id != pack["recipe"]["id"]:
        errors.append(
            _issue(
                "unknown_recipe",
                f"Unknown recipe `{recipe_id}`. This module serves `{pack['recipe']['id']}`.",
                "recipeId",
            )
        )
        recipe_id = pack["recipe"]["id"]

    width, height = (
        workflows.target_dimensions(source["width"], source["height"], resolution)
        if source is not None
        else (0, 0)
    )
    if int(steps) != int(model_view["defaults"]["steps"]):
        warnings.append(
            _issue(
                "steps_not_turbo",
                f"Turbo ships an {int(model_view['defaults']['steps'])}-step sigma schedule. "
                f"{int(steps)} steps interpolate it and may reduce fidelity; 8 is recommended.",
                "steps",
            )
        )
    if float(denoise) < 1.0:
        warnings.append(
            _issue(
                "img2img_path",
                f"Denoise {_fmt(denoise)} starts from the VAE-encoded source instead of the "
                "official turbo edit path. Use 1.0 for the reference behaviour.",
                "denoise",
            )
        )

    if errors:
        raise ValidationError(errors, warnings)

    assert source is not None
    return {
        "prompt": prompt,
        "negativePrompt": negative,
        "model": model_view,
        "source": source,
        "sources": sources,
        "sourceName": source["originalName"],
        "resolution": int(resolution),
        "width": int(width),
        "height": int(height),
        "batch": int(batch),
        "seed": int(seed),
        "lockSeed": bool(payload.lockSeed),
        "seedRandomized": seed_randomized,
        "steps": int(steps),
        "cfg": float(cfg),
        "denoise": float(denoise),
        "sampler": sampler,
        "scheduler": "manual",
        "cacheDevice": cache_device,
        "cacheDtype": cache_dtype,
        "recipeId": recipe_id,
        "tab": (payload.tab or TAB_ID).strip() or TAB_ID,
        "warnings": warnings,
    }


def _source_view(source: dict) -> dict:
    return {
        "name": source["originalName"],
        "width": source["width"],
        "height": source["height"],
        "thumbnail": source["thumbnail"],
    }


def _public_normalized(normalized: dict) -> dict:
    source = normalized["source"]
    sources = normalized.get("sources") or [source]
    return {
        "modelId": normalized["model"]["id"],
        "modelName": normalized["model"]["label"],
        "prompt": normalized["prompt"],
        "negativePrompt": normalized["negativePrompt"],
        "resolution": normalized["resolution"],
        "width": normalized["width"],
        "height": normalized["height"],
        "batch": normalized["batch"],
        "seed": normalized["seed"],
        "lockSeed": normalized["lockSeed"],
        "seedRandomized": normalized["seedRandomized"],
        "steps": normalized["steps"],
        "cfg": normalized["cfg"],
        "denoise": normalized["denoise"],
        "sampler": normalized["sampler"],
        "scheduler": normalized["scheduler"],
        "cacheDevice": normalized["cacheDevice"],
        "cacheDtype": normalized["cacheDtype"],
        "source": _source_view(source),
        "sources": [_source_view(item) for item in sources],
        "recipeId": normalized["recipeId"],
        "tab": normalized["tab"],
    }


# -- jobs -----------------------------------------------------------------------


def _initial_stages() -> list[dict]:
    return [
        {"id": stage_id, "label": label, "status": "pending", "detail": ""}
        for stage_id, label in STAGE_DEFS
    ]


def _job_params(
    normalized: dict,
    meta: dict | None,
    *,
    engine_prompt_id: str | None = None,
    warnings: list[dict] | None = None,
) -> dict:
    source = normalized["source"]
    sources = normalized.get("sources") or [source]

    def view(item: dict) -> dict:
        return {
            "name": item.get("uploadName") or "",
            "originalName": item["originalName"],
            "width": item["width"],
            "height": item["height"],
            "thumbnail": item["thumbnail"],
        }

    return {
        "recipe": normalized["recipeId"],
        "recipeId": normalized["recipeId"],
        "seed": normalized["seed"],
        "lockSeed": normalized["lockSeed"],
        "seedRandomized": normalized["seedRandomized"],
        "steps": normalized["steps"],
        "effectiveSteps": (meta or {}).get("effectiveSteps", normalized["steps"]),
        "cfg": normalized["cfg"],
        "sampler": normalized["sampler"],
        "scheduler": normalized["scheduler"],
        "denoise": normalized["denoise"],
        "resolution": normalized["resolution"],
        "width": normalized["width"],
        "height": normalized["height"],
        "batch": normalized["batch"],
        "cacheDevice": normalized["cacheDevice"],
        "cacheDtype": normalized["cacheDtype"],
        "modelId": normalized["model"]["id"],
        "modelName": normalized["model"]["label"],
        "promptUsed": normalized["prompt"],
        "negativePrompt": normalized["negativePrompt"],
        "source": view(source),
        "sources": [view(item) for item in sources],
        "referenceCount": len(sources),
        "enginePromptId": engine_prompt_id,
        "workflow": (meta or {}).get("workflow") or normalized["model"]["workflow"],
        "nodeCount": (meta or {}).get("nodeCount"),
        "path": (meta or {}).get("path"),
        "warnings": list(normalized["warnings"] if warnings is None else warnings),
    }


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
        tracker.progress(min(90, 40 + int(elapsed / 2)))
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
    tags = ["image-to-image", MODULE_ID]
    recipe = str(job_params.get("recipeId") or "").strip()
    if recipe:
        tags.append(recipe)
    if str(job_params.get("path") or "") == "img2img":
        tags.append("img2img")
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
        sources = normalized.get("sources") or [normalized["source"]]
        tracker.start(
            "source",
            f"Preparing {len(sources)} reference image(s)...",
        )
        tracker.done(
            "source",
            ", ".join(
                f"Image {index + 1} {item['width']}x{item['height']}"
                for index, item in enumerate(sources)
            )
            + f" -> {normalized['width']}x{normalized['height']}",
        )
        tracker.progress(6)
        _check_cancel(cancel_event)

        tracker.start(
            "upload",
            f"Sending {len(sources)} reference image(s) to ComfyUI...",
        )
        client = connectors.comfy_client()
        token = re.sub(r"[^A-Za-z0-9_-]+", "_", job_id)
        source_refs: list[str] = []
        for index, source in enumerate(sources):
            upload_name = f"genai_i2i_{token}_{index + 1}.png"
            try:
                uploaded = await client.upload_image(
                    source["bytes"],
                    upload_name,
                    subfolder="genai_i2i",
                )
            except Exception as err:  # noqa: BLE001 - turn transport errors into readable job errors
                raise EngineError(_engine_error("ComfyUI", client.base_url, err)) from err
            returned_name = str(uploaded.get("name") or upload_name)
            returned_sub = str(uploaded.get("subfolder") or "")
            source_ref = f"{returned_sub}/{returned_name}" if returned_sub else returned_name
            source["uploadName"] = source_ref
            source_refs.append(source_ref)
        tracker.done("upload", ", ".join(source_refs))
        tracker.progress(14)
        _check_cancel(cancel_event)

        tracker.start("compose", "Building the ComfyUI API graph...")
        graph, meta = workflows.compose_i2i(
            pack,
            normalized["model"],
            normalized,
            source_images=source_refs,
            job_id=job_id,
        )
        jobs.update_job(
            job_id,
            {"params": _job_params(normalized, meta)},
        )
        tracker.done("compose", f"{meta['nodeCount']} nodes")
        tracker.progress(22)
        _check_cancel(cancel_event)

        tracker.start("submit", "Submitting to ComfyUI...")
        try:
            submitted = await client.submit_prompt(graph, client_id=f"{MODULE_ID}:{job_id}")
        except Exception as err:  # noqa: BLE001
            raise EngineError(_engine_error("ComfyUI", client.base_url, err)) from err
        prompt_id = str(submitted.get("prompt_id") or "")
        if not prompt_id:
            raise EngineError("ComfyUI accepted the request but returned no prompt_id.")
        jobs.update_job(
            job_id,
            {
                "params": _job_params(
                    normalized,
                    meta,
                    engine_prompt_id=prompt_id,
                )
            },
        )
        tracker.done("submit", f"prompt {prompt_id}")
        tracker.progress(32)

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
        logger.info("[i2i] job %s done: %s image(s)", job_id, len(assets))
    except JobCancelled:
        tracker.fail(tracker.active or "generate", "Cancelled by user")
        jobs.update_job(job_id, {"status": "error", "error": "Cancelled by user"})
        if not completed:
            await _cancel_engine(client, prompt_id)
        logger.info("[i2i] job %s cancelled", job_id)
    except Exception as err:  # noqa: BLE001 - every failure must land on the job record
        if isinstance(err, (EngineError, ValidationError)):
            logger.warning("[i2i] job %s stopped: %s", job_id, err)
        else:
            logger.exception("[i2i] job %s failed", job_id)
        message = _err_text(err)[:1200] or "Image -> Image job failed."
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
    by_id["source"]["status"] = "done"
    by_id["source"]["detail"] = "Resumed from persisted job metadata."
    by_id["upload"]["status"] = "done"
    by_id["upload"]["detail"] = "Resumed from persisted job metadata."
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
        logger.info("[i2i] resumed job %s done: %s image(s)", job_id, len(assets))
    except JobCancelled:
        tracker.fail(tracker.active or "generate", "Cancelled by user")
        jobs.update_job(job_id, {"status": "error", "error": "Cancelled by user"})
        if not completed:
            await _cancel_engine(client, prompt_id)
    except Exception as err:  # noqa: BLE001
        if isinstance(err, EngineError):
            logger.warning("[i2i] resumed job %s engine error: %s", job_id, err)
        else:
            logger.exception("[i2i] resumed job %s failed", job_id)
        message = _err_text(err)[:1200] or "Image -> Image resume failed."
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


async def _node_report(client, model_view: dict | None) -> dict[str, bool | None]:
    """Probe the ComfyUI nodes this module needs. Never raises."""
    names = list(REQUIRED_NODES)
    if model_view is not None:
        if model_view.get("loader") == "UnetLoaderGGUF" and "UnetLoaderGGUF" not in names:
            names.append("UnetLoaderGGUF")
        if (
            model_view.get("textEncoderLoader") == "CLIPLoaderGGUF"
            and "CLIPLoaderGGUF" not in names
        ):
            names.append("CLIPLoaderGGUF")

    async def probe(name: str) -> bool | None:
        try:
            result = await client.object_info_node(name, timeout=8.0)
        except Exception:  # noqa: BLE001 - a probe failure is "unknown", not "missing"
            return None
        return bool(isinstance(result, dict) and name in result)

    results = await asyncio.gather(*(probe(name) for name in names))
    return dict(zip(names, results))


async def catalog_snapshot(model_id: str | None = None) -> dict:
    pack = _pack_for_request(model_id)
    user = catalog.load_user_catalog()
    if model_id and model_id not in pack["models"]:
        raise ValidationError(
            [_issue("unknown_model", f"Unknown Image -> Image model `{model_id}`.", "modelId")]
        )
    probe = await connectors.comfy_status()
    comfy = probe if isinstance(probe, dict) else {
        "connected": False,
        "detail": str(probe)[:240],
        "installed": [],
    }
    engine = {"comfyui": comfy, "ready": bool(comfy.get("connected"))}

    node_report: dict[str, bool | None] = {}
    if comfy.get("connected") and model_id:
        try:
            preview = catalog.build_snapshot(pack, user, model_id=model_id, engine=engine)
            node_report = await _node_report(connectors.comfy_client(), preview.get("model"))
        except Exception:  # noqa: BLE001 - catalog must render even if a probe fails
            logger.debug("[i2i] node probe failed", exc_info=True)

    try:
        snapshot = catalog.build_snapshot(
            pack,
            user,
            model_id=model_id,
            engine=engine,
            node_report=node_report,
        )
    except KeyError as exc:
        raise ValidationError([_issue("unknown_model", str(exc), "modelId")]) from exc

    if not comfy.get("connected"):
        snapshot.setdefault("warnings", [])
        if not any(item.get("code") == "comfyui_offline" for item in snapshot["warnings"]):
            snapshot["warnings"].append(
                _issue(
                    "comfyui_offline",
                    "ComfyUI is offline. Generation is unavailable until it is running.",
                )
            )
    snapshot["engine"] = engine
    snapshot["nodeInfo"] = node_report
    return snapshot


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
        "samplers": pack["options"]["samplers"],
        "resolutions": pack["options"]["resolutions"],
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


def _preview_refs(normalized: dict) -> list[str]:
    count = max(1, len(normalized.get("sources") or []))
    return [f"genai_i2i/preview_{index + 1}.png" for index in range(count)]


def validate_payload(payload: I2IJobRequest) -> dict:
    pack = _pack_for_request(payload.modelId)
    normalized = _normalize_request(payload, pack)
    graph, meta = workflows.compose_i2i(
        pack,
        normalized["model"],
        normalized,
        source_images=_preview_refs(normalized),
        job_id="preview",
    )
    return {
        "valid": True,
        "normalized": _public_normalized(normalized),
        "warnings": normalized["warnings"],
        "graph": {
            "recipeId": meta["recipeId"],
            "nodeCount": meta["nodeCount"],
            "width": meta["width"],
            "height": meta["height"],
            "batch": meta["batch"],
            "path": meta["path"],
            "scheduler": meta["scheduler"],
        },
    }


async def start_job(payload: I2IJobRequest) -> dict:
    pack = _pack_for_request(payload.modelId)
    normalized = _normalize_request(payload, pack)
    # Compose once with a temporary prefix so graph errors surface before a job
    # exists. The real prefix is set after the job id is allocated.
    _, meta = workflows.compose_i2i(
        pack,
        normalized["model"],
        normalized,
        source_images=_preview_refs(normalized),
        job_id="preview",
    )
    params = _job_params(normalized, meta)
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
    cancel_event = asyncio.Event()
    _CANCEL[job["id"]] = cancel_event
    _TASKS[job["id"]] = asyncio.create_task(
        _run_job(job["id"], pack, normalized, cancel_event),
        name=f"i2i-{job['id']}",
    )
    return jobs.get_job(job["id"]) or job


def _is_i2i_job(job: dict | None) -> bool:
    return bool(job) and job.get("module") == MODULE_ID


def get_job(job_id: str) -> dict | None:
    job = jobs.get_job(job_id)
    return job if _is_i2i_job(job) else None


def list_jobs(limit: int = 80) -> list[dict]:
    return jobs.list_jobs(limit=limit, module=MODULE_ID)


async def cancel_job(job_id: str) -> dict | None:
    job = jobs.get_job(job_id)
    if not _is_i2i_job(job):
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
        logger.warning("[i2i] cannot resume jobs: %s", err)
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
            name=f"i2i-resume-{job['id']}",
        )
        logger.info("[i2i] resuming job %s (prompt %s)", job["id"], prompt_id)


def shutdown() -> None:
    for task in list(_TASKS.values()):
        task.cancel()
    _TASKS.clear()
    _CANCEL.clear()
