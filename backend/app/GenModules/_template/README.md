# GenModule template

Copy this folder to `backend/app/GenModules/<module-id>/` (e.g. `text-to-image`) and follow
the checklist in `docs/BACKEND_GUIDELINES.md` §0. Folders starting with `_` are ignored by
the capability registry (`app/common/capabilities.py`), so this template is never reported
as an installed capability.

What to change after copying:

- `manifest.json` — id / name / group / description (+ recipe ids once packs land).
- `schema.py` — request/response models for this module.
- `service.py` — the pipeline stages: compose → submit → collect.
- `api.py` — the thin router; mount it in `backend/app/api/__init__.py`.
- GUI counterpart: `frontend/src/features/<module-id>/` (see `docs/GUI_GUIDELINES.md` §0).

Rules (full list in `docs/BACKEND_GUIDELINES.md`):

- Import from `app.common`, `app.connectors` and the shared services only — never from
  another GenModule.
- Jobs are created via `app.jobs.service` before work starts; outputs enter the library via
  `app.library.service`.
- Probes stay read-only; tests must never cause a model load.
