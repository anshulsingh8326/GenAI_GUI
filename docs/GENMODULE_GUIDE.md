# GenModule Development Guide

A **GenModule** is one portable vertical slice of GenAI GUI: a generation
workflow with its own backend service, API, canonical frontend, runtime page,
job history, and tests. Modules with GUI defaults, fixed choices, or model/LoRA
ranges ship a tracked pack. `_template` is the complete working starter;
`T2I_main` (strict Text → Image) is the engine-backed reference.

This guide is self-contained for the module's behavior, host contracts, and
copy/register procedure **when the repository and `_template` are available**.
It is not a standalone source dump: with only this Markdown file you cannot
copy the starter or run the host checks. The app does **not** auto-discover
modules. Copying a folder into `backend/app/GenModules/` creates the code;
three host edits are still mandatory: mount the backend router, add the Vue
route, add the sidebar item. §3 gives the exact edits, and Appendix A lists the
shared contracts. If you have no prior module context, start from `_template`;
do not infer contracts from `T2I_main`.

The module README is a per-module contract, not a prerequisite for this guide.
For a copy-paste agent prompt that points at this guide and the one-of/alias
contract, use `docs/GENMODULE_PROMPT.md`.

---

## 1. What “portable” means

A module is portable when all of the following are true:

1. Its backend lives entirely under
   `backend/app/GenModules/<module-id>/`.
2. Its canonical frontend lives under that module's `frontend/` folder.
3. Runtime frontend files are byte-identical copies in
   `frontend/src/features/<nav-id>/`.
4. It imports shared app services only (`app.common`, `app.connectors`,
   `app.jobs`, `app.library`, `app.settings`) and never another GenModule.
5. All history and deletion operations are **module-scoped**.
6. The only integration points outside the module are explicit registrations:
   the backend router mount, the Vue route, and the nav item.
7. It contains no hard-coded absolute paths, localhost URLs, credentials, or
   machine-specific file paths.
8. Its canonical and runtime frontend files can be checked with hashes and
   are always kept in sync.

Do not copy T2I's business rules into an unrelated module. Copy the
architecture, contracts, and UX patterns; replace the model, validation,
graph, settings, and prompt semantics.

---

## 2. Architecture at a glance

```text
backend/app/GenModules/<module-id>/
  manifest.json                 identity, nav id, API prefix, entrypoint
  requirements.json             optional ComfyUI nodes / model files
  __init__.py
  backend/
    __init__.py
    api.py                      thin FastAPI router
    schema.py                   request/response models
    service.py                  validation, stages, runner, deletion, library
    catalog.py                  pack + installed-catalog merge (optional)
    workflows.py                ComfyUI graph composition (optional)
    pack/                       tracked, authoritative module JSON (optional)
      registry.json             pack ids, labels, paths, default pack
      packs/<pack-id>/          one family/recipe per folder
        pack.json               label, description, nsfw, order
        defaults.json           the one editable generation-defaults file
        options.json            recipe, ratios, sampler lists, limits
        models.json             model bindings, ranges, workflow/composer
        loras.json              optional LoRA catalog
        upscalers.json          optional upscaler catalog
        text_models.json        optional prompt-enhancement models
        workflows/*.api.json    API-format ComfyUI graph(s)

  frontend/                     canonical frontend deliverable
    README.md                   module-specific contract
    types.ts
    api.ts
    store.ts
    <Module>Page.vue
    <Module>SettingsPanel.vue
    <Module>GenerationCard.vue

frontend/src/
  features/<nav-id>/            runtime copies of the canonical files
  components/ui/                shared primitives
  components/chat/              shared StageTimeline
  components/media/             shared MediaViewer
  stores/library.ts             backend-first asset cache
  stores/jobs.ts                generic Jobs page cache
  stores/engine.ts              live /api/status readiness and queue
```

`backend/app/GenModules/_template/` is the same shape, with a local placeholder
renderer instead of an engine and a minimal `pack/options.json` for its
defaults/choices. `T2I_main/` splits generation defaults into
`packs/<pack>/defaults.json`, adds per-model ranges, `catalog.py`, and
`workflows.py` for the full ComfyUI path. A module with more than one model
family uses `pack/registry.json` plus one folder per pack; a single-pack module
may keep the JSON files directly in `pack/`. Neither folder is auto-mounted:
the backend router, Vue route, and sidebar item are explicit host edits (§3).

End-to-end flow:

```text
Page -> module store -> /api/<module> -> service
                                      -> app.jobs.service
                                      -> ComfyUI / Ollama (engine-backed)
                                      -> app.library.service
                                      -> /api/assets/{id}/file|thumb

GET /api/status -> shared engine store -> live badges + Generate enablement
```

Rules:

1. **No GenModule imports another GenModule.**
2. When the module has a tracked pack, that pack is authoritative for module
   ranges, defaults, and graph wiring. A user catalog may supply installed-file
   presence, never module ranges.
3. The GUI and API/MCP callers must pass through the same service validation.
4. The library owns files. The jobs service owns job records. The module owns
   its workflow and its module-scoped history operations.
5. Promote reusable UI and state to the shared layer; do not fork it per
   module.
6. The canonical frontend is the source of truth. Copy it into the runtime
   feature folder; never edit only the runtime copy.

---

## 3. Copy-paste quick start

### 3.0 What copy-paste means here

A GenModule is portable, but the app does **not** auto-discover it. Copying a
folder into `backend/app/GenModules/` creates the module's code; it does not
mount its router, add a Vue route, or add a sidebar item. Those are three
explicit host edits (§3.3 and §3.4). The manifest fields are identity and
documentation, not runtime wiring.

The starter under `_template/` is a complete working vertical slice:

- backend: catalog, validation, job runner, stages, library writes, delete/clear;
- frontend: the six canonical files, persistence, polling, viewer, settings;
- output: a deterministic SVG card, so it works without ComfyUI or a model.

Replace `_render_svg` in `_template/backend/service.py` with your engine
pipeline when you are ready. A folder starting with `_` is ignored by the
capability registry; after you copy it to a real id it becomes visible.

### 3.1 Choose a starting point

| Starting point | Use it when | What you get |
| --- | --- | --- |
| `backend/app/GenModules/_template/` | You have only the docs, or you want a working first run | Complete backend + frontend, local SVG renderer, no engine |
| `backend/app/GenModules/T2I_main/` | You have the repo and need the full ComfyUI reference | Pack, LoRA/upscale/enhancement, real engine runner, real tests |

Do not copy both into the same module. If you start from `_template`, use T2I
only as a read-only reference for engine-specific code.

### 3.2 Copy and rename the starter

From the repository root (PowerShell):

```powershell
$repo = (Resolve-Path '.').Path
$moduleId = 'My_module'          # folder + manifest id
$navId = 'my-module'             # runtime folder, route id, nav id
$src = Join-Path $repo 'backend/app/GenModules/_template'
$dst = Join-Path $repo "backend/app/GenModules/$moduleId"

if (Test-Path $dst) { throw "Module folder already exists: $dst" }
Copy-Item $src $dst -Recurse
Get-ChildItem $dst -Recurse -Directory -Filter '__pycache__' |
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
```

Minimum identity changes (the module works after these; internal `Template*`
symbol names may stay until you refactor):

| Concept | Starter value | Your value |
| --- | --- | --- |
| Module folder / manifest `id` | `_template` / `template` | `My_module` |
| Manifest `navId` | `template` | `my-module` |
| Backend `MODULE_ID` | `template` | `My_module` (must match the folder) |
| Backend `TAB_ID` / schema default / request `tab` | `template` | `my-module` |
| Display name / manifest `name` | `Template` | `My Module` |
| API prefix / client base (`api.ts`) | `/api/template` | `/api/my-module` |
| Backend router prefix | `/template` | `/my-module` |
| Vue route | `/image/template` | `/image/my-module` |
| Runtime feature folder (create it) | `frontend/src/features/template/` | `frontend/src/features/my-module/` |
| Storage key | `genai.template.form.v1` | `genai.my-module.form.v1` |
| Pinia id | `template` | `my-module` |
| Recipe id | `template-card-v1` | `my-recipe-v1` |
| Page component | `TemplatePage.vue` | `MyModulePage.vue` (recommended) |
| Settings panel | `TemplateSettingsPanel.vue` | `MyModuleSettingsPanel.vue` |
| Result card | `TemplateGenerationCard.vue` | `MyModuleGenerationCard.vue` |

`_template` is the one intentional id/folder mismatch: its placeholder manifest
id is `template` while its folder is `_template`, and the leading underscore
keeps it out of the registry. After copying, the folder and `manifest.id` are
both `My_module`. Keep `manifest.recipeIds` in sync with the backend
`RECIPE_ID`, and update `manifest.frontend` if you rename the page.

Recommended full rename: replace `Template` with `MyModule`. Then use the table
above deliberately: the manifest id, folder, and backend `MODULE_ID` are
`My_module`; nav id, API/router prefix, `TAB_ID`/`tab`, storage key, and Pinia
id use `my-module`. Do not blind-replace `template-card-v1` or
`genai.template.form.v1`; update each contract deliberately. Use PowerShell to
find every occurrence:

```powershell
Get-ChildItem $dst -Recurse -File |
  Select-String -Pattern 'template|Template' |
  Select-Object Path, LineNumber, Line
```

The template's backend lives in `_template/backend/`; the API files are not at
the module root. Keep that layout.

### 3.3 Register the backend router

Edit `backend/app/api/__init__.py`. Add the import next to the existing T2I
import, and add one `include_router` call after the existing includes:

```python
from app.GenModules.My_module.backend import api as my_module_api

# The file already has:
# api = APIRouter(prefix="/api")
# ... existing include_router calls ...
api.include_router(my_module_api.router)
```

Do not create a second `api = APIRouter(prefix="/api")`; that would discard the
existing routers. The module router itself supplies the module prefix:

```python
router = APIRouter(prefix="/my-module", tags=["my-module"])
```

so the final paths are `/api/my-module/...`. Keep `manifest.apiPrefix` in sync.

Optional: add a module endpoint table to `backend/README.md` for operators.

### 3.4 Register the Vue route and sidebar item

Add the import and one route in `frontend/src/router/index.ts`:

```ts
import TemplatePage from '@/features/my-module/TemplatePage.vue'

// inside routes: [
{ path: '/image/my-module', component: TemplatePage, meta: { title: 'My Module' } },
```

The import must match the filename you actually copied. The example keeps the
starter filename for a first run; if you rename the page to `MyModulePage.vue`,
import that name and update `manifest.frontend`.

Add the nav item inside the correct group in `frontend/src/lib/nav.ts`. The file
is grouped; a top-level flat array is wrong:

```ts
{
  id: 'image',
  label: 'Image',
  items: [
    // ... existing image items ...
    { id: 'my-module', label: 'My Module', to: '/image/my-module' },
  ],
},
```

Constraints:

- `manifest.navId` === runtime feature folder === nav item `id`.
- Nav item `to` === Vue route path.
- For a new generation module, put the route under its group segment
  (`/image/my-module`, `/video/my-module`, or `/audio/my-module`). The existing
  `library` and `system` groups use top-level routes (`/gallery`, `/settings`),
  so do not assume the first route segment always equals `NavGroup['id']`; the
  `to` value must match the route exactly. If you need a new group, update the
  `NavGroup['id']` union and the sidebar, not just one item.
- `soon: true` is optional; it does not disable the route.
- The manifest is not read by the router or nav. Keep it in sync by hand.

### 3.5 Copy canonical frontend files into the runtime folder

The canonical files live with the module backend. Create the runtime folder and
copy the six files (the README stays canonical):

```powershell
$repo = (Resolve-Path '.').Path
$src = Join-Path $repo 'backend/app/GenModules/My_module/frontend'
$dst = Join-Path $repo 'frontend/src/features/my-module'
New-Item -ItemType Directory -Force -Path $dst | Out-Null

Get-ChildItem $src -File |
  Where-Object { $_.Name -ne 'README.md' } |
  ForEach-Object { Copy-Item $_.FullName (Join-Path $dst $_.Name) -Force }
```

Hash-check both copies:

```powershell
Get-ChildItem $src -File | Where-Object { $_.Name -ne 'README.md' } | ForEach-Object {
  $a = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
  $b = (Get-FileHash (Join-Path $dst $_.Name) -Algorithm SHA256).Hash
  '{0}: {1}' -f $_.Name, $(if ($a -eq $b) { 'match' } else { 'MISMATCH' })
}
```

If you renamed the page/settings/card files, copy them under the new names and
update the imports in the page/store. The runtime folder is what Vite builds;
the canonical folder is what travels with the module.

### 3.6 Verify before adding features

```powershell
# from backend/
uv run python -c "from app.main import app; print([p for p in app.openapi()['paths'] if 'my-module' in p])"

# from frontend/
npm run typecheck
npm run build
```

Then start the app and verify the full starter path:

1. The route and sidebar item open the page.
2. Generate one job and a batch of two; stages move to done.
3. The SVG results appear on the card, in Gallery, and in the Library.
4. Favorite, per-image trash, per-job delete, and both clear options work.
5. Reload the page: the form and history return; a running job reattaches.
6. Toggle settings on desktop and mobile; each panel resets only its slice.
7. `npm run build` is clean and the backend test suite still passes.

### 3.7 Zero-context acceptance test

If this is your first time seeing the project, do not open `T2I_main` or any
shared component to guess a prop. Follow §3.0–§3.6 using only this guide and
`_template`. The dry-run procedure in §8.5 is the acceptance test for this
document; record any step that forced you to inspect another module or guess an
API, and fix the guide before calling the module portable.

---

## 4. Backend module contract

### 4.1 `manifest.json`

```json
{
  "id": "My_module",
  "navId": "my-module",
  "name": "My Module",
  "group": "image",
  "version": "0.1.0",
  "status": "installed",
  "description": "What this module generates and which engine it uses.",
  "entrypoint": "backend.api:router",
  "apiPrefix": "/api/my-module",
  "frontend": "frontend/MyModulePage.vue",
  "recipeIds": ["my-recipe-v1"],
  "capabilities": ["my-capability"],
  "excludes": []
}
```

- `id` must match the module folder name. The copy must not start with `_`;
  folders beginning with `_` are scaffolding and are ignored by the capability
  registry. `_template` itself is the exception: its placeholder id is
  `template` while the folder is `_template`. An installed copy must use its
  real folder name (for example `My_module`).
- `navId` must match the frontend feature folder and the sidebar item id.
  It is not read by the router or nav; keep all three in sync by hand.
- `group` should match the nav group (`image`, `video`, `audio`, `library`,
  `system`). It is descriptive metadata, not a routing instruction.
- `entrypoint` names the router object (`backend.api:router`). It documents the
  import path; it does **not** mount the router.
- `apiPrefix` documents the final prefix (`/api/<module>`). The router's own
  `APIRouter(prefix=...)` is what FastAPI uses.
- `frontend` points at the canonical page, not the runtime copy. It documents
  where the source lives; it does not add a Vue route. Update it if you rename
  the page.
- `recipeIds`, `capabilities`, and `version` are module metadata for docs,
  tests, and future tooling. They do not generate code. Keep `recipeIds` in
  sync with the backend `RECIPE_ID` if you rename the starter recipe.
- `excludes` documents inputs the module deliberately does not support. For
  strict Text → Image, keep reference-image, identity, edit, and face-swap
  paths out of the API and the Gallery.

The current capability registry reads only the folder name and a few display
fields. Treat the rest of the manifest as a contract with humans and future
tooling, not as runtime wiring. `_template/manifest.json` is the complete
starter example.

#### `requirements.json` (module-owned content manifest)

`requirements.json` is optional. Ship it only when the module needs ComfyUI
custom nodes or model files; Settings → Engine content audits it read-only
against the user's install and the module's `/setup` popup uses the same file.
Delete the file when the module needs nothing. The full schema also lives in
`docs/COMFYUI_CONTENT.md` §2.

```json
{
  "schemaVersion": 2,
  "module": {
    "id": "My_module",
    "label": "My Module",
    "description": "What the user needs before the first run.",
    "nsfw": false
  },
  "groups": [{
    "id": "my-base-group",
    "pack": "my-pack",
    "label": "Base model",
    "mode": "oneOf",
    "required": true,
    "aliases": ["my-family"],
    "why": "Install one base model."
  }],
  "nodes": [{
    "name": "ComfyUI-GGUF",
    "repo": "https://github.com/city96/ComfyUI-GGUF",
    "commit": "<40-char sha>",
    "optional": false,
    "why": "Loads the GGUF base."
  }],
  "models": [{
    "id": "my-base-int8",
    "pack": "my-pack",
    "role": "base",
    "label": "My Base",
    "name": "my_base_int8.safetensors",
    "target": "unet",
    "aliases": ["my_base", "my-family"],
    "required": false,
    "group": "my-base-group",
    "tested": true,
    "nsfw": false,
    "size": 12829186855,
    "url": "https://example.com/my_base_int8.safetensors",
    "pageUrl": "https://example.com/my-model",
    "sha256": "<64 hex chars>",
    "why": "One of the accepted base files."
  }]
}
```

Key rules:

- `schemaVersion` is `2` for the grouped/alias-aware schema. Older files still
  load, so a module without groups keeps working.
- `module` is display metadata. `nsfw` adds a badge; it never hides a download.
- `models[].pack` is the owning pack id. Use one pack or set it explicitly when
  the module has several packs.
- `models[].role` is `base`, `text_encoder`, `vae`, `lora`, `upscaler`, or a
  module-specific role. `target` is the ComfyUI `models/<target>/` folder.
- `models[].required` defaults to `true`; set it to `false` for optional files.
  Do **not** mark one-of group members individually required.
- `groups[].required: true` plus `mode: "oneOf"` makes the group required while
  each member is optional. A satisfied group counts once; absent alternatives do
  not create extra missing-file warnings.
- `groups[].aliases` are a last-resort group match (for example a generic
  `krea2` file). The setup payload reports the matched filename.
- `models[].url` is a direct download when documented. `pageUrl` is the source
  page. Either may be empty for an optional file with no tracked source; the
  popup then says no URL is documented.
- `tested` and `nsfw` are presentation/audit metadata. `size` is bytes.
  `sha256` is optional metadata and is not hashed on every page view.
- `nodes` keeps the existing installer contract (`name`, `repo`, `commit`,
  `optional`, `why`, and optional `package`/`pip`).
- Nothing in this file downloads, installs, moves, or deletes a file.

#### Filename aliases

The user catalog keeps the real downloaded filename. The module binds the real
name into the graph; users never rename files to match a manifest.

Resolution order for a model file:

1. exact catalog id (`catalogId` in `pack/models.json`);
2. exact target + filename, then exact filename;
3. declared aliases (case- and separator-insensitive, extension-insensitive);
4. a separately declared fallback alias, but only for a file no sibling model
   already claimed by a specific alias.

In `pack/models.json`, keep model-specific aliases in `aliases` and generic
ones in `fallbackAliases`:

```json
{
  "id": "my-base-int8",
  "file": "my_base_int8.safetensors",
  "target": "unet",
  "aliases": ["my_base", "my-family", "my_base_v2"],
  "fallbackAliases": ["my-family"],
  "baseGroup": "my-base-group",
  "baseGroupLabel": "My base model",
  "required": false,
  "nsfw": false,
  "textEncoderAliases": ["my_encoder"],
  "vaeAliases": ["my_vae"]
}
```

- `aliases` match a normalized filename token or a multi-part alias such as
  `my_base_v2` whose parts all appear in the name.
- Keep a generic `fallbackAliases` out of `aliases` when another model also
  matches the same family. Otherwise both models can claim one file and the UI
  will show a misleading second match. Use `excludeAliases` on the broad model
  to refuse files that belong to a more specific sibling pack:

```json
{
  "fallbackAliases": ["my-family"],
  "excludeAliases": ["variant-name", "variant-token"]
}
```

- The excluded file stays untouched; it simply cannot satisfy this model. This
  is how T2I_main keeps a generic Krea 2 file in the normal pack while `snofs`
  files go to the SNOFS pack.
- Alias matching applies to the base model, text encoder, VAE, LoRAs, and
  upscalers. Add `*Aliases` fields where the pack schema supports them.
- The resolved loader follows the real filename: a `.gguf` base uses
  `UnetLoaderGGUF`, and a `.safetensors`/`.sft`/`.ckpt` base uses `UNETLoader`.
  A generic alias can therefore bind an official safetensors file without a
  pack edit.
- Catalog entries kept with `present: false` are history, not bindable files.
  They never hide an installed alias, and they never satisfy a one-of group.
- If only one member of a `baseGroup` is installed, the backend selects that
  installed default and the frontend switches a stale saved model to it.

#### First-open setup endpoint

Engine-backed modules should expose `GET /setup` and build it with
`app.common.module_setup.build_setup_payload` (pass the normalized
`requirements.json`, pack metadata, and the user catalog). It returns the module
and pack descriptions, groups, required/optional items, destinations, sizes,
download/source links, NSFW flags, `missingRequired`, and `ready` (`null` when
the catalog is unavailable). The shared `ModuleSetupModal.vue` renders it.

`ready` is deliberately `null`, not `false`, when no user catalog exists: the app
does not know which files are missing yet. Auto-open the modal only when
`ready === false`; always provide a header **Setup** button so the user can
reopen it.

### 4.2 Thin API router

The router should only declare routes, map service exceptions to HTTP, and
return service data. Keep all validation and workflow logic in the service.

Minimum route set for a generation module:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/catalog` | controls, ranges, defaults; engine snapshot when engine-backed |
| `GET` | `/pack` | secret-free pack summary for debug/ops |
| `GET` | `/setup` | engine-backed only: missing required files + links for the shared setup modal |
| `POST` | `/validate` | validate/normalize without creating a job |
| `POST` | `/jobs` | create and start a job |
| `GET` | `/jobs?limit=` | module-scoped history, newest first |
| `GET` | `/jobs/{id}` | one module job |
| `POST` | `/jobs/{id}/cancel` | best-effort cancel |
| `DELETE` | `/jobs/{id}?deleteAssets=true\|false` | delete one terminal job |
| `DELETE` | `/jobs?deleteAssets=true\|false` | clear this module's history |

`_template` implements the generic set except `/setup`; its `/pack` returns the
starter tracked pack summary, and its catalog has no engine snapshot because it
is engine-free. T2I also exposes `POST /enhance` for prompt rewriting previews
and `GET /setup` for its first-open model popup. Add module-specific routes as
needed, but keep the generic job routes above.

Job ids may contain `#` (for example `#145`). Every client must encode ids:

```ts
`/jobs/${encodeURIComponent(jobId)}`
```

and the backend must read the decoded id, not assume it is URL-safe.

### 4.3 Error mapping

Use one decorator/helper around the router. T2I returns:

```json
{
  "detail": {
    "code": "validation_error",
    "message": "Size 2000 is outside this model's safe range 512-1536.",
    "errors": [
      { "code": "out_of_safe_range", "field": "size", "min": 512, "max": 1536 }
    ],
    "warnings": []
  }
}
```

- `422` for validation and active-job conflicts.
- `503` for engine unavailability.
- `500` for pack/workflow/internal failures.
- `404` for unknown jobs outside the module.
- Never leak a stack trace or an absolute file path to the client.

### 4.4 Validation is shared

`/validate` and `/jobs` must call the same normalization service. A GUI range
check is a convenience, never a security or validity boundary.

- The tracked pack defines ranges and defaults.
- The installed catalog supplies file presence and labels.
- Hard limits and safe ranges are distinct.
- Return structured errors; non-fatal warnings may be returned by `/validate`
  or stored in `job.params` for display. There is no separate job `warnings`
  column.
- Do not silently clamp API input. The only allowed clamp is **restoration**
  of a stale saved form, and the user must be told it happened.

#### Defaults and ranges come from the pack

Keep one authoritative JSON source; do not duplicate defaults in Vue. The
starter (`_template`) keeps small UI defaults in
`_template/backend/pack/options.json`. Engine-backed packs such as T2I_main keep
**one editable `defaults.json` per pack** and leave `options.json` for choices:

```text
packs/<pack>/
  defaults.json   modelId, ratio, size, batch, seed, sampling, refine,
                  upscaler and the default LoRA chain
  models.json     bindings plus safe ranges (no defaults needed)
  options.json    recipe, ratios, sampler/scheduler lists, limits
  workflows/*.api.json
```

```json
{
  "modelId": "my-model",
  "ratio": "1:1",
  "size": 1024,
  "batch": 1,
  "sampling": { "steps": 9, "cfg": 2.0, "sampler": "euler", "scheduler": "simple", "denoise": 1.0 },
  "refine": { "steps": 6, "cfg": 2.0, "denoise": 0.45, "scale": 1536 },
  "upscaler": { "id": "latent-refine", "enabled": true, "value": 1536 },
  "loraChain": [{ "id": "my-lora", "strength": 0.6, "on": true }]
}
```

Engine-backed modules add per-model runtime ranges in `pack/models.json`
(T2I shape). A range may omit `default`; the loader then takes it from
`defaults.json`:

```json
{
  "models": [{
    "id": "my-model",
    "ranges": {
      "steps": { "label": "Steps", "min": 8, "max": 20, "step": 1 },
      "cfg": { "label": "CFG", "min": 1.5, "max": 5.0, "step": 0.05 }
    }
  }]
}
```

- `/catalog` returns the active defaults plus the chosen model's cleaned ranges
  and fixed value lists. The GUI binds sliders to `min/max/step/default` and
  selects to only the returned values.
- The same pack values drive backend validation. The frontend clamp is only for
  restoring a stale form; it tells the user when it adjusted something.
- The workflow's literal sampler/size values are **not** defaults: the composer
  rewrites them from `defaults.json` and the request. Do not edit the API
  workflow to change a default.
- The user model catalog supplies installed-file presence and labels, never
  module ranges.

#### Multiple model packs, one module

Use one GenModule when the families share the same page, jobs, library,
history, and API contract. Do **not** clone the module for Flux/Qwen/Krea.

```text
pack/
  registry.json                 { "defaultPack": "krea2", "packs": [...] }
  packs/krea2/
    pack.json                   label, description, nsfw, order
    defaults.json               9 steps / CFG 2.0, size, refine, upscaler, LoRA chain
    options.json                recipe.id, recipe.workflow, recipe.composer
    models.json                 model.packId is added by the loader
    workflows/krea2_t2i.api.json
  packs/krea2-snofs/
    pack.json
    defaults.json               12 steps / CFG 2.5, same graph
    options.json                recipe.workflow may point at ../krea2/workflows/...
    models.json                 may override workflow/composer per model
```

Rules:

1. The registry is the source of truth for pack id, path, and default. `pack.json`
   owns the user-facing label, description, NSFW badge, and order; registry
   label is the fallback.
2. Model ids are unique across all packs; the model selects its pack.
3. A pack owns its workflow. Sibling variants may deliberately share one
   API-format graph by pointing `recipe.workflow` at a path inside
   `backend/pack`; the loader rejects paths that escape that tree. Never add
   another family's nodes to the Krea graph or build a switch-node mega-graph.
4. `catalog.load_packs()` validates every pack; `pack_for_model()` resolves the
   selected model; `workflows.compose_t2i()` dispatches by `composer`.
5. `requirements.json` stays at the module root and covers all packs. It is the
   download/setup manifest, not a per-pack file and not an installer. Set
   `models[].pack` when a module has more than one pack, and give each base
   group its own `pack`/`group` id. Use optional groups when packs are
   alternatives so an uninstalled pack does not block readiness.
6. A model may override `workflow` and `composer` in `models.json` when its
   loader or graph really differs; otherwise it inherits its pack's recipe.
7. Packs share the module API, jobs, library, and page. Add a pack folder and
   registry entry; do not clone the GenModule for each family.
8. Flux/Qwen-style packs are added only after their API graph and model bindings
   are verified; keep unverified families out of the registry.

### 4.5 Jobs and stages

Use `app.jobs.service`. Do not create a parallel job table.

```python
job = jobs.create_job(
    {
        "tab": "my-module",
        "module": MODULE_ID,
        "modelId": model["id"],
        "modelName": model["label"],
        "prompt": request.prompt,
        "params": params,
        "stages": initial_stages,
    }
)
```

Recommended stage shape:

```python
STAGE_DEFS = (
    ("enhance", "Enhance prompt"),
    ("compose", "Compose workflow"),
    ("submit", "Submit to engine"),
    ("generate", "Generate"),
    ("collect", "Collect results"),
)
```

Each persisted stage carries:

```json
{
  "id": "generate",
  "label": "Generate",
  "status": "running",
  "detail": "step 6 / 8",
  "startedAt": 1792831851043,
  "finishedAt": null,
  "durationMs": null
}
```

Statuses are `pending`, `running`, `done`, `error` (the shared type also allows
`skipped`).

Lifecycle:

1. Validate and compose before creating the job, so graph errors do not leave a
   broken row.
2. Create the job, then start the background runner.
3. Patch `status`, `progress`, `stages`, `params` (including the persisted
   engine prompt id), `resultIds`, and `error` through `jobs.update_job`.
   Unknown patch keys are ignored; there is no `warnings` field. Store warnings
   inside `params` if the card needs them.
4. On success, register result files in the library and set `resultIds`.
5. Set a terminal status (`done` or `error`) and finish the stages.
6. On backend restart, reattach to persisted engine prompt ids when possible;
   if it is too late, mark the job failed with an actionable message. See
   §4.9 for the lifecycle hook.
7. If the job fails or is cancelled after some library writes, attach the
   partial asset ids to `resultIds` before marking it failed (or trash them).
   Otherwise the files are orphaned: no job delete or clear can find them.

Cancellation is best-effort. Cancelling an already terminal job is a no-op.
Deleting a live job is always refused.

### 4.6 Deletion ownership: per job and clear history

**A GenModule owns the deletion of its own chat history.** Do not delete
module history through the generic `/api/jobs` routes, and never run a global
history delete from a module page.

Use two distinct module-scoped operations:

```text
DELETE /api/<module>/jobs/{id}?deleteAssets=false   # one generation
DELETE /api/<module>/jobs?deleteAssets=false        # whole module chat
```

Both operations:

- resolve the job through `module=MODULE_ID`;
- refuse `queued`/`running` jobs with `422 job_running`;
- optionally move result assets through `library.trash_asset()`;
- soft-delete the job with `jobs.delete_job()`;
- return the ids that were trashed and those already missing.

Per-job delete (T2I default `deleteAssets=true`):

```json
{
  "id": "#145",
  "deleted": true,
  "assetsTrashed": ["a-123"],
  "assetsMissing": []
}
```

Clear history (T2I default `deleteAssets=false`):

```json
{
  "deleted": 12,
  "jobIds": ["#145", "#144"],
  "assetsTrashed": [],
  "assetsMissing": []
}
```

Clear-history rules:

1. List only this module's jobs. Do **not** call a generic all-module list.
2. Collect every queued/running job before changing anything. If any exist,
   return `422 job_running` and change nothing. Never silently cancel a job the
   user may still want.
3. If `deleteAssets=true`, trash each job's result assets before deleting the
   job. Reuse the library trash path so files remain recoverable.
4. Soft-delete every terminal job. Do not `DELETE FROM jobs`.
5. Deduplicate asset ids across jobs before returning them.
6. Clear the runner maps for cleared job ids and let the frontend stop polling.
7. The operation must be safe to call when the module already has no history:
   return zero counts, not an error.

Why active jobs are rejected:

- The runner could write results into a hidden record.
- Deleting a running job while the engine still owns the prompt can orphan
  work or interrupt an unrelated prompt later.
- The user may prefer to cancel or wait, so the choice belongs to them.

T2I's implementation enumerates up to 10,000 module jobs for clear. The UI may
show a smaller page (60 in T2I), so clear must operate on the backend's full
module history, not just visible cards.

Frontend responsibilities after a successful clear/delete:

- remove the returned ids from the local chat list;
- stop polling those ids;
- release their shared-engine slots;
- sync the library store when assets moved, and also on keep-media clears so
  missing assets disappear from cards;
- sync the generic jobs store for the Jobs page;
- close the media viewer if its current items were cleared;
- show a scope-aware confirmation, not a global one.

The backend is authoritative even if the UI disabled a button. The UI should
disable clear while `busy`, but the API must still reject active jobs.

### 4.7 Library integration

The library is the only owner of generated files. The exact write contract is:

```python
asset = library.add_bytes(
    data,                       # bytes
    filename,                   # e.g. "job-145-1.png"
    *,
    label="Job #145 result 1",  # optional display label
    prompt=prompt,              # original prompt
    model=model_name,           # display model name
    seed=actual_seed,           # int
    tags=["my-module", "recipe-v1"],
    origin_job=job_id,          # "#145"
)
```

`add_bytes` writes the file, creates the library row, and returns the public
asset dict. Use `library.add_file(path, ...)` instead when the engine already
wrote a file. Both accept the same keyword arguments.

- Tag results with the module id, model/recipe, and origin job.
- Return asset ids in `job.resultIds`.
- Serve full media through `GET /api/assets/{id}/file`.
- Serve thumbnails through `GET /api/assets/{id}/thumb`.
- Delete results only through `library.trash_asset(id)`; it returns
  `{"id": ..., "movedTo": ...}` or `None` when the asset is already gone. It
  moves the file to `data/trash` and removes the asset row.
- Never unlink a module result directly from module code.

**Media limitation:** the current library accepts images only: `.png`, `.jpg`,
`.jpeg`, `.webp`, `.bmp`, `.gif`, `.svg`, up to 128 MB. It does not accept audio
or video. If your module generates audio/video, that is a host change, not a
module setting: extend `backend/app/library/service.py` (extensions, asset
`kind`, metadata), the frontend `Asset` type and Gallery filters, and the
viewer handling. Do not save an `.mp4` or `.wav` under a fake image suffix.

The frontend must treat `resultIds` as references, not proof that a file still
exists. If the library has synced and an id is absent, hide the image. If the
library has not loaded yet, a constructed file URL is an acceptable temporary
fallback.

### 4.8 Backend tests

At minimum, cover:

- manifest/pack loading and unknown ids;
- validation and range enforcement through the same service used by `/jobs`;
- workflow composition paths;
- job creation, stage transitions, and error handling;
- result collection into the library;
- cancel behavior;
- per-job delete with and without assets;
- clear history with and without assets;
- clear/delete rejection while queued/running;
- module scoping: another module's jobs are never listed, cleared, or deleted;
- HTTP route contract, including both delete routes.

Run from `backend/`:

```powershell
uv run python -m pytest -q
# Add focused module tests when you have them:
# uv run python -m pytest tests/test_my_module.py -q
```

Run from `backend/` so the `app` package resolves; do not invoke pytest from the
repository root.

### 4.9 Engine-backed modules (ComfyUI / Ollama)

`_template` is deliberately engine-free, so it works without a GPU. When you
replace `_render_svg`, use the shared connector rather than a module-local HTTP
client:

```python
from app import connectors

client = connectors.comfy_client()
submitted = await client.submit_prompt(workflow)
prompt_id = str(submitted["prompt_id"])
jobs.update_job(job_id, {"params": {**job["params"], "enginePromptId": prompt_id}})
```

`ComfyUIClient` (from `app.connectors.comfyui`) exposes:

| Method | Purpose |
| --- | --- |
| `system_stats()` | Engine/GPU snapshot |
| `queue()` | Running/pending queue |
| `object_info()` / `object_info_node(name)` | Node schemas for catalog checks |
| `submit_prompt(prompt, client_id=None, timeout=60)` | Return `prompt_id`; raises on node errors |
| `history(prompt_id)` | Outputs for a completed prompt |
| `view(filename, subfolder="", type="output")` | Download output bytes |
| `queue_delete(prompt_id)` | Remove a pending prompt |
| `interrupt()` | Interrupt the currently running prompt |
| `free(unload_models=True)` | Free ComfyUI models |

Rules:

- Persist `enginePromptId` in `job.params` as soon as submit returns.
- Poll `history()` with a bounded timeout; download with `view()` and register
  bytes through `library.add_bytes`.
- Cancel is best-effort. Prefer `queue_delete()` for a pending prompt and
  `interrupt()` for the current one; never interrupt a prompt that another job
  started.
- Do not call `free()` as part of the Ollama unload toggle. ComfyUI manages its
  own cache; a global free can disrupt unrelated jobs.
- Ollama unload is `await connectors.unload_ollama(model)` and returns
  `{"ok": bool, "message": str}`. Treat failure as non-fatal.

**Restart/resume is a host hook, not auto-discovery.** `T2I_main` is wired in
`backend/app/main.py`: startup calls `t2i_service.resume_pending_jobs()` and
shutdown calls `t2i_service.shutdown()`. An engine-backed module that can resume
must add its own import and calls there. The template needs no hook because it
has no engine; it marks stale `running` jobs as failed in `get_job`/`list_jobs`.

**Readiness is live.** `connectors.status_snapshot()` feeds `GET /api/status` and
the shared frontend engine store. Do not add a module-local status poller or a
second queue counter. See §5.5 and Appendix A.3.

Use `T2I_main/backend/workflows.py`, `catalog.py`, and the runner sections of
`service.py` as references for graph composition and output collection. Copy
the patterns, not the Text → Image business rules.

---

## 5. Frontend module contract

### 5.1 Canonical and runtime files

Canonical files live beside the backend and travel with the module. Runtime
files are copied into `frontend/src/features/<nav-id>/`.

`_template/frontend/` is the complete zero-context starter. Its six files are:

```text
types.ts                      wire types, catalog, job record
api.ts                        typed fetch client + asset URLs
store.ts                      persistence, catalog, jobs, polling, delete/clear
TemplatePage.vue              header, chat, composer, settings, viewer
TemplateSettingsPanel.vue     output + renderer cards, resets, autosave
TemplateGenerationCard.vue    prompt bubble, stages, results, actions
```

`_template/frontend/README.md` explains which parts to replace. A real module
renames the three components (recommended) and the module identity; internal
`Template*` type names may stay for the first run.

Both copies use the same `@/` imports for shared app code. Do not import from
`backend/` at runtime and do not put module-specific settings inside shared
components.

| File | Owns | Do not put here |
| --- | --- | --- |
| `types.ts` | Camel-case wire types, catalog, job params | Vue state, fetch calls |
| `api.ts` | Same-origin fetch, error normalization, URL encoding | persistence, polling timers |
| `store.ts` | Form, persistence, catalog reconciliation, job history, polling, delete/clear | DOM refs, drawer state, viewer state |
| `*Page.vue` | Layout, transient UI, composer, viewer owner | durable form state or backend calls |
| `*SettingsPanel.vue` | Controls bound directly to the store, panel resets | job creation |
| `*GenerationCard.vue` | One job's presentation, stages, result actions | global polling or catalog load |

#### Shared module setup modal

Engine-backed modules should reuse
`frontend/src/components/content/ModuleSetupModal.vue` instead of building their
own first-run dialog. The page owns only transient state:

```ts
const setupOpen = ref(false)
const setupPayload = ref<ModuleSetupPayload | null>(null)
const setupLoading = ref(false)
const setupError = ref('')

async function loadSetup(openWhenMissing = false): Promise<void> {
  setupLoading.value = true
  setupError.value = ''
  try {
    setupPayload.value = await api.getSetup()
    if (openWhenMissing && setupPayload.value.ready === false) setupOpen.value = true
  } catch (err) {
    setupError.value = store.errorText(err)
  } finally {
    setupLoading.value = false
  }
}
```

- Fetch once on page mount and auto-open only when `ready === false`.
- Keep a **Setup** header button that reopens the modal and refreshes the check.
- The modal shows module/pack descriptions, missing required files and folders,
  one-of groups and their members, an optional-files disclosure, direct
  download/source links, sizes, and NSFW tags. It never downloads, installs,
  moves, or deletes anything.
- The shared contract lives in `frontend/src/types.ts`
  (`ModuleSetupPayload`, `ModuleSetupPack`, `ModuleSetupGroup`,
  `ModuleSetupItem`, `ModuleSetupMissingGroup`). Do not re-declare a private
  copy in a module.
- Add the canonical page/settings changes under the module's `frontend/` folder,
  then copy them into `frontend/src/features/<nav-id>/` exactly as §3.5 says.

### 5.2 The store owns durable state

The page owns transient UI only: drawer open, viewer open/index, scroll
position, open popovers. The module Pinia store owns:

- form fields and catalog reconciliation;
- persistence to `genai.<module>.form.v1`;
- selected model/defaults and panel resets;
- prompt enhancement selection and approved preview;
- job history order and polling;
- generation, cancel, delete, clear, reuse, and seed actions;
- library and generic-jobs synchronization;
- live readiness computed from the shared engine store.

Persistence pattern:

```ts
const STORAGE_KEY = 'genai.my-module.form.v1'

function schedulePersist(): void {
  if (saveTimer !== undefined) window.clearTimeout(saveTimer)
  saveTimer = window.setTimeout(persistNow, 180)
}

watch(form, schedulePersist, { deep: true })
window.addEventListener('beforeunload', persistNow)

// Multi-tab safety: adopt a newer saved form instead of leaving this tab with
// stale defaults that overwrite it on the next edit. persistNow() should skip
// the write when the stored form is already identical (no echo loop).
window.addEventListener('storage', (event) => {
  if (event.key !== STORAGE_KEY || !event.newValue) return
  // merge the new payload into the reactive form, then reconcile
})
```

Store payload:

```json
{
  "version": 1,
  "savedAt": 1792831851043,
  "form": { "...": "..." }
}
```

Rules:

1. Read and validate the payload defensively; merge only known keys with the
   correct primitive types.
2. Start from pack defaults for missing keys.
3. Debounce writes (~150–250 ms) and flush on `beforeunload` and page unmount.
4. After the catalog loads, reconcile restored values:
   - unknown model/ratio/sampler/LoRA/upscaler → fallback;
   - incompatible LoRAs removed; limits enforced;
   - stale ranges clamped;
   - prompts, seed, and valid preferences preserved;
   - one visible notice if the restored form changed.
5. Never persist secrets, API keys, or absolute server paths.
6. Bump the version when a field's meaning changes; migrate or start fresh
   rather than guessing.
7. **Persist deliberate switches immediately.** A LoRA on/off toggle must call
   `persistNow()` directly, not wait for the debounce. A rebuild or reload can
   otherwise race the timer and make the form look reset.
8. **A saved LoRA chain is authoritative, including zero active entries.** An
   all-off chain is normally stored as five entries with `on: false`, not an
   empty array. Never re-apply `defaults.loraChain` on startup, catalog
   refresh, or model reconciliation. Default chain values are used only on the
   first visit, an explicit panel reset, or global reset.
9. **Sync tabs, but never echo.** On a `storage` event, merge the incoming form
   and reconcile it. In `persistNow()`, compare the current form with the saved
   payload and skip the write when they are identical. Without that guard two
   tabs can ping-pong saves and a stale tab can silently resurrect defaults.
10. **Retry a failed write.** A transient `localStorage` failure must not
    disable autosave for the rest of the session; surface the error and try
    again on the next change.

### 5.3 Per-panel and global reset

Every settings panel gets its own reset, and the page gets one global reset.
Implement both centrally in the store:

```ts
function resetPanel(panel: ModulePanel): void {
  switch (panel) {
    case 'prompt': /* negative prompt + approved preview */ break
    case 'output': /* model + ratio + size + batch + seed */ break
    case 'loras': /* default chain + triggers */ break
    case 'enhance': /* provider/model/fallback + custom prompt */ break
    case 'sampling': /* sampling defaults */ break
    case 'upscale': /* path + value + enabled */ break
    case 'advanced': /* runtime handoff toggles (unload = true) */ break
    case 'all': /* all defaults; clear composer prompt */ break
  }
  persistNow()
}
```

A panel reset must not clear unrelated slices. The global reset should confirm
because it can clear the prompt and approved enhancement. Put panel reset
buttons in the `<summary>` and use `@click.prevent.stop` so clicking the reset
does not toggle the `<details>`.

### 5.4 API client

- Same-origin base only (`/api/<module>`); no CORS or base URL setting.
- Encode every job id.
- Normalize FastAPI validation, detail objects, and transport errors into one
  typed error class carrying `status`, `code`, `errors`, and `warnings`.
- Provide an `AbortSignal` for catalog, validate, and enhancement requests that
  the page can cancel.
- Implement both module-scoped deletes explicitly:

```ts
async clearHistory(deleteAssets = false): Promise<ClearResult> {
  return request(`/jobs?deleteAssets=${deleteAssets ? 'true' : 'false'}`, {
    method: 'DELETE',
  })
}

async deleteJob(jobId: string, deleteAssets = true): Promise<DeleteResult> {
  return request(
    `/jobs/${encodeURIComponent(jobId)}?deleteAssets=${deleteAssets ? 'true' : 'false'}`,
    { method: 'DELETE' },
  )
}
```

### 5.5 Live engine readiness

Readiness must be live state, not a one-time catalog snapshot. A user can start
ComfyUI or Ollama while the page is open, and Generate must recover without a
browser reload.

Source of truth: the shared `engine` Pinia store, fed by `GET /api/status`.

```ts
const comfyReady = computed(() => engine.comfy.connected === true)

const providerReady = computed(() => {
  if (form.enhanceProvider === 'ollama') return engine.ollama.connected === true
  return comfyReady.value
})

const canGenerate = computed(
  () =>
    catalog.value != null &&
    form.prompt.trim().length > 0 &&
    !busy.value &&
    !enhancing.value &&
    selectedModel.value != null &&
    selectedModel.value.ready !== false &&
    comfyReady.value &&
    (!form.enhanceEnabled ||
      form.approvedPrompt.trim().length > 0 ||
      form.fallbackToOriginal ||
      providerReady.value),
)
```

If the catalog carries more than connectivity (installed text models, missing
files, warnings), refresh it when connectivity changes. Debounce the refresh
and compare against the catalog's snapshot first:

```ts
watch(
  [() => engine.comfy.connected, () => engine.ollama.connected],
  ([comfy, ollama]) => {
    const snapshot = catalog.value?.engine
    if (!snapshot) return
    if (snapshot.comfyui.connected === comfy && snapshot.ollama.connected === ollama) return
    window.clearTimeout(engineCatalogTimer)
    engineCatalogTimer = window.setTimeout(() => {
      if (catalog.value) void loadCatalog()
    }, 450)
  },
)
```

UI expectations:

- Header badge shows checking, ready, or offline from the live store.
- Generate enables as soon as the engine is ready and the other conditions
  pass.
- Do not cache readiness in localStorage.
- Do not require a route switch or reload after an engine starts.
- The shared top bar and module should agree; use the shared engine store
  rather than a module-local polling loop.

### 5.6 Job polling, reattachment, and engine accounting

1. Build the complete request from the form.
2. Call `/validate` for preflight warnings.
3. `POST /jobs`; append the returned record in chat order.
4. Mark the job active in the shared engine store exactly once.
5. Poll `GET /jobs/{id}` every ~750–2000 ms while `queued`/`running`.
6. On terminal status:
   - replace the card;
   - keep any warnings returned by validation in the store/params;
   - release the engine slot;
   - sync the library and generic jobs stores;
   - stop polling.
7. On page load, list recent jobs, reverse the API's newest-first list once,
   reattach polling, and mark running jobs active.
8. On 404, drop the local job and release its engine slot.
9. On transient polling failures, keep retrying with backoff. Do not pretend
   the job finished. Surface a retry warning after repeated failures.
10. On route switch, leave polling alive in the store. The job is
    backend-owned and must continue after the page unmounts.
11. Keep a deduplicated set of tracked job ids in the store so create, reattach,
    cancel, delete, and clear cannot double-count the shared queue.

Cancellation is best-effort. Finished jobs are a no-op.

### 5.7 Deletion UI and module-owned controls

Deletion must be visible and owned by the module. Do not rely on the generic
Jobs page to remove chat records.

**Per-generation delete** — terminal cards get a visible Delete control and a
small menu:

- `Remove message only` → `deleteAssets=false`; images stay in the Library.
- `Delete message + images` → `deleteAssets=true`; result assets move to the
  library trash.

**Per-image trash** — each result image gets a trash overlay action. It calls
`library.trash(assetId)`, not a job deletion. The chat message remains, but the
image disappears from the Library and from the card after sync. Treat the
library cache as authoritative, not the job's `resultIds`.

**One deletion affordance per scope.** Do not repeat the same delete action in
the card action row and the shared `MediaViewer`. T2I's viewer action slot is
favorite-only; per-image deletion stays on the card overlay, and the
per-generation Delete menu stays in the card action row. If a module chooses a
viewer trash action, remove the card overlay (or vice versa) instead of offering
both. The fullscreen viewer must not become a second deletion surface.

**Clear chat** — header menu with exactly two options:

- `Clear chat` → clear history, keep all media.
- `Clear chat + media` → clear history and move result images to library trash.

Do not mention counts of only the loaded page in the confirmation. The backend
clears the full module history, which can be larger than the visible page. Use
scope wording such as:

```text
Clear all My_module chat messages? Their result images stay in the Library.
Clear all My_module chat messages and move their result images to the library
trash? This only affects My_module.
```

`AppPopover` does not toggle its own trigger. Every trigger must update the
bound open flag:

```vue
<AppPopover v-model="clearMenuOpen" align="right">
  <template #trigger>
    <button
      type="button"
      :disabled="!jobs.length || clearing"
      @click="clearMenuOpen = !clearMenuOpen"
    >
      Clear
    </button>
  </template>
  <!-- options -->
</AppPopover>
```

Without that click handler, the menu never opens. Apply the same rule to the
per-generation Delete menu and every other `AppPopover`.

### 5.8 Custom enhancement system prompts

Modules that rewrite prompts with a text model should let the user override the
system prompt without editing backend settings. T2I exposes this as
“Advanced · enhancement brief”.

Request field:

```ts
interface EnhanceRequest {
  prompt: string
  provider?: 'ollama' | 'comfyui' | null
  model?: string | null
  systemPrompt?: string | null
  maxLength?: number | null
  temperature?: number | null
}
```

Both the preview endpoint and a generation job use the same semantics:

- `systemPrompt` omitted or `null` → use the backend default from
  `settings.prompts[<systemPromptKey>]`.
- A non-empty string → use that custom brief for preview and generation.
- An explicit empty string is a valid override that suppresses the default.
  The UI avoids that ambiguity by sending `undefined` when its textarea is
  empty.

Frontend behavior:

```ts
const customSystemPrompt = computed(
  () => store.form.enhanceSystemPrompt.trim().length > 0,
)

// Preview:
systemPrompt: form.enhanceSystemPrompt.trim() || undefined

// Job request:
enhance: {
  enabled: form.enhanceEnabled,
  provider: form.enhanceProvider,
  model: form.enhanceModel || undefined,
  systemPrompt: form.enhanceSystemPrompt.trim() || undefined,
  fallbackToOriginal: form.fallbackToOriginal,
  unloadAfter: form.unloadEnhanceModel,
}
```

- Persist the custom prompt with the module form.
- Empty textarea means “backend default”; show that label in the UI.
- Provide a “Load cards template” action with a structured brief. A good
  template asks the model to build cards for intent, character, wardrobe/props,
  scenery, camera, lighting/color, and style/finish, then return one prompt.
- Provide “Use backend default” to clear the override.
- Show the resolved backend default in a read-only preview.
- Use the same character/wording budget as the main prompt if the module has
  one.
- Invalidating rules: changing the source prompt **or** the system prompt must
  abort an in-flight preview and clear any approved rewrite. Never approve a
  rewrite generated for different input or a different brief.
- The approved rewrite is consumed by the next generation and then cleared.
- Store the resolved system prompt in job params so the result card can show
  what was actually used.

### 5.9 Unload the text model before image generation

Prompt enhancement and image generation compete for the same GPU. Ollama keeps
a text model resident after a rewrite; if ComfyUI then loads the diffusion
model, VRAM pressure slows generation. Modules that enhance prompts should
offer a default-on **Unload enhancement model** toggle in the settings drawer
and honor it for both previews and queued jobs.

Contract:

```ts
// job request, inside enhance
enhance: { unloadAfter: true }

// POST /enhance
{ prompt, provider, model, systemPrompt, unloadAfter: true }
```

- Persist the toggle as a form field (`unloadEnhanceModel`) and reset it to
  `true` with the enhancement/advanced panel resets and global reset.
- Send the same value on the preview request and the job request.
- On Reuse, restore `params.enhance.unloadAfter`, defaulting to `true` for
  older jobs that predate the field.

Backend behavior:

- Unload only the model that was just used, through the shared
  `connectors.unload_ollama(model)` service. It checks `/api/ps` first, so it
  can never cause a model load.
- Do **not** call a global ComfyUI free as part of this toggle. ComfyUI manages
  its own model cache, and a global free can disrupt unrelated jobs.
- Unload on the Ollama success path and best-effort on the failure path. A
  preview must still return the rewrite when the unload fails.
- Send Ollama `think: false` for the rewrite. A thinking model otherwise spends
  the whole `num_predict` budget in `thinking` and returns an empty `response`;
  non-thinking models and older servers ignore the field.
- Preview `maxLength` is a **token** cap (1–512), not the prompt character
  limit. Omit it to use the backend default; never send
  `limits.promptMaxChars` (often thousands) or the preview returns 422.
- The job runner records `unloadError` in job params and appends an
  `enhance_unload_failed` warning, then continues to compose and submit. The
  image job must not fail because the VRAM handoff failed.
- Surface the result in the enhance stage detail (`text model unloaded` or
  `unload failed`).

Frontend behavior:

- Put the toggle at the bottom of the drawer in a distinct **Advanced** runtime
  card. Default it on, give it its own reset, and show a clear On/Off badge.
- On the enhancement preview, show a small `text model unloaded` note or
  `unload failed · prompt kept` warning.
- Explain that only Ollama text models are unloaded; ComfyUI text models are
  left for ComfyUI to manage.

Tests:

- default-on normalization and explicit opt-out;
- preview calls the unload service with the resolved model;
- job pipeline passes the flag and records a non-fatal warning on failure.

### 5.10 Shared `StageTimeline`

Do not rebuild the stage list per module. Import the shared component:

```vue
<script setup lang="ts">
import type { Stage } from '@/types'
import StageTimeline from '@/components/chat/StageTimeline.vue'

defineProps<{ stages: Stage[] }>()
</script>

<template>
  <StageTimeline :stages="stages" />
</template>
```

`StageTimeline` renders:

- `done` → success check;
- `running` → spinning accent loader;
- `error` → danger cross;
- `pending` (and `skipped`) → neutral circle;
- `label`, optional `detail`, and optional `durationMs` in seconds.

The backend owns stage ids, labels, status, detail, and timing. The card maps
its wire stages to the shared `Stage` shape if needed.

Use it for queued/running jobs, failed jobs with stages, and the generic Jobs
page. Keep progress bars and cancel controls in the module card; the timeline is
presentation only.

### 5.11 Settings cards that are visually distinct

Settings panels use `<details>` cards bound directly to the store form. The
reference design creates clear separation in both themes:

```vue
<details
  class="group overflow-hidden rounded-xl border border-l-2 border-border
         border-l-sky/60 bg-surface shadow-sm
         open:ring-1 open:ring-accent/20"
>
  <summary
    class="flex cursor-pointer list-none items-center gap-2 border-b
           border-border/80 bg-surface-2/75 px-3.5 py-2.5
           transition-colors hover:bg-surface-2
           [&::-webkit-details-marker]:hidden"
  >
    <span class="h-2 w-2 rounded-full bg-sky" />
    <span class="text-xs font-semibold">Section title</span>
    <span class="truncate text-[10px] text-muted">Current value</span>
    <button
      type="button"
      class="ml-auto ..."
      title="Reset section"
      @click.prevent.stop="reset('section')"
    >
      <!-- reset icon -->
    </button>
    <!-- chevron -->
  </summary>

  <div class="space-y-3 bg-surface px-3.5 py-3">
    <!-- controls -->
  </div>
</details>
```

Requirements:

- Visible border plus a colored left rail or accent dot.
- Header surface differs from the card body surface.
- Clear spacing between cards (`space-y-3` or larger), not one undifferentiated
  column.
- Open state gets a subtle accent ring.
- Use semantic theme tokens (`border-border`, `bg-surface`, `bg-surface-2`,
  `text-muted`, accent colors) in both light and dark themes.
- Bind controls directly to `store.form`; do not copy into a local form object
  that can drift.
- Use `AppSelect`, `AppSwitch`, `AppSlider`, and `AppButton` for consistency.
- Keep the upscale on/off and enhancement on/off controls visible in the
  composer; do not bury them behind collapsed advanced sections.
- The settings panel edits state only. It must not start jobs.

---

## 6. Compact chat workspace layout

T2I's page is the reference layout:

```text
┌ header: module id/title · live engine badge · model chip · Gallery · Clear · Settings ┐
├─────────────────────────────────────────┬─────────────────────────────────────────────┤
│ chat scroller                           │ settings drawer                              │
│  user prompt bubble                     │  Output                                      │
│  result card (progress, stages, images) │  Upscale                                     │
│  ...                                    │  LoRA chain                                  │
│                                         │  Enhancement (+ advanced brief)              │
│                                         │  Sampling                                    │
│                                         │  Prompt extras                               │
├─────────────────────────────────────────┤  Advanced (runtime)                           │
│ composer: textarea + quick chips        │  Reset all                                   │
│ [settings] [Generate]                   │                                              │
└─────────────────────────────────────────┴─────────────────────────────────────────────┘
```

### 6.1 Header

- Module id/eyebrow and human title.
- Live ComfyUI/provider readiness from the shared engine store.
- Selected model chip.
- Gallery link.
- Clear-chat menu, disabled when there is no history or while clearing.
- Settings toggle.
- On desktop the settings drawer defaults open; on mobile it is a fixed
  overlay with a backdrop.

### 6.2 Composer

- Prompt textarea; `Ctrl+Enter`/`Meta+Enter` generates. Plain Enter is a
  newline.
- Character counter and autosave label.
- Quick chips open the matching settings panel: model, ratio/size, LoRA count,
  **upscale on/off**, enhancement on/off.
- Upscale must be visibly switchable here. Turning it off preserves the last
  non-none path; selecting `none` also turns the switch off.
- Action group stays right-aligned with `ml-auto`.
- Disable Generate when: prompt empty, catalog missing, model missing/not
  ready, ComfyUI offline, enhancement requested while its text provider is
  offline unless an approved rewrite or fallback is ready, enhancement in
  flight, or another job is active.
- A live engine badge must recover without reload; see §5.5.

### 6.3 Chat messages

Every job is a chat turn, oldest → newest:

- right-aligned user bubble with prompt and compact time/model/ratio/batch
  chips;
- left-aligned result card with status dot, job id, time, and progress;
- queued/running: progress bar, shared `StageTimeline`, Cancel;
- error: readable message and stages;
- done: result grid, favorite/fullscreen actions, any params warnings, settings
  disclosure;
- actions: View, Reuse, Use seed, Download, More menu;
- Delete menu: `Remove message only` / `Delete message + images`;
- per-image trash overlay;
- the shared `MediaViewer` action slot is favorite-only; per-image deletion is
  on the card overlay, and chat-level deletion is the card menu above;
- settings disclosure shows every applied setting, the prompt used, negative
  prompt, actual seed, final size, upscale/enhancement summaries, and timing.

Do not hide the actual seed or final dimensions behind stale form values; use
the job params.

### 6.4 Settings drawer

- Desktop static column (~380–400 px); mobile fixed overlay.
- Every section is a distinct card with its own reset (see §5.11).
- Prompt and negative prompt fields live here or in the composer as the module
  design requires, but there must be one owner.
- Enhancement panel: provider/model, fallback toggle, preview/cancel, approved
  prompt, and the advanced system-prompt editor.
- Sampling panel: base and refine settings as applicable.
- Upscale panel: path select, enabled switch, value slider, recommended range.
- LoRA chain: compatibility-filtered list, add/remove, per-LoRA strength and
  switch, auto-trigger injection, count/limit.
- Prompt extras: trigger words, negative prompt, character budget.
- Advanced (runtime): default-on unload of the Ollama enhancement model before
  ComfyUI loads the image model. Explain previews, queue jobs, and non-fatal
  failures; keep the toggle out of the collapsed enhancement-brief editor.
- Footer has the confirmed global reset and the autosave status.

---

## 7. Library, Gallery, and `MediaViewer`

### 7.1 Sync rules

- After every terminal job, call `library.syncFromBackend()`.
- After any asset trash or history clear, sync again.
- Gallery syncs on mount and has a visible Refresh button; do not rely on
  app-startup sync alone.
- Sync the generic jobs store after create, terminal status, delete, and clear
  so the Jobs page is current.
- Search in Gallery should cover prompt, label, model, tags, job id, and seed.
- A strict Text → Image Gallery must not offer “use as reference.” Do not
  reintroduce an input path the module excludes.

### 7.2 Missing assets

`resultIds` can outlive the files. After the library has synced, an absent id
means the image was removed. Hide it; do not render a broken fallback URL.
Before the first successful library sync, a constructed `/api/assets/{id}/file`
URL is acceptable for optimistic rendering.

A library row can also exist while its backing file is missing (for example,
someone deleted a file from disk). That produces a 404 from the asset endpoint.
Treat this as a library integrity problem: re-sync, prune server-side if the
product supports it, and handle image `error` events. Do not construct a second
URL that hides the failure.

### 7.3 Shared viewer

Use `frontend/src/components/media/MediaViewer.vue` and
`MediaViewerItem` from `frontend/src/components/media/types.ts`.

```ts
import type { MediaViewerItem } from '@/components/media/types'

const items: MediaViewerItem[] = [
  {
    id: 'a-1808e246b5',
    url: '/api/assets/a-1808e246b5/file',
    thumbUrl: '/api/assets/a-1808e246b5/thumb',
    kind: 'image',
    label: 'Job #145 · result 1',
    prompt: 'An orange cat on a table',
    filename: 'job-145-1.png',
    meta: [
      { label: 'Model', value: 'SNOFS-Krea2_Q8' },
      { label: 'Seed', value: '2300737279' },
      { label: 'Size', value: '1536 × 1536' },
    ],
  },
]
```

```vue
<MediaViewer
  v-model:open="viewerOpen"
  v-model:index="viewerIndex"
  :items="viewerItems"
  title="Job #145"
>
  <template #actions="{ item }">
    <button v-if="item" @click="toggleFavorite(item)">Favorite</button>
  </template>
  <template #info="{ item }">
    <p v-if="item">Module-specific metadata</p>
  </template>
</MediaViewer>
```

For T2I, the viewer action slot is **favorite-only**. Per-image trash is the
card overlay and per-generation delete is the card menu; do not add a third
trash control to the viewer. Gallery may keep its own trash action because it
has no generation card, but a module page should not duplicate the same action.

Props: `items`, `title`, `downloadable` (default true), `showThumbs` (default
true), `info` (default true). Models: `open`, `index`. Slots: `actions(item)`,
`info(item)`. Event: `close`.

Built-in keys while open:

| Key | Action |
| --- | --- |
| `Escape` | exit fullscreen, otherwise close |
| `←` / `→` | previous / next item |
| `+` / `-` | zoom in / out |
| `0` | reset zoom |
| `F` | toggle fullscreen |

Parent responsibilities:

- Build URLs from asset ids, never from hardcoded absolute paths.
- Own the item list and update it after favorite/trash.
- Remove deleted items and close the viewer when it becomes empty.
- Keep `index` valid after removal.
- If an image is removed from the Library, remove it from both the viewer and
  the card fallback list.
- Pass module-specific metadata through `meta` or the `info` slot. Do not put
  module settings logic inside the viewer.

The viewer deliberately uses a dark lightbox in both themes; that is the
documented exception to semantic theme tokens for app chrome.

---

## 8. Verification

### 8.1 Automated checks

From `frontend/`:

```powershell
npm run typecheck
npm run build
```

`npm run build` runs `vue-tsc --noEmit` and Vite. Fix type errors before
runtime smoke tests.

From `backend/`:

```powershell
uv run python -m pytest -q
# If you added focused module tests, run them directly too:
# uv run python -m pytest tests/test_my_module.py -q
```

### 8.2 Live route check

With the backend running, confirm both delete routes are actually loaded:

```powershell
$spec = Invoke-RestMethod http://127.0.0.1:8766/openapi.json
$spec.paths.'/api/my-module/jobs'.PSObject.Properties.Name -join ','
$spec.paths.'/api/my-module/jobs/{job_id}'.PSObject.Properties.Name -join ','
```

The first must include `delete`; the second must include `get`, `delete`, and
the cancel route separately. A live OpenAPI check is important because a
running uvicorn process without `--reload` can serve old routes after code
changes.

### 8.3 Browser smoke checklist

- [ ] Route and nav item open the module; no console errors.
- [ ] Light and dark themes both show distinct settings cards with visible
      borders and header/body separation.
- [ ] Every settings panel resets only its own slice; global reset confirms.
- [ ] Prompt/settings survive route switches and reloads.
- [ ] A saved 0-active LoRA chain survives reload, a frontend rebuild, and a
      backend restart. A second tab cannot resurrect the pack default chain.
- [ ] Custom enhancement prompt loads the cards template, persists after reload,
      and “Use backend default” clears it.
- [ ] The Advanced runtime card defaults the unload toggle on, persists it,
      resets it to on, and shows the preview “text model unloaded” / failure
      note. A failed unload leaves the rewrite and the image job intact.
- [ ] Starting/stopping the engine flips the header badge and Generate
      availability without reloading. Restore the engine state afterwards.
- [ ] Clear menu opens, states module scope, and is disabled while busy.
- [ ] Per-generation Delete menu opens and shows both options.
- [ ] Per-image trash overlay opens the confirmation and updates the Library.
- [ ] `StageTimeline` shows pending/running/done/error stages during a job.
- [ ] New results appear in chat, Library, Gallery, and the generic Jobs page.
- [ ] `MediaViewer` opens, navigates, zooms, favorites, and closes when its
      list becomes empty. The T2I viewer has no duplicate trash action; image
      deletion remains on the card overlay.
- [ ] No hardcoded localhost URLs or cross-module fetches.
- [ ] Canonical and runtime files hash-match.

### 8.4 Do not destroy real data while smoke testing

Use throwaway jobs/assets for destructive tests. If the live module already has
user history, verify the menu and confirmation text but do not execute a clear.
Backend tests should cover the destructive path against temporary rows.

### 8.5 Zero-context dry run (acceptance test for this guide)

Run this in a throwaway worktree or a copy of the repo. The goal is to prove
that a new agent can ship a working module from this guide plus `_template`
without reading `T2I_main` or guessing a shared prop.

1. Copy `_template` to `Smoke_module` exactly as in §3.2.
2. Apply the minimum identity changes from §3.2; keep internal `Template*`
   symbols if you like.
3. Apply all three host edits from §3.3–§3.4. Do not skip the nav group.
4. Copy the six canonical files to `frontend/src/features/smoke-module`.
5. Run:
   ```powershell
   # backend/
   uv run python -c "from app.main import app; print([p for p in app.openapi()['paths'] if 'smoke-module' in p])"
   uv run python -m pytest -q
   # frontend/
   npm run typecheck
   npm run build
   ```
6. Start the app with a throwaway data directory:
   ```powershell
   $env:GENAI_DATA_DIR = Join-Path $env:TEMP "genai-smoke-$([guid]::NewGuid())"
   ```
   Generate a batch of two; verify stages, SVG results, Library/Gallery sync,
   favorite, per-image trash, per-job delete, both clear options, reload
   persistence, and the desktop/mobile settings drawer.
7. Record every point where you had to open another module, inspect a shared
   component to learn a prop, or guess a host behavior. That is a documentation
   bug, not an acceptable shortcut.
8. Remove the smoke module, its route/nav entries, and the throwaway data
   directory. Do not leave smoke rows in the real database.

If this dry run fails, the guide is not portable yet. Fix the guide or the
starter before adding features.

---

## 9. Portable module checklist

Copy this list into the module PR or README and keep it current. Items marked
**(engine)**, **(enhancement)**, **(LoRA)**, or **(T2I)** are only required when
your module uses that feature; the starter path does not.

### Backend

- [ ] Chose `_template` or `T2I_main`; did not mix them.
- [ ] Folder and `manifest.json` use the same module id (no leading `_`).
- [ ] Manifest has `id`, `navId`, `name`, `group`, `version`, `status`,
      `description`, `entrypoint`, `apiPrefix`, `frontend`, `recipeIds`,
      `capabilities`, and `excludes`; ids/prefixes are consistent.
- [ ] `requirements.json` exists only if needed and is valid.
- [ ] Router is thin and added to `backend/app/api/__init__.py` with an import
      plus one `include_router`; the existing `api` object is not replaced.
- [ ] Validation and execution use the same service normalization.
- [ ] **(pack)** Pack ranges are authoritative; installed catalog supplies
      presence only.
- [ ] Jobs use `app.jobs.service`; `stages`, `params`, and `resultIds` are
      persisted through the documented patch keys.
- [ ] Results use `app.library.service` and return asset ids.
- [ ] The module's media kind is supported by the library. Current library is
      image-only; audio/video requires a host change.
- [ ] Per-job delete is module-scoped, rejects active jobs, and soft-deletes.
- [ ] Clear history is module-scoped, rejects active jobs, and returns ids.
- [ ] Both delete variants support `deleteAssets` through library trash.
- [ ] No global/all-module history deletion is called from this module.
- [ ] **(engine)** Engine calls use `connectors.comfy_client()`, persist
      `enginePromptId`, and resume/shutdown via the `main.py` hook.
- [ ] **(enhancement)** Enhancement can unload its Ollama text model before
      image generation; the unload is best-effort and never fails the job.
- [ ] **(recommended)** Tests cover validation, stages, collection, cancel,
      per-job delete, clear, active rejection, module isolation, and any
      enabled feature. `_template` ships no module-specific tests; run the
      host suite first, then add focused tests before shipping a real module.

### Frontend

- [ ] Vue route added to `frontend/src/router/index.ts`.
- [ ] Nav item added inside the correct group in `frontend/src/lib/nav.ts`;
      `navId`, feature folder, item id, and `to` match.
- [ ] Canonical files exist under the module's `frontend/`.
- [ ] Runtime copies are byte-identical and hash-checked.
- [ ] Store owns persisted form state and reconciles it after catalog load.
- [ ] Per-panel resets and confirmed global reset exist.
- [ ] API client encodes job ids and normalizes errors.
- [ ] Jobs reattach after reload and polling lives in the store.
- [ ] Generate disables for all required conditions.
- [ ] Clear chat and Clear chat + media are visible and module-scoped.
- [ ] Per-generation Delete and per-image trash are visible.
- [ ] Clear confirmation is count-free and scope-aware.
- [ ] Every `AppPopover` trigger explicitly toggles its `v-model`.
- [ ] Shared `StageTimeline` renders job stages.
- [ ] Settings cards use borders, accents, header/body separation, and spacing
      in both themes.
- [ ] Library and generic jobs caches sync after terminal/delete/clear.
- [ ] Gallery syncs on mount, searches all documented fields, and opens the
      shared `MediaViewer`.
- [ ] Missing assets are hidden after library sync.
- [ ] **(LoRA)** A saved all-off chain is preserved across reloads/rebuilds;
      tabs sync through `storage` without echoing or resurrecting defaults.
- [ ] **(enhancement)** Custom enhancement prompt persists; empty means backend
      default; preview and approved rewrite invalidate on prompt/brief changes.
- [ ] **(enhancement)** The Advanced runtime card exposes the default-on unload
      toggle, persists it, resets it, and sends it on preview and job requests.
- [ ] **(engine)** Readiness comes from the shared engine store and recovers
      live; catalog refreshes after a connectivity transition.
- [ ] **(engine)** Engine accounting is deduplicated and released on
      terminal/404/delete.
- [ ] **(T2I)** The `MediaViewer` action slot is favorite-only; no duplicate
      trash action appears in the viewer and the card.
- [ ] **(T2I)** No reference/image-input path appears in a strict T2I module.
- [ ] Zero-context dry run in §8.5 passed without opening another module.
- [ ] `npm run typecheck`, `npm run build`, and backend tests pass.
- [ ] Browser console is clean.

---

## 10. Gotchas

- **A folder copy is not registration.** The app has no GenModule auto-discovery
  for routers, Vue routes, or nav items. The three host edits in §3.3–§3.4 are
  mandatory. The manifest does not perform them.
- **The sidebar is grouped.** Insert the nav item inside the `image`, `video`,
  `audio`, `library`, or `system` group. A flat top-level array is the old shape
  and will not typecheck. Use the same id for `navId`, the runtime folder, and
  the nav item.
- **`_template` is ignored by design.** Its folder starts with `_`. Copy it to a
  real module id before expecting it in the installed capability list. Its
  backend files live under `backend/`, not at the module root.
- **The manifest is documentation, not wiring.** `entrypoint`, `apiPrefix`, and
  `frontend` must stay accurate, but FastAPI uses the router prefix and Vite
  uses the files copied into `frontend/src/features/<nav-id>/`.
- **Shared control models are typed.** `AppInput`, `AppTextarea`, and
  `AppSelect` use `defineModel<string>()`; `AppSwitch` is boolean; `AppSlider`
  is number. A `number` bound directly to `AppInput`/`AppSelect` fails
  typecheck or renders as an empty control.
- **The library is image-only today.** `add_bytes` accepts
  png/jpg/jpeg/webp/bmp/gif/svg up to 128 MB. Audio/video needs a host change to
  `app/library/service.py`, the `Asset` type, Gallery filters, and viewer
  handling. Do not disguise another format with an image suffix.
- **Engine lifecycle is manual.** An engine-backed module that resumes jobs must
  add its own `resume_pending_jobs()`/`shutdown()` calls in
  `backend/app/main.py`; there is no plugin registry for lifespan hooks.
- **`frontend/README.md` is not a runtime file.** Copy only the six code files
  into `frontend/src/features/<nav-id>/`.
- **Canonical/runtime drift**: editing only the runtime copy loses the change
  when the canonical folder is copied next. Always copy canonical → runtime and
  hash-check.
- **`AppPopover` does not auto-toggle.** Each trigger needs
  `@click="open = !open"`. Without it the menu never appears.
- **Clear must reject active jobs.** Do not silently cancel and delete. The
  backend must return `422 job_running` before changing anything.
- **Clear is not the visible page.** The UI may show 60 jobs while the backend
  owns thousands. Clear the full module history and avoid count-based
  confirmation wording.
- **Never use the generic jobs API for module history deletion.** It is not
  module-scoped. Use the module's `/jobs` and `/jobs/{id}` routes.
- **Job ids contain `#`.** Encode them in every URL.
- **Newest-first vs chat order.** The API returns newest first; reverse once
  for chronological chat and append new jobs at the end.
- **Page-local forms reset on route change.** Put durable state in the store.
- **Reset all vs panel reset.** Global reset clears the prompt; sampling or
  upscale reset must not.
- **A saved 0-LoRA chain is valid.** Five entries with `on: false` is not an
  empty/missing setting. Never run pack LoRA defaults after a saved form is
  restored; only an explicit LoRA/global reset may do that. Persist the toggle
  immediately and sync `storage` events so a stale tab cannot overwrite it.
- **Text-model unload is Ollama-only and non-fatal.** Use
  `connectors.unload_ollama(model)` after enhancement. Do not globally free
  ComfyUI, and never block the image job if the unload fails; surface a warning
  and continue.
- **One delete per scope.** Do not put a trash action in both the card and the
  `MediaViewer`. T2I keeps per-image trash on the card overlay and
  per-generation delete in the card menu; the viewer is favorite-only.
- **Upscaler path vs enabled.** Selecting `none` disables upscaling; turning
  the switch off preserves the last path.
- **Readiness is not a catalog snapshot.** Use the polling engine store, and
  refresh the catalog when connectivity changes. Otherwise Generate stays
  disabled until reload.
- **`systemPrompt` empty-string semantics.** Omit or send `null` for the
  backend default. An explicit `""` is an intentional empty override.
- **Approved rewrites are input-bound.** Changing the prompt or the custom
  system prompt must discard the preview and approved text.
- **Soft delete only.** Use `jobs.delete_job()`; do not `DELETE FROM jobs`.
- **Asset deletion only through the library trash path.** Never unlink a file
  from module code.
- **`resultIds` are references.** After a library delete they may point at
  nothing. The library cache is authoritative once loaded.
- **A library row can outlive its file.** Treat asset endpoint 404s as an
  integrity issue, not as a reason to render a second fallback URL.
- **One engine poll, one queue.** Do not add module-local readiness timers or a
  second busy pill; use the shared engine store.
- **Settings `<details>` reset buttons** need `.prevent.stop` or the panel
  toggles while resetting.
- **Fullscreen viewer** uses a dark lightbox in both themes by design.
- **Cross-module imports** break portability. Shared behavior belongs in the
  shared layer, not in another module.
- **No hardcoded paths.** Use asset ids and same-origin API prefixes.

---

## Appendix A — Host contract

These are the shared APIs the starter uses. Code against them; do not copy a
private helper out of `T2I_main`. If a signature changes, update `_template`,
the frontend starter, and this appendix together.

### A.1 Jobs (`app.jobs.service`)

```python
from app.jobs import service as jobs

jobs.create_job(payload: dict) -> dict
jobs.update_job(job_id: str, patch: dict) -> dict | None
jobs.get_job(job_id: str, *, include_deleted: bool = False) -> dict | None
jobs.list_jobs(limit: int = 80, module: str | None = None) -> list[dict]
jobs.delete_job(job_id: str) -> bool
jobs.now_ms() -> int
```

`create_job` payload keys:

```text
tab, module, modelId, modelName, recipe, prompt, seed, params, stages
```

`update_job` accepted patch keys:

```text
status, progress, enhancedPrompt, params, stages, resultIds, error
```

Notes:

- `status` is `queued | running | done | error`; the service creates the job as
  `running` and assigns `#N` ids.
- `progress` is clamped to 0–100.
- `params`, `stages`, and `resultIds` are JSON-serialized by the service.
- `module` is the exact `MODULE_ID`; list only your module's jobs.
- `delete_job` is a soft delete. Do not execute `DELETE FROM jobs`.
- `list_jobs` is newest first; the frontend reverses once for chat order.

### A.2 Library (`app.library.service`)

```python
from app.library import service as library

library.add_bytes(data, filename, *, label=None, prompt="", model="", seed=0,
                  tags=None, origin_job=None) -> dict
library.add_file(path, *, label=None, prompt="", model="", seed=0,
                 tags=None, origin_job=None) -> dict
library.get_asset(asset_id) -> dict | None
library.file_path(asset_id) -> tuple[Path, dict] | None
library.ensure_thumb(asset_id) -> tuple[Path, dict] | None
library.list_assets(limit=500) -> list[dict]
library.trash_asset(asset_id) -> dict | None   # {"id": ..., "movedTo": ...} or None
```

- Accepted extensions: `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`, `.gif`, `.svg`.
- `add_bytes` rejects files larger than 128 MB.
- Asset URLs: `/api/assets/{id}/file` and `/api/assets/{id}/thumb`.
- There is no audio/video storage path yet; that is a host change.

### A.3 Connectors (`app.connectors`)

```python
from app import connectors

connectors.comfy_client() -> ComfyUIClient
connectors.ollama_client() -> OllamaClient
await connectors.status_snapshot() -> dict
await connectors.unload_ollama(model: str | None = None) -> {"ok": bool, "message": str}
```

`ComfyUIClient` methods:

```text
system_stats()
queue()
object_info()
object_info_node(node_class, timeout=15.0)
submit_prompt(prompt, client_id=None, timeout=60.0) -> dict   # includes prompt_id
history(prompt_id, timeout=15.0) -> dict
view(filename, subfolder="", type="output", timeout=120.0) -> bytes
queue_delete(prompt_id)
free(unload_models=True)
interrupt()
```

`status_snapshot()` returns `{"comfyui": ..., "ollama": ..., "resources": ...}`
and feeds `GET /api/status`. The frontend `useEngineStore` consumes that route;
do not add a module-local status endpoint or timer.

### A.4 Settings (`app.settings.service`)

```python
from app.settings import service as settings

values, initialized = settings.get()
defaults = settings.get_defaults()
settings.update({"prompts": {...}})
settings.reset()
```

`values["prompts"]` is the map of backend default system prompts. Use it when a
module supports prompt rewriting; do not hardcode the default brief in two
places.

### A.5 Frontend stores

```ts
import { useEngineStore } from '@/stores/engine'
import { useLibraryStore } from '@/stores/library'
import { useJobsStore } from '@/stores/jobs'
import { useUiStore } from '@/stores/ui'
```

| Store | Key state / methods |
| --- | --- |
| `useEngineStore` | `comfy`, `ollama`, `gpu`, `ram`, `queue`, `busy`, `activeJobs`, `queueLabel`, `comfyLoaded`, `ollamaLoaded`, `launching`, `refresh()`, `startPolling()`, `test(kind)`, `unloadComfy()`, `unloadOllama(id)`, `unloadAllOllama()`, `launchComfy()`, `jobStarted()`, `jobFinished()` |
| `useLibraryStore` | `assets`, `loaded`, `importing`, `byId(id)`, `syncFromBackend()`, `add(list)`, `toggleFavorite(id)`, `trash(id)`, `importFiles(files)` |
| `useJobsStore` | `jobs`, `byId(id)`, `syncFromBackend()`, `create(draft)`, `update(id, patch)`, `replace(job)` |
| `useUiStore` | `theme`, `accent`, `collapsedGroups`, `toasts`, `applyTheme()`, `setTheme()`, `setAccent()`, `toggleGroup()`, `toast(message, kind?, duration?)`, `dismiss(id)` |

Pinia setup stores unwrap their refs on the store object: use `library.loaded`,
not `library.loaded.value`, in components. In plain script outside a store,
`storeToRefs` is still the right way to destructure reactive fields.

`useJobsStore` is the generic Jobs-page cache. A module page should poll its own
`/api/<module>/jobs/{id}` route and call `genericJobs.syncFromBackend()` after
terminal/delete/clear, not use `useJobsStore.update()` to mutate its own job.

### A.6 Shared UI components

| Component | Model / props | Notes |
| --- | --- | --- |
| `AppButton` | `variant?: primary\|soft\|ghost\|danger`, `size?: sm\|md\|lg`, `disabled?`, `block?` | Native button attrs/click fall through |
| `AppInput` | `v-model: string`, `placeholder?`, `type?`, `disabled?`, `size?: sm\|md` | `type="number"` still uses a string model |
| `AppTextarea` | `v-model: string`, `placeholder?`, `rows?`, `disabled?` | |
| `AppSelect` | `v-model: string`, `options: {value,label,disabled?}[]`, `disabled?`, `size?` | Values are strings; convert numbers at the boundary |
| `AppSwitch` | `v-model: boolean`, `label?`, `disabled?` | |
| `AppSlider` | `v-model: number`, `min?`, `max?`, `step?`, `label?`, `disabled?` | |
| `AppPopover` | `v-model: boolean` (required), `align?: left\|right`, `up?`, `width?` | Slots `trigger`, default; trigger must toggle the model |
| `AppModal` | `v-model: boolean` (required), `title?`, `subtitle?`, `width?` | Slots default, `footer` |
| `Badge` | `tone?: neutral\|accent\|ok\|warn` | Slot text |
| `Chip` | `active?`, `disabled?`; emits `click` | Use for suggestions/quick chips |
| `Section` | `title`, `desc?` | Card shell |
| `ResetButton` | `disabled?`, `label?`; emits `reset` | 40×40 ghost button |
| `StatusDot` | `state: ok\|off\|warn\|busy` | Animated for busy |
| `StageTimeline` | `stages: Stage[]` | Shared chat stage list |
| `MediaViewer` | `v-model:open`, `v-model:index`, `items: MediaViewerItem[]`, `title?`, `downloadable?`, `showThumbs?`, `info?` | Slots `actions(item)`, `info(item)`; event `close` |

`MediaViewerItem` fields:

```ts
{
  id: string
  url: string
  thumbUrl?: string | null
  kind?: 'image' | 'video' | 'audio'
  label?: string
  prompt?: string
  meta?: { label: string; value: string }[]
  filename?: string
}
```

Shared types live in `frontend/src/types.ts`: `Asset`, `Stage`, `JobRecord`,
`JobStatus`, `StageStatus`, `AdvancedParams`. Formatting helpers are in
`frontend/src/lib/format.ts` (`formatTime`, `timeAgo`, `formatDuration`,
`formatSeed`) and downloads in `frontend/src/lib/download.ts`
(`downloadAsset(asset)`).

### A.7 CSS tokens and layout

Use semantic Tailwind classes generated from the theme tokens:

```text
bg-bg            page background
bg-surface       card / panel
bg-surface-2     inset / secondary surface
border-border    default border
text-text        primary text
text-muted       secondary text
accent           accent text
accent-soft      accent-tinted background
accent-contrast  text on accent
success warn danger
mint lavender peach sky rose   settings-card accent rails
```

`AppSlider` uses `var(--c-accent)` internally. The `MediaViewer` lightbox is
deliberately dark in both themes; that is the one documented exception to the
semantic-token rule.

### A.8 Registration map

| Host file | Edit | Automatic? |
| --- | --- | --- |
| `backend/app/api/__init__.py` | import module router + `include_router` | No |
| `frontend/src/router/index.ts` | import page + one route | No |
| `frontend/src/lib/nav.ts` | one item inside a group's `items` | No |
| `frontend/src/features/<nav-id>/` | copy six canonical files | No |
| `backend/app/main.py` | optional `resume_pending_jobs()`/`shutdown()` for engine modules | No |
| `backend/README.md` | optional module endpoint table | No |

The manifest does not perform any row in this table.

---

## Appendix B — `_template` file map

`backend/app/GenModules/_template/` is a working scaffold, not a capability.
Its folder starts with `_`, so the capability registry ignores it.

### Backend

| File | Responsibility | Adapt |
| --- | --- | --- |
| `backend/__init__.py` | Package export of `router` | Rename comments |
| `backend/api.py` | Thin router, error mapping, module-scoped routes | Rename router prefix; keep decorated shape |
| `backend/schema.py` | Camel-case request model | Replace fields with your inputs |
| `backend/service.py` | Catalog, normalization, runner, stages, library writes, delete/clear, stale-job reconciliation | Replace `_render_svg`; extend the pack/catalog; keep job/library/delete lifecycle |
| `backend/pack/options.json` | Starter defaults, supported size values, batch range | Replace with your real pack. Engine-backed packs split generation defaults into `packs/<id>/defaults.json`; keep `models.json` for bindings/ranges. Multi-family modules add `pack/registry.json` + `pack/packs/<id>/` |
| `manifest.json` | Identity and metadata | Update every field; `entrypoint` is `backend.api:router` |
| `requirements.json` | Optional ComfyUI nodes/models | Module-level, covers every pack; add only if your engine needs them. The app does not install them |

`service.py` sections to keep:

- `ValidationError` / `EngineError` and the error-mapping contract;
- `_normalize` called by both `/validate` and `/jobs`;
- `_StageTracker` (or the same behavior through `jobs.update_job`);
- `start_job`, `_run_job`, `get_job`, `list_jobs`, `cancel_job`;
- `delete_job`, `_trash_job_assets`, `clear_history`;
- `_reconcile_restarted_job` (for an engine module, replace with resume).

Replace:

- `catalog_snapshot()` with your real controls/catalog;
- `_render_svg()` with your engine call and asset collection;
- the placeholder pack values with your real defaults and ranges.

### Frontend

| File | Responsibility | Adapt |
| --- | --- | --- |
| `frontend/types.ts` | Wire types, catalog, job params | Rename/replace types; keep camelCase |
| `frontend/api.ts` | Same-origin fetch, errors, URL encoding | Change `BASE` to `/api/<module>` |
| `frontend/store.ts` | Form, persistence, catalog reconciliation, polling, delete/clear | Change `STORAGE_KEY`, Pinia id, request fields |
| `frontend/TemplatePage.vue` | Header, chat, composer, settings, viewer | Rename; keep layout/transient-state split |
| `frontend/TemplateSettingsPanel.vue` | Output/renderer cards, resets, autosave | Replace renderer-specific cards |
| `frontend/TemplateGenerationCard.vue` | Prompt bubble, stages, results, actions | Replace settings disclosure rows |
| `frontend/README.md` | Starter contract | Keep canonical; do not copy to runtime |

The template's page uses a local placeholder renderer so the entire job →
library → history → delete path can be tested without ComfyUI. That is a
feature, not a mock in the shared layer: the renderer is module code and is
replaced wholesale.

### T2I copy-prune reference

If you need the full engine path, read these T2I files and copy patterns, not
business rules:

| T2I file | Use it for |
| --- | --- |
| `backend/catalog.py` | Merging tracked pack with installed-file presence |
| `backend/workflows.py` | ComfyUI graph composition and node wiring |
| `backend/pack/` | Ranges, defaults, recipes |
| `backend/service.py` | Engine submit/poll/collect, resume, cancel |
| `frontend/store.ts` | Enhancement, LoRA, upscale, catalog refresh, resume polling |
| `frontend/T2IPage.vue` | Full T2I-specific composer and settings |
| `frontend/T2ISettingsPanel.vue` | Enhancement/LoRA/upscale cards |

Keep the generic parts from `_template`: job creation, stage persistence,
library collection, module-scoped delete/clear, polling/backoff, autosave,
viewer ownership, and panel-reset discipline.

---

## Appendix C — Zero-context acceptance record

Use this table in the module PR after the §8.5 dry run:

| Check | Result |
| --- | --- |
| Copied `_template` and renamed only the documented identity fields | |
| Backend router import + `include_router` added without replacing `api` | |
| Vue route added inside the router's `routes` array | |
| Nav item added inside the correct group | |
| Six runtime files hash-match the canonical folder | |
| `npm run typecheck` / `npm run build` pass | |
| `uv run python -m pytest -q` passes | |
| Generate batch 2 produces two SVG assets | |
| Stages reach done; library/Gallery/Jobs show the results | |
| Per-image trash, per-job delete, and both clear options work | |
| Reload restores the form/jobs; active jobs reattach | |
| Desktop and mobile settings drawers work; panel resets are isolated | |
| No step required opening `T2I_main` or guessing a shared prop | |

Report every unchecked row as a documentation or starter defect. A module is
not "portable from docs" until the table is clean.
