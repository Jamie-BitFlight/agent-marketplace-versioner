from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Final

import pytest
from tests.integration_consumer import git, prepare, stage

ROOT: Final = Path(__file__).resolve().parents[1]


@pytest.mark.slow
@pytest.mark.parametrize("runner", ["prek", "pre-commit"])
def test_distributed_hook_installs_syncs_and_is_idempotent(tmp_path: Path, runner: str) -> None:
    hook_repo = tmp_path / "hook"
    subprocess.run(["git", "clone", "--quiet", "--local", str(ROOT), str(hook_repo)], check=True)
    shutil.copyfile(ROOT / ".pre-commit-hooks.yaml", hook_repo / ".pre-commit-hooks.yaml")
    git(hook_repo, "config", "user.name", "Integration Test")
    git(hook_repo, "config", "user.email", "test@example.invalid")
    git(hook_repo, "add", ".pre-commit-hooks.yaml")
    git(hook_repo, "-c", "core.hooksPath=/dev/null", "commit", "--quiet", "--allow-empty", "-m", "hook fixture")
    consumer = tmp_path / "consumer with spaces"
    prepare(consumer)
    (consumer / ".pre-commit-config.yaml").write_text(
        f"repos:\n  - repo: {hook_repo.as_uri()}\n    rev: {git(hook_repo, 'rev-parse', 'HEAD').strip()}\n"
        "    hooks:\n      - id: agent-marketplace-versioner\n",
        encoding="utf-8",
    )
    git(consumer, "add", ".pre-commit-config.yaml")
    git(consumer, "commit", "--quiet", "-m", "configure hook")
    stage(consumer)
    env = {**os.environ, "PREK_HOME": str(tmp_path / "prek"), "PRE_COMMIT_HOME": str(tmp_path / "pre-commit")}
    command = ["uv", "tool", "run", "--from", runner, runner]

    subprocess.run([*command, "install", "--install-hooks"], cwd=consumer, env=env, check=True, capture_output=True)
    first = subprocess.run([*command, "run"], cwd=consumer, env=env, check=False, capture_output=True, text=True)

    assert first.returncode == 0, first.stdout + first.stderr
    assert json.loads((consumer / "catalog/tool/.codex-plugin/plugin.json").read_text())["version"] == "1.0.1"
    staged = git(consumer, "diff", "--cached")
    second = subprocess.run([*command, "run"], cwd=consumer, env=env, check=False, capture_output=True, text=True)
    assert second.returncode == 0, second.stdout + second.stderr
    assert git(consumer, "diff", "--cached") == staged
    subprocess.run(["git", "commit", "--quiet", "-m", "versioned change"], cwd=consumer, env=env, check=True)
    assert git(consumer, "status", "--porcelain") == ""


@pytest.mark.slow
@pytest.mark.parametrize("runner", ["prek", "pre-commit"])
def test_moving_hook_tag_refreshes_after_cache_clean_and_reinstall(tmp_path: Path, runner: str) -> None:
    hook_repo = tmp_path / "hook"
    hook_repo.mkdir()
    git(hook_repo, "init", "--quiet")
    git(hook_repo, "config", "user.name", "Integration Test")
    git(hook_repo, "config", "user.email", "test@example.invalid")
    (hook_repo / ".pre-commit-hooks.yaml").write_text(
        "- id: cache-probe\n  name: Cache probe\n  entry: ./cache-probe\n  language: script\n"
        "  pass_filenames: false\n  always_run: true\n",
        encoding="utf-8",
    )
    probe = hook_repo / "cache-probe"
    probe.write_text("#!/bin/sh\nprintf '%s\\n' v1 > .versioner-cache-probe\n", encoding="utf-8")
    probe.chmod(0o755)
    git(hook_repo, "add", ".")
    git(hook_repo, "commit", "--quiet", "-m", "initial hook")
    git(hook_repo, "tag", "v1")
    consumer = tmp_path / "consumer"
    prepare(consumer)
    (consumer / ".pre-commit-config.yaml").write_text(
        f"repos:\n  - repo: {hook_repo.as_uri()}\n    rev: v1\n    hooks:\n      - id: cache-probe\n", encoding="utf-8"
    )
    git(consumer, "add", ".pre-commit-config.yaml")
    git(consumer, "commit", "--quiet", "-m", "configure hook")
    env = {**os.environ, "PREK_HOME": str(tmp_path / "prek"), "PRE_COMMIT_HOME": str(tmp_path / "pre-commit")}
    command = ["uv", "tool", "run", "--from", runner, runner]
    subprocess.run([*command, "install", "--install-hooks"], cwd=consumer, env=env, check=True, capture_output=True)
    subprocess.run([*command, "run"], cwd=consumer, env=env, check=True, capture_output=True)
    assert (consumer / ".versioner-cache-probe").read_text(encoding="utf-8") == "v1\n"
    probe.write_text("#!/bin/sh\nprintf '%s\\n' v2 > .versioner-cache-probe\n", encoding="utf-8")
    git(hook_repo, "add", "cache-probe")
    git(hook_repo, "commit", "--quiet", "-m", "advance hook")
    git(hook_repo, "tag", "--force", "v1")
    subprocess.run([*command, "run"], cwd=consumer, env=env, check=True, capture_output=True)
    assert (consumer / ".versioner-cache-probe").read_text(encoding="utf-8") == "v1\n"
    subprocess.run([*command, "clean"], cwd=consumer, env=env, check=True, capture_output=True)
    subprocess.run([*command, "install", "--install-hooks"], cwd=consumer, env=env, check=True, capture_output=True)
    subprocess.run([*command, "run"], cwd=consumer, env=env, check=True, capture_output=True)
    assert (consumer / ".versioner-cache-probe").read_text(encoding="utf-8") == "v2\n"
