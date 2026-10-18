"""Pydantic models for the settings API.

PUT /api/settings accepts a *partial* document: every field is optional and is
deep-merged onto the current settings, then validated as a whole. Unknown keys
are ignored so an older/newer GUI can't break the backend.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ConnectionEntry(BaseModel):
    url: str = ""


class ConnectionProfile(BaseModel):
    id: str
    name: str = ""
    kind: Literal["comfyui", "ollama"]
    url: str = ""
    auth: str = ""


class DefaultsBlock(BaseModel):
    imageModel: str = ""
    upscaler: str = ""
    textProvider: str = ""
    enhanceModel: str = ""
    describeModel: str = ""


class FoldersBlock(BaseModel):
    library: str = ""
    exports: str = ""
    imports: str = ""
    agentInbox: str = ""


class SettingsPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    connections: dict[str, ConnectionEntry] | None = None
    profiles: list[ConnectionProfile] | None = None
    activeProfiles: dict[str, str] | None = None
    defaults: DefaultsBlock | None = None
    folders: FoldersBlock | None = None
    prompts: dict[str, str] | None = None
    autoFreeVram: bool | None = None
    comfyuiLauncher: str | None = None
    agentEnabled: bool | None = None
    agentToken: str | None = None
