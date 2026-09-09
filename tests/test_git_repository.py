# Copyright (c) 2026 Jamie Nelson
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(["git", "-C", str(repository), *arguments], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _committed_repository(tmp_path: Path) -> tuple[Path, str, str]:
    repository = tmp_path / "repository"
    repository.mkdir(parents=True)
    _git(repository, "init", "-q")
    _git(repository, "config", "user.email", "tests@example.com")
    _git(repository, "config", "user.name", "Tests")
    (repository / "version.json").write_text('{"version": "1.2.3"}\n')
    _git(repository, "add", "version.json")
    _git(repository, "commit", "-qm", "base")
    base = _git(repository, "rev-parse", "HEAD")
    (repository / "version.json").write_text('{"version": "1.2.4"}\n')
    (repository / "broken.json").write_text("not json\n")
    _git(repository, "add", "version.json", "broken.json")
    _git(repository, "commit", "-qm", "head")
    return repository, base, _git(repository, "rev-parse", "HEAD")


def test_list_name_status_changes_reads_caller_supplied_refs(tmp_path: Path) -> None:
    # Given: a real repository with two committed refs.
    from agent_marketplace_versioner.git_repository import NameStatusChange, list_name_status_changes

    repository, base, head = _committed_repository(tmp_path)

    # When: consumers list name-status changes across those refs.
    changes = list_name_status_changes(repository, base, head)

    # Then: Git's modified and added paths are represented without shell execution.
    assert changes == (
        NameStatusChange(status="A", path="broken.json", previous_path=None),
        NameStatusChange(status="M", path="version.json", previous_path=None),
    )


def test_read_json_file_at_ref_reads_and_parses_historical_json(tmp_path: Path) -> None:
    # Given: a real repository and its original commit ref.
    from agent_marketplace_versioner.git_repository import read_json_file_at_ref

    repository, base, _ = _committed_repository(tmp_path)

    # When: consumers read version JSON from the caller-supplied historical ref.
    document = read_json_file_at_ref(repository, base, Path("version.json"))

    # Then: parsed JSON reflects the historical version.
    assert document == {"version": "1.2.3"}


def test_read_json_file_at_ref_rejects_missing_and_malformed_files(tmp_path: Path) -> None:
    # Given: a real repository whose head includes malformed JSON.
    from agent_marketplace_versioner.git_repository import (
        GitFileNotFoundError,
        MalformedGitJsonError,
        read_json_file_at_ref,
    )

    repository, _, head = _committed_repository(tmp_path)

    # When: consumers read absent and malformed JSON files.
    with pytest.raises(GitFileNotFoundError):
        read_json_file_at_ref(repository, head, Path("missing.json"))
    with pytest.raises(MalformedGitJsonError):
        read_json_file_at_ref(repository, head, Path("broken.json"))

    # Then: each file failure is typed.


def test_git_repository_rejects_unknown_refs_and_non_repositories(tmp_path: Path) -> None:
    # Given: a real repository plus a non-repository directory.
    from agent_marketplace_versioner.git_repository import (
        GitCommandError,
        NotGitRepositoryError,
        list_name_status_changes,
        read_json_file_at_ref,
    )

    repository, base, _ = _committed_repository(tmp_path / "repository-root")
    non_repository = tmp_path / "not-a-repository"
    non_repository.mkdir()

    # When: consumers supply invalid repository and ref boundaries.
    with pytest.raises(GitCommandError):
        read_json_file_at_ref(repository, "missing-ref", Path("version.json"))
    with pytest.raises(NotGitRepositoryError):
        list_name_status_changes(non_repository, base, base)

    # Then: Git boundary failures are typed.


def test_list_name_status_changes_rejects_git_option_refs_without_writing_output(tmp_path: Path) -> None:
    # Given: a real repository and an external path named by a malicious ref.
    from agent_marketplace_versioner.git_repository import GitCommandError, list_name_status_changes

    repository, _, head = _committed_repository(tmp_path / "repository-root")
    outside_file = tmp_path / "outside.txt"

    # When: a caller supplies Git's output option where a base ref belongs.
    with pytest.raises(GitCommandError):
        list_name_status_changes(repository, f"--output={outside_file}", head)

    # Then: the Git option is rejected rather than creating the external output file.
    assert not outside_file.exists()
