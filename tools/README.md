# tools\ - optional drop-in utilities

`Launch.bat` (repo root) bootstraps the project on a fresh machine:

1. creates `backend\.venv` - via `uv` if found on PATH, otherwise via
   Python + pip, otherwise it looks for `uv.exe` **right here** in `tools\`;
2. builds `frontend\dist` - via Node.js/npm (one time);
3. runs the backend **in the same console window** (FastAPI serves the built
   frontend; logs stream right there) and opens http://127.0.0.1:8766 in the
   browser once it is up.

To stop the app press `Ctrl+C` in that window - or just close it.

## Fully self-contained option (no global installs)

Copy a portable `uv.exe` into this folder (download: https://docs.astral.sh/uv/ -
it is a single executable, no installer needed). `Launch.bat` prefers it when
`uv` is not on PATH. `uv` can also download and manage its own Python, so with
this one file the backend side needs nothing installed on the PC.

Node.js is still required for the *initial* frontend build. Once
`frontend\dist` exists, the app runs without Node (the backend serves the
built files).

## What lives where (portability)

| Path                  | Contents                                | Portable?          |
| --------------------- | --------------------------------------- | ------------------ |
| `backend\.venv\`      | Python environment (rebuilt by Launch)  | recreated on 1st run |
| `frontend\node_modules\` | npm packages (browser/UI toolchain)  | reinstallable      |
| `frontend\dist\`      | built UI, served by the backend          | rebuildable        |
| `data\`               | `settings.json`, `app.db`, library, exports | your data - keep it |

The whole folder can be copied to another PC; run `Launch.bat` once there
(it recreates the venv/build as needed). Your `data\` folder travels with it.
