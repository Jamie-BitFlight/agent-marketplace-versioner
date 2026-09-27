from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from tests.integration_consumer import git
from typer.testing import CliRunner

from agent_marketplace_versioner.auto_sync_manifests import sync_native_marketplaces, sync_staged_manifests
from agent_marketplace_versioner.check_plugin_version_bump import check_native_version_bumps
from agent_marketplace_versioner.cli import app
from agent_marketplace_versioner.native_manifests import discover_manifests


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


@pytest.mark.parametrize(("args", "exit_code"), [(["--staged"], 0), ([], 1)])
def test_reconcile_staged_ignores_untracked_skills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, args: list[str], exit_code: int
) -> None:
    initialize(tmp_path)
    write_json(tmp_path / "tool/.claude-plugin/plugin.json", {"name": "tool", "version": "1.0.0", "skills": []})
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    wip = tmp_path / "tool/skills/wip/SKILL.md"
    wip.parent.mkdir(parents=True)
    wip.write_text("---\nname: wip\n---\n")
    monkeypatch.chdir(tmp_path)

    assert CliRunner().invoke(app, ["reconcile", "--dry-run", *args]).exit_code == exit_code


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


CATALOG = Path(".claude-plugin/marketplace.json")
REMOTE = {"source": "github", "repo": "example/remote"}


def commit_catalog(repo: Path, entries: dict[str, object], version: str = "1.0.0") -> str:
    """Commit a catalog of name → source; each string source gets a plugin manifest."""
    shutil.rmtree(repo / "plugins", ignore_errors=True)
    for name, source in entries.items():
        if isinstance(source, str):
            write_json(repo / source / ".claude-plugin/plugin.json", {"name": name, "version": "1.0.0"})
    plugins = [{"name": name, "source": source} for name, source in entries.items()]
    write_json(repo / CATALOG, {"metadata": {"version": version}, "plugins": plugins})
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "+".join(entries))
    return git(repo, "rev-parse", "HEAD").strip()


def catalog_version(repo: Path) -> str:
    return json.loads((repo / CATALOG).read_text())["metadata"]["version"]


@pytest.mark.parametrize(
    ("base_entries", "head_entries", "expected"),
    [
        pytest.param({"one": "./plugins/one", "two": "./plugins/two"}, {"one": "./plugins/one"}, "2.0.0", id="remove"),
        pytest.param({"one": "./plugins/one"}, {"one": "./plugins/one", "two": "./plugins/two"}, "1.1.0", id="add"),
        pytest.param({"one": "./plugins/one"}, {"one": "./plugins/moved/one"}, "1.0.1", id="move"),
        pytest.param({"one": "./plugins/one", "remote": REMOTE}, {"one": "./plugins/one"}, "2.0.0", id="remote"),
        pytest.param(
            {"one": "./plugins/one", "remote": REMOTE},
            {"one": "./plugins/one", "remote": {**REMOTE, "repo": "example/moved"}},
            "1.0.1",
            id="remote-source",
        ),
    ],
)
def test_marketplace_sync_bumps_for_membership_change_between_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    base_entries: dict[str, object],
    head_entries: dict[str, object],
    expected: str,
) -> None:
    initialize(tmp_path)
    base = commit_catalog(tmp_path, base_entries)
    head = commit_catalog(tmp_path, head_entries)
    monkeypatch.chdir(tmp_path)

    assert sync_native_marketplaces(base_ref=base, head_ref=head) == [CATALOG]
    assert catalog_version(tmp_path) == expected


def test_marketplace_membership_reads_head_ref_not_worktree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    initialize(tmp_path)
    base = commit_catalog(tmp_path, {"one": "./plugins/one", "two": "./plugins/two"})
    head = commit_catalog(tmp_path, {"one": "./plugins/one"})
    git(tmp_path, "checkout", "--quiet", base)
    monkeypatch.chdir(tmp_path)

    assert sync_native_marketplaces(base_ref=base, head_ref=head) == [CATALOG]
    assert catalog_version(tmp_path) == "2.0.0"


def test_marketplace_membership_runs_git_inside_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    initialize(repo)
    base = commit_catalog(repo, {"one": "./plugins/one", "two": "./plugins/two"})
    head = commit_catalog(repo, {"one": "./plugins/one"})
    (tmp_path / "outside").mkdir()
    monkeypatch.chdir(tmp_path / "outside")

    assert sync_native_marketplaces(repo, base_ref=base, head_ref=head) == [CATALOG]
    assert catalog_version(repo) == "2.0.0"
    assert git(repo, "diff", "--cached", "--name-only").split() == [CATALOG.as_posix()]


def test_marketplace_membership_keeps_a_bump_committed_at_head(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    initialize(tmp_path)
    base = commit_catalog(tmp_path, {"one": "./plugins/one"})
    head = commit_catalog(tmp_path, {"one": "./plugins/one", "two": "./plugins/two"}, version="1.1.0")
    monkeypatch.chdir(tmp_path)

    sync_native_marketplaces(base_ref=base, head_ref=head)
    assert catalog_version(tmp_path) == "1.1.0"


def test_marketplace_membership_bumps_a_worktree_behind_a_bumped_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize(tmp_path)
    base = commit_catalog(tmp_path, {"one": "./plugins/one"})
    head = commit_catalog(tmp_path, {"one": "./plugins/one", "two": "./plugins/two"}, version="1.1.0")
    git(tmp_path, "checkout", "--quiet", base)
    monkeypatch.chdir(tmp_path)

    sync_native_marketplaces(base_ref=base, head_ref=head)
    assert catalog_version(tmp_path) == "1.1.0"


def test_marketplace_membership_reads_each_revisions_version_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize(tmp_path)
    commit_catalog(tmp_path, {"one": "./plugins/one"})
    write_json(tmp_path / CATALOG, {"version": "1.0.0", "plugins": [{"name": "one", "source": "./plugins/one"}]})
    git(tmp_path, "commit", "--quiet", "-am", "top-level version")
    base = git(tmp_path, "rev-parse", "HEAD").strip()
    head = commit_catalog(tmp_path, {"one": "./plugins/one", "two": "./plugins/two"}, version="1.1.0")
    monkeypatch.chdir(tmp_path)

    sync_native_marketplaces(base_ref=base, head_ref=head)
    assert catalog_version(tmp_path) == "1.1.0"


def test_marketplace_membership_needs_a_base_ref(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    initialize(tmp_path)
    commit_catalog(tmp_path, {"one": "./plugins/one", "two": "./plugins/two"})
    commit_catalog(tmp_path, {"one": "./plugins/one"})
    monkeypatch.chdir(tmp_path)

    assert sync_native_marketplaces() == []
    assert catalog_version(tmp_path) == "1.0.0"


def test_marketplace_membership_fails_for_an_unreadable_base_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize(tmp_path)
    (tmp_path / CATALOG).parent.mkdir(parents=True)
    (tmp_path / CATALOG).write_text("{")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "--quiet", "-m", "broken")
    base = git(tmp_path, "rev-parse", "HEAD").strip()
    head = commit_catalog(tmp_path, {"one": "./plugins/one"})
    monkeypatch.chdir(tmp_path)

    with pytest.raises(RuntimeError, match="cannot parse"):
        sync_native_marketplaces(base_ref=base, head_ref=head)


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

    assert sync_staged_manifests() == {Path("tool"): "1.0.1"}
    assert json.loads(claude_manifest.read_text())["version"] == "1.0.1"
    assert json.loads(codex_manifest.read_text())["version"] == "1.0.1"


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


def test_staged_catalog_uses_the_staged_plugin_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    initialize(tmp_path)
    marketplace = tmp_path / ".claude-plugin/marketplace.json"
    write_json(marketplace, {"plugins": []})
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    manifest = tmp_path / "tool/.codex-plugin/plugin.json"
    write_json(manifest, {"name": "staged", "version": "1.0.0"})
    git(tmp_path, "add", ".")
    write_json(manifest, {"name": "unstaged", "version": "1.0.0"})
    monkeypatch.chdir(tmp_path)

    sync_staged_manifests()

    staged_catalog = json.loads(
        subprocess.check_output(["git", "show", ":.claude-plugin/marketplace.json"], cwd=tmp_path)
    )
    assert staged_catalog["plugins"] == [{"name": "staged", "source": "./tool"}]


def test_check_requires_a_bump_when_a_loose_manifest_moves_to_a_harness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize(tmp_path)
    loose = tmp_path / "tool/tool.plugin.json"
    write_json(loose, {"name": "tool", "version": "1.0.0"})
    readme = tmp_path / "tool/README.md"
    readme.write_text("before\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    base = git(tmp_path, "rev-parse", "HEAD").strip()
    git(tmp_path, "rm", "--quiet", loose.relative_to(tmp_path).as_posix())
    harness = tmp_path / "tool/.codex-plugin/plugin.json"
    write_json(harness, {"name": "tool", "version": "1.0.0"})
    readme.write_text("after\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "migrate")
    monkeypatch.chdir(tmp_path)

    assert check_native_version_bumps(base) == [Path("tool/.codex-plugin/plugin.json")]


def test_staged_non_skill_file_does_not_register_a_skill_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize(tmp_path)
    manifest = tmp_path / "tool/.codex-plugin/plugin.json"
    write_json(manifest, {"name": "tool", "version": "1.0.0", "skills": []})
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    note = tmp_path / "tool/skills/drafts/notes.txt"
    note.parent.mkdir(parents=True)
    note.write_text("draft\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    monkeypatch.chdir(tmp_path)

    assert sync_staged_manifests() == {Path("tool"): "1.0.1"}
    assert json.loads(manifest.read_text())["skills"] == []


PLUGIN = Path("plugins/x/.claude-plugin/plugin.json")
FIXTURE = Path("plugins/x/evals/files/hidden-styles/.claude-plugin/plugin.json")


def commit_plugin_with_fixture(repo: Path, fixture_data: dict[str, object] | None = None) -> None:
    initialize(repo)
    write_json(repo / PLUGIN, {"name": "x", "version": "1.0.0"})
    write_json(repo / FIXTURE, fixture_data or {"name": "fixture", "version": "0.1.0"})
    (repo / FIXTURE.parent.parent / "README.md").write_text("before\n")
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "base")


def version(repo: Path, path: Path) -> str:
    return json.loads((repo / path).read_text())["version"]


def test_audit_and_repair_treat_a_nested_fixture_manifest_as_plugin_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commit_plugin_with_fixture(tmp_path)
    (tmp_path / FIXTURE.parent.parent / "README.md").write_text("after\n")
    git(tmp_path, "commit", "--quiet", "-am", "edit fixture")
    monkeypatch.chdir(tmp_path)

    audit = CliRunner().invoke(app, ["audit"])
    assert json.loads(audit.stdout) == {"drifted_manifests": [PLUGIN.as_posix()]}
    assert CliRunner().invoke(app, ["repair"]).exit_code == 0
    assert (version(tmp_path, PLUGIN), version(tmp_path, FIXTURE)) == ("1.0.1", "0.1.0")


def test_staged_sync_bumps_the_enclosing_plugin_for_a_fixture_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commit_plugin_with_fixture(tmp_path)
    (tmp_path / FIXTURE.parent.parent / "README.md").write_text("after\n")
    git(tmp_path, "add", ".")
    monkeypatch.chdir(tmp_path)

    assert sync_staged_manifests(tmp_path) == {Path("plugins/x"): "1.0.1"}
    assert version(tmp_path, FIXTURE) == "0.1.0"


def test_check_requires_the_enclosing_plugin_bump_for_a_fixture_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commit_plugin_with_fixture(tmp_path)
    base = git(tmp_path, "rev-parse", "HEAD").strip()
    (tmp_path / FIXTURE.parent.parent / "README.md").write_text("after\n")
    git(tmp_path, "commit", "--quiet", "-am", "edit fixture")
    monkeypatch.chdir(tmp_path)

    assert check_native_version_bumps(base) == [PLUGIN]


def test_reconcile_leaves_a_nested_fixture_manifest_alone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    commit_plugin_with_fixture(tmp_path, {"name": "fixture", "version": "0.1.0", "skills": []})
    skill = tmp_path / FIXTURE.parent.parent / "skills/demo/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: demo\n---\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "fixture skill")
    monkeypatch.chdir(tmp_path)

    assert CliRunner().invoke(app, ["reconcile", "--dry-run"]).exit_code == 0


def test_marketplace_sync_leaves_a_fixture_catalog_alone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    commit_plugin_with_fixture(tmp_path)
    catalog = tmp_path / FIXTURE.parent.parent / ".claude-plugin/marketplace.json"
    write_json(catalog, {"version": "1.0.0", "plugins": [{"name": "fixture", "source": "./"}]})
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "fixture catalog")
    before = catalog.read_text()
    monkeypatch.chdir(tmp_path)

    assert sync_native_marketplaces() == []
    assert CliRunner().invoke(app, ["reconcile"]).exit_code == 0
    assert catalog.read_text() == before


def test_a_catalog_declared_nested_plugin_stays_a_plugin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    initialize(tmp_path)
    catalog = tmp_path / ".claude-plugin/marketplace.json"
    write_json(
        catalog,
        {
            "version": "1.0.0",
            "plugins": [
                {"name": "suite", "source": "./plugins/suite"},
                {"name": "sub", "source": "./plugins/suite/sub"},
            ],
        },
    )
    write_json(tmp_path / "plugins/suite/.claude-plugin/plugin.json", {"name": "suite", "version": "1.0.0"})
    sub = Path("plugins/suite/sub/.claude-plugin/plugin.json")
    write_json(tmp_path / sub, {"name": "sub", "version": "1.0.0"})
    (tmp_path / "plugins/suite/sub/README.md").write_text("before\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    before = catalog.read_text()
    (tmp_path / "plugins/suite/sub/README.md").write_text("after\n")
    git(tmp_path, "add", ".")
    monkeypatch.chdir(tmp_path)

    assert sync_staged_manifests(tmp_path) == {Path("plugins/suite/sub"): "1.0.1"}
    assert sync_native_marketplaces() == []
    assert catalog.read_text() == before


def test_fixtures_under_a_repository_root_plugin_still_count_as_manifests(tmp_path: Path) -> None:
    initialize(tmp_path)
    write_json(tmp_path / ".claude-plugin/plugin.json", {"name": "root", "version": "1.0.0"})
    fixture = Path("evals/files/case/.claude-plugin/plugin.json")
    write_json(tmp_path / fixture, {"name": "fixture", "version": "0.1.0"})
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")

    assert [manifest.path for manifest in discover_manifests(tmp_path)] == [Path(".claude-plugin/plugin.json"), fixture]


def test_check_keeps_requiring_a_nested_plugin_bump_when_head_adds_an_enclosing_plugin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize(tmp_path)
    inner = Path("suite/inner/.claude-plugin/plugin.json")
    write_json(tmp_path / inner, {"name": "inner", "version": "1.0.0"})
    (tmp_path / "suite/inner/README.md").write_text("before\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    base = git(tmp_path, "rev-parse", "HEAD").strip()
    write_json(tmp_path / "suite/.claude-plugin/plugin.json", {"name": "suite", "version": "1.0.0"})
    (tmp_path / "suite/inner/README.md").write_text("after\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "wrap in suite")
    monkeypatch.chdir(tmp_path)

    assert check_native_version_bumps(base) == [inner]


def test_staged_sync_ignores_an_untracked_enclosing_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    initialize(tmp_path)
    write_json(tmp_path / "suite/inner/.claude-plugin/plugin.json", {"name": "inner", "version": "1.0.0"})
    (tmp_path / "suite/inner/README.md").write_text("before\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    write_json(tmp_path / "suite/.claude-plugin/plugin.json", {"name": "suite", "version": "1.0.0"})
    (tmp_path / "suite/inner/README.md").write_text("after\n")
    git(tmp_path, "add", "suite/inner/README.md")
    monkeypatch.chdir(tmp_path)

    assert sync_staged_manifests(tmp_path) == {Path("suite/inner"): "1.0.1"}


def promote_fixture_with_edit(repo: Path) -> None:
    catalog = repo / ".claude-plugin/marketplace.json"
    write_json(catalog, {"version": "1.0.0", "plugins": [{"name": "x", "source": "./plugins/x"}]})
    commit_plugin_with_fixture(repo)
    data = json.loads(catalog.read_text())
    data["plugins"].append({"name": "fixture", "source": "./plugins/x/evals/files/hidden-styles"})
    write_json(catalog, data)
    (repo / FIXTURE.parent.parent / "README.md").write_text("after\n")
    git(repo, "add", ".")


def test_staged_sync_bumps_the_former_owner_when_a_fixture_is_promoted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    promote_fixture_with_edit(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert sync_staged_manifests(tmp_path) == {Path("plugins/x"): "1.0.1", FIXTURE.parent.parent: "0.1.1"}


def test_check_requires_the_former_owner_bump_when_a_fixture_is_promoted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    promote_fixture_with_edit(tmp_path)
    base = git(tmp_path, "rev-parse", "HEAD").strip()
    write_json(tmp_path / FIXTURE, {"name": "fixture", "version": "0.1.1"})
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "promote fixture")
    monkeypatch.chdir(tmp_path)

    assert check_native_version_bumps(base) == [PLUGIN]


def test_check_does_not_require_the_enclosing_bump_for_a_new_declared_nested_plugin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = tmp_path / ".claude-plugin/marketplace.json"
    write_json(catalog, {"version": "1.0.0", "plugins": [{"name": "x", "source": "./plugins/x"}]})
    initialize(tmp_path)
    write_json(tmp_path / PLUGIN, {"name": "x", "version": "1.0.0"})
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "base")
    base = git(tmp_path, "rev-parse", "HEAD").strip()
    data = json.loads(catalog.read_text())
    data["plugins"].append({"name": "sub", "source": "./plugins/x/sub"})
    write_json(catalog, data)
    write_json(tmp_path / "plugins/x/sub/.claude-plugin/plugin.json", {"name": "sub", "version": "0.1.0"})
    (tmp_path / "plugins/x/sub/README.md").write_text("new\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "add sub")
    monkeypatch.chdir(tmp_path)

    assert check_native_version_bumps(base) == []


def commit_two_declared_plugins(repo: Path) -> Path:
    catalog = repo / ".claude-plugin/marketplace.json"
    write_json(catalog, {"plugins": [{"name": "a", "source": "./a"}, {"name": "b", "source": "./b"}]})
    initialize(repo)
    for name in ("a", "b"):
        write_json(repo / name / ".claude-plugin/plugin.json", {"name": name, "version": "1.0.0"})
    (repo / "a/moved.txt").write_text("content\n")
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "base")
    return catalog


def test_check_requires_the_rename_source_owner_bump(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    commit_two_declared_plugins(tmp_path)
    base = git(tmp_path, "rev-parse", "HEAD").strip()
    git(tmp_path, "mv", "a/moved.txt", "b/moved.txt")
    write_json(tmp_path / "b/.claude-plugin/plugin.json", {"name": "b", "version": "1.0.1"})
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "move file to b")
    monkeypatch.chdir(tmp_path)

    assert check_native_version_bumps(base) == [Path("a/.claude-plugin/plugin.json")]


def test_staged_relocation_under_a_plugin_does_not_bump_the_enclosing_plugin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = commit_two_declared_plugins(tmp_path)
    git(tmp_path, "mv", "a", "b/a")
    write_json(catalog, {"plugins": [{"name": "a", "source": "./b/a"}, {"name": "b", "source": "./b"}]})
    git(tmp_path, "add", ".")
    monkeypatch.chdir(tmp_path)

    assert Path("b") not in sync_staged_manifests(tmp_path)
    assert version(tmp_path, Path("b/.claude-plugin/plugin.json")) == "1.0.0"
