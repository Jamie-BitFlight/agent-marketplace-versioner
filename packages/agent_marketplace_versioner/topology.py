"""Immutable repository topology used by version mutations."""

# Copyright (c) 2026 Jamie Nelson
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class InvalidTopologyConfigError(ValueError):
    """A typed configuration boundary violation."""

    def __init__(self, field: str, problem: str) -> None:
        self.field = field
        self.problem = problem
        super().__init__(f"invalid topology configuration for {field}: {problem}")


@dataclass(frozen=True, slots=True)
class VersionOwnerConfig:
    """Repository-relative source configuration for one version owner."""

    path: Path
    version_key_path: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RepositoryTopologyConfig:
    """Typed source configuration for repository version topology."""

    plugin_manifest: VersionOwnerConfig
    marketplace_version: VersionOwnerConfig | None
    generated_outputs: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class PluginManifestOwner:
    """The plugin manifest that owns a version value."""

    path: Path
    version_key_path: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MarketplaceVersionOwner:
    """The marketplace file that owns a plugin version value."""

    path: Path
    version_key_path: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GeneratedOutput:
    """A file regenerated after its version owners are updated."""

    path: Path


@dataclass(frozen=True, slots=True)
class RepositoryTopology:
    """The ordered version owners and generated outputs for one repository."""

    plugin_manifest: PluginManifestOwner
    marketplace_version: MarketplaceVersionOwner | None
    generated_outputs: tuple[GeneratedOutput, ...]

    @property
    def ordered_owners(self) -> tuple[PluginManifestOwner | MarketplaceVersionOwner, ...]:
        """Version owners in mutation order."""
        if self.marketplace_version is None:
            return (self.plugin_manifest,)
        return (self.plugin_manifest, self.marketplace_version)

    @property
    def mutation_paths(self) -> tuple[Path, ...]:
        """Owners followed by generated outputs in mutation order."""
        return (
            *tuple(owner.path for owner in self.ordered_owners),
            *(output.path for output in self.generated_outputs),
        )


def parse_repository_topology(config: RepositoryTopologyConfig) -> RepositoryTopology:
    """Parse typed source configuration into validated repository topology.

    Returns:
        The validated immutable repository topology.
    """
    plugin_manifest = _parse_version_owner(config.plugin_manifest, "plugin_manifest")
    marketplace_version = (
        None
        if config.marketplace_version is None
        else _parse_version_owner(config.marketplace_version, "marketplace_version")
    )
    return RepositoryTopology(
        plugin_manifest=PluginManifestOwner(
            path=plugin_manifest.path, version_key_path=plugin_manifest.version_key_path
        ),
        marketplace_version=(
            None
            if marketplace_version is None
            else MarketplaceVersionOwner(
                path=marketplace_version.path, version_key_path=marketplace_version.version_key_path
            )
        ),
        generated_outputs=tuple(
            GeneratedOutput(path=_parse_relative_path(path, "generated_outputs")) for path in config.generated_outputs
        ),
    )


def _parse_version_owner(config: VersionOwnerConfig, field: str) -> VersionOwnerConfig:
    """Validate one version owner configuration.

    Returns:
        The validated owner configuration.
    """
    if not config.version_key_path:
        raise InvalidTopologyConfigError(f"{field}.version_key_path", "must not be empty")
    return VersionOwnerConfig(
        path=_parse_relative_path(config.path, f"{field}.path"), version_key_path=config.version_key_path
    )


def _parse_relative_path(path: Path, field: str) -> Path:
    """Validate a path that must remain inside its repository.

    Returns:
        The validated repository-relative path.
    """
    if path.is_absolute():
        raise InvalidTopologyConfigError(field, "must be repository-relative")
    if ".." in path.parts:
        raise InvalidTopologyConfigError(field, "must not escape the repository")
    return path
