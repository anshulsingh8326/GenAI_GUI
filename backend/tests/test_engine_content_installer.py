"""Planning tests for the ComfyUI node installer.

These tests never clone, pip-install, or touch a real ComfyUI folder. They
exercise the safety gate that makes git installs reproducible: a git entry must
carry a full 40-character pinned commit.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.engine_content import installer

PIN = "a" * 40
NODES = [
    {
        "name": "PinnedGit",
        "repo": "https://github.com/example/pinned",
        "commit": PIN.upper(),
    },
    {
        "name": "UnpinnedGit",
        "repo": "https://github.com/example/unpinned",
    },
    {
        "name": "InvalidGit",
        "repo": "https://github.com/example/invalid",
        "commit": "main",
    },
    {
        "name": "PackageNode",
        "package": "demo_pkg",
        "pip": "demo-pkg>=1",
    },
]


@pytest.fixture()
def comfy_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "ComfyUI"
    (root / "custom_nodes").mkdir(parents=True)
    (root / "main.py").write_text("", encoding="utf-8")
    report = {"valid": True, "path": str(root), "pythonPath": str(root / "python.exe")}

    monkeypatch.setattr(installer.service, "inspect", lambda: report)
    monkeypatch.setattr(
        installer.service,
        "load_requirements",
        lambda module_id: ("Test module", {"nodes": NODES}),
    )
    # Planning tests should not depend on Git being on the test machine.
    monkeypatch.setattr(installer, "_git_available", lambda: True)
    return root


def test_plan_pins_and_normalizes_git_commit(comfy_root: Path) -> None:
    plan = installer._plan("test", "PinnedGit")

    assert plan["action"] == "clone"
    assert plan["commit"] == PIN
    assert Path(plan["target"]) == comfy_root / "custom_nodes" / "PinnedGit"


def test_plan_refuses_unpinned_git_entry(comfy_root: Path) -> None:
    with pytest.raises(installer.InstallError, match="no pinned commit"):
        installer._plan("test", "UnpinnedGit")


def test_plan_refuses_non_sha_commit(comfy_root: Path) -> None:
    with pytest.raises(installer.InstallError, match="full 40-character pinned commit"):
        installer._plan("test", "InvalidGit")


def test_plan_refuses_git_install_when_git_is_missing(
    comfy_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(installer, "_git_available", lambda: False)

    with pytest.raises(installer.InstallError, match="Git is required"):
        installer._plan("test", "PinnedGit")


def test_plan_allows_package_without_git(comfy_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(installer, "_git_available", lambda: False)

    plan = installer._plan("test", "PackageNode")

    assert plan["action"] == "pip"


def test_plan_allows_package_without_commit(comfy_root: Path) -> None:
    plan = installer._plan("test", "PackageNode")

    assert plan["action"] == "pip"
    assert plan["commit"] == ""
    assert plan["pipCommand"][-1] == "demo-pkg>=1"


def test_plan_updates_existing_pinned_checkout(comfy_root: Path) -> None:
    checkout = comfy_root / "custom_nodes" / "PinnedGit"
    (checkout / ".git").mkdir(parents=True)

    plan = installer._plan("test", "PinnedGit")

    assert plan["action"] == "update"
    assert plan["commit"] == PIN


def test_plan_refuses_update_without_pin(comfy_root: Path) -> None:
    checkout = comfy_root / "custom_nodes" / "UnpinnedGit"
    (checkout / ".git").mkdir(parents=True)

    with pytest.raises(installer.InstallError, match="no pinned commit"):
        installer._plan("test", "UnpinnedGit")


def test_shipped_git_requirements_are_pinned() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    manifests = [
        backend_root / "app" / "engine_content" / "core_requirements.json",
        *sorted((backend_root / "app" / "GenModules").glob("*/requirements.json")),
    ]

    for manifest in manifests:
        block = json.loads(manifest.read_text(encoding="utf-8"))
        for node in block.get("nodes") or []:
            if not node.get("repo") or node.get("package"):
                continue
            commit = str(node.get("commit") or "")
            assert re.fullmatch(r"[0-9a-f]{40}", commit.lower()), (
                f"{manifest} node {node.get('name')!r} needs a full 40-character pinned commit"
            )
