# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


def prepare(repo: Path) -> None:
    repo.mkdir(parents=True)
    git(repo, "init", "--quiet", "--initial-branch=fixture")
    git(repo, "config", "user.name", "Integration Test")
    git(repo, "config", "user.email", "test@example.invalid")
    manifest = repo / "catalog/tool/.codex-plugin/plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"name": "tool", "version": "1.0.0"}) + "\n", encoding="utf-8")
    content = repo / "catalog/tool/README.md"
    content.write_text("before\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "base")
    print(f"base={git(repo, 'rev-parse', 'HEAD').strip()}")
    content.write_text("committed change without version bump\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "change")


def stage(repo: Path) -> None:
    (repo / "catalog/tool/README.md").write_text("staged change\n", encoding="utf-8")
    git(repo, "add", "catalog/tool/README.md")


def verify(repo: Path) -> None:
    manifest = repo / "catalog/tool/.codex-plugin/plugin.json"
    assert json.loads(manifest.read_text(encoding="utf-8"))["version"] == "1.0.1"
    assert git(repo, "diff", "--cached", "--name-only").splitlines() == [
        "catalog/tool/.codex-plugin/plugin.json",
        "catalog/tool/README.md",
    ]
    git(repo, "commit", "--quiet", "-m", "versioned change")


if __name__ == "__main__":
    {"prepare": prepare, "stage": stage, "verify": verify}[sys.argv[1]](Path(sys.argv[2]))
