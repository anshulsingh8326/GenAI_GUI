"""Request models for T2I_main.

The JSON boundary is camelCase (docs/BACKEND_GUIDELINES.md §2) so the GUI,
REST clients and the future MCP tool all speak the same shape. The module's
own validation (service.py) does the range enforcement; Pydantic only checks
the transport shape, which keeps the error messages useful.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LoraSelection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    strength: float | None = None
    on: bool = True
    order: int | None = None


class RefineOptions(BaseModel):
    model_config = ConfigDict(extra="ignore")

    steps: int | None = None
    cfg: float | None = None
    denoise: float | None = None


class UpscalerOptions(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    enabled: bool | None = None
    value: int | None = None


class AdvancedOptions(BaseModel):
    model_config = ConfigDict(extra="ignore")

    steps: int | None = None
    cfg: float | None = None
    sampler: str | None = None
    scheduler: str | None = None
    denoise: float | None = None
    refine: RefineOptions | None = None
    upscaler: UpscalerOptions | None = None


class EnhanceOptions(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # None means "use the pack default"; an explicit false disables it.
    enabled: bool | None = None
    provider: Literal["ollama", "comfyui"] | None = None
    model: str | None = None
    systemPrompt: str | None = None
    fallbackToOriginal: bool = False
    # Free the Ollama text model after the rewrite and before ComfyUI starts
    # the image job. Default-on: the GUI exposes a visible opt-out.
    unloadAfter: bool = True


class T2IJobRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt: str = ""
    negativePrompt: str = ""
    modelId: str = ""
    recipeId: str | None = None
    width: int | None = None
    height: int | None = None
    ratio: str | None = None
    size: int | None = None
    batch: int | None = None
    seed: int | None = None
    lockSeed: bool = False
    loras: list[LoraSelection] = Field(default_factory=list)
    autoTriggers: bool = True
    enhance: EnhanceOptions | None = None
    enhancedPrompt: str | None = None
    advanced: AdvancedOptions | None = None
    tab: str = "text-to-image"


class T2IEnhanceRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt: str = ""
    provider: Literal["ollama", "comfyui"] | None = None
    model: str | None = None
    systemPrompt: str | None = None
    maxLength: int | None = None
    temperature: float | None = None
    # Release the text model after the rewrite by default; the GUI exposes a
    # visible opt-out.
    unloadAfter: bool = True
