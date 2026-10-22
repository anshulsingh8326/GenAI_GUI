"""REST layer - thin routers that wire HTTP to the services.

Keep routers boring: validation + service call + response. All real logic lives
in the service folders (common, settings, connectors, ... GenModules).
"""

from fastapi import APIRouter

from . import assets, connectors, engine_content, folders, jobs, model_catalog, settings, status, system

api = APIRouter(prefix="/api")
api.include_router(system.router)
api.include_router(settings.router)
api.include_router(folders.router)
api.include_router(status.router)
api.include_router(connectors.router)
api.include_router(engine_content.router)
api.include_router(model_catalog.router)
api.include_router(assets.router)
api.include_router(jobs.router)
