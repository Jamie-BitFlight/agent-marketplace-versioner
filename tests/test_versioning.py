# Copyright (c) 2026 Jamie Nelson
from __future__ import annotations

import pytest


def test_semantic_version_parses_compares_and_bumps_patch() -> None:
    # Given: strict three-part semantic versions.
    from agent_marketplace_versioner.versioning import SemanticVersion

    version = SemanticVersion.parse("1.2.3")

    # When: consumers compare and patch-bump the parsed value.
    bumped = version.bump_patch()

    # Then: numeric ordering and patch reset behavior are available without I/O.
    assert version < SemanticVersion.parse("1.2.4")
    assert str(bumped) == "1.2.4"


@pytest.mark.parametrize("raw", ["1.2", "1.2.3.4", "-1.2.3", "01.2.3"])
def test_semantic_version_rejects_non_strict_three_part_values(raw: str) -> None:
    # Given: a malformed semantic version.
    from agent_marketplace_versioner.versioning import InvalidSemanticVersionError, SemanticVersion

    # When: consumers parse the value.
    with pytest.raises(InvalidSemanticVersionError):
        SemanticVersion.parse(raw)

    # Then: no partial or non-semantic version is accepted.


def test_semantic_version_rejects_negative_direct_construction() -> None:
    # Given: a direct semantic version value with a negative component.
    from agent_marketplace_versioner.versioning import InvalidSemanticVersionError, SemanticVersion

    # When: consumers construct the value without parsing text.
    with pytest.raises(InvalidSemanticVersionError):
        SemanticVersion(-1, 2, 3)

    # Then: the semantic-version invariant remains enforced.


def test_mutate_json_version_copies_input_and_changes_configured_key_path() -> None:
    # Given: nested JSON-compatible data with a version at its configured path.
    from agent_marketplace_versioner.versioning import SemanticVersion, mutate_json_version

    document = {"plugins": {"weather": {"version": "1.2.3", "label": "Weather"}}, "generated": False}

    # When: consumers mutate exactly the nested version key.
    result = mutate_json_version(
        document=document, version_key_path=("plugins", "weather", "version"), version=SemanticVersion.parse("1.2.4")
    )

    # Then: the original remains intact and only the requested value changes.
    assert result.previous_version == SemanticVersion.parse("1.2.3")
    assert result.document == {"plugins": {"weather": {"version": "1.2.4", "label": "Weather"}}, "generated": False}
    assert document == {"plugins": {"weather": {"version": "1.2.3", "label": "Weather"}}, "generated": False}


def test_mutate_json_version_rejects_empty_version_key_path() -> None:
    # Given: JSON-compatible data and an empty configured version-key path.
    from agent_marketplace_versioner.versioning import InvalidVersionKeyPathError, SemanticVersion, mutate_json_version

    # When: consumers attempt to mutate the path.
    with pytest.raises(InvalidVersionKeyPathError) as error:
        mutate_json_version(document={"version": "1.2.3"}, version_key_path=(), version=SemanticVersion.parse("1.2.4"))

    # Then: the key-path boundary is identified.
    assert error.value.field == "version_key_path"
