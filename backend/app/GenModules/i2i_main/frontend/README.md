# i2i_main — frontend contract (strict Image → Image)

Canonical frontend deliverable for the `i2i_main` GenModule. It sits next to the module backend
so the API contract, range rules, source limits and GUI behaviour travel together. The runtime
copy lives in `frontend/src/features/image-to-image/` and is what Vite builds.

This is a **strict Image → Image** module: one to three reference images in, one edited image per
batch item out. There is no text-only path, no identity lock, no face swap and no inpainting
mask. Do not add a “generate without a source” shortcut.

## Files

```text
frontend/
  README.md                 this contract
  types.ts                  wire types
  api.ts                    same-origin client (/api/image-to-image)
  store.ts                  module store: form, references, persistence, catalog, jobs, actions
  I2IPage.vue               compact chat workspace + reference drop/upload composer
  I2ISettingsPanel.vue      right drawer, per-panel resets
  I2IGenerationCard.vue     chat result card, settings disclosure, deletion
```

Runtime copy: `frontend/src/features/image-to-image/`. Keep imports aligned with the app (`@/`
aliases); do not import from the backend folder at runtime. Reusable media viewing lives in
`frontend/src/components/media/MediaViewer.vue`.

---

## 1. Scope

- One tracked pack, `qwen21`, one model entry (`qwen21-turbo-edit`), one recipe
  (`qwen-i2i-turbo-v1`) and one API graph (`workflows/qwen_i2i.api.json`).
- Qwen Image 2.1 Turbo + Qwen3-VL 8B text encoder + Qwen Image 2.1 VAE. The diffusion model is a
  one-of choice (bf16 or a GGUF quant); the catalog resolves the real filename and binds it into
  the graph, so a renamed file still works.
- Up to three reference images. They are bound to `TextEncodeQwenImage21` as
  `images.image_1`, `images.image_2` and `images.image_3`; the GUI labels them **Image 1..3**
  while prompts address them as `<image1>`, `<image2>` and `<image3>`. Unused slots are pruned
  from the graph instead of left with dangling links.
- Denoise is the main creative knob:
  - `denoise == 1.0` → `TextEncodeQwenImage21` emits the empty 64-channel latent at Image 1's
    size and `SamplerCustom` runs the checkpoint's own 8-step turbo sigmas (fed by
    `ManualSigmas`, euler). `RepeatLatentBatch` applies the requested batch.
  - `denoise < 1.0` → the first reference is scaled, VAE-encoded and batched instead of the
    encoder latent, then sampled with the tail of the same sigma schedule.
  The graph is pruned per request; there is no switch node.
- Resolution `0` keeps the first reference size rounded to 32 px. A positive value is a **total
  pixel budget** that preserves the aspect ratio. The pack defaults to `1024`, the model's
  official budget.
- Batch 1–4; each item is an independent variation of the same references and prompt.
- Steps 4–20, default `8`. Turbo ships its 8-step sigma schedule; other counts interpolate it
  and can reduce fidelity, so the UI warns when it is not 8.
- CFG 1.0–8.0 with 1.0 recommended. The old `KSampler` + `simple` scheduler is gone: it produced
  a much steeper sigma curve than the checkpoint's schedule.
- Sampler is selectable (Euler, Heun, DPM++ 2M, DPM++ 2M SDE). Sigmas always come from
  `ManualSigmas`, not a built-in scheduler.
- Persisted settings, size-gated persisted reference images, module-scoped chat history, library
  results and soft deletion.

Out of scope: prompt enhancement, LoRAs, upscalers, ratio presets, masks, more than three
reference images, video.

## 2. API contract

All calls are same-origin under `/api/image-to-image`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/catalog?modelId=` | model, components, ranges, defaults, resolutions, samplers, source limits, engine status, preflight |
| `GET` | `/pack` | secret-free pack summary for debug/ops |
| `GET` | `/setup` | missing required files/groups, destinations, links for the setup modal |
| `POST` | `/validate` | normalize/validate without creating a job |
| `POST` | `/jobs` | create and start a job |
| `GET` | `/jobs?limit=` | module-scoped history, **newest first** |
| `GET` | `/jobs/{id}` | one job |
| `POST` | `/jobs/{id}/cancel` | best-effort cancel |
| `DELETE` | `/jobs/{id}?deleteAssets=true\|false` | soft-delete one terminal job; optionally trash results (default `true`) |
| `DELETE` | `/jobs?deleteAssets=true\|false` | clear this module's whole chat; optionally trash all module results (default `false`) |

Job ids contain `#`. Always call `encodeURIComponent(jobId)` before building a URL.

The create request carries the complete resolved selection:

```json
{
  "modelId": "qwen21-turbo-edit",
  "recipeId": "qwen-i2i-turbo-v1",
  "prompt": "Change the jacket to a deep red leather jacket",
  "negativePrompt": "",
  "sourceImages": [
    { "image": "data:image/png;base64,...", "name": "portrait.png" },
    { "image": "data:image/png;base64,...", "name": "jacket.png" }
  ],
  "resolution": 0,
  "batch": 1,
  "seed": 123,
  "lockSeed": true,
  "cfg": 1.0,
  "denoise": 1.0,
  "sampler": "euler",
  "tab": "image-to-image"
}
```

Each reference is sent as a data URL. The backend decodes every image, enforces the pack's
size/mime limits, normalizes it, stores a small JPEG thumbnail per reference in
`job.params.sources[i].thumbnail` for the chat card, and uploads the real bytes to ComfyUI's input
folder only when the job starts. `sourceImage` / `sourceName` remain as a single-image fallback for
older clients.

### First-open setup

`GET /setup` returns the shared `ModuleSetupPayload` (see `frontend/src/types.ts`). Fetch it once
on mount and auto-open `frontend/src/components/content/ModuleSetupModal.vue` only when
`ready === false`; `ready: null` means the user catalog is unavailable, not that every file is
missing. A header **Setup** button reopens the modal and refreshes the check. The modal only
reports files and opens links; it never downloads, installs, moves or deletes anything.

Three required one-of groups: diffusion model, text encoder, 2.1 VAE. The older
`qwen_image_vae.safetensors` is reported but never satisfies the 2.1 VAE group.

### Errors and warnings

The client normalizes FastAPI validation and transport errors into `I2IApiError`:

- `code` — `validation_error`, `request_validation`, `job_running`, `backend_offline`, ...;
- `errors` — structured field errors from the service;
- `warnings` — non-fatal range/engine warnings.

Show the first error in the page; show warnings as a list above the composer and on the card.
The backend is authoritative. The GUI may clamp only during **restoration** of stale saved
settings, and must tell the user when it did.

## 3. Form state, reference images and persistence

`store.ts` owns the durable form and the reference list. The page owns only transient UI (drawer
open, viewer open, scroll position, drag state).

Storage:

```text
form:    genai.image-to-image.form.v1     { version: 2, savedAt: <ms>, form: { ... } }
sources: genai.image-to-image.sources.v2  { version: 2, savedAt: <ms>, sources: [ ... ] }
legacy:  genai.image-to-image.source.v1   read once for migration, then removed
```

The references are stored **together** and only while their combined data URLs are at or under the
pack's `source.persistMaxChars` (2,500,000 characters). Above that:

- the images stay in memory for the session;
- any previously saved set is removed so a reload cannot resurrect unrelated images;
- the UI shows “session only” plus `sourceNotice` and never claims they were saved.

Form fields:

- prompt, negative prompt;
- model id, resolution, batch, seed, lock seed;
- cfg, denoise, sampler.

Behaviour:

1. Restore only known keys and correct primitive types.
2. Merge over pack defaults (a fresh seed is generated, never restored from another module).
3. After the catalog arrives, reconcile:
   - unknown model → the pack default, then any installed model;
   - a saved model whose files are missing → an installed alternative;
   - unknown resolution/sampler value → pack default;
   - batch/CFG/denoise clamped to the selected model's ranges, seed repaired;
   - the saved references re-checked against the real `persistMaxChars`.
4. Debounced autosave (~180 ms); flush on `beforeunload` and page `onBeforeUnmount`.
5. If reconciliation changed anything, show one toast:
   “Restored Image -> Image settings were adjusted to the current pack ranges.”
6. Listen to `storage` and adopt a newer saved form/reference set. Compare before writing so two
   tabs cannot echo each other.
7. A catalog refresh triggered by a ComfyUI connectivity flip must not wipe the form.

Per-panel resets (`resetPanel`):

| Panel | Resets |
| --- | --- |
| `source` | clears all reference images and their saved copy (the composer owns the main prompt) |
| `output` | model, resolution, batch, seed, lock seed |
| `sampling` | CFG, denoise, sampler |
| `prompt` | negative prompt |
| `advanced` | legacy cache fields only (not shown in the UI) |
| `all` | pack defaults, then clears the prompt and the references |

Each panel header has its own reset icon. The global reset is confirmed.

## 4. Layout

Compact chat workspace:

```text
header: I2I_MAIN · live engine status · model chip · Gallery · Clear · Setup · Settings
┌─────────────────────────────────────┬─────────────────────────┐
│ chat scroller                       │ settings drawer         │
│  user turn: Image 1..n + prompt      │  References             │
│  generation card                    │  Output                 │
│  ...                                │  Sampling               │
│                                     │  Prompt extras          │
│                                     │  Advanced (workflow)    │
│                                     │  Reset all              │
├─────────────────────────────────────┤                         │
│ composer: reference strip/drop zone │                         │
│  textarea + quick chips             │                         │
│ [Settings] [Generate]               │                         │
└─────────────────────────────────────┴─────────────────────────┘
```

### Header

- `I2I_MAIN` label, “Image → Image” title.
- ComfyUI state: checking / ready / offline, read live from the shared engine store
  (`/api/status`), not cached from the catalog snapshot. Generate recovers when ComfyUI comes
  online without reloading the browser.
- Selected model chip; Gallery link; Clear chat menu; Setup; Settings toggle.
- On desktop the drawer defaults open; on mobile it is a fixed overlay with backdrop.

### Composer

- Reference strip when images are selected: thumbnails labelled Image 1..n, per-slot Replace and
  Remove, an Add slot, target size and a session-only note.
- Empty state: a dashed drop zone (“Add reference images”) that also opens the file picker.
  Dragging files anywhere over the composer highlights it and appends them in order.
- Prompt textarea. `Ctrl+Enter` / `Meta+Enter` generates; plain Enter is a newline.
- Autosave label and character counter.
- Quick chips open the matching settings panel: model, resolution + target size, **denoise path**
  (green `full (official turbo)` / amber `img2img 0.55`), batch.
- Generate is disabled when the prompt is empty, no reference is selected, the catalog/model is not
  ready, ComfyUI is offline, or a job is already active.

### Chat messages

Oldest → newest. Each job renders as:

- right-aligned user turn: one labelled thumbnail per reference (click to expand), reference names
  and sizes → target size, path chip, the prompt, and denoise/batch chips. If the job has no
  stored thumbnail (older jobs), show a placeholder icon rather than a broken image;
- left-aligned result card with status dot, job id, time and progress;
- queued/running: progress bar, `StageTimeline`, Cancel;
- error: readable message + stages;
- done: result grid, favorite/fullscreen/trash actions, warnings, collapsible full settings;
- action row: View, Reuse, Use seed, Download, More menu;
- deletion menu: “Remove message only” or “Delete message + images”;
- per-image trash overlay on each result image.

“Reuse” restores the prompt and every setting, **not** the reference images: the job only keeps
thumbnails, so the references stay whatever the user has selected now. Say so in the toast when no
reference is selected.

The settings disclosure must include job id, model, recipe, reference count/names/sizes, output
size, resolution, path, batch, seed(s), lock seed, steps, CFG, sampler, scheduler, denoise, engine,
workflow node count, the uploaded ComfyUI filenames, prompt used and the negative prompt.

### Settings drawer

- Desktop static column, `w-[390px]`; mobile fixed overlay.
- Each section uses `AppSelect`, `AppSwitch`, `AppSlider`, `AppButton` and semantic tokens.
- Bind directly to the store form; no local copies.
- References panel: labelled thumbnails Image 1..n, per-slot Replace/Remove, Add image, Remove all,
  save-state note.
- Output panel: model, resolution, batch, seed + dice, lock seed, batch explanation.
- Sampling panel: denoise slider with its path note, CFG, sampler, fixed-step explanation.
- Prompt extras: negative prompt with counter.
- Advanced: workflow summary, reference binding note, per-reference upload note.
- Storage failures surface as a small visible error, never silently.

## 5. Generation and job lifecycle

1. Build the complete request from the form and the source data URL.
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
- the card's per-generation Delete menu is the only chat-level deletion control; the per-image
  trash overlay is the only image-level control on the card.

Clearing history (module-owned):

- `DELETE /jobs?deleteAssets=false` clears only `i2i_main` chat records and keeps all images.
- `DELETE /jobs?deleteAssets=true` also moves every result image in this module's history to
  library trash. Other GenModules, other modules' jobs, and favorites are untouched.
- Both clear variants return `{ deleted, jobIds, assetsTrashed, assetsMissing }`.
- Any queued/running `i2i_main` job rejects the whole clear with `422 job_running`; nothing is
  cancelled or deleted.
- The backend enumerates the full module history, not just the 60-card page.
- Never call the generic `/api/jobs` API to clear or delete module history.

## 6. Library and Gallery

- Results are PNGs written by the backend through `library.add_bytes` and referenced by
  `job.resultIds`.
- Use `assetFileUrl(id)` / `assetThumbUrl(id)` for `/api/assets/{id}/file|thumb`.
- After a terminal job, call `library.syncFromBackend()`.
- If the library has synced (`library.loaded`) and an asset id is missing, treat it as deleted:
  hide the image instead of rendering a broken fallback URL.
- The Library is image-only. This module must not attempt video/audio results.

## 7. Shared media viewer

Use `frontend/src/components/media/MediaViewer.vue` and `MediaViewerItem` from
`frontend/src/components/media/types.ts`.

- Props: `items`, `title`, `downloadable`, `showThumbs`, `info`.
- Models: `open`, `index`.
- Slots: `actions` (`item`) for favorite, `info` (`item`) for extra metadata.
- i2i's viewer action slot is **favorite-only**. Per-image deletion is the card overlay and
  per-generation deletion is the card menu; a viewer trash button would be a duplicate.
- Parent owns the item list: remove deleted items, close when empty, keep index valid.
- Do not add i2i settings logic to the viewer. Pass a flattened `meta` array.

Result items include the job id, model, path, reference names/sizes, output size, resolution, seed,
batch, CFG, sampler, scheduler, denoise and the prompt.

## 8. Acceptance checks

- [ ] Strict i2i: Generate stays disabled without a reference image; there is no text-only path.
- [ ] Upload and drag-drop append up to three references; oversize/wrong-type files are rejected
      with a readable message before the backend is called.
- [ ] Each reference is labelled Image 1..n in the composer, the settings drawer and the chat turn.
- [ ] The prompt can refer to `<image1>`, `<image2>` and `<image3>` and the backend binds them in order.
- [ ] References, prompt and every setting survive route switches and reloads.
- [ ] A set above `persistMaxChars` survives navigation but not reload, and the UI says so.
- [ ] Denoise 1.0 selects the full turbo path; any lower value selects the img2img path, and
      the composer chip matches.
- [ ] Steps is editable (4–20), defaults to 8, shows the off-8 warning, and survives reload/reuse.
- [ ] Advanced exposes KV-cache device/dtype and lists `SamplerCustom` + `ManualSigmas`.
- [ ] Resolution 0 mirrors the first reference rounded to 32; a positive budget preserves the aspect
      ratio and matches the size the backend reports.
- [ ] ComfyUI readiness updates from `/api/status` without a reload; Generate recovers when the
      engine comes online.
- [ ] Each settings panel resets only its own slice; global reset is confirmed and clears the
      references.
- [ ] Stale saved values reconcile once, with a single toast; a catalog refresh does not wipe the
      form.
- [ ] New results appear in chat, Library and Gallery.
- [ ] Result card shows each reference thumbnail, full applied settings, warnings, media viewer and
      deletion actions.
- [ ] Running jobs reattach after navigation/reload; engine busy state is correct and not
      double-counted.
- [ ] Deleting with assets moves them to trash; deleting message-only keeps them in Library.
- [ ] Clear chat keeps media; Clear chat + media trashes this module's results; both stay scoped.
- [ ] `npm run typecheck` and `npm run build` pass; backend `uv run python -m pytest -q` passes.
- [ ] Browser console clean.

### Live verification (2026-11-04, ComfyUI 0.37.0, RTX 4070 12 GB)

> These runs validated the node wiring with the earlier `KSampler` + `simple` scheduler. The
> `ManualSigmas` sigma fix was made afterwards and has not been re-run live, so treat it as
> implemented and unit-tested, not re-verified on the GPU.

- Two references, denoise 1.0, resolution 768, batch 1: job `#169` completed on the full path and
  produced an 896x672 PNG. The red cube from `<image2>` was placed on the table in front of the
  frame from `<image1>` with the rest of the room intact. `/api/assets/<id>/file` returned
  `200 image/png` and `/thumb` returned `200 image/jpeg`.
- Three references, denoise 0.6, batch 2: job `#170` completed on the `img2img` path (14 nodes,
  all three uploads, two result assets), confirming the VAEEncode branch and multi-reference
  batching.
- At denoise 0.6 the first reference stayed dominant and the requested additions were muted. That
  is expected for img2img; use 1.0 when the prompt must add or move content.
- Components used: `qwen-image-2.1-turbo-Q8_0.gguf` (UnetLoaderGGUF),
  `qwen3vl_8b_int8_convrot.safetensors` (CLIPLoader, type `qwen_image`), and
  `qwen_image_2.1_vae_bf16.safetensors`. Marked `tested: true` in the pack and requirements.

## 9. Gotchas

- API history is newest-first; the store reverses once for chat order.
- Job ids contain `#`; encode them.
- Reference data URLs are large. Never include the bytes in `job.params`; only thumbnails belong
  there.
- Do not clear `form.prompt` or the references after generation.
- Reuse cannot restore reference bytes; it restores settings only. Do not claim otherwise.
- Saved references are size-gated as a set. Never write them unconditionally to `localStorage`.
- `AppPopover` does not toggle itself. Every trigger needs `@click="open = !open"`.
- Clear/delete are module-scoped and must reject active jobs. Never use generic `/api/jobs`
  history deletion from a module.
- `lockSeed: true` sends `seed`; otherwise the backend randomizes.
- A restored form and restored references are reconciled against the current pack, not trusted.
- `deleteJob` is soft delete. Do not add a hard-delete SQL path.
- Missing result assets after a library sync are deleted assets, not broken URLs.
- Never call `useChatStore.send()` from i2i; jobs are backend-owned.
- The text encoder must live in `models/text_encoders`; a GGUF in `models/unet` is reported as
  misplaced and never bound into the graph.
- The older `qwen_image_vae.safetensors` is not the 2.1 VAE. Never accept it silently.
- Qwen Image 2.1 needs ComfyUI 0.37.0 or newer; that release ships
  `TextEncodeQwenImage21`, `QwenImage21Cache`, `ManualSigmas` and `SamplerCustom`. The graph uses
  those core nodes plus `KSamplerSelect`, `RepeatLatentBatch`, `ImageScale` and `VAEEncode`.
- Never replace `ManualSigmas` with a `KSampler` + `simple` scheduler. That curve drops sigma far
  faster than Turbo's shipped schedule and the edits lose fidelity.
- `steps` is not the same thing as the sigma count: a lower denoise trims the same curve, so the
  effective step count can be smaller than the requested one.
- The text encoder must include its vision tower (`qwen3vl_8b_bf16` or
  `qwen3vl_8b_int8_convrot`). A text-only GGUF can load, but it cannot encode the reference
  images, so it is not a supported encoder for this module.
