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
