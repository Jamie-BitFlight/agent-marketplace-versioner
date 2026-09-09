# Reviewer host setup

The reviewer consumes this skill and its rubric, applicable project rules and
the pinned review sources. Fetch external evidence before launching it. Do not
supply author discussion or expected findings. Return its report to the caller;
the caller owns fixes and persistence.

## Claude Code

The generated skill uses `context: fork` and
`agent: skill-lapidary:semantic-reviewer`, the packaged agent's scoped name.
The packaged agent selects `opus` and exposes only `Read, Bash`; it does not
expose `Skill`, `Agent` or MCP tools. The fork injects the skill process, so the
agent does not preload another copy through a `skills` list. Its body only
anchors that process. Invoke the packaged skill with the repository, base,
candidate, paths and change goal. The caller waits for the result before pushing.

Claude documents that forked skills omit conversation history; custom agents
still receive applicable project memory. Tool allowlisting does not make Bash
read-only: the process prohibits mutation, and deployments needing enforcement
must use their host's read-only permissions. Plugin agents cannot enforce
`permissionMode` through their frontmatter.

## Codex

The repository-local `.codex/agents/semantic-reviewer.toml` selects
`gpt-5.6-sol`, high reasoning and a read-only sandbox. Start it in a new context
with no inherited conversation, and pass the absolute path to this skill plus
the pinned review inputs. A host exposing `fork_turns` uses `none`.
Read and shell inspection are performed through Codex's file/shell facilities.
The canonical skill's frontmatter stays portable; Claude's fork fields are
generated only in the Claude package.

Local Codex discovers this agent from a checkout's `.codex/agents/`. Installing
the skill plugin alone does not install that repository-local agent into another
project. Copy the TOML into that project's `.codex/agents/` and provide the
installed skill path when invoking it.

The configuration disables web search, apps and further delegation. Codex
inherits omitted MCP and skill configuration; an empty table is not a verified
global deny rule. Before using a host with extra integrations, disable each
unneeded server with `mcp_servers.<id>.enabled = false` and each unneeded skill
with its documented `skills.config` path override in that agent's local config.
Do not change the parent session's configuration. Verify the resulting catalog
in that host; do not describe a small used-tool set as a small exposed-tool set.

ChatGPT Work subagents inherit the parent's tools. A fresh Work context tests
the review process without author history, but does not validate this local
Codex TOML, Claude fork resolution or a restricted startup catalog. Record those
host checks as unverified until exercised in the relevant clients. No model
substitution or weaker isolation should be silent.

## Kimi Code

Kimi receives the canonical skill without Claude's automatic fork fields. The
caller uses `Agent` with `subagent_type: semantic-reviewer`, a new instance
(omit `resume`), and a prompt containing the absolute skill path and pinned
review inputs. This matches the unscoped agent names used by this repository's
Kimi worker mapping. Confirm that `semantic-reviewer` is in the installed host's
agent catalog before calling it; publication in `kimi.plugin.json` alone does
not establish that the installed client registered it. If absent, return
`BLOCKED` with the missing registration rather than using the author context.

The caller must select and record the agreed review model through the host's
model configuration or `Agent` model override; the shared Claude `model: opus`
field is not a Kimi model selection. If the agreed model is unavailable, report
`BLOCKED` instead of silently substituting it. Verify the exposed tools and
context isolation in the installed client. The intended tool set is file reads
and shell inspection; shell access alone does not enforce read-only behavior.
Native Kimi invocation and catalog restrictions have not been exercised here.

## Configuration sources

Verified against the official documentation on 2026-09-09:

- [Claude skills](https://code.claude.com/docs/en/skills): fork execution and agent selection.
- [Claude subagents](https://code.claude.com/docs/en/sub-agents): tools, models, skill preloading and plugin restrictions.
- [Claude plugin reference](https://code.claude.com/docs/en/plugins-reference): scoped agent names.
- [Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents): local agent files and inherited configuration.
- [Codex configuration](https://learn.chatgpt.com/docs/config-file/config-reference): sandbox, web search, apps, agents and per-server/per-skill overrides.
- [Kimi agents](https://moonshotai.github.io/kimi-cli/en/customization/agents.html): isolated agent instances, invocation fields and model override. Custom plugin registration remains an installed-client check.
