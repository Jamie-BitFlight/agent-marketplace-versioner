from __future__ import annotations

import subprocess
from pathlib import Path


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments], check=True, capture_output=True, text=True
    ).stdout.strip()


def test_validate_pre_merge_ignores_changed_gitignored_manifest(tmp_path: Path) -> None:
    # Given: an ignored conventional manifest that was explicitly tracked.
    from agent_marketplace_versioner.manifest_discovery import validate_pre_merge

    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.email", "tests@example.com")
    _git(repository, "config", "user.name", "Tests")
    (repository / ".gitignore").write_text("ignored.plugin.json\n")
    (repository / "ignored.plugin.json").write_text(' {"version":"1.0.0"}')
    _git(repository, "add", "-f", ".gitignore", "ignored.plugin.json")
    _git(repository, "commit", "-qm", "base")
    base = _git(repository, "rev-parse", "HEAD")
    (repository / "ignored.plugin.json").write_text('{"version":"1.0.0"}')
    _git(repository, "add", "-f", "ignored.plugin.json")
    _git(repository, "commit", "-qm", "change")
    head = _git(repository, "rev-parse", "HEAD")

    # When: the universal validator reads the committed refs.
    report = validate_pre_merge(repository, base, head)

    # Then: ignored conventional files never become version owners.
    assert report.is_valid
