# tools\ - portable backend bootstrap

`Launch.bat` (repo root) is the normal entry point. It calls `Setup.bat` on first
run or when the Vue sources are newer than the existing build.

## What Setup.bat checks

1. Creates `backend\.venv` with `uv` when needed. If `uv` is missing, Setup
   offers to download the portable `tools\uv.exe` from the official Astral
   release (one executable, no installer). `uv` can also manage its own Python,
   so the backend usually needs no global Python install. Python + pip remains
   a fallback.
2. Checks **Git**. Git is required for ComfyUI node installs/updates; there is
   no ZIP fallback. If Git is missing, Setup offers `winget install Git.Git` or
   opens <https://git-scm.com/download/win>. The app can still start without
   Git, but node installs stay disabled.
3. Builds `frontend\dist` only when it is missing or older than
   `frontend\src`, `index.html`, Vite/TypeScript/Tailwind configs or
   `package*.json`. Node.js/npm is only needed for that build; the backend
   serves the already-built `dist` at runtime.

Every missing tool is installed only after a Y/N prompt. Setup never changes
ComfyUI content; node installs remain explicit clicks in the app.

## Fully self-contained option (no global installs)

Copy a portable `uv.exe` into this folder (download:
<https://docs.astral.sh/uv/> - it is a single executable, no installer needed).
`Setup.bat` and `Launch.bat` prefer it when `uv` is not on `PATH`. With this one
file the backend side needs nothing installed on the PC.

Node.js is still required for the *initial* frontend build (or after Vue source
changes). Once `frontend\dist` exists, the app runs without Node.

## What lives where (portability)

| Path                  | Contents                                | Portable?          |
| --------------------- | --------------------------------------- | ------------------ |
| `backend\.venv\`      | Python environment (rebuilt by Setup)   | recreated on 1st run |
| `frontend\node_modules\` | npm packages (browser/UI toolchain)  | reinstallable      |
| `frontend\dist\`      | built UI, served by the backend          | rebuildable        |
| `data\`               | `settings.json`, `app.db`, library, exports | your data - keep it |

The whole folder can be copied to another PC; run `Launch.bat` once there
(it recreates the venv/build as needed). Your `data\` folder travels with it.
