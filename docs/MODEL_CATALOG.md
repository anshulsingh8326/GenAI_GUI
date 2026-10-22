# Model & LoRA catalog

Status: **implemented**. This is the contract for `data/model_catalog.json`, the editable layer
between ComfyUI header inference and module recipes.

The catalog answers the questions a generation UI needs before it can run a workflow:

- which base models are installed, and which family each belongs to;
- which LoRAs belong to which model;
- the safe/default strength range for each LoRA (plus optional CLIP and partner-parameter
  ranges);
- which trigger words a LoRA needs, so they can be added automatically when it is active.

It is **metadata only**. Building or editing the catalog never loads a model, never downloads
anything, never moves/deletes a model file, and never touches the ComfyUI install. The only
write is `data/model_catalog.json` (or `$GENAI_DATA_DIR/model_catalog.json`).

## 1. Building and refreshing

Settings -> **Model catalog** -> **Build from ComfyUI** / **Refresh from ComfyUI**
(`POST /api/model-catalog/refresh`).

1. The backend re-runs the read-only ComfyUI inspection (Phase A): model folder scan plus
   safetensors/GGUF header reads. No model is loaded.
2. Existing entries are matched by normalized `target` + file `name`. Their `id`, labels,
   model links, triggers, ranges and notes are kept.
3. Intrinsic fields (`name`, `target`, `kind`, `role`, `architecture`, `base` when empty,
   `family`, `size`, `present`) are refreshed.
4. New files get new entries. Files whose LoRA/model is no longer found are **kept** and marked
   `present: false`; they are not deleted. If the file returns, the next refresh reuses the
   same entry.
5. LoRAs with `modelsAuto: true` are re-linked to all base entries with the same `base`.

The first build is explicit; a plain `GET /api/model-catalog` only reads the saved file and
does not scan or create anything. A corrupt JSON file is reported as an error rather than
silently replaced.

## 2. File shape

Objects are keyed by stable id in the file; the API returns sorted arrays plus computed fields.

```json
{
  "version": 1,
  "createdAt": "2026-10-22T14:41:45+00:00",
  "updatedAt": "2026-10-22T14:42:01+00:00",
  "source": {
    "comfyuiFolder": "D:/ComfyUI",
    "flavor": "portable",
    "version": "0.30.0"
  },
  "models": {
    "model-krea2-turbo-q5-k-m": {
      "id": "model-krea2-turbo-q5-k-m",
      "label": "krea2_turbo-Q5_K_M",
      "name": "krea2_turbo-Q5_K_M.gguf",
      "target": "unet",
      "kind": "image",
      "role": "base",
      "architecture": "qwen_image",
      "base": "krea2",
      "family": "Krea 2",
      "size": 8871195936,
      "present": true,
      "suggestedTarget": null,
      "notes": ""
    }
  },
  "loras": {
    "lora-krea2-g4ngb4ng-v1": {
      "id": "lora-krea2-g4ngb4ng-v1",
      "label": "KREA2_G4NGB4NG_V1",
      "name": "KREA2_G4NGB4NG_V1.safetensors",
      "target": "loras",
      "kind": "lora",
      "base": "krea2",
      "family": "Krea 2",
      "size": 228587768,
      "present": true,
      "triggers": ["G4NGB4NG"],
      "models": ["model-krea2-turbo-q5-k-m"],
      "modelsAuto": true,
      "strength": { "default": 0.8, "min": 0.0, "max": 1.5, "step": 0.05 },
      "clipStrength": {
        "default": 0.8,
        "min": 0.0,
        "max": 1.5,
        "step": 0.05,
        "enabled": false
      },
      "otherRanges": {},
      "notes": ""
    }
  }
}
```

### 2.1 Model entries

| Field | Meaning |
| --- | --- |
| `id` | `model-<slug-of-file-stem>`, suffixed `-2`, `-3` on collisions. Stable while the file stays at the same `target`/`name`. |
| `label` | User-facing name; starts as the file stem. Editable. |
| `name`, `target` | File name (relative path inside the category) and ComfyUI model folder. |
| `kind` | `image`, `video`, `audio`, `lora`, `vae`, `text_encoder`, `controlnet`, `upscaler`, `embedding`, ... from the header/inventory. |
| `role` | `base` for image/video/audio generation models; `companion` for VAE, text encoders, upscalers, etc. Only `base` entries can be linked from a LoRA. |
| `architecture` | Short header-derived architecture tag (`qwen_image`, `mmdit`, ...), if any. |
| `base` | Family key used for LoRA matching (`krea2`, `flux2-klein`, `minimax-h3`, ...). Best-effort from filename/header; editable. |
| `family` | Display label for `base`. |
| `size` | File size in bytes. |
| `present` | False when the last scan could not find the file. The entry is kept. |
| `suggestedTarget` | Inventory hint when a file sits in an unusual folder. Informational only; the app never moves it. |
| `loras` | **Computed by the API**, not stored: ids of LoRAs whose `models` contains this entry. |

Advanced users can rename a label or correct a base from the model's **Edit** dialog. Changing a
model's base re-runs auto-linking for LoRAs that still use `modelsAuto`.

### 2.2 LoRA entries

| Field | Meaning |
| --- | --- |
| `base` | Intrinsic family from the header (`krea2`, `flux2_klein_9b` -> `flux2-klein`, ...) or the filename. Editable. |
| `triggers` | Trigger words, deduped case-insensitively. Editable; empty is valid. |
| `models` | Explicit base-model ids this LoRA belongs to. |
| `modelsAuto` | Default `true`: on refresh, replace `models` with every `base` model matching this LoRA's `base`. Setting the links manually in the editor turns this off. Turning it on again lets auto-linking resume. |
| `strength` | `{default, min, max, step}` for the LoRA weight. Default: `0.8 / 0.0 / 1.5 / 0.05`. The composer initializes and bounds its slider from this object. |
| `clipStrength` | Same range shape plus `enabled`. For dual-strength LoRAs; `enabled` defaults to false. The catalog stores it for modules; the current mock composer uses the base strength only. |
| `otherRanges` | Optional named ranges for partner knobs (`steps`, `cfg`, `denoise`, ...). Each value is `{default, min, max, step}`. Recipes may consume these; the catalog does not force them on a workflow. |
| `present` | False when the last scan could not find the file. A missing LoRA cannot be added to a new chain, but its catalog entry and links stay. |
| `notes` | Free text (recommended usage, caveats). |

All ranges are validated server-side: finite numbers, `max > min`, `default` inside `min..max`,
`step > 0`. `otherRanges` is capped at 30 names; names use letters, numbers, `.`, `_`, `-`.
The raw file is pretty-printed and atomically replaced (`model_catalog.json.tmp` -> rename).
Unknown fields are preserved when the file is rewritten.

## 3. Trigger words

Trigger application happens at **send time**, not while typing:

- Only LoRAs with the chain switch **on** contribute.
- Triggers follow LoRA-chain order, deduped case-insensitively.
- A trigger already present in the prompt as a word is not appended again.
- The prompt is kept intact and the missing triggers are appended:
  `a portrait` + `G4NGB4NG` -> `a portrait, G4NGB4NG`.
- The textarea is not mutated, and the user message in chat shows the original text. The job
  prompt and generated asset carry the triggers.
- The LoRA popover shows each LoRA's triggers and a summary of what will be added.

Modules use the same rule through `app.engine_content.catalog.trigger_words(catalog, ids)` and
`prompt_with_triggers(catalog, prompt, ids)`. The frontend store mirrors it in
`promptWithTriggers()`.

## 4. API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/model-catalog` | Saved catalog; empty object until built. Read-only. |
| POST | `/api/model-catalog/refresh` | Scan ComfyUI headers and merge. Writes metadata only. |
| PATCH | `/api/model-catalog/loras/{id}` | Edit label, base, `models`, `modelsAuto`, triggers, strength, clipStrength, `otherRanges`, notes. |
| PATCH | `/api/model-catalog/models/{id}` | Edit label, base, notes. Re-runs auto-links. |

HTTP mapping: unknown id `404`, invalid range/link/JSON `400`, unreadable catalog `500`.
The GUI only sends the fields the user actually changed.

## 5. UI

**Settings -> Model catalog**

- Build/refresh with source path, updated time, counts (base models, LoRAs, trigger sets,
  missing files).
- Base model cards show family, architecture, size, linked LoRAs, and an Edit dialog.
- LoRA cards show base, triggers, weight range, CLIP/extra-range flags, linked models and an
  Edit dialog. Missing files are flagged.
- Filter LoRAs by base. Companion files (VAE, encoders, ...) are collapsed under the base
  models for reference.
- Edit LoRA: label, base, auto/manual model links, comma-separated triggers, strength range,
  optional CLIP range, advanced `otherRanges` JSON, notes. Validation errors stay in the
  dialog; the backend repeats all checks.

**Composer (image modes)**

- The LoRA chain reads this catalog (no fixture LoRAs). LoRAs for another base are marked
  "other base" but remain selectable for experimentation; missing files are disabled.
- Each new chain entry starts at the catalog default and uses its min/max/step range.
- Active triggers are summarized in the popover and appended by `chat.send()`.
- If the catalog has not been built, the popover links to Settings -> Model catalog.

## 6. Safety & limits

- Header reads only; no model load, no ComfyUI write, no download.
- Model files are never moved, renamed or deleted. Catalog entries are never deleted; a stale
  entry is `present: false`.
- The catalog file can be reset only by editing/removing that file; the Settings "Reset all"
  action does not touch it.
- Base inference is best-effort. Unknown families remain a slug (or unassigned) and can be
  corrected in the UI. Unusual headers may leave `kind: unknown`; the inventory's
  `suggestedTarget` is shown but never acted on.
- Phase C downloads, hashes and shipped catalog sources are separate; this file starts from
  the user's existing files.

## 7. Verification

Covered by backend probes and an isolated UI run (scratch `GENAI_DATA_DIR`, fake/real
read-only roots; no model server touched):

- build from a folder with base models + LoRAs, auto-links per base, unassigned LoRAs;
- refresh preserves labels, triggers, strength/clip ranges, notes and manual links;
- missing files stay with `present: false`;
- invalid range, unknown model id and malformed triggers are rejected;
- Settings builds/refreshes from the UI and edits a LoRA;
- composer shows catalog LoRAs and ranges, appends the trigger once, and never duplicates a
  trigger already typed in the prompt.
