# GenModule Development Guide

A **GenModule** is one vertical slice of the product: a generation workflow with
its own backend service, tracked pack, API, canonical frontend contract, runtime
page, job semantics, library integration and tests. `T2I_main` (strict
Text → Image) is the reference implementation; new modules should follow this
guide rather than inventing a second architecture.

This guide covers the reusable pattern, not just T2I. For T2I-specific control
details, see `backend/app/GenModules/T2I_main/frontend/README.md`.

---

## 1. Architecture at a glance

```
backend/app/GenModules/<module-id>/
  manifest.json                 identity, nav id, API prefix, frontend entry
  requirements.json             optional ComfyUI nodes / model files
  backend/
    api.py                      thin FastAPI router
    service.py                  validation + job stages + asset collection
    schema.py                   request/response models
    catalog.py                  pack + user-catalog merge
    workflows.py                ComfyUI graph composition (optional)
    pack/                       authoritative module ranges/defaults
  frontend/
    README.md                   canonical GUI/API contract
    types.ts                    wire types
    api.ts                      same-origin API client
    <Module>Page.vue            canonical route page
    store.ts                    module Pinia store (state/persistence/jobs)
    <Module>SettingsPanel.vue   settings drawer
    <Module>GenerationCard.vue  chat result card

frontend/src/
  features/<module-id>/         runtime copy of the canonical module frontend
  components/ui/                shared primitives
  components/media/             shared MediaViewer
  components/chat/              shared StageTimeline and legacy mock chat pieces
  stores/library.ts             backend-first asset cache
  stores/jobs.ts                generic job history cache
```

Rules:

1. A module may import shared app code (`app.common`, `app.connectors`,
   `app.jobs`, `app.library`) but **never another GenModule**.
2. The backend and frontend contract travel together. Keep the canonical
   copy under `backend/app/GenModules/<module-id>/frontend/` authoritative and
   copy it into `frontend/src/features/<module-id>/`.
3. Promote reusable behaviour to the shared layer. `MediaViewer` exists because
   a second module should not rebuild fullscreen media handling.
4. A module owns its jobs, but not the files. The library owns files and
   thumbnails; the jobs service owns job records.

---

## 2. Backend module anatomy

### 2.1 Manifest

```json
{
  "id": "T2I_main",
  "navId": "text-to-image",
  "name": "Text -> Image",
  "entrypoint": "backend.api:router",
  "apiPrefix": "/api/t2i",
  "frontend": "frontend/T2IPage.vue",
  "capabilities": ["t2i", "lora", "refine"],
  "excludes": ["identity", "reference-image", "edit-image"]
}
```

- `navId` matches the frontend route/nav id.
- `frontend` points at the canonical page, not the runtime copy.
- `excludes` is documentation as much as policy: T2I must stay strict T2I.

### 2.2 API router

The router is thin. It should only:

- declare routes and query aliases;
- map service exceptions to HTTP via one decorator/helper;
- return service data.

T2I maps:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/catalog` | models, LoRAs, upscalers, ranges, defaults, engine status |
| `GET` | `/pack` | secret-free pack summary |
| `POST` | `/validate` | normalize/validate without creating a job |
| `POST` | `/enhance` | prompt rewrite preview |
| `POST` | `/jobs` | create and start a job |
| `GET` | `/jobs` | module-scoped history |
| `GET` | `/jobs/{id}` | one job |
| `POST` | `/jobs/{id}/cancel` | best-effort cancel |
| `DELETE` | `/jobs/{id}?deleteAssets=true\|false` | soft-delete a terminal job; optionally trash its results |

Job ids contain `#` (`#145`). Every client must call
`encodeURIComponent(jobId)` before placing it in a URL.

### 2.3 Validation

- The tracked pack is authoritative for ranges/defaults and graph wiring.
- `/validate` and `/jobs` must run the same normalization service. The GUI
  cannot bypass a rule by calling the API directly.
- Return structured errors:

```json
{
  "detail": {
    "code": "validation_error",
    "message": "Size 2000 is outside this model's safe range 512-1536.",
    "errors": [{ "code": "out_of_safe_range", "field": "size", "min": 512, "max": 1536 }],
    "warnings": []
  }
}
```

- Warnings are not errors. Surface them in the page and store them on the job.
- Do not silently clamp user input. The one exception is **restoration**:
  a saved form from an older pack may be clamped when reconciled against the
  current catalog, and the user must see a short notice.

### 2.4 Jobs

Use `app.jobs.service`; do not invent a parallel job store.

```python
job = jobs.create_job(
    {
        "tab": "text-to-image",
        "module": MODULE_ID,
        "modelId": model["id"],
        "modelName": model["label"],
        "prompt": request.prompt,
        "params": params,
        "stages": initial_stages,
    }
)
```

Then:

1. run stages (`enhance → compose → submit → generate → collect`);
2. patch progress/stages through `jobs.update_job`;
3. write result files through the library;
4. set `resultIds` and terminal status.

Jobs are **soft-deleted** through `jobs.delete_job(id)`: the row remains for
audit but disappears from `get/list/count/update` paths. A module's
`delete_job` should refuse `queued`/`running` jobs, optionally move result
assets to trash, then soft-delete the row.

### 2.5 Library integration

The library is the only place that owns files.

- Save generated bytes with `library.add_bytes(...)` and tag them with the
  module id, model, recipe and origin job.
- Return asset ids in `job.resultIds`; the frontend uses:
  - `GET /api/assets/{id}/file` for full media;
  - `GET /api/assets/{id}/thumb` for cards and thumbnails.
- Deleting a result image uses `library.trash_asset(id)`, which moves the file
  into `data/trash` and removes the asset row. Nothing is hard-deleted.
- After a job finishes, the frontend must sync the shared library store so the
  Gallery sees the new images.
- If an asset id no longer exists in a synced library, hide it rather than
  rendering a broken `/file` URL.

### 2.6 Tests

At minimum cover:

- payload validation and range enforcement;
- graph composition paths (none / latent / ESRGAN, enhancement);
- job creation and stage/error handling;
- result collection into the library;
- cancel behaviour;
- soft-delete, asset trash, and the HTTP delete contract.

Run from `backend/`:

```powershell
uv run python -m pytest -q
```

---

## 3. Frontend module anatomy

### 3.1 Runtime vs canonical copy

Canonical files live next to the module backend. Runtime files live in
`frontend/src/features/<module-id>/`. They are copies, not imports from the
backend folder. When the module is being developed, update the canonical copy
first, then copy:

```text
types.ts
api.ts
store.ts
<Module>Page.vue
<Module>SettingsPanel.vue
<Module>GenerationCard.vue
```

Keep imports identical in both copies. Runtime pages may import shared app
components through `@/components`, `@/stores` and `@/lib`.

### 3.2 Module store is the state owner

Do not keep the durable form in a page-level `reactive()` object. The page can
own transient UI (drawer open, viewer open, scroll position), but the module
store owns:

- form fields and catalog reconciliation;
- prompt / negative prompt / approved enhancement;
- LoRA selections and strengths;
- upscaler path/enabled/value;
- job history and polling;
- generation, cancel, delete, reuse and seed actions;
- library sync after terminal jobs.

Why: route switches unmount the page. Page-local state disappears; a store with
localStorage persistence survives reloads and lets every panel reset a slice
without duplicating field logic.

### 3.3 Persistence contract

T2I uses:

```text
localStorage key: genai.t2i.form.v1
```

Payload:

```json
{
  "version": 1,
  "savedAt": 1792831851043,
  "form": { "...": "..." }
}
```

Pattern:

1. Read and validate the payload defensively; merge only known keys and the
   correct primitive types.
2. Start from pack defaults for any missing key.
3. Watch the form deeply and debounce a write (~150–250 ms).
4. Flush synchronously in `beforeunload` and in the page's `onBeforeUnmount`.
5. After the catalog arrives, reconcile the restored form with the current
   pack:
   - unknown model/ratio/sampler/LoRA/upscaler → fallback;
   - remove incompatible LoRAs and enforce `maxLoras`;
   - clamp stale ranges and oversize values;
   - keep the prompt, negative prompt, seed and upscale choice when valid;
   - show one “settings adjusted” notice if anything changed.
6. Never persist secrets, absolute server paths, or API keys.

Use a versioned key (`genai.<module>.form.v1`). Bump the version when the
meaning of a field changes; write a migration or start fresh rather than
guessing.

### 3.4 Per-panel reset

Every settings panel gets its own reset action and the page gets one “reset
all” action. Implement reset centrally in the store:

```ts
function resetPanel(panel: ModulePanel): void {
  switch (panel) {
    case 'prompt': /* negative prompt + approved preview (composer owns prompt) */ break
    case 'output': /* model + ratio + size + batch + seed */ break
    case 'loras': /* default chain + auto triggers */ break
    case 'enhance': /* provider/model/fallback + preview */ break
    case 'sampling': /* model sampling defaults */ break
    case 'upscale': /* default path + value + enabled */ break
    case 'all': /* pack defaults, then clear page text */ break
  }
  persistNow()
}
```

Reset buttons are icon buttons in each panel header. The global reset should
ask for confirmation because it may clear the prompt and approved enhancement.
A panel reset must not accidentally clear unrelated prompts or output settings.

### 3.5 Jobs, polling and reattachment

1. Build the request from the form.
2. Call `/validate` (cheap preflight) and show warnings.
3. `POST /jobs`; prepend/append the returned record in the intended display
   order (T2I displays oldest → newest chat messages; the API returns newest
   first, so reverse once).
4. Poll `GET /jobs/{id}` every ~0.75–2 s while `queued`/`running`.
5. On terminal status:
   - update the card;
   - store job warnings;
   - sync the library and generic jobs caches;
   - stop polling.
6. On load, list recent jobs and reattach polling to any queued/running job.
7. On route switch, leave polling in the store; the job is backend-owned.
8. On 404, drop the job from the local list and release its engine slot.
9. Engine accounting: keep a deduplicated set of tracked job ids in the module
   store. Mark on create and reattach; release on terminal status, 404 and
   delete. This drives the shared top-bar queue pill; never add a module-local
   busy pill.

Cancellation is best-effort; finished jobs are a no-op. Deleting requires a
terminal status; T2I returns `job_running` if you try earlier.

### 3.6 API client

- Same-origin base (`/api/<module>`); no CORS or base URL setting.
- Encode every job id.
- Normalize FastAPI’s validation shape and transport errors into one typed
  error class (`T2IApiError`) containing `code`, `errors` and `warnings`.
- Provide `AbortSignal` for validate/enhance/catalog where the page can cancel.

---

## 4. Layout pattern: compact chat workspace

T2I’s page is the reference layout:

```
┌ header: module, engine status, model chip, Gallery, Settings ┐
├───────────────────────────────────────┬───────────────────────┤
│ chat scroller                         │ settings drawer       │
│  user prompt bubble                   │  Output               │
│  result card (stages, images, actions)│  Upscale              │
│  ...                                  │  LoRA chain           │
│                                       │  Enhancement          │
│                                       │  Sampling             │
│                                       │  Prompt extras        │
├───────────────────────────────────────┤  global reset         │
│ composer: textarea + quick chips      │                       │
│ [Generate]                            │                       │
└───────────────────────────────────────┴───────────────────────┘
```

### 4.1 Header

- Module label and page title.
- Engine readiness (`ComfyUI ready/offline`), with a checking state before the
  catalog loads.
- Selected model chip.
- Link to the Gallery (results must be discoverable).
- Settings toggle.

### 4.2 Composer

- Prompt textarea; `Ctrl+Enter`/`Meta+Enter` generates, plain Enter stays a
  newline.
- Character counter and autosave label.
- Quick chips open the relevant settings panel:
  model, ratio + long side, LoRA count, upscale on/off, enhancement on/off.
- **Upscale must have a clearly visible on/off control in the composer**, not
  only inside a collapsed advanced section. Turning it off sets
  `advanced.upscaler.enabled = false`; the selected path remains for next time.
- Action group (settings + Generate) is right-aligned with `ml-auto` so it stays
  stable when chips wrap.
- Disable Generate when: prompt empty, catalog missing, selected model missing,
  ComfyUI offline, enhancement requested while its text provider is offline
  (unless an approved rewrite or fallback-to-original is ready), enhancement in
  flight, or another job is active.

### 4.3 Chat messages

Every job is a chat turn:

- right-aligned **user bubble** with prompt and compact chips (time, model,
  ratio, batch);
- left-aligned **assistant result card** with status dot, job id, time and
  progress;
- running: progress bar, shared `StageTimeline`, Cancel;
- error: readable message, stages;
- done: result grid, favorite/fullscreen/open actions, warnings, settings
  disclosure;
- actions: View, Reuse, Use seed, Download, more menu;
- deletion menu offers **Remove message only** and **Delete images & message**;
- settings disclosure includes every applied setting, prompt-used and negative
  prompt; do not hide the actual seed or final dimensions.

### 4.4 Settings drawer

- Desktop: static right column, ~380–400 px.
- Mobile: fixed overlay drawer with backdrop; close button.
- Each panel is a `<details>` section with a summary line and a reset icon.
- Use `AppSelect`, `AppSwitch`, `AppSlider`, `AppButton` and semantic tokens.
- State is bound directly to the store form; never copy it into a local form
  object that can drift.
- Settings panel must not own generation; it only edits the store.

### 4.5 Gallery page

- Sync the library on mount; add a visible Refresh button for files added outside
  the current page.
- Search across prompt, label, model, tags, job id and seed.
- Open the shared `MediaViewer` when a card is clicked.
- Viewer actions: favorite, download (built-in), move to trash.
- Do not offer “use as reference” on a strict Text→Image module; that would
  reintroduce a reference-image input path. Remove or replace such actions when
  migrating a mock gallery.

The Gallery search placeholder should mention the same fields it searches
(prompts, labels, models, jobs, seeds).

---

## 5. Reusable media viewer

`frontend/src/components/media/MediaViewer.vue` is module-agnostic. It supports
images, video and audio, fullscreen, keyboard navigation, zoom, thumbnails and
an optional metadata panel.

### 5.1 Item shape

```ts
import type { MediaViewerItem } from '@/components/media/types'

const items: MediaViewerItem[] = [
  {
    id: 'a-1808e246b5',
    url: '/api/assets/a-1808e246b5/file',
    thumbUrl: '/api/assets/a-1808e246b5/thumb',
    kind: 'image',                    // default: image
    label: 'Job #145 · result 1',
    prompt: 'An orange cat on a table',
    filename: 'job-145-1.png',
    meta: [
      { label: 'Model', value: 'Krea 2 Turbo (int8)' },
      { label: 'Seed', value: '2300737279' },
      { label: 'Size', value: '1536 × 1536' },
    ],
  },
]
```

### 5.2 Usage

```vue
<MediaViewer
  v-model:open="viewerOpen"
  v-model:index="viewerIndex"
  :items="viewerItems"
  title="Library"
>
  <template #actions="{ item }">
    <button v-if="item" @click="toggleFavorite(item)">Favorite</button>
  </template>
  <template #info="{ item }">
    <p v-if="item">Any module-specific metadata</p>
  </template>
</MediaViewer>
```

Props: `items`, `title`, `downloadable` (default true), `showThumbs` (default
true), `info` (default true).

Models: `open`, `index`.

Slots: `actions` (`item`) in the header, `info` (`item`) in the metadata panel.

Events: `close` when the internal close action runs.

Built-in keyboard support while open:

| Key | Action |
| --- | --- |
| `Escape` | exit fullscreen, otherwise close |
| `←` / `→` | previous / next item |
| `+` / `-` | zoom in / out |
| `0` | reset zoom |
| `F` | toggle fullscreen |

Parent responsibilities:

- Build item URLs from the library/backend; do not hardcode absolute file paths.
- Own the item list and update it after delete/favorite changes.
- Close the viewer if the current list becomes empty.
- If a library asset is deleted, remove it from the viewer and from any chat
  card fallback list.
- Do not put module-specific settings logic inside `MediaViewer`; pass metadata
  through `meta` or the `info` slot.

### 5.3 Deletion and missing assets

- T2I job deletion with `deleteAssets=true` moves result assets to trash.
- A job can remain in history while its images are already gone. In that case:
  - if the library has synced and `byId(id)` is missing, do not render a
    fallback `/file` URL;
  - show “no result images” instead.
- Only fall back to a constructed file URL while the library has not yet loaded
  (`library.loaded === false`).

---

## 6. State, cache and sync checklist

Per module:

- [ ] Module store owns persisted form state (`genai.<module>.form.v1`).
- [ ] Debounced autosave + sync flush on unload.
- [ ] Catalog reconciliation after load; user-visible notice only if adjusted.
- [ ] Per-panel reset + global reset.
- [ ] Jobs list loaded on mount; running jobs reattach.
- [ ] Job deletion soft-deletes; running jobs are refused.
- [ ] Result assets are saved through the library and tagged.
- [ ] Library store synced after each terminal job and on Gallery mount.
- [ ] Generic jobs store synced so Jobs page is current.
- [ ] Missing assets hidden after library sync.
- [ ] No hard-coded localhost URLs; all same-origin API paths.
- [ ] Job ids encoded.
- [ ] Tests cover backend validation, delete and asset trash.
- [ ] `npm run typecheck` and `npm run build` (which also runs `vue-tsc`) pass.
- [ ] Browser console clean.

---

## 7. New GenModule checklist

1. Create `backend/app/GenModules/<module-id>/` from the T2I layout.
2. Add `manifest.json` and a `pack/` with authoritative ranges/defaults.
3. Implement schema + service + thin API router; mount the router in
   `app/api/__init__.py`.
4. Add `requirements.json` if ComfyUI nodes/model files are needed.
5. Add backend tests; run `uv run python -m pytest -q`.
6. Add canonical frontend files and README.
7. Copy them to `frontend/src/features/<module-id>/`.
8. Register the route and nav entry.
9. Verify the module store persistence, resets, job polling, deletion and
   library/gallery round trip.
10. Add the module to the GenModules docs and update this guide if the pattern
    changes.

---

## 8. Gotchas

- **Stale library cache**: syncing only once at app startup makes new T2I images
  invisible in the Gallery. Sync on Gallery mount and after terminal jobs.
- **Result ids vs assets**: `resultIds` are references. After a library delete,
  they can point at nothing. Treat missing assets as deleted, not as a broken
  image.
- **`#` in job ids**: always `encodeURIComponent`.
- **Newest-first vs chat order**: the API returns newest first; the T2I store
  reverses once for chronological messages and appends new jobs at the end.
- **Page-local forms**: they reset on route change. Use the store.
- **Reset all vs prompt**: a global reset clears the prompt; a sampling or
  upscale reset must not.
- **Upscaler path vs enabled**: selecting `none` disables upscaling and turns
  the switch off; turning the switch off preserves the last non-none path.
- **Soft delete**: do not `DELETE FROM jobs`; use `jobs.delete_job()` so audit
  data survives and every read path filters it.
- **Asset deletion**: use the library trash path, never unlink files directly
  from a module.
- **Client-only range checks**: the pack/backend are authoritative; the UI
  slider is not a security or validity boundary.
- **Fullscreen viewer**: `MediaViewer` uses a dark lightbox regardless of the
  app theme; that is intentional and is the documented exception to the
  “semantic tokens only” rule for chrome.
