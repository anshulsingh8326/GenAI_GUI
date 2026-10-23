"""GenModules - one folder per generation module (added from Group 3 on).

Naming note: this folder is deliberately called GenModules (not "modules") so
nobody confuses it with general code modularity. Each generation feature -
text-to-image, image-to-image, edit, face swap, video, audio - gets its own
self-contained folder here, mirroring `frontend/src/features/<module-id>/`.

## What a module folder owns

```
backend/app/GenModules/<module-id>/
  manifest.json          # identity, nav id, API prefix, frontend entry
  requirements.json      # optional: custom nodes + model files
  backend/
    __init__.py
    api.py               # REST router (thin - mounted in app/api/__init__.py)
    service.py           # pipeline stages: compose -> submit -> collect
    schema.py            # request/response models specific to the module
    catalog.py           # optional: pack + user catalog merge
    workflows.py         # optional: ComfyUI API graph composition
    pack/                # optional: tracked model/LoRA/recipe JSON
      models.json
      loras.json
      upscalers.json
      text_models.json
      options.json
      workflows/*.api.json
  frontend/
    README.md            # GUI behaviour contract
    types.ts             # wire types for the module
    api.ts               # module API client
    T2IPage.vue          # route-ready shell (visual pass may follow)
```

T2I_main is the reference implementation of this nested layout. The `backend/`
and `frontend/` subfolders keep the module's Python package and its GUI contract
together; `manifest.json` points at `backend.api:router` and advertises the
module-owned frontend entry.

## Rules

- A GenModule may import from `app.common`, `app.connectors` (ComfyUI/Ollama)
  and the shared services (library, jobs, settings) - never from another
  GenModule.
- Shared behaviour gets promoted into `app/common` / the shared services
  instead of being copied between modules.
- The tracked pack is authoritative for that module's ranges and defaults. The
  user-owned `data/model_catalog.json` supplies installed-file presence and
  user metadata, never module ranges.
- If the module needs engine content (custom nodes, model files), ship a
  `requirements.json` next to `manifest.json` - Settings > Engine content audits
  it against the user's ComfyUI install (schema: docs/COMFYUI_CONTENT.md §2).
- The runtime GUI lives in `frontend/src/features/<module-id>/`. The
  module-owned `frontend/` folder is the canonical contract/source; copy it
  into the app feature folder when wiring the route, then keep both in sync
  while the module is being developed.
- API/agent callers use the same service validation as the GUI. A module must
  not expose a client-only range check that the REST/MCP path can bypass.
"""
