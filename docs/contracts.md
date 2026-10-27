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
| [C-10] | Honor `paused`/`backlog`, each dependency hold, and each park's recorded reason for waiting for a human. |
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
them. So can a crash inside the label move a dependency release or a blocked parent's return to `workflow:ready`
makes: it adds the new label before it takes off the one it replaces, so that no hold applied meanwhile is written
away, and the issue's next relabel takes the extra one off. Guard exemptions are listed in the label specification.

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
names. Public Python names are the explicit `__all__` exports [C-13] covers: `orchestrator.agents` publishes its result
model as `AgentResult` alone, and the agent runner and the scheduler's `submit` take only their typed records,
`AgentRunOptions` and `SubmissionRequest`; no keyword form beside them is a current call shape. An internal refactor
changes none of them; a deliberate change updates the affected contracts, specifications, and tests with the behavior.

The 1.0 release preparation supports current formats only: breaking changes have already landed, and earlier state has
no promised conversion or continuity. Pinned-state admission accepts only version 1; records missing `schema_version` or
carrying non-integer, float, boolean, string, or unsupported integer versions are refused, preserved unchanged, and
cannot authorize work or dependent effects; ordinary dispatch refuses such an issue from the reading taken under its
writer claim, before any guard, reconciliation, or handler acts, and holds every later reading it acts on to admission
too. The base refresh refuses one the same way, before any route reads a branch, pull request, or recovery anchor off
it, and the base fetch every worktree shares licenses nothing on its checkout or refs. Genuine new pins are stamped
with version 1 on first write. Cleanup that removes a historical format, alias, or Python call signature needs no
compatibility reader, migration, or final 0.x release. A contract for current output does not oblige readers to accept
earlier formats, nor functions to accept callers' obsolete argument aliases. This decision sets no compatibility or
deprecation policy for later releases.
Historical forms the runtime still reads stay documented in their specifications until their owners remove them.
Analytics and trajectory readers interpret only what current producers write: a field a producer did not report is
unknown rather than inferred from another (a skill load is no evidence of its offer), and a row narrower than its
query's SELECT list raises rather than reading as NULL. A current optional field's absence, an ID-less CLI run, an
unpriced cost, and a malformed record's containment remain current answers. A recorded requirements fingerprint
(`user_content_hash`, `observed_user_content_hash`) is compared with the current fingerprint alone, which leaves bare
operator controls out: a value no current reading reproduces -- one an earlier producer wrote counting a bare
`/orchestrator continue` included -- is drift for the stage's deliberate drift or hold route, and is never recognized
as covering the thread, rewritten in the current spelling, or a baseline a retry is folded into. A first drift check
recording the thread it meets where no reading is recorded, and the observed reading a late adjudication keeps in a
missing baseline's place, remain current initialization and recovery. Verification artifacts are read only in the
compact format, their commands decoded from the hidden payload alone: a comment without it, one an earlier build
published with its commands in view included, is left untouched and is no artifact for verification, a reviewer's
reuse, an approval, or a recovered settlement. No missing field marks human feedback consumed or names a delivered
batch, and no bounded prompt's omission counts as delivered: the PR-feedback readers count as delivered only the stretch
of the issue thread a developer prompt was handed, above `delivered_after_comment_id` through
`delivered_through_comment_id` -- recorded by the first prompt from the newest comment its excerpt cut, moved by a later
settlement, resume, or park walk only where nothing unread stands between it and what that road read, and never by a
pickup, a handoff, or a park's stamp -- while parks and resumes wait on the reply boundary `last_action_comment_id`
alone, which counts nothing as delivered; a record missing either end counts nothing. An in_review watermark a manual
relabel or an approval that could not read its pull request left unset is initialized from recorded delivery alone --
the orchestrator's own posts, that delivered stretch, and bare run-grant controls, never a comment's age nor anything
above what its two thread reads prove complete -- with the review surfaces scanned from 0. A fix round's settlement
moves `pr_last_comment_id` over nothing above what its thread and pull-request reads prove complete, so an issue reply
landing between them is left to the next scan, and a `/orchestrator continue` replay is rebuilt only from the id lists
its route recorded, a list missing or damaged replaying nothing. An approval or permission is read only as its current
writers record it whole: no approval record, an approval beside no evidence claim, a `late_approved_sha` with no
`late_approved_basis` this build can read, and a rewrite permission beside an attempt record with no declared terms are
each no grounds -- never an earlier producer's default -- and authorize no publication, transfer, or ready notification.
An exempt commit with no semantic identity, the settlement's when fingerprinting fails, stays a current record that
exempts that commit alone.

Unsupported input cannot serve as fresh work, current evidence, or authorization to publish or delete artifacts. Neither
a format change nor a refusal grants permission to discard that input or the artifacts it names; the owning
specification says what a reader does with it. Close observation, recovery, and cleanup read an unsupported record as
neither a fresh owner nor a cycle with nothing left owed, and write nothing for it. A parent's split seeds, recovery,
and dependency release read an unsupported child as neither a fresh child to seed nor one to start, and its merge
finalize, snapshot notices, and snapshot delete read one as neither a child to finalize or tell nor a consumer done with
the ref: nothing is written to it, the seed, release, or notice stays uncompleted, and the ref stays. Artifact
maintenance reads an unsupported record as no record at all to classify on, never as an issue that pinned nothing:
every checkout and branch of its issue stays, however the issue ended, and nothing is deleted or written for it. The
flat pre-namespacing layout is unsupported input too: an `orchestrator/issue-<n>` branch or `WORKTREES_DIR/issue-<n>`
checkout is no repository's artifact, and no ownership, terminal, late-split, or scheduled cleanup path adopts or
deletes one, whether the clone holds it or only the remote does.
Current-format authentication [C-04], writer claims and artifact ownership [C-05], guarded and uncertain-write recovery
[C-06], approval evidence [C-09], pinned session commands [C-14], lifetime run accounting [C-15], and the audit-log
recovery exception [C-12] remain required. Optional fields the current format defines and current transactions a crash
or lost write interrupted are current state, not historical compatibility.

**Specs:** [state](state-machine/labels-and-state.md#pinned-state),
[branches](security.md#scheduled-artifact-reclamation),
[refs](security.md#the-snapshot-ref-namespace),
[host records](configuration/operations.md#running-more-than-one-poller),
[command specs](workflow.md#in-flight-session-lock--pinned-full-spec-until-the-session-ends),
[events](observability/event-streams.md#audit-event-log-event_log_path),
[loggers](../.agents/skills/develop/SKILL.md#workflow-owners-and-stage-modules),
[evidence](security.md#what-a-trusted-pinned-record-still-cannot-license),
[dispatch admission](state-machine/labels-and-state.md#per-tick-flow-workflowengineticktick),
[refresh admission](state-machine/labels-and-state.md#base-refresh),
[artifact admission](configuration/operations.md#what-clears-a-candidate-and-what-keeps-it),
[deployment without migration](configuration/operations.md#deploying-without-migration),
[close recovery](state-machine/delivery-stages.md#closed-owner-cleanup-sweep-no-label-of-its-own),
[analytics readers](observability/analytics-dashboard.md#read-model-orchestratorobservabilityanalyticsquery),
[requirements baselines](state-machine/delivery-stages.md#user-content-drift-detection),
[watermark initialization](state-machine/delivery-stages.md#_handle_in_review-label-in_review),
[replay batches](state-machine/labels-and-state.md#pinned-state).

**Checks:** [state](../tests/github/test_pinned_state.py), [events](../tests/github/test_events.py),
[agent surface](../tests/agents/test_imports.py), [submissions](../tests/scheduler/test_submission.py),
[refused closes](../tests/workflow/engine/test_dispatch_refused_record_cleanup.py),
[dispatch admission](../tests/workflow/engine/test_dispatch_record_admission.py),
[later readings](../tests/workflow/engine/test_dispatch_admitted_rereads.py),
[child seeds](../tests/workflow/stages/decomposition/test_claimed_seeds.py),
[refresh admission](../tests/workflow/engine/test_base_refresh.py),
[refreshed tick](../tests/workflow/engine/test_tick_refresh.py),
[snapshot consumers](../tests/workflow/stages/decomposition/test_claimed_reclamation.py),
[artifact admission](../tests/git/worktrees/test_maintenance_admission.py),
[analytics readers](../tests/observability/analytics/query/test_skill_adoption_reads.py),
[verification artifacts](../tests/github/test_verification_artifacts.py),
[requirements baselines](../tests/workflow/engine/test_drift.py),
[late first baselines](../tests/workflow/stages/decomposition/test_late_first_baseline.py),
[watermark initialization](../tests/workflow/stages/in_review/test_watermark_initialization.py),
[delivered thread](../tests/workflow/engine/test_thread_delivery.py),
[timeout parks](../tests/workflow/stages/documenting/test_timeout_delivery.py),
[fix settlement](../tests/workflow/stages/fixing/test_cross_read_race.py),
[replay batches](../tests/workflow/stages/fixing/test_batch.py),
[approval bases](../tests/workflow/stages/implementing/test_late_approval_basis.py),
[rewrite permissions](../tests/git/base_sync/test_transfers.py).

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
records written before acquiring the claim; [C-06] covers lost or refused writes and comment capacity. Artifact
ownership is exact repository and issue attribution of the current layout only: a branch is an issue's when it is that
repository's `orchestrator/<slug>/issue-<n>` character for character, and a checkout when it is that repository's
`WORKTREES_DIR/<slug>/issue-<n>`, a worktree of its clone, on that branch. An `orchestrator/` prefix, a flat name, or an
authentic pin alone is no ownership evidence, so cleanup a record or a scan points at anything else deletes nothing, and
a name two entries derive alike, a checkout standing on one, or a checkout directory two entries are handed belongs to
neither. Terminal, question, and late-split teardowns ask those collision refusals themselves, and every teardown
removes a checkout only where it proves the tree a worktree of the clone on the issue's exact branch, reached at its own
path through no symlink below `WORKTREES_DIR`, so a foreign checkout keeps its files; the scheduled pass reads that
identity again immediately before the removal. Close observation, recovery, and cleanup admit the record they act on
from a read under the issue's claim, the poll's alongside one included; a close held in memory never stands in for that
record. A parent's seed or repair of a child, an adopted one included, its merge finalize of a closed child, its
snapshot notice to a consumer, its release of a group of children, and its delete of a snapshot admit each child's
record from a read under that child's claim, held through the effect; an earlier family scan never stands in for it, and
a release or a delete admits every child it would act on before acting on any. The base refresh admits the record it
routes a worktree on from its read under the claim it holds through that route. Artifact maintenance takes each
candidate's issue claim before it reads the issue, admits the record it classifies on from that read, and holds the
claim through the teardown; a candidate whose claim is refused is left untouched. The scheduler barrier, host
exclusivity, and every other maintenance gate stay required beside it.

**Specs:** [ownership](architecture.md#design-constraints), [claims](architecture.md#process-model),
[artifact ownership](security.md#scheduled-artifact-reclamation),
[poller setup](configuration/operations.md#running-more-than-one-poller),
[family writes](state-machine/labels-and-state.md#per-tick-flow-workflowengineticktick).

**Checks:** [dispatch claims](../tests/workflow/engine/test_dispatch_writer_claims.py),
[claimed admission](../tests/workflow/engine/test_dispatch_record_admission.py),
[refresh claims](../tests/workflow/engine/test_base_refresh_contention.py),
[maintenance claims](../tests/git/worktrees/test_maintenance_guards.py),
[branch attribution](../tests/git/worktrees/test_artifact_attribution.py),
[flat-layout preservation](../tests/git/worktrees/test_maintenance_pass.py),
[terminal cleanup](../tests/git/worktrees/test_terminal.py),
[teardown ownership](../tests/git/worktrees/test_teardown_ownership.py),
[removal races](../tests/git/worktrees/test_maintenance_tips.py),
[host exclusion](../tests/runtime/test_exclusion.py),
[claimed release](../tests/workflow/stages/decomposition/test_claimed_release.py),
[claimed finalize](../tests/workflow/stages/decomposition/test_claimed_closed_children.py).

## C-06: Guarded writes and recoverable effects

**Rule: Treat unconfirmed writes as unknown; read back what landed before retrying publication.**

**Why:** An unconfirmed write proves neither success nor absence of an effect.

**Limits:** Recovery rechecks prerequisites. An unreadable record or artifact does not prove the write failed, and an
incomplete one proves nothing landed: recovery finishes a current transaction from its whole record -- a debt with
its basis, a rewrite permission bound to its attempt's declared terms -- and refuses one missing either. Close
recovery answers a record admission refuses as an unreadable one: the close it read is kept, and nothing is posted,
marked, or reclaimed over it. Snapshot recovery over a ref already gone tells no consumer admission refuses and keeps
that notice owed rather than recording it delivered.
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
[ready-ping publication](state-machine/delivery-stages.md#the-ready-ping-publication-contract),
[ready decision](state-machine/delivery-stages.md#_handle_ready-label-workflowready--workflowimplementing).

**Checks:** [guarded commits](../tests/workflow/engine/test_pinned_commit.py),
[recovery checkpoints](../tests/git/base_sync/test_persistence.py),
[captured-run abandonment](../tests/workflow/engine/test_rewrite_landing_moved.py),
[finalization checkpoints](../tests/workflow/engine/test_rewrite_finish_writes.py),
[ready-ping recovery](../tests/workflow/stages/in_review/test_ready_ping_recovery.py),
[refused close recovery](../tests/workflow/stages/decomposition/test_late_refused_closes.py),
[admitted read-back](../tests/workflow/engine/test_dispatch_current_recovery.py),
[ready recovery](../tests/workflow/stages/decomposition/test_ready_recovery.py).

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
to the new revision. An approval stands only on its own records read whole -- the subject it covers and the evidence
claim it was proved over -- so one missing either is handed back for review, with no squash publication, move, docs
pass, or ready ping over it. The ready ping announces an approval only over current passing
evidence proved at the ping, or, over a final docs pass's recorded completion, only over that completion proved whole
at the ping. Evidence is what an artifact comment of ours carries in its hidden payload, the whole body re-rendering
exactly in the current format; the commands a comment shows count for nothing, and one without the payload binds no
approval and settles no transaction.

The final-documentation exception records a docs pass apart from the approval it followed: the approved review
subject, the settled report and its source commit, and the evidence the approval rests on stay as they were, and the
head the pass completed on is verified on its own -- unchanged, by that evidence with its own provenance; changed, by
a run of exactly that head this orchestrator executed; changed under an empty `VERIFY_COMMANDS`, by nothing, recorded
as no evidence that anything passed. Only that recorded completion lets the run answer for the approved review, and
only bound to the settled report's publication at that head; it is also the only thing that qualifies such a head for
the ready ping, which a docs stamp on it never does. No record says the reviewer was handed the docs commit
or that checks ran on another commit, and a completion missing, malformed, or moved; an approval or its evidence
claim that no longer reads as the one the completion followed; requirements, a report, or a publication that
changed, an edit or a push landing while the proof reads included; the evidence that claim names no longer published
as it settled; a lineage from the approved commit not proved; or a run owed, failed, or incomplete authorizes
nothing, and evidence or an issue nobody could read holds it. Every final docs pass that finishes records that
completion and goes straight to review: documentation alone buys no fresh review, developer report, or review round,
and a docs commit the configured run does not pass on is offered to nobody.

**Specs:** [reports](workflow.md#developer-report-contract-in-developer-prompts),
[verification](workflow/conversations.md#the-reviewer-verification-contract),
[readiness](state-machine/delivery-stages.md#the-readiness-proof-at-the-ping),
[final-documentation records](state-machine/labels-and-state.md#pinned-state).

**Checks:** [subjects](../tests/workflow/engine/test_review_subjects.py),
[unrecorded approvals](../tests/workflow/stages/in_review/test_routing.py),
[unapproved squash recoveries](../tests/workflow/stages/validating/test_squash_approval_real_git.py),
[claimless approvals](../tests/workflow/stages/documenting/test_unchanged_evidence.py),
[verification](../tests/workflow/engine/test_verification_current.py),
[readiness](../tests/workflow/stages/in_review/test_readiness_proof.py),
[final documentation](../tests/workflow/engine/test_final_docs_proof.py),
[final-head runs](../tests/workflow/stages/documenting/test_final_verification.py),
[final-docs completion](../tests/workflow/stages/validating/test_changed_docs_journey.py),
[artifact recovery](../tests/github/test_pull_request_verification.py).

## C-10: Pauses and parks

**Rule: Honor `paused`/`backlog`, each dependency hold, and each park's recorded reason for waiting for a human.**

**Why:** Resuming work requires the action that answers the specific hold or park.

**Limits:** A hold does not undo earlier writes or commits. A dependency hold is an issue on `workflow:blocked`, and
only its parent's release, once the recorded prerequisites permit it, answers it. An edit made meanwhile is not read:
nothing hashes it, records or replaces a baseline, or reroutes the issue, so its baseline, decomposition records,
dependency graph, and tracked children stand, and its requirements are compared on the legitimate entry to
`workflow:ready` that release makes, before anything implements it. The hold stops no dependency progress: a blocked
parent's walk still releases eligible children, and still finishes waiting, through the existing claims, admission,
and lineage checks, and an umbrella keeps its own drift route. Neither an edit nor a finished prerequisite lifts or
works past `paused`/`backlog`: a held child is not released, a held parent is neither polled nor handed back to
`workflow:ready`, and the `ready` decision stops at either control or at a relabel back to `workflow:blocked`. The
release and the parent's return move only the workflow label, and the walk reads the parent's controls again in front
of every release, so a hold applied while the poll runs is never written away or worked past. Lifetime agent-run
charges and the grant that permits further runs are covered by [C-15].

**Specs:** [controls](state-machine/labels-and-state.md#workflow-labels),
[waiting for human action](state-machine.md#per-tick-flow-workflowengineticktick),
[dependency holds](state-machine/delivery-stages.md#_handle_blocked-label-workflowblocked),
[deferred drift](state-machine/delivery-stages.md#user-content-drift-detection),
[retry budget](state-machine/labels-and-state.md#the-retry-budget).

**Checks:** [live holds](../tests/workflow/engine/test_guards_paused.py),
[ready holds](../tests/workflow/stages/decomposition/test_ready_holds.py),
[dependency holds](../tests/workflow/stages/decomposition/test_blocked_deferral.py),
[held releases](../tests/workflow/stages/decomposition/test_claimed_release.py),
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
labels must still leave the workflow engine unloaded. Where an owner defines the typed request or context an entry is
driven by -- an agent run's options, a scheduler submission, a dev resume, a base-sync route -- callers build that
record and the entry takes it as its one signature, so a test patching the owner and a caller reaching it meet the same
parameters.

**Specs:** [ownership](architecture.md#top-level-layout),
[development conventions](../.agents/skills/develop/SKILL.md#workflow-owners-and-stage-modules).

**Checks:** [imports](../tests/workflow/test_imports.py), [exports](../tests/repository/test_package_exports.py),
[owner patching](../tests/agents/test_owner_patching.py).

## C-14: Pinned session commands

**Rule: Resume sessions with their pinned command's original backend and arguments.**

**Why:** A configuration change must not retarget an existing conversation or discard its model and reasoning settings.

**Limits:** Reviewers start fresh with current configuration. A plain `codex` or `claude` is a current command spec,
kept as pinned with no arguments. Resumes, rotation, failure retirement, and a failed developer conversation's
replacement keep the pinned command. Only `dev_agent` and `dev_session_id` lock a developer session; no other key is
resumed, converted, or cleared as one.

**Specs:** [session commands](workflow.md#in-flight-session-lock--pinned-full-spec-until-the-session-ends).

**Checks:** [session pins](../tests/workflow/stages/implementing/test_full_spec_dev.py),
[session reads](../tests/workflow/stages/implementing/test_full_spec_reader.py),
[retirements](../tests/workflow/stages/implementing/test_rotation.py),
[fresh reviewers](../tests/workflow/stages/implementing/test_full_spec_reviewer.py).

## C-15: Lifetime agent-run budget

**Rule: Never refund charges against an issue's lifetime `MAX_AGENT_RUNS_PER_ISSUE` budget.**

**Why:** Crashes, retries, and restarts must not let an issue evade its lifetime run limit.

**Limits:** Only a trusted `/orchestrator add-agent-runs N` grants more runs to an issue parked at its lifetime limit;
other budgets have their own rules. The count is never read below the `issue_agent_runs` usage meter, whose every
counted exit was a launch charged first, so a count that is missing or unreadable refunds nothing that meter saw.
Session rotation and retirement touch neither meter.

**Specs:** [run budget](state-machine/labels-and-state.md#the-agent-run-circuit),
[charging before launch](security.md#bounded-agent-spend-per-issue-max_agent_runs_per_issue).

**Checks:** [charging](../tests/workflow/engine/test_run_circuit.py),
[meter floor](../tests/workflow/engine/test_run_ledger.py).

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
