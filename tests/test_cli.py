from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agent_marketplace_versioner.cli import app


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


def test_sync_stages_the_version_manifest_it_updates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "user.email", "test@example.test")
    manifest = tmp_path / "catalog" / "tool" / ".codex-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"name": "tool", "version": "1.0.0"}) + "\n", encoding="utf-8")
    content = manifest.parent.parent / "README.md"
    content.write_text("before\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "base")
    content.write_text("after\n", encoding="utf-8")
    _git(tmp_path, "add", content.relative_to(tmp_path).as_posix())
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["sync"])

    assert result.exit_code == 0
    assert (
        _git(tmp_path, "diff", "--cached", "--name-only")
        == "catalog/tool/.codex-plugin/plugin.json\ncatalog/tool/README.md\n"
    )
