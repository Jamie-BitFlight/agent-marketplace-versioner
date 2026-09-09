#!/usr/bin/env python3
"""CI gate, retroactive audit, and repair for plugin.json version-bump drift.

Companion to ``auto_sync_manifests.py`` (the pre-commit hook). That hook only
inspects **staged** changes (``git diff --cached``), which is always empty in
a CI checkout -- nothing is ever staged there. A PR merged via GitHub's UI or
API never runs the local pre-commit hook either. Both gaps combined let PR
#3005 land a plugin content change with zero corresponding ``plugin.json``
version bump, and the marketplace cache -- keyed on that version -- kept
serving stale content indefinitely. See issue #3021.

Three modes:

``--check`` (CI gate, required check)
    Diffs *base-ref* against *head-ref* (a real base-vs-head tree comparison,
    not a staged-index comparison) and fails when any plugin with a changed
    file did not also raise its ``plugin.json`` version relative to
    *base-ref*. Newly added or fully deleted plugins are exempt -- there is
    no prior version to compare against. *head-ref* defaults to ``HEAD`` but
    should be passed explicitly (e.g. ``origin/$GITHUB_HEAD_REF``) on a
    GitHub Actions ``pull_request`` trigger, where the checked-out ``HEAD``
    is a synthetic merge commit rather than the PR's actual head commit.

``--audit`` (retroactive, report-only)
    Scans every plugin currently on disk, finds the most recent commit that
    changed its ``plugin.json`` version, and reports drift when any file
    under that plugin changed *after* that commit without a further bump.
    This is how a gap like #3021's -- already merged before this gate
    existed -- gets found without a manual ``git show`` investigation.

``--repair`` (post-merge, ``main``-only, authoritative)
    Same drift detection as ``--audit``, but patch-bumps each drifted
    plugin's ``plugin.json`` version in place instead of only reporting it.
    Run on ``main`` after every push -- this is the only correctness
    mechanism for the version-collision race (#3027): two branches deriving
    the same next version from an identical ``origin/main`` snapshot land on
    the same number, and this is what un-collides them after merge. See
    ``.claude/rules/plugin-development.md``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from agent_marketplace_versioner.auto_sync_manifests import (
    bump_version,
    extract_version_from_json,
    parse_plugin_path,
    read_ref_json,
    resolve_base,
    run_git_command,
)
from agent_marketplace_versioner.native_manifests import (
    NativeManifest,
    discover_manifests,
    manifest_kind,
    manifest_root,
    source_for_path,
)


def _commit_ref(ref: str) -> str:
    if ref.startswith("-"):
        msg = f"invalid Git ref: {ref}"
        raise ValueError(msg)
    resolved = run_git_command(["rev-parse", "--verify", "--quiet", "--end-of-options", f"{ref}^{{commit}}"])
    if not resolved:
        msg = f"invalid Git ref: {ref}"
        raise ValueError(msg)
    return resolved


def _git_paths(args: list[str]) -> list[Path]:
    git_path = shutil.which("git")
    if git_path is None:
        msg = "git executable not found"
        raise ValueError(msg)
    result = subprocess.run([git_path, *args], check=False, capture_output=True)
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(message or f"git {' '.join(args)} failed")
    return [Path(path.decode("utf-8", errors="surrogateescape")) for path in result.stdout.split(b"\0") if path]


def _native_manifests_at_ref(ref: str) -> list[NativeManifest]:
    git_path = shutil.which("git")
    if git_path is None:
        msg = "git executable not found"
        raise ValueError(msg)
    manifests: list[NativeManifest] = []
    paths = _git_paths(["ls-tree", "-r", "--name-only", "-z", ref])
    with tempfile.TemporaryDirectory(prefix="versioner-ignore-") as directory:
        snapshot = Path(directory)
        subprocess.run([git_path, "init", "--quiet", directory], check=True, capture_output=True)
        for path in paths:
            if path.name == ".gitignore":
                content = subprocess.check_output([git_path, "show", f"{ref}:{path.as_posix()}"])
                (snapshot / path).parent.mkdir(parents=True, exist_ok=True)
                (snapshot / path).write_bytes(content)
        for path in paths:
            kind = manifest_kind(path)
            if kind is None:
                continue
            (snapshot / path).parent.mkdir(parents=True, exist_ok=True)
            ignored = subprocess.run(
                [git_path, "-C", directory, "check-ignore", "--no-index", "-q", "--", path.as_posix()], check=False
            )
            if ignored.returncode not in {0, 1}:
                ignored.check_returncode()
            if ignored.returncode != 0:
                manifests.append(
                    NativeManifest(
                        path=path,
                        kind=kind,
                        version_key_path=("metadata", "version") if kind == "marketplace" else ("version",),
                    )
                )
    return manifests


def _plugin_identity_at_ref(ref: str, manifest: NativeManifest) -> tuple[str, str, str] | None:
    data = read_ref_json(ref, manifest.path)
    if not isinstance(data, dict) or not isinstance(name := data.get("name"), str):
        return None
    return name, manifest.path.name, manifest.path.parent.name


def _moved_manifests_missing_bumps(
    base: str,
    head: str,
    base_manifests: dict[Path, NativeManifest],
    head_manifests: dict[Path, NativeManifest],
    changed_roots: set[Path],
) -> list[Path]:
    base_only = [manifest for path, manifest in base_manifests.items() if path not in head_manifests]
    head_only = [manifest for path, manifest in head_manifests.items() if path not in base_manifests]
    missing: list[Path] = []
    for base_manifest in base_only:
        identity = _plugin_identity_at_ref(base, base_manifest)
        if identity is None:
            continue
        matches = [manifest for manifest in head_only if _plugin_identity_at_ref(head, manifest) == identity]
        if len(matches) != 1:
            continue
        head_manifest = matches[0]
        if manifest_root(head_manifest) not in changed_roots:
            continue
        base_version = extract_version_from_json(read_ref_json(base, base_manifest.path), ["version"])
        head_version = extract_version_from_json(read_ref_json(head, head_manifest.path), ["version"])
        if base_version is not None and (head_version is None or head_version <= base_version):
            missing.append(head_manifest.path)
    return missing


def check_native_version_bumps(base_ref: str, head_ref: str = "HEAD") -> list[Path]:
    """Return changed native manifests whose declared version did not increase.

    Returns:
        Repository-relative paths of existing manifests missing a version bump.
    """
    base = _commit_ref(base_ref)
    head = _commit_ref(head_ref)
    if not run_git_command(["merge-base", base, head]):
        msg = f"revisions have no merge base: {base_ref}, {head_ref}"
        raise ValueError(msg)
    base_manifests = {manifest.path: manifest for manifest in _native_manifests_at_ref(base)}
    head_manifests = {manifest.path: manifest for manifest in _native_manifests_at_ref(head)}
    manifests_by_path = base_manifests | head_manifests
    changed_paths = _git_paths(["diff", "--name-only", "-z", f"{base}...{head}"])
    changed_roots = {
        source_root
        for path in changed_paths
        if (source_root := source_for_path(list(manifests_by_path.values()), path)) is not None
    }
    missing: list[Path] = []
    for manifest in sorted(manifests_by_path.values(), key=lambda manifest: manifest.path.as_posix()):
        if manifest.path not in base_manifests or manifest.path not in head_manifests:
            continue
        if manifest.kind != "plugin" or manifest_root(manifest) not in changed_roots:
            continue
        base_version = extract_version_from_json(read_ref_json(base, manifest.path), ["version"])
        head_version = extract_version_from_json(read_ref_json(head, manifest.path), ["version"])
        if base_version is not None and (head_version is None or head_version <= base_version):
            missing.append(manifest.path)
    missing.extend(_moved_manifests_missing_bumps(base, head, base_manifests, head_manifests, changed_roots))
    return sorted(set(missing), key=lambda path: path.as_posix())


def plugins_with_diff(base_ref: str, head_ref: str = "HEAD") -> set[str]:
    """Return plugin directory names with any file changed between two refs.

    Args:
        base_ref: The git ref to diff against (e.g. a PR's merge-base with main).
        head_ref: The git ref representing the current state.

    Returns:
        Set of plugin directory names (the ``<name>`` in ``plugins/<name>/``)
        touched anywhere in the diff between the two refs.
    """
    output = run_git_command(["diff", "--name-only", f"{base_ref}...{head_ref}"])
    plugins: set[str] = set()
    for line in output.splitlines():
        parsed = parse_plugin_path(line.strip())
        if parsed:
            plugins.add(parsed["plugin"])
    return plugins


def check_version_bumps(base_ref: str, head_ref: str = "HEAD") -> list[str]:
    """Find plugins whose files changed between refs without a version bump.

    Args:
        base_ref: The git ref to diff against (e.g. the PR's merge-base with main).
        head_ref: The git ref representing the proposed merge state.

    Returns:
        Sorted list of plugin directory names that changed but whose
        ``plugin.json`` version at *head_ref* is not strictly greater than at
        *base_ref*. Plugins created or deleted within the diff are excluded --
        there is no prior version to compare against.
    """
    return [path.as_posix() for path in check_native_version_bumps(base_ref, head_ref)]


def find_last_version_bump_commit(plugin_json_relpath: str) -> str | None:
    """Find the most recent commit that changed plugin.json's version field.

    Args:
        plugin_json_relpath: Path to plugin.json, relative to the repo root.

    Returns:
        The commit SHA of the most recent version change. When the version was
        set once at file creation and never changed since, the creation
        (root) commit is returned -- it is still a valid drift baseline.
        Returns None only when plugin.json has no commit history at all.
    """
    commits = run_git_command(["log", "--format=%H", "--", plugin_json_relpath]).splitlines()
    for commit in commits:
        version = extract_version_from_json(read_ref_json(commit, plugin_json_relpath), ["version"])
        if version is None:
            continue

        # --verify --quiet: a root commit has no parent, so this exits non-zero --
        # --quiet suppresses git's "fatal: ... unknown revision" stderr for that
        # expected case (run_git_command forwards stderr on any non-zero exit).
        parent_sha = run_git_command(["rev-parse", "--verify", "--quiet", f"{commit}^"])
        if not parent_sha:
            return commit  # root commit -- version was set here, counts as the bump point

        parent_version = extract_version_from_json(read_ref_json(parent_sha, plugin_json_relpath), ["version"])
        if parent_version is None or version != parent_version:
            return commit

    return None


def audit_version_drift(plugins_root: Path) -> list[str]:
    """Find plugins whose content changed after their last recorded version bump.

    Assumes the current working directory is the repository root (true for
    every caller in this script -- git subcommands here rely on it). Plugin
    paths are always rebuilt as ``plugins/<name>/...`` strings rather than
    reused from *plugins_root* directly: ``git show ref:path`` -- unlike
    ``git log -- path`` or ``git diff -- path`` -- requires a repo-root-relative
    path and silently returns nothing for a filesystem-absolute one, so an
    absolute *plugins_root* (e.g. a pytest ``tmp_path`` fixture) would
    otherwise make every plugin look falsely un-bumped.

    Args:
        plugins_root: Path to the plugins/ directory (relative or absolute --
            only used to list plugin directory names, never passed to git).

    Returns:
        Sorted list of plugin directory names exhibiting drift -- i.e. a file
        under ``plugins/<name>/`` changed after the plugin's last version-bump
        commit, with no further bump since.
    """
    drifted: list[str] = []
    for plugin_dir in sorted(plugins_root.iterdir()):
        if not plugin_dir.is_dir():
            continue
        plugin_json_path = plugin_dir / ".claude-plugin" / "plugin.json"
        if not plugin_json_path.exists():
            continue

        plugin_name = plugin_dir.name
        rel_plugin_json = f"plugins/{plugin_name}/.claude-plugin/plugin.json"
        last_bump = find_last_version_bump_commit(rel_plugin_json)
        if last_bump is None:
            continue  # plugin.json has no commit history -- nothing to diff against

        changed = run_git_command(["diff", "--name-only", last_bump, "HEAD", "--", f"plugins/{plugin_name}"])
        if changed.strip():
            drifted.append(plugin_name)

    return drifted


def repair_plugin_version(plugin_dir: Path) -> tuple[str, str] | None:
    """Bump a drifted plugin's version by one patch and write it to disk.

    Args:
        plugin_dir: Path to the plugin's directory (``plugins/<name>``).

    Returns:
        ``(old_version, new_version)`` on success, or None when
        ``plugin.json`` is missing, unreadable, malformed, or lacks a
        well-formed ``major.minor.patch`` string ``version`` field.
    """
    plugin_json_path = plugin_dir / ".claude-plugin" / "plugin.json"
    try:
        data = json.loads(plugin_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    # extract_version_from_json validates well-formed major.minor.patch, not just str-ness --
    # reused here (instead of a bare isinstance check) so a malformed version like "abc" is
    # rejected as unrepairable rather than silently coerced by bump_version to "0.1.0".
    if extract_version_from_json(data, ["version"]) is None:
        return None
    old_version = data["version"]
    new_version = bump_version(old_version, "patch")
    data["version"] = new_version
    # Same 2-space-indent + LF-trailing-newline format as auto_sync_manifests.py's
    # writers (write_bytes avoids Windows CRLF conversion in text mode).
    plugin_json_path.write_bytes((json.dumps(data, indent=2) + "\n").encode("utf-8"))
    return old_version, new_version


def _run_repair() -> int:
    """Bump the version of every plugin whose content drifted past its last bump.

    Reuses ``audit_version_drift`` for detection -- the same predicate that
    closes both the #3027 collision case and the #3021 no-bump case (see
    ``plan/architect-plugin-version-bump-race.md``). Always a patch bump:
    re-deriving minor/major from the merge diff is unnecessary for the
    invariant this enforces (monotonic, cache-invalidating version).

    Returns:
        0 when every drifted plugin was repaired (including the no-drift
        case, which is idempotent); non-zero when the ``plugins/`` directory
        is missing, or when any drifted plugin could not be repaired (e.g.
        its ``plugin.json`` is missing, unreadable, malformed, or lacks a
        well-formed string ``version``) -- that plugin remains drifted and
        must not be reported as a successful repair.
    """
    repaired: list[dict[str, str]] = []
    failed: list[str] = []
    for path in _native_drifted_manifests():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            failed.append(path.as_posix())
            continue
        if not isinstance(data, dict) or extract_version_from_json(data, ["version"]) is None:
            failed.append(path.as_posix())
            continue
        old_version = data["version"]
        new_version = bump_version(old_version, "patch")
        data["version"] = new_version
        path.write_bytes((json.dumps(data, indent=2) + "\n").encode("utf-8"))
        repaired.append({"manifest": path.as_posix(), "old_version": old_version, "new_version": new_version})

    print(json.dumps({"repaired": repaired, "failed": failed}))
    return 1 if failed else 0


def _run_check(base_ref_arg: str | None, head_ref_arg: str | None = None) -> int:
    """Run the CI version-bump gate and print the result.

    Args:
        base_ref_arg: Explicit base ref to diff against, or None to
            auto-resolve via ``resolve_base()`` (``origin/main`` -> ``main``).
        head_ref_arg: Explicit head ref to diff against, or None to use the
            checked-out working tree's ``HEAD``. On a GitHub Actions
            ``pull_request`` trigger, ``actions/checkout`` checks out a
            synthetic merge commit (base tip merged with the PR head) by
            default, not the PR's actual head commit -- diffing against that
            ``HEAD`` mixes in base-only changes that landed after the PR
            branch diverged. Callers on that trigger must pass the PR's real
            head ref explicitly (e.g. ``origin/${GITHUB_HEAD_REF}``, or
            ``github.event.pull_request.head.sha``).

    Returns:
        0 when every changed plugin bumped its version (or no base ref is
        needed because nothing changed); 1 when a bump is missing or no base
        ref is resolvable.
    """
    base_ref = base_ref_arg or resolve_base()
    if base_ref is None:
        sys.stderr.write("Error: no base ref resolvable (origin/main or main) -- pass --base-ref explicitly\n")
        return 1

    try:
        missing = check_version_bumps(base_ref, head_ref_arg or "HEAD")
    except ValueError as error:
        sys.stderr.write(f"Error: {error}\n")
        return 1
    if not missing:
        print(f"OK: all changed native manifests bumped their version relative to {base_ref}")
        return 0

    sys.stderr.write("The following changed native manifests did not bump their version:\n")
    for path in missing:
        sys.stderr.write(f"  - {path}\n")
    return 1


def _native_drifted_manifests() -> list[Path]:
    drifted: list[Path] = []
    for manifest in discover_manifests():
        if manifest.kind != "plugin":
            continue
        last_bump = find_last_version_bump_commit(manifest.path.as_posix())
        if last_bump is None:
            continue
        source_root = manifest_root(manifest).as_posix()
        if run_git_command(["diff", "--name-only", last_bump, "HEAD", "--", source_root]):
            drifted.append(manifest.path)
    return drifted


def _run_audit() -> int:
    """Run the retroactive drift audit and print results as compact JSON.

    This tool has no human operator -- every caller is an agent or CI script
    (see AGENTS.md "CLI and script output -- agent-only, never human-facing").
    JSON output lets a caller parse the result directly instead of scraping
    prose.

    Returns:
        0 always -- this is a report-only mode (issue #3021 acceptance
        criterion #2 scopes retroactive repair as report-only so it never
        blocks unrelated PRs); non-zero is reserved for genuine tool errors.
    """
    print(json.dumps({"drifted_manifests": [path.as_posix() for path in _native_drifted_manifests()]}))
    return 0


def main() -> int:
    """Dispatch to the requested mode.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="CI gate: fail if a changed plugin's version was not bumped")
    mode.add_argument(
        "--audit", action="store_true", help="Report plugins whose content changed after their last version bump"
    )
    mode.add_argument(
        "--repair", action="store_true", help="Patch-bump plugins whose content changed after their last version bump"
    )
    parser.add_argument("--base-ref", default=None, help="Explicit base ref for --check (default: resolve_base())")
    parser.add_argument(
        "--head-ref",
        default=None,
        help=(
            "Explicit head ref for --check (default: HEAD). Required on a GitHub Actions "
            "pull_request trigger, since actions/checkout's default HEAD there is a synthetic "
            "merge commit, not the PR's real head -- pass origin/$GITHUB_HEAD_REF instead."
        ),
    )
    args = parser.parse_args()

    if args.check:
        return _run_check(args.base_ref, args.head_ref)
    if args.repair:
        return _run_repair()
    return _run_audit()


if __name__ == "__main__":
    sys.exit(main())
