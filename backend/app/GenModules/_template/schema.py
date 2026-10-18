"""Request/response models for this GenModule.

Keep the JSON boundary camelCase (the GUI and MCP consume the same shapes -
docs/BACKEND_GUIDELINES.md §2).

from pydantic import BaseModel


class TemplateJobRequest(BaseModel):
    prompt: str = ""
    params: dict = {}
"""

from __future__ import annotations
