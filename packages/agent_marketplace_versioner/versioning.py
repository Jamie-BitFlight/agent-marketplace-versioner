"""Pure semantic-version parsing and JSON version-key mutation."""

# Copyright (c) 2026 Jamie Nelson
from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Final, Self, TypeAlias

JsonValue: TypeAlias = str | int | float | bool | list["JsonValue"] | dict[str, "JsonValue"] | None
JsonObject: TypeAlias = dict[str, JsonValue]

_STRICT_SEMANTIC_VERSION: Final = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


class InvalidSemanticVersionError(ValueError):
    """A value that is not a strict three-part semantic version."""

    def __init__(self, value: str) -> None:
        self.value = value
        super().__init__(f"invalid semantic version: {value}")


class InvalidVersionKeyPathError(ValueError):
    """A configured JSON version-key path that cannot be traversed."""

    def __init__(self, field: str, problem: str) -> None:
        self.field = field
        self.problem = problem
        super().__init__(f"invalid version key path for {field}: {problem}")


@dataclass(frozen=True, slots=True, order=True)
class SemanticVersion:
    """A strict non-negative three-part semantic version."""

    major: int
    minor: int
    patch: int

    def __post_init__(self) -> None:
        """Reject negative semantic version components."""
        if min(self.major, self.minor, self.patch) < 0:
            raise InvalidSemanticVersionError(str(self))

    @classmethod
    def parse(cls, value: str) -> Self:
        """Parse a strict semantic version.

        Returns:
            The parsed semantic version.
        """
        match = _STRICT_SEMANTIC_VERSION.fullmatch(value)
        if match is None:
            raise InvalidSemanticVersionError(value)
        major, minor, patch = match.groups()
        return cls(major=int(major), minor=int(minor), patch=int(patch))

    def bump_patch(self) -> Self:
        """Return a copy with its patch number incremented.

        Returns:
            The patch-bumped semantic version.
        """
        return type(self)(major=self.major, minor=self.minor, patch=self.patch + 1)

    def __str__(self) -> str:
        """Render the strict three-part version value.

        Returns:
            The semantic version string.
        """
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True, slots=True)
class JsonVersionMutation:
    """The copied JSON object and semantic versions involved in one mutation."""

    document: JsonObject
    previous_version: SemanticVersion
    version: SemanticVersion


def mutate_json_version(
    document: Mapping[str, JsonValue], version_key_path: tuple[str, ...], version: SemanticVersion
) -> JsonVersionMutation:
    """Copy JSON-compatible data and replace the configured version value.

    Returns:
        The immutable result containing the copied document and version values.
    """
    if not version_key_path:
        raise InvalidVersionKeyPathError("version_key_path", "must not be empty")
    updated_document = deepcopy(dict(document))
    target = updated_document
    for key in version_key_path[:-1]:
        target = _next_json_object(target, key)
    key = version_key_path[-1]
    try:
        raw_previous_version = target[key]
    except KeyError as error:
        raise InvalidVersionKeyPathError("version_key_path", f"does not contain {key!r}") from error
    if not isinstance(raw_previous_version, str):
        raise InvalidVersionKeyPathError("version_key_path", f"{key!r} is not a version string")
    previous_version = SemanticVersion.parse(raw_previous_version)
    target[key] = str(version)
    return JsonVersionMutation(document=updated_document, previous_version=previous_version, version=version)


def _next_json_object(document: JsonObject, key: str) -> JsonObject:
    """Return a configured nested JSON object.

    Returns:
        The nested JSON object at the configured key.
    """
    try:
        value = document[key]
    except KeyError as error:
        raise InvalidVersionKeyPathError("version_key_path", f"does not contain {key!r}") from error
    if not isinstance(value, dict):
        raise InvalidVersionKeyPathError("version_key_path", f"{key!r} is not a JSON object")
    return value
