# agent-marketplace-versioner

Manage native agent plugin and marketplace versions from the consumer Git repository.
The distributable hook and composite GitHub Action invoke the same CLI.

## Commands

| Command | Effect |
| --- | --- |
| `check --base-ref BASE --head-ref HEAD` | Read-only gate; exits 1 when required version bumps are missing. |
| `audit` | Read-only JSON drift report. |
| `sync` | Update and stage versions affected by the Git index. |
| `sync --marketplace` | Reconcile and version native marketplace catalogs. |
| `repair` | Apply manifest repairs and report results as JSON. |
| `reconcile --dry-run` | Preview full reconciliation; exits 1 when changes are needed. |
| `reconcile` | Apply full reconciliation. |

Both revisions must exist locally for `check`. A shallow checkout may need
additional history. Mutation commands change local files; the caller owns review,
commit and publication.

## Git hook

Add this to the consumer's `.pre-commit-config.yaml`, replacing the revision with
a reviewed immutable commit SHA:

```yaml
repos:
  - repo: https://github.com/Jamie-BitFlight/agent-marketplace-versioner
    rev: <full-commit-sha>
    hooks:
      - id: agent-marketplace-versioner
```

Run `prek install` or `pre-commit install`. Both runners install the Python package
and call `agent-marketplace-versioner sync` once per pre-commit run, without passing
filenames. Stage intended content changes before running the hook. It stages
updated version manifests and preserves the same bump on repeat runs.
Each native manifest uses its own version at `HEAD` as its staged-change baseline.
Catalog entry additions and removals are also reconciled and staged, without
changing the catalog version or introducing a version field.

## GitHub Action

```yaml
- uses: actions/checkout@v7
  with:
    fetch-depth: 0
- uses: Jamie-BitFlight/agent-marketplace-versioner@<full-commit-sha>
  with:
    base-ref: ${{ github.event.pull_request.base.sha }}
    head-ref: ${{ github.event.pull_request.head.sha }}
```

The default `command: check` reads the consumer repository at `repository`
(the workflow workspace by default). Pass `command: sync`, `repair`, or `reconcile`
only when local mutation is intended. Only `check` consumes `base-ref` and `head-ref`.
The action does not commit or push. It supports Linux and macOS Bash runners.

For post-merge catalog reconciliation, use `command: sync` with `marketplace: true`.
This invokes `sync --marketplace`. The default `marketplace: false` keeps ordinary
staged-manifest synchronization; the input has no effect on other commands.

The action installs the source at its pinned checkout with `uv sync --locked`
and no development dependencies. GitHub downloads actions without Git metadata,
so the temporary installation uses package metadata version `0+action`; the
reviewed action commit selects the actual code, and its lockfile selects dependencies.
