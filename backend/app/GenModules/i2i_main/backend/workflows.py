"""ComfyUI API-format graph composition for i2i_main.

The pack ships one API-format graph built from the official Qwen Image 2.1
image-edit workflow. The composer rewrites only what the request changes:

- diffusion / text encoder / VAE loaders (chosen from the real filenames)
- the KV-cache device and dtype
- the 1..3 reference images (``TextEncodeQwenImage21`` exposes
  ``images.image_1`` .. ``images.image_3``)
- prompt, negative prompt and the reference resolution budget
- sampler, seed, CFG, steps and denoise
- the save prefix

Two sampling paths exist, and the composer prunes the unused branch instead of
adding a switch node:

- ``denoise == 1.0``: ``TextEncodeQwenImage21`` returns an empty 64-channel
  latent at the first reference's size and the turbo sigma schedule samples it.
- ``denoise < 1.0``: the first reference is scaled to the same size, encoded by
  the VAE, and sampled with the tail of the turbo schedule.

Sampling goes through ``SamplerCustom`` + ``ManualSigmas`` instead of
``KSampler``. Qwen Image 2.1 Turbo ships its own 8-step schedule
(``sample_sigmas`` in the checkpoint) and ComfyUI's ``simple`` scheduler produces
a very different curve, which visibly hurts edits. ``ManualSigmas`` feeds the
shipped values so ComfyUI follows the model's own schedule. Other step counts are
interpolated from it, and a lower denoise starts later in the same schedule.

``RepeatLatentBatch`` applies the requested batch to either latent source, so the
graph never needs an ``EmptyLatentImage`` (which would emit 16 channels instead
of the 64 the 2.1 transformer expects).

Only core ComfyUI nodes are used. The graph requires ComfyUI 0.37.0 or newer,
which ships ``TextEncodeQwenImage21``, ``QwenImage21Cache`` and
``ManualSigmas``.
"""

from __future__ import annotations

import copy
import math
import re
from typing import Any

FULL_DENOISE = 0.999

# Qwen Image 2.1 Turbo ships this 8-step schedule in the checkpoint
# (`sample_sigmas` in model_index.json). It holds high sigmas far longer than
# ComfyUI's `simple` scheduler, so the graph feeds it through ManualSigmas.
TURBO_SIGMAS = (
    1.0,
    0.978453,
    0.95418,
    0.926626,
    0.89508,
    0.845148,
    0.704534,
    0.414568,
    0.0,
)
TURBO_STEPS = len(TURBO_SIGMAS) - 1


def turbo_schedule(steps: int) -> list[float]:
    """Return the turbo sigma schedule interpolated to ``steps`` steps.

    The shipped 8-step values are returned verbatim. Other counts are
    log-linearly interpolated between the positive sigmas, which keeps the
    curve's shape; the terminal 0 is always exact.
    """
    steps = max(1, int(steps))
    if steps == TURBO_STEPS:
        return list(TURBO_SIGMAS)
    positive = TURBO_SIGMAS[:-1]
    last = len(positive) - 1
    schedule: list[float] = []
    for index in range(steps):
        position = (index * last / (steps - 1)) if steps > 1 else 0.0
        lower = int(math.floor(position))
        upper = min(lower + 1, last)
        frac = position - lower
        start, end = positive[lower], positive[upper]
        schedule.append(math.exp(math.log(start) * (1.0 - frac) + math.log(end) * frac))
    schedule.append(0.0)
    return schedule


def sampling_sigmas(steps: int, denoise: float) -> list[float]:
    """Trim the turbo schedule so ``denoise`` starts later in the same curve."""
    schedule = turbo_schedule(steps)
    if float(denoise) >= FULL_DENOISE:
        return schedule
    total = len(schedule) - 1
    effective = max(1, min(total, int(round(total * float(denoise)))))
    return schedule[total - effective :]


def _sigma_text(values: list[float]) -> str:
    parts = []
    for value in values:
        text = f"{value:.6f}".rstrip("0")
        if text.endswith("."):
            text += "0"
        parts.append(text)
    return ", ".join(parts)


class WorkflowError(Exception):
    pass


def _round32(value: float) -> int:
    return max(32, int(round(float(value) / 32.0) * 32))


def target_dimensions(source_width: int, source_height: int, resolution: int) -> tuple[int, int]:
    """Return the output latent size for the first reference image.

    ``resolution == 0`` keeps the source size rounded to 32. A positive value is
    a total pixel budget that keeps the aspect ratio. ``TextEncodeQwenImage21``
    uses the same rule to size the latent it emits, so the img2img branch scales
    the first reference to exactly the size the encoder would have used.
    """
    width = max(1, int(source_width or 1))
    height = max(1, int(source_height or 1))
    if int(resolution or 0) > 0:
        budget = float(resolution)
        ratio = width / height
        out_w = _round32(math.sqrt(budget * budget * ratio))
        out_h = _round32(math.sqrt(budget * budget / ratio))
    else:
        out_w = _round32(width)
        out_h = _round32(height)
    return out_w, out_h


def _safe_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "")).strip("_")
    return token or "i2i"


def _node(graph: dict, node_id: str) -> dict:
    node = graph.get(node_id)
    if not isinstance(node, dict):
        raise WorkflowError(f"Workflow is missing node {node_id}.")
    return node


def _set(graph: dict, node_id: str, **inputs: Any) -> None:
    node = _node(graph, node_id)
    node.setdefault("inputs", {}).update(inputs)


def _remove(graph: dict, node_ids: list[str]) -> None:
    for node_id in node_ids:
        graph.pop(node_id, None)


def _check_links(graph: dict) -> None:
    for node_id, node in graph.items():
        for name, value in (node.get("inputs") or {}).items():
            if (
                isinstance(value, list)
                and len(value) == 2
                and isinstance(value[0], str)
                and value[0] not in graph
            ):
                raise WorkflowError(
                    f"Node {node_id} input `{name}` references missing node `{value[0]}`."
                )


def assert_no_switches(graph: dict) -> None:
    for node_id, node in graph.items():
        class_type = str((node or {}).get("class_type") or "")
        if "IAMCCS" in class_type or "Switch" in class_type:
            raise WorkflowError(
                f"Node {node_id} uses `{class_type}`. i2i_main prunes blocks instead of switching."
            )


SOURCE_SLOTS = (("5", "image_1"), ("6", "image_2"), ("7", "image_3"))
MAX_REFERENCES = 3


def _reference_refs(
    source_images: list[str] | None,
    source_image: str | None,
) -> list[str]:
    """Normalize the reference list and keep the first, second and third slot."""
    refs = [str(item).strip() for item in (source_images or []) if str(item).strip()]
    if not refs and str(source_image or "").strip():
        refs = [str(source_image).strip()]
    if not refs:
        raise WorkflowError("At least one reference image is required.")
    return refs[:MAX_REFERENCES]


def compose_i2i(
    pack: dict,
    model: dict,
    normalized: dict,
    *,
    source_images: list[str] | None = None,
    source_image: str | None = None,
    job_id: str = "preview",
) -> tuple[dict, dict]:
    """Build the API graph for one request and return ``(graph, meta)``."""
    if model.get("workflow") not in (pack.get("workflows") or {}):
        raise WorkflowError(f"Unknown workflow `{model.get('workflow')}`.")
    graph = copy.deepcopy(pack["workflows"][model["workflow"]])
    if not isinstance(graph, dict) or not graph:
        raise WorkflowError("The pack workflow is not a non-empty API-format object.")

    references = _reference_refs(source_images, source_image)

    # -- loaders -------------------------------------------------------------
    if model.get("loader") == "UnetLoaderGGUF":
        graph["1"] = {
            "class_type": "UnetLoaderGGUF",
            "_meta": {"title": "Qwen Image 2.1 Turbo diffusion model (GGUF)"},
            "inputs": {"unet_name": model["file"]},
        }
    else:
        _set(graph, "1", unet_name=model["file"], weight_dtype="default")

    if model.get("textEncoderLoader") == "CLIPLoaderGGUF":
        graph["2"] = {
            "class_type": "CLIPLoaderGGUF",
            "_meta": {"title": "Qwen3-VL text encoder (GGUF)"},
            "inputs": {"clip_name": model["textEncoder"], "type": model["clipType"]},
        }
    else:
        _set(
            graph,
            "2",
            clip_name=model["textEncoder"],
            type=model["clipType"],
            device="default",
        )
    _set(graph, "3", vae_name=model["vae"])
    _set(
        graph,
        "4",
        model=["1", 0],
        device=str(normalized.get("cacheDevice") or "auto"),
        dtype=str(normalized.get("cacheDtype") or "default"),
    )

    # -- reference images (1..3) ---------------------------------------------
    text_inputs: dict[str, Any] = {
        "clip": ["2", 0],
        "vae": ["3", 0],
        "prompt": normalized["prompt"],
        "negative_prompt": normalized["negativePrompt"],
        "resolution": int(normalized["resolution"]),
    }
    for index, (node_id, input_name) in enumerate(SOURCE_SLOTS):
        if index < len(references):
            _set(graph, node_id, image=references[index])
            text_inputs[f"images.{input_name}"] = [node_id, 0]
        else:
            _remove(graph, [node_id])
    _node(graph, "8")["inputs"] = text_inputs

    # -- sampling ------------------------------------------------------------
    steps = int(normalized["steps"])
    denoise = float(normalized["denoise"])
    sigmas = sampling_sigmas(steps, denoise)
    full = denoise >= FULL_DENOISE
    if full:
        _set(graph, "12", samples=["8", 2], amount=int(normalized["batch"]))
        _remove(graph, ["13", "14"])
        path = "full"
    else:
        _set(
            graph,
            "13",
            image=["5", 0],
            upscale_method="lanczos",
            width=int(normalized["width"]),
            height=int(normalized["height"]),
            crop="disabled",
        )
        _set(graph, "14", pixels=["13", 0], vae=["3", 0])
        _set(graph, "12", samples=["14", 0], amount=int(normalized["batch"]))
        path = "img2img"

    _set(graph, "15", sigmas=_sigma_text(sigmas))
    _set(graph, "16", sampler_name=normalized["sampler"])
    _set(
        graph,
        "9",
        model=["4", 0],
        add_noise=True,
        noise_seed=int(normalized["seed"]),
        cfg=float(normalized["cfg"]),
        positive=["8", 0],
        negative=["8", 1],
        sampler=["16", 0],
        sigmas=["15", 0],
        latent_image=["12", 0],
    )
    _set(graph, "10", samples=["9", 0], vae=["3", 0])
    _set(
        graph,
        "11",
        images=["10", 0],
        filename_prefix=f"genai_i2i/{_safe_token(job_id)}",
    )

    assert_no_switches(graph)
    _check_links(graph)

    meta = {
        "recipeId": pack["recipe"]["id"],
        "nodeCount": len(graph),
        "width": int(normalized["width"]),
        "height": int(normalized["height"]),
        "batch": int(normalized["batch"]),
        "seed": int(normalized["seed"]),
        "steps": steps,
        "effectiveSteps": len(sigmas) - 1,
        "sigmas": list(sigmas),
        "cfg": float(normalized["cfg"]),
        "denoise": denoise,
        "resolution": int(normalized["resolution"]),
        "cacheDevice": str(normalized.get("cacheDevice") or "auto"),
        "cacheDtype": str(normalized.get("cacheDtype") or "default"),
        "path": path,
        "sourceImageName": references[0],
        "sourceImages": list(references),
        "referenceCount": len(references),
        "workflow": model["workflow"],
        "sampler": normalized["sampler"],
        "scheduler": "manual",
        "schedule": f"qwen21-turbo-{len(sigmas) - 1}-step",
    }
    return graph, meta


def find_output_images(history: dict, prompt_id: str) -> list[dict]:
    entry = history.get(prompt_id) if isinstance(history, dict) else None
    outputs = (entry or {}).get("outputs") if isinstance(entry, dict) else None
    images: list[dict] = []
    for node_output in (outputs or {}).values():
        if not isinstance(node_output, dict):
            continue
        for image in node_output.get("images") or []:
            if not isinstance(image, dict) or not image.get("filename"):
                continue
            images.append(
                {
                    "filename": str(image.get("filename")),
                    "subfolder": str(image.get("subfolder") or ""),
                    "type": str(image.get("type") or "output"),
                }
            )
    return images


def history_error(history: dict, prompt_id: str) -> str:
    """Turn ComfyUI's history status messages into one readable error."""
    entry = history.get(prompt_id) if isinstance(history, dict) else None
    if not isinstance(entry, dict):
        return "ComfyUI has no history for this prompt."
    status = entry.get("status") or {}
    messages = status.get("messages") if isinstance(status, dict) else None
    for message in messages or []:
        if not isinstance(message, (list, tuple)) or len(message) < 2:
            continue
        kind, data = message[0], message[1]
        if kind != "execution_error" or not isinstance(data, dict):
            continue
        node = data.get("node_type") or data.get("node_id") or "ComfyUI"
        detail = data.get("exception_message") or data.get("exception_type") or "execution error"
        return f"{node}: {detail}"
    status_str = status.get("status_str") if isinstance(status, dict) else ""
    return f"ComfyUI generation failed ({status_str or 'error'})."


def history_completed(history: dict, prompt_id: str) -> tuple[bool, str]:
    entry = history.get(prompt_id) if isinstance(history, dict) else None
    if not isinstance(entry, dict):
        return False, ""
    status = entry.get("status") or {}
    if isinstance(status, dict):
        status_str = str(status.get("status_str") or "")
        completed = bool(status.get("completed"))
        if completed or status_str in {"success", "error"}:
            return True, status_str
    if entry.get("outputs"):
        return True, "success"
    return False, ""
