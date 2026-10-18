@echo off
rem GenAI GUI - start the backend (dev). Requires uv + Python 3.11+.
cd /d "%~dp0..\backend"
uv sync
uv run uvicorn app.main:app --reload --port 8766
