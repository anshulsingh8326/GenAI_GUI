# ComfyUI content management (custom nodes + models)

Status: **Phase A + A.5 implemented** (folder detection, read-only requirements audit, core
baseline, model inventory with header-derived kinds). Phases B–D are planned, not built.
This doc is the contract for all of them.

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

### 2.3 Model catalog & metadata

Three layers, so metadata never drifts:

1. **Per-install inference (implemented, read-only).** `inspect()` reads header bytes of
   `.safetensors` (8-byte length + JSON header) and `.gguf` (scalar metadata keys) to fill
   `kind`, `arch`, `base` and `triggers`. Unknown files stay `unknown` - nothing is guessed
   from the extension. `suggestedCategory` flags misfiled files; no file is moved.
2. **Shipped catalog (Phase C).** Curated, intrinsic facts + download sources. One entry per
   model or LoRA; entries are global because several modules may use the same file.
3. **Module recipes (with the packs).** Usage defaults per workflow - steps, cfg, sampler,
   LoRA stack, resolution. The same model can be used differently by two modules, so these
   never live in the catalog.

Catalog entry (illustrative):

```json
{
  "id": "krea2-turbo",
  "kind": "image",
  "family": "Krea 2",
  "architecture": "qwen_image",
  "files": [
    {
      "target": "diffusion_models",
      "name": "krea2_turbo_q5_k_m.gguf",
      "url": "https://huggingface.co/<org>/<repo>/resolve/main/krea2_turbo_q5_k_m.gguf",
      "sha256": "<64 hex chars>",
      "size": 8870000000
    }
  ],
  "companions": {
    "vae": ["qwen_image_vae.safetensors"],
    "text_encoder": ["qwen3vl_4b_fp8_scaled.safetensors"]
  },
  "defaults": { "steps": 8, "cfg": 1.0, "sampler": "euler", "scheduler": "simple" },
  "source": "https://...",
  "license": "unknown"
}
```

LoRA entry - `base` and `triggers` are intrinsic, `defaultWeight` is a suggestion a recipe
may override:

```json
{
  "id": "krea2-g4ngb4ng",
  "kind": "lora",
  "base": "krea2",
  "file": { "target": "loras", "name": "KREA2_G4NGB4NG_V1.safetensors" },
  "triggers": ["G4NGB4NG"],
  "defaultWeight": 0.8,
  "sha256": "<64 hex chars>"
}
```

`kind` values are shared with the inspect payload (`image`, `video`, `audio`, `lora`, `vae`,
`text_encoder`, `clip_vision`, `controlnet`, `upscaler`, `embedding`). Module manifests
reference catalog `id`s; the audit resolves an id to `target`/`name`/`size` and still matches
by filename, so a user's existing file is reused without downloading.

Not built yet: the catalog file itself ships with the first real module (it needs verified
hashes), and user overrides (sidecar JSON next to a file) arrive with an explicit action -
Phase A writes nothing.

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

## 4. Phase B - node installer (planned)

- Trigger: per-node "Install" button in the Engine content tab (and a "Install all missing"
  per module), after a confirm dialog that lists exactly what will run.
- Mechanic (mirrors what ComfyUI-Manager / `comfy-cli` do):
  1. `git clone <repo> <custom_nodes>/<name>` (or `git fetch` + `checkout <commit>` when the
     folder already exists) - **falls back to a zip download** (`codeload.github.com/<repo>/zip/<sha>`)
     when git is not on the machine.
  2. If `requirements.txt` exists: `<python> -m pip install -r requirements.txt`.
     Else if `install.py` exists: `<python> install.py`.
  3. Log every line to the GUI (streaming); failures leave the clone in place for retry.
- Node changes need a **ComfyUI restart**: the GUI offers "Restart ComfyUI" - uses the
  Manager reboot endpoint (`POST /api/v2/manager/reboot` on Manager 4.x, legacy
  `/api/manager/reboot` otherwise) when Manager is installed, else tells the user to close +
  relaunch (the launcher button is right there).
- Pinned commits only; version skew is reported ("installed: abc1234, wanted: def5678") and
  never auto-updated.

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
| B | `POST /api/comfyui/nodes/install` | install/repair one required node (pinned) |
| B | `POST /api/comfyui/restart` | restart ComfyUI (Manager reboot, else instructions) |
| C | `POST /api/comfyui/models/download` | queue a verified model download |
| C | `GET /api/comfyui/models/downloads` | queue status/progress |
| D | `POST /api/comfyui/bootstrap` | download + extract official portable |

Phase A endpoints are implemented; B–D are placeholders until built.
