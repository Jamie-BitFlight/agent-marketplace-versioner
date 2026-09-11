# Setup

Install paths and the choice between versioning approaches. Command semantics
live in [Commands](index.md#commands); hook and Action snippets in
[Git hook](index.md#git-hook) and [GitHub Action](index.md#github-action).

## Install

| Surface | Install |
| --- | --- |
| CLI | `uv tool install agent-marketplace-versioner` (PyPI) → `agent-marketplace-versioner` on PATH |
| pre-commit hook | Repo stanza at `rev: v1` in the consumer's `.pre-commit-config.yaml`, then `prek install` — see [Git hook](index.md#git-hook) |
| GitHub Action | `uses: Jamie-BitFlight/agent-marketplace-versioner@v1` — see [GitHub Action](index.md#github-action) |

No per-consumer adapter or versioner-specific configuration file is required.
The CLI needs `git` on PATH.

## Exclude manifests from formatters and linters

The versioner rewrites `plugin.json`, `*.plugin.json`, and `marketplace.json`
with a canonical style (2-space indent, trailing newline). If a commit-time
formatter (biome, prettier, oxfmt/oxlint, ...) also touches them, each pass
reformats against the other and hooks cycle until one side stops; CI format
checks flag the same churn. Exclude these files everywhere they are formatted
or linted — the formatter's own config so CI inherits it:

```json5
// prettier: .prettierignore
**/plugin.json
**/*.plugin.json
**/marketplace.json
```

```json5
// biome.json — formatter and linter
{
  "files": {
    "includes": ["!**/plugin.json", "!**/*.plugin.json", "!**/marketplace.json"]
  }
}
```

```toml
# oxlint / oxfmt config — same three globs in its ignore/exclude option
```

For pre-commit, also narrow the hook's own `files`/`exclude` so the formatter
hook never receives the manifests, keeping each versioner-managed file owned by
exactly one tool.

## Choosing a versioning approach

**Hook + CI** — plugin authors commit locally and want immediate cache-busting:

1. The pre-commit hook runs `sync` on every commit: plugin manifest versions
   bump and stage locally.
2. A post-merge workflow on the default branch runs the Action with
   `command: sync`, `marketplace: true`: catalog entries reconcile and existing
   marketplace versions bump. The workflow owns commit and push of the result.
3. Optional belt-and-braces: a PR workflow runs the default `command: check`
   gate.

**CI-only** — commits arrive from agents or bots, or hook maintenance is
unwanted; enforcement lives entirely at merge:

1. A PR workflow runs the Action default `command: check` with `base-ref` and
   `head-ref` (checkout with `fetch-depth: 0`). It exits 1 when changed plugin
   content lacks a version bump.
2. The PR author — human or agent — clears the gate by running
   `agent-marketplace-versioner repair` locally and committing the bumps.
3. The same post-merge `command: sync` + `marketplace: true` workflow as above
   bumps catalogs; the Action never commits or pushes, so the workflow adds a
   commit step.

Choose Hook + CI when local plugin evaluation matters during development;
choose CI-only when one enforcement point at merge beats per-machine setup.
Both approaches share the identical post-merge marketplace step.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `check` exits 1 in CI | Changed plugin content is missing a version bump; run `repair`, commit the result |
| `check` cannot find a revision | Shallow checkout; use `fetch-depth: 0` so both refs exist locally |
| Hook still runs an old version after a new v1 release | Runners cache the revision first resolved for `v1`; refresh with `prek clean && prek install --install-hooks` — see [Git hook](index.md#git-hook) |
| Action ran but nothing was committed | By design; the Action never commits or pushes — the calling workflow owns publication |
| `git executable not found in PATH` | Install git; manifest discovery shells out to it |
