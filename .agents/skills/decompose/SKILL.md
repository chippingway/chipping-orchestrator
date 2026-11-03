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
- the format and integration work repository policy requires — workflow labels, pinned-state fields, comment
  markers, and event payloads keep their current formats under
  [C-03](../../../docs/contracts.md#c-03-persisted-and-externally-consumed-formats), so a child that deliberately
  changes one updates the affected contracts, specifications, and tests with it, and one that removes a historical
  format owes no migration or compatibility reader;
- the final documentation pass every implementation PR receives after reviewer approval
  ([documenting stage](../../../docs/state-machine.md#_handle_documenting-label-workflowdocumenting)).

Point a child body at those sections rather than restating them. Two kinds of child follow from this closure and must
not be proposed:

- a **checks-only** child — "run the suite", "confirm lint passes", "verify nothing broke" — because every child
  already owes its own checks;
- a **mechanical documentation cleanup** child for work a prerequisite already owes — updating names, inventories,
  counts, diagrams, or descriptions because another child moved, renamed, or removed something. That child's own
  scope and its final documentation pass cover it.

## Sizing by scope and effort

The sizing question is whether the complete deliverable — everything in the scope above — fits one coding-agent
context: one implementer investigates it, builds it, proves it, documents it, and carries it through review without
losing the thread. Judge that from:

- the number and complexity of the distinct behaviors it delivers;
- how tightly the changes are coupled — whether one can be built or verified without the others;
- the context an implementer has to read and hold: the owners, contracts, specifications, and tests around them;
- the effort needed to verify the result — new fixtures, failure and recovery paths, integration tests.

File and commit counts can guide inspection, but neither decides single versus split on its own, and no other count
stands in for them as a cutoff. A coherent, manageable change stays one child however many files its completion
touches; a change concentrated in one or two files can still hold several substantial behaviors that each deserve a
child of their own.

When the complete work is too large, split it at meaningful deliverable boundaries: each child delivers a behavior a
reviewer can accept on its own, carries its own acceptance criteria and verification, and is manageable in one
context. Before committing to a split, compare it with the plausible coarser groupings:

- Prefer fewer complete children while their combined scope stays manageable. Every extra child repeats
  investigation, adds integration work, and puts another dependency handoff — a whole implement, review, and merge
  cycle — between the parent and its completion.
- A different file, owner, layer, or display is not on its own a reason for another child. Merge adjacent slices that
  read the same context and share their verification unless the merged child would no longer be manageable.
- The prompt's child limit is a ceiling, not a target. A split that reaches it, or a long serial chain of
  dependencies, is a reason to re-check the coarser groupings, though neither alone proves the split wrong.
- A residual parent implementation is sized by the same rule: once every child has landed, what the parent keeps must
  fit one context by itself.

Explain the decision in the `rationale` by concrete scope and dependencies — the behaviors, their coupling, the
boundaries kept and why — rather than by a raw count.

## The residual test

Before emitting any split, run this for every proposed child B:

1. Collect every **direct and transitive** prerequisite of B.
2. Assume they have all landed **completely** on the base: implementation, tests, consequent documentation,
   format and integration work, and their final documentation pass.
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

- **Many files, one change.** Requiring one new manifest field touches the shared validator, the prompts that state
  the field, the readers of recorded manifests, their tests, and the state-machine, workflow, and architecture pages
  that describe the refusal — a dozen files for one rule with one acceptance criterion and one set of tests. When an
  implementer can hold that context, it stays `single`. Splitting the prompt wording, the validator, or the pages apart
  would leave children that each half-land the rule or have no residual work.
- **Few files, several deliverables.** One stage module gaining a park with its resume path, a reworked retry budget,
  and recovery for a new crash window holds three behaviors, each with its own failure paths, fixtures, and
  documentation. If together they exceed one context, children that each edit that module are a valid split when each
  carries its own acceptance criterion and tests: the shared file is not a conflict to split around. If together they
  stay manageable, they stay one child. The small file count decides neither way.
- **Many candidate slices.** An issue spanning several contracts or subsystems — accounting, capture, recovery, and
  route integrations, say — offers more boundaries than it needs. Start from the coarsest grouping whose children each
  stay manageable. Keep a boundary only where the two sides deliver and verify different behavior, or where one must
  land first for the other to be built or proven, and merge slices that read the same owners and share their tests.
  Before emitting a split at the child limit with nearly every child waiting on another, check whether adjacent links
  in that chain can share one implementation pass.
- **Removal.** The child that deletes a helper or module also owns the inventory entries, prose, and docstrings that
  name it. Put likely grep targets in its body — for example the entry under `docs/architecture/`, the stage page under
  `docs/state-machine/`, and the owner module's docstring — so its implementer knows where to look. A separate "remove
  the documentation for X" child has no residual work.
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
- **Sizing.** Size each child, and any residual parent work, by its complete scope as
  [Sizing by scope and effort](#sizing-by-scope-and-effort) describes. Keep coupled documentation attached to the
  change that forces it: detaching it to make a child look smaller creates exactly the cleanup child rejected above.
- **Single.** When the complete scope is manageable in one context, or cannot be cut without an empty or overlapping
  child, return `"single"` in the `orchestrator-manifest` block, and hand the implementer your groundwork through
  `affected_files` and `notes`.
- **Clarification.** End with a question for the human and emit no manifest, as the prompt says.

### Late adjudication

- **Coverage.** Partition the declared scope completely among the children, each part owned by exactly one. There is
  no `umbrella` field here and no parent coding pass to reserve work for.
- **Slicing.** Before answering `single`, consider dependency-ordered slices, dormant prerequisites included, as the
  prompt requires.
- **Sizing.** Each child's `estimated_added_lines` counts the lines it adds over every path in its diff —
  implementation, tests, documentation, fixtures, generated files — stays strictly below the ceiling the prompt
  supplies, and leaves headroom for review fixes. The scope-and-effort judgment above shapes where slices fall but
  never replaces or loosens this budget: a slice that fits one context still has to clear it, and a coarser grouping
  is viable only while every child still clears it with that headroom.
- **No safe split.** Answer `"single"` in the `orchestrator-late-manifest` block with a `split_blocker` naming what
  makes a safe split unavailable. That verdict publishes nothing: it hands the publication decision to a human.
- **Clarification.** Ask through the `"question"` decision inside the block; prose alone is not an outcome here.

In both stages keep the prompt's child limit, lineage rules, decision semantics, and clarification format, and never
carry one stage's fence, fields, or meaning of `single` into the other.

## Before you emit the manifest

Valid JSON is not a valid manifest. A reply that parses but leaves out a field its decision requires is refused even
though your run exited cleanly — a split whose children all omit `depends_on` is the failure this check exists for.
An initial decomposition's refused manifest is handed back to your session once, with the exact error, for one
complete corrected manifest; a second refusal, and any refusal in late adjudication, parks the issue for a human.
Re-read the block against the active prompt's schema, field by field:

- the fence the prompt names, one block, and nothing after its closing line;
- a `decision` value the prompt allows, and every field that decision requires there;
- on a split, an explicit `depends_on` array on **every** child — `[]` for none, never omitted or `null` — naming
  exactly the prerequisites that child's body and your `rationale` describe, with no self-dependency or cycle;
- the child limit, and in late adjudication each child's `estimated_added_lines` and a `single`'s `split_blocker`.
