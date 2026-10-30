"""Focused coverage for T2I_main: pack defaults, ranges, graph composition and
the HTTP error contract.

These tests deliberately do not require ComfyUI or Ollama. The runner test uses
an offline fake client, so it verifies the persisted error stage without a GPU.
"""

from __future__ import annotations

import asyncio
import json
import shutil

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.jobs import service as jobs
from app.GenModules.T2I_main.backend import catalog, service, workflows
from app.GenModules.T2I_main.backend.schema import T2IEnhanceRequest, T2IJobRequest
from app.library import placeholders, service as library
from app.common import settings_store
from app.common.model_aliases import best_alias_match, normalize_token
from app.engine_content import service as engine_service

client = TestClient(app)


def _default_chain() -> list[dict]:
    pack = catalog.load_pack()
    return [
        {"id": ref["id"], "strength": ref["strength"], "on": True}
        for ref in pack["options"]["defaults"]["loraChain"]
    ]


def _freeze_request(**overrides) -> T2IJobRequest:
    body = {
        "prompt": "a portrait of a woman in a rainy city at night",
        "modelId": "krea2-turbo-int8",
        "ratio": "1:1",
        "size": 1024,
        "batch": 1,
        "loras": _default_chain(),
        "enhance": {"enabled": False},
    }
    body.update(overrides)
    return T2IJobRequest.model_validate(body)


def test_pack_keeps_freeze_v8_values() -> None:
    pack = catalog.load_pack()
    model = pack["models"]["krea2-turbo-int8"]

    assert model["defaults"] == {
        "steps": 12,
        "cfg": 2.5,
        "sampler": "euler",
        "scheduler": "simple",
        "denoise": 1.0,
    }
    refine = model["ranges"]["refine"]
    assert refine["steps"]["default"] == 6
    assert refine["cfg"]["default"] == 2.0
    assert refine["denoise"]["default"] == 0.45
    assert refine["scale"]["default"] == 1536
    assert pack["options"]["defaults"]["upscaler"] == {
        "id": "latent-refine",
        "enabled": True,
        "value": 1536,
    }
    assert [ref["id"] for ref in pack["options"]["defaults"]["loraChain"]] == [
        "lora-xcreampiex-krea2-v1-1-000002500",
        "lora-krea2-g4ngb4ng-v1",
        "lora-mysticxxx-krea2-v3",
        "lora-krea-2-mombod-epoch-7",
        "lora-realism-engine-krea2-v3-1",
    ]
    workflows.assert_no_switches(pack["workflow"])


def test_pack_registry_resolves_models_to_their_pack() -> None:
    packs = catalog.load_packs()
    assert set(packs) == {"krea2"}
    pack = catalog.load_pack()
    assert pack["id"] == "krea2"
    assert pack["default"] is True
    assert pack["recipe"]["composer"] == "krea2"
    assert set(pack["workflows"]) == {"workflows/krea2_t2i.api.json"}

    model = pack["models"]["krea2-turbo-int8"]
    assert model["packId"] == "krea2"
    assert model["composer"] == "krea2"
    assert model["workflow"] == "workflows/krea2_t2i.api.json"
    assert catalog.pack_for_model("krea2-turbo-q5")["id"] == "krea2"
    assert catalog.pack_for_model("not-a-model") is None


def test_registry_can_load_two_packs_without_model_collisions(tmp_path, monkeypatch) -> None:
    source = catalog.PACK_DIR / "packs" / "krea2"
    root = tmp_path / "pack"
    shutil.copytree(source, root / "packs" / "krea2")
    shutil.copytree(source, root / "packs" / "alt")

    options_path = root / "packs" / "alt" / "options.json"
    options = json.loads(options_path.read_text(encoding="utf-8"))
    options["recipe"]["id"] = "alt-t2i-v1"
    options["recipe"]["label"] = "Alt family"
    options["defaults"]["modelId"] = "alt-int8"
    options_path.write_text(json.dumps(options, indent=2), encoding="utf-8")

    models_path = root / "packs" / "alt" / "models.json"
    models = json.loads(models_path.read_text(encoding="utf-8"))
    models["models"] = [models["models"][0]]
    models["models"][0]["id"] = "alt-int8"
    models["models"][0]["label"] = "Alt int8"
    models["models"][0]["shortLabel"] = "Alt"
    models_path.write_text(json.dumps(models, indent=2), encoding="utf-8")

    registry = {
        "version": 1,
        "defaultPack": "krea2",
        "packs": [
            {"id": "krea2", "label": "Krea 2", "path": "packs/krea2"},
            {"id": "alt", "label": "Alt", "path": "packs/alt"},
        ],
    }
    (root / "registry.json").write_text(json.dumps(registry, indent=2), encoding="utf-8")
    monkeypatch.setattr(catalog, "PACK_DIR", root)
    monkeypatch.setattr(catalog, "REGISTRY_FILE", root / "registry.json")

    packs = catalog.load_packs()
    assert set(packs) == {"krea2", "alt"}
    assert packs["krea2"]["default"] is True
    assert packs["alt"]["default"] is False
    assert packs["alt"]["models"]["alt-int8"]["packId"] == "alt"
    assert catalog.load_pack("alt")["recipe"]["id"] == "alt-t2i-v1"
    assert catalog.pack_for_model("alt-int8")["id"] == "alt"
    assert catalog.pack_for_model("krea2-turbo-int8")["id"] == "krea2"


def test_composer_dispatch_is_model_scoped(monkeypatch) -> None:
    pack = catalog.load_pack()
    normalized = service._normalize_request(_freeze_request(loras=[]), pack)
    seen: dict = {}

    def fake_composer(graph, pack_arg, model, normalized_arg, *, job_id="preview"):
        seen["graph"] = graph
        seen["pack"] = pack_arg["id"]
        seen["model"] = model["id"]
        seen["job_id"] = job_id
        return {"fake": True}, {"recipeId": pack_arg["recipe"]["id"]}

    monkeypatch.setitem(workflows.COMPOSERS, "fake", fake_composer)
    model = {**normalized["model"], "composer": "fake"}
    graph, meta = workflows.compose_t2i(pack, model, normalized, job_id="#dispatch")

    assert graph == {"fake": True}
    assert seen == {
        "graph": pack["workflow"],
        "pack": "krea2",
        "model": "krea2-turbo-int8",
        "job_id": "#dispatch",
    }
    assert meta["packId"] == "krea2"
    assert meta["composer"] == "fake"
    assert meta["workflow"] == "workflows/krea2_t2i.api.json"


def test_snapshot_exposes_pack_identity() -> None:
    snapshot = catalog.build_snapshot(catalog.load_pack())
    assert snapshot["pack"]["id"] == "krea2"
    assert snapshot["pack"]["label"] == "Krea 2"
    assert snapshot["pack"]["description"]
    assert snapshot["pack"]["nsfw"] is True
    model = next(item for item in snapshot["models"] if item["id"] == "krea2-turbo-int8")
    assert model["packId"] == "krea2"
    assert model["composer"] == "krea2"
    assert model["label"] == "SNOFS_Krea2"


def test_krea2_labels_and_wide_ratio_fit_band() -> None:
    pack = catalog.load_pack()

    assert pack["models"]["krea2-turbo-int8"]["shortLabel"] == "SNOFS_Krea2"
    assert pack["models"]["krea2-turbo-q5"]["shortLabel"] == "Krea2 Turbo Q5_K_M"
    assert pack["models"]["krea2-turbo-q5"]["tested"] is True
    assert pack["models"]["krea2-turbo-int8"]["nsfw"] is True
    assert pack["models"]["krea2-turbo-q5"]["nsfw"] is False
    assert pack["loras"]["lora-realism-engine-krea2-v3-1"]["nsfw"] is True
    assert [item["label"] for item in pack["options"]["ratios"]] == [
        "1:1 - Square",
        "4:5 - Portrait",
        "3:4 - Portrait",
        "2:3 - Portrait",
        "9:16 - Portrait",
        "5:4 - Landscape",
        "4:3 - Landscape",
        "3:2 - Landscape",
        "16:9 - Widescreen",
    ]
    for model_id in ("krea2-turbo-int8", "krea2-turbo-q5"):
        width = pack["models"][model_id]["ranges"]["width"]
        height = pack["models"][model_id]["ranges"]["height"]
        assert (width["recommendedMin"], width["recommendedMax"]) == (640, 1536)
        assert (height["recommendedMin"], height["recommendedMax"]) == (640, 1536)

    result = service.validate_payload(_freeze_request(ratio="16:9", size=1152))
    normalized = result["normalized"]
    assert (normalized["width"], normalized["height"]) == (1152, 640)
    assert not [
        warning for warning in result["warnings"] if warning.get("field") in {"width", "height"}
    ]

    manual = service.validate_payload(_freeze_request(ratio="16:9", size=1024))
    manual_codes = {
        warning["code"]
        for warning in manual["warnings"]
        if warning.get("field") in {"width", "height"}
    }
    assert "outside_recommended" in manual_codes
    assert "normalized_step" not in manual_codes

    explicit = service.validate_payload(
        _freeze_request(ratio=None, size=None, width=1280, height=720)
    )
    explicit_codes = {
        warning["code"]
        for warning in explicit["warnings"]
        if warning.get("field") in {"width", "height"}
    }
    assert "outside_recommended" not in explicit_codes
    assert "normalized_step" in explicit_codes


def test_default_validation_and_graph_summary() -> None:
    result = service.validate_payload(_freeze_request())

    assert result["valid"] is True
    normalized = result["normalized"]
    assert (normalized["width"], normalized["height"]) == (1024, 1024)
    assert len(normalized["loras"]) == 5
    assert normalized["promptUsed"].startswith("creampie, G4NGB4NG")
    assert normalized["refine"]["on"] is True
    assert normalized["refine"]["scale"] == 1536
    assert result["graph"]["nodeCount"] == 16
    assert (result["graph"]["finalWidth"], result["graph"]["finalHeight"]) == (1536, 1536)


def test_graph_contains_lora_chain_and_refine() -> None:
    pack = catalog.load_pack()
    normalized = service._normalize_request(_freeze_request(), pack)
    graph, meta = workflows.compose_t2i(pack, normalized["model"], normalized, job_id="#test")

    workflows.assert_no_switches(graph)
    assert graph["lora_1"]["inputs"]["model"] == ["1", 0]
    assert graph["lora_5"]["inputs"]["model"] == ["lora_4", 0]
    assert graph["lora_1"]["inputs"]["lora_name"] == "xCreampiex_krea2_v1.1_000002500.safetensors"
    assert graph["8"]["class_type"] == "LatentUpscale"
    assert graph["9"]["class_type"] == "KSampler"
    assert graph["9"]["inputs"]["denoise"] == 0.45
    assert meta["refine"]["enabled"] is True
    assert (meta["upscaler"]["outputWidth"], meta["upscaler"]["outputHeight"]) == (1536, 1536)
    assert graph["11"]["inputs"]["filename_prefix"] == "T2I_main/test"


def test_esrgan_is_an_alternative_to_refine() -> None:
    pack = catalog.load_pack()
    request = _freeze_request(
        loras=[],
        advanced={
            "upscaler": {"id": "4x-ultrasharp", "enabled": True, "value": 2048},
        },
    )
    normalized = service._normalize_request(request, pack)
    graph, meta = workflows.compose_t2i(pack, normalized["model"], normalized)

    assert "upscale_model" in graph
    assert "8" not in graph and "9" not in graph
    assert meta["refine"]["enabled"] is False
    assert (meta["upscaler"]["outputWidth"], meta["upscaler"]["outputHeight"]) == (2048, 2048)


def test_no_upscale_prunes_both_blocks() -> None:
    pack = catalog.load_pack()
    request = _freeze_request(
        loras=[],
        advanced={"upscaler": {"id": "none", "enabled": False}},
    )
    normalized = service._normalize_request(request, pack)
    graph, meta = workflows.compose_t2i(pack, normalized["model"], normalized)

    assert "8" not in graph and "9" not in graph
    assert "upscale_model" not in graph
    assert meta["refine"]["enabled"] is False
    assert (meta["upscaler"]["outputWidth"], meta["upscaler"]["outputHeight"]) == (1024, 1024)


def test_enhance_graph_and_embedding_filter() -> None:
    pack = catalog.load_pack()
    text_model = pack["comfyTextModels"]["qwen3vl-4b-comfy"]
    graph = workflows.compose_enhance(
        pack,
        text_model,
        "a rainy street",
        system_prompt="be vivid",
        max_length=128,
    )

    workflows.assert_no_switches(graph)
    assert graph["1"]["class_type"] == "CLIPLoader"
    assert graph["2"]["class_type"] == "TextGenerate"
    assert graph["2"]["inputs"]["max_length"] == 128
    assert graph["3"]["class_type"] == "RgthreeDisplayAny"
    assert service._is_ollama_text_model("huihui_ai/gemma-4-abliterated:12b-qat") is True
    assert service._is_ollama_text_model("embeddinggemma-2:740m") is False


def test_enhancement_accepts_a_custom_system_prompt_and_falls_back() -> None:
    pack = catalog.load_pack()
    settings, _ = settings_store.load()
    custom = service._resolve_enhance(
        _freeze_request(
            enhance={"enabled": True, "systemPrompt": "Build intent, character and scenery cards."}
        ),
        pack,
        settings,
        [],
        [],
    )
    assert custom["systemPrompt"] == "Build intent, character and scenery cards."

    fallback = service._resolve_enhance(
        _freeze_request(enhance={"enabled": True}),
        pack,
        settings,
        [],
        [],
    )
    assert fallback["systemPrompt"] == settings["prompts"]["enhance"]


def test_enhancement_unload_defaults_on_and_can_be_disabled() -> None:
    pack = catalog.load_pack()
    settings, _ = settings_store.load()

    enabled = service._resolve_enhance(
        _freeze_request(enhance={"enabled": True}),
        pack,
        settings,
        [],
        [],
    )
    disabled = service._resolve_enhance(
        _freeze_request(enhance={"enabled": True, "unloadAfter": False}),
        pack,
        settings,
        [],
        [],
    )

    assert enabled["unloadAfter"] is True
    assert disabled["unloadAfter"] is False


def test_enhance_preview_unloads_ollama_text_model(monkeypatch: pytest.MonkeyPatch) -> None:
    unloaded: list[str] = []
    generate_kwargs: list[dict] = []

    class FakeOllama:
        async def generate(self, model: str, prompt: str, **kwargs) -> dict:
            generate_kwargs.append(kwargs)
            return {"response": "rewritten prompt"}

    async def fake_status() -> dict:
        return {
            "connected": True,
            "url": "http://127.0.0.1:11434",
            "installed": [{"name": "test-chat:latest"}],
        }

    async def fake_unload(model: str) -> dict:
        unloaded.append(model)
        return {"ok": True, "message": f"{model} unloaded from memory"}

    monkeypatch.setattr(service.connectors, "ollama_status", fake_status)
    monkeypatch.setattr(service.connectors, "ollama_client", lambda: FakeOllama())
    monkeypatch.setattr(service.connectors, "unload_ollama", fake_unload)

    on = asyncio.run(
        service.enhance_prompt(
            T2IEnhanceRequest(
                prompt="a cat",
                provider="ollama",
                model="test-chat:latest",
                unloadAfter=True,
            )
        )
    )
    assert on["prompt"] == "rewritten prompt"
    assert on["unloaded"] is True
    assert on["unloadError"] is None
    assert unloaded == ["test-chat:latest"]
    assert generate_kwargs[0]["think"] is False

    off = asyncio.run(
        service.enhance_prompt(
            T2IEnhanceRequest(
                prompt="a cat",
                provider="ollama",
                model="test-chat:latest",
                unloadAfter=False,
            )
        )
    )
    assert off["prompt"] == "rewritten prompt"
    assert off["unloaded"] is False
    assert unloaded == ["test-chat:latest"]


def test_enhance_preview_unload_failure_is_non_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeOllama:
        async def generate(self, model: str, prompt: str, **kwargs) -> dict:
            return {"response": "rewritten prompt"}

    async def fake_status() -> dict:
        return {
            "connected": True,
            "url": "http://127.0.0.1:11434",
            "installed": [{"name": "test-chat:latest"}],
        }

    async def failing_unload(model: str) -> dict:
        return {"ok": False, "message": "Could not read loaded models: offline"}

    monkeypatch.setattr(service.connectors, "ollama_status", fake_status)
    monkeypatch.setattr(service.connectors, "ollama_client", lambda: FakeOllama())
    monkeypatch.setattr(service.connectors, "unload_ollama", failing_unload)

    result = asyncio.run(
        service.enhance_prompt(
            T2IEnhanceRequest(
                prompt="a cat",
                provider="ollama",
                model="test-chat:latest",
                unloadAfter=True,
            )
        )
    )

    assert result["prompt"] == "rewritten prompt"
    assert result["unloaded"] is False
    assert "offline" in result["unloadError"]


def test_unsafe_range_is_rejected_by_the_module() -> None:
    with pytest.raises(service.ValidationError) as info:
        service.validate_payload(_freeze_request(advanced={"steps": 50}))

    issue = info.value.errors[0]
    assert issue["code"] == "out_of_safe_range"
    assert issue["field"] == "advanced.steps"


def test_http_error_contract() -> None:
    pack = client.get("/api/t2i/pack")
    assert pack.status_code == 200
    assert pack.json()["workflow"]["format"] == "comfyui-api"

    unknown = client.get("/api/t2i/catalog?modelId=nope")
    assert unknown.status_code == 422
    detail = unknown.json()["detail"]
    assert detail["code"] == "validation_error"
    assert detail["errors"][0]["code"] == "unknown_model"

    invalid = client.post(
        "/api/t2i/validate",
        json={
            "prompt": "x",
            "modelId": "krea2-turbo-int8",
            "advanced": {"steps": 50},
        },
    )
    assert invalid.status_code == 422
    detail = invalid.json()["detail"]
    assert detail["code"] == "validation_error"
    assert detail["errors"][0]["code"] == "out_of_safe_range"

    invalid_job = client.post(
        "/api/t2i/jobs",
        json={
            "prompt": "x",
            "modelId": "krea2-turbo-int8",
            "advanced": {"steps": 50},
        },
    )
    assert invalid_job.status_code == 422
    assert invalid_job.json()["detail"]["errors"][0]["field"] == "advanced.steps"

    missing = client.get("/api/t2i/jobs/%23missing")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Job not found"


def test_t2i_job_access_is_module_scoped() -> None:
    foreign = jobs.create_job(
        {
            "tab": "text-to-image",
            "module": "other_module",
            "prompt": "not a T2I_main job",
        }
    )
    assert service.get_job(foreign["id"]) is None
    assert foreign["id"] not in {job["id"] for job in service.list_jobs(200)}
    assert asyncio.run(service.cancel_job(foreign["id"])) is None


def test_runner_persists_a_readable_offline_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class OfflineClient:
        base_url = "http://127.0.0.1:8188"

        async def submit_prompt(self, graph: dict, client_id: str = "") -> dict:
            raise httpx.ConnectError("offline")

        async def queue(self) -> dict:
            return {"queue_running": [], "queue_pending": []}

    monkeypatch.setattr(service.connectors, "comfy_client", lambda: OfflineClient())
    request = _freeze_request(loras=[], enhance={"enabled": False})

    async def scenario() -> dict:
        job = await service.start_job(request)
        current = job
        for _ in range(100):
            await asyncio.sleep(0.01)
            current = service.get_job(job["id"]) or job
            if current["status"] in {"done", "error"}:
                return current
        return current

    job = asyncio.run(scenario())
    assert job["status"] == "error"
    assert job["module"] == "T2I_main"
    assert "ComfyUI is not reachable at http://127.0.0.1:8188" in job["error"]
    submit = next(stage for stage in job["stages"] if stage["id"] == "submit")
    assert submit["status"] == "error"
    assert "ComfyUI is not reachable" in submit["detail"]


def test_runner_passes_unload_preference_and_surfaces_unload_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {"unloadAfter": None, "submitted": False}

    class RecordingOfflineClient:
        base_url = "http://127.0.0.1:8188"

        async def submit_prompt(self, graph: dict, client_id: str = "") -> dict:
            seen["submitted"] = True
            raise httpx.ConnectError("offline")

        async def queue(self) -> dict:
            return {"queue_running": [], "queue_pending": []}

    async def fake_enhance(payload: T2IEnhanceRequest) -> dict:
        seen["unloadAfter"] = payload.unloadAfter
        return {
            "prompt": "rewritten prompt",
            "originalPrompt": payload.prompt,
            "provider": "ollama",
            "model": "test-chat:latest",
            "durationMs": 12,
            "unloaded": False,
            "unloadError": "Could not read loaded models: offline",
        }

    monkeypatch.setattr(service, "enhance_prompt", fake_enhance)
    monkeypatch.setattr(service.connectors, "comfy_client", lambda: RecordingOfflineClient())
    request = _freeze_request(
        loras=[],
        enhance={
            "enabled": True,
            "provider": "ollama",
            "model": "test-chat:latest",
            "unloadAfter": True,
        },
    )

    async def scenario() -> dict:
        job = await service.start_job(request)
        current = job
        for _ in range(100):
            await asyncio.sleep(0.01)
            current = service.get_job(job["id"]) or job
            if current["status"] in {"done", "error"}:
                return current
        return current

    job = asyncio.run(scenario())

    assert seen["unloadAfter"] is True
    assert seen["submitted"] is True
    assert job["status"] == "error"
    assert job["params"]["enhance"]["mode"] == "applied"
    assert any(
        warning["code"] == "enhance_unload_failed"
        for warning in job["params"]["warnings"]
    )
    enhance_stage = next(stage for stage in job["stages"] if stage["id"] == "enhance")
    assert "unload failed" in enhance_stage["detail"]


def _completed_t2i_job_with_asset(name: str) -> tuple[dict, dict]:
    data = placeholders.make_placeholder_png(f"delete-{name}", 0, 64, 64)
    asset = library.add_bytes(
        data,
        f"delete-{name}.png",
        label=name,
        prompt=name,
        tags=["test"],
        origin_job="pending",
    )
    job = jobs.create_job(
        {
            "tab": "text-to-image",
            "module": "T2I_main",
            "prompt": name,
            "modelId": "krea2-turbo-int8",
            "modelName": "Krea 2 Turbo",
            "seed": 42,
            "params": {},
            "stages": [],
        }
    )
    jobs.update_job(
        job["id"],
        {"status": "done", "progress": 100, "resultIds": [asset["id"]]},
    )
    return service.get_job(job["id"]), asset


def test_delete_job_moves_assets_to_trash_and_soft_deletes() -> None:
    job, asset = _completed_t2i_job_with_asset("with-assets")
    assert job is not None

    result = service.delete_job(job["id"], delete_assets=True)

    assert result is not None
    assert result["deleted"] is True
    assert result["assetsTrashed"] == [asset["id"]]
    assert service.get_job(job["id"]) is None
    assert library.get_asset(asset["id"]) is None
    # Audit record stays in SQLite, hidden from normal reads.
    hidden = jobs.get_job(job["id"], include_deleted=True)
    assert hidden is not None and hidden["status"] == "done"


def test_delete_job_can_keep_assets_and_http_contract() -> None:
    job, asset = _completed_t2i_job_with_asset("keep-assets")
    assert job is not None

    response = client.delete(
        f"/api/t2i/jobs/{job['id'].replace('#', '%23')}?deleteAssets=false"
    )

    assert response.status_code == 200
    assert response.json()["assetsTrashed"] == []
    assert service.get_job(job["id"]) is None
    assert library.get_asset(asset["id"]) is not None
    assert client.get(f"/api/t2i/jobs/{job['id'].replace('#', '%23')}").status_code == 404


def test_delete_running_job_is_rejected() -> None:
    running = jobs.create_job(
        {
            "tab": "text-to-image",
            "module": "T2I_main",
            "prompt": "still running",
            "params": {},
            "stages": [],
        }
    )
    with pytest.raises(service.ValidationError) as info:
        service.delete_job(running["id"], delete_assets=False)
    assert info.value.errors[0]["code"] == "job_running"
    jobs.delete_job(running["id"])


def test_clear_history_can_keep_assets_and_ignores_other_modules() -> None:
    job, asset = _completed_t2i_job_with_asset("clear-keep")
    foreign = jobs.create_job(
        {
            "tab": "text-to-image",
            "module": "other_module",
            "prompt": "keep me",
            "params": {},
            "stages": [],
        }
    )
    try:
        result = service.clear_history(delete_assets=False)
        assert job["id"] in result["jobIds"]
        assert result["assetsTrashed"] == []
        assert service.get_job(job["id"]) is None
        assert library.get_asset(asset["id"]) is not None
        assert jobs.get_job(foreign["id"]) is not None
    finally:
        jobs.delete_job(foreign["id"])


def test_clear_history_http_moves_assets_to_trash() -> None:
    job, asset = _completed_t2i_job_with_asset("clear-trash")

    response = client.delete("/api/t2i/jobs?deleteAssets=true")

    assert response.status_code == 200
    payload = response.json()
    assert job["id"] in payload["jobIds"]
    assert asset["id"] in payload["assetsTrashed"]
    assert service.get_job(job["id"]) is None
    assert library.get_asset(asset["id"]) is None


def test_clear_history_rejects_an_active_generation() -> None:
    running = jobs.create_job(
        {
            "tab": "text-to-image",
            "module": "T2I_main",
            "prompt": "still running",
            "params": {},
            "stages": [],
        }
    )
    try:
        with pytest.raises(service.ValidationError) as info:
            service.clear_history(delete_assets=False)
    finally:
        jobs.delete_job(running["id"])
    assert info.value.errors[0]["code"] == "job_running"
    assert running["id"] in info.value.errors[0]["jobIds"]


def _catalog_entry(
    entry_id: str,
    name: str,
    target: str,
    *,
    present: bool = True,
    triggers: list[str] | None = None,
) -> dict:
    return {
        "id": entry_id,
        "name": name,
        "target": target,
        "present": present,
        "triggers": triggers or [],
    }


def _alias_shifted_catalog(*, base_name: str = "SNOFS_Krea2_Turbo_v14_int8.safetensors") -> dict:
    return {
        "available": True,
        "models": {
            "base": _catalog_entry("base", base_name, "unet"),
            "clip": _catalog_entry("clip", "qwen3vl_4b_fp8_scaled_v2.safetensors", "text_encoders"),
            "vae": _catalog_entry("vae", "qwen_image_vae_fp16.safetensors", "vae"),
            "upscale": _catalog_entry("upscale", "4x_UltraSharp_v2.pth", "upscale_models"),
        },
        "loras": {
            "lora-x": _catalog_entry(
                "lora-x",
                "xcreampiex_krea2_shifted.safetensors",
                "loras",
                triggers=["creampie"],
            )
        },
        "source": {"comfyuiFolder": "C:/ComfyUI"},
        "updatedAt": "2026-10-30T00:00:00Z",
        "createdAt": "2026-10-30T00:00:00Z",
    }


def test_alias_matching_is_case_and_separator_insensitive() -> None:
    assert normalize_token("Krea2_Turbo-Q5_K_M.gguf") == "krea2turboq5km"
    entry = {"name": "snofsSexNudesAndOther_krea2TurboV14_int8.safetensors"}
    assert best_alias_match([entry], ["SNOFS_Krea2", "snofs_krea2"]) is entry
    assert best_alias_match([entry], ["q5_k_m"]) is None


def test_snapshot_and_graph_bind_actual_aliased_filenames(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _alias_shifted_catalog()
    monkeypatch.setattr(catalog, "load_user_catalog", lambda: user)
    pack = catalog.load_pack()

    snapshot = catalog.build_snapshot(pack)
    model = next(item for item in snapshot["models"] if item["id"] == "krea2-turbo-int8")
    assert model["declaredFile"] == "snofsSexNudesAndOther_krea2TurboV14_int8.safetensors"
    assert model["file"] == "SNOFS_Krea2_Turbo_v14_int8.safetensors"
    assert model["textEncoder"] == "qwen3vl_4b_fp8_scaled_v2.safetensors"
    assert model["vae"] == "qwen_image_vae_fp16.safetensors"
    assert model["missing"] == []

    request = _freeze_request(
        loras=[
            {
                "id": "lora-xcreampiex-krea2-v1-1-000002500",
                "strength": 1.0,
                "on": True,
            }
        ],
        advanced={"upscaler": {"id": "4x-ultrasharp", "enabled": True, "value": 2048}},
    )
    normalized = service._normalize_request(request, pack)
    graph, _ = workflows.compose_t2i(pack, normalized["model"], normalized)

    assert graph["1"]["inputs"]["unet_name"] == "SNOFS_Krea2_Turbo_v14_int8.safetensors"
    assert graph["2"]["inputs"]["clip_name"] == "qwen3vl_4b_fp8_scaled_v2.safetensors"
    assert graph["3"]["inputs"]["vae_name"] == "qwen_image_vae_fp16.safetensors"
    assert graph["lora_1"]["inputs"]["lora_name"] == "xcreampiex_krea2_shifted.safetensors"
    assert graph["upscale_model"]["inputs"]["model_name"] == "4x_UltraSharp_v2.pth"


def test_q5_only_install_selects_q5_and_satisfies_the_base_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _alias_shifted_catalog(base_name="krea2_turbo-Q5_K_M_alt.gguf")
    monkeypatch.setattr(catalog, "load_user_catalog", lambda: user)
    pack = catalog.load_pack()

    snapshot = catalog.build_snapshot(pack)
    states = {item["id"]: item for item in snapshot["models"]}
    assert states["krea2-turbo-int8"]["present"] is False
    assert states["krea2-turbo-q5"]["present"] is True
    assert states["krea2-turbo-q5"]["baseGroupSatisfied"] is True
    assert snapshot["defaults"]["modelId"] == "krea2-turbo-q5"
    assert not [
        warning for warning in snapshot["warnings"] if warning["code"] == "model_group_missing"
    ]


def test_stale_exact_catalog_entry_does_not_hide_an_installed_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _alias_shifted_catalog()
    user["models"]["stale"] = _catalog_entry(
        "stale",
        "snofsSexNudesAndOther_krea2TurboV14_int8.safetensors",
        "unet",
        present=False,
    )
    monkeypatch.setattr(catalog, "load_user_catalog", lambda: user)

    snapshot = catalog.build_snapshot(catalog.load_pack())
    model = next(item for item in snapshot["models"] if item["id"] == "krea2-turbo-int8")
    assert model["present"] is True
    assert model["file"] == "SNOFS_Krea2_Turbo_v14_int8.safetensors"

    setup = service.setup_info()
    pack = setup["packs"][0]
    base = next(item for item in pack["groups"][0]["items"] if item["id"] == "krea2-snofs-int8")
    assert base["present"] is True
    assert base["matchedFile"] == "SNOFS_Krea2_Turbo_v14_int8.safetensors"


def test_generic_krea2_file_is_accepted_as_a_fallback_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _alias_shifted_catalog(base_name="Krea2_Turbo_v1.0_fp8.safetensors")
    user["models"]["stale"] = _catalog_entry(
        "stale",
        "snofsSexNudesAndOther_krea2TurboV14_int8.safetensors",
        "unet",
        present=False,
    )
    monkeypatch.setattr(catalog, "load_user_catalog", lambda: user)

    snapshot = catalog.build_snapshot(catalog.load_pack())
    states = {item["id"]: item for item in snapshot["models"]}
    assert states["krea2-turbo-int8"]["present"] is True
    assert states["krea2-turbo-int8"]["file"] == "Krea2_Turbo_v1.0_fp8.safetensors"
    assert states["krea2-turbo-q5"]["present"] is False
    assert snapshot["defaults"]["modelId"] == "krea2-turbo-int8"


def test_setup_payload_reports_one_of_base_and_shared_required_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _alias_shifted_catalog(base_name="krea2_turbo-Q5_K_M_alt.gguf")
    monkeypatch.setattr(catalog, "load_user_catalog", lambda: user)

    payload = service.setup_info()
    assert payload["ready"] is True
    assert payload["policy"] == {
        "autoDownload": False,
        "autoInstall": False,
        "note": "This popup only reports files and opens source links. Download and place them manually, then refresh the model catalog.",
    }
    pack = payload["packs"][0]
    assert pack["id"] == "krea2"
    assert pack["description"]
    assert pack["groups"][0]["id"] == "krea2-base"
    assert pack["groups"][0]["satisfied"] is True
    assert pack["groups"][0]["matchedFile"] == "krea2_turbo-Q5_K_M_alt.gguf"
    assert pack["groups"][0]["items"][0]["present"] is False
    assert pack["groups"][0]["items"][1]["present"] is True
    assert pack["missingRequired"] == []


def test_setup_endpoint_returns_the_shared_contract() -> None:
    response = client.get("/api/t2i/setup")
    assert response.status_code == 200
    payload = response.json()
    assert payload["schemaVersion"] == 2
    assert payload["module"]["id"] == "T2I_main"
    assert payload["packs"][0]["id"] == "krea2"
    assert payload["policy"]["autoDownload"] is False
    assert payload["policy"]["autoInstall"] is False


def test_engine_audit_counts_one_of_base_group_once(tmp_path) -> None:
    requirements_path = catalog.PACK_DIR.parent.parent / "requirements.json"
    raw = json.loads(requirements_path.read_text(encoding="utf-8"))
    models_dir = tmp_path / "models"
    for target in ("unet", "text_encoders", "vae", "loras", "upscale_models"):
        (models_dir / target).mkdir(parents=True)
    (models_dir / "unet" / "krea2_turbo-Q5_K_M_alt.gguf").write_bytes(b"gguf")
    (models_dir / "text_encoders" / "qwen3vl_4b_fp8_scaled_v2.safetensors").write_bytes(b"clip")
    (models_dir / "vae" / "qwen_image_vae_fp16.safetensors").write_bytes(b"vae")

    nodes, models, groups, missing_nodes, missing_models = engine_service._audit_block(
        raw, True, [], models_dir
    )

    assert nodes[0]["optional"] is True
    assert missing_nodes == 0
    assert missing_models == 0
    assert groups[0]["id"] == "krea2-base"
    assert groups[0]["satisfied"] is True
    assert groups[0]["matchedFile"] == "krea2_turbo-Q5_K_M_alt.gguf"
    q5 = next(item for item in models if item["id"] == "krea2-turbo-q5")
    assert q5["installed"] is True
    assert q5["resolvedName"] == "krea2_turbo-Q5_K_M_alt.gguf"
    snofs = next(item for item in models if item["id"] == "krea2-snofs-int8")
    assert snofs["installed"] is False
