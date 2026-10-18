"""Pipeline for this GenModule: compose -> submit -> collect.

Rules (docs/BACKEND_GUIDELINES.md §4):

- `app.jobs.service.create_job()` first; persist stages/progress with
  `update_job()` as they happen (the GUI and agents read them at any time).
- Outputs enter the library only through `app.library.service.add_file/add_bytes`.
- Engine access goes through `app.connectors` (never httpx directly here).
- Probes are read-only; nothing in this module may trigger a model load.

Stage shape (keep stable - the Jobs page and MCP render it directly):

    [{"id": "compose", "label": "Compose graph", "status": "running",
      "detail": "", "startedAt": 0, "finishedAt": 0}]
"""

from __future__ import annotations

# from app.connectors import service as connectors
# from app.jobs import service as jobs
# from app.library import service as library
