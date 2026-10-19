# Backend Guidelines — GenAI GUI (FastAPI)

Version 0.1 (post-Group 3: settings, connectors, library and jobs are real; execution is
still simulated in the GUI). This is the authoritative reference for building **any new
backend piece** — the next act is `GenModules/text-to-image` and the ComfyUI pipeline.
Follow it in every session so all modules behave like one product. If something here blocks
a design, change this doc in the same session.

Companion docs: `docs/GUI_GUIDELINES.md` (frontend counterpart) · `docs/PLAN.md`
(architecture, §7 tree, §8 feature ladder) · `backend/README.md` (endpoint tables).

---

## 0. TL;DR — new module checklist

1. Copy `backend/app/GenModules/_template/` to `backend/app/GenModules/<module-id>/`
   (e.g. `text-to-image`) and fill in `manifest.json`, `schema.py`, `service.py`, `api.py`.
   If the module needs ComfyUI content, fill in `requirements.json` too
   (custom nodes + model files; schema: `docs/COMFYUI_CONTENT.md` §2).
2. Mount the router in `backend/app/api/__init__.py` under a clear prefix
   (`/api/<module-id>/...`). Routers stay thin — no logic in `api/`.
3. Import only from `app.common`, `app.connectors` and the shared services
   (`app.library`, `app.jobs`, `app.settings`) — **never from another GenModule**.
4. One capability = REST route + MCP tool (when the feature ships) + GUI feature folder +
   docs row. Nothing exists only in the GUI (PLAN §2: one API, two clients).
5. Verify small-to-big: read-only probe first, then the smallest real run, one known-good
   reference output per increment.
6. Update `backend/README.md` (endpoint table) and the capability registry notes when the
   ladder moves.

## 1. Layering & folders

```
backend/app/
  main.py            app factory; serves frontend/dist in prod (explicit MIME map - keep it)
  api/               thin REST routers; one file per area + __init__.py mounting them
  common/            paths, defaults, settings.json store, SQLite, capability registry
  settings/          settings service + pydantic models
  connectors/        ComfyUI + Ollama clients + status snapshot service
  engine_content/    ComfyUI folder inspection + per-module node/model audit (read-only)
  library/           asset store (files + rows, scans, thumbnails, trash)
  jobs/              persistent job records (ids, stages, progress, results)
  mcp/               MCP server (stdio v0) - thin tools over the same services
  GenModules/        one folder per generation module (copy _template/); _-prefixed = ignored
```

The flow is always `api/route → service → data`. If a route grows logic, move it to the
module's `service.py`; if two modules need it, promote it to a shared service or `common/`.

## 2. Conventions

- **JSON boundary is camelCase** (`thumbUrl`, `originJob`, `resultIds`); Python stays
  snake_case and converts at the edge. Keep the frontend store shapes identical to what the
  API returns — the settings store mirrors `settings.json` exactly.
- **Errors:** return structured JSON, not prose. Missing entity → `404` with a detail the
  GUI can show; validation problems → `4xx` before touching the engine or disk.
- **Async:** connector calls are `async` (httpx); services and DB are plain sync functions.
- **Ids:** job ids come from the backend (`#141`, `#142`, ...). In URLs they must be
  URL-encoded (`#` → `%23`); the frontend `lib/api.ts` already does this.
- **Types:** request/response models per module in its `schema.py` (or the module-specific
  part of `settings/models.py`). The GUI derives its TS types from the same contract in
  `frontend/src/types.ts`.

## 3. Data & persistence

Everything lives under `<repo>/data` (override: `GENAI_DATA_DIR`):

| Path | Contents | Rule |
| --- | --- | --- |
| `settings.json` | GUI settings — **authoritative copy** | written only via the settings service (atomic, deep-merged) |
| `app.db` | SQLite: jobs, assets, meta | migrations are forward-only (`common/db.py` `_migrate()`) |
| `library/` | asset files — **folder is the source of truth** | scans re-import dropped files automatically |
| `thumbnails/` | generated thumbnails | never scanned as library files |
| `trash/` | Delete chip destination | **never hard-delete anything** — move to trash, restoring = copy back |
| `agent-inbox/` | conventional drop folder for agent files | regular library rules apply |

- Adding a column/table = extend the schema **and** add an idempotent step in `_migrate()`;
  never rewrite or drop existing data.
- The DB rows add metadata to files, they never own them. Deleting a row without moving the
  file (or vice versa) is a bug.
- No deletion commands from tooling either — cleanup is a user action through the GUI.

## 4. Jobs & assets contract

- A job is created via `jobs.service.create_job()` **before** work starts; the backend owns
  ids and the `status`/`progress` lifecycle (`running → done | error`).
- Progress/stages are persisted incrementally via `update_job()` — the GUI and agents poll
  or re-read; nothing lives only in memory.
- Stages shape (keep it stable — the Jobs page and MCP render it directly):

  ```json
  [{ "id": "compose", "label": "Compose graph", "status": "done", "detail": "", "startedAt": 0, "finishedAt": 0 }]
  ```

- Engine outputs enter the library only through `library.service.add_file/add_bytes`, which
  hashes, measures, and stores metadata. Result ids go into the job's `resultIds`.
- **Mock phase marker:** `POST /api/jobs/{id}/mock-complete`, `library/placeholders.py`,
  `frontend/src/lib/mockApi.ts#runJob` and the GUI "MOCK DATA" badge all disappear in the
  same commit that lands real execution. Do not build new features on them.

## 5. Settings contract

- `common/defaults.py` is the single source of truth for shipped defaults — it powers the
  per-field reset buttons and "reset all". A new option means: default here, typed model in
  `settings/models.py` (if needed), GUI field with a reset chip in the same session.
- Writes go through `common/settings_store.merge_and_save()` (validated, atomic). Never
  write `settings.json` ad-hoc from a route.
- Secrets/tokens live here, not in code: `agentToken` is the gate for the future HTTP MCP
  transport; `agentEnabled` gates the MCP server startup today.

## 6. MCP surface (agents)

- The MCP server (`app/mcp/`, stdio v0) is a **thin wrapper over the same services** the
  REST API uses — never a second implementation.
- Tool rules: real data or explicit `{"error": ...}`; never invent capabilities. The
  capability registry (`common/capabilities.py`) is manifest-driven — adding a GenModule
  manifest is what makes a capability appear.
- stdio is implicitly local; keep the `agentEnabled` gate in place and read settings on
  every startup (the GUI can flip it at any time).
- Every new capability gets its tool with the feature (PLAN §8: "every step ends with GUI
  wired + REST endpoint + MCP tool + docs touched").

## 7. Safety rules (non-negotiable)

- **Probes are read-only.** Status checks may call `GET` endpoints on ComfyUI/Ollama and
  nothing else.
- **Never trigger a model load.** Ollama unload only ever targets models already listed by
  `GET /api/ps`; ComfyUI gets at most `POST /free`. No test, no matter how quick, may load
  a model as a side effect.
- **Starting user executables is opt-in, explicit, and guarded.** The ComfyUI launcher
  (`.bat` in settings) runs from a GUI click (`POST /api/engine/comfyui/launch`) or - only
  when the user enabled `comfyuiLauncherAutoStart` - once at backend boot. Even then it
  skips when ComfyUI is already reachable and debounces recent spawns (dev reloads).
  Never from probes or agent tools, and never anything other than the configured file.
- **No hard deletes** anywhere in backend code; the Delete path is move-to-trash.
- **Engine content inspection is read-only.** `app/engine_content` may list folders, read
  `.git/config` / `.git/HEAD`, stats and filenames - never execute or import anything from
  the ComfyUI folder, never write into it. Node installs / model downloads only arrive
  behind an explicit GUI click with a confirmation and a streamed log
  (`docs/COMFYUI_CONTENT.md` §7).
- Paths coming from users/agents are validated before use (folder validation service);
  imports are size- and extension-guarded (`library/service.py`).
- Remote exposure is opt-in only: localhost defaults, token for network transports, file
  allowlists when the agent file roots land.

## 8. Acceptance checklist (per backend session)

1. Dev run clean: `uv run uvicorn app.main:app --reload --port 8766` — no import errors,
   no console warnings that the GUI would surface.
2. Endpoint-level verification of everything touched (create → update → read → side effects),
   including the negative cases (missing id → 404, bad input → 4xx).
3. If the frontend changed: `npm run build` is green (vue-tsc gate) and the live UI path was
   exercised once (send → stages → result, or the equivalent for the feature).
4. Settings touched? Confirm `data/settings.json` is the only writer's target and per-field
   reset still works.
5. Docs touched in the same session: `backend/README.md` tables, `docs/PLAN.md` if the
   ladder/architecture moved, this file if a convention changed.
6. Test artifacts stay in `data/` and are removable through the GUI (Gallery → Delete → trash).
