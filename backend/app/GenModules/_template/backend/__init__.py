"""Backend package for the Template GenModule.

Import the router from ``app.GenModules._template.backend.api`` and mount it
under ``/api/template`` (see ``app/api/__init__.py``). Folders whose name
starts with ``_`` are ignored by the capability registry, so this starter is
never reported as an installed capability.
"""

from .api import router

__all__ = ["router"]
