"""Phase B - node installer for ComfyUI custom nodes and packages.

Everything here runs only from an explicit user click on an entry that a
shipped `requirements.json` declares (core or a GenModule). The GUI can name a
module + node; it can never hand the server an arbitrary repository.

Safety (docs/COMFYUI_CONTENT.md §4):
- full 40-character pinned commits only; unpinned git entries are refused;
  updates are also refused when the checkout has local changes;
- the folder is staged first and moved into `custom_nodes/` on success, so a
  failed download never leaves a half-written node behind;
- nothing is deleted from the user's install; a failed pip step leaves the node
  in place for a retry;
- installs are serialized (one at a time) and stream a log to the GUI.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.common import paths
from app.connectors.comfyui import parse_auth

from . import service

STAGING_DIR = paths.DATA_DIR / "tmp" / "comfyui-install"
MAX_LOG_LINES = 500
MAX_TASKS = 20
# A single git/pip step should never hang the install forever (network stalls,
# credential prompts, a proxy that never answers).
COMMAND_TIMEOUT = 900
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class InstallBusy(Exception):
    """Another install is already running."""


class InstallError(Exception):
    """A user-facing install failure."""


_TASKS: dict[str, dict] = {}
_TASK_ORDER: list[str] = []
_ACTIVE_ID: str | None = None
_LOCK = threading.Lock()


# -- task registry --------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _snapshot(task: dict) -> dict:
    with _LOCK:
        data = {key: value for key, value in task.items() if key != "log"}
        data["log"] = list(task["log"])
        return data


def _set(task: dict, **values) -> None:
    with _LOCK:
        task.update(values)


def _log(task: dict, line: str) -> None:
    text = str(line).replace("\r", "").strip()
    if not text:
        return
    text = text[:1000]
    with _LOCK:
        task["log"].append(text)
        overflow = len(task["log"]) - MAX_LOG_LINES
        if overflow > 0:
            del task["log"][:overflow]


def _staging_dir(task: dict) -> Path:
    return STAGING_DIR / task["id"]


def _safe_name(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', "-", name).strip(" .")
    if not cleaned or cleaned in {".", ".."}:
        raise InstallError("Invalid node name in requirements.json")
    return cleaned[:120]


def _display(cmd: list[str]) -> str:
    return subprocess.list2cmdline([str(part) for part in cmd])


# -- planning -------------------------------------------------------------------


def _requirement(module_id: str, node_name: str) -> tuple[str, dict]:
    module_name, block = service.load_requirements(module_id)
    raw_nodes = block.get("nodes") if isinstance(block, dict) else None
    wanted = node_name.strip().lower()
    for item in raw_nodes if isinstance(raw_nodes, list) else []:
        if isinstance(item, dict) and str(item.get("name") or "").strip().lower() == wanted:
            return module_name, item
    raise LookupError(f"'{node_name}' is not declared in {module_name}'s requirements.json")


def _git_available() -> bool:
    return shutil.which("git") is not None


def _validate_repo(repo: str) -> None:
    if not re.match(r"^https?://[^\s]+$", repo):
        raise InstallError("Only http(s) repositories are supported.")


def _validate_commit(commit: str) -> None:
    if not COMMIT_RE.fullmatch(commit):
        raise InstallError(
            "requirements.json needs a full 40-character pinned commit (hex SHA) for git installs."
        )


def _python_or_none(report: dict) -> str | None:
    python = report.get("pythonPath")
    return str(python) if python else None


def _plan(module_id: str, node_name: str) -> dict:
    module_name, item = _requirement(module_id, node_name)
    report = service.inspect()
    if not report.get("valid"):
        raise InstallError(report.get("error") or "Configure the ComfyUI folder first.")

    root = Path(report["path"])
    nodes_dir = root / "custom_nodes"
    if not nodes_dir.is_dir():
        raise InstallError("custom_nodes/ was not found in the ComfyUI folder.")

    name = str(item.get("name") or "").strip()
    if not name:
        raise InstallError("requirements.json node entry has no name.")
    target = nodes_dir / _safe_name(name)
    repo = str(item.get("repo") or "").strip()
    commit = str(item.get("commit") or "").strip().lower()
    package = str(item.get("package") or "").strip()
    pip_spec = str(item.get("pip") or "").strip()
    python = _python_or_none(report)

    if target.exists():
        if repo and (target / ".git").is_dir():
            action = "update"
        else:
            raise InstallError(
                "That folder already exists but is not a git checkout. "
                "Rename it or install the node manually - the app never overwrites it."
            )
        pip_command = None
    elif package:
        action = "pip"
        if not python:
            raise InstallError("No Python was found for this ComfyUI install, so pip installs are disabled.")
        requirements_file = root / "comfy" / "manager_requirements.txt"
        pip_base = [python, "-m", "pip", "install", "--disable-pip-version-check", "--no-input"]
        if package == "comfyui_manager" and requirements_file.is_file():
            pip_command = [*pip_base, "-r", str(requirements_file)]
        elif pip_spec:
            pip_command = [*pip_base, pip_spec]
        else:
            raise InstallError("requirements.json needs a `pip` package name for this install.")
    elif repo:
        action = "clone"
        _validate_repo(repo)
        pip_command = None
    else:
        raise InstallError("Nothing to install: requirements.json has neither a repo nor a package.")

    if not repo and action != "pip":
        raise InstallError("requirements.json has no repository for this node.")
    if action in {"clone", "update"}:
        if not commit:
            raise InstallError(
                "requirements.json has no pinned commit - refusing to install or update an unpinned checkout."
            )
        _validate_commit(commit)

    return {
        "moduleId": module_id,
        "moduleName": module_name,
        "nodeName": name,
        "action": action,
        "target": str(target),
        "repo": repo,
        "commit": commit,
        "package": package,
        "python": python,
        "pipCommand": pip_command,
    }


def start_install(module_id: str, node_name: str) -> dict:
    """Plan + start one install; returns the task snapshot (HTTP 202)."""
    plan = _plan(module_id, node_name)

    global _ACTIVE_ID
    with _LOCK:
        if _ACTIVE_ID is not None:
            raise InstallBusy("Another node install is already running - wait for it to finish.")
        task = {
            "id": uuid.uuid4().hex[:12],
            "moduleId": module_id,
            "moduleName": plan["moduleName"],
            "nodeName": plan["nodeName"],
            "action": plan["action"],
            "target": plan["target"],
            "repo": plan["repo"],
            "commit": plan["commit"],
            "status": "running",
            "stage": "starting",
            "log": [],
            "error": None,
            "warning": None,
            "restartRequired": False,
            "startedAt": _now(),
            "finishedAt": None,
        }
        _TASKS[task["id"]] = task
        _TASK_ORDER.append(task["id"])
        _ACTIVE_ID = task["id"]
        while len(_TASK_ORDER) > MAX_TASKS:
            _TASKS.pop(_TASK_ORDER.pop(0), None)

    thread = threading.Thread(target=_run, args=(task["id"], plan), name=f"comfy-install-{task['id']}", daemon=True)
    thread.start()
    return _snapshot(task)


def get_task(task_id: str) -> dict | None:
    with _LOCK:
        task = _TASKS.get(task_id)
    return _snapshot(task) if task else None


def list_tasks() -> list[dict]:
    with _LOCK:
        ids = list(reversed(_TASK_ORDER))
    result = []
    for task_id in ids:
        task = get_task(task_id)
        if task:
            result.append(task)
    return result


# -- execution ------------------------------------------------------------------


def _run(task_id: str, plan: dict) -> None:
    global _ACTIVE_ID
    with _LOCK:
        task = _TASKS.get(task_id)
    if task is None:
        return

    try:
        _log(task, f"{plan['action'].capitalize()} {plan['nodeName']} - {plan['moduleName']}")
        _set(task, stage="working")
        if plan["action"] == "pip":
            _install_pip(task, plan)
        elif plan["action"] == "clone":
            _install_clone(task, plan)
        else:
            _update_node(task, plan)
        _set(task, status="succeeded", stage="done", restartRequired=True, finishedAt=_now())
        _log(task, "Done. Restart ComfyUI to load the new node.")
    except Exception as exc:  # noqa: BLE001 - any failure becomes a task error
        _log(task, f"FAILED: {exc}")
        _set(task, status="failed", stage="failed", error=str(exc), finishedAt=_now())
    finally:
        with _LOCK:
            if _ACTIVE_ID == task_id:
                _ACTIVE_ID = None


def _install_pip(task: dict, plan: dict) -> None:
    command = plan["pipCommand"]
    if not command:
        raise InstallError("No pip command could be built for this node.")
    _set(task, stage="installing")
    _run_command(task, command)


def _install_clone(task: dict, plan: dict) -> None:
    target = Path(plan["target"])
    if target.exists():
        raise InstallError("The target folder appeared while installing - aborting without touching it.")

    if _git_available():
        staging = _staging_dir(task)
        try:
            staging.mkdir(parents=True, exist_ok=True)
            checkout = staging / "repo"
            _set(task, stage="cloning")
            _log(task, f"git clone {plan['repo']}")
            _run_command(task, ["git", "clone", "--quiet", plan["repo"], str(checkout)], cwd=staging)
            if plan["commit"]:
                _set(task, stage="checking out pinned commit")
                _log(task, f"git checkout {plan['commit']}")
                _run_command(task, ["git", "-C", str(checkout), "checkout", "--quiet", plan["commit"]])
            shutil.move(str(checkout), str(target))
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    else:
        _install_zip(task, plan)

    _install_python_deps(task, plan)


def _update_node(task: dict, plan: dict) -> None:
    target = Path(plan["target"])
    _set(task, stage="checking local changes")
    _log(task, "Checking the checkout for local changes...")
    status = subprocess.run(
        ["git", "-C", str(target), "status", "--porcelain"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if status.returncode != 0:
        raise InstallError("git could not read this checkout - update skipped.")
    if status.stdout.strip():
        raise InstallError("This node has local changes - update skipped so they are not overwritten.")

    _set(task, stage="fetching pinned commit")
    _run_command(task, ["git", "-C", str(target), "fetch", "--all", "--prune"])
    _run_command(task, ["git", "-C", str(target), "checkout", "--quiet", plan["commit"]])
    _install_python_deps(task, plan)


def _install_python_deps(task: dict, plan: dict) -> None:
    target = Path(plan["target"])
    requirements = target / "requirements.txt"
    installer = target / "install.py"
    python = plan.get("python")

    if not requirements.is_file() and not installer.is_file():
        _log(task, "No requirements.txt or install.py - nothing to pip install.")
        return
    if not python:
        warning = "Python was not found for this ComfyUI install - dependencies were not installed."
        _set(task, warning=warning)
        _log(task, warning)
        return

    _set(task, stage="installing dependencies")
    if requirements.is_file():
        _run_command(
            task,
            [python, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "-r", str(requirements)],
            cwd=target,
        )
    else:
        _run_command(task, [python, str(installer)], cwd=target)


def _run_command(task: dict, command: list[str], cwd: Path | None = None) -> None:
    _log(task, f"$ {_display(command)}")
    env = os.environ.copy()
    # Never let git or pip sit on an invisible credential prompt.
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env.setdefault("PIP_NO_INPUT", "1")
    try:
        proc = subprocess.Popen(
            [str(part) for part in command],
            cwd=str(cwd) if cwd else None,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        raise InstallError(f"Could not run {command[0]}: {exc}") from exc

    tail: list[str] = []

    def pump() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            text = line.rstrip()
            if text:
                tail.append(text)
                if len(tail) > 8:
                    tail.pop(0)
                _log(task, text)

    reader = threading.Thread(target=pump, name="install-output", daemon=True)
    reader.start()
    try:
        code = proc.wait(timeout=COMMAND_TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        reader.join(timeout=3)
        raise InstallError(
            f"{Path(str(command[0])).name} timed out after {COMMAND_TIMEOUT // 60} minutes."
        ) from None
    reader.join(timeout=5)

    if code != 0:
        detail = f" Last output: {tail[-1]}" if tail else ""
        raise InstallError(f"{Path(str(command[0])).name} exited with code {code}.{detail}")


# -- zip fallback ---------------------------------------------------------------


def _zip_url(repo: str, commit: str) -> str:
    match = re.match(r"^https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", repo)
    if not match:
        raise InstallError("Git is not installed and this repository is not on GitHub - install Git or the node manually.")
    if not commit:
        raise InstallError("Git is not installed and requirements.json has no pinned commit - cannot use the zip fallback.")
    owner, name = match.group(1), match.group(2)
    return f"https://codeload.github.com/{owner}/{name}/zip/{commit}"


def _download(task: dict, url: str, target: Path) -> None:
    _log(task, f"Downloading {url}")
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(target.suffix + ".part")
    try:
        with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                with open(part, "wb") as handle:
                    for chunk in response.iter_bytes():
                        handle.write(chunk)
        os.replace(part, target)
    finally:
        if part.exists():
            part.unlink(missing_ok=True)


def _safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            resolved = (root / member.filename).resolve()
            if resolved != root and root not in resolved.parents:
                raise InstallError("The downloaded archive contains an unsafe path - aborted.")
        bundle.extractall(root)


def _install_zip(task: dict, plan: dict) -> None:
    _set(task, stage="downloading")
    staging = _staging_dir(task)
    try:
        staging.mkdir(parents=True, exist_ok=True)
        archive = staging / "node.zip"
        extract_root = staging / "extract"
        _download(task, _zip_url(plan["repo"], plan["commit"]), archive)
        _safe_extract(archive, extract_root)
        candidates = [entry for entry in extract_root.iterdir() if entry.is_dir()]
        if not candidates:
            raise InstallError("The downloaded archive did not contain a folder.")
        source = next((entry for entry in candidates if (entry / "__init__.py").is_file()), candidates[0])
        target = Path(plan["target"])
        if target.exists():
            raise InstallError("The target folder appeared while installing - aborting without touching it.")
        shutil.move(str(source), str(target))
    finally:
        shutil.rmtree(staging, ignore_errors=True)


# -- restart --------------------------------------------------------------------


def restart_comfyui() -> dict:
    """Ask Manager to reboot ComfyUI; falls back to instructions."""
    from app.connectors import service as connectors_service

    url, auth = connectors_service.active_connection("comfyui")
    base = (url or "").strip().rstrip("/")
    if not base:
        return {"restarted": False, "endpoint": None, "message": "No ComfyUI connection is configured."}

    headers = parse_auth(auth)
    unreachable = False
    for path in ("/api/v2/manager/reboot", "/v2/manager/reboot", "/api/manager/reboot", "/manager/reboot"):
        try:
            with httpx.Client(timeout=httpx.Timeout(8.0, connect=3.0)) as client:
                response = client.post(f"{base}{path}", headers=headers)
            if response.status_code < 400:
                return {
                    "restarted": True,
                    "endpoint": path,
                    "message": "Restart requested - ComfyUI will be back in a few seconds.",
                }
        except (httpx.RemoteProtocolError, httpx.ReadTimeout):
            # Manager often closes the socket as it reboots - the request landed.
            return {
                "restarted": True,
                "endpoint": path,
                "message": "Restart requested - ComfyUI will be back in a few seconds.",
            }
        except httpx.HTTPError:
            unreachable = True
            break

    if unreachable:
        return {"restarted": False, "endpoint": None, "message": f"ComfyUI is not reachable at {base}."}
    return {
        "restarted": False,
        "endpoint": None,
        "message": "No ComfyUI-Manager reboot endpoint was found - close and relaunch ComfyUI.",
    }
