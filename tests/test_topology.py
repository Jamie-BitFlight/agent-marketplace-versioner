# Copyright (c) 2026 Jamie Nelson
from __future__ import annotations

from pathlib import Path

import pytest


def test_repository_topology_orders_version_owners_before_generated_outputs() -> None:
    # Given: a repository with plugin and marketplace version owners.
    from agent_marketplace_versioner.topology import (
        GeneratedOutput,
        MarketplaceVersionOwner,
        PluginManifestOwner,
        RepositoryTopology,
    )

    plugin_manifest = PluginManifestOwner(
        path=Path("plugins/weather/.codex-plugin/plugin.json"), version_key_path=("version",)
    )
    marketplace = MarketplaceVersionOwner(
        path=Path(".agents/plugins/marketplace.json"), version_key_path=("plugins", "weather", "version")
    )
    generated = GeneratedOutput(path=Path("dist/weather/plugin.json"))
    topology = RepositoryTopology(
        plugin_manifest=plugin_manifest, marketplace_version=marketplace, generated_outputs=(generated,)
    )

    # When: consumers request the ordered mutation paths.
    mutation_paths = topology.mutation_paths

    # Then: source version owners are updated before generated output.
    assert topology.ordered_owners == (plugin_manifest, marketplace)
    assert mutation_paths == (plugin_manifest.path, marketplace.path, generated.path)


def test_repository_topology_omits_an_absent_marketplace_owner() -> None:
    # Given: a repository without a marketplace version owner.
    from agent_marketplace_versioner.topology import PluginManifestOwner, RepositoryTopology

    plugin_manifest = PluginManifestOwner(path=Path("plugin.json"), version_key_path=("version",))
    topology = RepositoryTopology(plugin_manifest=plugin_manifest, marketplace_version=None, generated_outputs=())

    # When: consumers request the owners to mutate.
    owners = topology.ordered_owners

    # Then: only the plugin manifest is an owner.
    assert owners == (plugin_manifest,)


def test_parse_repository_topology_builds_existing_model_from_typed_config() -> None:
    # Given: typed repository-relative configuration.
    from agent_marketplace_versioner.topology import (
        RepositoryTopologyConfig,
        VersionOwnerConfig,
        parse_repository_topology,
    )

    config = RepositoryTopologyConfig(
        plugin_manifest=VersionOwnerConfig(Path("plugin.json"), ("version",)),
        marketplace_version=VersionOwnerConfig(Path("marketplace.json"), ("plugins", "weather", "version")),
        generated_outputs=(Path("dist/plugin.json"),),
    )

    # When: the configuration is parsed.
    topology = parse_repository_topology(config)

    # Then: it becomes the existing immutable topology values.
    assert topology.mutation_paths == (Path("plugin.json"), Path("marketplace.json"), Path("dist/plugin.json"))


def test_parse_repository_topology_rejects_empty_version_key_path() -> None:
    # Given: configuration with no plugin version-key path.
    from agent_marketplace_versioner.topology import (
        InvalidTopologyConfigError,
        RepositoryTopologyConfig,
        VersionOwnerConfig,
        parse_repository_topology,
    )

    config = RepositoryTopologyConfig(
        plugin_manifest=VersionOwnerConfig(Path("plugin.json"), ()), marketplace_version=None, generated_outputs=()
    )

    # When: the configuration is parsed.
    with pytest.raises(InvalidTopologyConfigError) as error:
        parse_repository_topology(config)

    # Then: the invalid version-key boundary is identified.
    assert error.value.field == "plugin_manifest.version_key_path"


def test_parse_repository_topology_rejects_absolute_repository_path() -> None:
    # Given: configuration with an absolute plugin path.
    from agent_marketplace_versioner.topology import (
        InvalidTopologyConfigError,
        RepositoryTopologyConfig,
        VersionOwnerConfig,
        parse_repository_topology,
    )

    config = RepositoryTopologyConfig(
        plugin_manifest=VersionOwnerConfig(Path("/plugin.json"), ("version",)),
        marketplace_version=None,
        generated_outputs=(),
    )

    # When: the configuration is parsed.
    with pytest.raises(InvalidTopologyConfigError) as error:
        parse_repository_topology(config)

    # Then: the absolute path boundary is identified.
    assert error.value.field == "plugin_manifest.path"


def test_parse_repository_topology_rejects_parent_escaping_repository_path() -> None:
    # Given: configuration whose plugin path escapes the repository.
    from agent_marketplace_versioner.topology import (
        InvalidTopologyConfigError,
        RepositoryTopologyConfig,
        VersionOwnerConfig,
        parse_repository_topology,
    )

    config = RepositoryTopologyConfig(
        plugin_manifest=VersionOwnerConfig(Path("../escape.json"), ("version",)),
        marketplace_version=None,
        generated_outputs=(),
    )

    # When: the configuration is parsed.
    with pytest.raises(InvalidTopologyConfigError) as error:
        parse_repository_topology(config)

    # Then: the parent path boundary is identified.
    assert error.value.field == "plugin_manifest.path"
