# ComfyUI content management (custom nodes + models)

Status: **Phase A + A.5 + B implemented** (folder detection, read-only requirements audit,
core baseline, model inventory with header-derived kinds, pinned node/package installer, and
the local editable model/LoRA catalog). Phases C–D are planned, not built. This doc is the
contract for all of them; implementation notes live in `docs/COMFYUI_INSTALLER.md` and
`docs/MODEL_CATALOG.md`.

The GUI is a studio on top of ComfyUI - it does **not** bundle it. Users bring their own
ComfyUI (portable download, ComfyUI Desktop, or a dev git clone); the app learns where it
lives and then manages the *content* inside it: the custom nodes and model files that the
generation modules need.

## 0. Principles

- **Connect, never bundle.** ComfyUI is 2–3 GB plus 6–50+ GB of models; a repo can't carry
  that, and users already have installs + model libraries. Nothing is ever downloaded or
  installed without an explicit user click.
- **Reads are free, writes are clicks.** Status/inspection endpoints only look at folders.
  Installs and downloads are separate, explicit actions with progress and logs.
- **Never delete.** Removal (if ever added) follows the trash rule from the root README -
  files move to `data/trash`, they are never hard-deleted. Phase A doesn't write at all.
- **Verify.** Downloads land as `.part` files, are checked against `sha256` + size, then
  renamed into place. Reuse detection runs before any download (a model already present in
  any known root is *reused*, never re-fetched).
- **Works with any flavor** - ComfyUI Portable, ComfyUI Desktop, dev clone. The folder
  detection tells us which Python runs `pip` for node installs.

## 1. Folder detection & flavors

Settings key: **`comfyuiFolder`** (Settings → Connections, block "ComfyUI folder") - the
ComfyUI **source folder**, i.e. the one containing `main.py`, `custom_nodes/` and `models/`.

| Flavor | Marker | Python used for `pip` |
| --- | --- | --- |
| **portable** | `..\python_embeded\python.exe` next to the source folder | `<root>\python_embeded\python.exe` |
| **venv** (Desktop / manual install) | `.venv\Scripts\python.exe` or `venv\Scripts\python.exe` inside | that venv's python |
| **unknown** | no `main.py`, or no Python found | node installs disabled (download-only) |

- `GET /api/comfyui/inspect` validates a folder and returns flavor, python path, version
  (from `comfyui_version.py`), the custom-nodes list (name, git origin, commit, disabled
  flag) and per-category model files. Each model file carries a best-effort **`kind`**
  (`image`, `video`, `audio`, `lora`, `vae`, `text_encoder`, `clip_vision`, `controlnet`,
  `upscaler`, `embedding`, `unknown`), a short `arch` tag and - for LoRAs - `base` +
  `triggers`. All of it is read from the safetensors / GGUF **header** (a few KB), never by
  loading the model.
- When `comfyuiFolder` is empty, the response carries **`suggestions`** derived from the
  launcher path (`comfyuiLauncher`): `<launcher folder>\ComfyUI` first, then the launcher
  folder itself. The GUI shows a one-click "Use this folder".
- An optional `?path=` lets the GUI preview a candidate before it is saved.
- A file whose inferred kind doesn't fit its folder gets `suggestedCategory` (e.g. a Qwen3-VL
  text encoder found in `models/unet`). It is a warning only - **the app never moves files**.

## 2. Requirement manifests & model metadata

### 2.1 Per-module requirements.json

Every installed module folder may ship **`backend/app/GenModules/<module-id>/requirements.json`**
next to its `manifest.json`. Only modules that need engine content have one.

```json
{
  "nodes": [
    {
      "name": "ComfyUI-Impact-Pack",
      "repo": "https://github.com/ltdrdata/ComfyUI-Impact-Pack",
      "commit": "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4",
      "optional": false
    }
  ],
  "models": [
    {
      "name": "krea2_turbo_int8.safetensors",
      "target": "checkpoints",
      "url": "https://huggingface.co/<org>/<repo>/resolve/main/krea2_turbo_int8.safetensors",
      "sha256": "<64 hex chars>",
      "size": 4294967296,
      "optional": false
    }
  ]
}
```

Field rules:

- `nodes[].name` - display name; matching is by folder name (case-insensitive) **or** by
  normalized git origin (`repo`), whichever hits first. `commit` is the SHA to pin installs
  to (Phase B); it also lets the audit report "installed but outdated".
- `nodes[].package` - optional Python module name for package-style installs. When no
  custom_nodes folder / git origin matches, the audit looks for `<module>/__init__.py` or a
  `<module>-*.dist-info` in the detected site-packages (portable + venv layouts). ComfyUI
  0.30+ Manager is installed this way; legacy `custom_nodes/ComfyUI-Manager` still matches
  by name.
- `nodes[].pip` - the pip requirement used when installing that package (for example
  `comfyui-manager>=4.2,<5`). Required for package entries that have no custom_nodes folder
  to clone; the installer uses the detected ComfyUI Python.
- `models[].target` - the ComfyUI models category folder (`checkpoints`, `loras`, `vae`,
  `text_encoders`, ...). `url`/`sha256`/`size` are required for Phase C downloads; Phase A
  only needs `name` + `target` (+ `size` when known for the match check).
- `optional: true` items are reported but never block "Ready".

### 2.2 Core baseline

**`backend/app/engine_content/core_requirements.json`** uses the same `nodes` / `models`
schema and is audited once per install, independently of modules. It exists for content
that *every* module effectively needs - everything workflow-specific belongs in that
module's manifest instead.

Current baseline:

| Item | Tier | Why |
| --- | --- | --- |
| `ComfyUI-GGUF` (city96) | required | Loads GGUF diffusion models and text encoders - GGUF variants of the modules need it. |
| `ComfyUI-Manager` (ltdrdata) | recommended (`optional: true`) | Updates, snapshots and a clean reboot endpoint. ComfyUI 0.30+ installs it as the `comfyui_manager` Python package (not a custom_nodes folder); the audit checks site-packages too. Our installer never depends on it. |

`optional: true` items never block `ready`; the GUI shows them as "recommended" instead of
"missing". `why` is an optional human-readable line rendered under the item.

### 2.3 Model catalog & metadata (implemented)

`data/model_catalog.json` is the persistent, editable layer between header inference and
module recipes. The full schema, merge rules, trigger behavior and API are in
`docs/MODEL_CATALOG.md`; the short version:

- **Per-install inference** stays read-only: `inspect()` reads headers for `kind`, `arch`,
  `base`, `triggers`, sizes and `suggestedCategory`.
- **Local catalog** (`GET /api/model-catalog`; build/refresh via
  `POST /api/model-catalog/refresh`) merges that inventory by `target` + file name. Labels,
  bases, LoRA→model links, triggers, strength/clip ranges, other ranges and notes are editable
  and survive refreshes. Missing files stay as `present: false`; nothing is deleted.
- **LoRA links** are explicit `loras[].models` (base model ids) with `modelsAuto` to auto-link
  by `base`; models expose the inverse list. `strength` is `{default, min, max, step}`
  (0.8 / 0-1.5 / 0.05 by default); `clipStrength.enabled` covers dual-strength LoRAs;
  `otherRanges` carries optional partner-knob bounds (`steps`, `cfg`, ...).
- **Triggers** are appended to the job prompt only while the LoRA is on, in chain order and
  without duplicates. Typing the trigger yourself does not duplicate it; the textarea is left
  untouched.
- **Module recipes** still own workflow-specific defaults (steps/cfg/sampler/stack order).
  Catalog `otherRanges` are recommendations; the catalog is not a workflow.

API: `GET /api/model-catalog`, `POST /api/model-catalog/refresh`,
`PATCH /api/model-catalog/loras/{id}`, `PATCH /api/model-catalog/models/{id}`. Building reads
headers only; the only write is the catalog JSON. Phase C will add curated download sources and
hashes on top of this local layer.

## 3. Phase A - read-only audit (implemented)

- `GET /api/comfyui/inspect?path=` - see §1. Read-only.
- `GET /api/comfyui/requirements` - `{ inspect, core, modules[] }`; `core` and each module
  list every required node/model with `installed: true | false | null` (`null` = no folder
  configured, can't check), plus `missingNodes`, `missingModels`, `ready`. `core.checked` is
  false when nothing could be audited.
- Model matching: filename (case-insensitive) under `models/<target>/`; when the manifest
  has a `size`, the audit also reports `sizeMatches` (mismatch = warning chip, never
  auto-fixed). Hashing 6 GB files on every page view is not acceptable - **sha256 is
  verified at download time** (Phase C) and via an explicit "Verify" action later.
- GUI: Settings → **Engine content** tab - folder status card, **Core requirements** card,
  per-module node/model report, and **Models in this install** grouped by kind (header-derived
  `kind` / `arch`, LoRA `base` + `triggers`, misfiled-file warning). Empty state until
  modules with `requirements.json` exist.
- Limits so huge libraries can't slow a poll: 2000 files/category, 400 model entries returned
  and 500 custom nodes are scanned; the inspect payload notes truncation. Parsed headers are
  cached per process keyed by path + mtime + size (a full scan of a ~40-file library is
  ~0.3 s cold, ~0 ms warm).

## 4. Phase B - node installer (implemented)

See `docs/COMFYUI_INSTALLER.md` for the full API, task shape, command limits and test matrix.

- Trigger: per-node **Install** / **Update** / **Retry** buttons in the Engine content tab,
  after a confirm dialog that lists the repository, pinned commit and what will run.
- Mechanic (mirrors what ComfyUI-Manager / `comfy-cli` do):
  1. `git clone <repo>` into staging, `checkout <commit>`, then move it to
     `custom_nodes/<name>` (or `git fetch` + `checkout <commit>` for an existing git
     checkout) - **falls back to a zip download**
     (`codeload.github.com/<repo>/zip/<sha>`) when git is not on the machine. The zip fallback
     requires a GitHub repo and a pinned commit.
  2. If `requirements.txt` exists: `<python> -m pip install -r requirements.txt`.
     Else if `install.py` exists: `<python> install.py`.
  3. Every command streams into a task log (last 500 lines, 15-minute timeout); failures
     leave the node in place for retry.
- Package-style entries (`package` + `pip`, e.g. ComfyUI-Manager) install with the detected
  ComfyUI Python instead of cloning. An official `comfy/manager_requirements.txt` takes
  precedence over the manifest's pip spec.
- Existing non-git folders are never overwritten; updates refuse a dirty checkout. One install
  runs at a time (HTTP 409 for a second). No automatic updates.
- Node changes need a **ComfyUI restart**: the GUI offers "Restart ComfyUI" - uses the
  Manager reboot endpoint (`POST /api/v2/manager/reboot` on Manager 4.x, legacy
  `/api/manager/reboot` otherwise) when Manager is installed, else tells the user to close +
  relaunch (the launcher button is right there).
- Pinned commits only; version skew is reported ("installed: abc1234, wanted: def5678") and
  never auto-updated. After each task the GUI re-runs the audit.

## 5. Phase C - model downloads (planned)

- Model roots: by default the audit uses the ComfyUI `models/` folder. Additional roots are
  discovered from `extra_model_paths.yaml` (read-only parse) and from an optional
  `modelsRoot` setting - models that big often live on a dedicated drive.
- Downloader: queue, pause/cancel, resume via HTTP Range, `.part` + atomic rename,
  sha256 + size verification, HF token support (optional setting) for gated repos.
- Reuse detection before download: same filename + size (+hash when cheap) in **any** known
  root → "already installed - reusing", zero bytes fetched.
- Disk-space pre-check; downloads go to the root with the required free space.

## 6. Phase D - new-user bootstrap (planned, optional)

A "Get ComfyUI" action in Settings for fresh machines: downloads the official ComfyUI
Portable release (comfy.org / GitHub releases link in onboarding), extracts it to a folder
the user picks, sets `comfyuiLauncher` + `comfyuiFolder` automatically, then offers the
module content installs from Phase B/C. This gives the "one download and everything is set
up" experience without shipping gigabytes in the repo.

## 7. Safety rules (all phases)

- Probes/inspection stay **read-only**; they never execute anything from the ComfyUI folder.
- Everything that writes is an explicit click, shows what it will do, and streams a log.
- Downloads: https only, hash-verified, `.part` files, no mirror guessing.
- No deletions - trash rule applies to any future removal feature.
- Settings follow the normal contract: `comfyuiFolder` is a partial-diff pushed field with
  a reset button and a shipped default (`""`).

## 8. API summary

| Phase | Endpoint | Purpose |
| --- | --- | --- |
| A | `GET /api/comfyui/inspect?path=` | validate folder, flavor, python, nodes, model inventory (kind/arch/base/triggers), suggestions |
| A | `GET /api/comfyui/requirements` | core baseline + per-module node/model audit |
| B | `POST /api/comfyui/nodes/install` | install/update/repair one declared node or package (pinned, 202 + task) |
| B | `GET /api/comfyui/nodes/tasks` | recent install tasks |
| B | `GET /api/comfyui/nodes/tasks/{id}` | one task: status, stage, log, error/warning |
| B | `POST /api/comfyui/restart` | restart ComfyUI (Manager reboot, else instructions) |
| catalog | `GET /api/model-catalog` | saved model/LoRA metadata; read-only |
| catalog | `POST /api/model-catalog/refresh` | build/merge from installed file headers |
| catalog | `PATCH /api/model-catalog/loras/{id}` | edit model links, triggers, strength/clip/other ranges, notes |
| catalog | `PATCH /api/model-catalog/models/{id}` | edit model label/base/notes |
| C | `POST /api/comfyui/models/download` | queue a verified model download |
| C | `GET /api/comfyui/models/downloads` | queue status/progress |
| D | `POST /api/comfyui/bootstrap` | download + extract official portable |

Phase A/B and catalog endpoints are implemented; C-D are placeholders until built.
