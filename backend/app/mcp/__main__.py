"""`python -m app.mcp` - run the MCP server on stdio.

Local agents (opencode, Claude Code, ...) spawn this as a subprocess. OpenCode V2
config (server names live under `mcp.servers`; V1 put the name directly under
`mcp`):

    {
      "mcp": {
        "servers": {
          "genai-gui": {
            "type": "local",
            "command": ["<repo>/backend/.venv/Scripts/python.exe", "-m", "app.mcp"],
            "cwd": "<repo>/backend"
          }
        }
      }
    }

Refuses to start while "Agent Access" is disabled in Settings - enable it
there first. stdio is implicitly local; the `agentToken` setting gates the
future streamable-HTTP transport for remote agents.

This process is standalone, so it bootstraps the data folders and SQLite schema
itself instead of relying on the FastAPI lifespan.
"""

from __future__ import annotations

import sys


def main() -> None:
    from app.common import db, paths, settings_store

    values, _ = settings_store.load()
    if not values.get("agentEnabled"):
        print(
            "[mcp] Agent access is disabled - enable it in the GUI "
            "(Settings -> Agent Access) and start this server again.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    # This process is standalone (it does not run FastAPI's lifespan), so it
    # owns its own bootstrap: create the data dirs and the SQLite schema before
    # any tool touches the library/jobs tables. Both calls are idempotent, so
    # running alongside the backend is safe.
    paths.ensure_base_dirs()
    db.init_db()

    from app.mcp.server import create_server

    create_server().run()  # stdio


if __name__ == "__main__":
    main()
