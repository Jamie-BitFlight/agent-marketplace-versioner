<div align="center">

<!-- start title -->

# agent-marketplace-versioner

<!-- end title -->
<!-- start badges -->
<!-- end badges -->

</div>

<!-- start description -->

Check and synchronize versions in native agent plugin and marketplace manifests.
The CLI, GitHub Action and Git hooks use the same implementation in the consumer repository.

<!-- end description -->

Documentation: <https://bitflight.io/agent-marketplace-versioner/>.

<!-- start usage -->

### GitHub Action

Pin this repository to a reviewed commit SHA. The default command is a read-only
base/head check; checkout must include both revisions.

```yaml
- uses: actions/checkout@v7
  with:
    fetch-depth: 0
- uses: Jamie-BitFlight/agent-marketplace-versioner@<full-commit-sha>
  with:
    base-ref: ${{ github.event.pull_request.base.sha }}
    head-ref: ${{ github.event.pull_request.head.sha }}
```

### Git hook (prek or pre-commit)

```yaml
repos:
  - repo: https://github.com/Jamie-BitFlight/agent-marketplace-versioner
    rev: <full-commit-sha>
    hooks:
      - id: agent-marketplace-versioner
```

Run `prek install` or `pre-commit install` in the consumer repository. The hook
installs the pinned Python package, runs once without filename arguments, and
updates and stages affected versions. Repeated runs preserve the same bump.

### CLI

```sh
uv tool install 'git+https://github.com/Jamie-BitFlight/agent-marketplace-versioner@<full-commit-sha>'
agent-marketplace-versioner check --base-ref origin/main --head-ref HEAD
agent-marketplace-versioner sync
```

Run the CLI from the consumer Git repository. `check` is read-only; `sync` mutates
and stages manifests. See the [usage guide](docs/index.md) for audit, repair and
marketplace reconciliation.

<!-- end usage -->

<!-- start inputs -->

| Input | Default | Meaning |
| --- | --- | --- |
| `command` | `check` | `check`, `audit`, `sync`, `repair`, or `reconcile` |
| `repository` | workflow workspace | Consumer Git repository directory |
| `base-ref` | PR base SHA or push before SHA | Required base for `check` |
| `head-ref` | PR head SHA or workflow SHA | Candidate for `check` |

`audit` reports drift without writing. `sync`, `repair`, and `reconcile` explicitly
authorize mutation; the action does not commit or push their changes. The composite
action supports Linux and macOS Bash runners and installs its checked-out package
and locked runtime dependencies in an isolated temporary environment.

<!-- end inputs -->

<!-- start outputs -->
<!-- end outputs -->
