from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from agent_marketplace_versioner.auto_sync_manifests import sync_native_marketplaces, sync_staged_manifests
from agent_marketplace_versioner.check_plugin_version_bump import check_native_version_bumps
from agent_marketplace_versioner.native_manifests import discover_manifests, marketplace_sources


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data) + "\n", encoding="utf-8")


def test_discovery_finds_native_manifests_anywhere_but_excludes_gitignored_files(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    _write_json(
        tmp_path / "catalog" / ".acme-plugin" / "marketplace.json",
        {"metadata": {"version": "1.0.0"}, "plugins": [{"name": "tool", "source": "./components/tool"}]},
    )
    _write_json(tmp_path / "catalog" / "components" / "tool" / ".codex-plugin" / "plugin.json", {"version": "1.0.0"})
    _write_json(tmp_path / "root.plugin.json", {"version": "1.0.0"})
    _write_json(tmp_path / "ignored" / ".codex-plugin" / "plugin.json", {"version": "1.0.0"})
    _git(tmp_path, "add", ".")
    _git(tmp_path, "add", "-f", "ignored/.codex-plugin/plugin.json")
    _git(tmp_path, "commit", "-m", "initial")

    manifests = discover_manifests(tmp_path)

    assert [manifest.path.as_posix() for manifest in manifests] == [
        "catalog/.acme-plugin/marketplace.json",
        "catalog/components/tool/.codex-plugin/plugin.json",
        "root.plugin.json",
    ]
    assert marketplace_sources(manifests[0], tmp_path) == [Path("catalog/components/tool")]


def test_discovery_handles_flat_and_agents_marketplaces_without_treating_remote_sources_as_local(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    _write_json(
        tmp_path / "catalog" / ".agents" / "plugins" / "marketplace.json",
        {"version": "1.0.0", "plugins": [{"source": "./local"}, {"source": {"host": "example.invalid"}}]},
    )
    _write_json(tmp_path / "catalog" / "local" / "name-plugin.json", {"version": "1.0.0"})
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")

    manifests = discover_manifests(tmp_path)

    marketplace = next(manifest for manifest in manifests if manifest.kind == "marketplace")
    assert marketplace.path == Path("catalog/.agents/plugins/marketplace.json")
    assert marketplace.version_key_path == ("version",)
    assert Path("catalog/local/name-plugin.json") in [manifest.path for manifest in manifests]
    assert marketplace_sources(marketplace, tmp_path) == [Path("catalog/local")]


def test_staged_content_change_bumps_all_native_manifests_at_an_arbitrary_root(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    plugin_root = tmp_path / "catalog" / "components" / "tool"
    for directory in (".codex-plugin", ".cursor-plugin"):
        _write_json(plugin_root / directory / "plugin.json", {"name": "tool", "version": "1.0.0"})
    (plugin_root / "README.md").write_text("before\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")
    (plugin_root / "README.md").write_text("after\n", encoding="utf-8")
    _git(tmp_path, "add", "catalog/components/tool/README.md")
    monkeypatch.chdir(tmp_path)

    updated = sync_staged_manifests(tmp_path)

    assert updated == {Path("catalog/components/tool"): "1.0.1"}
    for directory in (".codex-plugin", ".cursor-plugin"):
        assert json.loads((plugin_root / directory / "plugin.json").read_text(encoding="utf-8"))["version"] == "1.0.1"


def test_marketplace_reconciliation_preserves_remote_entries_and_updates_local_siblings(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    marketplace = tmp_path / "catalog" / ".acme-plugin" / "marketplace.json"
    _write_json(
        marketplace,
        {
            "metadata": {"version": "1.0.0"},
            "plugins": [
                {"name": "kept", "source": "./components/kept"},
                {"name": "removed", "source": "./components/removed"},
                {"name": "remote", "source": "github:example/remote"},
            ],
        },
    )
    _write_json(
        tmp_path / "catalog" / "components" / "kept" / ".codex-plugin" / "plugin.json",
        {"name": "kept", "version": "1.0.0"},
    )
    _write_json(
        tmp_path / "catalog" / "components" / "added" / ".codex-plugin" / "plugin.json",
        {"name": "added", "version": "1.0.0"},
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")
    monkeypatch.chdir(tmp_path)

    updated = sync_native_marketplaces(tmp_path)

    assert updated == [Path("catalog/.acme-plugin/marketplace.json")]
    data = json.loads(marketplace.read_text(encoding="utf-8"))
    assert data["metadata"]["version"] == "2.0.0"
    assert data["plugins"] == [
        {"name": "kept", "source": "./components/kept"},
        {"name": "remote", "source": "github:example/remote"},
        {"name": "added", "source": "./components/added"},
    ]


def test_version_check_requires_a_bump_for_changed_manifest_under_an_arbitrary_root(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    plugin_root = tmp_path / "catalog" / "components" / "tool"
    manifest = plugin_root / ".codex-plugin" / "plugin.json"
    _write_json(manifest, {"version": "1.0.0"})
    (plugin_root / "README.md").write_text("before\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    (plugin_root / "README.md").write_text("after\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "content change")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    monkeypatch.chdir(tmp_path)

    assert check_native_version_bumps(base, head) == [Path("catalog/components/tool/.codex-plugin/plugin.json")]

    _write_json(manifest, {"version": "1.0.1"})
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "version bump")
    bumped_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    assert check_native_version_bumps(base, bumped_head) == []
