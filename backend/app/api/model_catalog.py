"""Model + LoRA catalog routes.

`GET` only reads data/model_catalog.json. `POST /refresh` and `PATCH` are
explicit user actions; they never touch model files, they only write metadata.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.engine_content import catalog

router = APIRouter(tags=["model-catalog"])


class RangeBody(BaseModel):
    default: float
    min: float
    max: float
    step: float
    enabled: bool | None = None
    label: str | None = None


class LoraPatch(BaseModel):
    label: str | None = None
    base: str | None = None
    models: list[str] | None = None
    modelsAuto: bool | None = None
    triggers: list[str] | None = None
    strength: RangeBody | None = None
    clipStrength: RangeBody | None = None
    otherRanges: dict[str, RangeBody] | None = None
    notes: str | None = None


class ModelPatch(BaseModel):
    label: str | None = None
    base: str | None = None
    notes: str | None = None


@router.get("/model-catalog")
def get_model_catalog() -> dict:
    """The saved catalog (empty until the user builds it from ComfyUI)."""
    try:
        return catalog.catalog_response()
    except catalog.CatalogError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/model-catalog/refresh")
def refresh_model_catalog() -> dict:
    """Scan the configured ComfyUI install and merge headers into the catalog."""
    try:
        return catalog.build_catalog()
    except catalog.CatalogError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/model-catalog/loras/{lora_id}")
def update_catalog_lora(lora_id: str, body: LoraPatch) -> dict:
    """Edit one LoRA: label, base, linked models, triggers, ranges, notes."""
    try:
        return catalog.update_lora(lora_id, body.model_dump(exclude_unset=True))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0] if exc.args else exc)) from exc
    except catalog.CatalogError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/model-catalog/models/{model_id}")
def update_catalog_model(model_id: str, body: ModelPatch) -> dict:
    """Edit a base/companion model's label, base or notes."""
    try:
        return catalog.update_model(model_id, body.model_dump(exclude_unset=True))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0] if exc.args else exc)) from exc
    except catalog.CatalogError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
