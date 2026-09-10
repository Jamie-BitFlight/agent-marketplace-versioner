from __future__ import annotations

import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Final

import pytest
import yaml
from tests.integration_consumer import git, prepare, stage, verify

ROOT: Final = Path(__file__).resolve().parents[1]


def test_public_v1_contract_metadata_and_documentation() -> None:
    action = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
    package = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    documentation = (ROOT / "docs/index.md").read_text(encoding="utf-8")
    ghadocs = json.loads((ROOT / ".ghadocs.json").read_text(encoding="utf-8"))

    assert action["description"] == (
        "Keep agent plugin and marketplace versions in sync across Codex, Claude Code, and other harnesses."
    )
    assert action["branding"] == {"icon": "refresh-cw", "color": "purple"}
    assert {name: metadata["default"] for name, metadata in action["inputs"].items()} == {
        "command": "check",
        "marketplace": "false",
        "repository": "${{ github.workspace }}",
        "base-ref": "${{ github.event.pull_request.base.sha || github.event.before }}",
        "head-ref": "${{ github.event.pull_request.head.sha || github.sha }}",
    }
    assert package["project"]["description"] == "Keep agent plugin and marketplace versions in sync."
    assert "Development Status :: 5 - Production/Stable" in package["project"]["classifiers"]
    assert ghadocs["versioning"]["override"] == "v1"
    assert "Jamie-BitFlight/agent-marketplace-versioner@v1" in readme
    assert "Jamie-BitFlight/agent-marketplace-versioner@v1" in documentation
    assert "agent-marketplace-versioner@v0" not in readme


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
        "VERSIONER_MARKETPLACE": "false",
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

    marketplace = consumer / "catalog/.claude-plugin/marketplace.json"
    marketplace.parent.mkdir()
    original = {"metadata": {"version": "1.0.0"}, "plugins": [{"name": "old", "source": "./old"}]}
    marketplace.write_text(json.dumps(original))
    git(consumer, "add", ".")
    git(consumer, "commit", "--quiet", "-m", "add catalog")
    env["VERSIONER_COMMAND"] = "sync"
    subprocess.run(["bash", "-eo", "pipefail", "-c", script], env=env, check=True, capture_output=True)
    assert json.loads(marketplace.read_text())["metadata"] == original["metadata"]
    env["VERSIONER_MARKETPLACE"] = "true"
    subprocess.run(["bash", "-eo", "pipefail", "-c", script], env=env, check=True, capture_output=True)
    catalog = json.loads(marketplace.read_text())
    assert catalog["plugins"] == [{"name": "tool", "source": "./tool"}]
    assert catalog["metadata"]["version"] == "1.0.1"
    subprocess.run(["bash", "-eo", "pipefail", "-c", script], env=env, check=True, capture_output=True)
    assert json.loads(marketplace.read_text()) == catalog
