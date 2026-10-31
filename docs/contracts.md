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
are preserved unchanged and never overwritten, duplicated, or silently upgraded. A captured developer completion
(`developer_completion`) is the pinned record of one returned report alone: only its confirmed capture, or that
capture read back after an unconfirmed write, carries the report and what its road froze, never a log, analytics,
a native session, a trajectory, or a host record. Only the first implementation, an implementing resume, the fix a
reviewer's change request hands its developer -- the run its handoff launches, and the resume that finishes its parked
round -- the resume answering a pull request's human feedback, and a requirements-drift resume on `implementing`,
`validating`, `in_review`, or `resolving_conflict` -- the replies that remain its continuation included -- capture
one, as their developer returns. The dispatcher's recovery reads a pending capture through that read-back alone.

**Specs:** [state](architecture.md#design-constraints), [restarts](configuration/operations.md#what-survives-a-restart).

**Checks:** [pinned state](../tests/github/test_pinned_state.py),
[quota recovery](../tests/workflow/stages/implementing/test_quota_retirement_host.py),
[completion captures](../tests/workflow/engine/test_completion_checkpoint.py),
[capture recovery](../tests/workflow/engine/test_completion_recovery.py),
[captured attempts](../tests/workflow/stages/implementing/test_captured_attempts.py),
[captured fixes](../tests/workflow/stages/validating/test_captured_fixes.py),
[captured feedback](../tests/workflow/stages/fixing/test_captured_feedback.py),
[captured drift](../tests/workflow/stages/validating/test_captured_drift.py).

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
model as `AgentResult` alone, `orchestrator.github` publishes `PinnedState`, built from keywords and carrying its
payload as `state_data` alone, and the agent runner and the scheduler's `submit` take only their typed records,
`AgentRunOptions` and `SubmissionRequest`; no keyword form or attribute beside them is a current call shape. An
internal refactor changes none of them; a deliberate change updates the affected contracts, specifications, and tests
with the behavior.

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
unpriced cost, and a malformed record's containment remain current answers. A usage estimate prices a model only through
an active price-catalogue row naming its exact ID, documented alias, or published snapshot; an unknown version, an
arbitrary suffix, or a dormant row is an unpriced cost, never another row's rates. A Claude estimate prices each usage
row on its own, a run and its turns alike: a cache write at the lifetime its usage block reports as a whole number, a
write it reports no lifetime for at neither lifetime's rate, a block whose lifetime split contradicts its aggregate at
no rate at all, and a request-tiered rate only on one API message's own prompt, never on a `result` total or an
output-only hand-back. A Codex estimate prices a run's last usage record once, as the sum of every request it covers:
on a model charging cache writes by lifetime, a write only at a lifetime the record reports, never one the CLI's flat
count or its zero leaves unknown; reads and writes past the input at no rate at all; and a request-tiered row's base
rates only where the record's input keeps every request at or under its threshold, the tier's rates never. An
Antigravity estimate prices a run's own completed steps once, each once however often its frame repeats, as the Gemini
API model its one CLI slug is documented as -- cache reads beside the input at the cached rate, thinking inside the
output -- and only over a usage span one dated row is in effect for on every date it touches in any time zone: a slug
no SKU is established for, such as Gemini 3.7 Flash or 3.1 Pro, another provider's model, mixed or unnamed models, a
run spawning a subagent, a step reporting no count or a negative one, and a run with no span are unpriced. A usage
record states what its
cost and counters mean in its `cost_evidence` and `token_evidence`, which `UsageMetrics`, each `TurnUsage`, the
`agent_exit` record, and the trajectory `run_usage` serialize alike: a CLI-reported amount, an explicit zero included,
outranks an estimate and is labelled CLI-reported, never a verified bill; an estimate is a token-only Standard API
list-price equivalent on its provider's basis; an unpriced cost states no complete amount; no-usage stays its own
answer; and a counter no usage payload reported is missing evidence, never a reported zero. A record without that
evidence -- every one an earlier build wrote -- is read with an `unknown` basis and completeness, its `cost_usd` kept
under that basis, and with a cache overlap nothing establishes, so its tokens total only where no cache counter is
nonzero: no provider breakdown, completeness, or overlap is inferred from its `cost_source`, backend, or models, and
nothing backfills it. The analytics sync files that evidence on each `agent_exit` row as those readers read it -- an
amount per basis, an estimate's rate-verification dates, the completeness, and the non-overlapping token total -- and
the agent-run view, the daily rollup, and the read model's cost and token reductions sum and count those columns, never
`cost_source` alone: a reduced cost keeps each basis apart and the weakest completeness any run states, an empty
cohort stays apart from a complete zero, and a token sum keeps the runs whose total is unknown beside it. The issue
cost ranking orders in SQL, ahead of its cap, on every amount an issue's runs state -- a subtotal at its known part, an
issue stating none after every one that does -- and a listed or traced run reads its own row's evidence, never a
figure repriced from its tokens. Each grouped breakdown -- by stage, backend, repository, and review round and role --
reduces its group's runs through those same reductions, a ratio of its cost or tokens is qualified or unavailable
where either side falls short, and the cache and non-cache split of its amount is that stated amount allocated by its
runs' declared token share, never a measured cache charge, the amount of a run whose total is unknown left unsplit.
A row an earlier sync stored without those columns reads as
`unknown`, its `cost_usd` under that basis and its token total unknown, and nothing re-derives, reprices, or converts
it. An issue's pinned usage totals keep what its runs' evidence states: `issue_cost_evidence` is their costs reduced
alike, in the shape a usage record's `cost_evidence` takes, and `issue_total_tokens` adds only non-overlapping totals,
`issue_total_tokens_unknown_runs` counting the runs it lacks; the terminal receipt words that cost as every other
surface does -- an Antigravity-only total a Gemini API token estimate, a mixed one blended with each basis's amount
beside it, and a short one a subtotal -- never a merged figure. Totals an earlier build counted keep no evidence and
read as one record without it, their cost under the `unknown` basis and completeness and their overlap unknown,
nothing inferred from `issue_cost_sources`; the first run counted over them folds that reading in once and keeps
their number in `issue_unevidenced_runs`, so no later run makes them known, and no posted receipt is rewritten.
A recorded requirements fingerprint
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
its route recorded, a list missing or damaged replaying nothing. A captured feedback round's recovery settles only the
pairs its launch froze, never a rescan, so nothing posted after the scan is recorded as delivered, and a captured
drift resume's recovery settles the frozen reading its run was handed, never a newer one, the pull-request comments an
`in_review` prompt quoted left for the next scan rather than marked read. An approval or
permission is read only as its current writers record it whole: no approval record, an approval beside no evidence
claim, a `late_approved_sha` with no `late_approved_basis` this build can read, and a rewrite permission beside an
attempt record with no declared terms are each no grounds -- never an earlier producer's default -- and authorize no
publication, transfer, or ready notification.
An exempt commit with no semantic identity, the settlement's when fingerprinting fails, stays a current record that
exempts that commit alone. A recorded decomposition outcome is read only whole, under the manifest contract its reply
was held to: a split child with no stated `depends_on` list, a late slice with no `estimated_added_lines`, and a late
`single` with no `split_blocker` are no outcome, so nothing is created, released, parked, or announced on one, and
a park waiting on one comes down -- the candidate is adjudicated again before a split transaction begins, and once one
has begun the issue parks over what it made, whatever spelling its recorded verdict is in. A split's recorded
`children` beside no integer `expected_children_count` -- the count every split writes before its first create -- is
no finished split: recovery parks it with every child kept, adopting, seeding, or finalizing nothing. A late
pull-request hold is recognized only in the two spellings this build writes, on either side of publication; a
description in any other is never rewritten, released, or restored over: its hold marker refuses capturing it as
somebody's description and, on an open pull request, holds every release that would drop the preserved copy. An
optional rationale, an omitted ordinary `umbrella` flag, an
ordinary child with no budget, and no split marker at all for a split that never started remain current answers.
A usage receipt ledger (`issue_usage_receipts`) is read only in the shape its checkpoint writes: absent is an issue
that accounted nothing, and any other shape is damage, never an empty ledger, so nothing is counted on it or written
over it. A run is accounted only on the pinned comment its charge was written on, never a replacement copying it, and
only over a `late_cycle_id` that is absent or a positive whole number: a damaged one is no absent cycle. A parsed usage
adding what no counter's total is spelled as -- a negative count, or a negative cost or one no float holds -- is
refused, never committed as a total the next reading refuses. A captured completion (`developer_completion`) is read
only whole, in the one shape its stage writes: absent is an issue that captured nothing, and any other shape --
`null`, a key too many or too few, a member out of its bound, a report the report records refuse, or a road its
contract refuses -- is a damaged claim, never an absence, so nothing captures over it, retires it, or acts on it,
and no delivery is bound beside it. Its READY text and VERIFIED reference stay two outcomes, a rewritten-head refresh
is captured only READY, and a change-request or pull-request-feedback road only beside the handoff it froze. A
requirements-drift resume settles the input it was handed for itself, so the report its capture becomes carries none
of it, as the recording its own tick makes carries none, and no report hands its requirements baseline on to one that
supersedes it: the later report's settlement never writes an older baseline back.

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
deletes one, whether the clone holds it or only the remote does. No live work adopts one either: the branch resolver
answers only an issue's current-layout name, for fresh work and for a record pinning exactly that name, and refuses
any other record before a checkout, launch, or push, inferring no flat name from a recorded pull request, taking no
`orchestrator/` prefix as proof, and deriving no replacement for a pin; no road works in, resumes, reuses, rebases,
recovers, publishes from, or removes a checkout at the issue's path until it is proven a worktree of the clone on that
branch, whatever commits the tree carries, a detached HEAD passing only where an unfinished rebase of exactly that
branch accounts for it.
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
[branch refusal](state-machine/labels-and-state.md#branch-refusal),
[analytics readers](observability/analytics-dashboard.md#read-model-orchestratorobservabilityanalyticsquery),
[analytics evidence](observability/analytics-database.md#usage-evidence-columns),
[price catalogue](observability/usage.md),
[usage evidence](observability/usage.md#usage-parser),
[requirements baselines](state-machine/delivery-stages.md#user-content-drift-detection),
[watermark initialization](state-machine/delivery-stages.md#_handle_in_review-label-in_review),
[replay batches](state-machine/labels-and-state.md#pinned-state),
[decomposition records](state-machine/labels-and-state.md#pinned-state),
[late holds](workflow/roles.md#what-a-late-adjudication-is-asked-and-what-it-may-answer).

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
[stored evidence](../tests/observability/analytics/sync/test_usage_evidence_columns.py),
[cohort reads](../tests/observability/analytics/query/test_cost_cohorts.py),
[issue rankings](../tests/observability/analytics/query/test_issue_reads.py),
[run costs](../tests/observability/analytics/query/test_agent_exit_reads.py),
[evidence in Postgres](../tests/observability/analytics/sync/test_live_usage_evidence.py),
[rankings in Postgres](../tests/observability/analytics/sync/test_live_issue_reads.py),
[grouped reads](../tests/observability/analytics/query/test_rollup_breakdown_reads.py),
[groups in Postgres](../tests/observability/analytics/sync/test_live_grouped_reads.py),
[price catalogue](../tests/observability/usage/test_usage_price_catalogue.py),
[Claude requests](../tests/observability/usage/test_usage_claude_requests.py),
[Codex requests](../tests/observability/usage/test_usage_codex_requests.py),
[Antigravity requests](../tests/observability/usage/test_usage_agy_requests.py),
[cost evidence](../tests/observability/usage/test_usage_cost_evidence.py),
[token evidence](../tests/observability/usage/test_usage_token_evidence.py),
[recorded evidence](../tests/workflow/engine/test_usage_metrics.py),
[issue totals](../tests/workflow/engine/test_usage_accumulator.py),
[trajectory evidence](../tests/observability/analytics/trajectories/test_record.py),
[viewer evidence](../tests/observability/trajectory_viewer/test_usage_parsing.py),
[verification artifacts](../tests/github/test_verification_artifacts.py),
[requirements baselines](../tests/workflow/engine/test_drift.py),
[late first baselines](../tests/workflow/stages/decomposition/test_late_first_baseline.py),
[watermark initialization](../tests/workflow/stages/in_review/test_watermark_initialization.py),
[delivered thread](../tests/workflow/engine/test_thread_delivery.py),
[timeout parks](../tests/workflow/stages/documenting/test_timeout_delivery.py),
[fix settlement](../tests/workflow/stages/fixing/test_cross_read_race.py),
[replay batches](../tests/workflow/stages/fixing/test_batch.py),
[recovered batches](../tests/workflow/stages/fixing/test_captured_feedback.py),
[approval bases](../tests/workflow/stages/implementing/test_late_approval_basis.py),
[rewrite permissions](../tests/git/base_sync/test_transfers.py),
[split manifests](../tests/workflow/stages/decomposition/test_manifest.py),
[late records](../tests/workflow/stages/decomposition/test_late_session.py),
[unexplained singles](../tests/workflow/stages/decomposition/test_late_unsplit_park.py),
[hold spellings](../tests/workflow/stages/decomposition/test_late_hold.py),
[split recovery](../tests/workflow/stages/decomposition/test_recovery.py),
[usage receipts](../tests/workflow/engine/test_usage_checkpoint.py),
[completion records](../tests/workflow/engine/test_completion_records.py),
[completion roads](../tests/workflow/engine/test_completion_eligibility.py),
[superseded drift reports](../tests/workflow/stages/validating/test_report_hold.py),
[branch resolution](../tests/git/worktrees/test_resolution.py),
[checkout reuse](../tests/git/worktrees/test_creation.py),
[refused drift unwind](../tests/workflow/stages/documenting/test_drift_checkout.py),
[refused drift resume](../tests/workflow/stages/validating/test_drift_refusal.py),
[refused handoff recovery](../tests/workflow/stages/validating/test_review_resume_refusal.py).

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
exclusivity, and every other maintenance gate stay required beside it. A captured developer completion is decided
from a read under the dispatch claim, and its checkout is held out of the base refresh under the refresh's claim
until a transaction owns its report or a guarded invalidation retires it; it grants no checkout adoption, reset, or
deletion, so a checkout not proven the issue's own, or whose head is no commit the store holds, holds it.

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
[claimed finalize](../tests/workflow/stages/decomposition/test_claimed_closed_children.py),
[capture freeze](../tests/git/base_sync/test_completion_freeze.py).

## C-06: Guarded writes and recoverable effects

**Rule: Treat unconfirmed writes as unknown; read back what landed before retrying publication.**

**Why:** An unconfirmed write proves neither success nor absence of an effect.

**Limits:** Recovery rechecks prerequisites. An unreadable record or artifact does not prove the write failed, and an
incomplete one proves nothing landed: recovery finishes a current transaction from its whole record -- a debt with
its basis, a rewrite permission bound to its attempt's declared terms, a late split from a recorded verdict that reads
back whole -- and refuses one missing any of it; a split transaction in flight over a result that no longer answers,
a verdict no build reads included, parks rather than buying a second verdict beside the children it made. Close
recovery answers a record admission refuses as an unreadable one: the close it read is kept, and nothing is posted,
marked, or reclaimed over it. Snapshot recovery over a ref already gone tells no consumer admission refuses and keeps
that notice owed rather than recording it delivered.
A refused or unconfirmed write stops the steps that depend on it; a later tick reads state afresh. Guarded commits
and direct writes check admission: neither writer may overwrite an unsupported or malformed authoritative comment,
create a replacement beside it, or silently stamp it as current, whatever comment id its caller holds, and neither
sends a state the next reading would refuse; strict edits remain non-creating and land only on a comment still the
issue's record, never one a record ahead of it has displaced, and a direct write over such a comment raises, so the
steps depending on it stop. A usage checkpoint reads its invocation's receipt back before anything it
sends, so one left unconfirmed settles nothing until that read-back, and asking again adds nothing where it landed; a
refused checkpoint, an unreadable read-back, or a receipt read back beside a damaged counter licenses nothing that
depends on the accounting. A completion's capture, transfer, and retirement each read the capture back first, so
one left unconfirmed withholds the caller's state and settles nothing until read back, and asking again records
nothing twice; any of them answered or refused over a comment that moved since its caller read it withholds that
caller too, so its whole-state write never puts back a delivery, retirement, or damaged claim it did not hold. The
transfer records the delivered report and hands the capture off in one commit, what the capture's road retires with
the report -- a change request it answers -- riding it, so the report has one durable owner
either way; a pending capture is retired only by a guarded invalidation, never behind a transfer nobody confirmed,
and a handed-off one is neither replaced nor retired until the transaction its delivery becomes settles, the binding
holding that delivery to the commit the capture reported on -- save by a later capture carrying it while that
delivery stands unbound, which holds the delivery the same way and, invalidated, retires still carrying it. A
capture's settlement of what its tick staged rides its transfer's own commit, so neither lands without the other. A
transfer's read-back or retry, and a capture's or
retirement's retry finding the capture past pending, hands its caller the delivery that landed.
A pending capture is handed on only over readings that admit it, its road's own prerequisites included, and its
road's own reading of the recorded pull request -- a `discussion` plan the implementing road reads as one is none of
the run's, merged or not -- retired only by a guarded invalidation a reading proved, held to that very reading whole
so a comment that moved since -- a missing field restored included -- refuses it, and held with nothing written where
a reading fails or the claim is damaged: an unreadable prerequisite never discards it, a record its handoff froze
moved into a spelling its own reader refuses, or moved with no reader registered for it, included, and a cancelled or
restarted cycle never inherits it. A rewritten-head refresh is handed on only where its debt, the commit it reported
on, and the pull request's head are one commit, as that refresh's own road requires.
A capture is taken only where it, and then that transfer, its binding, and its settlement, still fit the comment
with every terminator escaped; the transfer, and the binding and settlement of a captured report, are measured that
way again over the comment each lands on, and refused for room with the report kept. A refusal leaves the run's
usage checkpoint to land or not on its own, and a park the binding takes over a capture is decided on that capture.
Writer exclusion comes from [C-05].

**Specs:** [transactions](state-machine/labels-and-state.md#pinned-state),
[publication evidence](security.md#what-a-trusted-pinned-record-still-cannot-license),
[base-rebase recovery](architecture.md#push-path-gitbranch_transport_push_branch),
[base-rewrite finalization](state-machine/delivery-stages.md#the-base-rewrite-finalization-contract),
[ready-ping publication](state-machine/delivery-stages.md#the-ready-ping-publication-contract),
[ready decision](state-machine/delivery-stages.md#_handle_ready-label-workflowready--workflowimplementing).

**Checks:** [guarded commits](../tests/workflow/engine/test_pinned_commit.py),
[strict edits](../tests/github/test_pinned_state_edits.py),
[usage checkpoints](../tests/workflow/engine/test_usage_checkpoint.py),
[displaced records](../tests/workflow/engine/test_usage_checkpoint_thread.py),
[completion handoffs](../tests/workflow/engine/test_completion_handoff.py),
[refusals behind a read](../tests/workflow/engine/test_completion_refused_behind_read.py),
[completion capacity](../tests/workflow/engine/test_completion_capacity.py),
[captured sources](../tests/workflow/engine/test_completion_binding.py),
[capture recovery](../tests/workflow/engine/test_completion_recovery.py),
[frozen handoffs](../tests/workflow/engine/test_frozen_handoff.py),
[effect re-reads](../tests/workflow/engine/test_completion_effect.py),
[retirement tick](../tests/workflow/engine/test_completion_retirement.py),
[recovery checkpoints](../tests/git/base_sync/test_persistence.py),
[captured-run abandonment](../tests/workflow/engine/test_rewrite_landing_moved.py),
[finalization checkpoints](../tests/workflow/engine/test_rewrite_finish_writes.py),
[ready-ping recovery](../tests/workflow/stages/in_review/test_ready_ping_recovery.py),
[refused close recovery](../tests/workflow/stages/decomposition/test_late_refused_closes.py),
[admitted read-back](../tests/workflow/engine/test_dispatch_current_recovery.py),
[ready recovery](../tests/workflow/stages/decomposition/test_ready_recovery.py),
[split recovery](../tests/workflow/stages/decomposition/test_late_recovery.py),
[in-flight splits](../tests/workflow/stages/decomposition/test_late_split_recovery.py).

## C-07: Publication authority and exact revisions

**Rule: Agents never push; the orchestrator never merges PRs and checks the commit and remote head before pushing.**

**Why:** Humans decide which PRs merge. Checking the inspected commit and expected remote branch head protects
intervening work.

**Limits:** Human maintainers may push; their changes to the remote branch are external changes the orchestrator must
handle. The publication protocol defines the commit and remote branch head checks and commit-selection fallbacks.
The orchestrator publishes only to an issue's current-layout branch the live resolver names: a recorded pull request
whose branch is missing, invalid, flat, another repository's, or otherwise not that name stops before any checkout,
agent launch, or push, and no newly derived branch is substituted for it. Each push, and each rebase, rebase abort,
reset, clean, squash, or subject amendment that rewrites or discards what a checkout stands on, is made only once that
checkout is proven the issue's own again, behind the reads, writes, fetches, and agent runs on its road — a lease no
caller pinned is read ahead of that proof and handed to the transport rather than read inside the push, and a push's
last proof is asked by the transport itself, behind its own preparation — and so is
each pull request opened, edited, or adopted. The handoff past a landed push is proven again on the far side of the
push and of the write carrying its receipt, and the initial publication's, a conflict round's, and an accepted
verdict's handoffs again behind their own writes, immediately before the label, so a tree switched onto the flat branch
meanwhile is neither published, rewritten, cleaned, nor handed on by them. A refusal
before the step leaves the intent, approval, anchor, or marker a crash there would leave; one after a landed push keeps
the push, the intent or receipt recording it, and any handoff it owes, and withholds only what follows. Current
unpushed work, a current pull request's restoration from its remote head, uncertain remote reads, and exact-head
pushes keep their protocols. A captured completion publishes nothing of its own: its recovery hands an admitted
capture to its road's owner, whose publication keeps every gate above, and the base refresh -- an interrupted
rebase's recovery included -- rewrites no captured source before that recovery has decided on it. While a report a
capture handed off is owed, the size gate holds the head to the commit that capture reported on, beside any candidate
a record names, so a checkout moved off it -- or a recorded candidate naming another commit -- is neither measured,
pushed, nor opened as a pull request.
Credential filtering does not enforce push authority; see [C-11].

**Specs:** [pushes](architecture.md#push-path-gitbranch_transport_push_branch),
[human merges](state-machine.md#_handle_in_review-label-in_review),
[branch refusal](state-machine/labels-and-state.md#branch-refusal).

**Checks:** [transport](../tests/git/test_push.py),
[rewrite publication](../tests/workflow/engine/test_rewrite_publication.py),
[human merge handoff](../tests/workflow/stages/in_review/test_routing.py),
[refused publication](../tests/workflow/stages/implementing/test_pr_reuse.py),
[refused seam push](../tests/workflow/stages/fixing/test_bounce.py),
[refused resume](../tests/workflow/stages/implementing/test_resume_checkout.py),
[refused refresh](../tests/workflow/engine/test_base_refresh_branch_refusal.py),
[refused adjudication](../tests/workflow/stages/decomposition/test_late_charged_run.py),
[switched initial publication](../tests/workflow/stages/implementing/test_initial_publication_checkout.py),
[switched seam push](../tests/workflow/stages/implementing/test_publication_checkout.py),
[switched accepted verdict](../tests/workflow/stages/decomposition/test_late_accepted_checkout.py),
[switched verdict label](../tests/workflow/stages/decomposition/test_late_settlement_replay.py),
[switched plan publication](../tests/workflow/stages/discussion/test_publication_checkout.py),
[switched plan handoff](../tests/workflow/stages/implementing/test_plan_handoff_checkout.py),
[switched squash](../tests/git/publication/test_squash_record_race.py),
[switched squash rollback](../tests/git/publication/test_squash_mid_rewrite.py),
[switched conflict rebase](../tests/workflow/stages/conflicts/test_rebase_checkout.py),
[switched docs amendment](../tests/workflow/stages/documenting/test_subject_checkout.py),
[switched drift unwind](../tests/workflow/stages/documenting/test_drift_checkout.py),
[switched refresh abort](../tests/workflow/engine/test_base_refresh_abort.py),
[switched refresh clean](../tests/git/base_sync/test_checkout_proof.py),
[switched conflict handoff](../tests/workflow/stages/conflicts/test_handoff_checkout.py),
[captured source](../tests/workflow/engine/test_tick_refresh.py),
[anchored capture](../tests/workflow/engine/test_anchored_capture.py),
[captured source](../tests/workflow/stages/implementing/test_captured_source.py),
[captured source beside a record](../tests/workflow/stages/implementing/test_captured_late_candidate.py).

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
approval and settles no transaction. A developer report, captured or not, names the requirements revision its run was
handed -- a `/orchestrator continue` retry, which hands none, the baseline the issue records -- never an edit the run
did not see.

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
[captured retry requirements](../tests/workflow/stages/implementing/test_captured_retry_edit.py),
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
of every release, so a hold applied while the poll runs is never written away or worked past. A hold a finished agent
run meets, or an accounting checkpoint of it that neither landed nor read back, permits that run's usage accounting
alone, beside a quota retirement it owes and, on the first implementation, an implementing resume, a reviewer's change
request's fix, a pull request feedback round, or a requirements-drift resume, the capture of the report the run
finished on: the exit is counted once, as it returns, and
nothing else of the run -- a
publication, a label, a park, a consumed input, a session pin, a further launch -- is written or made, nor does the
count give any stage outcome a replay; the hold the run's return first read is the one honored, whatever a later
fetch sees. A captured completion waits through `paused`/`backlog`, a dependency hold, the `ready`
decision, and a spent run ledger's park, none released, re-baselined, or cleared by it -- an interrupted auto
rebase's anchor beside it included, which the anchor's own hold answers without moving the captured checkout -- and
its recovery charges no run and grants no invocation; one whose run's accounting checkpoint neither landed nor read
back is handed on to no road until that run's receipt reads back, and the issue's controls, label, state, and
requirements, its checkout, and its pull request are read again right before the capture is retired or handed on,
so a hold applied, or a close, reopening, edit, or source moved or put back, while its readings were taken writes
nothing; a landed retirement ends its tick, so no stage runs on the snapshot its readings outdated. An applicable
capture of an implementing road, of a change request's fix, of a pull request feedback round, or of a
requirements-drift resume is finished with no developer launched: only what that run was handed and its session are
settled -- a feedback round's frozen batch, reset round, and cleared bookmarks, later feedback left unread, and a drift
resume's frozen reading, recorded as the baseline only by its report's handoff or its stage's own write, beside the
round its stage's drift disposition spends, resets, or hands on, the lease a conflict round's caller proved, and no
baseline a dependency hold defers, its handoff or withdrawal made only once its admission reads again behind every
request that disposition and the write itself took, and a status read that establishes nothing keeping it -- and its
report goes through
the existing delivery, size gate, and publication --
a change request's retired in the very commit that hands its report on, and its round spent once,
only over its reviewed subject read again save the head its run moved and the issue's controls and requirements,
its checkout, and its pull request's head read again behind it, damage there -- a settled report and its handoff
that no longer agree included, judged ahead of the revision reviewed -- or a push meanwhile holding it rather than
proving it stale, its report recorded decided on that subject and on the park's flags as those reads took them, so a
record moved or damaged, or a park recorded -- a spent run ledger's among them -- while they ran holds it too, a
handed request never dropped or launched
again beside a capture nothing has decided, and a reading that did not return holding the capture rather than
discarding it. Lifetime agent-run charges and
the grant that permits further runs are covered by [C-15].

**Specs:** [controls](state-machine/labels-and-state.md#workflow-labels),
[waiting for human action](state-machine.md#per-tick-flow-workflowengineticktick),
[dependency holds](state-machine/delivery-stages.md#_handle_blocked-label-workflowblocked),
[deferred drift](state-machine/delivery-stages.md#user-content-drift-detection),
[retry budget](state-machine/labels-and-state.md#the-retry-budget),
[held accounting](state-machine/labels-and-state.md#pinned-state).

**Checks:** [live holds](../tests/workflow/engine/test_guards_paused.py),
[held accounting](../tests/workflow/engine/test_exit_accounting.py),
[held developer runs](../tests/workflow/stages/implementing/test_paused.py),
[held resumes](../tests/workflow/stages/implementing/test_captured_resumes.py),
[ready holds](../tests/workflow/stages/decomposition/test_ready_holds.py),
[dependency holds](../tests/workflow/stages/decomposition/test_blocked_deferral.py),
[held releases](../tests/workflow/stages/decomposition/test_claimed_release.py),
[review parks](../tests/workflow/stages/in_review/test_parked.py),
[retry-cap parks](../tests/workflow/engine/test_retry_budget.py),
[held captures](../tests/workflow/engine/test_completion_holds.py),
[ready captures](../tests/workflow/stages/decomposition/test_ready_capture.py),
[held fixes](../tests/workflow/stages/validating/test_captured_fixes.py),
[held fix resumes](../tests/workflow/stages/fixing/test_captured_resumes.py),
[held feedback rounds](../tests/workflow/stages/fixing/test_captured_feedback.py),
[held drift resumes](../tests/workflow/stages/implementing/test_captured_drift.py),
[held drift replies](../tests/workflow/stages/validating/test_captured_drift.py),
[held in_review drift](../tests/workflow/stages/in_review/test_captured_drift.py),
[held conflict drift](../tests/workflow/stages/conflicts/test_captured_drift.py).

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
`base_rebased` twice. The per-issue usage counters are the accounting checkpoint's alone: an exit no usable checkpoint
landed is not counted, and nothing reconstructs it from the analytics or audit sinks.

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
replacement keep the pinned command, and a recovered captured completion pins the command its run ran under. Only
`dev_agent` and `dev_session_id` lock a developer session; no other key is resumed, converted, or cleared as one.

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
Session rotation and retirement touch neither meter. Usage accounting charges, refunds, and parks nothing: an exit is
accounted under the identity of the process it came from -- the charge that process was started under and a random
nonce, never the request's fingerprint -- and a receipt, or the floor receipts retire under, covers that identity, so
a settlement asked again never moves the meter past the charges it counts.

**Specs:** [run budget](state-machine/labels-and-state.md#the-agent-run-circuit),
[charging before launch](security.md#bounded-agent-spend-per-issue-max_agent_runs_per_issue),
[usage receipts](state-machine/labels-and-state.md#pinned-state).

**Checks:** [charging](../tests/workflow/engine/test_run_circuit.py),
[meter floor](../tests/workflow/engine/test_run_ledger.py),
[accounting once](../tests/workflow/engine/test_invocation_identity.py).

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
