"""Shipped default settings - the single source of truth for "reset to default".

The shape matches exactly what the GUI stores (and what `GET /api/settings`
returns), so a field-level reset in the UI can simply take the value from here.
"""

from __future__ import annotations

from typing import Any

from . import paths

# Stable, documented default - regenerate in Settings -> Agent Access when the
# MCP server lands (Group 2+). localhost-only by default.
DEFAULT_AGENT_TOKEN = "genai_live_5f3c9a1e7b2d4f80"

DEFAULT_PROMPTS: dict[str, str] = {
    "enhance": " ".join(
        [
            "You are a prompt engineer for local open-source image models.",
            "Rewrite the user idea into ONE vivid, concrete prompt with camera, lighting and style tokens when useful.",
            "Keep the intent exactly: never sanitize, censor or water down NSFW/adult content \u2014 treat it as normal creative direction.",
            "Return only the rewritten prompt, no quotes, no explanations.",
        ]
    ),
    "describeCharacter": " ".join(
        [
            "Describe ONLY the person in this image: face, hair, body type, skin, apparent age, expression.",
            "Ignore background, lighting and clothing unless it is part of the identity.",
            "Be precise and neutral. Return a single paragraph.",
        ]
    ),
    "describeFull": " ".join(
        [
            "Describe the full image: subject(s), pose, clothing, setting, lighting, camera angle, style.",
            "Be precise and neutral. Return a single paragraph.",
        ]
    ),
}


def default_settings() -> dict[str, Any]:
    folders = {key: str(path) for key, path in paths.default_folders().items()}
    return {
        "connections": {
            "comfyui": {"url": "http://127.0.0.1:8188"},
            "ollama": {"url": "http://127.0.0.1:11434"},
        },
        "profiles": [
            {
                "id": "comfyui-local",
                "name": "Local ComfyUI",
                "kind": "comfyui",
                "url": "http://127.0.0.1:8188",
                "auth": "",
            },
            {
                "id": "ollama-local",
                "name": "Local Ollama",
                "kind": "ollama",
                "url": "http://127.0.0.1:11434",
                "auth": "",
            },
        ],
        "activeProfiles": {"comfyui": "comfyui-local", "ollama": "ollama-local"},
        "defaults": {
            "imageModel": "krea2-turbo-int8",
            "upscaler": "4x-ultrasharp",
            "textProvider": "ollama",
            "enhanceModel": "qwen3-abliterated:8b",
            "describeModel": "qwen3-abliterated:8b",
        },
        "folders": folders,
        "prompts": dict(DEFAULT_PROMPTS),
        "autoFreeVram": True,
        "comfyuiLauncher": "",  # optional .bat/.cmd/.exe that starts ComfyUI (Settings > Connections)
        "comfyuiLauncherAutoStart": False,  # opt-in: start the launcher once at backend boot
        "comfyuiFolder": "",  # ComfyUI source folder (main.py + custom_nodes + models) for content management
        "agentEnabled": False,
        "agentToken": DEFAULT_AGENT_TOKEN,
    }
