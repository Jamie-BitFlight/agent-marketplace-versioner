# PR #3 Adversarial Review — docs/setup.md + marketplace-versioning skill

Branch `feat/setup-skill` @ d5f2c65, base `main` @ 562755f. Docs-only diff:
`docs/setup.md` (+87), `skills/marketplace-versioning/SKILL.md` (+25), two
symlinks, one `mkdocs.yml` nav line. All evidence below was gathered in this
session (`git diff main...HEAD`, `git show main:<path>`, `git ls-remote`,
PyPI JSON API, live `mkdocs build --strict`, biomejs.dev reference extract).

Verdict: **2 P1, 1 P2, 5 P3.** Do not merge as-is; both P1s are small fixes.

---

## P1-1 — Biome snippet is invalid under current Biome v2 (negated-only `files.includes`)

`docs/setup.md` (Exclude manifests section):

```json
{ "files": { "includes": ["!**/plugin.json", "!**/*.plugin.json", "!**/marketplace.json"] } }
```

Biome's configuration reference (biomejs.dev/reference/configuration, fetched
this session, schema version 2.3.11) states, under `files.includes`:

> "When using a negated pattern, you should always specify `**` first to match
> all files and folders, otherwise the negated pattern will not match any files."

and under Glob syntax reference:

> "Negated patterns cannot be used alone, they can only be used as *exception*
> to a regular glob."

The snippet contains **only** negated patterns with no leading `"**"`. Per the
vendor docs it either errors or silently excludes nothing — the exact opposite
of the section's purpose. Correct form is
`["**", "!**/plugin.json", "!**/*.plugin.json", "!**/marketplace.json"]`.
This is the doc's flagship config example; shipping it broken guarantees the
formatter-vs-versioner cycle it exists to prevent.

## P1-2 — Glob set misses the `*-plugin.json` manifest shape the versioner actually rewrites

`docs/setup.md` claims: "The versioner rewrites `plugin.json`, `*.plugin.json`,
and `marketplace.json`", and gives three exclude globs. But
`packages/agent_marketplace_versioner/native_manifests.py::manifest_kind()`
(on main) accepts a fourth shape:

```python
if path.name.endswith((".plugin.json", "-plugin.json")):
    return "plugin"
```

i.e. any loose `foo-plugin.json` (hyphen form) anywhere in the repo is a
versioner-managed plugin manifest. `**/*.plugin.json` does **not** match
`foo-plugin.json` under prettier/gitignore, Biome, or any glob semantics
verified this session. A consumer who follows the doc verbatim still gets
formatter/versioner churn on every `-plugin.json` manifest — the precise
failure mode the section claims to eliminate. The prose sentence is also
factually wrong about the versioner's file set (claims less than reality).

Fix: add `**/*-plugin.json` to all three snippets and to the sentence.

Note on the other direction (over-claim, demoted to P3-2): `manifest_kind()`
only accepts bare `plugin.json`/`marketplace.json` inside harness dirs
(`_HARNESS_DIRECTORY = re.compile(r"\.[A-Za-z0-9_-]+-plugin")`, fullmatch on
parent) or `.agents/plugins/marketplace.json`; the docs' `**/plugin.json` and
`**/marketplace.json` globs also exclude files the versioner never touches.
Harness-dir forms like `.foo-plugin/plugin.json` **are** covered by the doc
globs (verified: `**/plugin.json` matches at any depth incl. dot-directories).

---

## P2-1 — Install instructions point at a `v1` tag that does not exist

`docs/setup.md` install table: `rev: v1` (pre-commit) and
`uses: Jamie-BitFlight/agent-marketplace-versioner@v1` (Action). Verified via
`git ls-remote --tags origin`: the only tags are `v0.1`, `v0.1.0`, `v0.1.1`,
`v0.1.2`. No `v1` ref exists, so both install paths fail today. This claim is
inherited verbatim from `docs/index.md` on main (pre-existing, not introduced
by this PR — hence P2 not P1), but the PR's new "Setup" page canonizes it as
the primary install guidance. Either create the `v1` moving tag before/with
merge, or the docs should reference what resolves now. (PyPI package
`agent-marketplace-versioner` 0.1.2 does exist — the `uv tool install` row is
accurate, including the console-script name per `pyproject.toml
[project.scripts]`.)

---

## P3 (nits)

1. **Fence language lies.** The prettier block is tagged ` ```json5 ` but a
   `.prettierignore` is a plain-text gitignore-style file — the `// prettier:
   .prettierignore` comment line is not valid ignore-file syntax and would be
   parsed as a pattern if copy-pasted wholesale. Use ` ```gitignore ` (or
   `text`) and put the filename outside the fence. (The task brief suspected a
   `.prettierignore` vs `.prettierconfig` mix-up; checked — the filename cited
   is correct, only the fence language is wrong.)
2. **Over-broad exclusion framed as exact.** Prose says the versioner
   "rewrites plugin.json ... and marketplace.json", implying any file so
   named; in reality only harness-dir / `.agents/plugins/` placements count
   (see P1-2 note). The broad globs silently strip unrelated
   `plugin.json`/`marketplace.json` files from formatting/linting. Safe
   direction, but one sentence acknowledging it would keep the doc honest.
3. **Empty TOML placeholder fence.** ` ```toml / # oxlint / oxfmt config —
   same three globs in its ignore/exclude option / ``` ` carries zero
   information and its language tag is speculative (oxlint's config is
   `.oxlintrc.json`, JSON not TOML — unverified against oxc docs this
   session). Either give a real snippet or delete the fence and keep the
   sentence.
4. **Symlink convention inconsistency.** Existing `.claude/skills/*` symlinks
   point at `../../.agents/skills/<name>`; the two new symlinks both point at
   `../../skills/marketplace-versioning`. Both resolve correctly (verified:
   targets exist, `readlink` output checked), but the repo now has two
   competing layouts for the same directory. Cosmetic; pick one convention.
5. **Invariant stated 4×.** "The Action never commits or pushes" appears in
   `docs/index.md`, `docs/setup.md` (twice: CI-only step 3 and the
   troubleshooting table) and `SKILL.md`. Fine today, drift magnet tomorrow;
   the troubleshooting row alone would suffice in setup.md.

---

## Verified-correct claims (checked, no finding)

- **SKILL.md URLs (4/4 resolve post-merge).** `docs/setup.md` (added by this
  PR), `docs/index.md`, `action.yml`, `docs/reference/cli.md` — all present in
  `git ls-tree -r main` or in this diff; repo URL matches `pyproject.toml
  [project.urls]`.
- **Hook + CI description vs reality.** `.pre-commit-hooks.yaml` entry is
  `agent-marketplace-versioner sync`, `pass_filenames: false`, `always_run:
  true`, stage `pre-commit` — matches setup.md step 1 and index.md. Post-merge
  `command: sync` + `marketplace: true` → `sync --marketplace` matches
  `action.yml`'s case arm and index.md. No contradiction found between
  setup.md and index.md; setup.md links to index.md for command semantics
  rather than restating tables (acceptable DRY; see P3-5 for the one repeated
  sentence).
- **CI-only description.** `check` is the Action default (`action.yml
  inputs.command.default: check`); `base-ref`/`head-ref` defaults pull from
  `github.event.pull_request.*`; `_run_check()` returns 1 on missing bumps and
  on unresolvable/invalid refs (`_commit_ref` → `ValueError` → `return 1`),
  matching troubleshooting rows 1–2, and `fetch-depth: 0` matches index.md's
  "Both revisions must exist locally".
- **`repair` as the gate-clearing command.** `_run_repair()` patch-bumps
  every drifted native plugin manifest (`_native_drifted_manifests()` via
  `discover_manifests()` + last-bump-commit diff), exits 0 on success / 1 with
  a `failed` list — consistent with "run `repair`, commit the result".
  Action exposes `repair` (`action.yml` case arm). Edge nuance (not a
  finding): repair is drift-based and needs a well-formed existing `version`;
  brand-new plugins are exempt from `check` anyway.
- **`git executable not found in PATH` row.** Exact string raised by
  `native_manifests.py::_git_visible_paths` / `_is_gitignored`; discovery does
  shell out to git (`shutil.which("git")` + `git ls-files`). Accurate.
- **`prek clean && prek install --install-hooks` row.** Matches index.md's
  v1-moving-tag cache paragraph verbatim (index.md also offers the
  `pre-commit` equivalent; setup.md mentions only `prek` — trivial).
- **Canonical-style claim** ("2-space indent, trailing newline") matches the
  writers (`json.dumps(data, indent=2) + "\n"`, `write_bytes`) in
  `check_plugin_version_bump.py::_run_repair` / `repair_plugin_version`.
- **mkdocs.** `uv run mkdocs build --strict` succeeds with the new
  `- Setup: setup.md` nav entry; `/tmp/pr3-mkdocs-site/setup/index.html`
  produced. In-page anchors (`index.md#commands`, `#git-hook`,
  `#github-action`) match real headings on main; strict mode would have
  failed on broken relative links.
- **Symlinks.** Both are mode `120000` in the diff, targets resolve from
  their own directory depth (`.agents/skills/../../skills/...` =
  `<repo>/skills/marketplace-versioning`, which the same commit adds).
