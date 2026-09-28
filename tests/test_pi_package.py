from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.integration_consumer import git
from typer.testing import CliRunner

from agent_marketplace_versioner.auto_sync_manifests import sync_native_marketplaces, sync_staged_manifests
from agent_marketplace_versioner.check_plugin_version_bump import check_native_version_bumps
from agent_marketplace_versioner.cli import app

# The skill-lapidary layout: three native manifests and a Pi package.json share one repository-root source.
NATIVE = (Path(".claude-plugin/plugin.json"), Path(".codex-plugin/plugin.json"), Path("kimi.plugin.json"))
PACKAGE = Path("package.json")
CATALOG = Path(".claude-plugin/marketplace.json")
PI_PACKAGE = {
    "name": "skill-lapidary",
    "version": "0.6.29",
    "private": True,
    "type": "module",
    "peerDependencies": {"@earendil-works/pi-coding-agent": "*"},
    "pi": {"extensions": ["./packaging/pi/index.ts"], "skills": ["./skills"]},
}


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def version(repo: Path, path: Path) -> str:
    return json.loads((repo / path).read_text(encoding="utf-8"))["version"]


def commit_layout(repo: Path, package: dict[str, object] | None = None) -> None:
    git(repo, "init", "--quiet", "--initial-branch=fixture")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.invalid")
    for manifest in NATIVE:
        write_json(repo / manifest, {"name": "skill-lapidary", "version": "0.6.29", "skills": "./skills/"})
    write_json(repo / PACKAGE, package or PI_PACKAGE)
    write_json(repo / CATALOG, {"name": "skill-lapidary", "plugins": [{"name": "skill-lapidary", "source": "./"}]})
    skill = repo / "skills/cut/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: cut\n---\nbefore\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "base")


def edit_skill(repo: Path) -> None:
    (repo / "skills/cut/SKILL.md").write_text("---\nname: cut\n---\nafter\n", encoding="utf-8")


def test_staged_sync_bumps_the_pi_package_with_the_native_manifests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commit_layout(tmp_path)
    catalog = (tmp_path / CATALOG).read_text(encoding="utf-8")
    edit_skill(tmp_path)
    git(tmp_path, "add", ".")
    monkeypatch.chdir(tmp_path)

    assert sync_staged_manifests(tmp_path) == {Path(): "0.6.30"}
    assert {version(tmp_path, path) for path in (*NATIVE, PACKAGE)} == {"0.6.30"}
    assert json.loads(git(tmp_path, "show", ":package.json")) == {**PI_PACKAGE, "version": "0.6.30"}
    assert git(tmp_path, "diff", "--name-only") == ""
    assert (tmp_path / CATALOG).read_text(encoding="utf-8") == catalog


def test_repair_bumps_the_pi_package_with_the_native_manifests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    commit_layout(tmp_path)
    edit_skill(tmp_path)
    git(tmp_path, "commit", "--quiet", "-am", "edit skill")
    monkeypatch.chdir(tmp_path)

    audit = CliRunner().invoke(app, ["audit"])
    assert PACKAGE.as_posix() in json.loads(audit.stdout)["drifted_manifests"]
    assert CliRunner().invoke(app, ["repair"]).exit_code == 0
    assert {version(tmp_path, path) for path in (*NATIVE, PACKAGE)} == {"0.6.30"}


def test_check_reports_a_pi_package_that_missed_the_bump(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    commit_layout(tmp_path)
    base = git(tmp_path, "rev-parse", "HEAD").strip()
    edit_skill(tmp_path)
    for manifest in NATIVE:
        write_json(tmp_path / manifest, {"name": "skill-lapidary", "version": "0.6.30", "skills": "./skills/"})
    git(tmp_path, "commit", "--quiet", "-am", "bump natives only")
    monkeypatch.chdir(tmp_path)

    assert check_native_version_bumps(base) == [PACKAGE]


@pytest.mark.parametrize("args", [["reconcile", "--dry-run"], ["reconcile", "--dry-run", "--staged"]])
def test_reconcile_leaves_the_pi_package_and_catalog_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, args: list[str]
) -> None:
    commit_layout(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, args)
    assert (result.exit_code, "No drift detected" in result.stdout) == (0, True)


def test_a_package_json_that_is_not_a_pi_package_is_left_alone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tooling: dict[str, object] = {"name": "tooling", "version": "1.0.0", "devDependencies": {"prettier": "*"}}
    commit_layout(tmp_path, tooling)
    edit_skill(tmp_path)
    git(tmp_path, "add", ".")
    monkeypatch.chdir(tmp_path)

    assert sync_staged_manifests(tmp_path) == {Path(): "0.6.30"}
    assert version(tmp_path, PACKAGE) == "1.0.0"


def test_a_pi_package_without_a_plugin_manifest_is_unmanaged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    commit_layout(tmp_path)
    keyword_only = {"name": "pi-only", "version": "2.0.0", "keywords": ["pi-package"]}
    write_json(tmp_path / "packages/pi-only/package.json", keyword_only)
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "add a Pi-only package")
    (tmp_path / "packages/pi-only/index.ts").write_text("export {};\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    monkeypatch.chdir(tmp_path)

    sync_staged_manifests(tmp_path)
    assert sync_native_marketplaces(tmp_path) == []
    assert version(tmp_path, Path("packages/pi-only/package.json")) == "2.0.0"
    assert json.loads((tmp_path / CATALOG).read_text(encoding="utf-8"))["plugins"] == [
        {"name": "skill-lapidary", "source": "./"}
    ]
