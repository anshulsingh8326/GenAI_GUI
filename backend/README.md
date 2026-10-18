# GenAI GUI backend (FastAPI)

The app's single source of truth. The GUI and AI agents (via the MCP server,
stdio v0) talk only to this API - the browser never connects to ComfyUI directly.

## Layout

```
backend/app/
  main.py            app factory, CORS, serves frontend/dist in prod
  api/               thin REST routers (system, settings, folders, status, connectors, assets, jobs)
  common/            shared infrastructure: paths, defaults, settings.json store, SQLite
  settings/          settings service + pydantic models
  connectors/        ComfyUI + Ollama HTTP clients and the status snapshot service
  library/           asset store: files in data/library + rows, scans, thumbnails, placeholders
  jobs/              persistent job records (ids, stages, progress, results)
  mcp/               MCP server (stdio v0): thin tools over the same services
  GenModules/        one folder per generation module - arrives with the first real pipeline step (see its README)
```

## Run (dev)

```powershell
cd backend
uv sync                              # creates .venv, installs deps
uv run uvicorn app.main:app --reload --port 8766
```

Frontend dev server (vite) proxies `/api` to `http://127.0.0.1:8766`.
Or just run `scripts/start-backend.cmd` from the repo root, or `Launch.bat`
from the repo root for the full app (creates .venv + builds + starts + opens).

## Data

Everything the backend persists lives in `<repo>/data` (override with the
`GENAI_DATA_DIR` env var):

- `settings.json` - GUI settings (shape matches the frontend store exactly)
- `app.db` - SQLite (jobs, assets, meta)
- `library/`, `exports/`, `imports/`, `agent-inbox/` - default asset folders
- `thumbnails/` - generated asset thumbnails (never scanned as library files)
- `trash/` - destination for the gallery's Delete chip; restoring = copy a file
  back into `library/` and it is re-imported on the next scan. Nothing is ever
  hard-deleted by the backend.

## Group 1 endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | liveness |
| GET | `/api/system/info` | version, data dir, db tables (GUI diagnostics) |
| GET | `/api/settings` | `{ values, initialized }` - `initialized:false` lets the GUI push its current settings on first connect |
| PUT | `/api/settings` | partial update, deep-merged + validated, atomic save |
| GET | `/api/settings/defaults` | shipped defaults - powers the per-field reset buttons |
| POST | `/api/settings/reset` | reset settings.json to defaults (never touches files) |
| POST | `/api/folders/validate` | check a typed folder path, optionally create it (`{ path, create }`) |

## Group 2 endpoints (connectors + resources)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/status` | one live snapshot: ComfyUI (version, GPU, VRAM, queue), Ollama (installed + loaded models), RAM/VRAM - polled by the GUI |
| POST | `/api/connectors/{kind}/test` | on-demand connection test (`kind`: `comfyui` \| `ollama`) |
| POST | `/api/engine/comfyui/free` | `POST /free` on ComfyUI - frees its cache, never loads anything |
| POST | `/api/engine/ollama/unload` | `{"model": name}` or omitted for all - only ever targets models already in memory (`GET /api/ps`), so it can never cause a load |

Safety rules live in `connectors/service.py`: probes are read-only, the unload
path re-checks `/api/ps` before calling `keep_alive: 0`.

## Group 3 endpoints (library + jobs)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/assets` | library list (newest first). `?favorites=true`, `?q=`, `?limit=`. Auto-scans the library folder for dropped-in files |
| POST | `/api/assets/import` | multipart upload (`file`, optional `label`, `tags`) - saved into the library folder |
| PATCH | `/api/assets/{id}` | edit `favorite` / `label` / `tags` / `nsfw` |
| DELETE | `/api/assets/{id}` | move the file to `data/trash` and drop the row (recoverable) |
| GET | `/api/assets/{id}/file` | the image itself |
| GET | `/api/assets/{id}/thumb` | thumbnail (generated on first request into `data/thumbnails`; SVG falls back to the original) |
| GET | `/api/jobs` | job history, newest first (`?limit=`) |
| POST | `/api/jobs` | create a job record - the backend owns ids (`#142`, `#143`, ...) |
| GET | `/api/jobs/{id}` | one job |
| PATCH | `/api/jobs/{id}` | persist `status` / `progress` / `stages` / `enhancedPrompt` / `resultIds` / `error` |
| POST | `/api/jobs/{id}/mock-complete` | **mock phase** (see below) |

### Mock phase: `POST /api/jobs/{id}/mock-complete`

Execution is still simulated in the GUI until the ComfyUI pipeline lands, so
this endpoint stands in for "the engine wrote outputs into the library": it
generates deterministic placeholder PNGs (`library/placeholders.py`, Pillow),
registers them as assets of that job, and marks the job done. Deleting this
endpoint (and its frontend caller) is all that changes when real execution
arrives - the response shape `{ job, assets }` stays the same.

## MCP server (agent access)

The backend doubles as an MCP server so local AI agents (opencode, Claude Code, ...)
use the exact same services the REST API uses - tools never bypass them.

- **Start (stdio):** `uv run python -m app.mcp` from `backend/`.
- **Gate:** refuses to start while `agentEnabled` is false in `settings.json`
  (exit code 2 + a pointer to Settings). Enable it in the GUI under
  **Settings -> Agent Access**. `agentToken` gates the future streamable-HTTP
  transport for remote agents; stdio is implicitly local.
- **Tools (v0):** `app_info` (engines, counts, capability registry), `list_models`
  (Ollama installed + loaded; ComfyUI listing arrives with the packs step),
  `job_status`, `list_jobs`, `library_list`, `import_asset` (copy a file into the library).
- **Capability registry:** `app/common/capabilities.py` - `installed` is
  manifest-driven (`GenModules/<id>/manifest.json`, folders starting with `_`
  are ignored), `planned` mirrors `docs/PLAN.md` §8. Generation tools appear
  with the first pipeline step; until then `app_info` reports the truth.

Agent config example (opencode style):

```json
{
  "mcp": {
    "genai-gui": {
      "type": "local",
      "command": ["<repo>/backend/.venv/Scripts/python.exe", "-m", "app.mcp"],
      "cwd": "<repo>/backend"
    }
  }
}
```
