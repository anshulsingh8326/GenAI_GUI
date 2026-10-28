"""Read-only folder detection tests for ComfyUI content management."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.engine_content import service


def _make_source(root: Path) -> Path:
    source = root / "ComfyUI"
    (source / "custom_nodes").mkdir(parents=True)
    (source / "models").mkdir()
    (source / "main.py").write_text("", encoding="utf-8")
    return source


def test_portable_root_suggests_source_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    portable = tmp_path / "ComfyUI_windows_portable"
    source = _make_source(portable)
    monkeypatch.setattr(service, "_configured_folder", lambda: str(portable))

    report = service.inspect()

    assert report["valid"] is False
    assert report["suggestedFolder"] == str(source)
    assert "No main.py" in report["error"]


def test_suggester_handles_launcher_file_and_subfolder(tmp_path: Path) -> None:
    portable = tmp_path / "ComfyUI_windows_portable"
    source = _make_source(portable)
    launcher = portable / "run_nvidia_gpu.bat"
    launcher.write_text("", encoding="utf-8")

    assert service._source_folder_suggestion(launcher) == str(source)
    assert service._source_folder_suggestion(source / "custom_nodes") == str(source)
    assert service._source_folder_suggestion(source / "models" / "checkpoints") == str(source)


def test_valid_source_has_no_correction_suggestion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    portable = tmp_path / "ComfyUI_windows_portable"
    source = _make_source(portable)
    monkeypatch.setattr(service, "_configured_folder", lambda: str(source))

    report = service.inspect()

    assert report["valid"] is True
    assert report["suggestedFolder"] is None


def test_inspect_reports_git_availability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service.shutil, "which", lambda name: None)
    monkeypatch.setattr(service, "_configured_folder", lambda: "")

    assert service.inspect()["gitAvailable"] is False
