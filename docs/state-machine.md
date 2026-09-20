# Workflow state machine

This area documents the label-based state machine that drives every GitHub issue from pickup to terminal. It is split
out of [`architecture.md`](architecture.md), which keeps the high-level overview, the top-level module map, and the
process / agent / push model. Workflow labels and pinned-state JSON keys are a compatibility contract — live issues
already carry them — so this area is where label spelling, the transitions between them, and each handler's behavior
are authoritative.

## The pages in this area

- [`state-machine/labels-and-state.md`](state-machine/labels-and-state.md) — the label set and the control labels, the
  typed states and the transition guard, the migration off the pre-namespace spellings, what one tick reads and writes
  per issue, and every pinned-state key a handler depends on.
- [`state-machine/delivery-stages.md`](state-machine/delivery-stages.md) — pickup, the user-content drift hook,
  decomposition and the family walks, and the dev / reviewer / docs loop through `in_review`, `workflow:fixing`, and
  `workflow:resolving_conflict`.
- [`state-machine/conversation-stages.md`](state-machine/conversation-stages.md) — the two operator-applied
  conversation stages, `question` and `discussion`, including the plan PR a confirmed design earns.
- [`state-machine/lifecycle.md`](state-machine/lifecycle.md) — the compact label-lifecycle reference diagram.

Every section below keeps its heading here as a summary of what moved, so a link written against this page still lands
on the answer.

For the multi-repo dispatch, module map, and push model, see [`architecture.md`](architecture.md). For agent roles,
prompt contracts, and command specs, see [`workflow.md`](workflow.md). For env vars and the operator runbooks beside
them, see [`configuration.md`](configuration.md). For the audit event log and analytics sink, see
[`observability/event-streams.md`](observability/event-streams.md); for the usage parser over them,
[`observability/usage.md`](observability/usage.md); and for the map over every observability surface,
[`observability.md`](observability.md). For the security checklist, see [`security.md`](security.md).

## Workflow labels

An issue carries at most one workflow label at a time, and the orchestrator only ever swaps labels from its own set —
`bug`, `enhancement`, and a repository's own triage labels are preserved. `workflow:<tag>` is the **wire label**: the
literal string on the GitHub issue that a label write puts there, the transition guard checks, and the per-tick
dispatcher partitions on. A bare `<tag>` is the **stage**: the handler, the subpackage under
`orchestrator/workflow/stages/` holding it, and the identifier analytics rows, audit event payloads, and agent-session
attribution carry. `in_review`, `question`, `discussion`, `done`, and `rejected` were never namespaced, so those read
the same either way.

The states, in lifecycle order: no label, `workflow:decomposing`, `workflow:ready`, `workflow:blocked`,
`workflow:umbrella`, `workflow:implementing`, `workflow:documenting`, `workflow:validating`, `in_review`,
`workflow:fixing`, `workflow:resolving_conflict`, the operator-applied `question` and `discussion`, and the `done` /
`rejected` terminals. Three non-workflow **control labels** modify behavior without occupying the workflow slot:
`backlog` (a "not yet" hard skip on a fresh issue), `paused` (the same hard skip on an in-flight one, honored again
right after every agent run returns), and `workflow:community_contribution` (applied by the per-tick open-PR sweep,
never by an operator). What each state means, what a `paused` mid-run withholds, and why the prefix is a collision
guard rather than the membership test are in
[`state-machine/labels-and-state.md#workflow-labels`](state-machine/labels-and-state.md#workflow-labels).

### Typed states and the transition guard

`WorkflowLabel` and `ControlLabel` in [`orchestrator/workflow/state.py`](../orchestrator/workflow/state.py) define
both vocabularies once; because `StrEnum` members *are* their wire strings, a member is the GitHub label verbatim.
Two guards run at `GitHubClient.set_workflow_label`, the single label-write chokepoint: an always-strict **typo
guard** that raises on a name outside `WorkflowLabel`, and the **transition guard**
(`WORKFLOW_TRANSITION_GUARD` = `off` / `warn` / `enforce`, default `warn`) checking `current → new` against
`ALLOWED_TRANSITIONS`. Operator relabels through the GitHub UI bypass both, so the guard never fights a human — and
one orchestrator write skips the transition guard for the same reason: the late size gate putting a label back where
a human moved it from is repairing a move the graph has no edge for. The edge set, that one exemption, the
`orchestrator.state_machine` logger a rejection is filtered by, and how `create_child_issue` shares the typo guard for
its direct write are in [`state-machine/labels-and-state.md`][typed-states].

### Legacy labels and the migration off them

A repository whose labels predate the namespace is migrated by the startup label bootstrap: a pre-namespace spelling
that exists alone is **renamed in place**, so every issue holding it moves across in one edit; a namespaced label that
already exists is left alone, as is any bare label beside it; neither present means the namespaced one is created
fresh. Wherever that rename could not run, three reads still take either spelling — issue routing, the community
sweep's dedup marker, and the closed-issue sweep's query — and a namespaced label always outranks a bare one on the
same issue. What a PAT without `Issues: Read and write` leaves behind, and which bare tags a relabel deliberately does
not delete, are in [`state-machine/labels-and-state.md`][legacy-labels].

<a id="per-tick-flow-workflowtick"></a>

## Per-tick flow (`workflow.engine.tick.tick`)

One repo's pass runs the base refresh, the community-contribution PR sweep, and the repo skill-catalog emission, then
dispatches each pollable issue by workflow label. **Family-aware labels** (`workflow:decomposing`,
`workflow:blocked`, `workflow:umbrella`, unlabeled pickup) read and write cross-issue parent ↔ child state, so they
fold into one bucket per repo that drains sequentially; every other label fans out concurrently up to
`MAX_PARALLEL_ISSUES_GLOBAL` / `MAX_PARALLEL_ISSUES_PER_REPO`. An open `workflow:blocked` / `workflow:umbrella` issue
joins only on the ticks `DEPENDENCY_POLL_EVERY_N_TICKS` makes due — the first poll and every Nth after it, default
`5` — and is dropped before that split in between, which saves the child reads its dependency walk spends at the price
of up to N ticks before a child is activated, a parent completes, or drift on either is detected; `1` dispatches it
every tick. Only issue numbers cross the thread boundary — each
worker mints its own `GitHubClient` and re-fetches the issue. The cap exemptions, the `duplicate_active` gate, and
what each step reads and writes are in [`state-machine/labels-and-state.md`][per-tick]; the multi-repo dispatch and
scheduler lifecycle around them are in
[`architecture.md#per-tick-flow-workflowengineticktick`](architecture.md#per-tick-flow-workflowengineticktick).

Two parks are answered by the dispatcher rather than by a stage. The first is the agent-run limit. An issue
standing on `agent_run_limit` has spent every
agent run it is allowed, and every stage below reads `awaiting_human` as the park it was written against —
a resume on the next trusted reply, a hold waiting on guidance, a classifier that refuses a command carrying none —
none of which buys back a run. So it is held once, ahead of the handler table and behind only the two guards that
have to RUN (an authorized restart and a cancelled cycle's cleanup); the hold says the sentence the park still owes,
since nothing below it would, and it steps aside for work that has ENDED so a terminal arc can finish — a closed
issue, which the object in hand already shows, and a recorded pull request that has merged or been closed, which it
cannot: a merge leaves the issue open until a stage terminal reads it, and a close nobody merged leaves it open for
good, so a spent issue behind either would sit on a park nothing lifts over work a human already decided. That second
reading is a request per parked poll and fails OPEN, since a remote that would not answer says nothing about whether
the work is over. The one reading of
a thread that lifts it is answered in the same place: a trusted `/orchestrator add-agent-runs N`, bounded per
command, which persists an allowance of exactly `used + N`, puts back the park the refused launch was on, and lets
that tick go on to the stage its label names — so a resume refused on a reply is resumed on that reply. What it widens
is what the issue may still spend, since nothing returns a run already taken.

The second is `report_record_damaged`, taken by the developer-report reconciliation for the same kind of reason: the
record is the dispatcher's to act on, so a record nobody can read is nobody below's to explain. It is announced once
and then held silently, and the same guard retires it — a record repaired and settled, or the field cleared to
abandon the report, both take the flags down, because a park nothing takes back leaves every stage behind the guard
reading the issue as waiting on a reply nobody owes. Where another route's park already stands, this one is **not**
taken and the tick is **not** held: the pinned flags are single, so writing over that reason would discard an
obligation a stage is still waiting on — and what answers a foreign park is the handler behind this guard, so
holding in front of it would leave both parks standing for the life of the issue with neither announced. It stands
down instead, and takes its own park on the tick after that one clears
([`state-machine/delivery-stages.md`](state-machine/delivery-stages.md#the-developer-report-transaction-every-dispatch)).

### Base refresh

Before any issue is dispatched the tick fetches `<remote>/<base>` once and rebases each existing per-issue worktree
onto it, so a long-lived worktree does not stay anchored to whatever base looked like when it was added. A pre-PR
worktree rebases locally; a PR-having one in `workflow:validating` / `workflow:documenting` / `in_review` /
`workflow:fixing` pushes the clean rebase with a pinned `--force-with-lease`, resets `review_round`, and relabels to
`workflow:validating`, reaching `workflow:resolving_conflict` only when the rebase actually leaves conflicted files.
That push goes through the size gate, and where the branch was standing on the commit an authorized settlement
accepted the refresh hands the gate the same rewrite evidence a squash does, so a replay that contributes what a human
already ruled on carries the exemption — and the operator authorization that made it a bypass — over instead of being
adjudicated again. A transfer of an exemption nothing authorizes is refused, since moving one would hand the rewritten
commit a permission the accepted one never had. A process lost anywhere in that rebase comes back to the record the
attempt pinned, and the recovery finishes it on the permit alone — reissuing a push that never went out, receipting one
that landed through a leased no-op — so the replay is never measured or adjudicated again. The `question` and
`discussion` labels — and the parks and in-flight discussion records that outlive them — skip both paths. Beside an
interrupted auto rebase's anchor, of the records and parks that freeze a branch only the late size-gate claims keep the
refresh away, so its recovery answers the anchor ahead of any stage handler. The failure modes, their durable
`park_reason` tokens, and the refresh-owned retry are in
[`state-machine/labels-and-state.md#base-refresh`](state-machine/labels-and-state.md#base-refresh).

### Pollable issues and finalization

`gh.list_pollable_issues()` yields every open non-PR issue plus the closed ones still carrying one of the ten swept
labels — the eight a terminal arc may still be owed on, and `workflow:decomposing` / `workflow:umbrella`, whose
closed issues are yielded for snapshot cleanup only and never reach the stage handler their label names — each also
queried under its pre-namespace spelling where it has one, so an external merge or an operator close finalizes
cleanly instead of stranding the issue. `CLOSED_ISSUE_SWEEP_EVERY_N_TICKS` batches that sweep to once every N ticks,
which is the knob for the GitHub primary-rate-limit cost it carries on a multi-repo host. Which labels are swept, why
the pre-PR labels are not, and how a closed `discussion` is held for its plan PR are in
[`state-machine/labels-and-state.md`][pollable].

### Pinned state

Per-issue durable state is a single **pinned comment** on the issue (`<!--orchestrator-state {...json...}-->`),
trusted as state only when the orchestrator's own account authored it and its whole body is the marker. Its keys group
into agent identity, decomposition, PR / branch, the drift baseline, the HITL park, the in-review watermarks, the
final-docs handoff, fix routing, the crash-recovery anchors, counters and timestamps, the per-issue usage meter, the
lifetime agent-run ledger beside it — what the issue is allowed, what it has spent, and the launch holding a charge,
charged at the one boundary every agent process is invoked from —
the `agent_run_limit` park a spent one leaves and the sentence that park owes the thread,
the additive `late_*` group a late generation is adjudicated under, the one commit an accepted candidate publishes
under with the semantic identity of the change it was accepted for and the bounded authorization a workflow rewrite
carries that exemption over with, the `decomposing` stage's own record of the run that adjudicates one, and the
additive `developer_report_*` group one report publication is recorded as — the report a completed run delivered
before its code went out, the transaction that report is bound into once a pull request carries the code, the report
the pull request carries, and the receipt one finished transaction leaves. Its owners read and write those records
fail-closed; the initial implementation delivery produces and settles one on the tick it publishes, and the
dispatcher reconciles an outstanding transaction ahead of every handler
([the developer-report transaction](state-machine/delivery-stages.md#the-developer-report-transaction-every-dispatch)).
Every key, what writes it, what spends it, and the legacy `codex_session_id` still honored on read are in
[`state-machine/labels-and-state.md#pinned-state`](state-machine/labels-and-state.md#pinned-state).

## Stage handlers

Each workflow label dispatches to one `_handle_<label>` function under `orchestrator/workflow/stages/`, with two
exceptions that belong to no label of their own: one read of the issue's own pinned comment runs ahead of every
handler and can stop the tick outright, and a CLOSED issue on `workflow:decomposing`, `workflow:umbrella`,
`workflow:ready`, or `workflow:blocked` goes to the cleanup sweep instead of the stage its label names — the first
two because a late adjudication runs there, the other two because a decomposition outcome that landed after its
owner was observed closed can leave that adjudication's ending under one of them. Both are on the delivery-stages
page below. The delivery stages — pickup through the PR loop — are in
[`state-machine/delivery-stages.md`](state-machine/delivery-stages.md); the two operator-applied conversation stages
are in [`state-machine/conversation-stages.md`](state-machine/conversation-stages.md). Which module owns each handler
is in [`architecture/workflow-modules.md`](architecture/workflow-modules.md), and the dispatch that reaches one in
[`architecture.md#stage-handlers`](architecture.md#stage-handlers); what the agent each one spawns is allowed to
do is in [`workflow.md`](workflow.md).

### `_handle_pickup` (no label → `workflow:decomposing` or `workflow:implementing`)

An open issue with no workflow label: when `ALLOWED_ISSUE_AUTHORS` is set an issue from outside the list is silently
skipped; otherwise the handler posts the pickup comment, anchors `pickup_comment_id` and `last_action_comment_id` on
it (the floor the park ending the first agent run walks from), snapshots `user_content_hash`, and routes to
`workflow:decomposing` (`DECOMPOSE=on`) or `workflow:implementing` (off), running that stage's handler in the same
tick. Full flow: [`state-machine/delivery-stages.md`][pickup].

No unlabeled issue that already carries a pinned comment reaches it. Greeting one a second time writes a second
pinned comment that every later read shadows, so an issue whose workflow label a human removed is left where they
left it and driven back in by applying a label by hand. The one exception is the restart: taking `rejected` off an
issue whose pinned comment records a late cancellation with nothing left owed authorizes a fresh late-split cycle,
which reaches the same two labels by projecting the comment the issue already has —
[`state-machine/labels-and-state.md`](state-machine/labels-and-state.md#late-generation-state).

### User-content drift detection

The drift-sensitive handlers hash the issue title, body, and every human-authored issue-thread comment, and react
once to a change: `workflow:decomposing` re-spawns inline, `workflow:ready` / `workflow:blocked` /
`workflow:umbrella` route back to `workflow:decomposing`, the dev stages resume the locked dev session, and
`workflow:documenting` unwinds to `workflow:validating`. A reply to a parked `workflow:implementing` or
`workflow:validating` issue is not such a change: those stages measure a parked tick by what the park had already
read, and the frozen reply batch delivers the reply. On `workflow:validating` that reply can still be the drift
road's CONTINUATION rather than an ordinary fix: a park left standing over an edit its own resume never answered, or
over a report the issue owes, makes the next reply read the way the resume's own answer reads — held to the developer
report contract before the size gate, with a report and no commit published onto the unchanged head. Either way the
report is stamped with the requirements revision that session was actually handed — the drift check's own hash for
the resume it launched, and the revision the frozen batch delivered for the reply continuing it — and no reviewer
runs until the pull request carries it. `in_review` runs the same contract on its own drift resume, recording the
report under its own route ahead of the size gate and publishing a report with no commit onto the head the pull
request carries; the issue then goes back to `workflow:validating`, which is where that reviewer waits.
`_handle_fixing`, `_handle_question`, and
`_handle_discussion` deliberately skip the check. The eight non-human filters (including the untrusted-author filter
and the whole-comment operator-command exclusions — `/orchestrator continue`, `/orchestrator add-agent-runs N`, and
`/orchestrator authorize-oversized <commit>`), the
legacy-hash normalization, and the per-stage result routing are in
[`state-machine/delivery-stages.md#user-content-drift-detection`][drift].

### `_handle_decomposing` (label `workflow:decomposing`)

Two questions wear this label, and the tick asks which one it is first. An issue whose record carries a live late
generation is not waiting to be decomposed — its implementation is committed and measured past the ceiling — so the
whole tick belongs to the late coordinator and nothing below runs for it. Everything else is the initial
decomposition: the decomposer runs read-only in a scratch worktree and its fenced `orchestrator-manifest` block is
parsed, where `single` posts the collected-context comment and flips to `workflow:ready`, and `split` creates children
labeled `workflow:blocked` and leaves the parent on `workflow:blocked` or `workflow:umbrella`. Half-finished splits
recover rather than re-spawn, a `DECOMPOSE` kill switch falls through to `workflow:implementing`, and commits or a
dirty tree park with the worktree kept. An issue standing on a `retry_cap` park is held ahead of all of that — the
drift reset, the kill switch, and the human-reply resume each answer a park that is not this one — so it keeps
everything it carries until a trusted `/orchestrator continue` buys it one more attempt. The late coordinator holds
the same park one step earlier on its own road, so an issue whose adjudication ran the budget out keeps its frozen
candidate, the pull request that candidate stands under, and its recorded run until the same command buys it one
more adjudication. Full flow:
[`state-machine/delivery-stages.md`][decomposing].

### `_handle_ready` (label `workflow:ready` → `workflow:implementing`)

A pass-through: post the pickup comment if needed, ratchet `last_action_comment_id` past everything posted while the
issue sat in `workflow:decomposing` / `workflow:blocked`, flip to `workflow:implementing`, and fall into that handler
on the same tick. Full flow: [`state-machine/delivery-stages.md`][ready].

### `_handle_blocked` (label `workflow:blocked`)

The parent reads each child's current label: every child `done` flips the parent to `workflow:ready`, a `rejected` or
manually-closed child parks it, and the dep-graph walk relabels any `workflow:blocked` child whose recorded
dependencies are all `done` to `workflow:ready`. A child with no children of its own and a recorded `parent_number`
is a no-op. Full flow: [`state-machine/delivery-stages.md`][blocked].

### `_handle_umbrella` (label `workflow:umbrella`)

Mirrors `_handle_blocked` for the rejected / manually-closed checks and the dep-graph walk; the difference is the
terminal — every child `done` reconciles whatever the issue still owes a remote, then posts a checkmark comment,
stamps `umbrella_resolved_at`, sets `done`, and closes the issue, since an umbrella has no implementation of its own.
An umbrella a late split made owes the superseded branch and the snapshot ref its children were cut from, and this is
the last tick that could settle either — so the park a `rejected` or hand-closed child earns settles the same ledger
on its way out, since nothing revisits an open umbrella either. Something still owed keeps the label, which is the
retry. Full flow: [`state-machine/delivery-stages.md`][umbrella].

### `_handle_implementing` (label `workflow:implementing`)

Spawns (or resumes) the locked dev session in the per-issue worktree at
`<WORKTREES_DIR>/<owner>__<name>/issue-<n>` on branch `orchestrator/<owner>__<name>/issue-<n>`. Only a fresh spawn is
gated by the 24h retry budget (`MAX_RETRIES_PER_DAY`, shared with decomposing) — an awaiting-human resume and a
recovered worktree, which skips the agent entirely, are carry-over work rather than retries. An exhausted budget
parks the issue as `retry_cap`, says so once, and stands until a human answers it — and that park is answered ahead
of the drift and resume roads below it, so the only thing that lifts it is a trusted `/orchestrator continue` buying
one more attempt, exactly as on `workflow:decomposing`. New commits on a clean
tree are measured by the late size gate and then push the branch, open or reuse a PR, and set `workflow:validating`;
a candidate strictly past `MAX_ADDED_LINES` is held unpublished and routed to `workflow:decomposing` instead —
unless an exemption nothing authorized names it, which is a change already ruled one change, so it parks
`late_unauthorized_exemption` for the operator rather than paying for a second adjudicator — and one
that could not be measured parks rather than publishing — except a base the TRANSPORT could not reach, which is
counted quietly for three consecutive misses on the same pair, saying nothing and spawning nothing, before the fourth
takes that park. The park keeps the frozen pair, names the step the reading stopped at once per step, and is answered
here by a trusted bare `/orchestrator continue`, which re-measures that exact pair and spawns no agent. So does a
checkout that cannot name the commit it is on:
where the gate proved none — a new candidate while `DECOMPOSE=off` — the checkout is what names the commit the push
carries, the receipt records, and both proofs around the push compare against, so one that can name none publishes
nothing. A dirty tree, a tree `git status` could not report on, or a no-commit reply parks; a tree that stops being
provably clean between the measurement and the handoff refuses the publication or the handoff the same way a moved
checkout does. Every park that gate takes is routed by one owner (`implementing/late_recovery.py`) ahead of every
spawn and back through the same committed-work seam, because on all of them the work is committed already: the
measurement park above, the handoff's own moved-checkout park, and a standing `late_unauthorized_exemption` — the
park an oversized candidate takes when the exemption naming it has no operator authorization behind it, ended by a
trusted whole-comment `/orchestrator authorize-oversized <commit>`. A
`timed_out` run disposes on whether the run left a commit — HEAD moved past `pre_implement_sha` AND the branch is
ahead of `<remote>/<base>`, since a head that moved onto the base was written by nobody. The park it leaves freezes
the branch out of the pre-tick base refresh, and the next tick's silent recovery asks that same pair, so a base a
rebase fast-forwarded the checkout to is never published as a late-landing commit. `interrupted` or a mid-run
`paused` returns without writing pinned state. The external-merge short-circuit, the `/orchestrator continue` retry,
and the plan-PR question the merge terminal is reached past are in
[`state-machine/delivery-stages.md`][implementing].

### `_handle_documenting` (label `workflow:documenting`)

The single docs pass on the existing PR worktree, reached only via the final-docs handoff in `_handle_validating`'s
approval branch. It reuses the locked dev session — there is no `documenting_agent` and no separate retry budget —
and advances to `in_review` on either a pushed docs commit or an explicit `DOCS: NO_CHANGE` verdict. Under
`PR_REF_IN_SUBJECT` that docs commit goes out with its subject ending in exactly one ` (#N)`, naming the pull request:
before the size gate it is replaced by a commit bound to the one the pass made — same author, tree, and body — so the
gate, a hold, the push, and the recorded SHAs all name the replacement. Both this issue's number and the request's are
handed to the shared normalization, so a subject the agent left carrying the issue's own reference — alone, or beside
one an earlier publication appended — sheds it, while a subject that already reads as the normalization would write it
is published as it is. Drift
during the hop unwinds the worktree and relabels back to `workflow:validating` without spawning. The tick opens by
ending the
handoff record that brought the issue here, if one is still standing: this stage having the issue is the only proof
the relabel behind that handoff landed, and left standing the record would answer a drift unwind's re-review by
sending the unchanged head straight back. Full flow:
[`state-machine/delivery-stages.md`][documenting].

### `_handle_validating` (label `workflow:validating`)

Spawns a **fresh** reviewer every round (so a `REVIEW_AGENT` flip takes effect on the next tick) with a read-only
prompt that must end in `VERDICT: APPROVED` or `VERDICT: CHANGES_REQUESTED`. An approval runs the local verify gate,
then `SQUASH_ON_APPROVAL`, then hands off to `workflow:documenting`; `CHANGES_REQUESTED` flips to `workflow:fixing`
**before** the dev spawn. `MAX_REVIEW_ROUNDS` parks with the `/orchestrator add-review-rounds N` escape hatch. No
reviewer spawns while a developer report this issue recorded is still owed to the pull request.

A squash this issue began and did not finish is answered ahead of all of that, behind only the terminals and ahead of
every route that could point an agent at the branch: a branch mid-rewrite is not one a reviewer or a body-edit resume
may be run over, and a collapse the remote already carries would otherwise never get the notice, the watermarks, and
the relabel its handoff owes. An issue with nothing recorded costs one lookup on the pinned comment. Full
flow: [`state-machine/delivery-stages.md`][validating].

### The size gate on a published pull request (every push onto an open PR)

Ten pushes reach a pull request the remote already carries — the shared dev-fix publication, the fixing handler's
no-feedback bounce, the two validating recoveries, the three conflict publications (agent-resolved, clean rebase, and
recovered commits), the base sync's own auto-rebase and crash recovery, the final docs pass, and the squash on
approval — and the same late size gate stands in front of every one of them, through one call that measures, pushes,
and spends the debt the push pays. What it measures is what the pull request would **come to** — three-dot from the
base the remote names to the candidate, so the whole pull request rather than the diff this one push adds — and a
candidate strictly past `MAX_ADDED_LINES` is held off the branch and routed to `workflow:decomposing` from whichever
of `workflow:validating` / `workflow:documenting` / `in_review` / `workflow:fixing` / `workflow:resolving_conflict`
that push was reached under. The commit an adjudication accepted skips the reading only where an operator's
`late_override_*` authorization names it too and the contribution between the pair that record names still
fingerprints to what it says: an exemption is an agent's verdict, so on its own it is half a bypass, and a commit
only it names is measured like any other. The one thing such a commit still buys is the bookkeeping behind a
publication that has already happened — a pull request this call froze and found standing on that exact commit
finishes its relabel, receipt and debt, since the push would move nothing and holding it back would strand published
work under a stage no later tick advances. The stage, the pull request, and the head it stands on are frozen into
the record before any effect — and that pull request has to be open on the branch this publication will push, and
have its head in this repository, since the number and the branch are two fields on one pinned comment whose two can
disagree and a fork carries this repository's ref names over its commits; the push it allows is named against the
measured commit and
leased against that frozen head; a tree that is not provably clean, an unreadable or closed pull request, and a head
that moved off the frozen one each park rather than push. A pair frozen and never counted is measured ahead of the
handler on the next tick, by the dispatcher, on the stage the record names — and one whose checkout is not on this
host stops the tick instead of letting the stage run over a candidate nobody read. An auto-rebase anchor still
standing — a failed base fetch or a pull request that would not read returns before its recovery runs — holds the
handler back the same way, on every label and on the live adjudication's own road too, unless a hard-skip stands. On
a label the refresh does not drive — read-only stages and a generation still under adjudication included — nothing
is waited on: the dispatcher answers the anchor itself on the refresh's ineligible road, a clear or the stranded
park, and holds the handler until the record ends. On one it drives, a late claim the reconciliation answers — a
frozen pair, an approved push — releases the hold, since it keeps the refresh away and nothing but the reconciliation
ends it, and the hold is asked again once the reconciliation has run, so a claim it spends leaves the anchor holding
the tick. Every other record and park the refresh freezes on holds: a stage's handler takes its park down on a reply
and runs on into the agent it was holding back, and a timeout, a reading nobody could take, or a collapse mid-rewrite
is likewise ended by a handler the hold keeps back. So beside an anchor none of them keeps the refresh away, and the
refresh answers the anchor under them with the recovery alone, no reply spent, leaving each for its owner. A pull
request that merged or closed is asked for first under any park, the refresh's own included, and ends the attempt's
whole handoff there, so the hold never outlives it. A checkout
whose HEAD names a commit nothing can read stays held until the refresh has reset and parked it, and one that is not
on disk is restored, so the next refresh walks it.
Both roads that reconciliation takes end in a push, so an issue that is closed and a pull request that has merged or
been closed are each handed back to the stage terminal ahead of it, with the generation, the receipt and the debt left
exactly as they stand. Work that
ends *after* the gate has read it — a close a poll latched, or a pull request somebody merged or closed in the window
behind the entry freeze, whose branch is still at the head this tick froze so the lease would succeed — is refused
immediately before the push itself; the initial publication and the push a settled adjudication makes from
`workflow:decomposing` each carry the same barrier, and the second needs it most, since it reaches the transport
directly and its pull request was last read several steps back. That same reading is what a measurement park here is
retried by: it retakes the parked pair once a poll and asks nobody first, so a transport that comes back settles the
park without the human it mentioned ever replying, and each of those readings is held silently while it goes on
stopping at the step the standing notice named. Full flow: [`state-machine/delivery-stages.md`][published-gate].

Three of those pushes are REWRITES of the commit an adjudication accepted, and each may carry that exemption onto the
commit it produced instead of being measured: the squash on approval, the base refresh's clean rebase, and the clean
replay `workflow:resolving_conflict` runs — each only by the owner that ran it, over two canonical fingerprints that
agree. `late_exempt_sha` stays the exact commit a publication is matched against, the semantic identity beside it is
what a rewrite is proved against, and the rotation between them is a permission written before the push and settled
by the receipt of the landed push in one write, reported by one `late_transfer` record and no second verdict. A
descendant, a fix, the docs pass, a conflict resolution, and a heuristic match earn nothing and are measured afresh:
[`state-machine/labels-and-state.md#exemption-identity-and-rotation`](state-machine/labels-and-state.md#exemption-identity-and-rotation).

### `_handle_in_review` (label `in_review`)

A PR is open and humans drive the merge — the orchestrator never merges from here, so any `merged` state it observes
was produced externally. Behind the terminals, an issue whose approval a requirements edit made stale — one still
owing a developer report a drift resume recorded, or carrying the marker a hand-back whose relabel did not land
leaves — goes straight back to `workflow:validating`, since only that stage binds the report and re-reviews. The
handler scans four feedback surfaces over three id namespaces — the issue thread and the PR conversation share one,
so each is read against its own cursors before the two merge — and routes to `workflow:fixing` without advancing the
watermarks, falls back to the drift check, and otherwise posts the one-shot `:bell:` HITL ping when the head is
mergeable, docs-complete or GitHub-approved, and carries no standing human CHANGES_REQUESTED. Full flow:
[`state-machine/delivery-stages.md`][in-review].

### `_handle_fixing` (label `workflow:fixing`)

The dev fix loop, entered from `in_review` on unread feedback or from `workflow:validating` on a
`CHANGES_REQUESTED` verdict — `pending_fix_at` is the route discriminator that decides whether a pushed fix resets
`review_round` or bumps it. It owns the `IN_REVIEW_DEBOUNCE_SECONDS` quiet window, the `/orchestrator continue` batch
replay, the stranded-fix publish, the in_review-route ACK fast path, and the worktree-drift dead-lock breaker that
hands a stuck validating-route park to `workflow:resolving_conflict`. Full flow:
[`state-machine/delivery-stages.md`][fixing].

### `_handle_resolving_conflict` (label `workflow:resolving_conflict`)

Rebases the PR branch onto `<remote>/<base>` under a hardened git envelope and force-with-lease pushes the result,
flipping back to `workflow:validating` with `review_round=0` and `conflict_round` bumped — reached from an operator
relabel, from the base refresh when a rebase actually conflicts, or from `_handle_fixing`'s dead-lock breaker. A
conflicted rebase resumes the dev; a diverged branch parks unless the worktree is a recognizably orchestrator-produced
unpushed rebase, or one this stage's own replay record accounts for. `MAX_CONFLICT_ROUNDS` caps it. Full flow:
[`state-machine/delivery-stages.md`][resolving-conflict].

### `_handle_question` (label `question`)

The operator-applied read-only Q&A label: the decomposer's backend answers in the per-issue worktree under its own
`question_agent` / `question_session_id` pin, posts the answer pinging `HITL_HANDLE`, and parks. No PR is opened and
no branch is pushed. Commits, a dirty tree, or a timeout park with the worktree **kept** for inspection; closing the
issue flips it to `done`. Per-`park_reason` semantics and the relabel guard are in
[`state-machine/conversation-stages.md`][question].

### `_handle_discussion` (label `discussion`)

The operator-applied architecture discussion: the decomposer explores the design as a tree and closes each round with
a numbered frontier, parking until a trusted human reply resumes the same session. Once a human confirms the shared
understanding the agent may commit `plans/issue-<number>.md` alone, and the stage publishes that one file as a plan
PR whose verdict ends the issue — merged is `done`, closed unmerged is `rejected`. The `issue-N` checkout is
preserved on every round exit. The publication checks, the crash-recovery records, every `discussion_*` park, and the
read-only guard screening a relabel to `workflow:implementing` are in
[`state-machine/conversation-stages.md`][discussion].

## State transition (label lifecycle)

The compact reference diagram for every arc above — the forward spine, the decompose branch, the validating fix loop,
the `in_review` and `workflow:fixing` terminals, the conflict rounds, the family walks, both conversation stages, and
the shared awaiting-human park — is in [`state-machine/lifecycle.md`](state-machine/lifecycle.md).

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
