"""Read-only Git repository access for version metadata."""

# Copyright (c) 2026 Jamie Nelson
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

JsonValue: TypeAlias = str | int | float | bool | list["JsonValue"] | dict[str, "JsonValue"] | None
JsonObject: TypeAlias = dict[str, JsonValue]


class NotGitRepositoryError(ValueError):
    """A path that is not a usable Git working tree."""

    def __init__(self, repository: Path) -> None:
        self.repository = repository
        super().__init__(f"not a Git repository: {repository}")


class GitCommandError(RuntimeError):
    """A Git command that failed outside a missing file lookup."""

    def __init__(self, repository: Path, arguments: tuple[str, ...], stderr: str) -> None:
        self.repository = repository
        self.arguments = arguments
        self.stderr = stderr
        super().__init__(f"Git command failed for {repository}: {' '.join(arguments)}")


class GitFileNotFoundError(FileNotFoundError):
    """A repository-relative file that does not exist at a verified ref."""

    def __init__(self, ref: str, path: Path) -> None:
        self.ref = ref
        self.path = path
        super().__init__(f"Git file not found at {ref}: {path}")


class MalformedGitJsonError(ValueError):
    """A JSON file read from Git that cannot be parsed as an object."""

    def __init__(self, ref: str, path: Path) -> None:
        self.ref = ref
        self.path = path
        super().__init__(f"malformed JSON at {ref}: {path}")


class InvalidRepositoryPathError(ValueError):
    """A path that is not repository-relative."""

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"path must be repository-relative: {path}")


@dataclass(frozen=True, slots=True)
class NameStatusChange:
    """One name-status path change reported by Git."""

    status: str
    path: str
    previous_path: str | None


def list_name_status_changes(repository: Path, base_ref: str, head_ref: str) -> tuple[NameStatusChange, ...]:
    """List Git name-status changes between caller-supplied refs.

    Returns:
        The immutable sequence of changed paths.
    """
    _ensure_git_repository(repository)
    base_commit = _ensure_ref(repository, base_ref)
    head_commit = _ensure_ref(repository, head_ref)
    result = _run_git(repository, "diff", "--name-status", "-z", base_commit, head_commit, "--")
    if result.returncode != 0:
        raise _git_command_error(repository, ("diff", "--name-status", "-z", base_commit, head_commit, "--"), result)
    return _parse_name_status(result.stdout)


def read_json_file_at_ref(repository: Path, ref: str, path: Path) -> JsonObject:
    """Read and parse a repository-relative JSON object at a supplied ref.

    Returns:
        The parsed JSON object.
    """
    _ensure_git_repository(repository)
    _ensure_repository_path(path)
    commit = _ensure_ref(repository, ref)
    result = _run_git(repository, "show", f"{commit}:{path.as_posix()}")
    if result.returncode != 0:
        raise GitFileNotFoundError(ref, path)
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise MalformedGitJsonError(ref, path) from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise MalformedGitJsonError(ref, path)
    return value


def _ensure_git_repository(repository: Path) -> None:
    """Raise a typed error unless the path is a Git working tree."""
    result = _run_git(repository, "rev-parse", "--is-inside-work-tree")
    if result.returncode != 0 or result.stdout.strip() != "true":
        raise NotGitRepositoryError(repository)


def _ensure_ref(repository: Path, ref: str) -> str:
    """Resolve a supplied ref to a safe commit object ID.

    Returns:
        The verified commit object ID.
    """
    arguments = ("rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")
    result = _run_git(repository, *arguments)
    if result.returncode != 0:
        raise _git_command_error(repository, arguments, result)
    return result.stdout.strip()


def _ensure_repository_path(path: Path) -> None:
    """Raise a typed error for paths that can escape a repository."""
    if path.is_absolute() or ".." in path.parts:
        raise InvalidRepositoryPathError(path)


def _run_git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run Git with an argument list and without a shell.

    Returns:
        The completed Git process.
    """
    git_executable = shutil.which("git")
    if git_executable is None:
        raise GitCommandError(repository, arguments, "git executable not found")
    try:
        return subprocess.run(
            [git_executable, "-C", str(repository), *arguments], check=False, capture_output=True, text=True
        )
    except OSError as error:
        raise GitCommandError(repository, arguments, str(error)) from error


def _git_command_error(
    repository: Path, arguments: tuple[str, ...], result: subprocess.CompletedProcess[str]
) -> GitCommandError:
    """Construct a typed Git command error from a completed process.

    Returns:
        The typed Git command error.
    """
    return GitCommandError(repository, arguments, result.stderr)


def _parse_name_status(output: str) -> tuple[NameStatusChange, ...]:
    """Parse null-delimited Git name-status output.

    Returns:
        The parsed name-status changes.
    """
    fields = tuple(field for field in output.split("\0") if field)
    changes: list[NameStatusChange] = []
    index = 0
    while index < len(fields):
        status = fields[index]
        index += 1
        previous_path = None
        if status.startswith(("C", "R")):
            previous_path = fields[index]
            index += 1
        path = fields[index]
        index += 1
        changes.append(NameStatusChange(status=status, path=path, previous_path=previous_path))
    return tuple(changes)
