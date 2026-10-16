---
description: >-
  The label-based state machine that drives each GitHub issue from pickup to a terminal label, with its
  pinned-state keys and what each stage handler does.
---
# Workflow state machine

This area documents the label-based state machine that drives every GitHub issue from pickup to terminal. It is split
out of [`architecture.md`](architecture.md), which keeps the high-level overview, the top-level module map, and the
process / agent / push model. Workflow labels and pinned-state JSON keys are a compatibility contract — live issues
already carry them — so this area is where label spelling, the transitions between them, and each handler's behavior
are authoritative.

## The pages in this area

- [Labels and state](state-machine/labels-and-state.md) owns the label vocabulary, per-tick sequence, and pinned schema.
- [Delivery stages](state-machine/delivery-stages.md) owns pickup, drift, decomposition, publication, and review.
- [Conversation stages](state-machine/conversation-stages.md) owns the `question` and `discussion` handlers.
- [Lifecycle](state-machine/lifecycle.md) shows the main routes between labels.

The summaries below preserve the section addresses used by existing links. Agent prompt contracts belong to
[workflow](workflow.md); module ownership belongs to [architecture](architecture.md).

## Workflow labels

An issue has at most one workflow label; unrelated repository labels are preserved. A `workflow:<tag>` string is the
GitHub label, while its bare tag names the stage in handlers and analytics. `in_review`, `question`, `discussion`,
`done`, and `rejected` keep their bare spelling. `backlog`, `paused`, and `workflow:community_contribution` are control
labels outside that workflow slot. The [label reference](state-machine/labels-and-state.md#workflow-labels) defines
each label and control.

### Typed states and the transition guard

`WorkflowLabel` and `ControlLabel` define the vocabulary. `GitHubClient.set_workflow_label` rejects unknown workflow
labels and checks orchestrator transitions under `WORKFLOW_TRANSITION_GUARD`; human relabels bypass that check.
The [typed-state reference][typed-states] owns the graph, guard modes, and write exceptions.

### Legacy labels and the migration off them

Startup renames a legacy label in place when its namespaced counterpart does not exist. Routing still accepts either
spelling where migration could not run, preferring the namespaced label when both are present. The
[migration reference][legacy-labels] defines bootstrap and compatibility behavior.

<a id="per-tick-flow-workflowtick"></a>

## Per-tick flow (`workflow.engine.tick.tick`)

Each repository pass refreshes base and worktrees, sweeps community pull requests, emits the skill catalog, and
dispatches pollable issues. Family-aware work runs sequentially within a repository; independent issues share the
global and per-repository scheduler limits. Host-local writer claims prevent two pollers from acting on the same
issue concurrently. The [per-tick reference][per-tick] owns ordering, dispatch holds, and dependency-poll cadence.

### Base refresh

The refresh fetches the remote base once per repository and rebases eligible worktrees under their issue claims.
A clean rebase of an existing pull request is size-gated, published with a lease, and returned to validation; actual
conflicts route to `workflow:resolving_conflict`. The
[base-refresh reference](state-machine/labels-and-state.md#base-refresh)
owns frozen-state exclusions, rewrite evidence, report debt, and interrupted-attempt recovery.

### Pollable issues and finalization

Polling includes open non-PR issues and a periodic sweep of closed issues whose workflow still owes finalization or
cleanup. The [polling reference][pollable] lists the swept labels, legacy spellings, and conversation exceptions.

### Pinned state

One authenticated pinned comment (`<!--orchestrator-state {...json...}-->`) stores an issue's durable workflow state:
sessions, family relationships, publication and review subjects, recovery records, watermarks, parks, and budgets.
Some writers replace the record whole; guarded writers merge their owned fields over a fresh reading and refuse
changed or unconfirmed state. The [pinned-state reference](state-machine/labels-and-state.md#pinned-state) owns every
field, its consumers, and the write contract.

## Stage handlers

The workflow label selects a handler after shared dispatch guards and transaction reconciliation. Closed family
owners take the cleanup route instead. The following summaries link to each handler's authoritative flow.

### `_handle_pickup` (no label → `workflow:decomposing` or `workflow:implementing`)

A trusted, unlabeled new issue gets its pickup comment and initial state, then enters decomposition or implementation
according to `DECOMPOSE`. An issue with existing pinned state is screened by the reuse guard first.
The [pickup handler][pickup] owns initialization and same-tick routing.

### User-content drift detection

Drift-sensitive stages compare trusted issue content with the recorded baseline. An edit can restart decomposition,
resume the developer, or return final documentation to validation; fixing and conversation handlers skip this hook.
The [drift reference][drift] defines filtering, reply delivery, and stage-specific routing.

### `_handle_decomposing` (label `workflow:decomposing`)

Initial decomposition runs the decomposer read-only and consumes its manifest: `single` advances to `workflow:ready`,
while `split` creates a dependency family. A live late generation uses the same label for adjudicating a committed,
oversized candidate. The [decomposing handler][decomposing] owns both routes and their recovery.

### `_handle_ready` (label `workflow:ready` → `workflow:implementing`)

The [ready handler][ready] records the pickup and comment floor, then advances to implementation in the same tick.

### `_handle_blocked` (label `workflow:blocked`)

The [blocked handler][blocked] releases children whose dependencies are done and advances a parent to `workflow:ready`
once all its children finish. A rejected or manually closed child parks the parent; a blocked leaf waits.

### `_handle_umbrella` (label `workflow:umbrella`)

An umbrella has no implementation of its own. The [umbrella handler][umbrella] walks dependencies and settles any late
split cleanup before closing the issue as `done` after its children finish.

### `_handle_implementing` (label `workflow:implementing`)

The [implementing handler][implementing] runs or resumes the pinned developer in the issue worktree. Clean committed
work passes report recording and the size gate before publication and handoff to `workflow:validating`; oversized
work returns to decomposition. Its reference owns retry parks, quota retirement, and stranded-work recovery.

### `_handle_documenting` (label `workflow:documenting`)

The [documenting handler][documenting] resumes the developer for the final documentation pass after approval. It
publishes eligible docs work, records the head-specific completion, and hands the pull request to `in_review`;
changed requirements or a rewritten head can require validation again.

### `_handle_validating` (label `workflow:validating`)

The [validating handler][validating] obtains a current developer report and spawns a fresh reviewer over that subject.
Approval with passing verification proceeds through the optional squash to documenting; a change request enters
fixing. The handler reference owns review budgets, evidence settlement, and approval recovery.

### The size gate on a published pull request (every push onto an open PR)

Every publication onto an existing pull request gates the cumulative candidate against the remote base before a
named, leased push. Oversized work is held for adjudication; only proven, authorized rewrites may carry an existing
exemption. The [published-candidate gate][published-gate] owns the publication paths, barriers, and recovery.

### `_handle_in_review` (label `in_review`)

The [in-review handler][in-review] observes external merge or close decisions, routes unread human feedback to fixing,
and returns stale approvals to validation. A ready, currently approved head gets a one-time human ping; the
orchestrator does not merge it.

### `_handle_fixing` (label `workflow:fixing`)

The [fixing handler][fixing] resumes the developer for reviewer or human feedback, honoring the human-feedback quiet
window and delivery watermarks. Published fixes and report-only rounds return to validation; its reference owns
round accounting, recovery, and conflict routing.

### `_handle_resolving_conflict` (label `workflow:resolving_conflict`)

The [conflict handler][resolving-conflict] rebases the pull request branch, resumes the developer where conflicts need
resolution, and publishes with a lease before returning to validation. Rewritten heads owe a fresh developer report;
the handler reference defines replay evidence, recovery, and conflict-round limits.

### `_handle_question` (label `question`)

The [question handler][question] runs read-only Q&A with a separately pinned decomposer session, posts each answer,
and waits for a trusted reply. It opens no pull request; closing the issue ends the conversation as `done`.

### `_handle_discussion` (label `discussion`)

The [discussion handler][discussion] explores a design with humans. After confirmation it may publish only
`plans/issue-<number>.md` as a plan pull request; merging or closing that pull request determines the terminal label.

## State transition (label lifecycle)

The [lifecycle diagram](state-machine/lifecycle.md) shows the forward route, family branches, review loop, conflicts,
conversation endings, and human-wait behavior.

[typed-states]: state-machine/labels-and-state.md#typed-states-and-the-transition-guard
[legacy-labels]: state-machine/labels-and-state.md#legacy-labels-and-the-migration-off-them
[per-tick]: state-machine/labels-and-state.md#per-tick-flow-workflowengineticktick
[pollable]: state-machine/labels-and-state.md#pollable-issues-and-finalization
[pickup]: state-machine/delivery-stages.md#_handle_pickup-no-label--workflowdecomposing-or-workflowimplementing
[drift]: state-machine/delivery-stages.md#user-content-drift-detection
[decomposing]: state-machine/delivery-stages.md#_handle_decomposing-label-workflowdecomposing
[published-gate]: state-machine/delivery-stages.md#the-size-gate-on-a-published-pull-request-every-push-onto-an-open-pr
[ready]: state-machine/delivery-stages.md#_handle_ready-label-workflowready--workflowimplementing
[blocked]: state-machine/delivery-stages.md#_handle_blocked-label-workflowblocked
[umbrella]: state-machine/delivery-stages.md#_handle_umbrella-label-workflowumbrella
[implementing]: state-machine/delivery-stages.md#_handle_implementing-label-workflowimplementing
[documenting]: state-machine/delivery-stages.md#_handle_documenting-label-workflowdocumenting
[validating]: state-machine/delivery-stages.md#_handle_validating-label-workflowvalidating
[in-review]: state-machine/delivery-stages.md#_handle_in_review-label-in_review
[fixing]: state-machine/delivery-stages.md#_handle_fixing-label-workflowfixing
[resolving-conflict]: state-machine/delivery-stages.md#_handle_resolving_conflict-label-workflowresolving_conflict
[question]: state-machine/conversation-stages.md#_handle_question-label-question
[discussion]: state-machine/conversation-stages.md#_handle_discussion-label-discussion
