"""Connectors - the only place that talks to external engines (ComfyUI, Ollama).

Shared by every GenModule. The browser never connects to these services
directly; all traffic goes through the backend.
"""
