"""Backend package for the T2I_main GenModule.

Import the router from `app.GenModules.T2I_main.backend.api` and mount it under
`/api/t2i` (see `app/api/__init__.py`).
"""

from .api import router

__all__ = ["router"]
