"""MCP server - the agent-facing surface over the same services the REST API uses.

Transport: stdio (`uv run python -m app.mcp` from `backend/`), so local agents
spawn it as a subprocess. Streamable HTTP for remote agents arrives with the
Agent Access step - that transport is what the `agentToken` setting gates;
stdio is implicitly local.

Skeleton tool set (PLAN.md §8, Step 2 v0): real read/inspect tools plus file
import. Generation tools (`list_capabilities` with real recipes, `edit_image`,
`queue_generation`, ...) appear with the pipeline steps - until then `app_info`
reports the capability registry honestly.
"""

from __future__ import annotations

from pathlib import Path

from mcp.server import MCPServer

from app import APP_NAME, __version__
from app.common import capabilities, paths, settings_store
from app.connectors import service as connectors
from app.jobs import service as jobs
from app.library import service as library

INSTRUCTIONS = (
    "Local-first generative AI studio (GenAI GUI). Wraps the same API the GUI "
    "uses: inspect engine connections, jobs and the asset library, and import "
    "local files into the library. Generation tools are not available yet - "
    "call app_info() to see the capability registry and engine status."
)


def _asset_summary(asset: dict) -> dict:
    """Compact asset record for agent consumption (stable subset of the REST shape)."""
    return {
        "id": asset["id"],
        "label": asset.get("label", ""),
        "prompt": asset.get("prompt", ""),
        "model": asset.get("model", ""),
        "seed": asset.get("seed", 0),
        "createdAt": asset.get("createdAt", 0),
        "favorite": asset.get("favorite", False),
        "tags": asset.get("tags", []),
        "width": asset.get("width"),
        "height": asset.get("height"),
        "url": asset.get("url", ""),
        "thumbUrl": asset.get("thumbUrl", ""),
        "originJob": asset.get("originJob"),
    }


def create_server() -> MCPServer:
    server = MCPServer(name="genai-gui", version=__version__, instructions=INSTRUCTIONS)

    @server.tool()
    async def app_info() -> dict:
        """App summary: version, data dir, engine connections, library/job counts and the capability registry (installed GenModules + roadmap)."""
        snap = await connectors.status_snapshot()
        values, initialized = settings_store.load()
        comfy, ollama = snap["comfyui"], snap["ollama"]
        return {
            "app": APP_NAME,
            "version": __version__,
            "dataDir": str(paths.DATA_DIR),
            "engines": {
                "comfyui": {
                    "connected": comfy["connected"],
                    "url": comfy["url"],
                    "version": comfy.get("version"),
                    "gpu": comfy.get("gpuName"),
                    "vramFreeGb": comfy.get("vramFreeGb"),
                    "queue": comfy.get("queue"),
                },
                "ollama": {
                    "connected": ollama["connected"],
                    "url": ollama["url"],
                    "installed": len(ollama.get("installed") or []),
                    "loaded": [m["name"] for m in ollama.get("loaded") or []],
                },
            },
            "library": {"assets": library.count_assets()},
            "jobs": {"total": jobs.count_jobs(), "running": jobs.count_jobs("running")},
            "capabilities": capabilities.snapshot(),
            "agent": {
                "enabled": bool(values.get("agentEnabled")),
                "settingsInitialized": initialized,
            },
        }

    @server.tool()
    async def list_models() -> dict:
        """Models the engines offer right now. Ollama: installed + loaded. ComfyUI: only the connection - model listing arrives with the packs step."""
        snap = await connectors.status_snapshot()
        ollama, comfy = snap["ollama"], snap["comfyui"]
        return {
            "ollama": {
                "connected": ollama["connected"],
                "installed": ollama.get("installed") or [],
                "loaded": ollama.get("loaded") or [],
            },
            "comfyui": {
                "connected": comfy["connected"],
                "url": comfy["url"],
                "models": None,
                "note": "ComfyUI model listing (GET /models + manifest matching) arrives with the packs step - docs/PLAN.md §8 Step 3.",
            },
        }

    @server.tool()
    def job_status(job_id: str) -> dict:
        """One job by its backend id (e.g. '#143'): status, progress, stages, result asset ids."""
        job = jobs.get_job(job_id)
        if job is None:
            return {"error": f"job '{job_id}' not found"}
        return job

    @server.tool()
    def list_jobs(limit: int = 10) -> dict:
        """Recent jobs, newest first (compact records)."""
        limit = max(1, min(int(limit), 100))
        return {
            "jobs": [
                {
                    "id": job["id"],
                    "status": job["status"],
                    "progress": job["progress"],
                    "model": job["modelName"],
                    "prompt": (job["prompt"] or "")[:160],
                    "createdAt": job["createdAt"],
                    "resultIds": job["resultIds"],
                }
                for job in jobs.list_jobs(limit=limit)
            ]
        }

    @server.tool()
    def library_list(limit: int = 20, favorites_only: bool = False) -> dict:
        """Recent library assets, newest first. Asset ids are the inputs for future generation tools (edit_image, img2img, ...)."""
        rows = library.list_assets()
        if favorites_only:
            rows = [r for r in rows if r["favorite"]]
        return {"assets": [_asset_summary(r) for r in rows[: max(1, min(int(limit), 200))]]}

    @server.tool()
    def import_asset(path: str, label: str | None = None, tags: list[str] | None = None) -> dict:
        """Copy a local file (PNG/JPG/WebP/...) into the asset library and return its record.

        `path` may be any readable file; the Settings "Agent inbox" folder
        (data/agent-inbox) is the conventional drop location. Path allowlists
        arrive with the Agent Access step.
        """
        source = Path(path).expanduser()
        if not source.is_file():
            return {"error": f"not a file: {path}"}
        try:
            asset = library.add_bytes(
                source.read_bytes(),
                source.name,
                label=label,
                tags=tags or ["agent-import"],
            )
        except ValueError as err:
            return {"error": str(err)}
        return _asset_summary(asset)

    return server
