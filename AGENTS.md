# AGENTS.md

Universal working rules for repository tasks. Project-specific instructions override these where they conflict.

## Before Editing

1. **Define success.** State the required outcome, acceptance criteria, preserved behavior, constraints, and non-goals.
2. **Establish the boundary.** Identify owners, consumers, inputs, outputs, dependencies, interfaces, and affected environments.
3. **Separate evidence from inference.** Current code, tests, file placement, wiring, counts, versions, and other observed state describe what exists; they do not prove intended ownership, durable design intent, or the correct change location.
4. **Surface consequential uncertainty.** State assumptions and competing interpretations. Resolve uncertainty that could change scope, compatibility, ownership, or architecture before editing.
5. **Choose the smallest viable change.** Prefer existing abstractions and established dependencies over new code. Compare viable approaches by evidence, blast radius, trade-offs, maintenance cost, and reversibility.

## Claims and Evidence

The rules above govern changes. These govern statements — in a reply, an issue, a commit message, a code comment, or a brief handed to a subagent.

- **A claim about the world needs a command.** Do not state a fact about this codebase, another repository, a library, or a tool's behavior unless something run in the current session established it. Where no check was run, mark the claim unverified in the same sentence.
- **A subagent's characterization is not evidence.** It is a claim with the same standing as your own. Check the artifact it describes before repeating it or building on it.
- **Contradicting evidence stops the work.** An empty grep, a truncated capture, a result that disagrees with the plan already in flight — resolve it before continuing. These are the cheapest signals available and the easiest to walk past.
- **An unverified claim that reaches an issue, a commit, or a comment becomes a premise.** Later readers cannot distinguish it from a checked fact and will cite it as one. Correcting the claim later does not retract the work built on it — revisit that too.
- **A working tree is not the repository.** Read committed state — `git show <ref>:<path>` — before describing what a repository contains. A checkout can hold another session's uncommitted work, and reading it reports that work as the repo's own.
- **Absence of a config is not absence of a tool, and presence is not use.** A disabled stanza reads as presence to grep while meaning the opposite; a tool can also be configured in a file that names it nowhere. Check where the tool is actually resolved from — the lockfile, the hook, the CI step.

## While Editing

- Change only what is required for the defined outcome.
- Do not refactor, reformat, or clean unrelated code.
- Match established repository conventions.
- Remove only artifacts made obsolete by your change.
- Do not add speculative flexibility, abstractions, fallbacks, or features.
- Reassess the plan when evidence contradicts an assumption.

## Verification

- Validate each affected boundary independently.
- Do not generalize success from one test, harness, environment, or consumer.
- Prefer tests that demonstrate required behavior over implementation-detail tests.
- Verify relevant regression, compatibility, static-analysis, and runtime checks.

## Verifying a change

```sh
uv run prek run --all-files
uv run pytest
uv build
```

The hook set is the lint, formatting, type-check, workflow, Markdown, and shell gate. Run it rather than presenting a subset of checks as equivalent.

## Changing dependencies

Use `uv add` or `uv remove`; do not hand-edit dependency version strings. Regenerate `uv.lock` with `uv lock`.

## Before Commit

Review the complete diff against this `AGENTS.md` before committing.

- Confirm every changed line is required by the defined outcome and complies with the repository instructions above.
- Identify every new constraint, threshold, default, prohibition, workflow step, fallback, abstraction, or policy introduced by the diff. Keep it only when its existence is justified by the user requirement, repository evidence, an applicable external contract, or measured behavior; otherwise remove or demote it to an explicitly labeled hypothesis or experiment parameter.
- Remove unrelated cleanup, duplicated guidance, speculative flexibility, and implementation detail that does not earn its maintenance cost.
- Re-run affected verification when the diff review changes behavior.

Do not commit while a known unjustified constraint or instruction-compliance violation remains in the diff.

## Completion

Before declaring success, confirm:

- acceptance criteria are demonstrated;
- required checks pass;
- no known affected boundary remains unverified;
- no unnecessary changes remain in the diff;
- remaining uncertainty, limitations, or follow-up work is stated explicitly.
