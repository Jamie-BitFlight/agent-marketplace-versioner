from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_external_actions_are_immutable_and_version_labeled() -> None:
    files = [ROOT / "action.yml", *sorted((ROOT / ".github/workflows").glob("*.yml"))]
    for path in files:
        for line in path.read_text().splitlines():
            if "uses:" not in line or "uses: ./" in line:
                continue
            assert re.search(r"uses: [\w/-]+@[0-9a-f]{40} # v[\d.]+$", line), (path, line)


def test_pr_code_has_read_only_permissions_and_no_persisted_credentials() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/test.yml").read_text())
    assert workflow["permissions"] == {"contents": "read"}
    for name, job in workflow["jobs"].items():
        if name in {"release", "coverage-summary"}:
            continue
        assert job.get("permissions", workflow["permissions"]) == {"contents": "read"}
        for step in job["steps"]:
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] is False
    summary = workflow["jobs"]["coverage-summary"]
    assert summary["permissions"] == {"contents": "read", "pull-requests": "write"}
    assert summary["steps"][0]["with"] == {
        "persist-credentials": False,
        "ref": "${{ github.event.pull_request.base.sha }}",
    }
    release = workflow["jobs"]["release"]
    assert release["permissions"] == {"contents": "write"}
    assert release["if"] == "github.ref == 'refs/heads/main' && github.event_name == 'push'"


def test_credentials_are_limited_to_trusted_git_write_jobs() -> None:
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        workflow = yaml.safe_load(path.read_text())
        assert "write" not in workflow.get("permissions", {}).values()
        for name, job in workflow["jobs"].items():
            for step in job.get("steps", []):
                if not step.get("uses", "").startswith("actions/checkout@"):
                    continue
                if (path.name, name) in {("test.yml", "release"), ("update-readme.yml", "generate")}:
                    assert job["permissions"] == {"contents": "write"}
                    assert "github.ref ==" in job["if"]
                else:
                    assert step["with"]["persist-credentials"] is False
