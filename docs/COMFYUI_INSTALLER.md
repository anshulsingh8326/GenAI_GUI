# ComfyUI node installer (Phase B)

Status: **implemented**. This is the implementation contract for installing the custom nodes
and Python packages that `requirements.json` files declare. Model downloads are still Phase C
(see `docs/COMFYUI_CONTENT.md`).

The installer runs inside the local backend. The GUI can only name a **module id + node name**
that a shipped manifest already contains; it can never send an arbitrary repository URL.

## 1. What can be installed

| Manifest shape | Action | Notes |
| --- | --- | --- |
| `repo` + pinned `commit`, folder missing | **clone** | `git clone` into staging, `checkout <commit>`, then move into `custom_nodes/`. |
| same, but Git is not installed | **zip fallback** | GitHub codeload archive at the pinned commit. Refused for non-GitHub repos or missing commits. |
| folder exists, has `.git`, `repo` + `commit` | **update** | Refused when `git status --porcelain` is dirty. |
| folder exists without `.git` | **refused** | Never overwritten; the user must rename/remove it manually. |
| `package` + `pip`, folder missing | **pip** | Runs the detected ComfyUI Python: `<python> -m pip install ...`. |
| package already importable / folder installed | no button | The audit marks it installed; nothing runs. |

- `moduleId = "core"` resolves the shared `backend/app/engine_content/core_requirements.json`.
  Any other id resolves `backend/app/GenModules/<id>/requirements.json`.
- Node names are sanitized before becoming folder names. Only `http(s)` repository URLs are
  accepted; the GUI cannot supply paths.
- Package-style installs use the `pip` field (for example `comfyui-manager>=4.2,<5`). For
  `comfyui_manager`, an official `comfy/manager_requirements.txt` inside the ComfyUI folder
  takes precedence, so new ComfyUI releases install their own pinned Manager version.

## 2. Stages and dependencies

1. Plan: resolve the manifest entry, re-inspect the ComfyUI folder, find `custom_nodes/` and
   the install Python. Invalid folders/entries fail before a task starts.
2. Clone/update/download (staged outside `custom_nodes/`).
3. Move the finished node into `custom_nodes/<name>` (fails if the target appeared meanwhile).
4. Dependencies: `requirements.txt` if present, otherwise `install.py`; otherwise skip.
   A missing Python is a **warning**, not a failure - the node stays installed and the log says
   dependencies were skipped.
5. Done: `restartRequired = true`; the GUI offers **Restart ComfyUI**.

Every command:
- runs without a console window, with UTF-8 output streamed into the task log;
- gets `GIT_TERMINAL_PROMPT=0` / `PIP_NO_INPUT=1`, so a credential prompt can never hang a
  background install;
- has a **15-minute** timeout. Timeout kills the child and fails the task;
- is one command at a time, globally. A second install returns HTTP 409.

`git fetch` never modifies local work because updates first refuse a dirty checkout. A failed
pip step leaves the cloned node in place for a retry. Nothing is deleted.

## 3. Task API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | `/api/comfyui/nodes/install` | `{ "moduleId": "...", "nodeName": "..." }` -> 202 + task |
| GET | `/api/comfyui/nodes/tasks` | recent tasks, newest first |
| GET | `/api/comfyui/nodes/tasks/{id}` | one task (the GUI polls it) |
| POST | `/api/comfyui/restart` | ask Manager to reboot |

Task shape (camelCase):

```json
{
  "id": "8569a9df1ddb",
  "moduleId": "core",
  "moduleName": "Core requirements",
  "nodeName": "ComfyUI-GGUF",
  "action": "clone",
  "target": "D:/ComfyUI/custom_nodes/ComfyUI-GGUF",
  "repo": "https://github.com/city96/ComfyUI-GGUF",
  "commit": "6ea2651e7df66d7585f6ffee804b20e92fb38b8a",
  "status": "succeeded",
  "stage": "done",
  "log": ["git clone ...", "..."],
  "error": null,
  "warning": null,
  "restartRequired": true,
  "startedAt": "2026-10-22T14:24:07+00:00",
  "finishedAt": "2026-10-22T14:24:12+00:00"
}
```

- Statuses: `running`, `succeeded`, `failed`. The log keeps the last 500 lines; the last 20
  tasks are kept in memory and cleared when the backend restarts.
- HTTP mapping: busy `409`, unknown module/node `404`, invalid folder/entry `400`.
- `GET /api/comfyui/requirements` is re-run by the GUI after a task finishes, so Install/
  Update buttons and badges reflect the new state.

## 4. Restart

`POST /api/comfyui/restart` uses the configured `comfyui` connection and tries Manager's
reboot endpoints in order:

1. `POST /api/v2/manager/reboot`
2. `POST /api/v2/manager/reboot` on the connection base URL
3. legacy `/manager/reboot`, `/api/manager/reboot`, `/manager/reboot` variants

A connection closed during the request (`RemoteProtocolError` / `ReadTimeout`) is treated as
"restart requested" because Manager often drops the socket while rebooting. With no
connection configured, the endpoint returns `restarted: false` and an instruction to restart
the portable launcher; the GUI shows that as a warning. The installer itself never needs
Manager.

## 5. GUI flow

Settings -> **Engine content**:

1. A missing required/recommended node shows **Install**; an installed node whose HEAD differs
   from the pinned commit shows **Update**. Update on a dirty checkout fails with a clear log.
2. The confirmation dialog lists the repository / package, pinned commit and what will run.
3. The log modal polls the task, auto-scrolls, shows warnings/errors, and offers **Retry** on
   failure. Closing it ("Run in background") doesn't stop the install.
4. On success: **Restart ComfyUI** and a terminal button to reopen the log.
5. Only one install runs at a time; all other install buttons are disabled while it does.

## 6. Safety summary

- Writes only inside the configured ComfyUI `custom_nodes/` and its Python environment.
- Pinned commits, staging + atomic move, dirty-check before update.
- Never overwrites an existing folder, never deletes, never auto-updates.
- No arbitrary repository input and no shell interpolation: arguments are passed as a list.
- Inspection itself remains read-only.

## 7. Verification

The install engine was exercised against fake ComfyUI roots (seeded venv, empty
`custom_nodes/`, scratch `GENAI_DATA_DIR`), never the user's real install:

- clone + pinned checkout + `requirements.txt` install;
- update fetch/checkout, and a dirty checkout refused with the local file intact;
- package install into a fake venv (`comfyui-manager`), detected in site-packages;
- zip fallback with Git disabled, including the no-Python warning;
- restart with no connection configured;
- GUI install and update (task log, audit refresh, Update disappearing when HEAD matches).

Model downloads, hash verification and uninstall/repair remain out of scope for Phase B.
