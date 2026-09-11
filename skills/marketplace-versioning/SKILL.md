---
name: marketplace-versioning
description: Use when setting up, choosing, or troubleshooting agent plugin and marketplace versioning in a consumer repo — pre-commit hook, GitHub Action check/sync, version bumps, catalog reconciliation, bump-gate failures.
---

# Marketplace versioning

Read these, in order of need:

- Setup, approach choice, troubleshooting: <https://github.com/Jamie-BitFlight/agent-marketplace-versioner/blob/main/docs/setup.md>
- Command semantics, hook and Action snippets: <https://github.com/Jamie-BitFlight/agent-marketplace-versioner/blob/main/docs/index.md>
- Action inputs: <https://github.com/Jamie-BitFlight/agent-marketplace-versioner/blob/main/action.yml>
- CLI reference: <https://github.com/Jamie-BitFlight/agent-marketplace-versioner/blob/main/docs/reference/cli.md>

Approach decision:

- Local authors commit plugin changes → **Hook + CI**: pre-commit hook (`sync`)
  bumps plugin versions at commit time; post-merge Action (`sync` +
  `marketplace: true`) bumps catalogs, workflow commits the result.
- Agent/bot commits, or one enforcement point wanted → **CI-only**: PR Action
  `check` gate (needs `fetch-depth: 0`); author clears failures with `repair`;
  same post-merge marketplace step.

The Action never commits or pushes — publication belongs to the calling
workflow. Troubleshooting table: docs/setup.md.
