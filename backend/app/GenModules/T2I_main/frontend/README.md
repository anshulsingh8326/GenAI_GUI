# T2I_main — frontend contract (strict Text → Image)

Canonical frontend deliverable for the T2I_main GenModule. It sits next to the module backend so
the API contract, range rules and GUI behaviour travel together. The runtime copy lives in
`frontend/src/features/text-to-image/` and is what Vite builds.

This is a **strict Text → Image** module. There is no identity, reference-image, edit or face-swap
input. Do not add a “use as reference” path, not even in the Gallery.

## Files

```text
frontend/
  README.md                 this contract
  types.ts                  wire types
  api.ts                    same-origin client (/api/t2i)
  store.ts                  module store: form, persistence, catalog, jobs, actions
  T2IPage.vue               compact chat workspace + composer
  T2ISettingsPanel.vue      right drawer, per-panel resets
  T2IGenerationCard.vue     chat result card, settings disclosure, deletion
```

Runtime copy: `frontend/src/features/text-to-image/`. Keep imports aligned with the app (`@/`
aliases); do not import from the backend folder at runtime. Reusable media viewing lives in
`frontend/src/components/media/MediaViewer.vue`.

---

## 1. Scope

- Krea 2 Turbo (int8, or Q5 GGUF when installed)
- LoRA chain with per-LoRA strength and automatic trigger injection
- latent refine (default) or optional 4x-UltraSharp, or no upscale
- optional Ollama/ComfyUI prompt enhancement with preview/approve
- batch 1–4, ratio presets, model-specific safe ranges
- persisted settings, chat history, library results and soft deletion

Out of scope: image inputs of any kind, identity locking, face swap, inpainting/editing.

## 2. API contract

All calls are same-origin under `/api/t2i`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/catalog?modelId=` | models, LoRAs, upscalers, ratios, ranges, defaults, engine status |
| `GET` | `/pack` | secret-free pack summary for debug/ops |
| `POST` | `/validate` | normalize/validate without creating a job |
| `POST` | `/enhance` | prompt rewrite preview |
| `POST` | `/jobs` | create and start a job |
| `GET` | `/jobs?limit=` | module-scoped history, **newest first** |
| `GET` | `/jobs/{id}` | one job |
| `POST` | `/jobs/{id}/cancel` | best-effort cancel |
| `DELETE` | `/jobs/{id}?deleteAssets=true\|false` | soft-delete a terminal job; optionally trash results |

Job ids contain `#` (`#145`). Always call `encodeURIComponent(jobId)` before building a URL.

The create request carries the complete resolved selection:

```json
{
  "prompt": "...",
  "negativePrompt": "...",
  "modelId": "krea2-turbo-int8",
  "ratio": "1:1",
  "size": 1024,
  "batch": 1,
  "seed": 123,
  "lockSeed": true,
  "loras": [{ "id": "lora-...", "strength": 1.0, "on": true, "order": 0 }],
  "autoTriggers": true,
  "enhance": {
    "enabled": false,
    "provider": "ollama",
    "model": "qwen...",
    "fallbackToOriginal": false
  },
  "enhancedPrompt": "...",
  "advanced": {
    "steps": 8,
    "cfg": 1,
    "sampler": "euler",
    "scheduler": "simple",
    "denoise": 1,
    "refine": { "steps": 2, "cfg": 1, "denoise": 0.35 },
    "upscaler": { "id": "latent-refine", "enabled": true, "value": 1536 }
  },
  "tab": "text-to-image"
}
```

### Errors and warnings

The client normalizes FastAPI validation and transport errors into `T2IApiError`:

- `code` — `validation_error`, `request_validation`, `job_running`, `backend_offline`, ...
- `errors` — structured field errors from the service;
- `warnings` — non-fatal range/engine warnings.

Show the first error in the page; show warnings as chips on the card and in the settings drawer.
The backend is authoritative. The GUI may clamp only during **restoration** of stale saved
settings, and must tell the user when it did.

## 3. Form state and persistence

`store.ts` owns the durable form. The page owns only transient UI (drawer open, viewer open,
scroll position).

Storage:

```text
key:      genai.t2i.form.v1
payload:  { version: 1, savedAt: <ms>, form: { ... } }
```

Form fields:

- prompt, negative prompt, approved enhanced prompt;
- model id, ratio, long side, batch, seed, lock seed;
- LoRA entries (`id`, optional strength, `on`);
- auto triggers, enhancement enabled/provider/model/fallback;
- sampling: steps, CFG, sampler, scheduler, denoise;
- refine: steps, CFG, denoise;
- upscale: id, enabled, value.

Behaviour:

1. Restore only known keys and correct primitive types.
2. Merge over pack defaults.
3. After the catalog arrives, reconcile:
   - unknown model/ratio/sampler/scheduler/LoRA/upscaler → fallback;
   - incompatible LoRAs dropped; `maxLoras` enforced;
   - stale sampling/refine/LoRA/upscale ranges clamped;
   - oversize batch/size clamped to the selected model;
   - invalid seed replaced; fractional seed rounded.
4. Debounced autosave (~180 ms); flush on `beforeunload` and page `onBeforeUnmount`.
5. If reconciliation changed anything, show one toast:
   “Restored T2I settings were adjusted to the current pack ranges.”

Per-panel resets (`resetPanel`):

| Panel | Resets |
| --- | --- |
| `prompt` | negative prompt, approved prompt, preview (the composer owns the main prompt) |
| `output` | model, ratio, long side, batch, seed, lock seed (sampling is re-clamped only if invalid) |
| `loras` | default chain, auto triggers |
| `enhance` | enhancement defaults + preview |
| `sampling` | steps/CFG/sampler/scheduler/denoise + refine defaults |
| `upscale` | default upscaler path/value/enabled |
| `all` | pack defaults; then clears the prompt/approved preview |

Each panel header has its own reset icon. The global reset is confirmed.

## 4. Layout

Compact chat workspace:

```text
header: T2I_MAIN · engine status · model chip · Gallery · Settings
┌─────────────────────────────────────┬─────────────────────────┐
│ chat scroller                       │ settings drawer         │
│  user prompt bubble                 │  Output                 │
│  generation card                    │  Upscale                │
│  ...                                │  LoRA chain             │
│                                     │  Enhancement            │
│                                     │  Sampling               │
│                                     │  Prompt extras          │
│                                     │  Reset all              │
├─────────────────────────────────────┤                         │
│ composer: textarea + quick chips    │                         │
│ [Settings] [Generate]               │                         │
└─────────────────────────────────────┴─────────────────────────┘
```

### Header

- `T2I_MAIN` label, “Text → Image” title.
- ComfyUI state: checking / ready / offline.
- Selected model chip; Gallery link; Settings toggle.
- On desktop the drawer defaults open; on mobile it is a fixed overlay with backdrop.

### Composer

- Prompt textarea. `Ctrl+Enter` / `Meta+Enter` generates; plain Enter is a newline.
- Autosave label and character counter.
- Quick chips open the matching settings panel: model, ratio + size, LoRA count, **upscale
  on/off**, enhancement on/off.
- Upscale must be visibly switchable here; do not hide it behind a collapsed advanced panel.
- Turning upscale off keeps the selected path for next time. Choosing the `none` path turns the
  switch off.
- Generate disabled when prompt empty, catalog missing, model not ready, ComfyUI offline,
  enhancement requested while its provider is offline (unless an approved rewrite or fallback
  is ready), enhancement preview loading, or a job is already active.
- Action group stays right-aligned with `ml-auto`.

### Chat messages

Oldest → newest. Each job renders as:

- right-aligned user prompt bubble with model/ratio/batch/time chips;
- left-aligned result card with status dot, job id, time and progress;
- queued/running: progress bar, `StageTimeline`, Cancel;
- error: readable message + stages;
- done: result grid, favorite/fullscreen actions, warnings, collapsible full settings;
- actions: View, Reuse, Use seed, Download, more menu;
- deletion menu: “Remove message only” or “Delete images & message”;
- the settings disclosure must include prompt used, negative prompt, seed, model, ratio, size,
  batch, LoRAs, enhancement, upscale, final size and job timing.

### Settings drawer

- Desktop static column, `w-[390px]`; mobile fixed overlay.
- Each section uses `AppSelect`, `AppSwitch`, `AppSlider`, `AppButton` and semantic tokens.
- Bind directly to the store form; no local copies.
- Prompt character counter and negative prompt live here.
- Enhancement panel: provider/model, fallback toggle, Generate preview, loading/cancel state,
  preview text, Use result / Discard.
- Sampling panel: base steps/CFG/sampler/scheduler/denoise + refine steps/CFG/denoise.
- Upscale panel: visible path select, on/off switch, slider + exact value, recommended hint, model
  min/max explanation.
- LoRA chain: compatibility-filtered list, add/remove, per-LoRA strength slider + switch,
  auto-inject triggers, count/limit.
- Prompt extras: auto triggers, negative prompt, prompt character budget.

## 5. Generation and job lifecycle

1. Build the complete request from the form.
2. Call `/validate`; show warnings.
3. `POST /jobs`; append the returned record to the chronological chat list.
4. Mark the job active in the shared engine store (deduplicated by id).
5. Poll every ~750–2000 ms while queued/running.
6. On terminal status:
   - update the card, store warnings;
   - release the engine busy slot;
   - sync the shared library and generic jobs stores.
7. On page load: list recent jobs, reverse the API’s newest-first list once, reattach polling to
   queued/running jobs and mark them active.
8. On 404: drop the local job and release its engine slot.
9. On lost polling after retries: keep an actionable error; do not pretend the job finished.
10. Cancel is best-effort; a finished job is a no-op.

Deleting a job:

- only terminal jobs; running/queued return `job_running`;
- `deleteAssets=true` moves result images to library trash before the soft delete;
- `deleteAssets=false` keeps images in the Library;
- the row is always soft-deleted (`jobs.deleted_at`), never hard-deleted;
- after asset deletion, sync the library and remove the card/viewer items.

## 6. Library and Gallery

- Results are written by the backend to the library and referenced by `job.resultIds`.
- Use `assetFileUrl(id)` / `assetThumbUrl(id)` for `/api/assets/{id}/file|thumb`.
- After a terminal job, call `library.syncFromBackend()`.
- Gallery also syncs on mount and has a Refresh button; do not rely on app-startup sync alone.
- If the library has synced (`library.loaded`) and an asset id is missing, treat it as deleted:
  hide the image instead of rendering a broken fallback URL. The fallback URL may only be used
  before the library has loaded.
- Gallery search covers prompt, label, model, tags, job id and seed; viewer actions are favorite
  and trash. Gallery cards open `MediaViewer`; there is no reference-image action.

## 7. Shared media viewer

Use `frontend/src/components/media/MediaViewer.vue` and `MediaViewerItem` from
`frontend/src/components/media/types.ts`.

- Props: `items`, `title`, `downloadable`, `showThumbs`, `info`.
- Models: `open`, `index`.
- Slots: `actions` (`item`) for favorite/trash, `info` (`item`) for extra metadata.
- Built-in: images/video/audio, fullscreen, keyboard navigation, zoom, thumbnails, download and
  metadata panel.
- Keyboard: `Escape` exits fullscreen then closes; arrows navigate; `+`/`-` zoom; `0` resets;
  `F` fullscreen.
- Parent owns the item list: remove deleted items, close when empty, keep index valid.
- Do not add T2I settings logic to the viewer. Pass a flattened `meta` array.

T2I result items should include prompt, filename, model, seed, size, final size, created time,
job id, LoRA summary, enhancement summary and upscale summary.

## 8. Acceptance checks

- [ ] Strict T2I: no reference, identity, edit or face-swap inputs anywhere.
- [ ] Upscale on/off is visible in the composer and in the settings panel.
- [ ] Prompt, negative prompt, LoRA chain, model, sampling, enhancement and upscale settings
      survive route switches and reloads.
- [ ] Each settings panel resets only its own slice; global reset is confirmed.
- [ ] Model/range changes reconcile stale saved values and notify once.
- [ ] New results appear in chat, Library and Gallery; Gallery refreshes on mount.
- [ ] Result card shows full applied settings, warnings, media viewer and deletion actions.
- [ ] Running jobs reattach after navigation/reload; engine busy state is correct and not
      double-counted.
- [ ] Deleting with assets moves them to trash; deleting message-only keeps them in Library.
- [ ] `npm run typecheck` and `npm run build` pass; backend `uv run python -m pytest -q` passes.
- [ ] Browser console clean.

## 9. Gotchas

- API history is newest-first; the store reverses once for chat order.
- Job ids contain `#`; encode them.
- Do not clear `form.prompt` after generation. Only `approvedPrompt` is consumed by a job.
- Editing `form.prompt` clears `approvedPrompt`/the preview and aborts an in-flight enhancement;
  a rewrite must never leak onto different text.
- `lockSeed: true` sends `seed`; otherwise omit it and the backend randomizes.
- Selecting the `none` upscaler disables upscale; turning the switch off preserves the last path.
- A restored form is reconciled against the current pack, not trusted blindly.
- `deleteJob` is soft delete. Do not add a hard-delete SQL path.
- Missing result assets after a library sync are deleted assets, not broken URLs.
- Never call `useChatStore.send()` from T2I; jobs are backend-owned.
