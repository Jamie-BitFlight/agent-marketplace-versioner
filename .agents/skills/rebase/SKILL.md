---
name: rebase
description: "Strategic rebase with mandatory pre-analysis. Use when asked to rebase a branch onto main (or any target). Runs a file-level diff of both sides before touching git, produces a per-file disposition plan (KEEP/MERGE/DROP/REWRITE), and only then executes the rebase. Prevents surprise conflicts and silent data loss from rebasing without knowing what changed on both sides. Triggers: 'rebase', 'rebase onto main', 'rebase this branch', 'rebase and merge', 'update branch from main'."
---

# Rebase

## Mandatory Pre-Rebase Analysis

Complete all steps below before running `git rebase`.

### Step 1 — Identify the merge base and branch files

Check whether `<branch>` is already checked out in another worktree:

```bash
git worktree list          # find the worktree whose HEAD is <branch>
```

If it is, run every remaining command in this step, and the rebase itself, from that worktree — a
clean-tree check or diff run elsewhere silently inspects the wrong tree. If `<branch>` is not
checked out anywhere, run these commands from the current worktree instead, provided it is clean;
`git rebase` will check `<branch>` out there in Step 5.

Fetch `<target>` into its explicit remote-tracking ref, not a bare `git fetch origin <target>`. When
`<target>` sits outside `remote.origin.fetch` (for example a `--single-branch` clone tracking a
different branch), a bare fetch updates only `FETCH_HEAD` and leaves `origin/<target>` absent or
stale, so the `merge-base` below is computed against nothing. Force the update (`--force`, or a
leading `+` on the refspec) — a plain explicit-refspec fetch is rejected as a non-fast-forward, and
`origin/<target>` stays at its old commit, when `<target>` was rewritten upstream (force-pushed):

```bash
git fetch --force origin <target>:refs/remotes/origin/<target>
```

If `<branch>` has a remote counterpart, fetch and check it too — a stale local `<branch>` (for
example a collaborator pushed more commits) understates "files touched by the branch" the same way
a stale `<target>` ref would. Detect the counterpart against the remote itself
(`git ls-remote`), not the local ref cache (`git rev-parse --verify origin/<branch>`) — the local
cache is empty until something fetches it, which is exactly the case being detected, so checking it
first always reports "no counterpart" and silently skips the fetch:

```bash
if git ls-remote --exit-code origin "<branch>" >/dev/null 2>&1; then
  git fetch --force origin <branch>:refs/remotes/origin/<branch>
  git rev-list --count "<branch>..origin/<branch>"  # nonzero: local <branch> is behind; pull before continuing
fi
```

```bash
MERGE_BASE=$(git merge-base <branch> origin/<target>)
git log --name-status -M --pretty=format: "${MERGE_BASE}..<branch>" | sort -u | sed '/^$/d'  # every file any commit the rebase will replay touches
git diff -M --name-status "${MERGE_BASE}..origin/<target>"                                     # files changed on target since divergence
```

Both ranges use the same explicit `${MERGE_BASE}..` form — do not swap either one back to
`<target>...<branch>` triple-dot notation, which recomputes its own merge base and can silently
drift from `$MERGE_BASE` if `<target>` moves between commands.

The branch-side command lists files touched by any individual commit being replayed, not just the
net tip-to-base result: a tree diff between `$MERGE_BASE` and `<branch>` can be empty for a file an
intermediate commit edits and a later commit reverts, even though `git rebase` still replays both
commits individually and can still conflict on it. `--name-status -M` also makes both commands
rename-aware (`R<score>  old  new`), so no separate plain `--name-only` diff is needed alongside
them.

If either side reports a rename (`R...`), treat the file as touched under *both* its old and new
path for the overlap check — a target edit to the old path and a branch rename-plus-edit to the new
path are the same file and must be diffed against each other in Step 2, not treated as two
unrelated files.

Check the branch's own working tree is clean (`git status --porcelain`, from the worktree found
above) before continuing. An uncommitted change to a file this analysis is about to judge is
invisible to every `git diff`/`git log` above; commit or stash it first, or the disposition plan
silently omits it.

### Step 2 — Diff overlapping files

For each file appearing in both lists above (matching by either path, per the rename check above),
read both sides. For a file renamed on either side, pass both its old and new path together with
`-M` — a single-path diff (`-- <path>`) only ever shows one endpoint of a rename and can misreport
a logical edit as an unrelated add or delete instead of pairing it:

```bash
git diff -M "${MERGE_BASE}..origin/<target>" -- <old_path> <new_path>       # what target changed
git log -p -M "${MERGE_BASE}..<branch>" -- <old_path> <new_path>            # every commit the rebase replays, and what each one changed
```

Read the branch side as `git log -p` (every replayed commit's own patch), not an endpoint diff
between `$MERGE_BASE` and `<branch>` — an endpoint diff is empty for a file an intermediate commit
edits and a later commit reverts, even though the replayed edit commit can still conflict with
target's own change to the same region. `git log -p` shows that commit's patch even when the net
branch-side change is nothing.

For a file not involved in any rename, `<old_path>` and `<new_path>` are the same single path.

Determine what each side changed and in which regions.

### Step 3 — Assign a disposition to every overlapping file

| Disposition | When to use |
|---|---|
| KEEP | Branch version wins; target change is irrelevant or already superseded |
| MERGE | Both sides changed different regions — list which regions each side owns |
| DROP | Branch change superseded by what target already landed; discard it |
| REWRITE | Branch intent survives, but implementation must change to account for target's changes |
| NO_CONFLICT | File touched only by the branch — no overlap with target |

### Step 4 — State the plan before executing

Output the full plan in this format before any `git rebase` command:

```text
Pre-rebase plan — <branch> onto <target>

Overlapping files:
  path/to/file.py: MERGE — branch adds X in foo(); target rewrites bar(); no region overlap
  path/to/other.py: DROP — target already landed the same change
  path/to/third.py: REWRITE — branch intent survives; must account for renamed parameter on target

No-conflict files (branch-only): path/a.py, path/b.py
```

### Step 5 — Execute the rebase

```bash
git rebase origin/<target> <branch>
```

Rebase onto `origin/<target>` — the ref Step 1's plan was actually built against — not the bare
local `<target>`, which may still be behind if something else advanced it since the fetch.

Pass `<branch>` — the same one Steps 1-4 analysed. `git rebase`'s positional form is
`[<upstream> [<branch>]]`; omitting `<branch>` rebases whatever is currently checked out, which
is a different branch whenever the analysis targeted one you are not standing on. That rewrites
commits the plan never looked at and leaves the requested branch untouched.

Naming `<branch>` makes git check it out first, which fails with `fatal: '<branch>' is already
used by worktree at ...` when another worktree holds it. Run the rebase from the same worktree used
for Step 1 — the one already holding `<branch>`, if Step 1 found one, or the current worktree
otherwise. Do not free the branch by detaching or switching another worktree — another session may
be mid-task in it.

On each conflict:

1. Resolve according to the plan.
2. When a conflict deviates from the plan (e.g., a region marked NO_CONFLICT has an unexpected conflict): stop, explain the deviation, update the plan entry, then resolve.

After completing, verify with `git log --oneline` and run the test suite.

## Rules

- Run every Step 1 command, and the rebase itself, from the worktree already holding `<branch>`, if
  one exists; otherwise use the current clean worktree.
- Force-fetch `<target>` (and `<branch>`, if `git ls-remote` finds a remote counterpart) into an
  explicit remote-tracking ref before Step 1's diffs.
- Derive Step 1's branch-side file list from `git log --name-status -M` (per-commit union), not a
  net tip-to-base diff.
- For a renamed file, diff its old and new path together (Step 2) — never a single path alone.
- Read the branch side of Step 2 as `git log -p`, not an endpoint diff — an endpoint diff misses a
  replayed commit whose net effect a later commit undoes.
- Write the Step 4 plan before running `git rebase`.
- Name `<branch>` in the `git rebase` invocation — never rely on the current checkout matching it.
- Resolve each conflict according to the plan — check before accepting either side.
- Read file-level diffs (Step 2); commit message titles are not a substitute.
