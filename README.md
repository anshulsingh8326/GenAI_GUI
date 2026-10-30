# GenAI GUI

A local-first generative AI studio: **Vue 3 + TypeScript** frontend, **FastAPI** backend,
**ComfyUI** as the image/video engine and **Ollama** for text. One process in production -
the backend serves the built GUI and owns all state (settings, jobs, assets). An optional
**MCP server** exposes the same API to local AI agents.

> **Status: T2I_main is live.** Text → Image runs through the real backend and ComfyUI:
> validated pack ranges, persisted jobs, generated assets in the library, prompt
> enhancement and result history. Other generation tabs are still mock until their
> pipelines land - see `docs/PLAN.md` §8 for the feature ladder.

## Quick start

1. Double-click **`Launch.bat`**.
2. On first run it calls **`Setup.bat`**: creates `backend\.venv` with `uv`,
   which installs Python into `tools\python` (project-local, never on `PATH`),
   checks **Git** (required for ComfyUI node installs, no ZIP fallback), and
   builds `frontend\dist` when needed. If npm is missing, Setup can download
   portable Node.js into `tools\node`. Missing tools are only installed after a
   Y/N prompt; Node.js is only needed for a frontend build. See
   `tools\README.md`.
3. It rebuilds the Vue frontend automatically when sources/configs are newer
   than `frontend\dist`, then runs the backend **in the same console window**
   and opens <http://127.0.0.1:8766> in your browser.

To stop the app: press `Ctrl+C` in that window - or just close it. Nothing keeps
running in the background.

## First-time setup for new users

The app is the GUI; it does **not** include ComfyUI or any model files.

**Prerequisites and versions**

| Tool | Minimum | Recommended / tested | Needed for |
| --- | --- | --- | --- |
| uv | latest | 0.13.6 | Backend bootstrap; it installs a project-local Python. |
| Python | 3.11 | 3.13.x | Backend runtime. Setup uses uv to install 3.13; a manually installed Python 3.11+ also works as the fallback. |
| Node.js | 22.18 | 24 LTS (24.22.1 tested) | Building `frontend\dist` only. |
| Git for Windows | latest 2.x | latest 2.x | ComfyUI custom-node installs only. |
| 7-Zip | any recent | latest | Extracting the ComfyUI portable `.7z`. |
| ComfyUI | 0.26+ | latest (0.30.0 tested) | The image generation engine. Krea 2 needs 0.26+. |

`uv` installs Python; Python does not install `uv`. Python is required at
runtime. Node.js is only needed when the UI has to be built; a release that
includes `frontend\dist` runs without Node. Git is optional to open the app, but
custom-node installs are disabled until it is installed.

For a manual setup, install **uv** (or Python 3.11+) and **Git** first; install
**Node 24 LTS** only if `frontend\dist` is missing or you change the frontend.
`Launch.bat` reuses tools already on `PATH` and only prompts for a portable
download when it needs one.

**What you need**

- Windows 10/11 64-bit. The one-click `Launch.bat` flow is Windows-only for now.
- Internet access for the first setup.
- [ComfyUI Windows portable for NVIDIA](https://github.com/comfyanonymous/ComfyUI/releases/latest/download/ComfyUI_windows_portable_nvidia.7z) -
  the portable release is easiest. Extract it with
  [7-Zip](https://www.7-zip.org/) and point the app at the inner
  `ComfyUI_windows_portable\ComfyUI` folder. For AMD/older GPUs or other builds,
  use the [ComfyUI GitHub repository](https://github.com/Comfy-Org/ComfyUI), not
  the Desktop download page.
- Model files are **not** downloaded by this app. You can add them later; image
  generation will not work until the model files a workflow needs are present.
  See [`docs/MODEL_DOWNLOADS.md`](docs/MODEL_DOWNLOADS.md) for the manual
  download list, exact filenames and target folders.

**Steps**

1. Download or clone this project into a normal writable folder. Do not put it
   inside `Program Files`; the app creates `data\`, `tools\` and
   `backend\.venv\` next to it.
2. Double-click **`Launch.bat`**.
   - If Setup asks to download **portable uv**, choose **Y**. It installs Python
     inside `tools\python`; nothing is added to Windows `PATH`.
   - If the UI needs building and npm is missing, Setup offers **portable
     Node.js** in `tools\node`. Choose **Y** if you want Setup to build it.
   - If Setup says **Git is missing**, install it from
     <https://git-scm.com/download/win>, then run `Launch.bat` again. Git is
     required for ComfyUI custom-node installs; the app can still open without
     it, but node install buttons stay disabled.
3. Wait for the browser to open at <http://127.0.0.1:8766>. The first setup can
   take a few minutes.
4. In the **ComfyUI setup** popup, choose the ComfyUI **source** folder - the one
   that contains `main.py`, `custom_nodes\` and `models\`. For the portable
   release this is usually:
   `...\ComfyUI_windows_portable\ComfyUI`
   not the outer `ComfyUI_windows_portable` folder. **Browse...** opens a folder
   picker; if the app detects a folder it also offers **Use this folder**. If
   you do not have ComfyUI yet, use the portable link in **What you need**.
5. Check the list of **required custom nodes**. Installing is always an explicit
   action: click **Install**, confirm, and wait for the log. Git-based installs
   are pinned to a commit. When finished, click **Restart ComfyUI** if the log
   offers it; otherwise close and reopen your ComfyUI window.
6. Start ComfyUI if it is not already running. You can point
   *Settings -> Connections* at your ComfyUI start `.bat` and use **Launch
   ComfyUI** there.
7. Add model files. Pick **one** base (install both only if you want both packs):
   - **Krea 2 Turbo** — [krea2_turbo-Q5_K_M.gguf](https://huggingface.co/vantagewithai/Krea-2-Turbo-GGUF/resolve/main/krea2_turbo-Q5_K_M.gguf)
     → `ComfyUI/models/unet/`
   - **Krea 2 SNOFS** — [SNOFS_Krea2 int8](https://civitai.com/models/2416142?modelVersionId=3333138)
     → `ComfyUI/models/unet/`
   - **Text encoder (shared)** — [qwen3vl_4b_fp8_scaled.safetensors](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/text_encoders/qwen3vl_4b_fp8_scaled.safetensors)
     → `ComfyUI/models/text_encoders/`
   - **VAE (shared)** — [qwen_image_vae.safetensors](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/vae/qwen_image_vae.safetensors)
     → `ComfyUI/models/vae/`

   Then use **Settings -> Model catalog -> Refresh from ComfyUI**. The Text -> Image
   **Setup** popup shows the same links, destination folders and missing files, and
   accepts common renamed filenames through aliases. Full list:
   [`docs/MODEL_DOWNLOADS.md`](docs/MODEL_DOWNLOADS.md).

   Optional extras, separate from the base model:
   - **Realism Engine LoRA** (enabled by default) — [direct file](https://huggingface.co/RazzzHF/realism_engine_krea2/resolve/main/realism_engine_krea2_v3.1.safetensors)
     → `ComfyUI/models/loras/`
   - **4x-UltraSharp** (off by default) — [direct file](https://huggingface.co/Kim2091/UltraSharp/resolve/main/4x-UltraSharp.pth)
     → `ComfyUI/models/upscale_models/`
8. Open **Text -> Image** and generate. Ollama is optional; it is only needed for
   prompt enhancement.

Later launches are automatic. Node.js is only needed to rebuild the UI after
Vue source/config changes; once `frontend\dist` exists, running the app does not
need Node. A normal git commit carries frontend source, not the gitignored
`frontend\dist` - source users rebuild with system npm or portable Node. For a
release that needs no Node, build the frontend first and include
`frontend\dist` in the release ZIP (see `tools\README.md`).

## What you can do today

- **Settings** - saved in `data\settings.json` (authoritative), every field has a reset
  button plus a "reset all" action. Connection profiles for ComfyUI and Ollama.
- **Connections & resources** - live status pills in the top bar; GPU VRAM / RAM popover
  (VRAM via `nvidia-smi`, so it stays visible even with ComfyUI closed; falls back to
  ComfyUI's own stats). Safe memory actions - the app never loads a model just to unload it.
- **ComfyUI launcher** - point *Settings -> Connections* at your own ComfyUI start `.bat`
  (browse or paste). **Launch ComfyUI** opens it in its own terminal window - exactly like
  double-clicking it. When ComfyUI is offline, the Resources popover offers the same
  shortcut. A switch in the same section can start it automatically whenever the app
  launches (off by default; skipped when ComfyUI is already running).
- **ComfyUI content check** - point *Settings -> Connections* at your ComfyUI source folder
  (the one with `main.py`; auto-detected from the launcher, with a one-click correction when
  you pick the Portable root or a subfolder). *Settings -> Engine content* then reports the
  shared core baseline (GGUF loader required, Manager recommended), what each generation
  module needs, and every model file grouped by what it generates (image / video / LoRA /
  VAE / encoder) - kinds and LoRA triggers are read from file headers only. A startup popup
  lists missing **required custom nodes** with individual install buttons; engine-backed
  modules also open a setup popup for missing required model files. Optional nodes and models
  never block readiness. Node/package installers for declared requirements are implemented;
  verified model downloads are the next phase. Git is required for installs. The editable
  model/LoRA catalog (`data/model_catalog.json`, *Settings -> Model catalog*) tracks model
  links, strength ranges and trigger words and feeds the composer - see
  `docs/MODEL_CATALOG.md`.
- **Text → Image (T2I_main)** - strict T2I through ComfyUI with Krea 2 Turbo: model-aware
  ranges, LoRA chaining, optional latent refine or 4x-UltraSharp (off by default), prompt
  enhancement, batch generation and visible upscale on/off. Two packs share one graph:
  **Krea 2 Turbo** (Q5_K_M, 9 steps / CFG 2.0, not NSFW) and **Krea 2 SNOFS** (int8,
  12 steps / CFG 2.5). Each pack has its own
  `defaults.json`; edit that one file for its sampling, size, refine, upscaler and LoRA-chain
  defaults. Only the Realism Engine LoRA is enabled by default; the other LoRAs start off.
  Generic Krea 2 filenames are matched through aliases and the real catalog
  filename is bound into the graph. A first-open
  **Setup** popup reports
  missing required files, folders, sizes and links (and never downloads anything). Settings
  persist across tabs/reloads; every panel has a reset. History is a chat workspace with
  result cards, full applied settings, shared media viewer and soft deletion (message-only or
  move images to trash).
- **Library / Gallery** - import (upload or drop files into `data\library`), thumbnails,
  favorites, tags, search, refresh and a shared fullscreen viewer. Delete moves files to
  `data\trash` - **nothing is ever hard-deleted**.
- **Jobs** - every run gets a backend id (`#142`, ...) with persisted stages and progress; the
  top-bar queue pill shows **Working** while anything is running, `Queue idle` otherwise.
  Terminal jobs can be removed from history without destroying their audit row.
- **Folder browser** - folder fields have a real native "Browse..." dialog (the dialog
  opens on the machine running the backend).

## Build your own GenModule

Want Image → Image, Image → Video, or another workflow? The app does not
auto-discover modules, so start from `backend/app/GenModules/_template/`, copy
and rename it, then add the three host registrations (backend router, Vue route,
sidebar item) in `docs/GENMODULE_GUIDE.md` §3. New tabs use the existing grouped
sidebar in `frontend/src/lib/nav.ts`; `soon: true` is only the placeholder flag,
so remove it when the module is live. Image → Video also needs the shared
library/viewer change noted in the guide.

Paste this into your AI agent, replacing the idea placeholder:

> Read `docs/GENMODULE_GUIDE.md` and `docs/GENMODULE_PROMPT.md`. Build
> **`(Your GenModule Idea)`** as one GenModule from
> `backend/app/GenModules/_template`. Follow §3 to copy/rename it and register the
> backend router, Vue route, and grouped sidebar item. Keep one pack folder per
> family/recipe, put defaults/ranges/filenames in pack JSON, and expose them via
> `/catalog`. Use alias-based file detection and one-of groups in
> `requirements.json`; add the shared `/setup` modal for missing files. Run the
> §3.6 checks and §8.5 smoke test. Use `T2I_main` only as the ComfyUI reference;
> do not modify it.

`docs/GENMODULE_PROMPT.md` is the full copy-paste prompt. `docs/PACKS.md` covers
packs; `docs/MODEL_CATALOG.md` covers per-model ranges.

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
committed) · `docs/` plans and guidelines · `tools/` optional portable uv, Python and
Node.js · `Setup.bat` / `Launch.bat` bootstrap and run the app.

Full structure: `docs/PLAN.md` §7.

## Docs

| Doc | What |
| --- | --- |
| `docs/REQUIREMENTS.md` | the frozen product requirements |
| `docs/PLAN.md` | architecture + the one-feature-per-step roadmap |
| `docs/COMFYUI_CONTENT.md` | connect to a user's ComfyUI + manage custom nodes / models (phases A-D) |
| `docs/MODEL_CATALOG.md` | editable model/LoRA metadata: links, strength ranges, triggers, API |
| `docs/PACKS.md` | ComfyUI workflow -> pack/recipe guide |
| `docs/GUI_GUIDELINES.md` | frontend conventions for every new module |
| `docs/GENMODULE_GUIDE.md` | reusable GenModule guide: `_template` starter, host registration, packs, aliases, setup popup, jobs, library and media viewer |
| `docs/GENMODULE_PROMPT.md` | copy-paste AI prompt for building a GenModule from `(Your GenModule Idea)` |
| `docs/BACKEND_GUIDELINES.md` | backend conventions, data rules, safety rules |
| `backend/README.md` | API endpoint tables + MCP server details |
| `tools/README.md` | setup checks, portable uv/Python/Node, frontend rebuild rules |
