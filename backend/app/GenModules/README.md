"""GenModules - one folder per generation module (added from Group 3 on).

Naming note: this folder is deliberately called GenModules (not "modules") so
nobody confuses it with general code modularity. Each generation feature -
text-to-image, image-to-image, edit, face swap, video, audio - gets its own
self-contained folder here, mirroring `frontend/src/features/<module-id>/`.

## What a module folder owns

```
backend/app/GenModules/<module-id>/
  __init__.py
  api.py        # its REST router (thin - mounted in app/api/__init__.py)
  service.py    # its pipeline stages: compose -> submit -> collect
  schema.py     # request/response models specific to the module
  requirements.json  # optional: custom nodes + model files the module needs
```

## Rules

- A GenModule may import from `app.common`, `app.connectors` (ComfyUI/Ollama)
  and the shared services (library, jobs, settings) - never from another
  GenModule.
- Shared behaviour gets promoted into `app/common` / the shared services
  instead of being copied between modules.
- The GUI counterpart lives in `frontend/src/features/<module-id>/`, and its
  ComfyUI templates/packs live under `packs/` (see docs/PACKS.md).
- If the module needs engine content (custom nodes, model files), ship a
  `requirements.json` next to `manifest.json` - Settings > Engine content audits
  it against the user's ComfyUI install (schema: docs/COMFYUI_CONTENT.md §2).
- Nothing in Group 1 creates a module here yet; this README marks the spot and
  the naming decision.
"""
