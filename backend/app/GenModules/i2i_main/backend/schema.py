"""Request models for i2i_main.

The JSON boundary is camelCase so the GUI, REST clients and future MCP tools
speak one shape. Range enforcement lives in ``service.py``; Pydantic only
validates the transport shape.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class I2ISourceImage(BaseModel):
    """One reference image from the GUI (data URL + display name)."""

    model_config = ConfigDict(extra="ignore")

    image: str = ""
    name: str = ""


class I2IJobRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    modelId: str | None = None
    recipeId: str | None = None
    prompt: str = ""
    negativePrompt: str = ""
    # 1..3 reference images. `sourceImage`/`sourceName` remain as a single-image
    # fallback for older clients and API callers.
    sourceImages: list[I2ISourceImage] = Field(default_factory=list)
    sourceImage: str = ""
    sourceName: str = ""
    resolution: int | None = None
    batch: int | None = None
    seed: int | None = None
    lockSeed: bool = False
    cfg: float | None = None
    denoise: float | None = None
    steps: int | None = None
    sampler: str | None = None
    cacheDevice: str | None = None
    cacheDtype: str | None = None
    tab: str = "image-to-image"
