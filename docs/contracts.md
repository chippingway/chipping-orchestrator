---
description: >-
  Project contracts, invariants, and compatibility boundaries, with links to their specifications and checks.
---
# Contracts and invariants

Read this register before investigating or changing the project. Follow the specifications for the area you touch;
they own protocol details. Workspace and scope rules belong to [AGENTS.md](../AGENTS.md).

Use this checklist when reviewing a change; each ID links to its limits, specifications, and checks.

| ID | Rule |
| --- | --- |
| [C-01] | Keep durable workflow state in the issue's workflow label and pinned JSON comment. |
| [C-02] | Orchestrator relabels leave at most one current workflow label and preserve repository labels. |
| [C-03] | Change current formats and public names only deliberately; never treat unsupported input as current. |
| [C-04] | Authenticate pinned state separately from the allowlist that controls issue and comment input. |
| [C-05] | Run pollers on one host with the same explicit `WORKTREES_DIR`; hold claims from first read to last write. |
| [C-06] | Treat unconfirmed writes as unknown; read back what landed before retrying publication. |
| [C-07] | Agents never push; the orchestrator never merges PRs and checks the commit and remote head before pushing. |
| [C-08] | Update reply parsers when prompts change the reply format. |
| [C-09] | Bind approval to one PR head, requirements revision, and developer report backed by passing verification. |
| [C-10] | Honor `paused`/`backlog` and each park's recorded reason for waiting for a human. |
| [C-11] | Never load a GitHub token (`GITHUB_TOKEN` or its aliases) from `.env`. |
| [C-12] | Keep logs and analytics out of decisions; read the audit log only to avoid recording a base rebase twice. |
| [C-13] | Import shared helpers from the module that defines them; read settings through `orchestrator.config`. |
| [C-14] | Resume sessions with their pinned command's original backend and arguments. |
| [C-15] | Never refund charges against an issue's lifetime `MAX_AGENT_RUNS_PER_ISSUE` budget. |

## Terms used here

- **Tick:** one polling pass over a configured repository.
- **Pinned state:** the workflow's JSON record in a dedicated comment on the GitHub issue.
- **Writer claim:** a per-issue exclusive lock under `WORKTREES_DIR`; it only excludes pollers on the same host using
  the same `WORKTREES_DIR`.
- **Pinned command:** the agent backend and command-line arguments saved in pinned state when a role first runs.
- **Park:** a recorded wait for human action; its reason determines what action allows work to resume.
- **Requirements revision:** a content hash identifying the issue requirements and human guidance handed to an agent.
- **Host records:** local files under `WORKTREES_DIR` that coordinate pollers or retain recovery state.

## C-01: Durable workflow state and recovery

**Rule: Keep durable workflow state in the issue's workflow label and pinned JSON comment.**

**Why:** Progress stays visible to humans without another authoritative workflow database.

**Limits:** Recovery also uses per-issue worktrees,
[host records](configuration/operations.md#running-more-than-one-poller) under `WORKTREES_DIR`, and the audit-log
read-back in [C-12]. Treat `WORKTREES_DIR` as state and follow its cleanup rules. The pinned comment admits only
supported version-1 records authored by the orchestrator token account; malformed or unsupported pinned comments
are preserved unchanged and never overwritten, duplicated, or silently upgraded.

**Specs:** [state](architecture.md#design-constraints), [restarts](configuration/operations.md#what-survives-a-restart).

**Checks:** [pinned state](../tests/github/test_pinned_state.py),
[quota recovery](../tests/workflow/stages/implementing/test_quota_retirement_host.py).

## C-02: Workflow labels and transitions

**Rule: Orchestrator relabels leave at most one current workflow label and preserve repository labels.**

**Why:** Routing stays predictable without erasing repository metadata.

**Limits:** A workflow label is a current `WorkflowLabel` member or its exact canonical string, and a control label a
`ControlLabel` one; seven carry no prefix and are canonical as spelled: `in_review`, `question`, `discussion`, `done`,
`rejected`, `backlog`, and `paused`. Every other name is repository metadata, an obsolete bare spelling such as `ready`
or `fixing` included: it selects no stage, authorizes no artifact ownership, and survives every relabel, alone or
beside the canonical label of the state it resembles. Human edits can leave multiple workflow labels; readers tolerate
them. Guard exemptions are listed in the label specification.

**Specs:** [labels and guards](state-machine/labels-and-state.md#workflow-labels),
[obsolete labels](state-machine.md#obsolete-bare-labels).

**Checks:** [label writes](../tests/github/test_workflow_label_write.py),
[guards](../tests/workflow/test_state_guards.py), [resolution](../tests/workflow/test_label_namespace.py).

## C-03: Persisted and externally consumed formats

**Rule: Change current formats and public names only deliberately; never treat unsupported input as current.**

**Why:** Live issues and external consumers depend on the formats the current release writes, and unsupported input
taken as current could start work or license an irreversible effect.

**Limits:** Current formats include pinned-state keys (with explicit integer `schema_version: 1`), workflow labels,
comment markers, watermarks, event formats, branch/ref names, host record formats, agent command specs, and logger
names. Public Python names are the explicit `__all__` exports [C-13] covers. An internal refactor changes none of them;
a deliberate change updates the affected contracts, specifications, and tests with the behavior.

The 1.0 release preparation supports current formats only: breaking changes have already landed, and earlier state has
no promised conversion or continuity. Pinned-state admission accepts only version 1; records missing `schema_version` or
carrying non-integer, float, boolean, string, or unsupported integer versions are refused, preserved unchanged, and
cannot authorize work or dependent effects; ordinary dispatch refuses such an issue from the reading taken under its
writer claim, before any guard, reconciliation, or handler acts, and holds every later reading it acts on to admission
too. Genuine new pins are stamped with version 1 on first write. Cleanup that removes a historical format, alias, or
Python call signature needs no compatibility reader, migration, or final 0.x release. A contract for current output does
not oblige readers to accept earlier formats, nor functions to accept callers' obsolete argument aliases. This decision
sets no compatibility or deprecation policy for later releases.
Historical forms the runtime still reads stay documented in their specifications until their owners remove them.

Unsupported input cannot serve as fresh work, current evidence, or authorization to publish or delete artifacts. Neither
a format change nor a refusal grants permission to discard that input or the artifacts it names; the owning
specification says what a reader does with it. Close observation, recovery, and cleanup read an unsupported record as
neither a fresh owner nor a cycle with nothing left owed, and write nothing for it. Current-format authentication
[C-04], writer claims and artifact ownership [C-05], guarded and uncertain-write recovery [C-06], approval evidence
[C-09], pinned session commands [C-14], lifetime run accounting [C-15], and the audit-log recovery exception [C-12]
remain required. Optional fields the current format defines and current transactions a crash or lost write interrupted
are current state, not historical compatibility.

**Specs:** [state](state-machine/labels-and-state.md#pinned-state),
[branches](security.md#scheduled-artifact-reclamation),
[refs](security.md#the-snapshot-ref-namespace),
[host records](configuration/operations.md#running-more-than-one-poller),
[command specs](workflow.md#in-flight-session-lock--pinned-full-spec-until-the-session-ends),
[events](observability/event-streams.md#audit-event-log-event_log_path),
[loggers](../.agents/skills/develop/SKILL.md#workflow-owners-and-stage-modules),
[evidence](security.md#what-a-trusted-pinned-record-still-cannot-license),
[dispatch admission](state-machine/labels-and-state.md#per-tick-flow-workflowengineticktick),
[deployment without migration](configuration/operations.md#deploying-without-migration),
[close recovery](state-machine/delivery-stages.md#closed-owner-cleanup-sweep-no-label-of-its-own).

**Checks:** [state](../tests/github/test_pinned_state.py), [events](../tests/github/test_events.py),
[refused closes](../tests/workflow/engine/test_dispatch_refused_record_cleanup.py),
[dispatch admission](../tests/workflow/engine/test_dispatch_record_admission.py),
[later readings](../tests/workflow/engine/test_dispatch_admitted_rereads.py).

## C-04: Authentic state and trusted input

**Rule: Authenticate pinned state separately from the allowlist that controls issue and comment input.**

**Why:** A trusted author cannot make forged state authentic, and authentic state cannot make untrusted input safe.

**Limits:** Authentic state requires both bot authorship and whole-comment marker verification before schema admission,
and with no known bot account nothing is authentic. A comment passing authentication is admitted only if its payload
is a JSON object carrying integer `schema_version == 1`. Authentication alone does not authorize publication or
cleanup; those also require
[current evidence](security.md#what-a-trusted-pinned-record-still-cannot-license).

**Specs:** [authentication](security.md#pinned-state-authentication),
[author trust](security.md#comment-trust-boundary-allowed_issue_authors).

**Checks:** [state](../tests/github/test_pinned_state.py), [startup refusal](../tests/cli/test_composition.py).

## C-05: Writer claims and artifact maintenance

**Rule: Run pollers on one host with the same explicit `WORKTREES_DIR`; hold claims from first read to last write.**

**Why:** The claim excludes a second orchestrator writer, so code under it can rely on its own writes as checkpoints.

**Limits:** Do not add code that adopts, reconciles, or repairs a second orchestrator writer's changes during a claim.
The default `WORKTREES_DIR` follows the first configured repository, so pollers with different repository lists can
resolve different roots. Artifact maintenance needs
[exclusive access to that host's worktrees](architecture.md#process-model). Handle crashes, external changes, and
records written before acquiring the claim; [C-06] covers lost or refused writes and comment capacity. Close
observation, recovery, and cleanup admit the record they act on from a read under the issue's claim, the poll's
alongside one included; a close held in memory never stands in for that record.

**Specs:** [ownership](architecture.md#design-constraints), [claims](architecture.md#process-model),
[poller setup](configuration/operations.md#running-more-than-one-poller).

**Checks:** [dispatch claims](../tests/workflow/engine/test_dispatch_writer_claims.py),
[claimed admission](../tests/workflow/engine/test_dispatch_record_admission.py),
[host exclusion](../tests/runtime/test_exclusion.py).

## C-06: Guarded writes and recoverable effects

**Rule: Treat unconfirmed writes as unknown; read back what landed before retrying publication.**

**Why:** An unconfirmed write proves neither success nor absence of an effect.

**Limits:** Recovery rechecks prerequisites. An unreadable record or artifact does not prove the write failed. Close
recovery answers a record admission refuses as an unreadable one: the close it read is kept, and nothing is posted,
marked, or reclaimed over it.
A refused or unconfirmed write stops the steps that depend on it; a later tick reads state afresh. Guarded commits
and direct writes check admission: neither writer may overwrite an unsupported or malformed authoritative comment,
create a replacement beside it, or silently stamp it as current, whatever comment id its caller holds, and neither
sends a state the next reading would refuse; strict edits remain non-creating, and a direct write over such a comment
raises, so the steps depending on it stop.
Writer exclusion comes from [C-05].

**Specs:** [transactions](state-machine/labels-and-state.md#pinned-state),
[publication evidence](security.md#what-a-trusted-pinned-record-still-cannot-license),
[base-rebase recovery](architecture.md#push-path-gitbranch_transport_push_branch),
[base-rewrite finalization](state-machine/delivery-stages.md#the-base-rewrite-finalization-contract),
[ready-ping publication](state-machine/delivery-stages.md#the-ready-ping-publication-contract).

**Checks:** [guarded commits](../tests/workflow/engine/test_pinned_commit.py),
[recovery checkpoints](../tests/git/base_sync/test_persistence.py),
[captured-run abandonment](../tests/workflow/engine/test_rewrite_landing_moved.py),
[finalization checkpoints](../tests/workflow/engine/test_rewrite_finish_writes.py),
[ready-ping recovery](../tests/workflow/stages/in_review/test_ready_ping_recovery.py),
[refused close recovery](../tests/workflow/stages/decomposition/test_late_refused_closes.py),
[admitted read-back](../tests/workflow/engine/test_dispatch_current_recovery.py).

## C-07: Publication authority and exact revisions

**Rule: Agents never push; the orchestrator never merges PRs and checks the commit and remote head before pushing.**

**Why:** Humans decide which PRs merge. Checking the inspected commit and expected remote branch head protects
intervening work.

**Limits:** Human maintainers may push; their changes to the remote branch are external changes the orchestrator must
handle. The publication protocol defines the commit and remote branch head checks and commit-selection fallbacks.
Credential filtering does not enforce push authority; see [C-11].

**Specs:** [pushes](architecture.md#push-path-gitbranch_transport_push_branch),
[human merges](state-machine.md#_handle_in_review-label-in_review).

**Checks:** [transport](../tests/git/test_push.py),
[rewrite publication](../tests/workflow/engine/test_rewrite_publication.py),
[human merge handoff](../tests/workflow/stages/in_review/test_routing.py).

## C-08: Agent reply protocols

**Rule: Update reply parsers when prompts change the reply format.**

**Why:** Replies must mean what the prompt requested.

**Limits:** Malformed replies follow the role's policy for retries or human guidance. Session identity is covered by
[C-14].

**Specs:** [reply protocols](workflow.md).

**Checks:** [report prompts](../tests/workflow/engine/test_prompts_developer_report.py).

## C-09: Reports, review subjects, and verification

**Rule: Bind approval to one PR head, requirements revision, and developer report backed by passing verification.**

**Why:** Changed requirements or reports invalidate approval even on an unchanged head.

**Limits:** Evidence and approval may carry across a rewrite only when the verification protocol proves they apply
to the new revision. The ready ping announces an approval only over current passing evidence proved at the ping.

**Specs:** [reports](workflow.md#developer-report-contract-in-developer-prompts),
[verification](workflow/conversations.md#the-reviewer-verification-contract),
[readiness](state-machine/delivery-stages.md#the-readiness-proof-at-the-ping).

**Checks:** [subjects](../tests/workflow/engine/test_review_subjects.py),
[verification](../tests/workflow/engine/test_verification_current.py),
[readiness](../tests/workflow/stages/in_review/test_readiness_proof.py).

## C-10: Pauses and parks

**Rule: Honor `paused`/`backlog` and each park's recorded reason for waiting for a human.**

**Why:** Resuming work requires the action that answers the specific hold or park.

**Limits:** A hold does not undo earlier writes or commits. Lifetime agent-run charges and the grant that permits
further runs are covered by [C-15].

**Specs:** [controls](state-machine/labels-and-state.md#workflow-labels),
[waiting for human action](state-machine.md#per-tick-flow-workflowengineticktick),
[retry budget](state-machine/labels-and-state.md#the-retry-budget).

**Checks:** [live holds](../tests/workflow/engine/test_guards_paused.py),
[review parks](../tests/workflow/stages/in_review/test_parked.py),
[retry-cap parks](../tests/workflow/engine/test_retry_budget.py).

## C-11: Credentials and execution boundaries

**Rule: Never load a GitHub token (`GITHUB_TOKEN` or its aliases) from `.env`.**

**Why:** A checkout's `.env` sits beside agent worktrees, so keeping tokens out removes an easy leak; this is defense
in depth, not isolation.

**Limits:** There is no exception for `.env` loading. Environment filtering does not isolate agents or verification
commands: they run as the orchestrator's OS user and can read its credential files. Isolation comes from the host,
container, or VM.

**Specs:** [tokens](configuration.md#github-personal-access-token),
[push authentication](architecture.md#push-path-gitbranch_transport_push_branch),
[filtering](architecture.md#environment-filtering-agentsenvironmentfilter_agent_env).

**Checks:** [`.env` loading](../tests/config/test_dotenv.py),
[resolution](../tests/config/test_credentials.py), [transport](../tests/git/test_credentials.py).

## C-12: Observation and the audit recovery exception

**Rule: Keep logs and analytics out of decisions; read the audit log only to avoid recording a base rebase twice.**

**Why:** Logs and analytics must not become a second workflow database.

**Limits:** The base-rewrite finish reads the configured audit log and its rotated copies to avoid duplicate
`base_rebased` events, which record rebases onto the updated base branch. An unreadable log holds that finish.
Deleting a rotated copy or truncating the log without keeping a copy while a finish awaits retry can emit
`base_rebased` twice.

**Specs:** [audit recovery](observability/event-streams.md#audit-event-log-event_log_path).

**Checks:** [rewrite events](../tests/workflow/engine/test_rewrite_finish_event_stream.py),
[rotation](../tests/github/test_event_log.py).

## C-13: Module ownership and public surfaces

**Rule: Import shared helpers from the module that defines them; read settings through `orchestrator.config`.**

**Why:** Importing from one module keeps test patches and runtime calls on the same implementation.

**Limits:** Declared public exports are the supported entry points, changed only as [C-03] allows; importing workflow
labels must still leave the workflow engine unloaded.

**Specs:** [ownership](architecture.md#top-level-layout),
[development conventions](../.agents/skills/develop/SKILL.md#workflow-owners-and-stage-modules).

**Checks:** [imports](../tests/workflow/test_imports.py), [exports](../tests/repository/test_package_exports.py).

## C-14: Pinned session commands

**Rule: Resume sessions with their pinned command's original backend and arguments.**

**Why:** A configuration change must not retarget an existing conversation or discard its model and reasoning settings.

**Limits:** Reviewers start fresh with current configuration. A failed developer conversation's replacement keeps
its pinned command.

**Specs:** [session commands](workflow.md#in-flight-session-lock--pinned-full-spec-until-the-session-ends).

**Checks:** [session pins](../tests/workflow/stages/implementing/test_full_spec_dev.py),
[fresh reviewers](../tests/workflow/stages/implementing/test_full_spec_reviewer.py).

## C-15: Lifetime agent-run budget

**Rule: Never refund charges against an issue's lifetime `MAX_AGENT_RUNS_PER_ISSUE` budget.**

**Why:** Crashes, retries, and restarts must not let an issue evade its lifetime run limit.

**Limits:** Only a trusted `/orchestrator add-agent-runs N` grants more runs to an issue parked at its lifetime limit;
other budgets have their own rules.

**Specs:** [run budget](state-machine/labels-and-state.md#the-agent-run-circuit),
[charging before launch](security.md#bounded-agent-spend-per-issue-max_agent_runs_per_issue).

**Checks:** [charging](../tests/workflow/engine/test_run_circuit.py).

## Maintaining the contracts

Update affected contracts, specifications, implementation, and behavioral tests together. Keep IDs and section titles
stable: links use the full heading anchor, so renaming a title breaks them even when the ID stays the same. Never
reuse retired IDs. Keep each checklist row identical to its section's Rule. Keep each contract section in
Rule / Why / Limits / Specs / Checks order, with one central rule; Limits covers scope, exceptions, and additional
obligations. Protocol details and decision history belong in the linked specifications.

Linked tests are representative checks, not proof of every clause.
[Documentation checks](../tests/repository/test_doc_links.py) validate links, navigation, the required-reading route
from AGENTS.md, the instruction pages' links to [C-03], and the route to the deployment procedure. They also hold this
register's IDs and heading anchors, each checklist row against its section's Rule, and the section order; they do not
verify behavioral claims.

[C-01]: #c-01-durable-workflow-state-and-recovery
[C-02]: #c-02-workflow-labels-and-transitions
[C-03]: #c-03-persisted-and-externally-consumed-formats
[C-04]: #c-04-authentic-state-and-trusted-input
[C-05]: #c-05-writer-claims-and-artifact-maintenance
[C-06]: #c-06-guarded-writes-and-recoverable-effects
[C-07]: #c-07-publication-authority-and-exact-revisions
[C-08]: #c-08-agent-reply-protocols
[C-09]: #c-09-reports-review-subjects-and-verification
[C-10]: #c-10-pauses-and-parks
[C-11]: #c-11-credentials-and-execution-boundaries
[C-12]: #c-12-observation-and-the-audit-recovery-exception
[C-13]: #c-13-module-ownership-and-public-surfaces
[C-14]: #c-14-pinned-session-commands
[C-15]: #c-15-lifetime-agent-run-budget
