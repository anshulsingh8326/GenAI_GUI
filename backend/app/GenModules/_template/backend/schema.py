"""Request models for the Template GenModule.

The JSON boundary is camelCase so the GUI, REST clients and future MCP tools
speak one shape. Range enforcement lives in ``service.py``; Pydantic only
validates the transport shape.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TemplateJobRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt: str = ""
    accent: str | None = None
    width: int | None = None
    height: int | None = None
    batch: int | None = None
    seed: int | None = None
    lockSeed: bool = False
    tab: str = "template"
