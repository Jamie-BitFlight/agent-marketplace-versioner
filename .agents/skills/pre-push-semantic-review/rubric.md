# Semantic review rubric

Apply the sections relevant to the supplied change. Findings need source
evidence and a consequence for interpretation, execution or maintenance.
Do not require a rewrite merely to satisfy a stylistic preference.

## Section checklist

Read the complete selected change set and its full files before using this
checklist. Identify affected sections by heading or a named table, diagram or
configuration block. Then check each section against the surrounding contract.
Use the reasoning guidance below to investigate failures, not as a substitute
for recording which sections were checked.

| Check | Required inspection |
| --- | --- |
| Meaning and authority | Compare the section at both revisions. Account for removed or relocated obligations, new constraints, mission/goal alignment and compatibility names. Identify the authority for a behavioral change. |
| State handoffs | For each value a changed decision consumes, locate its producer and verify that the needed value still exists at that point. Walk a path through any intervening mutation, including decisions that need an earlier value. A named input without a producer or surviving carrier is a gap. Mark this N/A for sections without state or handoffs. |
| Paths and gaps | For instructions, processes, graphs and decision trees, trace each documented branch from entry through its actors, inputs, outputs and state changes to its destination. Include alternatives and failure paths. Check dangling targets, unreachable steps, unexplained state without a producer or consumer, contradictory guards and missing continuations. Distinguish deliberate terminal outputs from orphans. Record undecided behavior rather than inventing a branch or choosing precedence. |
| References | Inventory affected paths, headings, table names, identifiers and promises such as “below.” Resolve each to the promised content at the candidate revision. Search for surviving uses of renamed or removed names, including unchanged callers. A nearby related section does not make an obsolete name accurate. |
| Consistency | Compare the section's actors, fields, decisions and effects with their other affected representations. Distinguish the producer or mutator from its dispatcher. Distinguish an actual contradiction from an unchanged, explicitly deferred gap. |
| Readability | Check actors, verbs, antecedents, condition scope, step order and table-column labels. Report the competing readings or lost meaning, not a preference for shorter prose. Check whether history obscures the current instruction without discarding necessary rationale. |
| Repository rules | Apply the relevant file-type formatting, line-length, naming and instruction rules. Check local imports and required pointers. Record unavailable evidence as UNKNOWN, not PASS. |

In the report, give each affected section a result for every checklist row.
For each changed handoff, show the consumed values, their last writers, their
values before and after any intervening mutation, and the later condition that
reads them. Include existing values the new step needs, not only newly added
fields. A producer/consumer name pair alone is not evidence for a handoff PASS;
an undeclared carrier or an untraceable value remains UNKNOWN or a located defect.
For loops, trace entry, continuation, exit and applicable retry/cap boundaries;
do not enumerate unbounded iterations. Name untraced paths and the missing
evidence instead of claiming complete coverage. Compare each traced path across
prose, tables and diagrams, including any contradictions in actor or state ownership.
For a failure, locate the gap or stale reference and suggest the smallest
correction supported by the contract. If choosing a correction requires new
behavioral authority, separate the confirmed problem from that proposed choice.

## Authority and scope

* Does the change serve the stated goal under the governing project rules?
  Separate mission, goals, requirements, evidence and approval.
* Inventory new constraints, defaults, thresholds, prohibitions and dependencies.
  Which user requirement, existing contract or measured behavior justifies each?
  Flag unsupported additions rather than inventing their intended purpose.
* Preserve runtime identifiers and interface meanings. Check whether a glossary
  term is canonical domain language, a compatibility name or an actual field.
  Do not implement another issue's migration through a wording suggestion.

## Instructions and state

* Can the reader identify who acts, on what input, under which condition, and
  what observable result ends the step? Distinguish a decision from its dispatch
  and from the operation that records or applies it.
* For each changed handoff, locate the producer and consumer of its state.
  Walk a concrete affected path. Does an earlier mutation erase information a
  later decision needs? Does a retry reuse stale state or lack a stopping rule?
* Account for each changed branch and destination across prose, tables, diagrams
  and executable contracts. Check missing cases and overlapping guards separately.
  An edge-count match does not prove totality, reachability or unique routing.
* Verify claimed exclusions against their enforcing input or rule. Separate an
  impossible state from an unsupported state. Preserve known ambiguity visibly;
  do not choose precedence or add a fallback without authority.

## Meaning and evidence

* Do removed or relocated instructions retain their required action, condition,
  reasoning principle, constraint and outcome at a reachable location?
* Are claims no stronger than their evidence? Distinguish a proposed architecture
  from implemented behavior, a passing check from validation, and provenance
  from approval. Treat missing evidence as unknown rather than success.
* For Skill Lapidary work, consult the applicable canonical runtime instructions.
  Check preserved capability, frozen contract boundaries, uncertainty handling
  and independent checking. Use only the relevant sections; this review is not
  permission to invoke the producer, rewrite a target or simulate missing evals.
* Would a suggested edit change a decision or behavior? If so, name that change
  and the authority or evaluation it needs. Shorter text alone does not justify it.

## Pointers and consistency

* Verify affected paths, anchors, table names, identifiers and relative links at
  the reviewed revision. For renames/deletions, search for callers of the old
  name. Check that an existing pointer reaches the promised content, not merely
  that a file exists. State which external references could not be verified.
* Compare repeated definitions and constraints. Keep one authoritative statement
  where possible and preserve the pointers needed by its consumers. Distinguish
  justified local reminders from copies that can disagree.
* Read source and generated configuration at their actual host boundaries. A
  valid file format alone does not establish discovery, tool access or execution.

## Readability and structure

* Prefer explicit actors and verbs, stable terminology and clear antecedents.
  Identify the competing readings when reporting ambiguous wording.
* Separate sequential instructions when that clarifies their order. Keep a
  prerequisite beside the action it governs; preserve simultaneous actions and
  qualifications that change meaning. Do not hide required actions in notes.
* Keep each paragraph or table cell focused on its reader's immediate question.
  Use a list or decision table where it makes relationships easier to compare.
  Remove change history only when it does not carry a necessary rationale.
* Check configured line-length rules for the relevant file type. Do not apply a
  Python formatter's limit to Markdown. Without a prose limit, report a long
  sentence or cell only with the concrete reading problem it causes. Wrapping
  lines does not fix nested clauses; splitting them must not lose their scope.

The structural prompts above selectively adapt ASD-STE100 Issue 9 writing
principles (4.1, 5.2-5.5 and 6.1). They are advisory review lenses, not adoption
of its dictionary, numerical sentence limits or a claim of STE compliance.
Project contracts remain authoritative. Source:
[ASD-STE100 Issue 9](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf).
