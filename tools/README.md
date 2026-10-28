# tools\ - portable runtime bootstrap

`Launch.bat` (repo root) is the normal entry point. It calls `Setup.bat` on first
run or when the Vue sources are newer than the existing build.

## What Setup.bat checks

1. Creates `backend\.venv` with `uv` when needed. If `uv` is missing, Setup
   offers to download the portable `tools\uv.exe` from the official Astral
   release (one executable, no installer). uv downloads its Python into
   `tools\python`, so the backend needs **no system Python** and nothing is
   added to your PATH. Python + pip remains a fallback only when uv is skipped.
2. Checks **Git**. Git is required for ComfyUI node installs/updates; there is
   no ZIP fallback. If Git is missing, Setup offers `winget install Git.Git`
   when winget exists, otherwise it shows the official link and asks whether to
   open <https://git-scm.com/download/win>. The app can still start without
   Git, but node install buttons stay disabled.
3. Builds `frontend\dist` only when it is missing or older than
   `frontend\src`, `index.html`, Vite/TypeScript/Tailwind configs or
   `package*.json`. If npm is missing, Setup offers a portable Node.js download
   into `tools\node` first (no installer, no PATH changes), then winget, then
   the official download page. Node.js is only needed for that build; the
   backend serves the already-built `dist` at runtime.

Every missing tool is installed/downloaded only after a Y/N prompt. Setup never
changes ComfyUI content; node installs remain explicit clicks in the app.

## Fully self-contained option (no global installs)

Copy a portable `uv.exe` into this folder (download:
<https://docs.astral.sh/uv/> - it is a single executable, no installer needed).
`Setup.bat` prefers it when `uv` is not on `PATH`. With this one file the
backend side needs nothing installed on the PC.

Node.js is still required for the *initial* frontend build (or after Vue source
changes). Setup can download portable Node.js into `tools\node`; once
`frontend\dist` exists, the app runs without Node.

## What lives where (portability)

| Path                     | Contents                                | Portable?          |
| ------------------------ | --------------------------------------- | ------------------ |
| `tools\uv.exe`           | portable uv (downloaded on consent)     | re-downloadable    |
| `tools\python\`          | uv-managed Python used by `.venv`       | re-downloadable    |
| `tools\node\`            | portable Node.js used only to build     | re-downloadable    |
| `backend\.venv\`         | project Python environment              | recreated on 1st run |
| `frontend\node_modules\` | npm packages (browser/UI toolchain)     | reinstallable      |
| `frontend\dist\`         | built UI, served by the backend          | rebuildable        |
| `data\`                  | `settings.json`, `app.db`, library, exports | your data - keep it |

The whole folder can be copied to another PC; run `Launch.bat` once there
(it detects a moved/broken `.venv`, repairs it and rebuilds the frontend as
needed). Your `data\` folder travels with it.

## Building for other users

`frontend\dist` is gitignored, so a normal git commit carries the Vue source,
not the built UI. On the next launch, Setup sees that the sources changed and
offers to rebuild with system npm or portable Node.js.

To publish a release that needs no Node on the user's PC, run `Launch.bat` (or
`cd frontend && npm run build`) before packaging the ZIP/installer and include
`frontend\dist` in it. GitHub source users will still build automatically with
portable Node if they do not have it.
