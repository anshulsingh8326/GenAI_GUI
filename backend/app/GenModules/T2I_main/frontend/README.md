# T2I_main - frontend contract (strict Text -> Image)

This folder is the canonical frontend deliverable for the T2I_main GenModule.
It is deliberately kept next to the module backend so the API contract, range
rules and GUI behaviour travel together. The visual implementation lands next;
this page shell is already wired to the real API.

Runtime status: `types.ts`, `api.ts` and `T2IPage.vue` are copied into
`frontend/src/features/text-to-image/` and the existing route
(`frontend/src/router/index.ts`) now renders this functional shell. The visual
polish pass is still next; the copied module files are the canonical contract
source until that pass is complete.

---

## 1. Scope

Strict Text -> Image only:

- Krea 2 Turbo model (int8, or Q5 GGUF when installed)
- LoRA chain with per-LoRA strength and automatic trigger injection
- latent refine (default) or optional 4x-UltraSharp, or no upscale
- prompt enhancement through Ollama or ComfyUI, with preview/approve
- aspect ratio + long side, batch, seed
- advanced sampling (steps, CFG, sampler, scheduler, base denoise, refine)

Never add here:

- identity/reference-image inputs
- image-to-image, edit, describe, face-swap
- IAMCCS or switch nodes (the backend composes/prunes blocks instead)

---

## 2. Backend endpoints

Base URL is same-origin: `/api/t2i`. No CORS or base-URL setting is needed.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/catalog?modelId=...` | Complete GUI contract: models, LoRAs, upscalers, text models, ranges, defaults, presets, engine status, warnings. |
| `GET` | `/pack` | Secret-free summary of the tracked pack (debug/ops). |
| `POST` | `/validate` | Validate and normalize a `T2IJobRequest`; returns the actual size/seed/graph summary. Creates no job. |
| `POST` | `/enhance` | Rewrite one prompt through Ollama/ComfyUI. Creates no job. |
| `POST` | `/jobs` | Validate, persist and start a job. Returns the job record immediately. |
| `GET` | `/jobs?limit=80` | Recent T2I jobs (module-scoped). |
| `GET` | `/jobs/{job_id}` | One job with stages, params and result asset ids. |
| `POST` | `/jobs/{job_id}/cancel` | Best-effort cancel. Finished jobs are a no-op. |

Job ids contain `#` (for example `#141`). Always encode the id in a URL:
`encodeURIComponent(jobId)` -> `%23141`. The bundled `api.ts` does this.

### Error shape

`422` from the module validation layer:

```json
{
  "detail": {
    "code": "validation_error",
    "message": "Size 2000 is outside this model's safe range 512-1536.",
    "errors": [
      {
        "code": "out_of_safe_range",
        "message": "Size 2000 is outside this model's safe range 512-1536. A pro user can widen the safe range in the T2I pack JSON, up to the hard limit.",
        "field": "size",
        "min": 512,
        "max": 1536
      }
    ],
    "warnings": []
  }
}
```

`503` when an engine is unavailable:

```json
{ "detail": { "code": "engine_error", "message": "ComfyUI is not reachable at http://127.0.0.1:8188. Start it and try again." } }
```

FastAPI can still return its own `422` list for a malformed transport body
(for example a string where a number is required). The API client normalizes
both shapes.

---

## 3. Source of truth and range rules

The tracked pack under `backend/.../T2I_main/backend/pack/` is authoritative:

| File | GUI use |
| --- | --- |
| `models.json` | model labels, loader/file bindings, per-model safe ranges and defaults |
| `loras.json` | LoRA bindings, triggers, per-LoRA safe ranges, exclusions |
| `upscalers.json` | `none`, `latent-refine`, `4x-ultrasharp` paths and values |
| `text_models.json` | ComfyUI text model + Ollama discovery/preferred list |
| `options.json` | recipe id, Freeze v8 defaults, ratios, sizes, samplers, limits |
| `workflows/krea2_t2i.api.json` | the composable base workflow (no switch nodes) |

Rules the GUI must respect:

1. **Never clamp silently in the client.** The input sliders use the safe
   `min`/`max` from the catalog. The backend re-checks every value.
2. **Safe range vs hard range.** `min`/`max` are the model's safe range;
   `recommendedMin`/`recommendedMax` are a narrower warning band;
   `hardMin`/`hardMax` are the ComfyUI/model limits. Pro users widen the safe
   range by editing the pack JSON, never above the hard range.
3. **The backend is the final authority.** An API/agent call cannot bypass the
   same checks. A form value that is stale after a model switch must be fixed
   before Generate.
4. The user-owned `data/model_catalog.json` only supplies installed-file
   presence, labels and user trigger words. It never overrides T2I ranges.

### Freeze v8 defaults (must remain the reset target)

| Control | Base | Latent refine |
| --- | --- | --- |
| steps | 12 | 6 |
| CFG | 2.5 | 2.0 |
| sampler / scheduler | euler / simple | same |
| denoise | 1.0 | 0.45 |
| size | ratio long side 1024 | long side 1536 |

The default LoRA chain is the five Freeze v8 entries returned in
`catalog.defaults.loraChain`, in order, with the strengths from the pack.

---

## 4. State initialization

1. `GET /api/t2i/catalog`.
2. Use `catalog.selectedModelId` and `catalog.defaults` for the initial form.
   The defaults already reflect the selected model's sampler/CFG/steps.
3. Populate LoRA rows from `catalog.defaults.loraChain`; keep their order.
4. Populate enhancement from `catalog.defaults.enhance` and
   `catalog.textModels`.
5. Populate the upscaler from `catalog.defaults.upscaler`.
6. Keep `catalog.engine.comfyui.connected`: disable Generate and show a clear
   "ComfyUI offline" action when false. Do not fake a queue.
7. Surface `catalog.warnings` (missing model/LoRA, untested path, empty user
   catalog, Ollama offline). Warnings are not errors.

When the model changes:

- reset steps/CFG/sampler/scheduler/denoise and refine defaults to the new
  model's defaults;
- reset the size if it is outside the new model's long-side range;
- remove LoRAs that are not compatible with the new base;
- keep the prompt, negative prompt and enhancement preview.

---

## 5. Layout and controls

The page is a two-column composer with a right-side run panel. It must work at
1280 px and stack cleanly below ~1024 px.

### Header

- Module label: **Text -> Image**
- Recipe: **Krea 2 Turbo / Freeze v8**
- ComfyUI status dot + text (`ready`, `offline`, `checking`)
- Optional Ollama status chip; Ollama is only needed for enhancement.

### Prompt block

- Main prompt textarea (required, max `catalog.limits.promptMaxChars`).
- Negative prompt (optional, max `catalog.limits.negativePromptMaxChars`).
- Character counters and a short "strict T2I" hint.
- No identity/reference-image drop zone.

### Model + size row

- Model select. Show `label`, `shortLabel`, and badges:
  `missing` (disabled), `untested`, `int8`, `Q5 GGUF`.
- Ratio buttons/select from `catalog.ratios`. Show a visual aspect box.
- Size select from `catalog.size.values`; label it **long side**. The actual
  width x height is derived from the ratio and rounded to `size.step`.
- Optional explicit width/height disclosure for agents/pro users. If either is
  set, both are required; show the resulting exact dimensions.
- Batch input (1..model range max).
- Seed input + lock toggle. Unlocked means every request uses a fresh seed;
  the resulting job shows the actual seed. A "dice" button regenerates the
  displayed seed.

The backend accepts `ratio + size` or `width + height`. The GUI should prefer
ratio + long side for normal use. The output preview must show the normalized
`normalized.width` x `normalized.height` from `/validate`, not just the input.

### LoRA chain

- List only `t2i` LoRAs compatible with the selected model, sorted by
  `defaultOrder`.
- Each row: checkbox, label, file-present badge, trigger chips, strength
  slider/number with `min`, `max`, `step`, recommended band.
- Adding a LoRA inserts its default strength. Removing keeps the rest of the
  order stable. Reordering is optional but the request sends `order`.
- The default Freeze chain is already populated; the user can toggle rows. A
  default entry whose file is known-missing starts unchecked/absent so the
  first Generate does not fail on an unrelated missing LoRA.
- Automatic triggers: global toggle (`autoTriggers`). Show a read-only preview
  of the trigger words that will be prepended. Never let the user duplicate a
  trigger already present in the prompt (backend handles this).
- A missing LoRA is disabled; an excluded LoRA is not shown at all.
- The backend enforces `limits.maxLoras`.

### Prompt enhancement

- Toggle **Improve prompt**.
- Provider select: `Ollama` or `ComfyUI`. If a provider is offline, keep it
  visible but disabled with a reason.
- Model select grouped by provider, from `catalog.textModels`:
  - ComfyUI entries use the `id` (for example `qwen3vl-4b-comfy`).
  - Ollama entries use `model` (for example `huihui_ai/gemma-4-abliterated:12b-qat`).
  - Never show embedding-only Ollama models (the backend already filters them).
- Buttons:
  - **Preview enhancement** -> `POST /enhance`; show the rewritten text in an
    editable box with **Use this prompt**, **Regenerate**, **Discard**.
  - **Use this prompt** sets `enhancedPrompt` on the next job. The job's
    `enhance.mode` becomes `approved`, so the backend does not rewrite again.
- **If enhancement is enabled and no approved prompt is sent**, the backend
  auto-runs it as the first job stage.
- **Fallback to original prompt** toggle: only applies to auto-enhancement in
  the job runner. If enhancement fails and this is on, the job continues with
  the original prompt and records an `enhance_failed` warning. If off, the
  job fails at the `enhance` stage.
- The preview request can take tens of seconds (Ollama local model load or a
  cold ComfyUI text model). Show a spinner and a Cancel/Abort action; do not
  block the rest of the form.
- The system prompt comes from Settings -> Text & Prompts. Do not duplicate a
  prompt editor here; link to Settings.

### Upscaler

Single-choice path:

| Id | Behaviour |
| --- | --- |
| `none` | Decode base size; ignore refine values. |
| `latent-refine` | Default Freeze path. Base sample at 1024 long side, then latent refine at 1536 long side. Refine steps/CFG/denoise shown. |
| `4x-ultrasharp` | Optional ESRGAN after decode, using the installed `4x-UltraSharp.pth`. Value is the target long side. |

- Show the model's value range (for latent it is
  `model.ranges.refine.scale`; for ESRGAN it is `upscaler.valueRange`).
- Display the estimated final width x height. Latent refine preserves the base
  aspect ratio; the value is the **long side**, not necessarily square.
- Show a missing-file badge (4x) and disable the path if absent.
- These are alternatives, not a chain. Do not build "latent refine then ESRGAN"
  in this module.

### Advanced

Collapsed by default. Show:

- base steps, CFG, denoise
- sampler and scheduler (from catalog lists)
- refine steps, CFG, denoise (only when latent refine is enabled)
- seed lock state
- **Reset to Freeze v8** button

The reset sets the selected model's defaults, the default LoRA chain, the
default upscaler path and the pack defaults. It does not clear the prompt.

### Run panel

- Generate button (disabled if prompt empty, ComfyUI offline, model missing, or
  another job is running).
- Validation warnings list.
- Job status: stages `enhance -> compose -> submit -> generate -> collect`,
  with status icon, detail and duration. Progress bar.
- Cancel button while running.
- Error card with the readable backend message and a Retry action.
- Result grid from `job.resultIds`:
  `GET /api/assets/{asset_id}/file` for full images,
  `GET /api/assets/{asset_id}/thumb` for previews. Use `encodeURIComponent`.
- Show the actual seed, dimensions, LoRA chain and applied enhancement in a
  collapsible details block.

---

## 6. Generate flow

Recommended flow:

1. Build `T2IJobRequest` from the form.
2. `POST /validate` (optional but useful): show warnings and normalized
   dimensions/seed. If it fails, focus the first error field and do not create
   a job.
3. `POST /jobs` with the same request.
4. Poll `GET /jobs/{id}` every ~900 ms while `queued` or `running`.
5. On terminal status, render results/errors and stop polling.
6. If the page reloads, list recent T2I jobs and reattach to any `running`
   job (the backend resumes submitted jobs after a restart).

A request example:

```json
{
  "prompt": "portrait of a woman in a rainy city at night",
  "negativePrompt": "",
  "modelId": "krea2-turbo-int8",
  "recipeId": "krea2-t2i-v1",
  "ratio": "1:1",
  "size": 1024,
  "batch": 1,
  "lockSeed": true,
  "seed": 123456789,
  "loras": [
    { "id": "lora-xcreampiex-krea2-v1-1-000002500", "strength": 1.0, "on": true, "order": 0 },
    { "id": "lora-krea2-g4ngb4ng-v1", "strength": 2.0, "on": true, "order": 1 }
  ],
  "autoTriggers": true,
  "enhance": {
    "enabled": false,
    "provider": "ollama",
    "model": "huihui_ai/gemma-4-abliterated:12b-qat",
    "fallbackToOriginal": false
  },
  "advanced": {
    "steps": 12,
    "cfg": 2.5,
    "sampler": "euler",
    "scheduler": "simple",
    "denoise": 1.0,
    "refine": { "steps": 6, "cfg": 2.0, "denoise": 0.45 },
    "upscaler": { "id": "latent-refine", "enabled": true, "value": 1536 }
  },
  "tab": "text-to-image"
}
```

An approved enhancement is sent as `enhancedPrompt`; the backend uses it as the
base prompt and adds triggers if `autoTriggers` is on.

---

## 7. Error and warning UX

Map errors by `field` when present; otherwise show a top-level error card.
Fields used by the backend include:

`prompt`, `negativePrompt`, `modelId`, `recipeId`, `width`, `height`, `ratio`,
`size`, `batch`, `seed`, `loras`, `enhance.provider`, `enhance.model`,
`advanced.steps`, `advanced.cfg`, `advanced.denoise`,
`advanced.refine.steps`, `advanced.refine.cfg`, `advanced.refine.denoise`,
`advanced.upscaler.id`, `advanced.upscaler.value`.

Common codes:

- `out_of_safe_range` / `out_of_hard_range` - fix the control or tell the pro
  user to edit the pack JSON.
- `outside_recommended` - warning only, do not block.
- `model_missing`, `lora_missing`, `upscaler_missing` - file not installed.
- `unknown_model`, `unknown_lora`, `unknown_upscaler`, `unknown_ratio`,
  `unknown_sampler`, `unknown_scheduler` - stale catalog; reload.
- `prompt_required`, `prompt_too_long` - prompt constraints.
- `embedding_model` - selected Ollama model cannot generate text.
- `engine_error` (HTTP 503) - ComfyUI/Ollama is not running; keep the form and
  offer Retry.
- `internal_error`/`pack_error` (HTTP 500) - show the message, log the request,
  do not loop retries.

Warnings should be visible but not modal. Do not silently drop them.

---

## 8. Agent/MCP parity

The same request body is the future MCP tool input. Keep the contract
client-agnostic:

- no browser-only fields in the job request;
- no hidden auto-approval of enhanced prompts for agents unless the agent
  explicitly sends `enhancedPrompt` or `enhance.fallbackToOriginal`;
- `POST /validate` is the cheap preflight;
- the backend's range checks are the only source of truth.

---

## 9. Pro range editing

A pro user edits the pack JSON (tracked or installed copy) and reloads. The
backend reloads the pack per request, so a restart is not required for range
changes. If the deployed pack is read-only, expose a documented override copy
in the installer/settings workflow; do not add a free-form range editor to the
T2I page in this phase.

Never let a GUI control exceed `hardMin`/`hardMax`. If the user asks for more,
that is a pack/engine change, not a form value.

---

## 10. Integration checklist

Done in this phase:

1. `types.ts` and `api.ts` are copied into
   `frontend/src/features/text-to-image/`.
2. `T2IPage.vue` is copied there and the existing route renders it. Imports are
   relative (`./api`, `./types`).
3. `npm run typecheck` and `npm run build` pass.

Visual pass (next):

4. Replace the plain controls with the app primitives (`AppButton`,
   `AppSelect`, `AppModal`, `AppInput`) while keeping the same state flow.
   Use the design tokens (`bg-surface`, `text-muted`, `border-border`,
   `text-accent`, `bg-accent-soft`, `text-danger`, `text-warn`); Tailwind v4
   already scans `frontend/src/**`.
5. Keep the existing route. `manifest.json` advertises
   `frontend/T2IPage.vue`; the runtime path is the `frontend/src` copy.
6. Do not import from another GenModule. The module may use `@/components`,
   `@/lib` and `@/stores`.
7. On a live ComfyUI, run the acceptance checklist below.

---

## 11. Acceptance checklist (live)

- Catalog loads with ComfyUI on/off; Generate disabled when off.
- Defaults match Freeze v8: 12 / 2.5 / euler / simple / 1.0; refine 6 / 2.0 /
  0.45 / 1536.
- Toggling a LoRA adds/removes exactly one chain entry; triggers preview.
- Changing model updates ranges and removes incompatible LoRAs.
- 1:1 at 1024 produces a 1536x1536 refined output by default.
- 16:9 at 1024 produces the expected long side; refine preserves the ratio.
- `none` / latent / 4x paths are mutually exclusive; missing 4x file is disabled.
- Invalid values are rejected by the backend even if a client bypasses the
  slider; the field path is shown in the error.
- Enhancement preview works through Ollama and through ComfyUI (when the
  rgthree + TextGenerate nodes are available); approved text is used once.
- Auto-enhancement with fallback continues on provider failure; without
  fallback it fails at the `enhance` stage with a readable error.
- Cancel while generating stops the prompt; finished jobs are a no-op.
- Reload during a submitted job reattaches and collects results.
- Results appear in the library and job details expose seed/dimensions/LoRAs.

Known unverified live items from the backend phase: ComfyUI `object_info` for
the exact installed node versions, `TextGenerate` dynamic-combo serialization,
and one real Krea2 generation. The graph intentionally uses flattened
`TextGenerate` inputs (`"sampling_mode": "on"`, `"sampling_mode.temperature": ...`)
until that live check is done.
