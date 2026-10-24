"""Focused coverage for T2I_main: pack defaults, ranges, graph composition and
the HTTP error contract.

These tests deliberately do not require ComfyUI or Ollama. The runner test uses
an offline fake client, so it verifies the persisted error stage without a GPU.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.jobs import service as jobs
from app.GenModules.T2I_main.backend import catalog, service, workflows
from app.GenModules.T2I_main.backend.schema import T2IJobRequest
from app.library import placeholders, service as library

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
