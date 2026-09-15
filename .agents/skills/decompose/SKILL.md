---
name: decompose
description: >-
  Sizing and decomposition policy for chipping-orchestrator issues. Use when you
  decompose an issue or adjudicate an oversized, already-implemented change:
  size it, decide single versus split, plan child issues and their dependencies,
  and emit the manifest the active prompt requires.
---

# Decomposer skill — chipping-orchestrator

Two stages ask the same question — can this work be cut into child issues that each deliver something of their own?
— and answer it under different contracts:

- **Initial decomposition** sizes an issue before any code exists and ends in an `orchestrator-manifest` block.
- **Late adjudication** assesses a change a developer already wrote that measured past the addition ceiling, and ends
  in an `orchestrator-late-manifest` block.

The prompt you were spawned with is the contract. Its output fence, decision values, child limit, lineage rules, and
clarification format win over anything here; this skill tells you how to plan children this repository can land.

## You plan; the orchestrator acts

Inspection and planning are read-only. Read the tree, grep, and use `git log`, `git diff`, or `wc -l` — never edit a
file, commit, push, fetch, or run anything that writes. You do not open issues either: the orchestrator reads your
manifest and creates the child issues itself, allocating their numbers, which is why `depends_on` indexes into your
own children array.

## A child's complete scope

Size and describe each child by everything its normal pull-request lifecycle will require of it, not by its code
alone:

- the implementation;
- the tests that prove it;
- mechanically consequent documentation, inventories, and owner docstrings for every symbol or module it moves,
  renames, or deletes — the pages the `develop` skill's [Documentation drift](../develop/SKILL.md#documentation-drift)
  section lists;
- the compatibility and integration work repository policy requires — workflow labels, pinned-state fields, comment
  markers, and event payloads are a compatibility contract;
- the final documentation pass every implementation PR receives after reviewer approval
  ([documenting stage](../../../docs/state-machine.md#_handle_documenting-label-workflowdocumenting)).

Point a child body at those sections rather than restating them. Two kinds of child follow from this closure and must
not be proposed:

- a **checks-only** child — "run the suite", "confirm lint passes", "verify nothing broke" — because every child
  already owes its own checks;
- a **mechanical documentation cleanup** child for work a prerequisite already owes — updating names, inventories,
  counts, diagrams, or descriptions because another child moved, renamed, or removed something. That child's own
  scope and its final documentation pass cover it.

## The residual test

Before emitting any split, run this for every proposed child B:

1. Collect every **direct and transitive** prerequisite of B.
2. Assume they have all landed **completely** on the base: implementation, tests, consequent documentation,
   compatibility and integration work, and their final documentation pass.
3. Re-read B against that repository.
4. B survives only if it keeps at least one **unique acceptance criterion** and a **predicted non-empty diff** that
   delivers it.
5. A B whose criteria one prerequisite already delivers, or several deliver between them, has no residual work: fold
   its requirements into the children that own them, or redraw the split.

Evaluate the prerequisites as one completed set, never edge by edge. If A delivers X and C delivers Y, a B that depends
on both and promises only X and Y has nothing left, even though neither A nor C alone contains it. Dependencies order
work; they do not make overlapping scopes independent.

Also compare siblings with no dependency edge between them for **duplicate semantic ownership**: two children that
promise the same behavior are a defect whatever files they list. File overlap is a hint, not a verdict, in either
direction — children editing the same file can each own distinct behavior, and file-disjoint children can still
duplicate one requirement. Never require each child to own a file no sibling touches.

## Worked cases

- **Removal.** The child that deletes a helper or module also owns the inventory entries, prose, and docstrings that
  name it. Put likely grep targets in its body — for example the entry under `docs/architecture/`, the stage page under
  `docs/state-machine/`, and the owner module's docstring — so its implementer knows where to look. A separate "remove
  the documentation for X" child has no residual work.
- **Same file, distinct behavior.** Two children that both edit one stage module — one adding a park, one changing a
  retry budget — are valid when each carries its own acceptance criterion and tests. The shared file is not a conflict
  to split around.
- **Dormant prerequisite, then activation.** A prerequisite may land dormant — built, directly tested, documented, and
  reached by nothing in production — when that is safe. Its scope is its declared slice, not every future consumer.
  The child that wires it into the tick, prompt, or handler owns real activation work: the call site, the recovery and
  failure paths, the integration tests, and the documentation of the live behavior.
- **Docs-only child.** Valid only for an independently valuable deliverable that still remains once every prerequisite
  has landed — a migration guide, an operator runbook, a tutorial, a cross-cutting conceptual page. Its whole diff may
  then be documentation. Re-describing what another child changed is not such a deliverable.

## Child bodies

Every child body states:

- its **unique deliverable** and the **acceptance criteria** that prove it;
- the **likely owners and files**, including the documentation pages and docstrings it must update;
- its **verification** — the tests it adds or updates and the checks it runs;
- its **dependencies**, matching `depends_on`, and what it assumes they delivered.

## Stage contracts

### Initial decomposition

- **Coverage.** Assign every parent requirement exactly once, to one child or to an explicitly named residual parent
  diff. Then re-read the parent as if every child had landed completely. When nothing remains, set `"umbrella": true`.
  Use `"umbrella": false` only when the parent keeps a named, non-empty deliverable of its own, and describe that
  residual in the `rationale` so the parent's later implementation run has a clear handoff.
- **Sizing.** Count completion-closure files — tests, consequent documentation, docstrings — under the prompt's
  approximately-five-file heuristic. Keep coupled documentation attached to the change that forces it: detaching it to
  shrink a file count creates exactly the cleanup child rejected above.
- **No safe split.** When the closed scope cannot be cut without an empty or overlapping child, return `"single"` in the
  `orchestrator-manifest` block, and hand the implementer your groundwork through `affected_files` and `notes`.
- **Clarification.** End with a question for the human and emit no manifest, as the prompt says.

### Late adjudication

- **Coverage.** Partition the declared scope completely among the children, each part owned by exactly one. There is
  no `umbrella` field here and no parent coding pass to reserve work for.
- **Slicing.** Before answering `single`, consider dependency-ordered slices, dormant prerequisites included, as the
  prompt requires.
- **Sizing.** Each child's `estimated_added_lines` counts the lines it adds over every path in its diff —
  implementation, tests, documentation, fixtures, generated files — stays strictly below the ceiling the prompt
  supplies, and leaves headroom for review fixes. The five-file heuristic does not apply and does not replace this
  budget.
- **No safe split.** Answer `"single"` in the `orchestrator-late-manifest` block with a `split_blocker` naming what
  makes a safe split unavailable. That verdict publishes nothing: it hands the publication decision to a human.
- **Clarification.** Ask through the `"question"` decision inside the block; prose alone is not an outcome here.

In both stages keep the prompt's child limit, lineage rules, decision semantics, and clarification format, and never
carry one stage's fence, fields, or meaning of `single` into the other.
