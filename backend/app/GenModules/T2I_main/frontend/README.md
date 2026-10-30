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

- Krea 2 Turbo: **SNOFS_Krea2** (int8) or **Krea2 Turbo Q5_K_M** (GGUF) as a one-of base
  group; install either. Alias-based detection binds the real catalog filename, so a renamed
  SNOFS or official `krea2` file still works.
- LoRA chain with per-LoRA strength and automatic trigger injection; NSFW LoRAs are tagged
- latent refine (default) or optional 4x-UltraSharp, or no upscale
- optional Ollama/ComfyUI prompt enhancement with preview/approve and an advanced custom
  system brief
- batch 1–4, ratio presets, model-specific safe ranges
- persisted settings, module-scoped chat history, library results and soft deletion

Out of scope: image inputs of any kind, identity locking, face swap, inpainting/editing.

## 2. API contract

All calls are same-origin under `/api/t2i`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/catalog?modelId=` | models, LoRAs, upscalers, ratios, ranges, defaults, engine status |
| `GET` | `/pack` | secret-free pack summary for debug/ops |
| `GET` | `/setup` | missing required files/groups, destinations, links, tags for the setup modal |
| `POST` | `/validate` | normalize/validate without creating a job |
| `POST` | `/enhance` | prompt rewrite preview |
| `POST` | `/jobs` | create and start a job |
| `GET` | `/jobs?limit=` | module-scoped history, **newest first** |
| `GET` | `/jobs/{id}` | one job |
| `POST` | `/jobs/{id}/cancel` | best-effort cancel |
| `DELETE` | `/jobs/{id}?deleteAssets=true\|false` | soft-delete one terminal job; optionally trash results (default `true`) |
| `DELETE` | `/jobs?deleteAssets=true\|false` | clear this module's whole chat; optionally trash all module results (default `false`) |

Job ids contain `#` (`#145`). Always call `encodeURIComponent(jobId)` before building a URL.

### First-open setup

`GET /setup` returns the shared `ModuleSetupPayload` (see `frontend/src/types.ts`). Fetch it once
on mount and auto-open `frontend/src/components/content/ModuleSetupModal.vue` only when
`ready === false`; `ready: null` means the user catalog is unavailable, not that every file is
missing. A header **Setup** button reopens the modal and refreshes the check. The modal only
reports files and opens links; it never downloads, installs, moves or deletes anything. A
Q5-only install satisfies the `krea2-base` one-of group, and a stale saved model switches to an
installed group sibling.

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
    "systemPrompt": null,
    "fallbackToOriginal": false,
    "unloadAfter": true
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

### Prompt enhancement briefs

`POST /enhance` and the job's `enhance.systemPrompt` accept an optional system prompt:

- omitted or `null` → backend default from `settings.prompts[<systemPromptKey>]`;
- non-empty string → custom brief for both preview and generation;
- explicit `""` → empty override (the GUI avoids this by sending `undefined` when empty).

The settings panel exposes an advanced brief with a structured “cards” template and a
backend-default reset. The resolved brief is saved in job params for disclosure.

### Text-model unload

Prompt enhancement and image generation share the GPU. Ollama keeps a text model resident after
a rewrite, so ComfyUI may have to squeeze the diffusion model into less VRAM. The form therefore
has a default-on **Unload enhancement model** toggle in the bottom **Advanced** runtime card.

- Preview request: send `unloadAfter: form.unloadEnhanceModel`.
- Job request: send `enhance.unloadAfter: form.unloadEnhanceModel`.
- Backend: after an Ollama rewrite, call the shared `connectors.unload_ollama(model)` path. It
  checks `/api/ps` first, so it can never load a model. Unload is best-effort.
- Send Ollama `think: false` for the rewrite. Thinking models otherwise spend the whole
  `num_predict` budget in `thinking` and return an empty `response`; non-thinking models and
  older servers ignore the field.
- The preview `maxLength` is a token cap (1–512), not the prompt character limit. Omit it to use
  the backend default; do not send `limits.promptMaxChars` or the preview returns 422.
- On preview failure to unload, keep and return the rewrite with `unloaded: false` and
  `unloadError`; show a small “unload failed · prompt kept” note.
- On job failure to unload, add an `enhance_unload_failed` warning and continue to compose/submit.
  Never fail the image job because VRAM cleanup failed.
- The enhance stage detail says `text model unloaded` or `unload failed`.
- Do not globally free ComfyUI here. ComfyUI manages its own text-model cache; only Ollama is
  unloaded. The toggle is on by default and its own reset restores `true`.

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
- custom enhancement system prompt (empty means backend default);
- model id, ratio, long side, batch, seed, lock seed;
- LoRA entries (`id`, optional strength, `on`);
- auto triggers, enhancement enabled/provider/model/fallback;
- unload enhancement model after use (default on);
- sampling: steps, CFG, sampler, scheduler, denoise;
- refine: steps, CFG, denoise;
- upscale: id, enabled, value.

Behaviour:

1. Restore only known keys and correct primitive types.
2. Merge over pack defaults.
3. After the catalog arrives, reconcile:
   - unknown model/ratio/sampler/scheduler/LoRA/upscaler → fallback;
   - a saved model that is no longer installed → an installed base-group sibling, then any
     installed model;
   - incompatible LoRAs dropped; `maxLoras` enforced;
   - stale sampling/refine/LoRA/upscale ranges clamped;
   - oversize batch/size clamped to the selected model;
   - invalid seed replaced; fractional seed rounded.
4. Debounced autosave (~180 ms); flush on `beforeunload` and page `onBeforeUnmount`.
   LoRA on/off toggles persist immediately so a rebuild/reload cannot race the timer.
5. If reconciliation changed anything, show one toast:
   “Restored T2I settings were adjusted to the current pack ranges.”
6. Editing the prompt or the custom enhancement brief aborts an in-flight preview and clears any
   approved rewrite, so a rewrite can never leak onto different input.
7. A saved all-off LoRA chain is authoritative. Never re-apply `defaults.loraChain` after restore,
   catalog refresh or model reconciliation; only an explicit LoRA/global reset does that.
8. Listen to `storage` and adopt a newer saved form. Compare before writing so two tabs cannot
   echo each other or resurrect a stale chain. A failed write is retried on the next change.

Per-panel resets (`resetPanel`):

| Panel | Resets |
| --- | --- |
| `prompt` | negative prompt, approved prompt, preview (the composer owns the main prompt) |
| `output` | model, ratio, long side, batch, seed, lock seed (sampling is re-clamped only if invalid) |
| `loras` | default chain, auto triggers |
| `enhance` | enhancement defaults, custom system brief + preview |
| `sampling` | steps/CFG/sampler/scheduler/denoise + refine defaults |
| `upscale` | default upscaler path/value/enabled |
| `advanced` | unload enhancement model back to on |
| `all` | pack defaults; then clears the prompt/approved preview |

Each panel header has its own reset icon. The global reset is confirmed.

## 4. Layout

Compact chat workspace:

```text
header: T2I_MAIN · live engine status · model chip · Gallery · Clear · Settings
┌─────────────────────────────────────┬─────────────────────────┐
│ chat scroller                       │ settings drawer         │
│  user prompt bubble                 │  Output                 │
│  generation card                    │  Upscale                │
│  ...                                │  LoRA chain             │
│                                     │  Enhancement            │
│                                     │  Sampling               │
│                                     │  Prompt extras          │
│                                     │  Advanced (runtime)     │
│                                     │  Reset all              │
├─────────────────────────────────────┤                         │
│ composer: textarea + quick chips    │                         │
│ [Settings] [Generate]               │                         │
└─────────────────────────────────────┴─────────────────────────┘
```

### Header

- `T2I_MAIN` label, “Text → Image” title.
- ComfyUI state: checking / ready / offline, read live from the shared engine store
  (`/api/status`), not cached from the catalog snapshot. Generate recovers when ComfyUI comes
  online without reloading the browser.
- Selected model chip; Gallery link; Clear chat menu; Settings toggle.
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
- A connectivity transition also refreshes the catalog once (debounced) so installed text models
  and warnings catch up with the engine state.
- Action group stays right-aligned with `ml-auto`.

### Chat messages

Oldest → newest. Each job renders as:

- right-aligned user prompt bubble with model/ratio/batch/time chips;
- left-aligned result card with status dot, job id, time and progress;
- queued/running: progress bar, `StageTimeline`, Cancel;
- error: readable message + stages;
- done: result grid, favorite/fullscreen actions, warnings, collapsible full settings;
- action row: View, Reuse, Use seed, Download, More menu;
- deletion menu: “Remove message only” or “Delete images & message”;
- per-image trash overlay on each result image;
- the shared `MediaViewer` action slot is favorite-only; per-image deletion stays on the card,
  not duplicated in the viewer;
- the settings disclosure must include prompt used, negative prompt, seed, model, ratio, size,
  batch, LoRAs, enhancement, upscale, final size and job timing.

### Settings drawer

- Desktop static column, `w-[390px]`; mobile fixed overlay.
- Each section uses `AppSelect`, `AppSwitch`, `AppSlider`, `AppButton` and semantic tokens.
- Bind directly to the store form; no local copies.
- Prompt character counter and negative prompt live here.
- Enhancement panel: provider/model, fallback toggle, Generate preview, loading/cancel state,
  preview text, Use result / Discard, approved prompt, and the advanced custom system brief
  (cards template, backend-default reset, backend-default preview).
- Sampling panel: base steps/CFG/sampler/scheduler/denoise + refine steps/CFG/denoise.
- Upscale panel: visible path select, on/off switch, slider + exact value, recommended hint, model
  min/max explanation.
- LoRA chain: compatibility-filtered list, add/remove, per-LoRA strength slider + switch,
  auto-inject triggers, count/limit.
- Prompt extras: auto triggers, negative prompt, prompt character budget.
- Advanced (runtime): default-on unload of the Ollama enhancement model before ComfyUI starts.
  It applies to previews and queue jobs, has its own reset, and explains that a failed unload is
  non-fatal.

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
- returns `{ id, deleted, assetsTrashed, assetsMissing }`;
- after asset deletion, sync the library and remove the card/viewer items;
- the card's per-generation Delete menu is the only chat-level deletion control; the
  per-image trash overlay is the only image-level control on the card. Do not add a second
  trash action to `MediaViewer`.

Clearing history (module-owned):

- `DELETE /jobs?deleteAssets=false` clears only T2I_main chat records and keeps all images.
- `DELETE /jobs?deleteAssets=true` also moves every result image in this module's history to
  library trash. Other GenModules, other modules' jobs, and favorites are untouched.
- Both clear variants return `{ deleted, jobIds, assetsTrashed, assetsMissing }`.
- Any queued/running T2I_main job rejects the whole clear with `422 job_running`; nothing is
  cancelled or deleted. The user must cancel or wait first.
- The backend enumerates the full module history, not just the 60-card page, then soft-deletes
  each job. The frontend removes returned ids, stops polling, releases engine slots, closes the
  viewer, and resyncs Library/Jobs.
- The Clear menu must expose both options with scope-aware, count-free confirmations. It is
  disabled while the store is busy, but the backend rejection remains authoritative.
- Never call the generic `/api/jobs` API to clear or delete module history.

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
- Slots: `actions` (`item`) for favorite (and Gallery-only trash), `info` (`item`) for extra
  metadata.
- T2I's viewer action slot is **favorite-only**. Per-image deletion is the card overlay and
  per-generation deletion is the card menu; a viewer trash button would be a duplicate.
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
- [ ] A saved 0-active LoRA chain survives reload/rebuild/backend restart; a second tab cannot
      resurrect the pack defaults.
- [ ] Custom enhancement system prompt survives reload; empty means backend default; changing
      the prompt or brief invalidates an approved rewrite.
- [ ] The Advanced runtime card's unload toggle defaults on, persists, resets, and is sent on
      both preview and job requests. A failed unload is non-fatal.
- [ ] ComfyUI/provider readiness updates from `/api/status` without a reload; Generate recovers
      when the engine comes online.
- [ ] Each settings panel resets only its own slice; global reset is confirmed.
- [ ] Model/range changes reconcile stale saved values and notify once.
- [ ] New results appear in chat, Library and Gallery; Gallery refreshes on mount.
- [ ] Result card shows full applied settings, warnings, media viewer and deletion actions.
- [ ] The T2I viewer has no trash action; per-image trash remains on the card overlay.
- [ ] Running jobs reattach after navigation/reload; engine busy state is correct and not
      double-counted.
- [ ] Deleting with assets moves them to trash; deleting message-only keeps them in Library.
- [ ] Clear chat keeps media; Clear chat + media trashes this module's results; both stay scoped.
- [ ] Clear/delete are refused while a queued/running job exists; no silent cancel.
- [ ] Per-image trash removes the image from Library/chat without deleting unrelated history.
- [ ] `npm run typecheck` and `npm run build` pass; backend `uv run python -m pytest -q` passes.
- [ ] Browser console clean.

## 9. Gotchas

- API history is newest-first; the store reverses once for chat order.
- Job ids contain `#`; encode them.
- Do not clear `form.prompt` after generation. Only `approvedPrompt` is consumed by a job.
- Editing `form.prompt` or `form.enhanceSystemPrompt` clears `approvedPrompt`/the preview and
  aborts an in-flight enhancement; a rewrite must never leak onto different text or a different
  brief.
- An omitted/`null` enhancement `systemPrompt` uses the backend default. An explicit empty string
  is an empty override; the UI sends `undefined` instead.
- A saved LoRA chain with every entry `on: false` is a valid “0 LoRA” setting. Do not re-apply
  pack defaults on restore/catalog refresh. Persist toggles immediately, sync `storage` events,
  and skip identical writes so tabs cannot ping-pong.
- The enhancement-model unload is Ollama-only and best-effort. Never global-free ComfyUI and never
  fail a job because the unload failed; return/record the warning and continue.
- Do not duplicate deletion controls. T2I keeps per-generation delete in the card menu and
  per-image trash on the card overlay; the viewer is favorite-only.
- `AppPopover` does not toggle itself. Every trigger needs `@click="open = !open"`.
- Clear/delete are module-scoped and must reject active jobs. Never use generic `/api/jobs`
  history deletion from a module.
- Clear operates on the full module history, not just the visible page; keep confirmation wording
  count-free.
- `lockSeed: true` sends `seed`; otherwise omit it and the backend randomizes.
- Selecting the `none` upscaler disables upscale; turning the switch off preserves the last path.
- A restored form is reconciled against the current pack, not trusted blindly.
- `deleteJob` is soft delete. Do not add a hard-delete SQL path.
- Missing result assets after a library sync are deleted assets, not broken URLs.
- Never call `useChatStore.send()` from T2I; jobs are backend-owned.
