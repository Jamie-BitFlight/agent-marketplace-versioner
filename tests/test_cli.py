from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agent_marketplace_versioner.cli import app


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


def _initialize_repository(repo: Path) -> None:
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.test")


def _commit_all(repo: Path, message: str) -> str:
    _git(repo, "add", ".")
    _git(repo, "commit", "--quiet", "-m", message)
    return _git(repo, "rev-parse", "HEAD").strip()


def _write_plugin_manifest(repo: Path, relative_path: str, version: str = "1.0.0") -> Path:
    manifest = repo / relative_path
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"name": "tool", "version": version}) + "\n", encoding="utf-8")
    return manifest


def test_sync_stages_the_version_manifest_it_updates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _initialize_repository(tmp_path)
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


def test_check_reports_a_missing_version_bump_in_a_real_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _initialize_repository(tmp_path)
    _write_plugin_manifest(tmp_path, "catalog/tool/.codex-plugin/plugin.json")
    content = tmp_path / "catalog" / "tool" / "README.md"
    content.write_text("before\n", encoding="utf-8")
    base_ref = _commit_all(tmp_path, "base")
    content.write_text("after\n", encoding="utf-8")
    _commit_all(tmp_path, "change content without bump")
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["check", "--base-ref", base_ref, "--head-ref", "HEAD"])

    assert result.exit_code == 1
    assert "catalog/tool/.codex-plugin/plugin.json" in result.output


def test_marketplace_sync_bumps_for_a_versioned_plugin_change_since_the_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _initialize_repository(tmp_path)
    plugin = _write_plugin_manifest(tmp_path, "catalog/tool/.codex-plugin/plugin.json")
    content = tmp_path / "catalog" / "tool" / "README.md"
    content.write_text("before\n", encoding="utf-8")
    marketplace = tmp_path / "catalog" / ".codex-plugin" / "marketplace.json"
    marketplace.parent.mkdir(parents=True)
    marketplace.write_text(
        json.dumps({"metadata": {"version": "1.0.0"}, "plugins": [{"name": "tool", "source": "./tool"}]}) + "\n",
        encoding="utf-8",
    )
    base_ref = _commit_all(tmp_path, "base")
    content.write_text("after\n", encoding="utf-8")
    plugin.write_text(json.dumps({"name": "tool", "version": "1.0.1"}) + "\n", encoding="utf-8")
    _commit_all(tmp_path, "versioned plugin change")
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["sync", "--marketplace", "--base-ref", base_ref, "--head-ref", "HEAD"])

    assert result.exit_code == 0
    assert json.loads(marketplace.read_text(encoding="utf-8"))["metadata"]["version"] == "1.0.1"


def test_audit_and_repair_report_and_fix_real_repository_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _initialize_repository(tmp_path)
    manifest = _write_plugin_manifest(tmp_path, "catalog/tool/.codex-plugin/plugin.json")
    content = tmp_path / "catalog" / "tool" / "README.md"
    content.write_text("before\n", encoding="utf-8")
    _commit_all(tmp_path, "base")
    content.write_text("after\n", encoding="utf-8")
    _commit_all(tmp_path, "change content without bump")
    monkeypatch.chdir(tmp_path)

    audit = CliRunner().invoke(app, ["audit"])
    repair = CliRunner().invoke(app, ["repair"])

    assert audit.exit_code == 0
    assert json.loads(audit.output) == {"drifted_manifests": ["catalog/tool/.codex-plugin/plugin.json"]}
    assert repair.exit_code == 0
    assert json.loads(repair.output) == {
        "repaired": [
            {"manifest": "catalog/tool/.codex-plugin/plugin.json", "old_version": "1.0.0", "new_version": "1.0.1"}
        ],
        "failed": [],
    }
    assert json.loads(manifest.read_text(encoding="utf-8"))["version"] == "1.0.1"


def test_reconcile_reports_then_repairs_manifest_component_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _initialize_repository(tmp_path)
    manifest = _write_plugin_manifest(tmp_path, "plugins/tool/.claude-plugin/plugin.json")
    manifest.write_text(
        json.dumps({"name": "tool", "version": "1.0.0", "skills": ["./skills/removed"]}) + "\n", encoding="utf-8"
    )
    skill = tmp_path / "plugins" / "tool" / "skills" / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: demo\n---\n", encoding="utf-8")
    marketplace = tmp_path / ".claude-plugin" / "marketplace.json"
    marketplace.parent.mkdir()
    marketplace.write_text(
        json.dumps({"metadata": {"version": "1.0.0"}, "plugins": [{"name": "tool", "source": "./plugins/tool"}]})
        + "\n",
        encoding="utf-8",
    )
    _commit_all(tmp_path, "base")
    monkeypatch.chdir(tmp_path)

    dry_run = CliRunner().invoke(app, ["reconcile", "--dry-run"])
    repaired = CliRunner().invoke(app, ["reconcile"])

    assert dry_run.exit_code == 1
    assert "Drift detected" in dry_run.output
    assert repaired.exit_code == 0
    assert json.loads(manifest.read_text(encoding="utf-8")) == {
        "name": "tool",
        "version": "1.1.0",
        "skills": ["./skills/demo"],
    }
