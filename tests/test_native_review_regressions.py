from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from tests.integration_consumer import git
from typer.testing import CliRunner

from agent_marketplace_versioner.auto_sync_manifests import sync_native_marketplaces, sync_staged_manifests
from agent_marketplace_versioner.check_plugin_version_bump import check_native_version_bumps
from agent_marketplace_versioner.cli import app


def initialize(repo: Path) -> None:
    git(repo, "init", "--quiet", "--initial-branch=fixture")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.invalid")


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data) + "\n", encoding="utf-8")


@pytest.mark.parametrize("ignored", [True, False])
def test_check_uses_ignore_rules_at_refs_not_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ignored: bool
) -> None:
    initialize(tmp_path)
    manifest = Path("catalog/tool/.codex-plugin/plugin.json")
    write_json(tmp_path / manifest, {"name": "tool", "version": "1.0.0"})
    ignore = tmp_path / "catalog/.gitignore"
    ignore.write_text("tool/\n" if ignored else "")
    content = tmp_path / "catalog/tool/README.md"
    content.write_text("before\n")
    git(tmp_path, "add", "-f", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    base = git(tmp_path, "rev-parse", "HEAD").strip()
    content.write_text("after\n")
    git(tmp_path, "add", "-f", ".")
    git(tmp_path, "commit", "--quiet", "-m", "changed")
    ignore.write_text("" if ignored else "tool/\n")
    before = git(tmp_path, "diff")
    monkeypatch.chdir(tmp_path)

    assert check_native_version_bumps(base) == [manifest]
    assert git(tmp_path, "diff") == before


@pytest.mark.parametrize("remote", [[], [{"name": "remote", "source": "github:example/remote"}]])
def test_empty_local_catalog_bootstraps_nonignored_native_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, remote: list[dict[str, str]]
) -> None:
    initialize(tmp_path)
    catalog = tmp_path / "catalog/.codex-plugin/marketplace.json"
    write_json(catalog, {"plugins": remote})
    write_json(tmp_path / "catalog/components/tool/.codex-plugin/plugin.json", {"name": "tool", "version": "1.0.0"})
    write_json(tmp_path / "catalog/ignored/.claude-plugin/plugin.json", {"name": "ignored", "version": "1.0.0"})
    (tmp_path / ".gitignore").write_text("catalog/ignored/\n")
    git(tmp_path, "add", "catalog/.codex-plugin/marketplace.json", "catalog/components", ".gitignore")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    monkeypatch.chdir(tmp_path)

    assert sync_native_marketplaces() == [Path("catalog/.codex-plugin/marketplace.json")]
    assert json.loads(catalog.read_text()) == {"plugins": [*remote, {"name": "tool", "source": "./components/tool"}]}
    assert sync_native_marketplaces() == []


def test_object_local_sources_are_already_catalogued(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    initialize(tmp_path)
    catalog = tmp_path / ".agents/plugins/marketplace.json"
    write_json(
        catalog,
        {
            "plugins": [
                {
                    "name": "tool",
                    "source": {"source": "local", "path": "./plugins/tool"},
                    "policy": {"installation": "AVAILABLE"},
                }
            ]
        },
    )
    write_json(tmp_path / "plugins/tool/.claude-plugin/plugin.json", {"name": "tool", "version": "1.0.0"})
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    monkeypatch.chdir(tmp_path)

    assert sync_native_marketplaces(bump=False) == []
    assert json.loads(catalog.read_text()) == {
        "plugins": [
            {
                "name": "tool",
                "source": {"source": "local", "path": "./plugins/tool"},
                "policy": {"installation": "AVAILABLE"},
            }
        ]
    }


def test_relative_catalog_source_with_parent_traversal_is_already_catalogued(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize(tmp_path)
    catalog = tmp_path / "catalog/.claude-plugin/marketplace.json"
    write_json(catalog, {"version": "1.0.0", "plugins": [{"name": "tool", "source": "../shared/tool"}]})
    write_json(tmp_path / "shared/tool/.claude-plugin/plugin.json", {"name": "tool", "version": "1.0.0"})
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    monkeypatch.chdir(tmp_path)

    assert sync_native_marketplaces() == []
    assert json.loads(catalog.read_text()) == {
        "version": "1.0.0",
        "plugins": [{"name": "tool", "source": "../shared/tool"}],
    }


def test_check_requires_version_bump_when_native_plugin_moves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    initialize(tmp_path)
    old_manifest = Path("plugins/old/.claude-plugin/plugin.json")
    write_json(tmp_path / old_manifest, {"name": "tool", "version": "1.0.0"})
    content = tmp_path / "plugins/old/README.md"
    content.write_text("before\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    base = git(tmp_path, "rev-parse", "HEAD").strip()
    git(tmp_path, "mv", "plugins/old", "plugins/new")
    (tmp_path / "plugins/new/README.md").write_text("after\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "move")
    monkeypatch.chdir(tmp_path)

    assert check_native_version_bumps(base) == [Path("plugins/new/.claude-plugin/plugin.json")]


def test_check_requires_bumps_for_each_manifest_in_multi_harness_plugin_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize(tmp_path)
    for harness in (".claude-plugin", ".codex-plugin"):
        write_json(tmp_path / "plugins/old" / harness / "plugin.json", {"name": "tool", "version": "1.0.0"})
    content = tmp_path / "plugins/old/README.md"
    content.write_text("before\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    base = git(tmp_path, "rev-parse", "HEAD").strip()
    git(tmp_path, "mv", "plugins/old", "plugins/new")
    (tmp_path / "plugins/new/README.md").write_text("after\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "move")
    monkeypatch.chdir(tmp_path)

    assert check_native_version_bumps(base) == [
        Path("plugins/new/.claude-plugin/plugin.json"),
        Path("plugins/new/.codex-plugin/plugin.json"),
    ]


def test_reconcile_native_layout_dry_run_and_repair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    initialize(tmp_path)
    manifest = tmp_path / "catalog/tool/.codex-plugin/plugin.json"
    write_json(manifest, {"name": "tool", "version": "1.0.0", "skills": ["./skills/removed"]})
    kimi = tmp_path / "catalog/tool/kimi.plugin.json"
    scalar = {"name": "tool", "version": "2.0.0", "skills": "./skills/"}
    write_json(kimi, scalar)
    skill = tmp_path / "catalog/tool/skills/demo/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: demo\n---\n")
    marketplace = tmp_path / "catalog/.agents/plugins/marketplace.json"
    write_json(marketplace, {"plugins": []})
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    monkeypatch.chdir(tmp_path)

    assert CliRunner().invoke(app, ["reconcile", "--dry-run"]).exit_code == 1
    assert git(tmp_path, "status", "--porcelain") == ""
    assert CliRunner().invoke(app, ["reconcile"]).exit_code == 0
    assert json.loads(manifest.read_text())["skills"] == ["./skills/demo"]
    assert json.loads(manifest.read_text())["version"] == "1.1.0"
    assert json.loads(kimi.read_text()) == scalar
    assert json.loads(marketplace.read_text()) == {"plugins": [{"name": "tool", "source": "./tool"}]}
    assert CliRunner().invoke(app, ["reconcile", "--dry-run"]).exit_code == 0


def test_reconcile_explicit_empty_components(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    initialize(tmp_path)
    manifest = tmp_path / "tool/.codex-plugin/plugin.json"
    write_json(manifest, {"name": "tool", "version": "1.0.0", "skills": []})
    skill = tmp_path / "tool/skills/demo/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: demo\n---\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    monkeypatch.chdir(tmp_path)

    assert CliRunner().invoke(app, ["reconcile", "--dry-run"]).exit_code == 1
    assert CliRunner().invoke(app, ["reconcile"]).exit_code == 0
    assert json.loads(manifest.read_text())["skills"] == ["./skills/demo"]


def test_reconcile_ignores_gitignored_components(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    initialize(tmp_path)
    manifest = tmp_path / "tool/.codex-plugin/plugin.json"
    write_json(manifest, {"name": "tool", "version": "1.0.0", "skills": []})
    ignored_skill = tmp_path / "tool/skills/private/SKILL.md"
    ignored_skill.parent.mkdir(parents=True)
    ignored_skill.write_text("---\nname: private\n---\n")
    (tmp_path / ".gitignore").write_text("tool/skills/private/\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    monkeypatch.chdir(tmp_path)

    assert CliRunner().invoke(app, ["reconcile", "--dry-run"]).exit_code == 0
    assert json.loads(manifest.read_text())["skills"] == []


def test_reconcile_ignores_nested_gitignored_invocable_skills(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    initialize(tmp_path)
    manifest = tmp_path / "tool/.claude-plugin/plugin.json"
    write_json(manifest, {"name": "tool", "version": "1.0.0", "commands": []})
    ignored_skill = tmp_path / "tool/skills/group/private/SKILL.md"
    ignored_skill.parent.mkdir(parents=True)
    ignored_skill.write_text("---\nname: private\n---\n")
    (tmp_path / ".gitignore").write_text("tool/skills/group/private/\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    monkeypatch.chdir(tmp_path)

    assert CliRunner().invoke(app, ["reconcile", "--dry-run"]).exit_code == 0
    assert json.loads(manifest.read_text())["commands"] == []


def test_sync_updates_local_catalog_name_after_plugin_rename(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    initialize(tmp_path)
    catalog = tmp_path / ".claude-plugin/marketplace.json"
    write_json(catalog, {"version": "1.0.0", "plugins": [{"name": "old", "source": "./tool"}]})
    manifest = tmp_path / "tool/.claude-plugin/plugin.json"
    write_json(manifest, {"name": "old", "version": "1.0.0"})
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    write_json(manifest, {"name": "new", "version": "1.0.1"})
    monkeypatch.chdir(tmp_path)

    assert sync_native_marketplaces() == [Path(".claude-plugin/marketplace.json")]
    assert json.loads(catalog.read_text())["plugins"] == [{"name": "new", "source": "./tool"}]


def test_staged_sync_does_not_publish_untracked_plugin_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize(tmp_path)
    catalog = tmp_path / ".claude-plugin/marketplace.json"
    write_json(catalog, {"plugins": [{"name": "tool", "source": "./plugins/tool"}]})
    plugin = tmp_path / "plugins/tool/.codex-plugin/plugin.json"
    write_json(plugin, {"name": "tool", "version": "1.0.0"})
    readme = tmp_path / "plugins/tool/README.md"
    readme.parent.mkdir(parents=True, exist_ok=True)
    readme.write_text("before\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    readme.write_text("after\n")
    git(tmp_path, "add", str(readme))
    write_json(tmp_path / "plugins/untracked/.codex-plugin/plugin.json", {"name": "untracked", "version": "1.0.0"})
    monkeypatch.chdir(tmp_path)

    sync_staged_manifests()

    staged_catalog = json.loads(
        subprocess.check_output(["git", "show", ":.claude-plugin/marketplace.json"], cwd=tmp_path)
    )
    assert staged_catalog["plugins"] == [{"name": "tool", "source": "./plugins/tool"}]


def test_staged_sync_reconciles_components_without_replacing_a_manual_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize(tmp_path)
    manifest = tmp_path / "tool/.claude-plugin/plugin.json"
    write_json(manifest, {"name": "tool", "version": "1.0.0", "skills": ["./skills/existing"]})
    existing = tmp_path / "tool/skills/existing/SKILL.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("existing\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    added = tmp_path / "tool/skills/added/SKILL.md"
    added.parent.mkdir(parents=True)
    added.write_text("added\n")
    write_json(manifest, {"name": "tool", "version": "1.0.1", "skills": ["./skills/existing"]})
    git(tmp_path, "add", ".")
    monkeypatch.chdir(tmp_path)

    sync_staged_manifests()

    staged = json.loads(subprocess.check_output(["git", "show", ":tool/.claude-plugin/plugin.json"], cwd=tmp_path))
    assert staged == {"name": "tool", "version": "1.0.1", "skills": ["./skills/existing", "./skills/added"]}


def test_staged_sync_ignores_an_unstaged_manual_version_when_deciding_to_bump(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize(tmp_path)
    manifest = tmp_path / "tool/.codex-plugin/plugin.json"
    write_json(manifest, {"name": "tool", "version": "1.0.0"})
    content = tmp_path / "tool/README.md"
    content.write_text("before\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    content.write_text("after\n")
    git(tmp_path, "add", "tool/README.md")
    write_json(manifest, {"name": "tool", "version": "1.0.1"})
    monkeypatch.chdir(tmp_path)

    sync_staged_manifests()

    staged = json.loads(subprocess.check_output(["git", "show", ":tool/.codex-plugin/plugin.json"], cwd=tmp_path))
    assert staged["version"] == "1.0.1"


def test_staged_sync_preserves_an_unstaged_marketplace_edit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    initialize(tmp_path)
    marketplace = tmp_path / ".claude-plugin/marketplace.json"
    write_json(marketplace, {"description": "base", "plugins": [{"name": "tool", "source": "./plugins/tool"}]})
    write_json(tmp_path / "plugins/tool/.claude-plugin/plugin.json", {"name": "tool", "version": "1.0.0"})
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    write_json(tmp_path / "plugins/added/.claude-plugin/plugin.json", {"name": "added", "version": "1.0.0"})
    git(tmp_path, "add", "plugins/added/.claude-plugin/plugin.json")
    write_json(marketplace, {"description": "local", "plugins": [{"name": "tool", "source": "./plugins/tool"}]})
    monkeypatch.chdir(tmp_path)

    sync_staged_manifests()

    staged = json.loads(subprocess.check_output(["git", "show", ":.claude-plugin/marketplace.json"], cwd=tmp_path))
    assert staged == {
        "description": "base",
        "plugins": [{"name": "tool", "source": "./plugins/tool"}, {"name": "added", "source": "./plugins/added"}],
    }
    assert json.loads(marketplace.read_text()) == {
        "description": "local",
        "plugins": [{"name": "tool", "source": "./plugins/tool"}],
    }


def test_marketplace_sync_does_not_bump_for_its_own_prior_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize(tmp_path)
    marketplace = tmp_path / "tool/.claude-plugin/marketplace.json"
    write_json(marketplace, {"version": "1.0.0", "plugins": [{"name": "tool", "source": "./"}]})
    write_json(tmp_path / "tool/.codex-plugin/plugin.json", {"name": "tool", "version": "1.0.0"})
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    base = git(tmp_path, "rev-parse", "HEAD").strip()
    write_json(marketplace, {"version": "1.0.1", "plugins": [{"name": "tool", "source": "./"}]})
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "catalog bump")
    monkeypatch.chdir(tmp_path)

    assert sync_native_marketplaces(base_ref=base) == []
    assert json.loads(marketplace.read_text())["version"] == "1.0.1"


def test_marketplace_sync_fails_for_an_unavailable_revision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    initialize(tmp_path)
    marketplace = tmp_path / ".claude-plugin/marketplace.json"
    write_json(marketplace, {"version": "1.0.0", "plugins": [{"name": "tool", "source": "./tool"}]})
    write_json(tmp_path / "tool/.codex-plugin/plugin.json", {"name": "tool", "version": "1.0.0"})
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(RuntimeError, match="bad revision"):
        sync_native_marketplaces(base_ref="missing", head_ref="HEAD")


def test_staged_sync_bumps_existing_manifest_when_adding_a_harness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize(tmp_path)
    claude_manifest = tmp_path / "tool/.claude-plugin/plugin.json"
    write_json(claude_manifest, {"name": "tool", "version": "1.0.0"})
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    codex_manifest = tmp_path / "tool/.codex-plugin/plugin.json"
    write_json(codex_manifest, {"name": "tool", "version": "1.0.0"})
    git(tmp_path, "add", ".")
    monkeypatch.chdir(tmp_path)

    assert sync_staged_manifests() == {Path("tool"): "1.1.0"}
    assert json.loads(claude_manifest.read_text())["version"] == "1.1.0"
    assert json.loads(codex_manifest.read_text())["version"] == "1.1.0"


def test_reconcile_does_not_register_an_ignored_skill_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    initialize(tmp_path)
    manifest = tmp_path / "tool/.claude-plugin/plugin.json"
    write_json(manifest, {"name": "tool", "version": "1.0.0", "commands": []})
    skill = tmp_path / "tool/skills/private/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nuser-invocable: true\n---\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("tool/skills/private/SKILL.md\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    monkeypatch.chdir(tmp_path)

    assert CliRunner().invoke(app, ["reconcile", "--dry-run"]).exit_code == 0
    assert json.loads(manifest.read_text())["commands"] == []
