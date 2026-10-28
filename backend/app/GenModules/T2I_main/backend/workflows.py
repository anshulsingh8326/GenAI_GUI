"""ComfyUI API-format graph composition for T2I_main.

Each pack ships its own API-format workflow. ``compose_t2i`` resolves the
selected model's ``composer`` and workflow, then delegates to that family's
small composer. The Krea 2 template is a complete Freeze-v8-style T2I graph
(base sampler, latent refine, save) plus the default five-LoRA chain. The Krea
composer rewrites only what the request changes:

- model loader / text encoder / VAE bindings
- prompt and negative prompt
- latent size, batch and sampler values
- the LoRA chain (nodes are rebuilt in request order)
- refine on/off and its dimensions
- optional 4x-UltraSharp block

No switch nodes are used. When a block is not requested its nodes are removed
and the link is rewired, which is the contract for T2I_main graphs.
"""

from __future__ import annotations

import copy
import secrets
from typing import Any


class WorkflowError(Exception):
    pass


def _round_step(value: float, step: int = 64, minimum: int = 256) -> int:
    rounded = int(round(float(value) / step) * step)
    return max(int(minimum), rounded)


def _long_side_size(base_width: int, base_height: int, long_side: int) -> tuple[int, int]:
    """Return a 64-px-aligned size whose longest side is `long_side`."""
    if base_width >= base_height:
        width = int(long_side)
        height = _round_step(long_side * base_height / max(1, base_width))
        return width, height
    height = int(long_side)
    width = _round_step(long_side * base_width / max(1, base_height))
    return width, height


def _remove(graph: dict, node_ids: list[str]) -> None:
    for node_id in node_ids:
        graph.pop(node_id, None)


def _remove_class(graph: dict, class_type: str) -> None:
    for node_id in [node_id for node_id, node in graph.items() if node.get("class_type") == class_type]:
        graph.pop(node_id, None)


def _node(graph: dict, node_id: str, class_type: str | None = None) -> dict:
    node = graph.get(node_id)
    if not isinstance(node, dict):
        raise WorkflowError(f"Workflow is missing node {node_id}.")
    if class_type is not None and node.get("class_type") != class_type:
        raise WorkflowError(
            f"Workflow node {node_id} is `{node.get('class_type')}`, expected `{class_type}`."
        )
    return node


def _set(graph: dict, node_id: str, **inputs: Any) -> None:
    node = _node(graph, node_id)
    node.setdefault("inputs", {}).update(inputs)


def assert_no_switches(graph: dict) -> None:
    for node_id, node in graph.items():
        class_type = str(node.get("class_type") or "")
        if "IAMCCS" in class_type or "Switch" in class_type:
            raise WorkflowError(f"Switch node `{class_type}` (id {node_id}) is not allowed in T2I graphs.")


def _workflow_for_model(pack: dict, model: dict) -> tuple[str, dict]:
    """Resolve a model's workflow inside its pack; never cross packs."""
    path = str(model.get("workflow") or pack.get("recipe", {}).get("workflow") or "").strip()
    if not path:
        raise WorkflowError(f"Model `{model.get('id')}` has no workflow path.")
    workflows = pack.get("workflows") or {}
    graph = workflows.get(path)
    if graph is None and path == pack.get("recipe", {}).get("workflow"):
        graph = pack.get("workflow")
    if not isinstance(graph, dict) or not graph:
        raise WorkflowError(
            f"Workflow `{path}` is not loaded for pack `{pack.get('id', '?')}`."
        )
    return path, graph


def compose_t2i(
    pack: dict,
    model: dict,
    normalized: dict,
    *,
    job_id: str = "preview",
) -> tuple[dict, dict]:
    """Dispatch to the model's composer, then build its ComfyUI API prompt."""
    composer = str(model.get("composer") or pack.get("recipe", {}).get("composer") or "krea2")
    handler = COMPOSERS.get(composer)
    if handler is None:
        raise WorkflowError(
            f"No composer registered for `{composer}` (model `{model.get('id')}`). "
            f"Known composers: {', '.join(sorted(COMPOSERS))}."
        )
    path, workflow = _workflow_for_model(pack, model)
    graph, meta = handler(copy.deepcopy(workflow), pack, model, normalized, job_id=job_id)
    meta["packId"] = pack.get("id")
    meta["composer"] = composer
    meta["workflow"] = path
    return graph, meta


def _compose_krea2(
    graph: dict,
    pack: dict,
    model: dict,
    normalized: dict,
    *,
    job_id: str = "preview",
) -> tuple[dict, dict]:
    """Build a Krea 2 graph from the pack's already-validated API template."""
    options = pack["options"]
    if model["loader"] not in {"UNETLoader", "UnetLoaderGGUF"}:
        raise WorkflowError(
            f"Krea 2 composer cannot load `{model['loader']}` (model `{model['id']}`)."
        )

    # -- loaders ------------------------------------------------------------
    loader = _node(graph, "1")
    if model["loader"] == "UnetLoaderGGUF":
        loader["class_type"] = "UnetLoaderGGUF"
        loader["inputs"] = {"unet_name": model["file"]}
    else:
        loader["class_type"] = "UNETLoader"
        loader["inputs"] = {
            "unet_name": model["file"],
            "weight_dtype": model.get("weightDtype") or "default",
        }
    _set(graph, "2", clip_name=model["textEncoder"], type=model["clipType"], device="default")
    _set(graph, "3", vae_name=model["vae"])

    # -- prompts / latent ---------------------------------------------------
    prompt_used = normalized["promptUsed"]
    _set(graph, "4", text=prompt_used)
    _set(graph, "5", text=normalized["negativePrompt"])
    _set(graph, "6", width=normalized["width"], height=normalized["height"], batch_size=normalized["batch"])

    # -- LoRA chain ---------------------------------------------------------
    _remove_class(graph, "LoraLoaderModelOnly")
    previous: list[Any] = ["1", 0]
    chain_meta: list[dict] = []
    for index, lora in enumerate(normalized["loras"], start=1):
        node_id = f"lora_{index}"
        graph[node_id] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": previous,
                "lora_name": lora["file"],
                "strength_model": float(lora["strength"]),
            },
            "_meta": {"title": f"LoRA {index} - {lora['label']} {lora['strength']}"},
        }
        previous = [node_id, 0]
        chain_meta.append(
            {
                "id": lora["id"],
                "label": lora["label"],
                "file": lora["file"],
                "strength": float(lora["strength"]),
                "triggers": lora.get("triggers") or [],
            }
        )
    final_model = previous

    # -- base sampler -------------------------------------------------------
    base_seed = int(normalized["seed"])
    _set(
        graph,
        "7",
        model=final_model,
        positive=["4", 0],
        negative=["5", 0],
        latent_image=["6", 0],
        seed=base_seed,
        steps=int(normalized["steps"]),
        cfg=float(normalized["cfg"]),
        sampler_name=normalized["sampler"],
        scheduler=normalized["scheduler"],
        denoise=float(normalized["denoise"]),
    )

    # -- latent refine ------------------------------------------------------
    upscaler = normalized["upscaler"]
    refine_enabled = bool(upscaler.get("enabled")) and upscaler.get("kind") == "latent"
    refine_seed = None
    refine_width = None
    refine_height = None
    if refine_enabled:
        refine_seed = (base_seed + 1) & 0xFFFFFFFF
        refine_width, refine_height = _long_side_size(
            normalized["width"], normalized["height"], int(upscaler["value"])
        )
        _set(
            graph,
            "8",
            samples=["7", 0],
            upscale_method="nearest-exact",
            width=refine_width,
            height=refine_height,
            crop="disabled",
        )
        _set(
            graph,
            "9",
            model=final_model,
            positive=["4", 0],
            negative=["5", 0],
            latent_image=["8", 0],
            seed=refine_seed,
            steps=int(normalized["refineSteps"]),
            cfg=float(normalized["refineCfg"]),
            sampler_name=normalized["sampler"],
            scheduler=normalized["scheduler"],
            denoise=float(normalized["refineDenoise"]),
        )
        decode_input: list[Any] = ["9", 0]
    else:
        _remove(graph, ["8", "9"])
        decode_input = ["7", 0]

    _set(graph, "10", samples=decode_input, vae=["3", 0])

    # -- optional ESRGAN ----------------------------------------------------
    # The final saved size is the refined latent when the refine pass ran,
    # otherwise the base latent; ESRGAN then replaces it with its target size.
    if refine_enabled and refine_width and refine_height:
        output_width, output_height = refine_width, refine_height
    else:
        output_width, output_height = normalized["width"], normalized["height"]
    esrgan_enabled = bool(upscaler.get("enabled")) and upscaler.get("kind") == "esrgan"
    if esrgan_enabled:
        output_width, output_height = _long_side_size(
            normalized["width"], normalized["height"], int(upscaler["value"])
        )
        graph["upscale_model"] = {
            "class_type": "UpscaleModelLoader",
            "inputs": {"model_name": upscaler["file"]},
            "_meta": {"title": f"Upscale model - {upscaler['label']}"},
        }
        graph["upscale_image"] = {
            "class_type": "ImageUpscaleWithModel",
            "inputs": {"upscale_model": ["upscale_model", 0], "image": ["10", 0]},
            "_meta": {"title": "4x-UltraSharp"},
        }
        graph["upscale_scale"] = {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["upscale_image", 0],
                "upscale_method": "lanczos",
                "width": output_width,
                "height": output_height,
                "crop": "disabled",
            },
            "_meta": {"title": f"Downscale to {output_width}x{output_height}"},
        }
        save_input: list[Any] = ["upscale_scale", 0]
    else:
        save_input = ["10", 0]

    safe_job = "".join(ch for ch in str(job_id) if ch.isalnum() or ch in {"-", "_"}) or "preview"
    _set(graph, "11", images=save_input, filename_prefix=f"T2I_main/{safe_job}")

    assert_no_switches(graph)
    meta = {
        "recipeId": pack["recipe"]["id"],
        "modelId": model["id"],
        "modelLoader": model["loader"],
        "promptUsed": prompt_used,
        "negativePrompt": normalized["negativePrompt"],
        "seed": base_seed,
        "width": normalized["width"],
        "height": normalized["height"],
        "batch": normalized["batch"],
        "steps": int(normalized["steps"]),
        "cfg": float(normalized["cfg"]),
        "sampler": normalized["sampler"],
        "scheduler": normalized["scheduler"],
        "denoise": float(normalized["denoise"]),
        "loras": chain_meta,
        "refine": {
            "enabled": refine_enabled,
            "steps": int(normalized["refineSteps"]),
            "cfg": float(normalized["refineCfg"]),
            "denoise": float(normalized["refineDenoise"]),
            "seed": refine_seed,
            "width": refine_width,
            "height": refine_height,
        },
        "upscaler": {
            "id": upscaler.get("id"),
            "kind": upscaler.get("kind"),
            "enabled": bool(upscaler.get("enabled")),
            "value": upscaler.get("value"),
            "outputWidth": output_width,
            "outputHeight": output_height,
        },
        "nodeCount": len(graph),
        "finalNode": "11",
        "samplers": {
            "base": normalized["sampler"],
            "scheduler": normalized["scheduler"],
        },
        "options": {
            "samplerIds": [item["id"] for item in options["samplers"]],
            "schedulerIds": [item["id"] for item in options["schedulers"]],
        },
    }
    return graph, meta


# One small dispatch table, one composer per family. A new family adds a
# composer and its own API graph; it does not add branches to _compose_krea2.
COMPOSERS = {
    "krea2": _compose_krea2,
}


def compose_enhance(
    pack: dict,
    text_model: dict,
    prompt: str,
    *,
    system_prompt: str = "",
    seed: int | None = None,
    max_length: int | None = None,
    temperature: float | None = None,
) -> dict:
    """Build the ComfyUI prompt-enhancement graph (CLIPLoader -> TextGenerate -> DisplayAny)."""
    config = pack["options"]["enhance"]["comfyui"]
    full_prompt = prompt.strip()
    if system_prompt.strip():
        full_prompt = f"{system_prompt.strip()}\n\nUser idea: {full_prompt}"
    sampling_seed = int(seed if seed is not None else secrets.randbelow(2**32))
    graph = {
        "1": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": text_model["file"],
                "type": text_model["clipType"],
                "device": "default",
            },
            "_meta": {"title": text_model["label"]},
        },
        "2": {
            "class_type": "TextGenerate",
            "inputs": {
                "clip": ["1", 0],
                "prompt": full_prompt,
                "max_length": int(max_length or text_model.get("maxLength") or config["maxLength"]),
                "sampling_mode": "on",
                "sampling_mode.temperature": float(temperature) if temperature is not None else config["temperature"],
                "sampling_mode.top_k": config["topK"],
                "sampling_mode.top_p": config["topP"],
                "sampling_mode.min_p": config["minP"],
                "sampling_mode.repetition_penalty": config["repetitionPenalty"],
                "sampling_mode.seed": sampling_seed,
                "sampling_mode.presence_penalty": config["presencePenalty"],
                "thinking": False,
                "use_default_template": True,
            },
            "_meta": {"title": "Generate enhanced prompt"},
        },
        "3": {
            "class_type": "RgthreeDisplayAny",
            "inputs": {"source": ["2", 0]},
            "_meta": {"title": "Return generated text"},
        },
    }
    assert_no_switches(graph)
    return graph


def extract_enhance_text(history: dict, prompt_id: str, node_id: str = "3") -> str:
    entry = history.get(prompt_id) if isinstance(history, dict) else None
    if not isinstance(entry, dict):
        raise WorkflowError("ComfyUI history has no entry for the enhancement prompt.")
    outputs = entry.get("outputs") or {}
    node_output = outputs.get(node_id) or {}
    text_value = node_output.get("text")
    if isinstance(text_value, (list, tuple)) and text_value:
        text_value = text_value[0]
    if isinstance(text_value, str):
        text = text_value.strip()
        if text:
            return text
    # Some DisplayAny versions / wrappers use a different node id. Accept any
    # non-empty `text` output as a fallback, but never an image output.
    for value in outputs.values():
        if not isinstance(value, dict):
            continue
        candidate = value.get("text")
        if isinstance(candidate, (list, tuple)) and candidate:
            candidate = candidate[0]
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    raise WorkflowError("ComfyUI finished the enhancement graph but returned no text.")


def find_output_images(history: dict, prompt_id: str) -> list[dict]:
    entry = history.get(prompt_id) if isinstance(history, dict) else None
    if not isinstance(entry, dict):
        return []
    images: list[dict] = []
    for node_output in (entry.get("outputs") or {}).values():
        if not isinstance(node_output, dict):
            continue
        for image in node_output.get("images") or []:
            if not isinstance(image, dict) or not image.get("filename"):
                continue
            if str(image.get("type") or "output") != "output":
                continue
            images.append(
                {
                    "filename": str(image["filename"]),
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
    # Older ComfyUI versions expose only outputs; outputs existing means done.
    if entry.get("outputs"):
        return True, "success"
    return False, ""
