# GenModule starter (`_template`)

This is a complete, working GenModule scaffold. It is not a capability: the
folder starts with `_`, so `app/common/capabilities.py` ignores it.

The starter proves the full host contract without ComfyUI or a GPU:

- backend catalog, validation, job runner, stages, library writes, delete/clear;
- frontend form, persistence, catalog reconciliation, polling, viewer, settings;
- a deterministic SVG renderer (`backend/service.py::_render_svg`).

Replace `_render_svg` with your engine pipeline when you are ready. Keep the job,
library, polling, and deletion code; those are the portable host contracts.

The starter ships a minimal tracked pack at `backend/pack/options.json`.
`/catalog` exposes its defaults, supported size values and batch range, so the
Vue form reads limits from the backend instead of hardcoding them. Replace that
file with your real pack; engine-backed modules add per-model `ranges` (see
T2I_main and `docs/GENMODULE_GUIDE.md` §4.4).

## Layout

```text
_template/
  manifest.json                 complete identity example
  requirements.json             optional engine content (empty here)
  backend/
    __init__.py                 exports router
    api.py                      thin module router, mounted by the host
    schema.py                   camelCase request model
    service.py                  catalog, validation, runner, library, delete/clear
    pack/options.json           starter defaults, size values, batch range
  frontend/
    README.md                   this contract
    types.ts                    wire types
    api.ts                      same-origin client + asset URLs
    store.ts                    form, persistence, catalog, jobs, polling
    TemplatePage.vue            page/layout/composer/viewer
    TemplateSettingsPanel.vue   settings cards and resets
    TemplateGenerationCard.vue  one chat result card
```

The canonical frontend is authoritative. Runtime files are copies under
`frontend/src/features/<nav-id>/`; both use the shared `@/` imports.

## Copy and rename

From the repository root:

```powershell
$repo = (Resolve-Path '.').Path
$moduleId = 'My_module'
$navId = 'my-module'
$dst = Join-Path $repo "backend/app/GenModules/$moduleId"
if (Test-Path $dst) { throw "Module folder already exists: $dst" }
Copy-Item (Join-Path $repo 'backend/app/GenModules/_template') $dst -Recurse
Get-ChildItem (Join-Path $repo "backend/app/GenModules/$moduleId") `
  -Recurse -Directory -Filter '__pycache__' |
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
```

Minimum identity changes (the module works after these):

| Concept | Starter | Yours |
| --- | --- | --- |
| Manifest `id` / folder | `template` / `_template` | `My_module` |
| Manifest `navId` / runtime folder | `template` | `my-module` |
| Backend `MODULE_ID` | `template` | `My_module` (matches folder) |
| Backend `TAB_ID` / schema default / request `tab` | `template` | `my-module` |
| Display name / manifest `name` | `Template` | `My Module` |
| Backend router prefix | `/template` | `/my-module` |
| API prefix / client base | `/api/template` | `/api/my-module` |
| Vue route | `/image/template` | `/image/my-module` |
| Storage key | `genai.template.form.v1` | `genai.my-module.form.v1` |
| Pinia id | `template` | `my-module` |
| Recipe id | `template-card-v1` | `my-recipe-v1` |

`_template` is the one intentional id/folder mismatch: its placeholder id is
`template` while the folder is `_template`, and the leading underscore keeps it
out of the registry. After copying, the folder and `manifest.id` are both
`My_module`. Keep `manifest.recipeIds` in sync with `RECIPE_ID`, and update
`manifest.frontend` if you rename the page.

Recommended full rename: `Template` → `MyModule`, then use the table: folder,
manifest id, and backend `MODULE_ID` are `My_module`; nav id, API/router prefix,
`TAB_ID`/`tab`, storage key, and Pinia id use `my-module`. Update imports. Do
not blind-replace `template-card-v1` or the storage key; update each contract
deliberately. Internal `Template*` type names are acceptable for a first run.

## Registration is explicit

Copying this folder does **not** mount anything. The app has no auto-discovery.

1. **Backend router** — in `backend/app/api/__init__.py`:

   ```python
   from app.GenModules.My_module.backend import api as my_module_api

   # Keep the existing api = APIRouter(prefix="/api") and includes.
   api.include_router(my_module_api.router)
   ```

2. **Vue route** — in `frontend/src/router/index.ts`, add the import and one
   entry inside `routes`:

   ```ts
   import TemplatePage from '@/features/my-module/TemplatePage.vue'

   { path: '/image/my-module', component: TemplatePage, meta: { title: 'My Module' } },
   ```

   If you rename the page, import the renamed component instead; the import
   must match the runtime filename.

3. **Sidebar item** — in `frontend/src/lib/nav.ts`, add one item inside the
   correct group's `items` array:

   ```ts
   { id: 'my-module', label: 'My Module', to: '/image/my-module' },
   ```

4. **Runtime frontend** — create `frontend/src/features/my-module/` and copy
   the six files from `frontend/` (not this README).

The full commands, hash check, and verification steps are in
[`docs/GENMODULE_GUIDE.md`](../../../../docs/GENMODULE_GUIDE.md) §3.

## Verify

From `backend/`:

```powershell
uv run python -c "from app.main import app; print([p for p in app.openapi()['paths'] if 'my-module' in p])"
uv run python -m pytest -q
```

From `frontend/`:

```powershell
npm run typecheck
npm run build
```

Then open the route, generate a batch of two, and verify stages, SVG results,
Library/Gallery/Jobs sync, favorite, per-image trash, per-job delete, both clear
options, reload persistence, and the desktop/mobile settings drawer.

## Make it a real module

1. Replace `_render_svg` with your engine call. Use
   `connectors.comfy_client()`, persist `enginePromptId` in `job.params`, poll
   `history()`, download with `view()`, and register bytes with
   `library.add_bytes`.
2. Replace `backend/pack/options.json` and `catalog_snapshot()` with your real
   defaults and ranges. Keep `/catalog` authoritative for the frontend.
3. If the module can resume after a backend restart, add
   `resume_pending_jobs()`/`shutdown()` to `backend/app/main.py`.
4. Update `manifest.json` (all fields), `schema.py`, `types.ts`, `api.ts`, and
   the store request shape.
5. Keep the module-scoped delete/clear routes and the library trash path.

**Media limitation:** the shared library is image-only (`.png`, `.jpg`, `.jpeg`,
`.webp`, `.bmp`, `.gif`, `.svg`, 128 MB). Audio/video modules require a host
change to `app/library/service.py`, the frontend `Asset` type/Gallery, and the
viewer.

The full behavior, host contracts, and zero-context dry run are in
[`docs/GENMODULE_GUIDE.md`](../../../../docs/GENMODULE_GUIDE.md). `T2I_main` is
the engine-backed reference; use it read-only for ComfyUI-specific patterns.
