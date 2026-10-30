"""Shared module setup payload for the first-open requirements popup.

The payload is deliberately presentation-ready: GenModules only supply their
own `requirements.json` and pack metadata. Nothing here downloads, installs,
moves or deletes a file. A module can call `build_setup_payload` from its API
and reuse the shared `ModuleSetupModal.vue` on the frontend.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from app.common.model_aliases import best_alias_match, name_has_alias

_ROLE_TARGETS = {
    "base": "unet",
    "text_encoder": "text_encoders",
    "vae": "vae",
    "lora": "loras",
    "upscaler": "upscale_models",
}


def load_requirements(path: Path) -> dict:
    """Read a module requirements file; an invalid file yields empty data."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"schemaVersion": 0, "module": {}, "groups": [], "nodes": [], "models": []}
    return raw if isinstance(raw, dict) else {"schemaVersion": 0, "module": {}, "groups": [], "nodes": [], "models": []}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _number(value: Any) -> int | None:
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    return None


def _catalog_entries(catalog: dict | None) -> list[dict]:
    entries: list[dict] = []
    for key in ("models", "loras"):
        values = (catalog or {}).get(key)
        if not isinstance(values, dict):
            continue
        for value in values.values():
            if isinstance(value, dict):
                entries.append(value)
    return entries


def _match_entry(item: dict, entries: Iterable[dict]) -> dict | None:
    target = str(item.get("target") or "").strip()
    name = str(item.get("name") or "").strip()
    wanted_target = target.casefold()
    wanted_name = name.replace("\\", "/").casefold()
    exclude = _string_list(item.get("excludeAliases"))
    exact: list[dict] = []
    for entry in entries:
        entry_name = str(entry.get("name") or "").replace("\\", "/").casefold()
        entry_target = str(entry.get("target") or "").casefold()
        if wanted_target and entry_target != wanted_target:
            continue
        if exclude and name_has_alias(entry.get("name"), exclude):
            continue
        if entry_name == wanted_name and entry.get("present") is not False:
            exact.append(entry)
    if exact:
        return exact[0]
    return best_alias_match(
        entries,
        [*_string_list(item.get("aliases")), name],
        target=target,
        exclude_aliases=exclude,
    )


def _present(entry: dict | None) -> bool | None:
    if entry is None:
        return None
    return bool(entry.get("present", True))


def _requirement_view(
    raw: dict,
    *,
    pack_id: str,
    entries: list[dict],
    catalog_available: bool,
    models_root: Path | None,
    group_id: str | None,
) -> dict:
    role = str(raw.get("role") or "model").strip()
    target = str(raw.get("target") or _ROLE_TARGETS.get(role, "")).strip()
    name = str(raw.get("name") or raw.get("file") or "").strip()
    label = str(raw.get("label") or name or raw.get("id") or "required file").strip()
    entry = _match_entry({**raw, "target": target, "name": name}, entries)
    if not catalog_available:
        present = None
    elif entry is None:
        present = False
    else:
        present = _present(entry)
    folder = f"ComfyUI/models/{target}" if target else "ComfyUI/models"
    destination = str((models_root / target) if models_root and target else (models_root or folder))
    return {
        "id": str(raw.get("id") or name or label),
        "pack": pack_id,
        "group": group_id,
        "role": role,
        "label": label,
        "name": name,
        "aliases": _string_list(raw.get("aliases")),
        "target": target,
        "folder": folder,
        "destination": destination,
        "required": bool(raw.get("required", not raw.get("optional", False))),
        "tested": bool(raw.get("tested")),
        "nsfw": bool(raw.get("nsfw")),
        "size": _number(raw.get("size")),
        "url": str(raw.get("url") or ""),
        "pageUrl": str(raw.get("pageUrl") or ""),
        "sha256": str(raw.get("sha256") or ""),
        "why": str(raw.get("why") or ""),
        "present": present,
        "matchedFile": str(entry.get("name") or "") if entry else "",
    }


def _group_view(
    raw: dict,
    *,
    pack_id: str,
    items: list[dict],
    entries: list[dict],
    catalog_available: bool,
) -> dict:
    group_id = str(raw.get("id") or "").strip()
    targets = {str(item.get("target") or "").casefold() for item in items if item.get("target")}
    candidates = [
        entry
        for entry in entries
        if not targets or str(entry.get("target") or "").casefold() in targets
    ]
    group_match = best_alias_match(
        candidates,
        _string_list(raw.get("aliases")),
        exclude_aliases=_string_list(raw.get("excludeAliases")),
    )
    present_count = sum(1 for item in items if item.get("present") is True)
    if not catalog_available:
        satisfied: bool | None = None
    else:
        satisfied = present_count > 0 or group_match is not None
    matched_file = str(group_match.get("name") or "") if group_match else ""
    if not matched_file:
        matched_file = next((item.get("matchedFile") for item in items if item.get("matchedFile")), "")
    return {
        "id": group_id,
        "pack": pack_id,
        "label": str(raw.get("label") or group_id or "Base model"),
        "mode": str(raw.get("mode") or "oneOf"),
        "required": bool(raw.get("required", True)),
        "why": str(raw.get("why") or ""),
        "nsfw": bool(raw.get("nsfw")),
        "aliases": _string_list(raw.get("aliases")),
        "excludeAliases": _string_list(raw.get("excludeAliases")),
        "satisfied": satisfied,
        "presentCount": present_count,
        "matchedFile": matched_file,
        "items": items,
    }


def _missing_item(item: dict) -> dict:
    return {
        "kind": "model",
        "id": item["id"],
        "pack": item["pack"],
        "label": item["label"],
        "name": item["name"],
        "role": item["role"],
        "target": item["target"],
        "folder": item["folder"],
        "destination": item["destination"],
        "url": item["url"],
        "pageUrl": item["pageUrl"],
        "size": item["size"],
        "nsfw": item["nsfw"],
    }


def _missing_group(group: dict) -> dict:
    return {
        "kind": "group",
        "id": group["id"],
        "pack": group["pack"],
        "label": group["label"],
        "mode": group["mode"],
        "target": group["items"][0]["target"] if group["items"] else "",
        "folder": group["items"][0]["folder"] if group["items"] else "",
        "url": next((item["url"] for item in group["items"] if item["url"]), ""),
        "nsfw": group["nsfw"] or any(item["nsfw"] for item in group["items"]),
        "items": group["items"],
    }


def build_setup_payload(
    *,
    requirements: dict,
    packs: list[dict],
    catalog: dict | None,
    module_id: str = "",
    module_label: str = "",
    module_description: str = "",
    module_nsfw: bool = False,
) -> dict:
    """Build the standardized first-open payload from requirements + packs."""
    raw_module = requirements.get("module") if isinstance(requirements.get("module"), dict) else {}
    pack_defs = [
        {
            "id": str(pack.get("id") or ""),
            "label": str(pack.get("label") or pack.get("id") or "Pack"),
            "description": str(pack.get("description") or ""),
            "nsfw": bool(pack.get("nsfw")),
            "order": int(pack.get("order") or 0),
        }
        for pack in packs
        if pack.get("id")
    ]
    pack_ids = {pack["id"] for pack in pack_defs}
    default_pack = pack_defs[0]["id"] if len(pack_defs) == 1 else ""

    entries = _catalog_entries(catalog)
    available = bool(catalog and catalog.get("available"))
    source = (catalog or {}).get("source") if isinstance((catalog or {}).get("source"), dict) else {}
    comfy_folder = str(source.get("comfyuiFolder") or "").strip()
    models_root = Path(comfy_folder) / "models" if comfy_folder else None

    raw_groups = requirements.get("groups") if isinstance(requirements.get("groups"), list) else []
    raw_models = requirements.get("models") if isinstance(requirements.get("models"), list) else []
    group_defs: dict[str, dict] = {}
    for raw in raw_groups:
        if not isinstance(raw, dict) or not raw.get("id"):
            continue
        group_id = str(raw["id"])
        group_pack = str(raw.get("pack") or default_pack)
        group_defs[group_id] = {**raw, "id": group_id, "_pack": group_pack if group_pack in pack_ids else default_pack}

    pack_items: dict[str, list[dict]] = {pack["id"]: [] for pack in pack_defs}
    pack_groups: dict[str, list[dict]] = {pack["id"]: [] for pack in pack_defs}
    group_items: dict[str, list[dict]] = {}
    for raw in raw_models:
        if not isinstance(raw, dict):
            continue
        group_id = str(raw.get("group") or "").strip()
        group_def = group_defs.get(group_id)
        pack_id = str(raw.get("pack") or (group_def or {}).get("_pack") or default_pack)
        if pack_id not in pack_items:
            pack_id = default_pack or (pack_defs[0]["id"] if pack_defs else "")
        view = _requirement_view(
            raw,
            pack_id=pack_id,
            entries=entries,
            catalog_available=available,
            models_root=models_root,
            group_id=group_id if group_def else None,
        )
        if group_def:
            group_items.setdefault(group_id, []).append(view)
        elif pack_id in pack_items:
            pack_items[pack_id].append(view)

    for group_id, group_def in group_defs.items():
        pack_id = str(group_def.get("_pack") or default_pack)
        if pack_id not in pack_groups:
            pack_id = default_pack or (pack_defs[0]["id"] if pack_defs else "")
        items = group_items.get(group_id, [])
        if not items:
            continue
        view = _group_view(
            group_def,
            pack_id=pack_id,
            items=items,
            entries=entries,
            catalog_available=available,
        )
        pack_groups[pack_id].append(view)

    packs_out: list[dict] = []
    module_missing: list[dict] = []
    for pack in pack_defs:
        items = sorted(pack_items[pack["id"]], key=lambda item: item["label"].casefold())
        groups = pack_groups[pack["id"]]
        missing: list[dict] = []
        for group in groups:
            if group["required"] and group["satisfied"] is False:
                missing.append(_missing_group(group))
        for item in items:
            if item["required"] and item["present"] is False:
                missing.append(_missing_item(item))
        pack_view = {
            **pack,
            "groups": groups,
            "items": items,
            "missingRequired": missing,
            "ready": None if not available else not missing,
        }
        if available:
            module_missing.extend(missing)
        packs_out.append(pack_view)

    module_ready: bool | None = None
    if available and packs_out:
        module_ready = not module_missing
    return {
        "ok": True,
        "schemaVersion": int(requirements.get("schemaVersion") or 1),
        "module": {
            "id": str(raw_module.get("id") or module_id),
            "label": str(raw_module.get("label") or module_label),
            "description": str(raw_module.get("description") or module_description),
            "nsfw": bool(raw_module.get("nsfw", module_nsfw)),
        },
        "packs": packs_out,
        "missingRequired": module_missing,
        "ready": module_ready,
        "catalog": {
            "available": available,
            "updatedAt": (catalog or {}).get("updatedAt"),
            "createdAt": (catalog or {}).get("createdAt"),
            "error": (catalog or {}).get("error"),
            "modelsRoot": str(models_root) if models_root else "",
        },
        "policy": {
            "autoDownload": False,
            "autoInstall": False,
            "note": "This popup only reports files and opens source links. Download and place them manually, then refresh the model catalog.",
        },
    }
