from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Final

import pytest
import yaml
from tests.integration_consumer import git, prepare, stage, verify

ROOT: Final = Path(__file__).resolve().parents[1]


@pytest.mark.slow
def test_composite_script_checks_and_syncs_a_consumer_without_vcs_metadata_in_action(tmp_path: Path) -> None:
    source = tmp_path / "downloaded action"
    source.mkdir()
    for name in ("pyproject.toml", "uv.lock", "README.md", "LICENSE"):
        shutil.copyfile(ROOT / name, source / name)
    shutil.copytree(ROOT / "packages", source / "packages", ignore=shutil.ignore_patterns("__pycache__"))
    consumer = tmp_path / "consumer"
    prepare(consumer)
    script = yaml.safe_load((ROOT / "action.yml").read_text())["runs"]["steps"][1]["run"]
    env = {
        **os.environ,
        "RUNNER_TEMP": str(tmp_path),
        "VERSIONER_SOURCE": str(source),
        "VERSIONER_REPOSITORY": str(consumer),
        "VERSIONER_BASE": "HEAD~1",
        "VERSIONER_HEAD": "HEAD",
        "VERSIONER_COMMAND": "check",
        "SETUPTOOLS_SCM_PRETEND_VERSION": "0+action",
    }
    rejected = subprocess.run(
        ["bash", "-eo", "pipefail", "-c", script], env=env, check=False, capture_output=True, text=True
    )
    assert rejected.returncode == 1, rejected.stdout + rejected.stderr
    assert "catalog/tool/.codex-plugin/plugin.json" in rejected.stderr
    assert git(consumer, "status", "--porcelain") == ""

    stage(consumer)
    env["VERSIONER_COMMAND"] = "sync"
    subprocess.run(["bash", "-eo", "pipefail", "-c", script], env=env, check=True, capture_output=True)
    staged = git(consumer, "diff", "--cached")
    subprocess.run(["bash", "-eo", "pipefail", "-c", script], env=env, check=True, capture_output=True)
    assert git(consumer, "diff", "--cached") == staged
    verify(consumer)
    env["VERSIONER_COMMAND"] = "check"
    subprocess.run(["bash", "-eo", "pipefail", "-c", script], env=env, check=True, capture_output=True)
    assert git(consumer, "status", "--porcelain") == ""
