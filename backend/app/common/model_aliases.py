"""Case/separator-insensitive model filename aliases.

A module declares aliases next to a tracked filename. The catalog keeps the
real downloaded filename, so matching is intentionally path- and
extension-agnostic:

- `snofs_krea2` matches `snofsSexNudesAndOther_krea2TurboV14.safetensors`
- `q5_k_m` matches `krea2_turbo-Q5_K_M.gguf`
- `qwen3vl` matches `qwen3vl_4b_fp8_scaled.safetensors`

Aliases never rename or move a file. The caller uses `best_alias_match` to
recover the real catalog entry and binds that filename into the graph.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Iterable

_EXTENSIONS = {
    ".safetensors",
    ".gguf",
    ".ckpt",
    ".pt",
    ".pth",
    ".bin",
    ".onnx",
    ".sft",
}


def normalize_token(value: Any) -> str:
    """Return the filename stem as lowercase alphanumeric characters only."""
    if value is None:
        return ""
    text = str(value).strip().replace("\\", "/")
    if not text:
        return ""
    text = PurePosixPath(text).name
    lowered = text.casefold()
    for extension in _EXTENSIONS:
        if lowered.endswith(extension):
            lowered = lowered[: -len(extension)]
            break
    return re.sub(r"[^a-z0-9]+", "", lowered)


def alias_tokens(values: Iterable[Any] | None) -> list[str]:
    """Normalize and de-duplicate an alias list while preserving order."""
    tokens: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        token = normalize_token(value)
        if not token or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _loose_parts(alias: Any) -> list[str]:
    """Separator-delimited alias parts, for names with words in between.

    `snofs_krea2` is not a contiguous substring of
    `snofsSexNudesAndOther_krea2TurboV14_int8`, but both meaningful parts are
    present. Ignore one-character fragments so a trailing `_m` cannot match
    every filename.
    """
    parts = [
        normalize_token(part)
        for part in re.split(r"[^A-Za-z0-9]+", str(alias or "").strip())
    ]
    parts = [part for part in parts if len(part) >= 2]
    return parts if len(parts) >= 2 else []


def alias_score(name: Any, aliases: Iterable[Any] | None) -> int:
    """How specifically an alias matches a filename (0 means no match).

    Exact stem matches outrank containment. Longer aliases outrank shorter
    ones, so `snofssexnudesandother` wins over a generic `snofs` alias. A
    multi-part alias may match when every part appears somewhere in the name.
    """
    name_token = normalize_token(name)
    if not name_token:
        return 0
    best = 0
    for aliases_raw in aliases or []:
        for alias in alias_tokens([aliases_raw]):
            if name_token == alias:
                best = max(best, 1000 + len(alias))
            elif alias in name_token:
                best = max(best, 100 + len(alias))
            else:
                parts = _loose_parts(aliases_raw)
                if parts and all(part in name_token for part in parts):
                    best = max(best, 90 + sum(len(part) for part in parts))
    return best


def name_has_alias(name: Any, aliases: Iterable[Any] | None) -> bool:
    """True when any normalized alias is contained in the filename token."""
    return alias_score(name, aliases) > 0


def best_alias_match(
    entries: Iterable[dict],
    aliases: Iterable[Any] | None,
    *,
    name_key: str = "name",
    target: str | None = None,
    exclude_aliases: Iterable[Any] | None = None,
) -> dict | None:
    """Pick the best catalog entry for an alias list, optionally by folder.

    ``exclude_aliases`` lets a broad fallback (for example a generic
    ``krea2`` family alias) refuse a file that belongs to a more specific
    pack variant (for example SNOFS). Exclusions are checked against the real
    catalog filename, never by renaming or moving the file.
    """
    wanted_target = (target or "").strip().casefold()
    best: dict | None = None
    best_score = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if wanted_target and str(entry.get("target") or "").strip().casefold() != wanted_target:
            continue
        # Missing catalog entries are kept for history, not for graph binding.
        if entry.get("present") is False:
            continue
        if exclude_aliases and name_has_alias(entry.get(name_key), exclude_aliases):
            continue
        score = alias_score(entry.get(name_key), aliases)
        if score <= 0:
            continue
        # A stale catalog entry is kept with `present: false`; an installed
        # alias must win over it, otherwise a renamed/re-downloaded file looks
        # missing forever.
        if entry.get("present") is True:
            score += 2000
        if score > best_score:
            best = entry
            best_score = score
    return best
