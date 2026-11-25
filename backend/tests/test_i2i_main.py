"""Focused coverage for i2i_main model resolution and graph composition.

The resolver must keep working when a file is renamed locally, so these tests
use catalog metadata (kind/architecture) exactly like a real ComfyUI scan and
never need model weights or a running ComfyUI.
"""

from __future__ import annotations

from app.GenModules.i2i_main.backend import catalog, workflows

DIFFUSION = "qwen-image-2.1-turbo-Q8_0.gguf"
ENCODER = "qwen3vl_8b_int8_convrot.safetensors"
TEXT_ONLY = "Qwen-Image-2.1-vl-Turbo-Uncensored-Q8_0.gguf"
VAE = "qwen_image_2.1_vae_bf16.safetensors"


def _entry(name: str, target: str, kind: str, arch: str | None, present: bool = True) -> dict:
    return {
        "id": f"{target}/{name}",
        "name": name,
        "target": target,
        "kind": kind,
        "architecture": arch,
        "present": present,
        "sizeBytes": 1,
    }


def _snapshot(*entries: dict) -> tuple[dict, dict]:
    pack = catalog.load_pack()
    user = {"available": True, "models": {e["id"]: e for e in entries}, "loras": {}}
    snapshot = catalog.build_snapshot(pack, user)
    return snapshot, snapshot["model"]


def _normalized(**overrides) -> dict:
    values = {
        "modelId": "qwen21-turbo-edit",
        "prompt": "put the jacket from <image2> on the model in <image1>",
        "negativePrompt": "",
        "resolution": 0,
        "batch": 1,
        "seed": 1234,
        "steps": 8,
        "cfg": 1.0,
        "sampler": "euler",
        "scheduler": "manual",
        "denoise": 1.0,
        "cacheDevice": "auto",
        "cacheDtype": "default",
        "width": 1024,
        "height": 1024,
    }
    values.update(overrides)
    return values


def test_installed_models_bind_with_their_loaders() -> None:
    snapshot, model = _snapshot(
        _entry(DIFFUSION, "unet", "image", "qwen_image"),
        _entry(ENCODER, "text_encoders", "text_encoder", "qwen3vl"),
        _entry(VAE, "vae", "vae", "qwen_image_2.1_vae"),
    )

    assert model["file"] == DIFFUSION
    assert model["loader"] == "UnetLoaderGGUF"
    assert model["textEncoder"] == ENCODER
    assert model["textEncoderLoader"] == "CLIPLoader"
    assert model["vae"] == VAE
    assert model["ready"] is True
    assert model["missing"] == []
    assert snapshot["preflight"]["errors"] == []


def test_official_encoder_wins_over_the_text_only_gguf() -> None:
    _, model = _snapshot(
        _entry(DIFFUSION, "unet", "image", "qwen_image"),
        _entry(TEXT_ONLY, "text_encoders", "text_encoder", "qwen3vl"),
        _entry(ENCODER, "text_encoders", "text_encoder", "qwen3vl"),
        _entry(VAE, "vae", "vae", "qwen_image_2.1_vae"),
    )

    assert model["textEncoder"] == ENCODER
    assert model["textEncoderLoader"] == "CLIPLoader"


def test_gguf_text_encoder_still_uses_the_gguf_loader() -> None:
    _, model = _snapshot(
        _entry(DIFFUSION, "unet", "image", "qwen_image"),
        _entry("qwen3vl_8b-Q8_0.gguf", "text_encoders", "text_encoder", "qwen3vl"),
        _entry(VAE, "vae", "vae", "qwen_image_2.1_vae"),
    )

    assert model["textEncoder"] == "qwen3vl_8b-Q8_0.gguf"
    assert model["textEncoderLoader"] == "CLIPLoaderGGUF"


def test_encoder_and_vae_fall_back_to_header_metadata_after_rename() -> None:
    snapshot, model = _snapshot(
        _entry(DIFFUSION, "unet", "image", "qwen_image"),
        _entry("my-favourite-encoder.gguf", "text_encoders", "text_encoder", "qwen3vl"),
        _entry("my-vae.safetensors", "vae", "vae", "qwen_image_2.1_vae"),
    )

    assert model["textEncoder"] == "my-favourite-encoder.gguf"
    assert model["vae"] == "my-vae.safetensors"
    assert model["ready"] is True
    assert snapshot["preflight"]["errors"] == []


def test_diffusion_alias_matches_names_with_extra_words() -> None:
    _, model = _snapshot(
        _entry("my-Qwen-Image-2.1-Turbo-edit-Q8_0.gguf", "unet", "image", "qwen_image"),
        _entry(ENCODER, "text_encoders", "text_encoder", "qwen3vl"),
        _entry(VAE, "vae", "vae", "qwen_image_2.1_vae"),
    )

    assert model["file"] == "my-Qwen-Image-2.1-Turbo-edit-Q8_0.gguf"
    assert model["loader"] == "UnetLoaderGGUF"
    assert model["ready"] is True


def test_text_encoder_never_binds_as_diffusion() -> None:
    snapshot, model = _snapshot(
        _entry(DIFFUSION, "unet", "image", "qwen_image"),
        _entry(TEXT_ONLY, "unet", "text_encoder", "qwen3vl"),
        _entry(VAE, "vae", "vae", "qwen_image_2.1_vae"),
    )

    assert model["file"] == DIFFUSION
    assert model["loader"] == "UnetLoaderGGUF"
    assert model["textEncoderLocation"] == {
        "name": TEXT_ONLY,
        "target": "unet",
        "catalogId": f"unet/{TEXT_ONLY}",
    }
    assert [issue["code"] for issue in snapshot["preflight"]["errors"]] == [
        "text_encoder_misplaced"
    ]


def test_old_qwen_image_vae_never_satisfies_2_1() -> None:
    snapshot, model = _snapshot(
        _entry(DIFFUSION, "unet", "image", "qwen_image"),
        _entry(ENCODER, "text_encoders", "text_encoder", "qwen3vl"),
        _entry("qwen_image_vae.safetensors", "vae", "vae", ""),
    )

    assert model["ready"] is False
    assert model["vae"] == VAE
    assert "qwen_image_2.1_vae_bf16.safetensors" in model["missing"]
    codes = [issue["code"] for issue in snapshot["preflight"]["warnings"]]
    assert "old_vae_not_compatible" in codes


def test_other_qwen_image_models_are_not_bound_by_architecture_alone() -> None:
    _, model = _snapshot(
        _entry("krea2_turbo-Q5_K_M.gguf", "unet", "image", "qwen_image"),
        _entry(ENCODER, "text_encoders", "text_encoder", "qwen3vl"),
        _entry(VAE, "vae", "vae", "qwen_image_2.1_vae"),
    )

    assert model["file"] == "qwen_image_2.1_turbo_bf16.safetensors"
    assert model["present"] is False


def test_compose_uses_the_official_2_1_nodes_for_both_denoise_paths() -> None:
    _, model = _snapshot(
        _entry(DIFFUSION, "unet", "image", "qwen_image"),
        _entry(ENCODER, "text_encoders", "text_encoder", "qwen3vl"),
        _entry(VAE, "vae", "vae", "qwen_image_2.1_vae"),
    )
    pack = catalog.load_pack()

    for denoise, expected_nodes, latent_source in (
        (1.0, 12, ["8", 2]),
        (0.6, 14, ["14", 0]),
    ):
        graph, meta = workflows.compose_i2i(
            pack,
            model,
            _normalized(denoise=denoise),
            source_images=["source.png"],
            job_id="test",
        )
        assert len(graph) == expected_nodes
        assert graph["1"]["class_type"] == "UnetLoaderGGUF"
        assert graph["1"]["inputs"]["unet_name"] == DIFFUSION
        assert graph["2"]["class_type"] == "CLIPLoader"
        assert graph["2"]["inputs"] == {"clip_name": ENCODER, "type": "qwen_image", "device": "default"}
        assert graph["3"]["inputs"]["vae_name"] == VAE
        assert graph["4"]["class_type"] == "QwenImage21Cache"
        assert graph["4"]["inputs"] == {"model": ["1", 0], "device": "auto", "dtype": "default"}
        assert graph["8"]["class_type"] == "TextEncodeQwenImage21"
        assert graph["8"]["inputs"]["images.image_1"] == ["5", 0]
        assert "images.image_2" not in graph["8"]["inputs"]
        assert "images.image_3" not in graph["8"]["inputs"]
        assert graph["8"]["inputs"]["negative_prompt"] == ""
        assert graph["8"]["inputs"]["resolution"] == 0
        assert graph["9"]["class_type"] == "SamplerCustom"
        assert graph["9"]["inputs"]["model"] == ["4", 0]
        assert graph["9"]["inputs"]["positive"] == ["8", 0]
        assert graph["9"]["inputs"]["negative"] == ["8", 1]
        assert graph["9"]["inputs"]["latent_image"] == ["12", 0]
        assert graph["9"]["inputs"]["sampler"] == ["16", 0]
        assert graph["9"]["inputs"]["sigmas"] == ["15", 0]
        assert graph["9"]["inputs"]["noise_seed"] == 1234
        assert graph["9"]["inputs"]["cfg"] == 1.0
        assert graph["15"]["class_type"] == "ManualSigmas"
        sigmas_text = graph["15"]["inputs"]["sigmas"]
        assert sigmas_text.endswith(", 0.0")
        assert "0.704534" in sigmas_text
        if denoise == 1.0:
            assert sigmas_text.startswith("1.0, 0.978453, 0.95418")
        else:
            assert sigmas_text.startswith("0.926626")
        assert graph["16"]["class_type"] == "KSamplerSelect"
        assert graph["16"]["inputs"]["sampler_name"] == "euler"
        assert graph["12"]["class_type"] == "RepeatLatentBatch"
        assert graph["12"]["inputs"]["samples"] == latent_source
        assert graph["12"]["inputs"]["amount"] == 1
        assert "6" not in graph and "7" not in graph
        assert "ModelSamplingAuraFlow" not in {
            node["class_type"] for node in graph.values()
        }
        assert "CLIPTextEncode" not in {node["class_type"] for node in graph.values()}
        assert "EmptyLatentImage" not in {node["class_type"] for node in graph.values()}
        assert meta["path"] == ("full" if denoise == 1.0 else "img2img")
        assert meta["referenceCount"] == 1


def test_compose_keeps_up_to_three_reference_images() -> None:
    _, model = _snapshot(
        _entry(DIFFUSION, "unet", "image", "qwen_image"),
        _entry(ENCODER, "text_encoders", "text_encoder", "qwen3vl"),
        _entry(VAE, "vae", "vae", "qwen_image_2.1_vae"),
    )
    pack = catalog.load_pack()

    graph, meta = workflows.compose_i2i(
        pack,
        model,
        _normalized(),
        source_images=["one.png", "two.png", "three.png"],
        job_id="test",
    )

    assert len(graph) == 14
    assert graph["5"]["inputs"]["image"] == "one.png"
    assert graph["6"]["inputs"]["image"] == "two.png"
    assert graph["7"]["inputs"]["image"] == "three.png"
    assert graph["8"]["inputs"]["images.image_1"] == ["5", 0]
    assert graph["8"]["inputs"]["images.image_2"] == ["6", 0]
    assert graph["8"]["inputs"]["images.image_3"] == ["7", 0]
    assert meta["referenceCount"] == 3


def test_compose_accepts_the_single_image_alias() -> None:
    _, model = _snapshot(
        _entry(DIFFUSION, "unet", "image", "qwen_image"),
        _entry(ENCODER, "text_encoders", "text_encoder", "qwen3vl"),
        _entry(VAE, "vae", "vae", "qwen_image_2.1_vae"),
    )
    pack = catalog.load_pack()

    graph, meta = workflows.compose_i2i(
        pack,
        model,
        _normalized(),
        source_image="legacy.png",
        job_id="test",
    )

    assert graph["5"]["inputs"]["image"] == "legacy.png"
    assert meta["sourceImageName"] == "legacy.png"
    assert meta["referenceCount"] == 1


def test_turbo_schedule_keeps_the_shipped_eight_step_values() -> None:
    assert workflows.turbo_schedule(8) == list(workflows.TURBO_SIGMAS)


def test_turbo_schedule_interpolates_other_step_counts() -> None:
    schedule = workflows.turbo_schedule(12)

    assert len(schedule) == 13
    assert schedule[0] == 1.0
    assert schedule[-1] == 0.0
    assert all(a > b for a, b in zip(schedule, schedule[1:]))


def test_sampling_sigmas_trims_the_same_curve_for_img2img() -> None:
    full = workflows.sampling_sigmas(8, 1.0)
    trimmed = workflows.sampling_sigmas(8, 0.6)

    assert full == list(workflows.TURBO_SIGMAS)
    assert trimmed[-1] == 0.0
    assert 1 <= len(trimmed) - 1 < len(full) - 1
    assert trimmed == full[len(full) - len(trimmed):]


def test_compose_uses_requested_steps_and_marks_the_manual_schedule() -> None:
    _, model = _snapshot(
        _entry(DIFFUSION, "unet", "image", "qwen_image"),
        _entry(ENCODER, "text_encoders", "text_encoder", "qwen3vl"),
        _entry(VAE, "vae", "vae", "qwen_image_2.1_vae"),
    )
    pack = catalog.load_pack()

    graph, meta = workflows.compose_i2i(
        pack,
        model,
        _normalized(steps=10, denoise=0.5),
        source_images=["source.png"],
        job_id="test",
    )

    assert graph["9"]["inputs"]["cfg"] == 1.0
    assert len(graph["15"]["inputs"]["sigmas"].split(",")) == 6
    assert meta["steps"] == 10
    assert meta["effectiveSteps"] == 5
    assert meta["scheduler"] == "manual"
    assert meta["schedule"] == "qwen21-turbo-5-step"

