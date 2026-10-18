# GenAI GUI

A local-first generative AI studio: **Vue 3 + TypeScript** frontend, **FastAPI** backend,
**ComfyUI** as the image/video engine and **Ollama** for text. One process in production -
the backend serves the built GUI and owns all state (settings, jobs, assets). An optional
**MCP server** exposes the same API to local AI agents.

> **Status: mock phase.** The common layer is real (settings, connectors, library, jobs,
> MCP skeleton). Generation execution is still simulated in the GUI with placeholder images
> (the "MOCK DATA" badge) until the Text->Image pipeline lands - see `docs/PLAN.md` §8 for
> the feature ladder.

## Quick start

1. Double-click **`Launch.bat`**.
2. First run only: it creates `backend\.venv` and builds `frontend\dist`
   (needs `uv` or Python 3.11+; Node.js is needed once for the build - see
   `tools\README.md` for the fully portable, no-install option).
3. After that it runs the backend **in the same console window** and opens
   <http://127.0.0.1:8766> in your browser.

To stop the app: press `Ctrl+C` in that window - or just close it. Nothing keeps
running in the background.

## What you can do today

- **Settings** - saved in `data\settings.json` (authoritative), every field has a reset
  button plus a "reset all" action. Connection profiles for ComfyUI and Ollama.
- **Connections & resources** - live status pills in the top bar, GPU VRAM / RAM popover,
  safe memory actions (the app never loads a model just to unload it).
- **ComfyUI launcher** - point *Settings -> Connections* at your own ComfyUI start `.bat`
  (browse or paste). **Launch ComfyUI** opens it in its own terminal window - exactly like
  double-clicking it. When ComfyUI is offline, the Resources popover offers the same
  shortcut. Nothing ever starts automatically.
- **Library / Gallery** - import (upload or drop files into `data\library`), thumbnails,
  favorites, tags, search. Delete moves files to `data\trash` - **nothing is ever
  hard-deleted**.
- **Jobs** - every run gets a backend id (`#142`, ...) with persisted stages and progress.
- **Folder browser** - folder fields have a real native "Browse..." dialog (the dialog
  opens on the machine running the backend).

## Agents (MCP)

The backend doubles as an MCP server (stdio transport). Enable it in
**Settings -> Agent Access**, then configure your agent - example for opencode:

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

Tools (v0): `app_info`, `list_models`, `job_status`, `list_jobs`, `library_list`,
`import_asset`. Generation tools arrive with the pipeline steps. Details and the
capability registry: `backend/README.md` -> "MCP server".

## Development

```powershell
# backend  -> http://127.0.0.1:8766
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8766

# frontend -> http://localhost:5173 (proxies /api to the backend)
cd frontend
npm install
npm run dev
```

Build gate: `npm run build` (vue-tsc + vite). The backend serves `frontend/dist` in
production (that is what `Launch.bat` uses).

## Layout

`backend/` FastAPI app + MCP server · `frontend/` Vue 3 SPA (one folder per module in
`src/features/`) · `data/` runtime state (settings.json, SQLite, library, trash - never
committed) · `docs/` plans and guidelines · `tools/` optional portable `uv.exe`.

Full structure: `docs/PLAN.md` §7.

## Docs

| Doc | What |
| --- | --- |
| `docs/REQUIREMENTS.md` | the frozen product requirements |
| `docs/PLAN.md` | architecture + the one-feature-per-step roadmap |
| `docs/PACKS.md` | ComfyUI workflow -> pack/recipe guide |
| `docs/GUI_GUIDELINES.md` | frontend conventions for every new module |
| `docs/BACKEND_GUIDELINES.md` | backend conventions, data rules, safety rules |
| `backend/README.md` | API endpoint tables + MCP server details |
| `tools/README.md` | the fully self-contained (uv.exe) option |
