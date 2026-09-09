"""Read-only discovery and validation of conventional version manifests."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from agent_marketplace_versioner.git_repository import (
    GitFileNotFoundError,
    list_name_status_changes,
    read_json_file_at_ref,
)
from agent_marketplace_versioner.versioning import (
    InvalidSemanticVersionError,
    InvalidVersionKeyPathError,
    SemanticVersion,
    mutate_json_version,
)

_MANIFEST = re.compile(r"(?:^|/)\.[A-Za-z0-9_-]+-plugin/(?:plugin|marketplace)\.json$|(?:^|/)[^/]+\.plugin\.json$")
_GIT: Final = shutil.which("git") or "git"


@dataclass(frozen=True, slots=True)
class VersionBumpRequired:
    """A changed conventional manifest whose version did not increase."""

    path: Path
    base_version: SemanticVersion
    head_version: SemanticVersion


@dataclass(frozen=True, slots=True)
class ManifestValidationError:
    """A conventional manifest that cannot provide its declared version."""

    path: Path
    ref: str
    problem: str


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Immutable findings for conventional changed manifests."""

    errors: tuple[VersionBumpRequired | ManifestValidationError, ...]

    @property
    def is_valid(self) -> bool:
        """Whether the report has no findings."""
        return not self.errors


def validate_pre_merge(repository: Path, base_ref: str, head_ref: str) -> ValidationReport:
    """Validate changed conventional manifests between supplied refs.

    Returns:
        The immutable report.
    """
    changes = list_name_status_changes(repository, base_ref, head_ref)
    paths = sorted({
        Path(path)
        for change in changes
        for path in (change.path, change.previous_path)
        if path and _MANIFEST.search(path) and not _is_ignored(repository, path)
    })
    errors: list[VersionBumpRequired | ManifestValidationError] = []
    for path in paths:
        try:
            base = read_json_file_at_ref(repository, base_ref, path)
            head = read_json_file_at_ref(repository, head_ref, path)
        except GitFileNotFoundError:
            continue
        key = ("metadata", "version") if path.name == "marketplace.json" else ("version",)
        try:
            base_version = mutate_json_version(base, key, SemanticVersion(0, 0, 0)).previous_version
            head_version = mutate_json_version(head, key, SemanticVersion(0, 0, 0)).previous_version
        except (InvalidSemanticVersionError, InvalidVersionKeyPathError) as error:
            errors.append(ManifestValidationError(path, head_ref, str(error)))
            continue
        if head_version <= base_version:
            errors.append(VersionBumpRequired(path, base_version, head_version))
    return ValidationReport(tuple(errors))


def _is_ignored(repository: Path, path: str) -> bool:
    """Report whether Git ignore rules exclude a repository-relative path.

    Returns:
        Whether Git ignores the path.
    """
    return (
        subprocess.run(
            [_GIT, "-C", str(repository), "check-ignore", "--no-index", "-q", "--", path], check=False
        ).returncode
        == 0
    )
