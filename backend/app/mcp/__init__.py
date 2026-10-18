"""MCP server package - thin tools over the same services the REST API uses.

Entry point: `python -m app.mcp` (see `__main__.py`). Deliberately empty of
imports: the stdio entry checks the Agent Access setting *before* loading the
MCP SDK, so a disabled install fails fast with a clear message.
"""
