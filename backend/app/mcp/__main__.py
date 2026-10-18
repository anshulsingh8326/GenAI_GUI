"""`python -m app.mcp` - run the MCP server on stdio.

Local agents (opencode, Claude Code, ...) spawn this as a subprocess, e.g.:

    {
      "command": "<repo>/backend/.venv/Scripts/python.exe",
      "args": ["-m", "app.mcp"],
      "cwd": "<repo>/backend"
    }

Refuses to start while "Agent Access" is disabled in Settings - enable it
there first. stdio is implicitly local; the `agentToken` setting gates the
future streamable-HTTP transport for remote agents.
"""

from __future__ import annotations

import sys


def main() -> None:
    from app.common import settings_store

    values, _ = settings_store.load()
    if not values.get("agentEnabled"):
        print(
            "[mcp] Agent access is disabled - enable it in the GUI "
            "(Settings -> Agent Access) and start this server again.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    from app.mcp.server import create_server

    create_server().run()  # stdio


if __name__ == "__main__":
    main()
