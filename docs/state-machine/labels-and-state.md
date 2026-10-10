# Workflow labels, per-tick flow, and pinned state

This page is the authoritative spelling of the state machine's public contract: the label set and how a wire label is
spelled apart from the stage under it, the migration off the pre-namespace spellings, what one tick reads and writes
per issue, and every pinned-state key a handler depends on. Live GitHub issues carry these strings, so a rename here
is a migration rather than a refactor.

The handlers that act on them are in [`delivery-stages.md`](delivery-stages.md) and
[`conversation-stages.md`](conversation-stages.md); the compact label-lifecycle reference is in
[`lifecycle.md`](lifecycle.md). For the summaries these sections are reached from, see
[`../state-machine.md`](../state-machine.md).

## Workflow labels

An issue should have at most one workflow label at a time. Non-workflow labels such as `bug` or `enhancement` are
preserved; the orchestrator only swaps labels from its own workflow set. Label names are part of the public contract
because live GitHub issues carry them.

A state's label and the stage under it are spelled apart throughout this file. `workflow:<tag>` is the **wire label**:
the literal string on the GitHub issue, which is what a label write puts there, the transition guard checks, the
pollable-issue queries ask for, and the per-tick dispatcher partitions on. A bare `<tag>` is the **stage**: the handler
that runs while an issue carries that label, the subpackage under `orchestrator/workflow/stages/` holding it, and the
identifier analytics rows, audit event payloads, and agent-session attribution carry. The labels that were never
namespaced — `in_review`, `question`, `discussion`, and the `done` / `rejected` terminals — read the same either way.

The prefix is a collision guard, not the membership test — being a `WorkflowLabel` member is. A `workflow:`-prefixed
name that is not one resolves to no state at all: the `workflow:dependencies` / `workflow:github_actions` /
`workflow:python:pip` service labels Dependabot stamps on its update PRs
([configuration/operations.md](../configuration/operations.md#continuous-integration)) share the prefix and nothing in
the tree reads them, so they route nowhere and a label write leaves them in place exactly as it leaves `bug` or
`enhancement`. Applying one as a workflow label is what the typo guard below rejects.

`workflow:python:uv` is a retired Dependabot service label. Existing PRs retain it; the `pip` entry stamps
`workflow:python:pip` on new updates. Both are outside the workflow state vocabulary.

Three non-workflow **control labels** modify behavior without occupying the workflow slot:

- `backlog` makes the orchestrator skip the issue: the per-tick dispatcher filters it out before the family/fanout split
  (so a parked, workflow-label-less issue cannot fold into the cap-counted family bucket and starve other work under
  `parallel_limit=1`), and each stage handler also skips it before the workflow label is read. Removing it hands control
  back to the state machine on the next tick.
- `paused` is the same hard skip as `backlog` at every point (dispatch, scheduler routing, `_process_issue`, and base
  sync), differing only in intent: `backlog` is a "not yet" hold on a fresh issue, `paused` freezes an already
  in-flight one without discarding its state. Removing it resumes processing on the next tick. Because those skip
  points read the issue's labels at tick start, every stage that runs an agent additionally re-checks a freshly
  fetched issue right after the run returns (`_paused_during_agent_run`, alongside each stage's `interrupted`
  short-circuit — both live on the `workflow/engine/guards.py` owner the stage leaves import directly): the dev-agent
  stages that resume committed work (`implementing`, `in_review`, `fixing`, `resolving_conflict`, the `validating`
  drift / awaiting-human / reviewer-change dev resumes, and the `documenting` initial and follow-up docs passes) and
  the stages whose agent is not a developer (the decomposer run in `decomposing`, fresh spawn and awaiting-human
  resume; the reviewer run in `validating`; and the question and discussion runs, opening round and awaiting-human
  resume alike) all consult it. A `paused` applied
  mid-run stops before a PR opens, the label flips, a HITL park or ACK comment posts, a docs push lands, usage
  counters fold, child issues are created, watermarks advance, or pinned state advances, so a dev stage's committed
  work stays on the branch and republishes through the normal recovered-worktree / stranded-fix path once the label is
  removed, while the read-only decomposer / reviewer / question runs simply re-run from durable state on the next
  tick. The `discussion` run is read-only only until the humans confirm the design: a confirmed round commits
  `plans/issue-<number>.md`, so a pause can leave that commit on the branch with no disposition, exactly as a crash
  can. It is not re-run — the pre-spawn write (the round anchor, `discussion_round_open`, and `discussion_base_sha`)
  is durable whatever the pause withholds, and the next tick reads the commit back through it: a valid plan is judged
  and published as the withheld round would have, and anything else parks on what the branch actually carries. Only a
  round that committed nothing re-runs against the same replies, since the watermark it staged is one of the
  mutations the pause leaves unpersisted. Because `paused` is a plain control label, removing it is the entire resume
  protocol — the next poll picks the
  issue back up from durable state; there is no un-pause command. This is distinct from `/orchestrator continue`
  ([`_handle_fixing`](delivery-stages.md#_handle_fixing-label-workflowfixing)'s `_handle_continue_command`, plus
  the shared implementing / documenting handling), which retries
  only specific `awaiting_human` session-failure parked *retry* flows — and, on a `decomposing` or `implementing`
  issue parked under [the retry budget](#the-retry-budget), renews that budget for one more spawn: pausing is never a
  `park_reason`, so a continue command is not an un-pause and does not clear `paused`. It is unrelated to un-pausing,
  but not exempt from it — the hard skip fires in `_process_issue` before any handler, so a continue comment posted
  on a paused issue is deferred with everything else until the label is removed.
- `workflow:community_contribution` is applied by the per-tick open-PR sweep (on the `workflow/engine/community.py`
  owner, which the tick drives before per-issue dispatch): any open PR whose author is not in `ALLOWED_ISSUE_AUTHORS`
  is labeled and `HITL_HANDLE` is @-mentioned once per PR. Bot-authored PRs (Dependabot, Renovate, CI bots) are
  skipped via GitHub's `user.type == "Bot"` flag — they open PRs structurally and are not community contributions. The
  orchestrator does not otherwise drive these PRs. The label is the sweep's own dedup marker rather than an operator
  control, which is why it is namespaced where `backlog` / `paused` are not, and why the sweep asks for both its
  spellings: a PR the bootstrap rename could not reach is already labeled, and re-labeling it would repeat the ping.

### Typed states and the transition guard

The label vocabulary is defined once in [`orchestrator/workflow/state.py`](../../orchestrator/workflow/state.py), which
callers import directly: `WorkflowLabel` (a `StrEnum`) is the single source of truth for workflow states,
and `ControlLabel` holds
the modifiers above. Because `StrEnum` members *are* their wire strings, a member is the GitHub label verbatim — the
enum just gives the names one authoritative definition. The labels the orchestrator writes itself are namespaced
`workflow:<tag>` so a repository's own labels cannot collide with them; `in_review`, `question`, `discussion`, `done`,
`rejected`, and the `backlog` / `paused` controls keep their bare spelling because a human applies or reads those
directly. The automatic `workflow:community_contribution` control is namespaced with the rest of what the
orchestrator applies. The
namespace stops at the GitHub boundary, and `stage_name` on the same owner is what strips a wire label back to the
stage tag every sink below that boundary records. A repository whose labels predate the namespace still carries the
bare spellings; how it moves off them is [below](#legacy-labels-and-the-migration-off-them).

Two guards run at `GitHubClient.set_workflow_label` (the single label-write chokepoint; `create_child_issue` bypasses
`set_workflow_label` and shares only the typo guard for its direct write, coercing each child label through
`label_reading.coerce_workflow_label` — the same strictness):

- **Typo guard (always strict).** A label name not in `WorkflowLabel` raises immediately, so a typo cannot be applied as
  a literal label that the next tick would treat as unlabeled-pickup. `create_child_issue` coerces each birth label the
  same way, so split children are born with only a valid workflow label and any control label is rejected.
- **Transition guard (`WORKFLOW_TRANSITION_GUARD` = `off` / `warn` / `enforce`, default `warn`).** An illegal
  `current → new` relabel is checked by `transition_guard.guard_transition` against `transitions.ALLOWED_TRANSITIONS`.
  `warn` logs the rejected edge through the
  `orchestrator.state_machine` logger and proceeds; `enforce` raises `IllegalTransition`; `off` disables the check. A
  same-label re-set is always allowed. That logger name is spelled out literally in the owner, so an operator log
  filter selects on it regardless of which module the guard lives in. One write asks to skip it (`guarded=False`), and
  only one: the late size gate putting a label back where a human moved it from. The graph describes the moves this
  orchestrator makes, so it has no edge for repairing one it never made — a guarded `workflow:validating →
  workflow:decomposing` restoration would raise under `enforce` and strand the generation under the wrong label for as
  long as the operator kept the guard on, which is the opposite of what the guard is for. See
  [`../workflow/roles.md`](../workflow/roles.md#what-the-humans-can-still-change-while-a-candidate-is-frozen).

The write also leaves the issue object it went through reading what it wrote. PyGithub's `Issue.set_labels` sends the
replacement and keeps nothing of GitHub's answer, so once the request returns the chokepoint stores the label set it
sent on that same object — without a second request — and only then emits `stage_enter`. Two relabels through one
object in one tick, such as pickup's `workflow:decomposing` followed by the decomposition outcome's `workflow:ready`,
are therefore each guarded against the state the one before left, and a write GitHub refuses raises before the cached
labels or the event move. Any other object fetched for the same issue still carries the labels it was fetched with.

`ALLOWED_TRANSITIONS` is a forward spine (e.g. `workflow:implementing → workflow:validating → workflow:documenting`)
plus interrupt / detour edges declared per-target. It is keyed by `WorkflowLabel` members, so a pre-namespace label
resolves to its member before the guard sees it and is checked against the same edges. Operator relabels via the
GitHub UI bypass both guards, so the guard never fights a human.

Fourteen of those edges belong to the late size gate and are declared ahead of the handlers that write them.
`workflow:implementing → workflow:decomposing` is the route a clean committed candidate measured past the threshold
takes instead of publishing — adjudication runs under the existing decomposing label rather than a state of its own.
`workflow:validating`, `workflow:documenting`, `in_review`, `workflow:fixing`, and `workflow:resolving_conflict` each
own the same edge, and they own it because the gate stands in front of every push onto a pull request the remote
already carries: a commit joining a branch a pull request is open on is measured for what that pull request would COME
TO, and one past the ceiling is held off it and adjudicated from whichever of the five states that push was reached
under. A candidate an exemption nothing authorized names takes none of those edges at any of the six: the change has
been ruled one change already, so it is held where it stands under `late_unauthorized_exemption` and waits for the
operator instead ([the HITL park](#pinned-state)). The pre-PR states own no such edge — nothing there has a
publication to be measured against.
The same five own the edge BACK — `workflow:decomposing → workflow:validating` / `workflow:documenting` /
`in_review` / `workflow:fixing` / `workflow:resolving_conflict` — because a settlement returns the
issue to the stage it was taken out of rather than to `workflow:implementing`: that stage is the only owner of the
completion the candidate still owes, and the record names which one it was
([below](#late-generation-state)). Both directions are declared from one set, so the way in and the way back cannot
drift apart.
The existing `workflow:decomposing → workflow:implementing` edge beside it is the way back a settlement of work
nothing had published takes, carrying the exemption naming the adjudicated commit, so the ordinary publication
reconciles that exact commit the way it does for any other change.
An adjudicator's own `single` walks neither: what a verdict earns is the park a human's decision to publish the
candidate unsplit is owed on, and the settlement those edges belong to is what such a decision would license
([`../workflow/roles.md`](../workflow/roles.md#what-a-verdict-the-read-cleared-earns)). The edges are declared all
the same, because a generation entered from one of the five is a generation that still names which state it would
be settled back into.
`workflow:decomposing → rejected` and `workflow:umbrella → rejected` are the one terminal a late generation whose
owner was closed mid-adjudication reaches, once its external cleanup is reconciled, under whichever of the two labels
it had reached; they are also the only way a pre-PR state reaches a terminal at all. `done → rejected` is the last of
the fourteen and the only edge out of a terminal this orchestrator declares, and it is there for an owner a human
moved onto the terminal over a cycle that still has an ending to reach. The umbrella's own terminal needs none of it:
the write that records the resolution **retires the cycle with it**, one write before the label, so a close arriving
past that write finds nothing left to cancel and no `done` issue is ever left carrying a late cycle. A close observed
*inside* that write is answered behind it — the generation is still in the pass's own memory, so it goes back
cancelled and the owner keeps `workflow:umbrella`, where the closed-owner sweep reaches the ending. Nothing else may
leave a terminal — the edge set is asserted whole, so the exception cannot grow a second. A restart after such a
cancellation needs no edge of its own: the operator authorizes it by *removing* `rejected`, so the label a restart
applies is written from the unlabeled entry and `rejected` keeps its empty edge set — a rejected issue left labeled
stays inert. The pinned state those transitions move an issue through is [below](#late-generation-state).

- _(none)_ — Open issue not yet picked up by the orchestrator.
- `workflow:decomposing` — The decomposer is deciding whether the issue is single-context or should become child
  issues.
- `workflow:ready` — The issue is decomposed and has no unresolved blockers.
- `workflow:blocked` — The issue is waiting on child issues or dependency edges.
- `workflow:umbrella` — Parent issue with no implementation of its own; closes to `done` when all children resolve.
- `workflow:implementing` — The dev agent is producing commits in a per-issue worktree. A clean result advances to
  `workflow:validating`.
- `workflow:documenting` — The single docs pass on the existing PR worktree, reached only via the final-docs handoff
  in `_handle_validating`'s approval branch (after verify + squash). Advances to `in_review` after a pushed docs
  commit OR an explicit `DOCS: NO_CHANGE` verdict.
- `workflow:validating` — The reviewer agent is checking the diff; on `VERDICT: APPROVED` the local verify gate runs
  `VERIFY_COMMANDS` before the squash + `workflow:documenting` handoff. `CHANGES_REQUESTED` relabels to
  `workflow:fixing` before the dev spawn.
- `in_review` — A PR is open and ready for human review. The orchestrator never merges from here — humans drive the
  merge. A mergeable PR whose current head completed the reviewer-approved final-docs handoff (or carries a real GitHub
  APPROVED review), with no standing human CHANGES_REQUESTED on that head, earns a one-shot HITL ping per head SHA.
- `workflow:fixing` — The dev fix-loop is active. Entered on unread in-review feedback OR a `CHANGES_REQUESTED`
  verdict. A successful fix bounces directly back to `workflow:validating` so the reviewer re-approves.
- `workflow:resolving_conflict` — The orchestrator is resolving a rebase conflict on a PR branch against
  `<remote>/<base>`. Reached only when the per-tick base-sync rebase actually leaves conflicted files, or via an
  operator relabel.
- `question` — Operator-applied read-only Q&A label: the decomposer agent answers in the per-issue worktree and waits
  on a human reply or close. No PR is opened.
- `discussion` — Operator-applied architecture discussion: the decomposer agent researches the repository, explores the
  design as a tree, and comes back with a numbered frontier of currently-answerable questions plus its own recommended
  answers, then parks awaiting human. Answering by number resumes the same session, which recomputes the frontier
  around what those answers settled and parks again, for as many rounds as the humans reply. Once a human confirms the
  shared understanding, the same session commits `plans/issue-<number>.md` and the stage publishes that one file as a
  plan PR, keeping the label and opening no further round while the humans read it. Nothing is implemented here and
  nothing routes an issue in. What takes it out is the humans deciding, in one of three places. Their verdict on that
  plan PR is drained by the stage itself: merged is `done`, closed unmerged is `rejected`, and either finalizes the
  issue and reaps the worktree and the branches. Closing the ISSUE before a plan PR exists is `rejected` the same way,
  with no teardown. Otherwise a human relabel takes it out — to `done` or `rejected` by hand, the two edges
  `ALLOWED_TRANSITIONS` grants the state, or through the GitHub UI to `workflow:implementing` to have the plan built,
  which arrives as an operator relabel and is screened by the read-only guard rather than travelling a graph edge.
- `done` — Terminal success; PR merged, umbrella resolved, or a `question` issue closed.
- `rejected` — Terminal rejection; PR or issue closed without merge.

### Legacy labels and the migration off them

A repository whose labels predate the namespace carries the bare spellings on live issues, so moving it over is one
write plus the reads that cover what that write could not reach.

The write is the label bootstrap, which `runtime.startup.connect_clients` runs once per configured repo at process
start — so such a repository is migrated at the next start, not mid-tick. `ensure_workflow_labels` walks both
vocabularies and provisions each label the repository is missing. Only a namespaced label has a pre-namespace
spelling to migrate off, so only those reach all three answers:

- **The namespaced label already exists** → nothing happens, and a bare label still defined on the repository beside
  it stays defined. The bootstrap neither renames nor deletes it: at the repository level a leftover of its own and a
  name the repository picked for itself are the same thing. Issues still carrying that bare label come off it one
  relabel at a time under the rules below, not on a second bootstrap pass.
- **Only the pre-namespace spelling exists** → it is renamed in place rather than duplicated, which carries every
  issue holding it across in a single edit — including the closed ones and the `backlog` / `paused` parked ones no
  label write of the orchestrator's would otherwise reach.
- **Neither exists** → the namespaced label is created fresh.

The seven labels that were never namespaced — `in_review`, `question`, `discussion`, `done`, `rejected`, and the
`backlog` / `paused` controls — have no second spelling to migrate off, so the bootstrap only ever skips one that
already exists or creates it bare. Which vocabulary a spec came from decides nothing here: the rename is driven by the
label's own spelling, which is why it covers `workflow:community_contribution` alongside the states.

A PAT without `Issues: Read and write` can neither rename nor create: the refusal is logged and the rest of the
bootstrap is abandoned, leaving that repository on its old vocabulary until the permission is granted and the process
restarts. That, the skip case above, and a human re-adding a retired label by hand are what the reads below exist
for.

Three reads take either spelling, so none of them depends on the rename having run:

- **Routing.** `github.labels.workflow_label` reads an issue's labels through `issue_workflow_label`, which resolves a
  bare tag back to its `WorkflowLabel`, so an issue still carrying the old label reaches its handler and the next
  label write rewrites it to the namespaced spelling. (`label_for_name` is the same lookup on the write side, where
  `coerce_workflow_label` accepts either spelling for a label about to be applied.)
- **The community sweep.** It asks for both spellings of `workflow:community_contribution` and rewrites neither: the
  label it finds is proof the PR's one HITL ping already went out, and re-labeling would repeat it.
- **The closed-issue sweep.** Each sweep label is queried under its pre-namespace spelling too, because a closed issue
  is the one case no other pass revisits — see [Pollable issues and finalization](#pollable-issues-and-finalization)
  for the request cost that carries.

An issue can therefore carry both spellings at once, and the namespaced one always wins — `issue_workflow_label`
scans for it across every label before it will settle for a bare tag, so the order GitHub happens to return them in
cannot change the answer. The write side mirrors that read. `replaced_label_names` takes off the namespaced labels
always; a bare tag joins them only when it names a state coming off anyway — because the namespaced spelling of that
same state sits beside it, or because the issue has no namespaced label at all and the bare one *is* its
pre-migration state. So a bare `blocked` or `ready` the repository uses for its own triage, on an issue whose state
is already namespaced, is read past and left in place: that protection is the point of the namespace, and it would be
worth nothing if a relabel deleted the label anyway. The one case the two spellings cannot be told apart is a bare tag
on an issue with no namespaced label — there it is taken as the pre-migration state, which is what lets the issue
keep routing.

<a id="per-tick-flow-workflowtick"></a>

## Per-tick flow (`workflow.engine.tick.tick`)

Each tick fans out across every configured repo (`config.default_repo_specs()` returns one `RepoSpec` per `REPOS` line)
and dispatches per-issue handlers through a long-lived `IssueScheduler` capped by `MAX_PARALLEL_ISSUES_GLOBAL` /
`MAX_PARALLEL_ISSUES_PER_REPO`. One repo's pass is entered through `workflow.engine.tick.tick`;
the multi-repo dispatch, the scheduler lifecycle, and the fixed order that pass runs its four steps
in are in
the [architecture's per-tick flow](../architecture.md#per-tick-flow-workflowengineticktick). What follows is what
each step reads and writes per issue.

The dispatch loop classifies each pollable issue by workflow label before submitting it:

- **Family-aware labels** (`workflow:decomposing`, `workflow:blocked`, `workflow:umbrella`, unlabeled pickup) read and
  write cross-issue state (parent ↔ child). They are folded into one bucket per repo that drains sequentially on a
  single worker thread, so parent / child handlers in one process cannot race; another poller on the host is kept off
  them only by the writer claims below, which is why a parent's write to a child reads the child again under the
  child's claim rather than trusting its scan. A bucket whose every label is in
  `_CAP_EXEMPT_FAMILY_LABELS` (`workflow:blocked` or `workflow:umbrella` — pure label / dep-graph walks) runs on a
  dedicated executor and does not consume a `MAX_PARALLEL_ISSUES_*` slot, so a blocked parent waiting on children
  cannot deadlock those children. A **closed** issue on a cleanup-swept label is not in this bucket at all: its
  handler is the cleanup sweep rather than the stage its label names, so it fans out with its own exemption. An
  **open** `workflow:blocked` / `workflow:umbrella` issue is left out before the split on the ticks
  `DEPENDENCY_POLL_EVERY_N_TICKS` skips — default `5`, counted on the same polls as
  `CLOSED_ISSUE_SWEEP_EVERY_N_TICKS`, so the first poll is due and every fifth after it. That saves the child reads
  its dependency walk spends, and costs up to N ticks before a child is activated, a parent completes, or drift on
  either is detected; `1` keeps the walk every tick. The rest of the bucket still drains in order on a skipped tick,
  and a close this process already observed still routes such an issue to its cleanup.
- **Fan-out labels** (`workflow:ready`, `workflow:implementing`, `workflow:documenting`, `workflow:validating`,
  `in_review`, `workflow:fixing`, `workflow:resolving_conflict`, and the operator-applied `question` and
  `discussion`) only touch their own state and worktree. They run concurrently up to the per-repo and global caps. A
  **closed** fan-out issue (a merged-PR, closed-`question`, or closed-`discussion` issue still carrying its sweep
  label, surfaced by the closed-issue sweep) is submitted `cap_exempt=True`: its handler only runs a terminal
  finalization (flip to `done` / `rejected` + branch cleanup) — or, on a closed `discussion` whose plan PR is still
  open, one PR poll and nothing at all, since that issue is held for the humans' verdict rather than finalized — with
  no agent spawn, so it must not be starved behind active agent work — otherwise under `parallel_limit=1` a merged-PR
  issue sits closed-but-labeled for many ticks while a sibling reviewer or docs agent holds the only slot.

The duplicate-active gate keys on `(repo_slug, issue_number)`: an in-flight handler that straddles polling passes is
reported active to the next poll's submit, which is rejected as `duplicate_active`. The pre-tick base-refresh skips any
active issue's worktree.

That gate answers for this process alone, so every dispatch path also takes the issue's host-local **writer claim**
(`scheduler/writer_claims.py`) — an exclusive, non-blocking `flock` keyed by the repository's numeric GitHub id (the
client's `repo_id`, never a name, so a rename leaves the key alone) and the issue number — before anything it does for
the issue: the refetch, the pinned-state guards, the close recovery wrapped around the pass (the closed reading an
ordinary pass keeps, the close a refetch establishes, the cleanup observation a sweep is held under), and the handler.
The sequential loop takes it once an issue survives the hard-skip classification, which a closed or latched reading
always does, as it does the partition's; the scheduler's fan-out task, its family-bucket iteration (inside
`track_active`), and the in-tick pool's tasks take it as their worker starts, so a queued submit holds no claim. Every
one of them then reads the issue again under it, the sequential loop included: the poll is older than the claim, and a
poller that advanced the issue and let go in between would otherwise have its stage resumed from the label the poll
read. The handler is the one the fresh label names; what the poll read is carried over that read only where it is a
close, and binds there: a pass reading the issue open again applies the close to any late cycle and runs no stage, nor
does one reading a stage outside its admitted lane (family work on a fan-out pass, anything but a dependency walk in a
capacity-exempt bucket); the next poll admits either afresh, under the caps and the family bucket. The enumeration takes
it too, for the one thing it writes: the pinned read and close receipt behind a closed fan-out issue, and the same pair
a refused cleanup submit spends on a reading still held. Those two ask for it *alongside* — granted beside a worker of
this same process that holds the issue, since the receipt is an added comment built to land beside one, and an
ordinary exclusive attempt against every other process.

An issue another poller on the host holds is skipped whole on every path: nothing is refetched, published, relabelled,
written, run, or accounted for, and the submit's publication hold and any latched close are left as they were. A close
the poll read for it is the one thing kept, in this process's latch alone — no receipt is posted — so a human reopening
the issue before the claim comes back cannot take the reading away. The poll's reading is older than any read after it,
and the holder may settle the cycle that close ended and start the fresh one an operator authorized in between, so the
contender reads the record first, the issue behind it, and the record again behind the issue: only a close still
standing there, with both record reads naming the same late cycle, is scoped to that cycle. A record that moved between
them — the holder restarting the cycle in that window, and the close perhaps the fresh cycle's — is read again behind
another issue read, a few times at most, and the close is scoped to the cycle the record settles on. A record a
retirement has just emptied names none, and there the close is scoped to the cycle the holder noted on the claim it is
retiring (`scheduler/claim_notes.py`), which a poller inside a retirement window notes for the rest of its hold, read as
the claim is refused and again behind the reads; the record's own correlation is not enough, since it outlives every
retirement. A close the record says ends nothing — no cycle, or one already marked — adds nothing, and leaves an older
latch as it was. One reopened between the reads, whose reads failed, whose record never held still across them, or whose
record named a cycle and then none is kept *unresolved*. The next tick routes the latch to a cleanup pass under the
claim. A scoped close marks the cancellation if its cycle is still the record's — and puts a retired one back and
cancels it — and is settled with nothing marked if the holder has since started a fresh cycle, unless the issue is read
closed again after the holder let go, which is a close of the fresh cycle; an unresolved one marks only a cycle the
issue reads closed over under the claim, and is settled with nothing marked on an issue open again.

The same proof binds a close this process's own poll read. Every acquisition signs the claim file with a per-process
token, every hold stamps the moment it let go on the host's monotonic clock, and an acquisition that finds another
process's token notes when that hold ended — when it is found, for a hold killed before it could say, and for the empty
file an issue's first claim on the host finds, which cannot say who held it last. A poll reads that clock before it
lists anything; a closed reading carries the moment, and a latch keeps the moment of the latest closed reading merged
into it, so the pass under the claim asks whether every hold of another poller found on the key had ended before it. If
so, no other poller has written the record since the close was read, and a close nothing else ties to the record's cycle
— none, or a scope the record has moved off — ends that cycle and is scoped to it. A lone poller is in that case,
restarted or not — its predecessor's stamped hold ended before its poll began — except on an issue its predecessor was
killed holding, or one no poller on the host has claimed before, until a claim finds that file. Otherwise the worker's
guard marks nothing on a reopened issue and stops the tick, and the cleanup pass the latch routes it to next settles the
reading. A claim that cannot be worked withholds the issue the same way rather than dispatching it uncoordinated. The
scheduler's own gates still run first and are unchanged: duplicate-active, the caps, the family slot, and the
refused-submit observation hold. An ordinary pass that finds a close latched once it holds the claim — a family drain or
fan-out queued before a poll took it — runs as that close's cleanup rather than as the handler its label names, which is
the route the partition gives an issue it finds owed. And every barrier that marks a cancellation inside a pass, the
retirement window included, ends a cycle only with a close that ends that cycle, by the same scope and the same claim
notes: a close held for a cycle another poller settled and restarted from ends none, and no receipt is posted or
remembered for it, so the next poll that reads the issue closed ties that fresh close to the fresh cycle and posts for
it. Every receipt confirms the close with an issue read behind the record, since a reader alongside this process's
own writer can see that writer restart the cycle between its reads. A restart this process writes holds every older
close off the fresh cycle for the same reason, from before its write lands, since no claim note records it, and a
settlement a publication hold postponed keeps its close's scope but drops its moment; a poll retrying an owed close
withdraws nothing.

A family-aware handler writes issues other than its own, so those writes take the target's claim as well, and decide on
what they read behind it. The walk that relabels a `workflow:blocked` child `workflow:ready` claims every child it would
release, then reads each again — its scan was taken before any claim, and another poller may have relabelled, finished,
or closed one in between — and releases none if one is held, cannot be read, or no longer reads open and
`workflow:blocked`, parking nothing; the next walk scans again. Recovery's orphan repair stops short of a held child
without parking; a merged child's finalize reads each claimed child again and counts it by that reading, so one another
poller finalized, relabelled, or reopened since the scan is never finalized twice, and leaves a held child as scanned,
counted neither done nor closed by hand; and the snapshot-reclaimed notice leaves a held consumer's obligation owed. An
ordinary split's seed is read and added to under the child's claim, never written as a fresh record: a poller that
reached the child first may have held it for the seed it lacks, parked on the one pinned comment every reader takes, and
the seed lifts that park in the same write. A child that poller still holds is left unseeded while the split creates the
rest, and the split stops short of its summary and finalize, leaving the parent `workflow:decomposing` with every child
recorded — exactly what the [half-finished recovery](delivery-stages.md#_handle_decomposing-label-workflowdecomposing)
seeds under the claim and finalizes on a later tick, with no human. Only a seed write that fails parks
(`child_seed_failed`), and only a late split's placement parks on a held child, as its failed seed does
(`late_children_failed`), for the next attempt to supersede. The pre-tick base refresh takes the same claim for each
worktree it syncs, after skipping the issues its own process's scheduler reports active, so another poller's refresh
or dispatch holding the issue keeps it out of this one's refresh as well ([Base refresh](#base-refresh)). The
supported topology and the namespace's access assumptions are in
[`../configuration/operations.md#running-more-than-one-poller`](../configuration/operations.md#running-more-than-one-poller).

Only issue numbers cross the thread boundary — each scheduler worker mints a fresh `GitHubClient` via
`gh._for_worker_thread()` and re-fetches its Issue against that client. The mint itself sends no request: the clone
reuses the parent's token and bot login on a requester of its own, and its repository is lazy. The first read of
repository metadata — the canonical `repo_slug` an ownership check or refusal quotes, or the owner login a branch's
pull-request lookup filters on — fetches `GET /repos/{slug}` once, and a handler that reads none never fetches it.
Issue, pull-request, label, and commit operations address the repository by URL and still ask GitHub at the call, as
they do on the eagerly built parent client that enumerates the tick.

### Base refresh

Before any issue is dispatched the tick runs `_refresh_base_and_worktrees(gh, spec)` on the workflow's refresh owner
(`workflow/engine/base_refresh.py`): a single
`git fetch <spec.remote_name> <spec.base_branch>` in `spec.target_root`, then per-issue dispatch on each existing
worktree under `<WORKTREES_DIR>/<owner>__<name>/issue-*`. The remote name defaults to `origin` and is overridable per
`REPOS` row. Per-stage `_ensure_*_worktree` helpers only fetch on (re)creation, so without this refresh long-lived
worktrees would stay anchored to whatever `<remote>/<base>` looked like when first added.

Each worktree is synced as its issue's one writer on the host. An issue its own process's scheduler reports active is
skipped first; every other one is synced under the issue's writer claim (see
[Per-tick flow](#per-tick-flow-workflowengineticktick)) — the claim every dispatch path takes, on the same key (the
repository's numeric id and the issue number) in the same namespace — taken without waiting before the issue or its
pinned comment is read, and held until the route below has ended, whichever it is: the pre-PR rebase, the PR rebase
with its push, notice, report debt, and relabel, the reset and park over a checkout whose lag cannot be read, and an
interrupted attempt's recovery and settlement. A refresh refused the claim — another poller dispatching the issue or
refreshing it, a writer of this process's own, or a namespace nothing can be locked in — skips that issue alone with
nothing read, rebased, pushed, published, labeled, written, or recorded, and the next tick's refresh asks again, while
every other worktree is synced. Nothing under the claim asks for it a second time: the one road the dispatcher reaches
too, the answer a standing anchor is owed, runs there under the dispatch claim the worker already holds.

Two paths depending on whether a PR exists:

- **Pre-PR worktrees** get a clean-tree `git rebase <remote>/<base>` directly, on the git `base_sync/pre_pr.py`
  route — no remote to push, so the local branch stays linear without publishing a rewrite.
- **PR-having worktrees** in `workflow:validating` / `workflow:documenting` / `in_review` / `workflow:fixing` go
  through `_sync_pr_worktree_to_base`, the workflow's base-rewrite coordinator (`workflow/engine/base_rewrite.py`),
  which orders the git `base_sync` gates and rebase and hands a pinned anchor to the workflow's recovery coordinator
  (`workflow/engine/rewrite_recovery.py`) — reached even when the checkout is no longer behind base, so a pinned
  anchor's recovery is still answered. The recovery asks its readings, refusals, and parks of the git owners in the
  order they have always been asked; a replay its crash kept off the pull request is retried by the workflow
  (`workflow/engine/rewrite_retry.py`) exactly as the publication below publishes a clean rebase -- the candidate
  reading, the gate, the exact-candidate push under the anchor's lease, and the finish -- with the transfer permit
  asked first where a transfer is the only voucher, and a push the recovery finds already landed is the workflow's
  too (`workflow/engine/rewrite_landed.py`): observed rather than pushed again, or, for a permission still
  outstanding, proved by the permit-only leased no-op that settles it, and handed to the same finish. A clean
  rebase is the workflow's own publication (`workflow/engine/rewrite_publication.py`): the git owner reads the
  candidate the rebase left (`git/base_sync/rewrite_facts.py`), the size gate and the transfer permit rule on it, and
  the git owner pushes exactly that candidate (`git/base_sync/rewrite_transport.py`, force-with-lease pinned to the
  pre-rebase SHA so a foreign update rejects rather than being clobbered). A landed push is finished by
  `workflow/engine/rewrite_finish.py`: it resets `review_round`, posts a PR notice, records the report the landed head
  is owed, makes the evidence that head is routed with durable, and relabels to `workflow:validating` so the reviewer
  re-runs against the rewritten head. Only when the
  rebase actually leaves conflicted files does the helper relabel to `workflow:resolving_conflict`.

The `question` and `discussion` labels skip both paths unconditionally (`_issue_skips_base_sync`) — the question
handler tears down its own worktree, the discussion stage keeps its checkout across every round exit, and merging
base into either would accrete commits on a branch no developer owns or rewrite the state an unsafe park left for an
operator to read. On the discussion side it is also what protects the publication: the plan is pushed at the SHA the
stage's own check read, so a rebase between that reading and the push — or after it, onto the tip the plan PR is open
against — would move the branch off the commit anything vouches for.

The skip outlives the label. An unconsumed `question_*` / `discussion_*` park is honored whatever the issue is
labeled now, because an operator's relabel to `workflow:implementing` takes the label off a full tick before the
read-only guard rules on the branch, and a rebase in that gap would move the tip off the SHA the guard measures and
convict a branch nobody touched. So are the five records that freeze a branch on their own
([`git/base_sync/frozen.py`](../../orchestrator/git/base_sync/frozen.py)): the two a discussion tick writes BEFORE the
thing they describe (`discussion_round_open` and `discussion_publishing_sha`, which a tick that died mid-round leaves
standing with no park at all, and with the commit it died holding on the branch), the `read_only_baseline_sha` the
guard writes in place of a park it clears, which stands until the dev run commits, and the two commits the late size
gate is deciding about — `late_candidate_sha`, the pair it froze, and `late_approved_sha`, the commit an approval has
still to publish, each dropped by the step that spends it. The `late_collapse_*` group joins them on stricter terms:
a squash mid-rewrite is proved by the TREE the commit on the branch carries, which a rebase replaces with one
carrying the base advance too, so any member of the group being on the comment at all — `null` included, since that
is what the squash's own reader refuses to resume — holds the branch until whatever finishes or undoes the collapse
drops it. So does a developer report recorded and not yet settled — `developer_report_delivery` or
`developer_report_pending` holding anything but `null`, a record nobody can read included. A delivery names no commit
and is bound to whichever one the code-publication receipt names when the binding runs, and a transaction names the
head it was written about, so a rebase in that window would bind a report to a head no developer read or leave one
about a head the pull request has left, which the report hold can only park on. The binding and the settlement write
each `null`, so the first refresh behind the settlement rebases as it always would, and a rewritten-head report debt
it leaves is refreshed afresh. Two PARKS freeze the branch as well, and by the park
rather than by a record, because neither can leave one. A standing `late_measurement_failed` is the first: the
sharpest of those refusals is taken before any commit could be named, so there is nothing on the pinned comment to
freeze by — and rebased under it, the exact-pair retry has lost its commit and the refusal that substitutes nothing
for a pair nobody froze is standing on the base. A standing `agent_timeout` is the second, and its watermark names a
commit that does not exist yet: `pre_implement_sha` is the tip the killed run STARTED at, so every reading of it is a
comparison against what the checkout has become since. On the commonest shape of that park — a run killed before its
first commit — the branch carries nothing of its own, so a base that advances fast-forwards the checkout straight
onto the new tip, and the next tick's silent recovery reads a head that moved with no developer having written a
line. Both parks end the way every park does, by being answered — with one exception on the size gate's side: a
`late_measurement_failed` standing over a split that has already become children is retired by the reconciliation
itself, since nothing about that record is a human's to answer, and the branch it was freezing goes back into base
sync with it.

One approval is the exception, and it is this refresh's own work rather than a stage's. An auto rebase pins its
recovery anchor before git runs and enters the size gate on that same head, and the gate records the rebased commit
as one still owed a push before the push goes out — so a process that dies in between leaves the anchor and the
approval together. Read as a freeze, the approval takes the branch out of the very recovery the anchor exists for:
the reconciliation ahead of the next handler would land the push while nothing ever cleared the anchor, reset
`review_round`, or routed the reviewer at the rewritten head. So an approval whose `late_approved_lease` IS the
pinned `pending_auto_base_rebase_push_sha` does not freeze the branch, and the refresh finishes the route it
started. Nothing else writes either field while an anchor is outstanding, and a group too damaged to show its lease
fails the test and keeps the freeze. The reading group is never set aside: a generation the gate froze and did not
answer is a question no push settles.

Beside a pinned anchor the rest of those freezes are set aside as well, and only the late claims — the reading
group, and an approval not leased to the anchor — keep the refresh away. The anchor is this refresh's own interrupted
work, and while it stands the dispatcher holds every stage handler back (`recovery_holds._recovery_holds_dispatch`,
see [Pinned state](#pinned-state)): a `question_*` / `discussion_*` park, the two discussion records,
`read_only_baseline_sha`, the `late_collapse_*` group, a developer report recorded and not yet settled,
`late_measurement_failed`, and `agent_timeout` are each ended by a handler, or the report reconciliation, that hold
keeps back, so a freeze on any of them as well would leave neither side able to move. None of
them is holding a branch still against a rebase any more — the anchor says one already ran — so the recovery reaches
the checkout, pushes the replay its record names or puts the branch back on the anchor and asks a human, and leaves
each record for its owner. The `question` and `discussion` labels themselves are still skipped, and an anchor under
either is answered by the dispatcher on the recovery's ineligible road. The one late claim beside an anchor that no
reconciliation ends is a generation measured past its ceiling over the anchor's own replay, which the refresh stays
away from and the hold would keep its adjudication off: the dispatcher hands that replay to the generation ahead of the
hold instead (below), so the two never stand against each other and the adjudication is always the road left.

`late_exempt_sha` and `implementing_published_sha` freeze the branch too, but on conditions rather than on their
presence: neither is ended by a write — the exemption is never cleared at all and the publication record is
overwritten rather than spent — so read by presence they would take a branch out of the refresh for the rest of its
issue's life. The refresh asks two things instead. The checkout: the head still IS the commit the record names, or
there is nothing there left to protect. And the label: the stage that has to act on that commit — `implementing` for
both, plus `decomposing` for an exemption a relabel has not carried out of it yet — still has the issue. Past the
handoff neither holds anything, and that is the point: a pushed branch is kept in step with base by the PR-aware
sync, which is the only route that can move it without stranding the SHA a reviewer is looking at. That rebase is a
REWRITE of whatever the branch was standing on, so where it was standing on an exempt commit the refresh hands the
size gate the same evidence a squash does — the pair the adjudication recorded, the pair the replay produced, and
the pull request and pre-rebase anchor the push is made against — and the transfer above may carry the verdict onto
the replay. A base advance that CHANGED what the branch adds to it fingerprints differently, so the permit refuses
and the ordinary cumulative gate measures the replay exactly as it always did.

Refresh-only failure modes — push rejected or refused (`auto_base_rebase_push_failed`), rebase failed without
conflicted files (`auto_base_rebase_failed`), dirty-after-clean-rebase (`auto_base_rebase_dirty`) — reset HEAD back to
the pre-rebase SHA and park awaiting human with a durable `park_reason`. A push is refused, with nothing sent, where the
checkout, the base ref, or the remote branch moved since the candidate was read, or the remote could not be read; a
remote already standing on the candidate excuses none of those refusals, and is proved there by a push leased to the
candidate itself before anything is finished -- announced as found standing even where that proof's answer was lost --
and refused like any other move where somebody pushed over it. A push whose answer was lost is classified by reading the
remote again, and one the remote is shown standing on is finished rather than rolled back. A pull request merged or
closed, or a close a poll latched, while the remote is read holds the tick whatever that reading found: nothing is
pushed, reset, parked, or announced. A landed push whose report debt the pinned comment has no
room for (`auto_base_rebase_unrecorded_debt`, below) parks the same way with nothing reset, since the pull request
already carries the head. Recovery is refresh-only and gated on a fresh human
issue-thread comment past `last_action_comment_id`; the actual `awaiting_human` / `park_reason` clear is deferred to the
same pinned-state write that publishes real progress, so an early-return path cannot silently drop the retry intent.
Every PR-stage handler short-circuits at its `awaiting_human` gate when `park_reason in _AUTO_REBASE_PARK_REASONS` so
the refresh owns the operator's retry comment. A park some STAGE left is kept intact rather than rebased past, but an
anchor standing under one is answered all the same: the recovery runs alone, with no reply spent and no rebase of its
own behind it, and a finish leaves the stage's park where it was -- as does a gate that routes the replay to an
adjudication instead (see the handoff below). Under every park, the refresh's own included, the
pull request is asked for first, and one that merged or closed ends the attempt's whole handoff rather than leaving
its anchor to hold back the handler that finalizes the issue.

A clean rebase whose push LANDS leaves the pull request on a head no developer report is about, and the reviewer
road refuses the report of the head before it. So the finish stages the report debt that head leaves
(`developer_report_rewrite_debt`, see [Pinned state](#pinned-state)) through
`workflow/engine/rewrite_finish_debt.py`, whichever road reached the finish -- the pinned pull request, its branch,
the anchor the push was leased against, and the head
that landed -- and the debt
rides the write that records the announcement mark, ahead of the write that clears the attempt and ahead of the
relabel, so the validating report refresh asks the developer for that head's report with no human reply. The
recovery records the same debt on every road that finishes a landed head: the push it reissues, the landed push it
only announces and routes, and the leased no-op that receipts a transfer. The route an announced finish still owes
stages it again: over a mark this build wrote that replays the debt beside it and writes nothing, and over a mark an
earlier build left alone it is a new claim, written at once while the anchor stands and before that route's relabel.
A process lost before the mark comes back to the attempt record itself: its anchor and its replay are the debt's two
heads, and the anchor holds every stage handler back until a finish has written both. A base that moves
again before that report is asked for retargets the claim onto the head the next rebase lands, keeping the head the
settled report is about, so repeated advances leave one debt naming the latest proved head -- and where the recovery
finds the base behind again, it records the landed head's debt before the same tick rebases it. A rebase that moved
nothing, a refused push, the reset a park makes, and a pull request somebody else moved never reach a finish, so they
record nothing and leave a standing claim exactly as it is. A standing claim the landed head does not follow --
another pull request or branch, a head somebody else pushed in between, a claim nobody can read -- is refused and
left standing, and the route goes on to the reviewer road, which refuses the stale report it finds as it would with
no claim.

The room the debt needs is measured on the whole write it rides -- the announcement, which also puts down the notice's
ledger entry (reserved at the widest id a comment is recorded at), the `review_round` both finishes reset ahead of the
mark, and the mark -- rather than on the debt alone, and on the comment as it stands as well, since resetting a wide
round can make the announcement the narrower of the two; the writes past it only clear. A proved debt that does not fit
stops the finish before it announces anything: no notice, no `base_rebased`, no relabel, and no clear. It parks
`auto_base_rebase_unrecorded_debt` with the push kept, the anchor and the replay standing, and the anchor holding every
stage handler back; the park asks for room to be made on the pinned comment and a reply, and the reply brings the
recovery back to finish the landed head -- recording the debt first, or parking again if there is still no room. A
standing claim the rewrite cannot be carried onto is no such debt, and `workflow/engine/report_rewrite_room.py` is what
tells the two refusals apart, for the conflict stage as well.

A clean rebase whose candidate the size gate hands to an adjudication instead of pushing leaves two owners over one
unpublished replay: the attempt's anchor, and the live late generation whose candidate that replay is. Left that way
each would hold the other for good -- the generation freezes the refresh that would end the attempt, and the anchor
holds the adjudication's handler -- so `workflow/engine/rewrite_takeover.py` hands the replay over. The ordinary
publication and the recovery's retry ask it of every answer the gate holds (`rewrite_publication.py`,
`rewrite_retry.py`); its proof is what tells the hold that routed the replay from the parks the gate takes instead --
a reading nobody could take, a refused entry, a moved publication -- none of which leaves a live measured adjudication
of this replay, so each keeps the attempt pinned for the recovery its reply brings back. The dispatcher asks it again
ahead of the anchor hold whenever an anchor stands beside a live adjudication (`dispatch_guards._anchor_holds_the_tick`,
see [Pinned state](#pinned-state)), which covers every write of the handoff a crash can interrupt -- the replay recorded
and unmeasured is the retry's, the generation persisted with its relabel lost is put back on `workflow:decomposing` by
the adjudication's own guard first, and the generation relabelled with the handoff lost is handed over there -- and a
pair an earlier build already stranded under its `auto_base_rebase_failed` park.
It proves off the pinned record alone, never off the checkout, that the attempt reads back whole with no announcement
mark, that the generation is one late adjudication would itself act on for this issue -- it passes the late domain's
record gate, freezes both its candidate and its base, and names this issue as `late_current_issue` -- and is live,
measured past its ceiling, with a whole publication group, and that the two name the same candidate, pull request,
anchor (the generation's `late_published_sha`), and stage. One guarded write, decided on both records and the park's
flags as they were read, then records the takeover (`late_auto_rebase_replay_sha`, see
[Late generation state](#late-generation-state)) and retires the whole attempt through the same clear every ending
uses, so the attempt is never gone without the generation carrying the replay. A park the attempt's own road left --
any of the `auto_base_rebase_*` reasons, the stranded park among them -- goes in that write, since nothing is left to
come back for the reply it asks for and the stage the replay is handed back to stands down on those reasons; every other
park, the round, the frozen pair, the measurement, the publication group, and every other field stay as the comment
spells them, and a repeated handoff finds the attempt gone and writes nothing.

Every `auto_base_rebase_*` notice asks for a reply, and the base sync reads one for its arrival alone: any trusted
comment past the notice lets the attempt go again. What the reply says is the adjudication's question once the replay
is handed to one, since it reads a trusted comment it has not counted as guidance, and guidance resumes the developer
over a candidate nobody adjudicated (`workflow/engine/rewrite_replies.py`). A reply that asks for the retry and nothing
else -- a bare `/orchestrator continue`, or a bare "retry", "try again", or "please retry" -- is the attempt's: it is
recorded read where the adjudication reads from, `last_action_comment_id` past it and `user_content_hash` over the
thread through it, which is what a generation's first late baseline counts comments up to. A reply that says anything
more is a human's words, a requirement or a decision, and stays unread for the adjudication to hand the developer. Only
the leading run of retries is spent, since the baseline covers a prefix of the thread and the first reply of guidance
is where it stops; and the baseline moves only where it already reproduces over the thread up to the watermark the
replies were written past -- short of that, words nobody read stand before the park's notice, and folding the retry in
would fold those in too. It reproduces in either spelling the drift check accepts: a baseline the legacy algorithm
wrote, counting a bare `/orchestrator continue`, covers the thread as the current one does, and what is written past
it is the current spelling, as that check normalizes a legacy baseline it recognizes.

Each retry is recorded in the write that already spends its reply, so no lost tick can split the two: the anchor's
write on a rebase the reply let start, which moves the watermark past every reply it read
(`workflow/engine/base_rewrite.py`); the gate's write on the recovery's retry, which takes the reply's park down
(`workflow/engine/rewrite_retry.py`); and the handoff's write over a park the attempt's own road left, which retires
the park with what answered it (`workflow/engine/rewrite_takeover_parks.py`). The park's notice outlives it, though:
it still stands on the thread asking for a reply once the handoff has landed, and a tick lost before the adjudication
first reads the thread leaves the human to answer it with no park left to say whose the answer is. So until that first
reading, with no park standing, the dispatcher's hold over a taken-over replay's adjudication spends a retry past the
watermark the same way, in a guarded write of its own ahead of the adjudication -- the only question a bare retry
could answer there being the attempt's -- and holds the tick only where that write did not land.

Any other park is somebody else's question, which nothing on `workflow:decomposing` answers -- and the adjudication's
verdict would take its flags over with one of its own. So such a park survives every step that brings the replay to an
adjudication: the size gate's route keeps one whose reason is neither the attempt's, the late domain's (`late_*`), nor
the spent spawn budget's (`retry_cap`) wherever an auto-rebase anchor is pinned -- the recovery a stage's park let
through with no reply spent (`stages/implementing/late_park_retirement.py`) -- the handoff leaves it, and the
dispatcher holds the taken-over replay's adjudication behind it, writing nothing, until a human replies past the park's
notice. The adjudication then reads that reply as it reads any reply on a park it does not own: guidance answers the
park and resumes the developer, and a bare `/orchestrator continue` lets the adjudication run. A write sent and never
confirmed answers UNCONFIRMED, since only the comment read again says whether it landed, and the dispatcher holds that
tick for the next to prove again. Evidence short of that is answered INCOMPLETE and evidence of other work UNRELATED,
and both leave the attempt standing; beside a live adjudication the dispatcher then takes the stranded park, which asks
for the `pending_auto_base_rebase_*` record to be reconciled by hand rather than for the label back, since the
adjudication's guard restores its label. Ownership licenses no push: the replay is published only by the settlement of
an authorized `single`, leased to the head the generation froze, which records the report debt that push leaves and
puts the reviewer's spent rounds back before it routes the head to `workflow:validating` -- where the rewrite finish
sends every rebase it publishes, whatever stage the rebase was made under, since the merge roads hold their handlers
while that report is owed and only validating pays it and reviews the head. A pull request somebody pushed to
meanwhile refuses that publication and parks, with nothing pushed and no debt recorded.

The retry is where a changed contribution meets a refused permit after a crash. A replay the attempt's own record names,
with no grant made before the crash, is vouched for by that record, so a permit that refuses the evidence re-derived for
it is a contribution the base advance changed -- and it is measured, with that evidence, as the publication the dead
tick was making would have measured it: past the ceiling it goes to a fresh adjudication with the replay standing, and
under it publishes on the count with the verdict left on the commit a human ruled on. A standing permission and a
replay the record does not name yet have only the permit behind them, so a refusal there still resets and parks.

Every finish is the workflow's (`workflow/engine/rewrite_finish.py`): of a head the refresh published itself, of one
the recovery's retry pushed again, and of one the recovery found already standing
(`workflow/engine/rewrite_landed.py`), so the three share one post-push policy and one evidence decision. The finish
is handed the typed landing (`git/base_sync/rewrite_handoffs.py`) beside the issue it finishes and applies the policy
above to the ordinary
publication, a recovered push, a landing a recovery found standing, and a finish whose mark already names the head
alike — the same debt measurement and park, notice texts, `base_rebased` payloads, round reset, retirement, retry
spend, and route by the base lag. Each of its writes is a guarded commit (see [Pinned state](#pinned-state)) decided on
the attempt, the report records and claim, the park's flags, the round, and the publication's pinned fields: the
announcement is prepared over the fresh comment before the notice is posted — its notice's ledger entry reserved over
the ledger that comment carries — the park before its notice, and the retirement before the relabel, so a write
another road's move refuses — or one nobody confirmed — stops the finish with nothing behind it made, and the
next finish picks up from the mark or the anchor it left. A landing the record does not account for — a rewrite that
moved nothing, a publication a guard refused for anything but the remote already standing on it, a replay record
(`pending_auto_base_rebase_rewrite_*`) naming another head, made under other terms, damaged, or never written -- save
the push the recovery's own retry made and saw land over an attempt from before that record existed, which the counts
alone vouched for -- a lag against the base that could not be counted, and a finish already retired included — makes
nothing, leaving the
attempt, the label, and the round as they are. A record whose terms stand with no head yet is the window before the
rebase recorded its replay, left to the recovery's vouching ahead of the hand-over; a publication refused because the
remote already stands on the replay sent nothing, and is announced on either road as a push found standing. A
refusal for room alone over a comment that still reads as the tick read it — a debt park that cannot fit included —
leaves the tick's state to be written, since that comment is only full; every other refusal, and an edit nobody
confirmed, withholds it. It takes no writer claim of its own: the caller's claim, held through the route, covers it.
Between the checkpoint and the route sits the post-push, pre-route step where the evidence a landed head
is routed with is decided (`workflow/engine/rewrite_evidence.py`) and, for a head the base has not advanced past
again, made durable before the relabel (`workflow/engine/rewrite_finish_evidence.py`, the
[base-rewrite evidence](delivery-stages.md#the-verification-evidence-transaction-every-dispatch) bullets): in one
guarded commit decided on the attempt, the debt, and every record the evidence is bound through, current evidence
the rewrite moved past -- its tree, or the context configured as the write is staged, behind any run -- is
invalidated into history, and a fresh run or a proved carry is recorded as
`verification_evidence_pending`, which the dispatcher publishes once the attempt is retired. Nothing is recorded where
the binding to a review of the rewritten head is not there yet, the configuration is empty, the run failed -- its
notice recorded in the same write (`auto_base_rebase_failed_verification`) and put on the pull request once before
the route -- something moved under it, or the comment cannot record it: the fresh reviewer owes the evidence. A
decision nobody could take, an invalidation with no room, a failure notice whose post nobody could confirm, or an
evidence write refused or unconfirmed holds the route with the attempt standing, for the recovery of the push already
landed to finish under its own mark, launching no developer. A tick that died before its evidence write landed --
before the configured commands ran, or behind a run that completed -- captured nothing, and that recovery runs them
again; a failure notice an earlier finish recorded is published once with nothing run again, and a transaction it
recorded is routed exactly as recorded only once its binding proves again, abandoned into history with nothing run
again -- then or by any later finish -- where the heads, the requirements, the report or review subject, or the
configuration moved since, or the base is no longer the tip its replay was recorded as made onto or no tip was
recorded, and abandoned too where the base advanced past the head it is about. Every route then ends in one last word
read behind every request it made -- the remote branch the head landed on, the base, and the requirements over the
network, then the checkout's own head and the configuration -- so a landing or a base that moved holds the route, and
whatever moved abandons a recorded transaction unrun, even one the base later comes back under; only a reading nobody
could take keeps it. The retirement behind the route is decided
on every record the evidence is bound through, so a review moved meanwhile refuses it. The invalidation a moved
context now owes lands before the route either way
([base-rewrite evidence, recovered](delivery-stages.md#the-verification-evidence-transaction-every-dispatch)).

Before rebasing, the flow fetches `gh.get_pr(pr_number)` and skips when `pr_state != "open"`: a just-merged PR advances
`<remote>/<base>`, so the stale worktree is naturally behind base; without this gate the refresh would push and relabel
a PR the next handler would finalize; an attempt still anchored to a PR that merged or closed has its whole handoff
ended there first, through `terminal_handoff`. A `gh.get_pr` failure is treated as "leave alone"; where an anchor is
pinned the dispatcher then holds the stage handler until a later refresh reaches the recovery. A base lag that cannot be
counted ends the sync the same way, except over a pinned anchor, where the checkout is reset and parked instead.

### Pollable issues and finalization

`gh.list_pollable_issues()` yields all open non-PR issues plus closed non-PR issues still labeled with one of the
eight recovery sweep labels — `workflow:implementing`, `workflow:documenting`, `workflow:validating`, `in_review`,
`workflow:fixing`, `workflow:resolving_conflict`, `question`, `discussion` — or one of the four cleanup ones,
`workflow:decomposing`, `workflow:umbrella`, `workflow:ready`, and `workflow:blocked`. Each of the seven that HAS a
pre-namespace spelling is queried under
that too, because a closed issue is the one case no other pass revisits: on a repository whose labels the
bootstrap could not rename (see
[Legacy labels and the migration off them](#legacy-labels-and-the-migration-off-them)), the bare label is
all that is left to find it by. Both queries feed one seen-number set, so an issue carrying both spellings is yielded
once. The closed-issue sweep makes external manual merges and operator closes finalize cleanly:
- Closed `in_review` / `workflow:fixing` / `workflow:resolving_conflict` — a human-merged PR with a `Resolves #N`
  footer auto-closes the issue before the orchestrator can flip the label.
- Closed `workflow:implementing` / `workflow:documenting` / `workflow:validating` — the same external-merge race when
  the human merges before reaching `in_review`. Each handler's entry-time `_pr_terminal_stops_the_tick` flips to
  `done` instead of stranding the issue, and decides the closed-without-merge ending off the same reading.
- Closed `question` — a human closing the issue is the terminal signal
  [`_handle_question`](conversation-stages.md#_handle_question-label-question) consumes to finalize to
  `done`.
- Closed `discussion` — two different endings, and the label is swept for a longer window than the rest. With no plan
  PR published, the close is the whole signal and
  [`_handle_discussion`](conversation-stages.md#_handle_discussion-label-discussion) finalizes to `rejected`,
  which is what takes
  the issue back out of the sweep. WITH one, the close says nothing about the design: the stage holds its terminal
  and keeps the `discussion` label precisely so this sweep goes on yielding the issue until the plan PR itself
  merges (`done`) or closes unmerged (`rejected`). Nothing else revisits a closed issue, so a terminal flip while
  that PR is open would strand the worktree and the branches the plan lives on.

`workflow:ready` and `workflow:blocked` are swept closed for **cleanup only**, and for one reason: a decomposition
outcome writes one of them, and a run spawned before its owner was observed closed lands *after* that observation. So
a close that was latched and receipted while the owner was still `workflow:decomposing` can end up on an issue closed
under one of these — with the ending unmarked, the ref its children were cut from still held, and the latch that
would route it living only in the process that took it. A restart before any cleanup pass would lose that ending for
good, so the query is what makes it discoverable without one. Only their CLOSED issues are asked about: an open
`workflow:ready` issue is polled and dispatched exactly as ever. What it costs is one pinned read per closed issue on
either, on the sweep cadence, and an issue read and a second pinned read behind it where the record still names a
cycle to end.

`workflow:decomposing` and `workflow:umbrella` are swept closed for the same pass, and all four are the one case where
the label does not choose the handler -- and the one case the `backlog` / `paused` filter does not get to drop, since
discarding a closed owner there would discard the close itself and leave a live generation to spawn against after a
reopen and an unpause. The control label defers what the pass would DO; the mark still lands. A split records what it
owes the remote on the closing issue's own generation ledger — the branch its superseded candidate was committed on, and
the immutable snapshot ref its children were cut from — and an issue a human closes mid-cycle is one nothing else would
ever bring a tick back to. So the dispatcher reads *closed* first and routes both to the cleanup sweep
([`delivery-stages.md`](delivery-stages.md#closed-owner-cleanup-sweep-no-label-of-its-own)) rather than to
`_handle_decomposing` or `_handle_umbrella`, which would spawn the decomposer or activate children on an issue whose
close was a decision to stop. The pass ends the cycle: it marks the cancellation, closes any pull request that cycle was
holding, re-reads every recorded snapshot consumer, settles what can be settled, and moves the issue to `rejected` once
nothing is owed. Being routed there at all is what says a close was *observed*, so an issue the pass finds open again —
reopened between the poll and the worker's refetch — is marked cancelled and stopped there, with the ending left to the
dispatcher's own guard from the next tick (unless its record has moved on to a cycle restarted after the close, as
above). It does nothing else — no agent, no activation, and no child of the split touched. `rejected` is the only label
it ever writes, and it is what takes the issue out of this sweep for good. It rides the same sweep walk, the same
cadence, the same label cache, and the same absent-label throttle as the recovery labels above. It is partitioned as
**fan-out** rather than into the family bucket, and submitted `cap_exempt=True` on its own: the bucket's exemption is
all-or-nothing, so one open `workflow:decomposing` issue sharing the tick would make a closed owner cap-counted and,
under a saturated cap, skipped — which would stop the repository reclaiming refs for as long as its decomposer stayed
busy.

- Closed `workflow:decomposing` / `workflow:umbrella` / `workflow:ready` / `workflow:blocked` — a snapshot owner a
  human closed mid-cycle, or one whose own decomposition outcome landed after that close. Its generation
  ledger may still hold a superseded branch, an immutable snapshot ref, and a pull request under a hold, and no
  other pass revisits a closed issue. It is the one sweep entry that resumes no workflow: what it ends is the late
  cycle, and it reaches a terminal only once that cycle owes the remote nothing (see above). An issue on any of the
  four with no late cycle at all costs the pass its one pinned read and nothing else — it is not written to, not
  relabelled, and not commented on.

The closed-issue sweep issues one closed-issue query per sweep label the repository actually carries, per repo, every
tick — a fixed request cost that drives GitHub primary-rate-limit exhaustion on multi-repo hosts. The four cleanup
labels ride that same walk rather than a second pass of their own, so what they add is four label lookups and four
closed-issue queries on the ticks the sweep already runs, and nothing at all in between. A pre-namespace
spelling the rename already retired costs only its `GET …/labels/<name>` miss, and even that is thrown away for
twenty sweeps before being asked again rather than re-requested every pass. The spellings one sweep confirms absent
are reported together, in a single repo-qualified INFO line naming them, so a migrated multi-repo host does not open
with a burst of near-identical lines that reads like broken configuration; a sweep whose legacy lookups all came from
the throttle confirms nothing and logs nothing, so that line recurs when the window expires rather than every pass. A
missing namespaced label, or a lookup that failed any other way — a 403 is no answer about whether the label exists —
stays a per-label warning.
`CLOSED_ISSUE_SWEEP_EVERY_N_TICKS` (default `1`) batches the whole sweep to once every N ticks; the open-issue poll is
unaffected, so the only effect of `N>1` is that an externally-merged/closed issue can take up to `N-1` extra ticks to
finalize. See [configuration.md#github-rate-limits](../configuration.md#github-rate-limits).

`done` is queried by neither sweep, and nothing needs it to be: an umbrella's terminal makes the retirement durable
one write *before* the label, so no `done` issue is ever left carrying a late cycle. A crash before that label lands
leaves the owner on `workflow:umbrella` with the resolution recorded, which the closed-owner sweep finishes.

`done` and `rejected` are terminal no-ops. Every handler receives the active `RepoSpec`, so `git worktree add`,
`git fetch <spec.remote_name> <spec.base_branch>`, push-token resolution, and PR-base selection all flow from the spec.

### Pinned state

Per-issue durable state lives in a single **pinned comment** on the issue (`<!--orchestrator-state {...json...}-->`).
The schema is defined by `read_pinned_state` / `write_pinned_state` (see `github.pinned_state.PINNED_STATE_MARKER` /
`PINNED_STATE_RE`). `read_pinned_state` trusts a comment as state only when it is authored by the account backing the
orchestrator's token AND its whole body is the marker, so neither a third party's forged marker nor an ordinary
bot-authored comment that embeds the marker in prose can preempt state (see
[pinned-state authentication](../security.md#pinned-state-authentication)).

The payload is written with the wrapper's own terminator escaped — `-->` inside it is serialized as `--\u003e`, the
JSON escape every reader decodes back to what was stored. Values reaching the record are not the writer's to
sanitize: an agent's explanation, a preserved pull-request body, a human's own words all arrive as somebody wrote
them, and one carrying `-->` would close the comment early and leave the rest of the record as visible issue text.
What is escaped is the serialized form and never the value, and a body written before this reads back the same.

A comment that passes both checks is the state comment whatever its payload turns out to be. One that will not parse,
or that parses into anything but a JSON object — `[]`, `7`, `null`, from a truncated write or a hand edit — is refused
rather than handed on: the state reads back empty and flagged unparsed, so a reader deciding on the absence of a
recorded branch or pull request can tell it from an issue that pinned nothing (both carry `{}`), and the comment id is
kept, so the next write replaces the corruption in place instead of leaving a second pinned comment beside it.

Most writers rewrite the whole record from the state they read (`write_pinned_state`), which lands wherever it can — in
place, or as a new comment where none is named or the named one is gone. A **guarded commit**
(`workflow/engine/pinned_commit.py`, which the verification-evidence publication and settlement, the evidence
reconciliation's retirements, `validating`'s invalidation of an unanswered carry, the developer report's writes, a
reviewer round's launch, return, verdict, and park writes, a change request's handoff and its recovery's writes, and
every write of an approval's tail commit through, and which the finish of a base rewrite the base refresh published
itself lands through) is never written from its caller's state. It is captured from the reading the caller decided on —
the comment's id, every field as the comment's JSON spells it, the prerequisite fields the decision rests on, an absent
one included, and the fields the caller owns — and derived over a fresh reading: each field the caller's staged state
changed, every one of which it has to own, is laid over that reading; a transformation the caller's domain supplies
decides its own owned field over the fresh value, so a total, a ledger, or a watermark both roads moved keeps both moves
— or answers that the two will not join, which is refused as an owned conflict; and every other field, unknown ones
included, is kept as the fresh reading carries it. Fields are compared as the JSON spells them, keys sorted, so `null`
is not an absent field, `true` is not `1`, and `1.0` is not `1`, at any depth. The fresh reading can be taken alone too
(`reread`), for a caller with requests of its own to make over the comment it captured before it stages anything.

It refuses — writing nothing, and touching nothing the caller holds — where the comment will not read, will not parse,
or is not the one captured (replaced, deleted, or never pinned: the strict edit never creates one); where a prerequisite
moved; where another writer moved an owned field to something other than what the caller staged; where the caller staged
or transforms a field it did not declare; and where the complete candidate, rendered through `pinned_state_body`, is
longer than `MAX_PINNED_BODY` or than the caller's own domain check admits — a check the guard carries, asked of that
very candidate. That measurement can be taken alone (`prepare`) ahead of an external effect that depends on the record.
The commit takes every check again over a reading taken behind whatever requests came between, sends nothing for a
candidate the comment already reads as, and otherwise lands in place through the strict edit
(`GitHubStateMixin.edit_pinned_state`), which walks to the comment once more and rewrites it only while it still reads
as that fresh reading did — a comment that moved in between is refused as moved. An edit that went out and was never
confirmed — a lost response, a refused request, or an answer carrying another body — is reported as unconfirmed, neither
committed nor refused: whatever receipt the caller's domain keeps remains what settles it on a later reading. None of
this serializes two pollers writing one issue. GitHub's comment edit takes no condition, so the guard narrows the window
between a reading and the write laid over it without closing it.

The developer report's writes commit this way too (`workflow/engine/report_commits.py`): recording a finished run's
delivery, binding it into a transaction, settling that transaction (`workflow/engine/report_settling.py`, prepared
before the report is posted and committed behind the post), the reconciliation's drop of a transaction nothing is owed
for and the retirement of its own `report_record_damaged` park, the `report_undeliverable` park a refused recording or
binding takes, and the fixing recovery's release of a report no checkout can publish. Each is captured
over the reading its tick last synced with the comment — what a state remembers it was read from or written as
(`PinnedState.synced`) — rather than over the state the tick holds, because a tick stages changes between two writes (a
run's usage and session, the park a reply answered) that have always ridden the next one. A field the tick changed since
that reading is its own and lands as the tick spells it; the write declares its own fields beside those, and the report
records it was decided on. A usage total, the cost tags, a comment-id watermark, and the comment-id ledger keep both
roads' moves rather than conflicting. A road that lays another road's moves over a tick's state without writing — the
validating reread, the run circuit's merge — advances that reading for the fields it laid, and one that replaces the
state with what its own commit landed — the verification settlement and the evidence retirements — advances it to that
reading whole (`pinned_commit.takes_in`), so none of it counts as the tick's own move. A refused report write leaves the
tick's state as it was and marks it withheld (`PinnedState.withheld`): the state was decided on a comment that has since
moved, and written whole it would put back every record the refusal kept, so the whole-state writer writes nothing for
it for the rest of the tick, until a guarded commit lands. A write sent and never confirmed is withheld the same way; a
refusal for room alone is not, where the comment read again is still the one the tick synced with, since that comment is
simply too full and the roads behind a report still owed are what give its room back. A report post or re-read that
leaves its transaction owed without any report write landing asks the comment the same question once more
(`ReportCommit.withholds`): one another road wrote while the request was out withholds the state, and one still reading
as the tick synced with leaves it to be written.

A reviewer round's writes on `workflow:validating` land through the same tick-state guard
(`stages/validating/review_writes.py`), each declaring the fields it owns and the records it was decided on, as those
records read on the reading behind it: the launch's `review_agent` and `review_subject`, captured over the reading its
subject was bound to rather than the tick's state and decided on the report records, `pr_number`, and
`review_returned_verdict`; a returned run's own records -- its usage folded into the `issue_*` totals, its session,
`last_review_at`, and `review_returned_subject` -- and the park a timeout or a missing VERDICT line takes with them,
decided on the same records; and the returned verdict persisted with the transaction its claim was minted as, its drop,
and the `reviewer_unverified` / `reviewer_unrecorded` parks and a failed verify gate's park, each decided on those and
the `verification_evidence_*` records besides. Each is decided as well on the fields of its own it may stage exactly as
the comment already spells them -- the launch on `review_agent` and `review_subject`, a return on
`review_returned_subject`, a park on `awaiting_human` and `park_reason` -- since a commit tells a write's own moves by
their difference from the reading, and a launch repeated over a subject already recorded, or a park taken by a round a
reply bought over a parked reading, would otherwise land beside another road's spec, subject, or cleared park. A park is
prepared before its notice, with what posting it writes reserved at its widest, and committed behind it; a verdict is
held, over the very candidate sent, to the room its handoff and its transaction's settlement reserve, and one without
that room is parked as unrecorded. A record another road moved after the reading a write was decided on, an owned field
it moved, a comment that will not read or parse or is not the one read, or a candidate past `MAX_PINNED_BODY` refuses
the write with nothing written, and nothing depending on it is made -- no reviewer launched, no notice posted, no
evidence published, no verdict acted on -- and the tick's state is withheld as a refused report write's is. A write sent
and never confirmed acts on nothing either: a launch it may have recorded is committed again, with nothing sent, by the
next tick's round, and a verdict and transaction it may have persisted are published and finished by the next tick's
reconciliation and recovery with no second reviewer, artifact, fold, charge, or round.

A change request's handoff and its recovery land through that guard too, each declaring its own fields and records.
The handoff (`stages/validating/review_handoffs.py`) is prepared before its feedback is posted -- the candidate measured
with the request at its widest handoff and its developer's charge beside it -- so a comment another road filled, moved,
or replaced posts nothing; behind the post it writes `review_returned_verdict` as handed beside
`pending_fix_reviewer_comment_id`, asking that same room of the candidate the commit sends -- its post's ledger entry
counted once -- so a comment another road filled while the post went out takes no handoff with no room left for the
developer's charge, and decided on the report records, `pr_number`, `review_returned_verdict`, the
`verification_evidence_*` records, that anchor, the run ledger the handed count is read off (`agent_runs_used`,
`issue_agent_runs`, `agent_run_reservation`, `agent_run_fingerprint`, `agent_run_owed_started`), and `awaiting_human`
and `park_reason`. A park another road records is a human's to answer: one the state in hand already shows -- carried
onto it by the reading that proved the request ready -- posts, writes, relabels, and launches nothing, and the reading
behind the post, the ones ahead of the relabel and the launch, and each the run circuit charges and starts the launch
from (`stages/validating/review_launch_hold.py`) hold the request where one stands or its flags moved, with nothing
written over it, relabelled, charged, or launched, until a reply clears it. The drop of a request
whose subject or evidence moved before its developer was launched is decided on the same records, the anchor, and
`agent_run_owed_started`; the retirement of one whose developer that start records launched on the verdict and that
start alone. The `agent_execution_failed` park of a launch that may have run (`stages/validating/review_launch_park.py`)
owns its flags, the verdict, the anchor, and its notice's ledger entry and thread read, decided on those records, the
anchor, `awaiting_human` and `park_reason`, and the run ledger, and is prepared before its notice. The recovery of a
waiting verdict (`stages/validating/review_resume.py`) writes back a cleared anchor decided on the records the request
stands on, the anchor still cleared, and the park's flags -- writing nothing where the reading it is decided over shows
a park standing -- drops a verdict for good over the comment read afresh with nothing of the
tick's own beside it -- a handed one whose developer may have run only where that reading's run ledger still shows the
launch not owed, and decided on that ledger too -- and settles a round a reply bought decided on the verdict and the
park's flags. A change request's developer run retires it only in a guarded commit decided on it, `pr_number`,
`agent_run_owed_started`, `pending_fix_reviewer_comment_id`, and the park's flags: the commit recording its report, the
park the round takes, or the hand-back behind the relabel. Any of them refused writes nothing over the other road's
write and nothing behind it -- no feedback post, relabel, notice, or launch -- and withholds the tick's state; one sent
and never confirmed is finished by the next tick from what the comment carries -- a handoff found handed and resumed, a
post found by its words and receipt, or by its place in the thread (`feedback_posts.finds`), a drop, retirement, park,
or settlement found landed -- with no second post, developer, or charge, and no review round but the one the confirmed
write itself leads to: a pushed fix's or a report's hand-back, a timeout park's recovery, the round a reply bought, or a
fresh one a dropped record leaves its subject for.

Every write of an approval's tail on `workflow:validating` lands through the same guard
(`stages/validating/squash_writes.py`), behind the reading of the comment the tail already takes ahead of each
(`handoff._holds_its_records`), and is decided on every record the tail holds as that reading spells it
(`handoff.HELD_ON`): the report records, `pr_number`, `review_returned_verdict`, the `verification_evidence_*`
records, the three review subjects and `review_approved_evidence`, `awaiting_human` and `park_reason`, the
`late_collapse_*` record with `late_collapse_handoff_sha`, and every record a report debt is read from, as the
evidence proofs bind them (`developer_report_owed` beside those). That reading holds the tail to all of them as well,
measured from the comment as the tail last read or wrote it, and so does the one behind the verify gate: a report
recorded as owed is a move of what the approval was proved over, retiring its verdict for a fresh reviewer, while a
park or a collapse record another road put down is never laid over the state for the tail's next write to clear or
end -- the arc writes nothing over it but what it posted, and the verdict waits for a later tick. Each write declares
what it owns beside what the tick staged: the retirement of the approval's verdict -- behind a subject that moved or
would not read, a squash the size gate held, or a notice that went unposted -- owns `review_returned_verdict`; the
squash's own writes through the client it is handed own the collapse record, the size gate's records riding them as
the tick's; the handoff ahead of the relabel owns the verdict it retires, `review_approved_subject` and
`review_approved_evidence`, the park it ends, and the collapse record and `late_collapse_handoff_sha`, plus
`verification_evidence_pending`, `_history`, and `_revision_floor` with the claim where the squash's evidence earns a
carry and what an invalidation writes where it is refused; a carry decided by the settled handoff's recovery owns only
what that decision writes; a failed squash's `squash_failed` park owns its flags, the verdict it retires, and what
posting its notice writes, prepared before that notice; and the end of `late_collapse_handoff_sha` behind the label
owns that field alone, over the comment read once the label moved. A carry is held to the very candidate its commit
sends, another road's writes since included: where that candidate is past `MAX_PINNED_BODY`, or has no room for the
carry's settlement or for the invalidation the settlement leaves room for, the carry is not recorded owed and
unpublishable, nor left unrecorded with the handoff behind it, but invalidated in its place, in a commit of its own
carrying no transaction. A record another road moved after that reading, an owned field it moved, a comment
that will not read or parse or was replaced, or a candidate past `MAX_PINNED_BODY` refuses the write with nothing
written and the tick's state withheld: no park is reported, no handoff ended, and no label moved, and where a record
the tail holds moved, only what it posted is recorded on the ledger -- and the verdict it holds retired, where that
record is one the approval was proved over -- as where that reading itself caught the move. A write sent and never
confirmed acts on nothing either: the handoff it may have landed names the commit the relabel is owed over -- for
every approval, one that collapsed nothing included -- so the next tick's recovery moves the label with no second
reviewer, gate, squash, notice, or charge; a carry it may have recorded is published and settled by the next tick's
reconciliation once; and a park it may have landed is found standing, and mentions nobody again. The squash's record
of its collapse is the one write whose unconfirmed edit the squash itself answers, taking it as refused and rewriting
nothing; where it landed, it carried the approval the tail had staged beside it, which the tail's next reading finds
where it last read none, so the tail records what it posted, retires the approval's verdict, and parks nothing, and
the next tick's recovery finishes the collapse that record claims under that approval with no second reviewer. Every
road but these, a change request's, the reviewer round's, and the verification evidence's still writes its whole
state.

The keys that matter for the state machine fall into a few groups:

- **Agent identity.** `dev_agent` + `dev_session_id` (locked dev session — see
  [in-flight session lock](../workflow/command-specs.md#in-flight-session-lock)),
  `review_agent` (traceability only; reviewer is fresh per round), `decomposer_agent` + `decomposer_session_id`
  (parents), `question_agent` + `question_session_id` (`question` stage), `discussion_agent` +
  `discussion_session_id` (`discussion` stage), `late_agent` + `late_session_id` (the late adjudication of an
  oversized committed candidate — see [the late run](#the-late-run) below). The last four pairs are separate pins on
  purpose: each seeds from `DECOMPOSE_AGENT` on its own first spawn and is then locked independently of the others on
  the same issue, so a flip of `DECOMPOSE_AGENT` between two rounds can neither move a conversation onto a backend
  that never ran it nor hand that backend a session id it never issued. The three conversation pairs also *resume*
  their own session id on a human reply — with the decomposer pair excepted on an issue stopped by its spawn budget,
  where no reply resumes anything and the renewal that lifts the park retires the session it would have replayed
  ([The retry budget](#the-retry-budget)) — and the late pair resumes on exactly one: a substantive trusted answer to
  the categorized question the adjudicator asked, which is a reply to the agent that asked it. Every other late run is a
  fresh conversation against the frozen candidate — see [the late run](#the-late-run) for the two conditions a resume
  takes.
- **Decomposition.** `children`, `dep_graph` (`{child_idx_str: [child_idx, ...]}` — GitHub has no first-class blocks
  relation), `decomposed_at`, `pickup_comment_id`. An ordinary split writes `expected_children_count`, `umbrella`, the
  whole declared `dep_graph`, and `split_attempt` in one write before its first child exists. `split_attempt` is sixteen
  lowercase hex digits minted for that split alone, and every child it creates carries it in a hidden body receipt
  stamped after its slice,
  `<!--orchestrator-split-child:issue=<parent>:attempt=<split_attempt>:index=<slice>:lineage=<owed>-->`, so a recovery
  can find the child a crash left created and never recorded — and never mistake another split's child for it. `<owed>`
  is the late lineage the split seeds that child with, `<root>-<depth>-<cycle>-<generation>`, or `none`. Only a whole
  receipt counts, and the last one in a body governs, since a slice may quote another child's body ahead of its own
  stamp. Any other `split_attempt` — another split's, a value no binary mints, or none — finds no receipt, so a split an
  older binary made leaves nothing to adopt. A drift reset clears `split_attempt` with the rest of the manifest, after
  writing that split's children — any unrecorded one found by its receipt — onto `late_consumers`, and a `blocked`
  parent whose children all resolved drops it in a write ahead of its flip back to `workflow:ready`. A child this
  orchestrator opened whose seed is not the one its receipt owes it — no `parent_number` naming that parent, none of an
  owed `late_ancestry_*` group, a group partial, rewritten, or naming another place in the lineage, any group on a child
  owed none, or a pointer at a snapshot other than the one that split preserved, or half of one — is held by the
  dispatcher ahead of every handler but `done`'s and `rejected`'s, and ahead of the step aside a live adjudication of
  its own takes, parked (the `park_awaiting_human` record's reason `replacement_lineage_unproved`) once, then silently,
  until its split or its parent's recovery writes that seed onto that record and lifts the park in the same write, or a
  human does both by hand; one whose pinned comment will not parse is held with nothing written. A restart an operator
  authorizes on such a child keeps the seed. A pointer is the one part a seed may lack, since the child's own reuse
  guard drops the ref and its commit together once its ref is gone. The split's summary ends on
  `<!--orchestrator-split-summary:issue=<parent>:attempt=<split_attempt>-->`, and a recovery that finalizes the split
  posts one only where no comment of ours carries that receipt — so a summary GitHub refused is posted again, one that
  landed ahead of a label write that failed is not, and a split recorded with no `split_attempt` gets none. A split that
  meets a child another poller holds records it, creates the rest, and leaves it unseeded with the parent on
  `workflow:decomposing`, withholding its summary, its label, and its first release until that recovery has seeded the
  child.
- **A debt with no record behind it.** `late_approved_sha` + `late_approved_lease` + `late_approved_basis` outlive the
  generation that granted them, because the write that approves a candidate retires that generation before the push.
  The basis is what the debt RESTS on, said by the owner that granted it rather than inferred from the records
  standing beside it, so the tick that comes back after a crash can tell the gate's own count from a debt an
  operator's gesture is behind. Where the lease is set the approval was taken over a pull request the remote already
  carries, and the dispatcher pays it ahead of every handler rather than leaving a stage to run over a publication the
  commit never joined — but only from a checkout still standing on the commit, and never while the issue is under
  `workflow:decomposing`, where the settlement owns the push. A checkout that is absent, unreadable, or standing
  elsewhere parks instead. The group is dropped by whatever settles the commit: the push that lands it, an approval
  superseded, a hold that routes it to the adjudication, or a reset that sends the branch back off it — the auto
  rebase's after a refused push, and the squash's own rollback after one.
- **A held pair's continuation.** `late_spends` records what the tick that froze a pair owed if its hold went
  through — the reviewer round a fix spends, the bookmarks a consumed batch clears, the head a finished docs pass
  produced, the outcome a resolution earned, the head a recovered push ahead of a rebase published — as
  `[[field, value], ...]`. It is one of `LATE_STATE_KEYS`, so it lives
  and dies with the generation it is about, and each member is bounded by the FIELD it names rather than by what a
  comment can carry: a round is a real non-negative count, a bookmark is only ever cleared, a settled head is a whole
  object id or none, an outcome is one bounded single-line name. A counter that came back as text would pass any
  looser check and fail at the `int(...)` the round cap is counted with, on a tick nobody is watching. One exception
  to living and dying with the generation: the write that APPROVES a small candidate retires that
  generation before the push it licenses runs, and puts these back inside the same write. Otherwise a push that misses
  leaves an approval the next tick can pay and nothing that says what paying it closes — the caller parked, and the
  stage it returns to short-circuits on that park. The reconciliation ahead of the next handler restores them for the
  same reason it restores an interrupted reading's: a tick with no run behind it could re-derive none of it. Whatever
  finally settles the approval drops them with it, so no later cycle inherits a round it was never owed — and a
  landed push settles it in the write that carries the receipt, so the fields go down with the publication rather
  than in a write behind it that a crash can take.
  Read back as ONE group, and bounded on both ends: the key has to name a field this workflow's routes actually
  close (`late_split/spends.py` spells that vocabulary as literals so the domain does not import the four stage
  packages that own the keys, and a guard test proves the two agree), and the value has to be one the pinned comment
  can carry. A single member that fails either refuses the whole group and `late_claims` parks on the raw key still
  being there — half-applied is worse than none, since the caller restoring the hold cannot tell which half it got:
  the round advances, the bookmark it was spent for stays pending, the record is discarded as paid, and the next
  re-entry reruns a developer over feedback that was already answered. On the allowed road the
  retirement drops this key in the same write that grants the approval, so the recovery reads it BEFORE its own push
  and the fields ride the receipt that push writes — one write, so no window exists in which the publication is
  recorded and the round it spent is not.
- **Conflict rounds.** `conflict_settled_outcome` + `conflict_settled_sha` name a resolution the size gate held —
  which of the four content updates it was (`agent_resolved` / `base_rebased_clean` / `recovered_push` /
  `drift_resolved`) and the head it produced. Written inside the
  routed hold's own write ahead of the relabel, and read back by the resumed `resolving_conflict` tick, which could
  not re-derive either: the settlement publishes the commit, so the branch it comes back to already carries its base
  and would be flipped as `base_up_to_date` — the one exit that resolves nothing and stamps no
  `last_conflict_resolved_at`. Dropped by whichever pushed-round tail finally pays the round. A landed push that
  finishes a round writes the pair too, in the gate's own write beside the publication receipt, so a round whose
  tail a crash cut short is finished from it on the next tick — and for `base_rebased_clean`, `agent_resolved`, and
  `recovered_push` that tail records the rewritten head's `developer_report_rewrite_debt` from the receipt beside it.
  `conflict_preamble_sha` is the counterpart for a recovered push that lands still behind base, which finishes no
  round and so writes no pair: the head it publishes, written in the same gate write (and in a hold's, ahead of the
  relabel) so the report debt it owes is not lost to a crash before the debt's own write or to an adjudication that
  publishes it later. The resumed tick reads it before anything else; once the publication receipt names that head
  it is written `null`, and the debt is recorded where the pull request was just fetched standing on it. Any debt
  this stage records drops it too. `conflict_handed_sha` is the head a counted round hands to `workflow:validating`,
  written in the same write as the count, ahead of the relabel, and written `null` by the write behind it; a tick
  that finds it on `workflow:resolving_conflict` with the branch in sync and standing on that head makes the move
  without counting the round again, and drops it where the checkout is proved elsewhere; a head nothing could prove
  holds the tick with the claim kept, so the round is neither counted again nor parked at the cap it reached. Where
  that `null` write was lost, `workflow:validating`
  writes it before anything else, and the base refresh drops it in the write that opens a new conflict episode, so
  no later episode reads it as a move still owed.
  - **The publication a body edit's resume owes.** `conflict_resume_from_sha`, `conflict_resume_to_sha`, and
  `conflict_resume_pr_number` are the head a body-edit resume's push is leased against, the commit it sends, and
  the pull request it goes onto, staged with the report that resume returned so the report's own guarded commit
  carries them -- or the park taken in its place, for the reply that finishes it. A rebase the developer ran
  diverges the branch exactly as a replay does, so the divergence guard admits that shape against this record while
  the issue still owes the report: the pull request has to stand on the head it names and the checkout on the
  commit it names. It is no rewrite evidence and the gate is handed nothing from it. It is also what the report saved
  beside it is about: while that report is recorded and unbound, the recovered push publishes no other head and the
  binding ahead of a rebase takes no other publication, parking `report_undeliverable` with the record left as it
  stands. A run that commits nothing and reports writes the head the pull request carries as both ends of it, in the
  guarded commit that saves that report (or the park held in its place, which marks the work undescribed), over any
  earlier candidate: that report is not tied to a candidate it is not about, and it is still the report of one
  commit, so a checkout that gains a commit after a crash cut its binding short parks the same way rather than
  publishing that commit under it. A run that reports over a head nothing could read writes neither this record
  nor its report: the issue parks for the report with the run's work marked undescribed. An `ACK:` or a question
  saves no report and leaves the record. It is read only while the report it went down with is unbound, and no
  write retires it while any report is: not a settlement, which could be an older transaction's beside a newer
  report of the same head, and not the tail that counts the round, since the relabel behind a landed push can fail
  and a commit the checkout gains before the binding is still refused against the record. That tail drops it where
  no report is unbound, and the base refresh that opens the next conflict episode drops whatever is left.
  - **The replay a rebase made.** `conflict_replay_from_sha`, `conflict_replay_from_base_sha`,
  `conflict_replay_to_sha`, and `conflict_replay_pr_number` are what a `workflow:resolving_conflict` rebase records
  ABOUT ITSELF, because the tick that runs a replay is not always the tick that publishes one. The head it is about
  to replace, the fork point that head's contribution is read over, and the pull request it is being made against go
  down before the rebase runs — the first two because the rebase destroys them, the third because `pr_number` is a
  field a later tick can find pointing somewhere else and a rewrite is evidence about ONE publication. The commit it
  produced is stamped on once there is one, before the size gate is entered. Written only for a branch standing on
  the commit `late_exempt_sha` names, because nowhere else could a transfer ever be granted and a record there would
  be a request spent to protect nothing. Two readers, both on the tick that finds the replayed commit unpushed after
  a crash. The divergence guard asks it FIRST, because a replay moves the branch off the head it replayed and so
  comes back ahead of the publication and behind it -- the shape a stale checkout carrying somebody else's commit
  also has, which this stage parks. A record naming that exact head, that exact commit and that pull request is what
  tells the two apart, and it leases the force-push to the pre-rebase head. The recovered push
  (`conflicts/divergence._push_recovered_commits`) reads it again for the evidence it hands the gate: no probe of
  the branch tells a replay from a resolution an agent wrote or the unpushed fix commits the `fixing` drift reroute
  sends over — on base as readily as behind it — so the record is the only thing that can. It is acted on only where
  it is about the publication and the commit in hand: the pull request it names has to be the one the issue still
  records, the head it names has to be the head that push is leased against, and the commit it names has to be the
  one the checkout is standing on. Read live, that first one is the gap: a repointed `pr_number` would let this
  branch's replay be offered as a rewrite of some other open pull request, and one standing on the same head would
  satisfy every check the permit makes. The stamped commit is also what makes a stale group inert rather than
  dangerous, which is why clearing it is tidiness: the no-op flip and whichever tail publishes the replay drop it on
  writes they were already making, and never for a request of its own.
- **PR / branch.** `branch`, `pr_number`, `review_round`, `conflict_round`. The first two are also what a published
  discussion plan records, beside `discussion_plan_path` — the path of the Markdown file that PR carries. The stage
  reads the plan path and `pr_number` together as its "already published" gate, since an issue relabeled into
  `discussion` from a PR stage arrives carrying somebody else's `pr_number`. `discussion_publishing_sha` is the
  in-flight half of that record: the tip a publication was pushing, written before the push and retired by the write
  that records the PR, and the only thing that makes a plan-shaped commit on a parked issue's branch one this stage
  may finish rather than one it merely found there.
- **Drift baseline.** `user_content_hash` — SHA-256 over title + body + non-orchestrator comments; updated whenever
  the orchestrator reacts to a human edit, and whenever a `workflow:implementing` / `workflow:validating` frozen reply
  batch is settled, to the fingerprint of that read through the last reply it delivered. On a parked tick the drift
  check compares it with the frozen comments at or below the park's watermark, so replies to the park are delivered
  by the batch rather than read as an edit. Every drift resume records it the same
  way: the settlement of the prompt that answered the edit writes it, to the fingerprint of the read that prompt was
  built from, so a comment written while the agent was out is still an edit. That fingerprint is also the revision
  the run's report is stamped with, so no reader holds a report against requirements its own prompt already
  contained. Three of the four roads write nothing ahead of the run: a deferral, a refusal park, a cleared park, a
  shutdown kill, a live pause and a launch the run circuit turned away all leave it where they found it, since a
  baseline written for a prompt nobody read would mark the edit answered and hand the words under it to the next
  spawn recorded as delivered. `in_review` stages the refreshed value ahead of its run, and only because it may
  never become durable apart from `in_review_handoff_pending` below; the settlement then refines it to what the
  prompt fingerprinted, and the two short-circuits that write no pinned state at all discard both. The `documenting`
  unwind writes it without delivering anything, and there it is a claim about the REROUTE rather than about the
  conversation: no agent ran, so no feedback watermark moves and the comments stay unread for the reviewer the
  relabel hands the issue to. A late adjudication on `workflow:decomposing` writes it too, whenever it consumes a
  content reading — the same write that moves its local watermark and the shared `last_action_comment_id`, to the
  hash that one reading froze (see [the local fingerprints](#late-generation-state)). So does an auto rebase's attempt,
  over the replies to its own park that only asked for the retry -- in the write that spends the reply, to the hash of
  the thread through the last of them, and only where the recorded value -- in either spelling the drift check
  accepts -- already covers the thread up to the watermark they were written past (`workflow/engine/rewrite_replies.py`,
  see [Base refresh](#base-refresh)), so an
  adjudication the replay is handed to never reads an operator's retry as guidance. What a run may cross on the
  issue thread is bounded beside it — see [the drift section](delivery-stages.md#user-content-drift-detection).
- **Observed reading.** `observed_user_content_hash` — the same fingerprint over a reading a stage acted on without
  consuming any of it, written only where no `user_content_hash` is recorded: by a late adjudication carrying on over a
  quiet reading. It moves no baseline. The drift check compares against it in place of the missing one, recording
  `user_content_hash` where the thread still matches and reporting drift where it does not, and ignores it once a
  baseline is recorded — so an umbrella a late split made meets a comment written while the adjudicator ran as an edit.
- **The developer report a pull request is owed and the one it carries.** The additive
  `developer_report_delivery` / `developer_report_pending` / `developer_report_current` /
  `developer_report_handoff` group, each one nested object, and each absent on every issue that predates it. They
  are not written together and none of them replaces another: the delivery record goes down when a run finishes and
  is dropped by the write that binds it, the pending record goes down when that binding happens and is dropped when
  it settles, while the settled pair records the last report that landed and stays until a later settlement
  overwrites it. So an issue between publications carries the settled pair and neither outstanding record; an issue
  whose run has reported and whose code is not published yet carries the delivery record alone; an issue inside its
  FIRST publication carries the pending record and neither settled one; and an issue inside any later publication
  carries the transaction beside the previous report and its receipt, which are what a reader still needs while the
  new one is outstanding and are exactly what the settlement then replaces. The owners are the
  `workflow/engine/report_record*`, `report_delivery_state` and `report_settlement_state` modules, what turns a
  finished run into a delivery is `report_delivery.py`, what binds it and publishes it once the code reaches a pull
  request is `report_binding.py`, and what reconciles an outstanding transaction ahead of every handler is
  [the developer-report transaction](delivery-stages.md#the-developer-report-transaction-every-dispatch). The
  initial implementation delivery produces them
  ([`_handle_implementing`](delivery-stages.md#_handle_implementing-label-workflowimplementing)), and so does either
  half of the fix loop on an open pull request: a requirements-drift resume, recorded under the `workflow:validating`
  or `in_review` route it ran on ([user-content drift](delivery-stages.md#user-content-drift-detection)), and a
  reviewer-requested round, recorded under `workflow:fixing` — the label that round actually runs under, and one of
  the roads whose park notice therefore says the pull request stands where it stood rather than that none was opened
  ([`_handle_validating`](delivery-stages.md#_handle_validating-label-workflowvalidating)'s `changes_requested` arc
  and [`_handle_fixing`](delivery-stages.md#_handle_fixing-label-workflowfixing) step 9). So does the rewritten-head
  report refresh, recorded under the `workflow:validating` route and the requirements baseline it froze before the
  run, with no round or watermarks riding it
  ([`_handle_validating`](delivery-stages.md#_handle_validating-label-workflowvalidating) step 3).

  `developer_report_delivery` is what one completed run wrote, recorded **before** the size gate reads its candidate
  and before the push sends it — which is the last moment the report is certainly recoverable, since the session
  that wrote it ends with the tick and every road past that line can freeze the work for a human, fail, or die. It
  carries the receipt the transaction will be named by, the report revision, whether a publication or a
  verification is owed, the route that produced it, the complete report text or the exact location and content
  revision a verification asserts, the feedback watermarks the run consumed, the bookkeeping its route closes, and
  the requirements revision the run was actually handed — for a drift resume on either review stage, the fingerprint
  of the read its own prompt was built from, and for a fix round the
  revision its own spawn was given — carried with the run rather
  than read back off the comment, which on a fixing tick is a baseline that same tick rewrites minutes later and
  would fold in every reply that arrived while the developer worked. The bookkeeping is what a
  fix round freezes there as well as handing to the size gate, because the one handover with no code in it — a report
  answering a reviewer item that named no repository change — passes no gate at all, and has bought nothing until the
  report is on the pull request: the write that SETTLES the report is the only thing that closes the round and the
  bookmarks it consumed, so a post GitHub refused, a re-read that failed, a requirements edit landing mid-run or a
  crash leaves the round unspent and the replay anchor intact. Applied from the frozen
  pair rather than recomputed, so a settlement a crash hid and a later tick replays counts the round once. The
  WATERMARKS are frozen there for the same handover and by the same producer the settlement itself derives them from
  (`workflow/engine/prompt_delivery.py`): a round whose report is the whole of what reached the pull request may not
  record the feedback it answered as read until that report lands, so those readers move in the write that settles it
  and in no other. Every other road answered its feedback in something already there — a pushed fix in code, a park in
  a notice a human is being asked to read — so those settle in the tick and the record's own pairs re-apply as a
  no-op. A PARK settles them in its own write rather than in a caller's behind it, because the park is durable the
  moment it is taken and one left over feedback that still reads as unanswered is one the next tick resumes the
  developer over again.

  Both groups also carry what the record **supersedes**. A record minted while an unsettled one is on the comment
  replaces it — the delivery by the write that records the new one, the transaction by the binding behind it — and
  nothing an unsettled record owes has been written anywhere, so its round, its bookmarks and its readers would go
  with it. They are joined onto the new record instead, the outstanding transaction first, then any unbound
  delivery, then this run's own pair, so a field two of them name keeps the newest reading of it (each was computed
  against a comment the superseded record wrote nothing to, and the watermarks ratchet forward regardless). The road
  that reaches this is a requirements edit landing while a report-only fix round's session is out: the transaction
  refuses to publish against requirements the run never saw, the drift resume that edit earns writes the report that
  supersedes it, and without the join that report would settle leaving `review_round` unspent,
  `pending_fix_reviewer_comment_id` still set for a `/orchestrator continue` to replay stale reviewer feedback from,
  and the human reply the fix round already answered reading as fresh feedback.

  It names no pull request,
  no branch and no commit, because none of those is settled until the code is published: the write that binds the
  record adds them as the subject below and drops the delivery in the same write. The revision is minted one past
  every report the issue has already recorded — the settled one, any transaction still outstanding, and any delivery
  still waiting to be bound — because the receipt is spelled from it and a retry finds its own comment by that
  receipt. That last one is the
  road a park answers: the reply it earns writes a fresh report over the delivery standing there, and minted at its
  revision the replacement would carry the receipt that record already carries.

  Both writes — the record, and the binding that exchanges it — are guarded commits
  (`workflow/engine/report_commits.py`, over the [guarded commit](#pinned-state) above). Recording is decided on every
  report record its revision was minted past and its superseded bookkeeping carried from, and on the requirements
  baseline it may be stamped with; it owns the delivery and the park and debt flags a recorded report retires. Binding
  is decided on the three report records and on the fields the publication it is bound to was resolved from —
  `pr_number`, `branch`, and the code-publication receipt — and owns the two records it swaps, so a pull request or
  receipt another road repointed since binds nothing and publishes nothing. Each is captured over the reading its tick
  last synced with, so what the tick staged since — a run's usage and session, a park a reply answered — rides the
  write, and a usage total or ledger the tick moved that another road left in no shape the two moves join is refused as
  an owned conflict rather than written over. The room either write needs is decided by its own validator, carried on
  the guard and asked of the very candidate the commit sends over the reading its edit lands on — never of the comment
  the tick read, which only refuses a record whose own reading fails or which no comment could carry — so room another
  road spent since refuses there, before the push or the post, and room it gave back is room: as a `CommentOverflow` the
  park explains for a record, and as the crowded comment the next tick retries for a binding. A comment that will not
  read, was replaced, or moved under the decision — another report record written, the baseline or the publication
  moved, a flag the write retires or a field the tick staged moved another way, before the commit read it or between
  that reading and the edit — refuses the write with nothing written, nothing published and nothing parked, and the
  tick's state is withheld from every whole-state write the stage takes behind the refusal; the tick ends and the next
  one decides afresh. A write GitHub took and never confirmed ends the tick the same way, its state left as it was and
  withheld, since nobody can say whether it landed or what another road wrote past it: where it landed, the next tick
  binds that record, or publishes that transaction without binding it again — no second developer run, and no second
  revision. The `report_undeliverable` park a refused record or binding takes is a guarded commit as well, prepared
  before its notice is posted with the ledger entry and the watermark that notice writes reserved at their widest — the
  entry reserved on the ledger as merged with the fresh comment's, under an id neither side already holds — so a park
  the comment cannot carry posts nothing; a binding's park is decided on the publication too, so one judged against
  a pull request or receipt another road has since repointed posts and parks nothing. One
  prepared and then refused — the comment moved before its edit, or the edit refused — leaves its notice on the thread
  with nothing recorded, and the road that took it parks again on a later tick.

  Accepting that record also RESERVES what the transaction bound from it will cost this comment, at the width every
  member of a subject is recorded at. The binding happens after the push, so a record accepted against its own
  write alone could be refused once the code is out — which is the one moment nothing can be done about it, since
  the session that wrote the report has ended. A verification is reserved against its own location's pull request
  instead of the widest number, because that is the number its transaction has to be about and any other is a
  refusal no width could prevent. The BRANCH is reserved at the width the comment renders rather than at the count
  its reader bounds: the reader counts codepoints and admits every one a JSON escape can spell, while the comment is
  measured in the characters that escape produces — one outside the BMP is a surrogate pair, twelve characters for
  one — so a ref bounded at 256 can occupy 3072, and a ref of 256 emoji is one git makes without complaint. What is
  measured is the comment the BINDING leaves rather than the one in hand:
  that write exchanges the two records, so a delivery already standing there is room the transaction gets to spend,
  and a comment that has never carried one still ends up holding the `null` the drop writes. The record's own write
  is measured in four worlds beside that reservation — this comment, and this comment carrying the
  code-publication receipt, the stale-approval hand-back, or both — because what stands between the record and the
  binding is the push and, on the `in_review` drift road, the hand-back behind it, and both write here. The
  hand-back is charged only to the route the record names, since `in_review` is the only stage that makes one.
  Those are worlds the reservation above never measures: the delivery added to everything the issue already
  carries, a transaction an earlier publication left outstanding included. The binding also holds
  the subject to the requirements revision the delivery froze; a subject restating it differently is refused with
  nothing staged, since a transaction bound to another revision would claim the report answers content the run
  never saw, and it is held to the record the comment CARRIES: a report the delivery field has none for, one
  nothing can read, and one a later report has already replaced are each refused, since the write drops whatever is
  there and binding on any of them would replace a finished run's report with a value the comment never held. Five
  roads on the recording side park the issue under `report_undeliverable`: a report this workflow cannot write down
  at all, a completed run that handed over no usable report to write, a recovery that republishes committed
  work no recorded report describes, a round reporting with NO commit over a head nothing could prove the pull
  request to be standing on, and — on `workflow:fixing` — a round that committed and did not FINISH, a reply that
  reached for the report contract and missed, a round that committed over a report an earlier tick recorded, and
  the wait a report no road left on the issue can move earns. The recovery beside them
  (`workflow/stages/fixing/report_recovery.py`) adds two of its own, and one of them is the
  only road here that does NOT leave its record where it found it: a record nobody can read parks untouched, for
  whoever repairs or abandons it, while a checkout this host proves it cannot publish from — gone, or carrying
  uncommitted changes — parks with the frozen pairs that record held applied and the record itself RELEASED, since
  left there, restoring or cleaning the checkout would publish the report and send the issue to review, which is the
  decision the notice exists to put in front of a human. The debt outlives that release, so the review stays held
  and the reply still brings a report. The release rides that park's own guarded commit, owning the delivery and the
  transaction it superseded besides the park's fields and decided on every report record the tick read, so a newer
  record another road wrote meanwhile is never released with the one the tick found — no notice is posted and
  nothing dropped — and a release that did not land, or landed unconfirmed, ends the tick, the next one finding
  whatever the comment then carries. A reading nobody could TAKE is on neither list — an unreadable tree, a head
  that would not resolve, a pull request this poll could not fetch — and buys nothing: nothing published, nothing
  released, no notice, and the poll behind it asks again. A binding REFUSES rather than parks — it
  stages nothing and says which refusal it was — and `report_binding.py` is what answers the refusal: a comment too
  full for the transaction, measured on the tick's reading or on the fresh one, is retried silently on the next call,
  as is a binding whose comment moved under it, since the routes a report still owed lets run are
  what give that room back, while a record no comment would ever hold, a delivery nothing can read, and a
  verification on the very description the publication needs for its closing reference park under the same reason.
  On `workflow:validating` the report hold that keeps the reviewer off an owed report parks under it too, for what no
  retry there settles: a record written against requirements the pinned baseline has moved past, a code-publication
  receipt naming no publication of this pull request, a checkout on a commit the pull request never received, a
  checkout that has picked up loose work or moved off the commit a bound transaction is about, a report the thread
  has moved out of reach — a comment of ours somebody
  edited, or a verified location gone, changed, or written by an author this deployment does not trust — and a
  `developer_report_owed` debt no record of this issue's describes — a run that committed and reported nothing, and
  one whose commits any record left by an EARLIER run predates. An `in_review`
  issue still owing any of these is handed back to `workflow:validating` before that stage does anything else,
  since the approval it stands on is stale.
  On every one of them the record that exists is left exactly as it stands.

  `developer_report_owed` is the debt those parks leave, a bare `true` written beside the reason by every road that
  parks under `report_undeliverable` — and by the drift resume's tree park, which names the loose files rather than the
  report though the run it refused to record had written one, and by the rewritten-head report refresh beside the
  agent-failure park `_on_question` classifies for a run that brought no report, since the reply to that question,
  silent exit, or unfinished command is the report the debt is owed. The flags are single, so any later park — a
  resumed run that times out, a question — replaces `park_reason`, and without the flag the report that finally comes
  back would read as an ordinary reply on an issue owing nothing. `owes_a_report` reads it beside the two records and
  the reason -- the four published as `report_delivery.REPORT_DEBT`, which every guarded verification-evidence write is
  held to, since a review subject stands only while no report is owed, so a debt another road records or pays under one
  stands it down -- and the write that records a delivered report retires it with the reason — as does the settlement
  that puts a report
  on the pull request, which retires the `report_undeliverable` park itself where that is the park it answers: a
  condition a human REPAIRS rather than replies to (an edited report restored, a checkout cleaned) leaves nothing else
  to end the wait, and a debt outliving the settlement would hold the reviewer over a report the pull request carries.
  Additive: an issue without it owes nothing on that account, and an older park carrying the reason alone still reads
  as a debt and is given the flag, with no second notice, the next time a road meets that park still standing — which
  is a notice withheld rather than a write: whatever the road staged beside the flag, a record it released among it,
  rides that write, and skipping it would leave the caller told the tick ended over a comment that never changed.

  `developer_report_unreported_work` is the narrower fact beside it: a run committed work and no record of
  this issue's describes it. Every road that holds such work writes it — one whose report this build cannot record,
  one that handed over no usable report at all, one whose run never finished, a commit an earlier run stranded that
  the reply in hand does not describe, the timeout retry that publishes a commit the run it is finishing was
  killed before reporting, and the rewritten-head report refresh whose run committed when it was asked for a report
  alone — and only a report recorded afterwards retires it, since only a
  report written over the branch as it stands describes those commits. The debt alone cannot say this, because a
  record an EARLIER run left is still a record: a reply that publishes the newer commits under it would settle a
  report of work it was written before, and the reviewer would read it as the account of the whole branch. So while
  this flag stands, a reply that brings no report publishes nothing and the review is held for the one the work is
  missing — and it answers that on its own, ahead of the debt it is normally written beside, so the answer cannot
  turn on which key an owner cleared first. A settlement retires nothing at all while it stands, for the same
  reason: an earlier transaction can settle long after those commits were made, and taking the debt, the park
  asking for their report, and the budget their publication is owed off with it would hand the next reply exactly
  the publication this flag exists to stop. Additive: an issue without it has no undescribed commits on that
  account.

  `developer_report_owed_round_reset` is the fresh review budget an `in_review` requirements edit earned, written
  beside the debt where the publication that edit produced is still owed as the hand-back moves the label. That stage
  resets `review_round` before it relabels, because the approval was earned against requirements that are gone — and a
  publication still owed then lands on `workflow:validating`, where a fix reaching the pull request spends a round.
  The flag is what keeps the delayed road from spending the budget that reset just made, which would leave an edit
  answered a tick late one round short of the same edit answered at once. A resume that answered the edit with
  nothing at all earns it too, since what the hand-back is for is the publication that reply will bring. Every road
  that lands that publication reads it: the resume answering the park, and the silent retry that finishes a push the
  park was delaying. Additive, a bare `true` while it stands, and retired by whatever ends the publication it is
  about. The settlement that ends the debt is one. The drift outcome that answers the edit is another, but only
  once that publication has actually happened: an `ACK:` leaving a commit withheld for the report it owes publishes
  nothing, and dropping the record there would charge the reply that finally publishes a round the edit had already
  bought back. A transient retry that clears its park is the third, and it drops the record with the park: that
  retry either pushed the publication or read the branch and found none, so nothing is left for the budget to pay
  for and the next unrelated publication this stage owes would otherwise spend nothing.

  `developer_report_pending` is one publication transaction, written **before the report it carries is published**
  — that ordering is the whole of what makes the publication recoverable. Whether the CODE that report is about is
  out by then belongs to whoever writes the record, and both roads are admitted: a transaction bound from a
  delivery is recorded once a pull request carries the code, since a subject cannot name a pull request that does
  not exist yet, while a transaction recorded ahead of the push is why the code-publication receipt is reserved
  beside it. It carries the receipt
  naming the transaction, the subject it is bound to (repository, pull request, branch, source commit, and the
  requirements revision the developer run was actually handed), the report revision, whether it is owed a
  publication or a verification, the route that produced it, the complete report text or the exact location and
  content revision a verification asserts, the feedback watermarks the run consumed, and the round and bookmark
  fields its route closes. The requirements revision is the one the run was GIVEN and never the one current when
  publication finally lands, so a delayed report cannot be stamped as answering an edit it never saw.

  `developer_report_current` is what the pull request carries now — subject, revision, exact location, and content
  digest — and it outlives every transaction that put one there, so a later reader can tell a report this
  orchestrator published from one a human has edited since. Its `mode` member (`publish` / `verify`) says which road
  settled it, because the digest proves a different thing on each: a verified location IS the text that hashes to
  it, while a published comment is that text under a header, and a comment cut down to the bare text hashes the
  same. It is the one additive member of the record: a settlement written without it reads back with no road and is
  re-read by what its location allows (`workflow/engine/report_settled_reading.py`), while a value that names no
  road is damage like any other — `null` included, since only the member's absence is what an older settlement
  left. A replay holds a settlement to it too (`workflow/engine/report_replay_guards.py`): a record naming one road
  is never the completion of a pending transaction on the other, which parks as a disagreeing handoff with the debt
  intact, and a record without the member is held to the content as it always was. `developer_report_handoff` is
  the receipt that one transaction finished; a replay under the same receipt recognizes its own completed work
  instead of repeating it. Its `under` member is the workflow label the issue was carrying when the settlement
  landed, and nothing reconstructs that afterwards: the reconciliation runs ahead of every handler on every
  non-terminal label, so a transaction can settle somewhere its own route's stage is not looking, and a route whose
  bookkeeping includes a hand-back that stage has to make needs to know whether the stage was ever there. It is read
  off the issue the settlement re-reads rather than off the copy in hand — a human who relabelled while the developer
  ran is invisible there — and fail-closed, since the labels are a lazy read: a settlement that could not take one
  records none, and every reader holds the absence to the stricter answer. Additive like `mode` on the current
  report: absent on a settlement written before the member existed, and damage where it is present and names no
  label, `null` included.
  Both settled records, the watermarks the run consumed, the bookkeeping its route owed, the debt that record left,
  and the drop of the pending record land in ONE durable write, because every split between them is a window a crash
  turns into a second report or a round spent twice. `fixing_round_settled` is REPLACED by that same write rather
  than merely left — retired first, and put back up only where the record's own frozen spends carry it — so the mark
  and the handoff beside it are always about one transaction. That write is composed whole before any of it is
  installed, so a settled record its own
  writer refuses lands none of itself rather than dropping the pending record beside a published report.
  It lands as the [guarded commit](#pinned-state) above (`workflow/engine/report_settling.py`), over the comment read
  afresh behind the post and the re-reads: it owns exactly those fields — the two settled records, the pending record,
  the watermarks and bookkeeping pairs this record froze, `fixing_round_settled`, `developer_report_owed`,
  `developer_report_owed_round_reset`, and `park_reason` / `awaiting_human` where the park is `report_undeliverable` —
  and is decided on every report record, the handoff, the debt, the park, `developer_report_unreported_work`, and the
  pull request, branch and code-publication receipt the evidence was proved against. So another domain's evidence or
  verdict and a usage total written meanwhile stay as they were written, a watermark and the comment-id ledger keep
  both roads' moves, and a newer record, a repointed pull request or receipt, a park, or a field it writes moved
  another way refuses it with nothing written. Its final candidate is held to the room every write behind it needs —
  the reviewer round, and the fixing hand-back where the record raises `fixing_round_settled` — measured with the two
  settled records as they land, so a comment another road filled while the report was posted refuses it with the
  pending record kept rather than taking the room the hand-back needs. The report is on the pull request by then, so a
  refused or unconfirmed commit holds the tick with the tick's state withheld, and a later tick settles from what the
  comment carries: a transaction still owed finds its report by its receipt rather than posting it again, and one
  whose settlement landed after all is owed nothing. Every other road that leaves the transaction owed once its post
  or re-read has gone out — an answer lost, a report edited, gone or untrusted, the requirements moved under it —
  reads the comment once more before it answers: one another road wrote meanwhile withholds the tick's state and
  holds the tick, so nothing behind it writes that state back over the other road's evidence, verdict or newer
  record, and one still reading as the tick read it leaves that road's own answer, hold or stand down, as it was.

  Every field is read fail-closed and every group all-or-nothing, so a record short of a member reads as no record,
  the two members named below excepted.
  Both a pending verification's location and the settled `developer_report_current` location are bound to their own
  subject's pull request, since a location is exact in both halves and still names a place anywhere in the
  repository — a subject naming one pull request beside a location on another would say the report this pull
  request carries is somewhere else. Every optional-looking field is written on *every* record, so its absence is
  damage rather than a default: an empty watermark or bookkeeping array is "nothing owed" while an absent or `null`
  one is a truncation, and a location without its comment field is a truncation while the `null` spelled there is
  the description. The legacy-safe absences are the whole additive record and one member of each settled record:
  `developer_report_current` without `mode`, which is what a settlement written before that member existed carries
  and reads back with no road, and `developer_report_handoff` without `under`, which is the same settlement read
  back as one nobody can place. Both are held to the stricter answer rather than guessed at, and in both a value
  that is present and names none — `null` included — is damage like any other member. Because
  a record's absence is also what an issue with nothing recorded reads as, presence is asked apart from meaning: an
  issue that CLAIMS a record nobody can describe is the one answer a guard may not confuse with an issue that owes
  none.

  What counts as a claim differs across the four, and it follows from which of them is ever cleared.
  `developer_report_delivery` is cleared by the write that binds it — and by nothing else, since a refusal that
  dropped it would lose the only copy of what the run reported — and `developer_report_pending` is cleared on every
  settlement. Both keep the key and hold `null`, so `null` on either is its ordinary resting state and an absence,
  and only a payload that is present and is not an object is a claim. What a `report_undeliverable` notice offers
  is a reply rather than a field to clear: it resumes the session, and the report that session writes is the one
  this workflow records — over the delivery standing there, where one is — and publishes. A notice refusing a report
  for the comment's room asks for room freed before that reply, and these two records are not where it comes from:
  clearing either drops a report the run that wrote it cannot write again.
  Nothing clears either settled record; a settlement REPLACES one. So `developer_report_current` and
  `developer_report_handoff` are claimed by the presence of their key alone, `null` included: a `null` there is a
  truncated write or a hand edit, and read as an absence it would be silently replaced after the next report is
  posted, or published over a second time because the handoff proving the first could not be seen.

  The watermark and bookkeeping pairs are bounded per key and per shape, so a hand-edited record cannot write into
  any field the workflow has, and the watermarks are ratcheted forward only. Every number is bounded too — each one
  is copied into the records a settlement adds, and a watermark carries a second reason besides: a boundary past
  every id GitHub will issue is one no later comment can pass, so a forward-only ratchet moved there would read
  every human reply for the rest of the issue's life as already answered. Recorded text has to be text UTF-8 can
  carry, which is not what `str` can hold: the comment is JSON, and JSON spells a lone surrogate as an escape that
  round-trips here and raises where the report is hashed. A record is refused where it is declared — not truncated —
  when it quotes a receipt marker of this orchestrator's, when this owner's own reader would not hand it back
  unchanged, or when either the comment it writes or the one its settlement would leave is past what GitHub
  accepts. That second measurement is taken here rather than at settlement, because by then the report is already
  on the thread and a refused write would leave a published comment beside a record still claiming it is owed. It
  measures the WHOLE settling write — the watermarks it advances, the bookkeeping it closes, the two records it
  adds, and the `orchestrator_comment_ids` entry that publishing the report leaves between the two — replayed
  through the owners that perform it rather than allowed for by a margin. That ledger entry is the one piece that
  does not happen in the settlement itself, and it is the reason a transaction accepted at the ceiling without it
  settles past the ceiling: the write that fails then fails after the report is already on the thread, and goes on
  failing identically for the rest of the issue's life. The entry is reserved under an id the ledger does not
  already hold, because the writer that records a comment is idempotent — reserving one already there reserves
  nothing, while the publication lands under an id of its own and adds an entry anyway. The report's reviewer
  round writes past the settlement on the same comment too — `review_agent` and `review_subject` ahead of its spawn,
  the `agent_runs_used` / `agent_run_reservation` / `agent_run_fingerprint` charge its launch takes,
  `last_review_session_id`, `last_review_at` and `review_returned_subject` on its return, and `review_approved_subject`
  when it approves — so the
  measurement replays that whole round through the validating stage's own writers, each at its widest
  (`stages/validating/review_records.py`), and a report is never accepted into a comment its own reviewer could not
  then write to. The usage meters that return folds are the one part left out: running totals every agent run
  folds, already on the comment from the developer run whose report it is wherever that run's usage parsed.

  **The same measurement is taken again at publication**, against the comment as it stands then, and that is not
  belt-and-braces: it is the only one that can be right. A transaction the dispatcher's reconciliation cannot
  complete *stands down* on purpose, so the routes behind it run — and a park taken, a retry notice recorded, a
  ledger entry added, a watermark advanced all write to this same comment. What the record reserved can be spent by
  work entitled to spend it, leaving a comment GitHub still accepts and a settlement that no longer fits on top of
  it. Refused before the post, nothing has happened and a later tick settles once the room comes back; refused at
  the write, the report is already on the pull request. It is taken as the settlement's own guarded commit PREPARED
  over the comment read afresh before the post, everything the settlement owes staged on it and this measurement
  asked of that very candidate — so room another road spent since the tick read the comment refuses the post, room
  it gave back is room, and a record the settlement is decided on that moved meanwhile posts nothing either, holding
  the tick with its state withheld. A refusal for room alone over the comment the tick read stands down. The commit
  behind the post asks it once more over its own final candidate, with the settled records as they land and the
  post's ledger entry already in place rather than reserved again — a measurement never larger than this one over the
  same comment, so a comment nobody else wrote that passed before the post passes again.

  The CODE-PUBLICATION RECEIPT is reserved beside it, in *both* measurements. A transaction can be recorded before
  the commit it reports on is pushed; its evidence then stands down to the publication gate, and that gate writes
  `implementing_published_sha` / `implementing_published_lease` / `implementing_published_pr` onto this same
  comment when it pushes. That write lands between the record and the settlement, so a record accepted without
  room for it leaves the gate's own write refused — or the settlement refused after the report is on the thread.
  It is reserved through the gate's own writer, at the widest every member of that receipt can be recorded at —
  a record cannot know the head a push will replace, and holding the other two to its own values would model a
  receipt narrower than one the gate could write for a commit somebody pushed past it.

  **Both worlds are measured**: the comment as it stands, and the same comment carrying that widest receipt.
  Neither is wider than the other in every field, because the reservation *replaces* what is there — so against a
  receipt already spelled wider than anything this build records (a hand edit, an older binary), the reserved world
  is the smaller of the two, and measuring it alone would accept a record whose own write is past the ceiling the
  moment it lands. Measuring both is what makes the answer "this record fits whatever happens next" rather than
  "it fits one of the things that might". Both settled writers refuse on the same terms: a current report or a
  handoff its own reader would not hand back unchanged is not stored, since a settled record nobody can act on is
  what the issue would carry in place of the one the report it just published deserved.

  A delivery or a transaction refused says WHICH of these it was, to the writer's caller and nowhere else. The
  record's own reading names a report quoting a receipt marker, one past `MAX_REPORT_TEXT`, and every other invalid
  record — a settlement that cannot even be built among them, since nothing was measured — and only a record that
  reads and does not fit is refused for the room (`workflow/engine/report_record_room.py`), naming the comment that
  came out too large: the record's own write, the transaction a delivery is reserved against, or the settlement, with
  whether the receipt or the hand-back was reserved beside it, and its size against the ceiling. No pinned field
  records the reason: the comment carries a record or does not. A refused DELIVERY's reason reaches a human through
  the `report_undeliverable` park its caller takes, whose notice and log line say the same thing in words
  (`workflow/engine/report_refusal_notices.py`), and it is gone once that park is announced.

  The watermark fields a record may advance are not spelled in this domain at all: they are read off
  `workflow/engine/prompt_delivery.py`, the owner that produces the consumed pairs a transaction freezes. Two lists
  would be two lists, and a drifted one fails silently at exactly the wrong moment — a producer surface the record
  reader had never heard of makes one member unreadable, which refuses the whole group, which holds a transaction
  whose report is written and whose feedback is already answered. What each field may HOLD is still bounded here,
  because a key names a shape this domain has to prove.
- **Rewritten-head report debt.** `developer_report_rewrite_debt` is the report a pull request is owed because this
  orchestrator rewrote its head (`workflow/engine/report_rewrite_debt.py`): `pr`, `branch`, `previous_head` -- the head
  the rewrite replaced, the first one across a retargeting, which is the head the settled report is about -- and
  `rewritten_head`, the exact commit the rewrite published. It is what lets a rebase this orchestrator made wait for a
  report of the head it published instead of parking for a human because `developer_report_current` still names the head
  before it. Additive: an issue without the key owes no rewrite a report, and `null` is what a paid debt leaves, so only
  a payload that is present and not `null` is a claim. The reader takes the record whole -- exactly those four members,
  the pull request and branch in the shape a report subject's are read in, both heads whole commit ids, and two heads
  that differ -- and anything else is a claim nobody can describe: `carries_rewrite_debt` still reports it, and no
  reader takes it for either head.

  A later rewrite of the head the debt names RETARGETS it onto the head that rewrite published and keeps
  `previous_head`, so repeated base advances leave one debt naming the latest head; a rewrite back onto `previous_head`
  is refused there, since the settled report covers the head the pull request returns to and the validating hold pays
  the standing debt. Where a report of the head the debt names has settled since, that report paid the debt, and the
  later rewrite's own debt takes its place, naming the head the settled report is about -- a rewrite back onto
  `previous_head` included, since the settled report no longer covers it. Replays are known by the head a rewrite
  PUBLISHED: a rewrite onto the head the claim already names, on its pull request and branch, leaves the claim as it is
  whatever head it says it replaced, since the claim already records that head as this orchestrator's and a replay moves
  nothing the settled report is about. A rewrite of any other head onto one the claim does not name, of another pull
  request or branch, or over a claim nobody can read is refused and leaves the claim as it stands, and a record that
  would not read back as written, or that the comment has no room for, is not staged.

  While a claim stands, readable or not, the dispatcher holds the roads past an approval -- `workflow:documenting` and
  `in_review` ([the rewritten-head report debt](delivery-stages.md#the-rewritten-head-report-debt-every-dispatch)) --
  and lets `workflow:validating` run. Its report hold, once no other report is owed, asks
  `stages/validating/report_refresh.py`. That pays the debt with a report settled about the head the pull request
  stands on, whichever head the claim names or whether it reads at all -- but only one PUBLISHED as a report of its
  own, written against the current `user_content_hash`, and still intact at its location -- writing `null` before the
  reviewer road. A `developer_report_current` in `verify` mode, or with no mode, pays nothing: a verification of the
  report standing when the head was rewritten is that report carried forward, not proof it describes the new head.
  Where a readable claim names the pinned pull request and the branch the issue pins, the pull request stands on
  `rewritten_head`, and the settled report is about `previous_head` or about `rewritten_head` without paying
  (`RewriteDebt.owes_a_refresh`), the hold keeps the reviewer off and resumes the developer for a fresh report of
  `rewritten_head` -- recorded as `developer_report_delivery`, bound, published, and settled like every other report,
  so the next tick finds it paid; a run that brings none parks with `developer_report_owed` so a reply's report pays it
  instead. Otherwise it holds nothing, leaving the reviewer road to refuse the stale report as it would with no claim.

  A settled report of the approved commit an approval's squash replaced is of neither head, so it pays nothing, and
  that hold refreshes it too only once a read-only proof (`workflow/engine/report_squash_lineage.py`,
  [approval-squash lineage](delivery-stages.md#the-rewritten-head-report-debt-every-dispatch)) shows from the squash's
  own evidence carry that this orchestrator's squash collapsed it into `previous_head`, the report was written against
  the current `user_content_hash`, and it re-reads intact at its location; otherwise the reviewer road refuses it. The
  claim's fields, their meanings, and its retargeting are unchanged, and `developer_report_current` keeps the commit
  it was written about until the fresh report settles over it.

  `workflow:resolving_conflict` records the claim for every head its own push rewrites -- a clean rebase, a
  resolution the dev finished one with, and a recovered push (`stages/conflicts/report_debt.py`) -- and reads it
  off the code-publication receipt that push left: `implementing_published_lease` is `previous_head` and
  `implementing_published_sha` is `rewritten_head`, on the pinned pull request, or nothing is recorded. It goes down
  in its own write ahead of the relabel to `workflow:validating`, and a round a crash cut short between its push and
  that relabel records it from the same receipt when the settled round is finished (**Conflict rounds** above) -- a
  crash before the gate's receipt write included, since the approval-debt reconciliation writes that receipt against
  the approval's original `late_approved_lease`, with the round's `late_spends` beside it; for a push an adjudication
  accepted, the settlement's retry writes it against the head the verdict was measured over. A proved debt the comment
  has no room for holds the round instead of handing it on: it parks `unrecorded_report_debt`, a reason no reply
  answers, and every later tick tries the write again before anything else. A
  recovered push that lands still behind base records its debt at once, and names its head as
  `conflict_preamble_sha` in the gate's write so a tick after a crash, or after an adjudication publishes it, records
  the debt from that. A no-op rebase, a failed push, and a body edit's commit record none, and a push the size gate
  held records its debt only once the tick behind its adjudication's publication reads one of those two back.

  The per-tick base refresh records the claim for each clean auto rebase whose push lands, before it clears its attempt
  or routes to `workflow:validating`, and its crash recovery records the same one on every road that finishes a landed
  head ([Base refresh](#base-refresh)); a rebase that lands nothing records nothing and leaves a standing claim as it
  is. Its room is measured on the whole announcement write the debt rides and on the comment as it stands, and a
  proved debt that does not fit either parks `auto_base_rebase_unrecorded_debt` before anything is announced or
  routed, with the attempt left standing for the recovery a reply brings back.

  A replay the size gate handed to an adjudication, and the late generation took over with its attempt retired, records
  the same claim once the authorized settlement publishes it (`stages/decomposition/late_replay_debt.py`): proved by
  that ownership and by the code-publication receipt naming the replay over `late_published_sha` on
  `late_published_pr_number`, in a write of its own before the label hands the head to `workflow:validating` -- the
  write that also puts a spent `review_round` back to zero, as the finish's announcement does. A
  retry after the push landed records it again from the same ownership with no second push, and a proved claim with no
  room parks `late_pr_unreconciled` with the push kept and the generation live, so a later tick records it once room
  is made -- or, where the comment has no room for that park either, posts and writes nothing and leaves the same
  ownership and receipt for the next tick to ask again from.
- **HITL park.** `awaiting_human`, `last_action_comment_id`, `park_reason`. `_park_awaiting_human` (on the same
  `workflow/engine/guards.py` owner as the two run refusals) sets
  `awaiting_human=True` and clears `park_reason` to `None`; a handler that needs the reason to survive into the next
  tick explicitly re-sets it after the park call. `last_action_comment_id` is stamped at the id of the notice that
  call POSTED, not at whatever the thread ends on once it has: the two differ only when a human replies between the
  post and the write, and on a park whose whole point is waiting for a reply, reading the tip there is the answer
  being thrown away by the question. A post this call could not identify moves the mark **nowhere** — reading the
  tip for one nothing named would cross whatever else stands on the thread, while our own unrecorded sentence carries
  the marker with no ledger entry behind it, so every prompt reading refuses it as forged.

  The parks that FOLLOW an agent run read the field differently, through `engine/park_watermarks.py`, because a human
  may have written while the agent was out: the walk starts at whatever the resume settled and advances through the
  unbroken run of comments the `orchestrator_comment_ids` ledger claims (the pinned comment left out by its id),
  stopping at the first it does not. A post the ledger never gained, a thread with no watermark under it, and a thread
  the walk cannot re-read all leave the mark where it is, never the tip, and the last never raises, since the notice
  is already posted and the park still has to be recorded. `_handle_pickup` writes the floor the first run walks from:
  the pickup comment anchors `last_action_comment_id` beside `pickup_comment_id`, because the spawn it opens quotes the
  thread as it stands. EVERY park the `workflow:implementing` and `workflow:validating` handlers take after a run reads
  the field that way — the agent question and checkout refusals call the walk directly, as do the returned-verdict parks
  (`stages/validating/review_parks.py`) behind their own notice -- which a live reviewer round's verdict takes through
  the disposition -- and every other one asks `_park_awaiting_human` for it with
  `bounded=True` (both timeout parks, both push failures, the measurement failure,
  the unauthorized-exemption hold, the checkout-moved refusals, the undeliverable-report park, the squash and verify
  failures, the reviewer timeout and no-VERDICT parks, and the review cap) — and so do the agent-run-limit notice and
  the repair of its lost write, because the launch the circuit refuses is very often one of these resumes. The
  `in_review` unmergeable park asks for it too, and it follows no run: what it follows is that tick's own feedback
  scan and several GitHub round-trips after it, which is the same window by another name. The `fixing` bounce's
  `stranded_unproved` park is the same shape — the scan is at the top of the tick and placing the branch is a fetch,
  so a human writing in between is numbered below the notice posted after them. Where nothing
  is unread the bound IS the notice id, so it is never the worse answer.

  That field doubles as the record that a mention was
  posted: a transient park that later self-recovers reads it back to decide whether it owes the thread a follow-up
  (see [`delivery-stages.md`](delivery-stages.md), **Recovery follow-up**). Park reasons that route via
  `_park_auto_rebase_failure` (`auto_base_rebase_failed` / `auto_base_rebase_dirty` /
  `auto_base_rebase_push_failed` / `auto_base_rebase_unrecorded_debt`) are owned by the per-tick
  base-sync flow — every PR-stage handler short-circuits when `park_reason in _AUTO_REBASE_PARK_REASONS`. A reply to
  one that only asks for the retry is the attempt's, recorded read past `last_action_comment_id` by the write that
  spends it, and a reply that says more is left for whoever reads guidance next; a park of any other reason standing
  beside an anchor is kept through the size gate's route to an adjudication (see [Base refresh](#base-refresh)). The
  exhausted retry budget re-sets `retry_cap` for the same kind of reason — a park nothing can recognize is one the
  next tick re-decides from scratch (see [The retry budget](#the-retry-budget)), and the spent lifetime agent-run
  ledger re-sets `agent_run_limit` for the same reason again, since the dispatcher's hold over it reads that flag and
  nothing else (see the **agent-run-limit park** bullet below). A returned verdict's parks set `reviewer_unverified`
  and `reviewer_unrecorded` in their own write for a reason of their own: neither retries itself, and the reason is
  what hands the reply to a fresh reviewer rather than to the developer, and what the drift check stands down for
  (see the **Returned reviewer verdict** bullet below). `reviewer_usage_limit` is the reviewer-side reason for a
  reviewer its provider's usage limit stopped -- additive, and one no road sets yet, since recognizing that stop on a
  reviewer's result is a separate change; what is defined is how the park is answered. It never retries itself,
  because another poll is no evidence the quota reset, so it is outside `_VALIDATING_TRANSIENT_PARK_REASONS`; it is
  among `_REVIEWER_SIDE_PARK_REASONS`, so the drift check stands down for it; and the one reply that answers it is a
  trusted `/orchestrator continue`. Anything short of that command -- a quiet tick, an outsider's words the trust
  filter takes out, a trusted reply without the command -- holds the park with nothing run, posted, consumed, or
  written, the round, the pull request, the worktree, and the developer session left as they are; the command clears
  it into a fresh reviewer round, never a developer resume (see
  [`delivery-stages.md`](delivery-stages.md#_handle_validating-label-workflowvalidating)). A `park_reason` spelled as
  anything but a word -- a hand edit leaving a list or an object -- names no park the `workflow:validating` awaiting
  and drift routes know, exactly as an unknown word does: a reply to it resumes the developer, and an edit under it
  takes the drift road. A failed
  verify gate's `verify_*` reason is set in the park's own write too, through the funnel a returned verdict's parks
  take (`stages/validating/review_parks.py`): only over the approved subject still standing behind the gate and
  behind the park's notice, and only behind a notice that was identified. A failed squash-on-approval sets
  `squash_failed` in the park's own guarded commit as well (`review_parks.parks_the_failed_squash`), prepared before
  its notice, landing only behind one identified, over the report, `pr_number`, `review_returned_verdict`, and
  `verification_evidence_*` records the squash tail holds -- and, on the approval road, over the approved subject
  standing behind that notice --
  and what reads it back is the recovery that took it: that route retries on every tick and stays silent while its
  own reason stands, so the reason is what tells a notice already on the thread from one to post afresh — and a park
  worded by the size gate behind it, which says its own piece on every reading it cannot take, is held for a human
  rather than re-entered. A pre-session requirements edit over recovered commits re-sets `stale_recovered_work`
  (`stages/implementing/drift_preflight.py`) for a reason of the same shape and one of its own: the edit it refused
  is an edit on every tick after it, so without the reason the refusal would meet its own issue afresh once a poll
  — the same sentence said again, standing in front of the reply it asked for. Recognizing it, the tick says
  nothing and stands down to the awaiting-human resume, which is where that reply is delivered and recorded; it
  supersedes a park standing for anything else, since what the issue waits on now is a decision about those
  commits; and while it stands the quiet `agent_timeout` recovery cannot publish them behind the operator's back,
  since the reason on the park is this one rather than `agent_timeout`. The developer-report reconciliation
  re-sets `report_record_damaged` for a reason of its
  own: the park is the dispatcher's rather than a stage's, so the reason is the only thing that tells a tick whose
  park it is standing over — this owner announces once, holds silently on its own, and retires *only* its own,
  since every other reason belongs to a stage still waiting for what it asked for. Where one of those is already
  standing it takes no park at all and does not hold either, because the route that answers a foreign park is the
  handler behind this guard (see
  [`delivery-stages.md`](delivery-stages.md#the-developer-report-transaction-every-dispatch)).
  The no-feedback bounce re-sets `stranded_unproved` for a reason unlike any of those: that park is waiting on a
  READING rather than on a person. The reason is the only thing that says so, and the parked dispatch reads it back
  to send a quiet poll straight to the bounce with the flags untouched — where the branch is placed again, whatever
  that reading places is published, and the hand-back retires the park in the write that relabels. Cleared on the way
  in instead, a reading that refused again would have to announce itself afresh — the standing park already says
  what a second notice would — and the issue would sit unparked with nothing published in between; filed under any
  of the transient validating reasons, it would dispatch to a recovery that publishes against a record this park has
  none of. A human reply still takes the ordinary resume road.
  `workflow/engine/report_delivery.py` re-sets `report_undeliverable` for a reason of a fourth kind: the roads on the
  recording side that take it — a report this build cannot record, a completed run that handed over none at all,
  and a recovery (the restart shortcut, or a road that republishes a candidate a gate record named) finding
  committed work no recorded report describes — leave no record behind them, so the park is the DEBT as well as the
  notice's bookkeeping. That debt is `developer_report_owed`, set beside the reason and outliving any later park that
  replaces it — a resumed run that times out included — and while either stands the issue reads as still owing a
  report: the handoff is withheld, and a resumed run that brings a report back publishes the commits already on the
  branch rather than parking as a question. The binding in `report_binding.py` and the description verdict in
  `stages/implementing/pr_description.py` take the same park after a push, for a report that cannot be bound and a
  description that does not close the issue and name the session — which no owner rewrites, so the notice quotes the
  two lines for a human to put there — and `stages/implementing/report_handoff.py` takes it for a debt no retry can
  pay and a settled report that no longer stands, though never behind a binding or settlement that did not land, or a
  post that left the report owed while another road wrote the comment, whose withheld state could record no park. It
  is announced once while it stands, retired the moment a report IS recorded or a settlement carries one onto the
  pull request, and spent by the publication handoff beside the agent timeout's,
  since reaching that line means the report the park was about has reached the pull request. The late
  size gate re-sets its own reasons for the same kind of reason: `late_measurement_failed`,
  `late_candidate_moved`, `late_unauthorized_exemption`, `late_evidence_missing`, `late_plan_pr_hold_failed`,
  `late_generation_incomplete`, `late_worktree_missing`, `late_worktree_mutated`, `late_adjudicator_timeout`,
  `late_manifest_invalid`, `late_result_unrecordable`, `late_owner_unreadable`, `late_pr_unreconciled`,
  `late_snapshot_failed`, `late_children_failed`, `late_supersession_failed`, `late_content_drift`,
  `late_revision_dirty`, `late_revision_unmeasured`, `late_revision_unanswered`, `late_question`, and
  `late_single_decision` — see [the late run](#the-late-run) for which of them the next attempt
  retires. A late tick can also hand the issue back
  under the shared `retry_cap`, which is not one of its own: the adjudication is charged to the same per-issue spawn
  budget every other agent run is, and a refusal there means the issue's day of tokens is spent rather than anything
  about its candidate. It is staged through the same late owner all the same, so the generation and the hold ride
  its write, and it is answered where every other `retry_cap` park is. `late_measurement_failed` is the only one
  of them taken outside `workflow:decomposing`, because it is the gate's own and the gate runs before any
  adjudication exists — under `workflow:implementing` where the push would open the pull request, and under any of
  the five states that push onto one the remote already carries. It is answered wherever it was taken, one step
  ahead of the generic continue
  classifier, since a content-free `/orchestrator continue` on it means "take the reading again" rather than the
  guidance a park needing a real answer would be refused for. While it stands, a fresh batch of nothing but bare
  continues is that road's alone (`late_measurement_reply._reserved_for_the_measurement_park`), and both roads
  behind it hand the whole tick back rather than spending one: each reads the thread again after the road above
  it returned, so a
  command landing in either window is in its batch and in nobody else's — refused and consumed past its own refusal
  by the classifier, or fed to a developer as guidance by the resume. Deferred entire, the next poll reads the same
  batch and re-measures the pair on it. The reservation is asked of the replies a resume would deliver
  (`implementing/parked_replies.py`), since that is the read the retry itself takes: asked of any other batch, a tick
  would defer what the road it deferred to then refuses. It is also the one of them a tick can retire with no
  answer at all, and under a label it is never taken on: a park standing over a record whose split has already
  become children is the
  reconciliation's own false positive — what a settled split keeps the publication group for is the releases and the
  branch delete its umbrella still owes, not a reading anybody is waiting on — so the guard clears it under
  `workflow:umbrella` and lets that handler run (see
  [`delivery-stages.md`](delivery-stages.md#the-size-gate-on-a-published-pull-request-every-push-onto-an-open-pr)).
  `late_candidate_moved` is the second taken outside the
  adjudication, and the guard that takes it is `checkout_guards` — one owner for the initial publication and every
  gated push rather than a pair of readings worded on each road: the checkout is not the one the gate approved, so
  nothing is pushed and the issue is not handed on. It reaches the same five states
  for the same reason — every gated push proves its checkout again on the far side of the effect, not just the one
  that opens the pull request. Two readings answer for "the checkout", because the head answers
  only half of what it means. A head somewhere else is one. A tree carrying work no push would publish — or one
  `git status` could not report on, which is not a clean tree but a reading that never happened — is the other, and
  it is the half that can be true with the head never having moved, so every proof about the commit passes over it.
  Both are asked before the push and again once the pull request is open. It has a reason of its own because the
  remedy is neither a retry nor a re-measurement — every stage past the handoff works from that checkout and none of
  them measures again, so what it asks for is the worktree back on the approved commit and carrying nothing else,
  and a worktree deliberately left on the descendant is measured as the fresh candidate it is on the next run. The
  same reason covers the pre-spawn refusal one step earlier: an approved commit this host
  cannot show at all — the checkout was rebuilt from the base or the plan pull request on a replacement machine — is
  the same ask with nothing to compare against, so neither the recovered-worktree shortcut nor a fresh developer run
  is allowed to proceed past it. It is also the one park answered by something other than a comment, and
  `checkout_recovery` is what answers it: the approved commit is recorded as `late_approved_sha`, every tick asks the
  checkout one local `rev-parse` against it and one `git status` around it, and a checkout put back — on that commit,
  with nothing loose beside it — publishes on the next poll with nothing re-run and no agent spawned. Both questions
  are asked, or the recovery would republish into the very refusal the park was taken on and post a fresh notice
  every poll for a checkout that has not changed.
  That record is what makes
  the answer possible at all — the generation is retired ahead of the effects it licenses, so once the approval lands
  nothing else on the issue still names the commit — and the read is silent, so an operator who leaves the checkout
  where it is is not told the same thing once a tick.

  `late_unauthorized_exemption` is the third taken outside the adjudication, and it is the one owed a DECISION
  rather than a reading or a look at a checkout. `late_exempt_sha` records that an ADJUDICATOR ruled a change one
  coherent whole, which is an agent's answer, and the `late_override_*` group beside it records the operator who
  read the change and agreed to publish past the ceiling. Only the two together are a bypass, so a candidate the
  first names alone — an older build's automatic exemption, or one whose authorization was hand-edited or
  half-written — is measured like any other: at or below the ceiling it publishes on its count, and past it this
  park holds it. It is a HOLD rather than a route back to `workflow:decomposing`, deliberately: the change has
  already been ruled one change, so re-adjudicating it would pay for a second agent over an answered question and
  risk a `split` cutting children out of work somebody decided ships whole. Nothing is deleted, migrated, or
  repaired to take it — the exemption, its identity, the approval naming the commit a push is owed for, and every
  other field are left exactly as found, since the record is what an authorization would be checked against.

  What it does **not** make durable is the count, and that is the difference between it and an adjudication. A
  generation carrying a reading past its ceiling is what this workflow means by *an adjudication in flight*: the
  dispatcher restores `workflow:decomposing` over one before any stage sees the issue, the coordinator owns every
  later tick, and a fresh adjudicator is paid for. So what stays on the comment is the pair the freeze recorded and
  nothing else, and the reading is re-taken by the tick that acts — which is the tick whose terms an authorization
  has to be written from anyway. Left durable, the park would be relabelled out from under itself on the very next
  poll and nothing could ever answer it.

  `late_exempt_sha` on its own is exactly what this park doubts, so the size gate never reads it as *already
  decided*: it is asked as a pair with the `late_override_*` group beside it, and a commit only the exemption names
  goes to the ordinary cumulative reading. `implementing/late_authority.py` is where the two are asked together,
  and a candidate it calls exempt-but-unauthorized is handed to `implementing/late_consent.py`, which measures it
  **afresh** — the pair frozen, the diff counted, the ceiling read on the tick that acts — and publishes only what
  the count or an operator allows.

  The door into that owner is `late_exempt_sha` naming **this very commit** and no authorization this build can
  read back whole standing behind it, which is the whole of what keeps the policy off every other issue. What this
  park collects is one half of the two-part bypass above, so entered without the other half a command alone would
  earn the `late_override_*` group and publish a candidate carrying only the operator's half of the record — the
  one outcome the ceiling exists to catch. The exemption is read through the domain's own object-id
  reader, so an abbreviation, prose, or a shape an older binary wrote is no exemption rather than one nothing can
  compare; and one naming another commit is a ruling a resumed developer's work has moved past, which says nothing
  about the change in hand. Where the door refuses, the tick takes the ordinary road below: the candidate is
  measured like any other and an oversized one is routed to `workflow:decomposing` for
  the adjudication a change with nobody's verdict behind it is owed.

  A candidate the fresh count puts at or below the ceiling is not this
  park's to hold at all — it is not the change anybody was asked about — and goes to the ordinary settlement, which
  takes `awaiting_human` and `park_reason` off on its way into that settlement's **own** durable write. Without
  this the gate would publish a commit over a record still saying a human is holding the issue, and the source
  stage would take its parked road on every poll after — waiting for a reply to a question that tick answered,
  while the approved commit sits unpushed.

  Every poll of a standing park reaches that gate through `implementing/late_recovery.py`, because an issue behind
  it has committed work and no run to dispose: nothing else on the tick would measure the candidate again or say a
  sentence the park still owes, and the spawn below it would buy a second developer run for an implementation the
  first one finished. What a poll costs is what the thread says. A command or an unsaid sentence is answered
  through the fresh reading; guidance is handed to the ordinary resume, which is what the notice on this side of
  publication offers; and a thread nobody has written on is held where it stands without a reading, a request, or
  a word.

  A publication still OWED is answered through that same reading, and it is the one thing here nobody says anything
  about. `late_approved_sha` names a commit this stage decided to push and has not pushed, and the handoff that
  pushes it is what drops it — so an approval still standing is a publication that did not land. What the park says
  decides nothing about that: a candidate the ceiling now lets through has this park and its receipt taken off in
  the settlement's own write, and a push failing after it puts the park back with neither the receipt nor a command
  nor a reading to bring the next poll into the gate. Read off the thread alone, that decided commit sits
  unpublished for as long as the issue lives, with nobody asked for anything and nothing left to ask.

  All three come off **one** look at the thread, and that is a correctness rule rather than a saved request. The
  two questions behind them — is there a command, and has anybody spoken at all — decide opposite things, so a poll
  that asked them separately would answer from two different threads: a command landing between the two reads makes
  the first say *no command* and the second say *somebody spoke*, and the tick classifies a thread whose last word
  IS the command as guidance. Handed to the ordinary resume on that reading, the command is fed to a developer as
  prose, consumed past `last_action_comment_id`, and paid for — and the park goes on standing over a decision
  nothing can ever read again.

  Which commit the park stands over is read **before** the pair in hand is frozen, and that ordering is the whole of
  what makes the announce-once guard mean anything. The freeze persists the candidate being measured, so a record
  read after it answers with that candidate and every park compares equal to itself: a park taken over one commit,
  re-entered after a resumed developer committed another, would hold the new one in silence and the human waiting on
  the issue would never be told about the candidate now in hand.

  What answers it is a trusted whole-comment `/orchestrator authorize-oversized <commit>` naming the parked
  candidate, read by `implementing/late_command.py` and acted on by `late_consent`. It is acted on where a READING
  is rather than at a stage's door, because that is where the terms come from: an operator
  authorizes a change of *this* size against *that* ceiling, so what the command earns is the `late_override_*`
  group written from the gate's own pair, its own count, the ceiling it counted against, the digest recomputed
  between that pair, and the comment it was written in — in one write with the park coming down, the reply being
  consumed, and any sentence the park still owed the thread being dropped. A reading this host cannot fingerprint
  records nothing and leaves everything exactly where it is, which costs a poll rather than a decision.

  The **last** fresh trusted reply is what decides, and reading the batch any other way poisons the park. Guidance
  written after a command outranks it — the safe reading of somebody who asked to publish and then asked for a
  change is the one that publishes nothing — and a command written after guidance is the decision that replaced it.
  A reply that IS the command is answered whatever it goes on to say: the right commit publishes, and one naming
  another commit — or an abbreviation, which names none, since nothing here ever writes one — is answered on the
  thread under a receipt scoped to the reply it answers, and **consumed**. The seams that publish onto a pull
  request the remote already carries move the watermark by no other means, so a reply left standing would be in
  every later batch and would refuse the correct command behind it for as long as the park stood. What that write
  consumes is what the READING got to, then the unbroken run of the orchestrator's OWN comments above it, and no
  further: comment ids ascend, so an
  answer of ours lands above the reply it answers and has to be consumed or the next poll reads the orchestrator's
  own words as a human's fresh guidance — while a watermark taken from the thread's tip *now* would swallow whatever
  landed since the fetch, a retraction of the very command being acted on included, unread and unanswered. Jumping
  straight to that answer's own id would swallow one too, and the likeliest one there is: an operator who reads the
  notice and posts the corrected command between the reading and the sentence refusing the wrong one lands *below*
  that sentence. So the first comment that is not ours ends the walk, whatever it says. The park's own notice moves
  the watermark to the id of the comment it POSTED rather than to whatever the
  thread ends on afterwards, since a reply landing between those two operations is the answer being thrown away by
  the question.

  Which comment is the pinned record is named by its **id** on every read this park takes, never by its marker. The
  marker fallback hides each comment that merely QUOTES it — an operator pasting a payload back to ask about it, a
  retraction written under one — and a reply hidden from this reading is a reply whose author never spoke: the stale
  command beneath it becomes the last word and publishes on consent that had been withdrawn. The consumption walk
  names it for the same reason one step over, since a reply it stepped past would be consumed unread.

  That record is also **dropped** from the one read that asks whether a sentence of ours already landed, and leaving
  it in is how the park silences itself. A receipt is a field on the record before it is a sentence on the thread,
  and [`pinned_state_body`](#pinned-state) writes a record as its own unescaped payload wherever escaping the
  comment terminator would push the write past GitHub's body ceiling — losing that write being the worse trade,
  since the record is what a later tick reads. On exactly those issues the receipt appears verbatim in the pinned
  comment, under this orchestrator's own login. Read there, every sentence a dying tick recorded and never said
  reads as one already said: the notice a human is waiting for is never posted, and a command this park may not act
  on is consumed with no answer on the thread at all.

  Our own comments are dropped from the reading, and being ours is **proved** by `orchestrator_comment_ids` alone —
  the bounded ledger of ids `_post_issue_comment` records, which is a fact about what this process DID. The park
  notice spells the command out ready to copy, so a reader matching on that syntax would mistake our sentences for
  somebody's decision — but the last-reply rule makes dropping a comment the same act as deleting what its author
  said, so over-filtering here is how the park publishes something nobody agreed to: a trusted retraction taken for
  one of ours never happened, and the authorization beneath it becomes the last word.

  Neither of the other two signals may stand in for that ledger, and both are refused rather than taken as a weaker
  second best. The `<!--orchestrator-comment-->` marker is plain text anybody may paste, or quote off a comment of
  ours. And the author login is the shared-PAT hazard this repository names where the ledger itself is defined: the
  token belongs to a human, so a reviewer posting from that account matches it exactly, and a retraction they wrote
  under a quoted marker would read as the orchestrator talking to itself. The two together are no better, since the
  human who shares the login is the one whose consent this park exists to collect. What failing closed costs is a
  comment of ours the ledger cannot vouch for — an id evicted past its bound — staying in the reading, where, not
  being the command, it leaves the park standing and waiting. That is the safe direction for a question only a
  human can answer.

  What guidance is worth differs by the side of publication the park was taken on, and the notice says which it is
  rather than promising one answer everywhere. Before there is a pull request the ordinary resume is still in front
  of the issue: a reply that is not the command falls through `implementing/late_recovery.py` to the road that
  feeds it to the developer. Past one it does not — the debt reconciliation that brings a parked issue back to the
  gate stops the tick ahead of the stage handler on every poll — and the notice taken on that side says the command
  is the only reply that stage reads while the park stands.

  A checkout the publication seam would REFUSE holds this park rather than passing through it. That seam reads the
  tree before any verdict can be recorded and parks under a reason of its own, which on every other road is right
  and here would take `late_unauthorized_exemption` off and move the watermark past the command still standing — so
  the operator who fixes the checkout is asked to authorize the same commit again, on an issue now waiting for a
  different reply. So `late_authorization_recovery` asks the seam's own questions first: the worktree on this host, its
  tree
  provably carrying nothing loose (a reading that established nothing is refused beside a dirty one, since it is no
  evidence of a clean tree), and its head the commit this park is about. None of the three is anybody's decision,
  so each leaves the park, the command and the record exactly as found, and the poll after any of them is fixed
  publishes on the command already written. That is the whole
  of what separates this park from the measurement one beside it, where the answer was a bare continue spent by the
  tick that read it and re-parking under a reason of its own costs nobody anything.

  The HEAD is asked here because a head that has moved is a candidate the exemption does not cover and the override
  does not name, which closes the policy's door and sends it down the ordinary road to be measured and published on
  its own count. An operator who authorized one commit would have another pushed under their command.
  `checkout_recovery._off_the_parked_commit` reads which commit the park is about off the record, the recorded
  override first — the terms a human agreed to, which outlive the generation a failed publication retires — with
  the exemption behind it for a park no authorization has reached yet, and a record naming no commit at all held
  rather than published under.

  Asking here does not settle it, and the commit is CARRIED for that reason. The gate reads the head again for
  itself, and the worktree is writable between the two readings — so the proved commit is named on the recovered
  work handed to the seam, and `late_freeze._moved_off_the_caller` holds that second read to it, refusing before
  anything is persisted or pushed. Every recovery road names the commit it proved, since none of them has a
  developer behind it: the reading that licensed each is about a commit a previous tick recorded, so a head that
  moved mid-tick is not fresh work to measure in its place. On this park the refusal is one more seam outcome that
  published nothing, so the park, its reason and its watermark come back and the operator is not asked twice.

  Asking first cannot close the tree half, because the sharpest case is a RACE: that tree is read again inside the
  seam, and
  everything between the two readings is time something can write in. So the park is put BACK rather than merely
  guarded — `awaiting_human`, `park_reason` and `last_action_comment_id` are held across the seam and restored
  wherever the call did not PUBLISH, whatever it refused for and whatever it left the record saying. The notice
  the seam posted stays on the thread, which is what tells the operator what to fix.

  What the seam left the park flags saying is deliberately not the question, and reading them instead is how this
  park gets dropped. Several of the gate's roads to a held verdict clear those flags without publishing anything —
  a bounded transport miss counting a quiet retry, a close that ended the cycle, a record this commit is
  superseded by — and each leaves the operator still owed the answer they are waiting for. Taken for a
  publication, their question is dropped and their command consumed, and the exemption nobody stands behind
  publishes on the next poll under nobody's authority at all. What answers the question instead is
  `late_held_authorization_park` itself: the write that moves the label out of implementing spends it, so a record
  still carrying it is a call that published nothing.

  The same rule decides which parks a road may retire at all. A reading answers the park a READING was owed,
  so `late_park_retirement._retire_spent_park` ends `late_measurement_failed` and nothing else; this park
  waits on a person, and no reading anybody takes answers a person, so it comes off only where a publication
  under it actually happens — `late_park_retirement._retire_authorized_park`, called past every refusal on
  both of the gate's answers that publish without asking anybody: every road that skips the reading
  altogether, which under a standing park means a commit an override now covers or the bookkeeping owed for
  one its own pull request already stands on, and a fresh count the ceiling lets through, which says no person
  was ever needed for a change this size.

  Where the publication does happen, that same reading is what **spends** the command. `late_consent` consumes the
  reply in the write that records an authorization from it, but two of the gate's roads publish without reading the
  thread at all: a candidate a fresh measurement puts under the ceiling settles on its own count, and one an
  authorization already on the record covers is recognized as decided and pushed without a reading. A command left
  standing on either travels to `validating` with the issue, where the next reader takes it for fresh feedback and
  sends the pull request back for a change — the second developer run over committed work this whole road exists to
  avoid.

  So how far that reading got goes onto the record as `late_held_authorization_command`, in the same write as the
  held park, and is spent by `implementing/handoff.py` — the write that records the published pull request, ahead
  of the `workflow:validating` label. That ordering is the whole of it: past the label nothing spends what this
  stage left behind and implementing never sees the issue again, so a boundary applied on the way out of the seam
  is one a crash in that window loses. Consumed to what the reading LOOKED at and no further, since a tick
  consuming past whatever the tip has become since would swallow a reply posted in between. And never on a call
  that published NOTHING: guidance written between the two readings makes the gate's own reading a park held
  rather than an authorization recorded, and the reply that would end it has to still be there for the poll that
  acts on it. Every road that puts the park back drops the boundary instead of spending it, the poll that comes
  back to a handoff which never returned among them.

  Those three are held on the **record** by `implementing/late_rollback.py` — `late_held_authorization_park`,
  written before the seam is entered and dropped by the write past it — because the seam's own writes are durable
  before that owner gets an answer back.
  `late_consent` records an authorization, clears the park and consumes the reply in one write, and a push failing
  after it parks again under a reason of its own; a rollback kept only in the frame that made it is gone with the
  process, and the poll after a crash finds an issue nobody is waiting on, over a watermark that has swallowed the
  command, with nothing anywhere saying what it had been.

  A record still carrying that field is a call that did NOT publish — the publication handoff spends all three
  in-flight fields in its own durable write ahead of the `workflow:validating` label, the one outcome this park
  never has to be put back from and the one that would otherwise strand them on an issue this stage never sees
  again. So both roads that read it answer the same way and neither asks what the seam meant: the call that came
  back with nothing pushed, and the poll that finds a tick killed halfway through one. Restoring is the safe
  direction on both sides. A park put back over work the seam did publish costs a poll — the gate finds the commit
  already pushed and lets it through without a reading, and the restored command is still the last fresh word, so
  nobody is asked twice — while an issue the seam had already relabelled never reaches this road again at all, the
  dispatcher routing by label. Left off, an operator's decision is consumed and gone.

  Both sentences this park writes — its own notice, and the refusal a wrong command earns — go out before the write
  that records having written them, and a process dying between the two leaves one on the thread with nothing
  saying it is ours. So each carries a **receipt** —
  `<!--orchestrator-unauthorized-exemption-parked:issue=…:candidate=…-->` and
  `<!--orchestrator-unauthorized-exemption-refused:issue=…:read=…-->` — written to
  `late_held_authorization_receipt` *before* the sentence carrying it goes out, then dropped by the write past the
  post.

  Those two are deterministic and they answer exactly one question: whether a sentence still has to be **said**.
  They are no evidence of who said it and are never read as any, because the record is itself a comment on the
  issue — writing one down publishes it, readable before the sentence it names exists, by the human whose consent
  this park collects and from a login they may share with us. Read as authorship, a receipt they wrote themselves
  would have their own retraction deleted from every later reading.

  What can say a comment is ours by its ID is `orchestrator_comment_ids`, and on this park the client
  `late_authorship` lends the publication seam is what writes it. Each comment goes out under a fresh secret, and
  the id GitHub answers with goes into the ledger in a write made the instant that post returns. That id binds the
  record to a comment, and the window it leaves is one API call wide.

  The **receipt** covers that call: a `sha256` written to `late_held_authorization_publication` before the comment
  exists, posted with it as `<!--orchestrator-unauthorized-exemption-publishing:issue=…:proof=…-->` and dropped by
  the write that records the id. One per comment, and the **first** goes down before the seam is entered at all, in
  the same write as `late_held_authorization_park` — the seam can post the moment it is called. Every sentence this
  park writes goes out from *inside* that seam call, `late_consent`'s notice and refusal among them, so all of them
  are recorded as they land.

  What the digest commits to is the **sentence** rather than the sender: the secret *and* the exact body it goes out
  on. That is what makes claiming one safe. A secret is unforgeable only until it is disclosed, and posting the
  sentence discloses it: from that moment a reply quoting our comment carries the secret too, and the login beside
  both is the shared token. Ordering told them apart only while our comment stood — a quote can only follow the
  comment it quotes — and ordering does not survive that comment being **deleted**, which is one tidy-up away on
  any thread where somebody has already quoted it. Bound to the body, their reply answers nothing: a quote carries
  their words as well as ours. What can still answer is a verbatim copy, which carries nobody's words to lose, so
  dropping it from a reading takes nothing from anyone.

  So an outstanding receipt is answered by a **ledger repair**, which `late_recovery` runs ahead of every routing
  decision it makes: one reading of the thread, the earliest comment answering each receipt recorded in
  `orchestrator_comment_ids`, and the receipts dropped. Ahead of the routing because everything downstream asks
  that ledger to tell our own prose from a human's — run after, the park's reading has already handed the tick back
  and the resume has already spawned a developer against our own notice.

  What it repairs is the ledger and never the **watermark**. A watermark moved to our sentence crosses everything
  under it, so an operator who read the notice and wrote the corrected command before that poll ran would have it
  consumed unread and never acted on. A ledger entry moves nothing: it says only that one comment is ours, so the
  next reading drops it and finds whatever a human wrote last.

  The **earliest** comment answering each, and no other. Answering means the body *is* that sentence, word for
  word, so the accidental case — a reviewer on the shared token quoting our notice back — can never be claimed at
  all: their reply carries their words as well as ours. What can still answer is a verbatim copy, and a copy can
  only follow what it copies, so ours is the earlier of the two.

  Where our own comment has been **deleted**, the earliest answer left is that copy and nothing on a thread can
  tell it from ours. Producing one takes reposting a bot notice byte for byte, hidden receipt included, and
  removing the original — not something a reviewer does by accident, and available only to somebody already holding
  the token that authorizes publication outright. The window is the same one API call, and the body a claim is made
  on there carried nobody's words.

  A receipt the thread answers nowhere is dropped with the rest, since nothing here re-says a sentence the seam
  worded — the next handoff words its own. And a receipt is dropped **nowhere else**: the write recording a posted
  id retires the one it went out on, this repair retires whatever a crash left, and the handoff into the
  publication seam retires only the promise it made and never worded a sentence for. One cleared while its sentence
  is still unledgered leaves nothing able to find that comment, and the next poll reads the orchestrator's own park
  notice as somebody asking for a change.

  For `late_held_authorization_receipt` the record and the thread answer different halves of that window, and
  neither answers the other's. The record
  says only that a tick died between recording a sentence and recording having said it; **which side of the post**
  it died on is a question the thread alone can answer. So a park carrying no receipt is answered without a
  request, and a park still carrying one asks the thread: a comment of ours bearing that receipt is a sentence that
  was said, and a receipt no comment bears is one still owed, so the road that owes it says it on this poll. A park
  that reaches the quiet road with a receipt outstanding drops it, rather than re-reading the whole thread on every
  later poll to reach the same answer.

  Both halves of that thread read are asked — the receipt **and** the author — and the direction it fails in is the
  whole point. For **silencing** a sentence it is the safe one: read from anybody, a receipt somebody pasted
  would suppress a notice a human is owed, and read this way the worst a reviewer sharing this token can do by
  quoting our notice back is cost a poll. For **claiming** a comment it is the wrong one, and nothing here does it.
  These receipts are public text, deterministic from an issue and a commit, and the login may be the operator's
  own — so read as proof of authorship, a retraction they wrote under a quoted receipt would be taken for one of
  ours, deleted from every later reading, and the authorization beneath it would become the last word and publish
  on consent that had been withdrawn. Only `orchestrator_comment_ids` says a comment is ours, and no reading of a
  body writes to it. What an unattributed sentence of ours costs instead is standing in the reading as somebody's
  word — which is no command, so the park holds and the operator's next command is still the last fresh reply.

  It costs one thing more, and the client the seam is handed is what pays it. That sentence is the last reply on
  the thread and it is not the command, so the reading hands the tick back and the ordinary resume spawns a
  developer against the orchestrator's own prose. What stops that is the id going into `orchestrator_comment_ids`
  the instant the post returns, rather than whenever the seam gets around to a write of its own.

  Nothing weaker may license a claim on that ledger, and a body read as one least of all: the bare
  `<!--orchestrator-comment-->` is text anybody may paste, the author login is the shared-token hazard above, and a
  reviewer answering our sentence quotes the whole comment back — marker, receipt and all — from that very account.
  The login is no narrowing either, deciding nothing and going stale in ways an id cannot: a rotated credential, or
  an author GitHub did not return, makes our own sentence fail a test the human quoting it passes.

  A digest committed to the **sentence** is what does license it, and only that: the secret and the exact body it
  went out on, so what a carrier proves is not who typed it but that its text is our sentence and nothing else.
  Dropping such a comment from a reading takes nothing from anyone, which is why this claim is safe where a claim
  about authorship never could be.

  `late_held_authorization_receipt` beside it is the one still answered by reading a thread for a body alone, and
  only for the question it was built for — whether a sentence has to be said — which fails toward saying it twice.

  Dropping our own comments is not this park's alone. The generic developer resume drops them too, by the same
  recorded ledger: every park in the implementing stage posts before the write that records posting it, and an
  `ALLOWED_ISSUE_AUTHORS` listing the token's own account trusts every comment it posts, so a notice whose write was
  lost would otherwise reach an agent as somebody asking for a change — and be paid for.

  That resume also **defers its whole tick** where the batch's last fresh reply is the command ending this park
  and the park is standing — an answered `/orchestrator add-agent-runs` read past on both sides, since this park's
  own reading does not count it as a reply. It reads the thread *after* `late_recovery` has classified it and handed
  the tick back, so a command landing between the two reads is in its batch and in nobody else's. Sparing just that one
  reply would not save it: a watermark is one number and the resume is not the last thing to move it, so the run
  it starts parks and that park stamps the thread read to the id of the notice it posts — above the command, which
  is then gone for good. Nothing consumed, nothing is lost: the next poll reads the command as the last fresh word
  and publishes on it, and the guidance underneath was superseded by it anyway. Only where the command is last,
  since guidance written after one is the decision that replaced it. Either way the command itself is in no
  developer prompt while this park stands: demoted, the resume delivers the words written after it, and where those
  are nothing it may deliver — a pasted `<!--orchestrator-comment-->` — nobody is resumed at all.

  The park goes down *before* the notice, so a
  restarted tick finds somebody already waiting behind this candidate rather than an unparked issue to announce all
  over again — over a watermark that would move past whatever the operator wrote in between, taking their decision
  with it.

  What CREATES the park is the reading itself, on both sides of publication: a candidate `late_authority` calls
  exempt-but-unauthorized and the count then puts strictly past `MAX_ADDED_LINES`. A change at or below the ceiling
  — exactly `MAX_ADDED_LINES` included — publishes on its own count and never reaches it, and a commit the pull
  request this call froze is already standing on is never held that way either: the push would move nothing, and
  what would be held back is the bookkeeping behind a publication that has already happened.

  `late_evidence_missing` is the adjudication's counterpart, taken
  under `workflow:decomposing` before the hold or any spawn: the checkout is there and one of the two recorded
  commits is not, so the agent would be shown a `git diff <base>...<candidate>` that cannot resolve and its verdict
  would be an answer about nothing. It asks for the worktree at the recorded commit, never another run.
  `late_owner_unreadable` is the one of them that recovers on its own: it is a GitHub read that failed after the
  agent had already answered, so the retry re-reads rather than re-running anything, and the tick that finds the
  issue readable again posts the same one-time follow-up a transient `validating` park does — before the write
  that clears the park, so a crash between them loses the write and not the sentence. What drives that retry is
  `late_owner_check_pending` on the generation rather than the park itself, which is also why this reason is taken
  only when the issue is not already parked on something a human has to answer. On an issue that already is, the
  notice that other park staged is still said when the reason it stands on is one no later attempt supersedes —
  the four revision and drift parks — since nothing else ever would, and an `awaiting_human` with no sentence
  behind it stands for as long as the read keeps failing.
- **Undelivered park notice.** `late_park_notice` is the `{reason, message}` a late park has recorded and not yet
  said. The flag is durable before the comment is posted — a comment GitHub refuses must not take a finished run's
  result with it — so without this field a refused post leaves an `awaiting_human` nothing can tell from one whose
  comment landed, and every later tick reads the flag, takes the human as told, and says nothing. It is written beside
  the flag on the same write and dropped by the post that discharges it, so a park whose sentence is still owed is
  never counted as a repeat and is re-said at the top of the next eligible tick. It is matched against the standing
  `park_reason` (a notice for a park something has replaced or answered is dropped rather than said), left to the
  fresh attempt for the reasons that attempt supersedes, dropped when the cycle is cancelled, and refused whole —
  loudly — when it would not fit the pinned comment: the reserve beside what that record actually costs, never below
  the standing ceiling (`MAX_NOTICE_COMMENT`) and never past the size a write really fails at. Held to the standing
  ceiling alone it would be refused for a record it did not write — one an older binary recorded against the whole
  outcome budget, or one written before the payload escaped the wrapper's own terminator and so rendering five
  characters longer per `-->` today than on the tick that accepted it, up to the point where the escape itself would
  put the comment past what GitHub takes and the payload goes as it was stored instead — and for a park nothing
  supersedes, a sentence refused for somebody else's record is a human never told. A sentence explaining a
  **recorded** outcome names that
  record rather than copying it: the explanation a `single` gave is
  already in this comment, so a notice repeating it would put the same agent prose there twice and an explanation an
  outcome could be recorded with would be one its own obligation could not be written beside — which for a park
  nothing supersedes is a human never told at all. The stored `message` therefore holds a marker where the explanation
  goes, bounded by this orchestrator's own wording — a bracketed token rather than an HTML comment, since this one is
  stored INSIDE the pinned comment and a marker carrying `-->` would close that comment early and leave GitHub
  rendering the rest of the payload as visible issue text — and the delivery puts the recorded explanation back on the
  way to the thread, in a fenced block at the end of the sentence: a thread is markdown, so an explanation opening an
  HTML comment anywhere in it would swallow everything after it and leave a human told neither what the agent said nor
  what to do, while a fence is shown rather than obeyed and costs the same few characters however long the quote is
  (escaping every opener instead grows the comment per occurrence, which an explanation the record can hold is enough
  of to push past what GitHub accepts). A fence is longer than the longest run of its OWN character the quote carries,
  or the quote would close it early — and only a LINE that is a run of the fence character and nothing else can close
  one, so a run in the middle of a line closes nothing. It is built out of whichever character the quote's own lines
  leave cheap, since a line of backticks cannot close a tilde fence, and an explanation that is ITSELF a long run of
  fences reaches the thread whole at three characters an end. The quote carrying a long line of EACH is blocked off in
  PIECES: a fence is two characters per character of width and a further block is a fixed handful, so the long lines
  land in blocks of their own and every HTML-comment opener between them stays inside a block, where it is shown
  rather than obeyed. Which way round is not something a rule of thumb gets right, so every width from the shortest
  fence up to the widest line is tried by doubling and the smallest rendering wins. What ends a LINE is markdown's
  answer rather than this orchestrator's — a newline, a carriage return, or the pair — so the quote is split on all
  three and rejoined by the terminators it arrived with: an explanation written with carriage returns reaches the
  thread as its author wrote it, and its fence lines are recognized rather than blocked off at three characters they
  could close. Past what any pieces can hold the
  quote goes in UNBLOCKED with its openers escaped a backslash apiece, since unblocked is where an opener is obeyed
  again; past what that holds it is cut and said to be cut, which nothing this orchestrator records can reach and
  which exists because a comment GitHub refuses is rebuilt identically on every poll — the park would stand with its
  sentence owed and the human told nothing at all. Nothing is stood in for, and no verdict is refused for how its
  explanation renders: `late_result_unrecordable` is superseded, so such a refusal would buy another decomposer run
  and leave the `single` short of its own park. The
  substitution happens identically on the first post and on every redelivery, since the already-posted reconciliation
  below matches what was actually said. The room that write needs is reserved where the
  outcome is accepted, so a notice named this way is one the comment can always hold. Not one of `LATE_STATE_KEYS`: a
  park outlives the generation that took it. It carries the shared spawn budget's `retry_cap` sentence too when a late
  adjudication is what ran out — that park is taken by this mode's owner, so it is this field rather than
  `retry_cap_notice` that holds what it owes, and the entry replay under `workflow:decomposing` finds nothing to say
  for it because the redelivery below is what says it. The converse is the one an old record leaves: an issue parked
  on `retry_cap_notice` under this label — by the shared parking form, before it entered the size gate or before this
  owner existed — is said by that entry replay instead, so the late spent-budget hold treats an obligation on
  **either** field as a park the thread has not been told about. Owned by
  [`late_notice`](../../orchestrator/workflow/stages/decomposition/late_notice.py). It is a claim about the thread, so
  the thread settles a disagreement with it. The post and the write recording it cannot be one operation, so a write
  that failed after a post that landed leaves the field claiming a sentence is owed to an issue that already has it —
  and the first thing a tick does is look for that sentence among the comments above `last_action_comment_id` (the
  mark a park's own mention ratchets, and only on a write that landed, which is what scopes the search to this
  episode). That read names the pinned comment by its own id rather than skipping whatever carries the state marker,
  which is what the body test elsewhere stands in for: a notice quoting an agent who wrote that marker reads as a
  state comment to the body test, so the one comment being looked for would be the one comment invisible to it.
  Rewriting the marker out of the sentence instead is what the search deliberately does not do — it grows the comment
  per occurrence, and an explanation the record can hold is enough of them to push the notice past what GitHub
  accepts, which is a sentence no tick could ever deliver. One found there discharges the obligation and repairs the
  watermark to it. Without that step the redelivery would repeat a comment, and — worse — the owner guard would read
  the standing obligation as proof nobody was told and clear its park without the recovery follow-up it promises. A
  read that could not be TAKEN answers here exactly as an empty one does, which is the opposite of the shared field's
  reading and is this mode's own choice: the sentence is said again, costing one repeated comment rather than risking
  a park that stands unexplained for as long as the read keeps failing. What that buys is the property every late park
  hangs on — the notice reaches the thread before anything on that thread is read as an answer to it.
- **Unattributed park sentence.** `late_held_authorization_receipt` is the receipt the
  `late_unauthorized_exemption` park stamps on a sentence it has not recorded posting — its own notice and the
  refusal a wrong command earns alike — written *before* that sentence goes out and dropped by the write past the
  post. Sibling to `late_park_notice` above, and a narrower question than it asks: not whether a sentence was ever
  recorded as owed, but which side of the post the tick recording one died on. Present, something may still be owed
  and the THREAD is asked which; absent, the write past the post ran and nothing is. What it may never be built
  into is a claim that some comment is *ours*: it is plain text on a record that is itself a public comment, so it
  is readable before the sentence it names exists, and read as authorship it hands the human whose consent this
  park collects the power to have their own retraction deleted from every later reading. Only
  `orchestrator_comment_ids` attributes a comment, and the one road that adds to it without a write of its own
  proves what it claims by the secret behind `late_held_authorization_publication`. Full contract with the park it
  belongs to, above.
- **Unaccounted seam sentences.** `late_held_authorization_publication` is the list of **digests**, one per
  comment, that `late_authorship`'s client records as the publication seam speaks — the first written down before
  the seam is entered at all and each one after it before its own comment goes out, every sentence this park writes
  among them since `late_consent`'s notice and refusal are worded inside that call. Each is dropped by the write
  that records the posted id in `orchestrator_comment_ids`, made the instant that post returns, so an entry still
  standing marks the one API call in between.

  What each commits to is the **sentence** and not the sender: the secret *and* the exact body it goes out on. A
  digest publishes nothing, but the secret it commits to is published by the sentence carrying it — so a reply
  quoting that sentence carries it too, and the login beside both is a token this repository says may be shared
  with the human whose consent this park collects. Order separated them only while our comment stood, and order
  does not survive that comment being deleted. Bound to the body, their reply answers nothing, since a quote
  carries their words as well as ours; a verbatim copy still answers, and carries nobody's words to lose. So the
  entry is answered by the ledger repair `late_recovery` runs ahead of its own routing: the EARLIEST comment whose
  body is that sentence goes into `orchestrator_comment_ids`, no watermark moves, and the entry is dropped. Earliest
  because a copy can only follow what it copies, and a reply merely quoting our sentence carries its author's words
  too and answers nothing at all. Each is dropped by that repair, by the write recording the posted id, or — for a
  promise the seam never worded a sentence for — by the handoff that made it, and nowhere else: one cleared while
  its sentence is still unledgered leaves nothing able to find that comment again. Its own field rather than a share
  of the one above, because a handoff and a sentence this stage worded can be outstanding at the same time.
- **Held authorization park.** `late_held_authorization_park` is what the `late_unauthorized_exemption` park was —
  `awaiting_human`, `park_reason`, `last_action_comment_id` — recorded beside the receipt above before
  `late_rollback` enters the publication seam, and dropped by the same write past it. The seam's own writes are
  durable before that call returns, so a rollback kept in memory dies with the process. A record still carrying
  this field is a handoff that never returned, and the poll that finds one puts back what it holds.
- **Held authorization reading.** `late_held_authorization_command` is how far the reading behind that handoff got,
  recorded in the same write and spent by a different one: the publication handoff's, ahead of the
  `workflow:validating` label. The seam consumes the command itself wherever it records an authorization from it,
  and its two roads that publish without reading the thread leave the reply that ended the park above the
  watermark — read on the next stage as fresh feedback, and paid for with a developer run over an implementation
  already published. Staged before the call because the handoff's write and its relabel both land before this stage
  gets an answer back, and past that label nothing spends what implementing left behind. Consumed to what the
  reading looked at and no further, and dropped rather than spent wherever somebody is still waiting.
- **In-review watermarks.** `pr_last_comment_id` (issue thread + PR conversation, shared IssueComment id space),
  `pr_last_review_comment_id` (inline PR review comments), `pr_last_review_summary_id` (PR review summary bodies). Only
  non-empty `CHANGES_REQUESTED` or `COMMENTED` review IDs ever advance the summary watermark; `APPROVED`, `DISMISSED`,
  `PENDING`, and empty-body reviews are filtered before the bump.

  The shared id space is a numbering, not a shared delivery record, so `in_review` and `fixing` read the two surfaces
  under it separately (`in_review/surfaces.py`: `_unread_issue_thread`, `_unread_pr_conversation`). The issue thread
  answers to `pr_last_comment_id` AND to `last_action_comment_id`, because the implementing and validating
  awaiting-human resumes — and the fresh spawn and the `workflow:implementing`, `workflow:validating` and
  `workflow:resolving_conflict` drift resumes beside them — watch that surface alone
  and settle the second field for what they quoted; a reply at or
  below it has been in a developer prompt and may not route the issue back to `workflow:fixing`. The PR conversation
  answers to `pr_last_comment_id` and to nothing else: nothing that advances the issue-thread cursor has read the pull
  request, so a PR comment numbered below the last answered reply is unread rather than delivered. Neither field is
  copied into the other and no maximum is taken across them — that maximum is exactly the value that hides one surface
  to bound the other.

  The `in_review` drift resume is the one developer prompt that reads BOTH surfaces, and it is the one whose
  settlement deliberately writes only ONE of the two fields. Its record covers the pull request's conversation and
  the issue thread at two different moments — the conversation before the notice this road posts on it, the thread
  after — so a comment landing on the pull request in between is in neither half while an issue reply numbered above
  it is in one. Settled from the pair, `pr_last_comment_id` would step straight over that comment and no later poll
  could go back for it. So the record settles `last_action_comment_id` and the requirements revision, and the shared
  cursor is left to the park carry, which re-reads both surfaces at one moment, crosses exactly what the record
  names, and stops at the first id it does not. Neither review surface is touched either way, because the prompt
  quotes no inline comment and no review summary; a road that crossed those would hide a reviewer's words from the
  `workflow:fixing` round that delivers them.

  `fixing` also WRITES `last_action_comment_id`, and it writes it for the issue thread alone. A fix round quotes every
  unread surface into one developer prompt, so the round that consumed an issue-thread reply settles that reply for the
  reader the reply belongs to as well (`fixing/feedback.py`, `_settle_consumed_feedback`) — left behind, a manual move
  between `workflow:fixing`, `workflow:validating` and the drift path pays a second developer to deliver the reply the
  fix round already answered. The PR-conversation, inline-review, and review-summary halves of that same batch move
  only their own in-review watermarks. Every surface advances to the max id actually quoted on it and no further, the
  pairs come from `workflow/engine/prompt_delivery.py` (the producer a recovered report transaction's watermarks are
  also read against, and the owner whose classifier the `fixing` scan asks of the two review surfaces, so no item is
  prompted that the settlement would then refuse to record), and a run that was never invoked, a shutdown-killed run,
  and a live-paused run settle nothing at all — delivery is what the field records, and none of those delivered
  anything. A round that finished on a report outcome settles nothing either: the publication it owes is not this
  tick's to promise, and feedback recorded as answered for a report no reviewer has is the one reading that fork
  exists to refuse.

  Every writer of these fields stops before unread human input, and none of them reads a tip. The
  approval handoff's seed walk stops at the first unread non-orchestrator comment on either surface; the legacy
  migration reuses that same walk and seeds the two review surfaces at 0, since the orchestrator posts on neither and
  any advance there would cross somebody's review; and the park carry walks forward from the mark already persisted
  through comments it can vouch for — ours, named by the frozen delivery record this tick's own prompt was built
  from, or recorded on `last_action_comment_id`
  for the issue thread alone — stopping at the first it cannot. That carry is handed the RECORD rather than the read
  behind it: a bounded excerpt delivers less than it read, and the context it cut is exactly what the walk has to
  stop below. A comment the record names REFUSED — an outsider's, a pasted marker the id ledger cannot vouch for —
  is crossed, since no reader is ever owed it and a walk that stopped there would stop forever. A carry to the
  newest comment would skip a PR comment
  written while the tick was deciding, permanently (see [`delivery-stages.md`](delivery-stages.md),
  `_handle_in_review`).
- **The requirements edit nothing has answered.** `requirements_drift_open`, additive and `true` only while a drift
  resume's park stands. A resume the edit earned can end without answering it — a question, a timeout, a tree nobody
  could publish, a push that did not land — and the reply that clears such a park is the rest of that resume rather
  than an ordinary fix: the report the edit is owed is the one that reply writes, and read as a plain fix the commit
  would reach the reviewer with no report of it anywhere. Nothing else on the comment says which road a park came
  off, so the claim goes down beside the park through the shared drift disposition and comes off with it — cleared
  by the road that clears the park, and by any outcome that answers the edit, together with the
  `developer_report_owed_round_reset` a hand-back recorded, where the publication that record is about has by then
  happened. It is read
  before the resume that continues the road, since that resume clears the park it was written beside. The
  disposition writes it only for a caller that named what its resume was handed, which is the caller that reads it
  back — both review stages do, and `in_review` reads it for the budget its hand-back owes.
  `workflow:resolving_conflict` names its body-edit resume too and writes no claim: a park that stage takes is
  answered by its own reply road, which reads the report the issue owes for itself and leaves a question to the
  resolution it interrupted. An issue without the key has no edit outstanding.
- **The reviewer round somebody is still owed.** `validating_reviewer_owes_a_round`, additive and set only between
  the `workflow:validating` tick that stood a round up and the round that runs. A reviewer-side park — a returned
  verdict's `reviewer_unverified` / `reviewer_unrecorded` among them — or a `review_cap` one owns the human's next
  comment, so the drift check stands down for it — but the park is gone before that
  round runs: the silent recovery clears the flags and ends its tick, a report still owed holds the reviewer
  behind a clear already written, and the reviewer spawns a tick or more later. An edit nobody has delivered would
  take that tick down the developer's drift road instead, ahead of the retry the park was taken for, so both the
  deferral and the road that clears such a park into a round write this down, whichever write goes out carries it,
  and the round that actually runs drops it. The VALUE says who stood the round up, because that decides what the
  round records: `true` is a silent recovery, which delivered nothing and leaves the edit outstanding, while
  `"bought_by_a_reply"` names a human's retry or an operator's grant, whose words the round settles off its own
  prompt wherever it finally runs. A deferral never writes over a claim already standing, or the round would be
  left with nothing to record and the reply unread for good. An issue without the key owes no round.
  `validating_reviewer_round_requirements` rides beside `"bought_by_a_reply"`: the requirements revision of the
  thread through the reply that bought the round, which is what that round is due to hand its reviewer. The reply is
  the reviewer's to read; anything written after it is a change the developer report never saw, so a reviewer read
  that differs from it holds the round and drops both keys, and the next tick's drift check hands the new words to
  the developer. Additive, written only where the buying reply is a control and nothing else — the bare cap grant,
  or a bare `/orchestrator continue` — and dropped with the note it rides beside. A reply carrying words is itself a
  requirements change (a reviewer-side park retries on its own or, for a returned verdict's `reviewer_unverified` /
  `reviewer_unrecorded` park, waits on exactly that reply, so a reply to one says something), so it records
  none and the round is held for the developer; a round bought before the key existed is held to the drift baseline
  too. A `reviewer_usage_limit` park is bought only by a reply carrying the `/orchestrator continue` line, and is
  held to the same split: the bare command records the reach, and words beside it record none.
- **The review-cap grant already honored.** `review_cap_granted_comment_id`, additive, holding the id of the
  comment the last `/orchestrator add-review-rounds` reset was written for. A grant may leave that command
  uncrossed — a bounded reviewer round records only what its own excerpt carried — so the batch a LATER cap
  freezes reaches back below it and offers the same words again; refusing a command this key already names is what
  stops one comment resetting every cap the issue reaches. It is written beside the round reset, in the same
  write, because the two must be durable together: the reset is staged for the reviewer's own write, so a launch
  the lifetime run circuit refuses discards both and leaves the command an `/orchestrator add-agent-runs` grant
  hands back to be honored for real. An issue without the key has granted nothing.
- **The label move `in_review` owes.** `in_review_handoff_pending`, additive and `true` only while one is outstanding.
  A requirements edit leaves the approval that carried the issue to `in_review` stale, so the round resets to 0 and
  the label moves to `workflow:validating` — two operations a process can die between, and the marker goes down with
  the reset and comes off in a write of its own behind the move. On the drift road it is staged earlier still,
  beside the refreshed `user_content_hash` and ahead of the resume: every write the disposition behind it makes
  persists the whole comment, that hash included, and once the hash is durable no later tick re-detects the edit —
  so something has to say the move is owed by then. A report a run recorded, or the debt of work it withheld, says
  it on the roads that leave one; an `ACK:` and a park with no report at all leave none. Staged together, no write
  can make the hash durable without the marker.
  A relabel that did not land is then found by the
  hand-back at the top of the next `in_review` tick and remade, which is what an `ACK:` outcome needs: it records no
  report, so without the marker nothing on the comment would say the move is owed, the drift is already consumed, and
  the ready ping is one tick away on an approval that is over. A drift resume that PARKED writes it for the same
  reason: it answered the edit with nothing, so the move is owed from a tick that recorded no report either — and
  without it the answer a human writes is read by the feedback scan and routed to `workflow:fixing`, where no report
  is owed and the stale approval survives. A marker whose clearing write is lost costs one
  spurious hand-back the next time the issue reaches `in_review` — a re-review rather than that ping — and that tick
  clears it. An issue without the key owes no move, which is every issue that predates it. It goes down in one
  staged write with the fresh round and the budget record beside it, spelled on the stage owner that holds the key
  rather than at the hand-back that makes it — a developer report recorded on THIS stage's drift road is accepted
  only where the comment has room for that whole write, so a field added to it moves that refusal too. A report
  recorded on any other route is not charged for it, since no other stage hands an approval back.
- **Review subject.** `review_subject` is what the latest reviewer was handed, written beside `review_agent` ahead
  of the spawn, in a guarded commit of its own over the comment as the round just read it (the launch charge writes
  only its own fields, and the state the tick holds carries what only the round's own write may land, such as a cap
  grant's round reset), decided on the report records, `pr_number`, and `review_returned_verdict` there, and on
  `review_agent` and `review_subject` themselves -- one that moved under it, a comment that will not read, or an
  edit never confirmed spawns no reviewer that tick, and one never confirmed is committed again with nothing sent by
  the next: `pr`, `sha` (the head the pull request stood on),
  `requirements`
  (the fingerprint of the thread read the prompt quotes), and `report_revision` + `report_content` (the revision and
  digest of the developer report quoted whole in the prompt; both `null` is a subject with no report, a shape the
  reader accepts though no reviewer is spawned over a pull request with no report).
  `review_returned_subject` is the same object again, written only in the write the round makes once its reviewer
  RETURNS: `review_subject` goes down before the run budget is asked, so a launch that budget refused, or a process
  that died before the spawn, leaves the report named there with no reviewer ever invoked, and this is the record
  that says one really read it. Additive: an issue without it records no reviewer that returned under this build.
  `review_approved_subject` is the same object for the latest approval, staged once the verify gate has passed and
  the approval comment is posted -- the subject resolved again behind that comment, the round's checkout proved to
  stand on the `sha` it names with nothing left uncommitted, and the pinned comment read last
  still carrying the report records, `pr_number`, `review_returned_verdict`, and `verification_evidence_*` records the
  gate's own reading left -- and written by whichever write the squash tail makes. Every later reader that would act
  on an approval -- the settled squash handoff on `workflow:validating`, and the stale-approval hand-back on
  `in_review` -- holds it to the report
  `developer_report_current` records now: another revision, other words, or a report where the approval saw none is
  a subject nobody reviewed, and so is a current report `developer_report_handoff` no longer describes -- the pair a
  settlement writes together, which a reviewer spawn refuses too -- so the handoff is dropped for a fresh reviewer
  and the in_review issue is handed back.
  Both also read that report at its location again, since no record sees its comment edited or removed in place,
  and hold rather than act where the location could not be read. The in_review stage, which would advertise the
  approval as ready to merge, also holds its `requirements` to `user_content_hash`, handing the issue back where they
  differ, and at the ready ping reads the issue afresh against that baseline, the pull request afresh for the head
  the ping names, and -- last -- the pinned comment for the report, verification evidence, and approval records in
  hand. The
  squash tail and the settled
  handoff read the issue afresh too before moving the label to `workflow:documenting`, against that baseline and
  against the approval's own `requirements` both (a baseline moved on to an edit since the approval says nothing
  about what the reviewer read), and the pull request afresh against the commit the move is owed over -- the one the
  squash published or the handoff recorded, or the approval's `sha` where the squash rewrote nothing -- holding the
  move where any moved (the settled handoff is then dropped, for the drift check or a fresh review to answer), and
  read the comment last, as does the squash tail once its rewrite is published. Where the comment moved them,
  none of them acts or writes. `review_subject` is handed over only where the
  pinned comment carries the report records the subject was resolved from, and the approval itself is taken only
  where it still carries them when the reviewer returns and once the approval is verified -- a settlement that
  landed meanwhile is kept, and the verdict dropped; a comment that will not read, or is no longer the pinned comment
  the tick read, is written over by nothing -- and
  the whole subject resolved again equals `review_subject`.
  Both are additive: an issue without `review_approved_subject` was approved before it existed, and that approval
  covers only an issue with no `developer_report_current` either — over a report, nothing says it was the one
  approved, so the issue goes back for a fresh review — while one present in any shape its reader refuses, `null`
  included, covers nothing. That reader takes the record whole: exactly the five members its writer spells, each in
  that writer's shape -- a whole commit id as `sha` wherever `pr` names a pull request, and both report members or
  neither -- so a record short of its `sha` or its `requirements` is no approval either.
  `review_approved_evidence` is the evidence claim that approval was proved over, written beside
  `review_approved_subject` in the same write and in the shape `review_returned_verdict` carries its `evidence` in
  (`stages/validating/approved_evidence.py`). Every approval records one, since an approval reaches the arc only once
  proved over its evidence, so an issue without the key carries an approval recorded before the key existed, held to
  no evidence -- save where `verification_evidence_current` is a carry onto a head it did not run on, which only a
  claim ever puts there: without one (the key removed or written `null`) that approval does not stand, and the
  settled handoff's retry invalidates the carry and drops the handoff for a fresh reviewer. Nor does any approval over
  a carry whose review subject no longer stands, or that no claim names (`squash_evidence.carry_unanswered`): the
  documenting stage and `in_review` hand the issue back, and `validating` invalidates the carry on arrival, ahead of
  any round, in a guarded commit of its own staged on the pinned comment read afresh -- held to the bound evidence
  records, the report debt the carry's review subject stands only without (`developer_report_owed` and an undeliverable
  `park_reason` beside the report records) among them, and to this claim, owning only the current record, the history,
  the
  approval, and the settled squash handoff, so a claim, an approval, a review subject, or a debt another road moved
  meanwhile, before that reading or under the commit, holds the tick with nothing written, and every other field is kept
  as written. Whichever road invalidates or abandons evidence an approval rests
  on retires the approval it was recorded for in the same write -- only that one, spelled exactly as the evidence
  recorded it: an approval another road recorded in its place, of another subject or spelled otherwise, stands -- even
  where the comment has no room for the evidence's own history entry --
  `review_approved_subject` written `null`, which `approval_covers_current` refuses -- so no reader takes it for an
  approval recorded before claims, and nothing moves it on until a fresh reviewer's approval replaces it. The claim is
  guarded like the review subjects across the tail's proof, relabel, and the write
  ending its handoff. Past the squash the evidence can no longer be proved against the pull request, which stands on a
  commit it was never bound to, so every road that would move the approval on -- the squash tail's relabel, the
  settled handoff, the recovery of a squash an earlier tick did not finish, the `workflow:documenting` tick's opening,
  and the merge gate -- holds it to this record and to every part of the proof the rewrite left standing
  (`approved_evidence.stands`, through `review_coverage._approval_holds` on all but the documenting opening): the claim
  has to
  name `verification_evidence_current` exactly -- receipt, revision, and digest -- that evidence has to have passed,
  no revision past it may have been spent (a newer transaction raises the floor the moment it is recorded, whether it
  settled or is still owed as `verification_evidence_pending`), `verification_evidence_handoff` has to still
  describe it, and it has to have been minted under the verification context configured now; and its artifact,
  re-read at the recorded `comment_id` on the pull request it was published on -- which no rewrite of the branch
  touches -- has to still be the one that settled, passing and covering `VERIFY_COMMANDS`. A later revision recorded
  or settled, the current record retired, `VERIFY_COMMANDS` or `VERIFY_TIMEOUT` changed, the artifact deleted or
  edited, or a record that will not read holds the move -- and the ready ping -- and the settled handoff behind it is
  dropped for a fresh reviewer; an artifact or pull request nobody could read holds them for a later tick. A squash that
  publishes another head carries that evidence onto it only by tree equivalence
  (`stages/validating/squash_evidence.py`) -- the passing run the approval's verify gate made on the approved head
  where it binds, orchestrator-executed, and the reviewer's evidence otherwise: the carried transaction is recorded
  as `verification_evidence_pending` and the claim pointed at it -- its receipt and revision, the digest and flags its
  transcript earns, `use` `published` -- in the write settling the squash's handoff, so the move waits until the next
  tick's reconciliation settles it as the current evidence -- a carry of the reviewer's evidence held until then to
  the artifact it copied (`copied_from`), so an edit or a deletion of that artifact, on a publication retried over a
  lost response included, abandons it. A carry still owed for its approval -- the reconciliation stood down for want of
  room on the comment, before the post or behind it, or over a bound record another road moved under its settlement,
  which refuses what the tick decided over rather than the carry -- holds the move with the handoff kept, and the next
  tick settles it or refuses it over the comment as it reads then; a carry abandoned leaves the claim naming no current
  evidence, which drops the handoff like any other;
  a refused carry -- a context moved during the squash
  included -- invalidates the evidence and drops the handoff in that same write, and so does a settled carry that no
  longer proves whole when the handoff's relabel is retried, or whose handoff that retry drops. Additive, and written
  only by the proof, which every approval a live reviewer round returns reaches, as does the recovery of one an
  earlier tick left waiting (`stages/validating/review_resume.py`).
- **Returned reviewer verdict.** `review_returned_verdict` is the verdict a returned reviewer left and nothing has
  disposed of yet (`stages/validating/review_verdicts.py`): `round` (the round it ran as), `verdict` (`approved` or
  `changes_requested`), `subject` (exactly as `review_subject` spells it), `feedback` (the words a change request hands
  the developer and posts on the pull request: a live round's findings with their verification declaration set aside
  (`workflow/engine/review_findings.py`) -- a record persisted before that formatting carries the declaration raw and
  is kept as written, its recovery formatting only the words it posts and hands on (`review_handoffs.py`); `""` for an
  approval, and neither an approval carrying any nor words UTF-8 cannot carry read),
  `evidence`, and `handed`. `evidence` is `null` where the reviewer's declaration earned none, and otherwise the one
  claim the verdict relies on (`review_claims.py`): its `use` -- `published` for a reviewer-reported transaction
  minted from the commands the reviewer ran, bound to the subject, head, and tree it was handed and the configured
  verification context, whose artifact has to render as one comment, or `reused` for the current evidence it was
  handed and named, never any other -- and that record's `receipt`, `revision`, evidence `digest`, `passed`, and
  `covers` (every configured `VERIFY_COMMANDS` command among its commands, exactly as configured, exiting 0). A
  claim's evidence is settled while `verification_evidence_current` names its receipt, revision, and digest, owed while
  `verification_evidence_pending` does, either bound under the configured verification context and at the latest
  revision the issue has spent, and lost otherwise -- a later transaction, settled or not, supersedes it. `handed` is
  `null` until a change request is handed to `workflow:fixing`, and then the `agent_runs_used` count as that handoff was
  written, no wider than the count its room is reserved at; an approval carrying one does not read. Once handed, the
  record carries a seventh member, `anchor`: the id of the reviewer-feedback comment the request was handed over with,
  written by that same handoff and no wider than the id its room is reserved at. A record waiting to be handed carries
  only the six, and one with `anchor` and no `handed` does not read. One with `handed` and no `anchor` is the shape a
  handoff wrote before it anchored its post: it reads as handed beside no post, and its launch is held for good, since
  no pinned anchor can be vouched for as its feedback -- and nothing stages that shape. The reader takes the record
  whole -- exactly those six members, or those seven once handed beside a post, a claim of exactly its six, each in its
  writer's shape -- or reads no verdict at all, and nothing that reader refuses is staged. It is staged only where the
  comment has room for it at the widest write it is part of: a change request's handoff, with its count and `anchor`,
  the `pending_fix_reviewer_comment_id` anchor, and that comment's ledger entry, and the developer launch's
  `agent_runs_used` / `agent_run_reservation` / `agent_run_fingerprint` charge composed over it and the start behind
  that charge, which records `agent_run_owed_started` -- each reserved at the widest a recorded number or fingerprint is
  spelled, the charge and the start through the very ledger writers the run circuit writes them with. A `published`
  claim is staged only in the same write as exactly
  the transaction it names -- its receipt, revision, digest, and `passed` -- measured with its settlement beside that
  reservation, a retry of the one the comment already carries included, and a `reused` claim or none only beside no
  transaction; where the pair does not match or either has no room, neither is staged. Its writers are the disposition
  service (`review_disposition.py`), where it persists the verdict a live reviewer round returned -- a road the
  recovery never takes, since it finishes a record already persisted -- and the change-request handoff below. In the
  service the transaction is minted first, since reading the reviewed tree is a
  request of its own, and the record and that transaction go down in one guarded commit with the returned run's own
  records, captured over the pinned comment read again once the subject has been resolved -- the last requests before
  that commit -- BEFORE the evidence is published through the dispatcher's own reconciliation. A report record,
  `pr_number`, the record itself, or a `verification_evidence_*` record another road moves after that reading refuses
  the commit with nothing written or published, and so does a comment that will not read or parse or was replaced; an
  edit never confirmed publishes and acts on nothing, and the record and transaction it may have left are published and
  finished by the next tick with no second reviewer, artifact, fold, charge, or round. The service stages those run
  records itself -- `last_review_session_id`, `last_review_at`, `review_returned_subject`, and the reviewer's usage
  folded into `issue_agent_runs` / `issue_total_tokens` / `issue_total_cost_usd` / `issue_cost_sources` -- over that
  last reading, so a usage total another road folded meanwhile is added to rather than written back over. A subject
  proved to have moved by then, or a `verification_evidence_*` record another road moved since the subject was resolved
  -- the transaction was minted, and a reuse named its evidence, over the records it replaced -- writes the run's own
  records and no verdict; one that would not read writes nothing. A record that would not read back as written --
  feedback UTF-8 cannot carry, say -- or one the comment has no room for beside its transaction, measured again over the
  very candidate the commit sends, is written nowhere and nothing is published: the service answers which, and parks it
  under `reviewer_unrecorded` (below). A returned run that does not
  name, as a whole number, the pull request its `subject` is on is refused before anything is minted, written, or
  published. The verdict is ready to act on only while the comment carries it as persisted, its subject -- held to it
  once more, the report records, the record itself, and `pr_number` read again last -- still stands, and its claim,
  judged over that last reading, is settled, or it relies on none: a settlement of the very evidence it claims readies
  it, and a push, a later report, or a later revision superseding that evidence sets it to `null`. A later tick asks the
  same of a waiting record over the pinned comment alone, since nothing of the run that returned it outlives its tick:
  the record's own `subject` is what the standing subject has to record as, and the comment as that tick read it is what
  the record is held against. That tick acts on a ready record only beside a run its caller rebuilt of the record's own
  `round` and `subject`, naming the pull request that `subject` is on, each read as the record spells it; through any
  other -- a round `False` for `0` or a report revision `True` for `1` included -- it acts on nothing and writes
  nothing. An owed transaction
  holds the record for a later tick while its subject stands -- held to it again on every tick it waits -- and sets it
  to `null` once that subject is proved to have moved, leaving the transaction owed to the reconciliation; a lost
  claim, whichever the verdict -- a transaction that can never settle, or reused evidence a later revision has
  superseded since -- sets it to `null` for a fresh reviewer. A `pr_number` naming another pull request than the
  record's `subject` -- moved while the verdict waited or between ticks -- is such a move too, even where that pull
  request still stands as it was handed: every road acting on the verdict reads the pull request off the comment. Every
  write the service makes, the record's own included, is a guarded commit captured over the comment read again just
  before it, keeping what another road wrote there, before that reading or after it -- newer records, and fields no
  verdict stands on, such as a `review_round` a reply bought or the `last_action_comment_id` it read through -- save,
  where the report records, the record, and `pr_number` stand, a field the service changed itself; a record it was
  decided on that moves after that reading refuses it, and a drop refused so leaves the record waiting for a later tick
  to decide again. A field both it and another road moved keeps both moves where they add up
  or only advance, however the records went -- the `issue_*` usage totals add, `issue_cost_sources` joins, and
  `last_action_comment_id` and the `pr_last_*` watermarks keep whichever reading went further, each only over values
  spelled as their writers spell them -- whole numbers for the run and token counts and the watermarks -- a hand edit
  being one road's to say -- and the `orchestrator_comment_ids` ledger is merged, an id either side recorded kept
  once among the newest 500 it holds, an id one reading already evicted evicted again rather than a newer one, a
  ledger already past 500 -- an older binary's, a hand edit -- cut to it even where the merge adds nothing, and an
  entry naming no comment -- or a ledger that is no list -- dropped from either side, so no later scan of the ledger
  fails on it. Every drop names the verdict it holds, so one another road put in its place is never the one dropped,
  and a caller holding none drops nothing -- a record no reader takes, which reads as none, included.
  Two parks answer a verdict that may not be acted on (`stages/validating/review_parks.py`): an approval relying on no
  valid evidence parks under `reviewer_unverified`, and a verdict that could not be persisted under
  `reviewer_unrecorded`, with nothing published or acted on -- its notice asking for room on the pinned comment only
  where room is what refused the record, and not where it would not read back as written. Each is measured before its
  notice is posted at the park's own write -- its flags beside the notice's ledger entry and `last_action_comment_id`,
  each at the widest id, with the record it refuses set to `null` -- and taken over the comment as it stands, the
  returned run's usage and session unrecorded, where it has no room beside what that run staged, but only while that
  reading carries the report records, `pr_number`, the record, and the `verification_evidence_*` records the tick last
  read; nothing is posted or written where there is room for no park. Behind the notice the subject is resolved again
  and the comment read last, against the one the tick last read or wrote -- the state a `reviewer_unverified` park began
  over, the reading a returned run was resolved over for `reviewer_unrecorded` -- so what that run staged, its session
  and usage among them, lands with the park: a push, a later report, a moved `pr_number`, a record another road put in
  place of the one parked, or a `verification_evidence_*` record moved there lands no park and sets the record held to
  `null` alone, over the newer records, whether or not the notice left an id; where nothing proved a move, a subject
  that would not read, or a notice that left no id and so may have reached nobody, lands none either and leaves the
  record as it waited. That write keeping the record can be wider than the park's own, and is measured behind the notice
  like every other: where it does not fit nothing is written and the record waits for a later tick's notice, rather than
  a park that fits being refused up front and the record waiting on it with nobody told. Every park write is the park's
  guarded commit over the comment as it stands, keeping and merging what another road wrote behind the notice as every
  write of the service does, measured again with it and not made where another road's write left no room or moved,
  after the last reading, a record the park was decided on; the measurement before the notice is that commit prepared.
  Only a park that lands sets `awaiting_human` and `park_reason`, sets the record it holds to `null` in its own write --
  a `reviewer_unrecorded` park holds none, and leaves the key, or whatever record another road or a hand edit left
  there, exactly as it found it, and a `reviewer_unverified` park holds the record only where it is the approval of the
  round and subject its run returned, and posts and writes nothing where it is not -- and reports `park_awaiting_human`
  once that write is down. Neither park retries itself: a bare `/orchestrator continue` buys a fresh reviewer, and an
  edit under one nobody replied to waits for that reviewer rather than resuming the developer.
  A change request is handed over (`review_handoffs.py`) through the decision it was persisted from -- the
  record's own `round`, `verdict`, `subject`, and `feedback` -- in the tick its reviewer returned, or from the record
  alone on a later tick, which holds no decision, either way on that subject's pull request: another round's decision,
  an approval, or other words hand nothing over. The handoff's guarded commit is prepared first, over the comment read
  afresh -- the record at its widest handoff and the developer's charge beside it -- so a comment another road filled,
  moved, or replaced posts nothing; then its feedback is posted, a post that failed or left no positive whole id -- or a
  run naming no pull request, or another -- relabelling, launching, and writing nothing, and leaving `handed` `null`. A
  later tick looks first for the post an earlier one made -- a comment this orchestrator wrote on the pull request in
  the words it posts, its marker included, never one another author copied, the line naming the review held to the
  record's round alone, whichever reviewer and round cap it names, since a restart may configure either otherwise --
  and takes it rather than posting twice. The whole subject is held again behind that post, and the record committed
  with `handed` and `anchor` set, beside a `pending_fix_reviewer_comment_id` naming the same post, BEFORE the relabel to
  `workflow:fixing` -- decided on the records, the anchor, the run ledger, and the park's flags above, and held to the
  room its preparation was, so another road moving one after that reading, or filling the comment past that room,
  refuses it with nothing relabelled or launched, and an edit never confirmed is resumed, or handed again behind the
  post it finds, by the next tick; the launch -- the subject, the evidence the request claims, `agent_run_owed_started`,
  `pending_fix_reviewer_comment_id`, and no park standing, over the comment read again -- is held to what stands before
  that relabel and once more right before the developer launch, so no relabel announces a launch another write behind
  the handed one already ruled out, and no developer runs under a park another road recorded, and the developer's
  run sets the record to `null` only in a guarded commit that records what it left and
  is decided on the record, `pr_number`, `agent_run_owed_started`, `pending_fix_reviewer_comment_id`, `awaiting_human`,
  and `park_reason` as the tick read them: the commit recording its report, which writes the `null` itself, the commit
  landing a park the round takes instead -- a timeout's, a question's, one over a tree or a push it could not publish,
  or the report-debt park (`report_undeliverable`), which writes the `null` itself too -- or, where no report was
  recorded first, the hand-back behind the relabel to `workflow:validating`. It is prepared over the comment read afresh
  right behind the run, and every write recording or holding the run's report is decided on the same fields, so a record
  another road put in its place, a start written away, or a park recorded -- behind the run or right ahead of the record
  -- writes, posts, pushes, and spends nothing of that result; a hand-back refused, over a record or a field
  another road wrote while the label moved, settles nothing behind it and keeps what that road wrote. The record stays
  until that write lands with it, so one never confirmed leaves both or neither, and the ticks behind answer it as
  they would a confirmed one -- never a record set to `null` with nothing of the run recorded, which the fixing stage
  would hand back for a review nobody asked for. A run paused, killed by the shutdown sweep, or refused at the run
  circuit sets nothing. Every hold counts the issue pointed
  at another pull request, or a later evidence revision superseding the evidence the request claims, as moves, and a
  move sets the
  record to `null` in a guarded commit that keeps the newer records, clearing `pending_fix_reviewer_comment_id` where it
  still names that post -- only where the record it set to `null` was the one held, never beside a record another road
  put in its place -- and keeping one another road wrote meanwhile -- which the post never stages over, since the
  anchor goes down only with the handed commit -- and refused, the record waiting, where the record, the anchor, or
  `agent_run_owed_started` moves under it. A move proved by a reading that records `agent_run_owed_started` at `handed`
  is
  that developer's own push and drops nothing: the record is retired as launched, as below, and the pinned anchor kept
  for that developer's replay. A record already `handed` posts no feedback again: it is relabelled and its developer
  launched, or -- where `agent_run_owed_started` records the start of that developer at `handed`, that developer already
  launched -- set to `null` in a guarded commit decided on the record and that start alone, so a later report or
  anything else another road wrote since the tick's reading is kept, and a record another road put in its place, or that
  start moved, refuses it with nothing written (any other run charged meanwhile, a reviewer's say, records no such
  start,
  and a charge still standing as an unstarted `agent_run_reservation` recorded none: the launch stays owed, and the run
  circuit honors that reservation rather than charging again), which is asked again right before every launch, so a
  developer another road launched behind the relabel is never launched a second time -- and once more by the run
  circuit, on the readings it charges and starts the launch from, which refuse it with nothing started or written over
  them where another road started that developer, charged a run over its `agent_run_reservation`, or started a run of
  that launch's very identity with no `agent_run_owed_started` (below) -- a continuation of the launch's own start
  excepted -- after the handoff last read the comment, pinned another comment in its place, or where the record,
  `pending_fix_reviewer_comment_id`, the report records, `pr_number`, or the claimed evidence moved there, the whole
  subject resolved again right behind the charge (`review_launch_hold.py`; see [the agent-run
  circuit](#the-agent-run-circuit)). Whatever else another road
  wrote on a reading the launch stands on is carried onto the state the developer's run is written back from, so that
  run's writes keep it -- a run allowance granted, a usage total folded. Either launch is made only while
  `pending_fix_reviewer_comment_id` names, as a whole comment id, the comment the record's `anchor` does: the fixing
  stage clears it with the round's other bookmarks, and a handoff that lost it, whose anchor names another comment, or
  whose anchor is spelled as anything but a whole id -- a float over the same number included, which the fixing stage's
  replay refuses -- is held -- nothing relabelled, launched, or written -- since no failed run could replay the
  feedback, or one would replay another comment to the developer as the reviewer's feedback. Additive: every live
  reviewer round that returns a verdict hands it to that service, which acts on a ready verdict, parks it, or hands it
  over, and the recovery (below) calls it to finish one an earlier tick left waiting; an issue without the key has no
  verdict waiting, as does every issue whose last verdict was returned before the key existed.
  A record an issue already carries is finished by the stage handlers themselves (`stages/validating/review_resume.py`),
  running no reviewer, folding no usage, and spending no round: its reviewer's run, usage, and round went down with it.
  `workflow:validating` asks behind the report hold and ahead of the round cap and the spawn. A record not yet `handed`
  is finished through a run rebuilt of its own `round` over the subject resolved again as a round resolves it, the issue
  fetched afresh, which has to record as the record's `subject`: a push, a later or edited report, or an edited issue
  sets it to `null` in a guarded commit over the comment read afresh, with nothing of the tick's own beside it -- only
  while that comment still carries it, so a record another road put in its place, before that reading or after it, is
  kept -- and ends the tick, for the next tick's fresh reviewer, and a reading nobody could take writes nothing. A
  record already `handed` -- its relabel never landed -- is relabelled and its developer
  launched, its feedback not posted again, while that launch is owed, and set to `null` the same way otherwise -- once
  its subject is resolved again, a reading nobody could take writing nothing -- since only a relabel from outside brings
  back one whose developer may have been launched; so is any record on a tick an awaiting-human park was cleared into,
  whose reply bought a round of its own -- where the report hold stops that round or a record waits, the tick ends in
  one guarded commit captured over the comment read afresh against the tick's own reading, keeping the cleared park and
  carrying what another road wrote meanwhile, the record set to `null` only where that comment still carries it, and
  the round runs next tick; a record, `awaiting_human`, or `park_reason` another road moves after that reading refuses
  it, and the next tick answers the reply again. A park another road recorded there is kept as it wrote it where its
  `awaiting_human` or `park_reason`
  moved. One recorded again for the same reason moves neither, and shows only in its notice, which no field names: so a
  comment another road posted meanwhile -- an id in `orchestrator_comment_ids` the tick never recorded -- that opens
  with `HITL_MENTIONS`, as every park notice does and a status line may, writes nothing, the park standing, and the next
  tick answers the reply again over the comment as it stands, as does a thread that will not read; a comment naming
  nobody is no park. A subject or thread nobody could read holds the tick. The issue's checkout is restored only behind
  the subject's reading, before a record not yet `handed` is finished and behind a `handed` one's relabel, so a record
  whose subject moved is set to `null` over GitHub's readings alone, and a checkout that will not restore ends the tick,
  the record kept, only where its subject still stands.
  A record no reader takes is left as it stands. `workflow:fixing` asks behind the report recovery and ahead of the
  feedback scan, whose no-feedback bounce would pay a second reviewer for a round already reviewed: a `handed` record
  whose launch is owed has its one developer launched, the issue not relabelled onto the label it is on, and one whose
  launch may have started is never launched again (`stages/validating/review_handoffs.py`, `HandedLaunch`, and
  `stages/validating/review_launch_park.py`); while a park
  stands -- the run circuit's `agent_run_limit` over a launch it refused -- that park's own dispatch answers first. The
  launch is owed unless `agent_run_owed_started` records a start at or past `handed`, is present and spelled as no count
  -- `null` included -- or the latest charge at or past `handed` is `started` under the very `agent_run_fingerprint` the
  developer's own launch is charged under with no owed start recorded -- at `handed` too, since a charge reserved before
  the handoff is counted in it -- or stands with a record no reader takes, which may be that very launch -- `started`,
  or in an `agent_run_reservation` phase no reader takes, under that `agent_run_fingerprint`, any charge under an
  `agent_run_fingerprint` gone or spelled as none, `reserved` included, or a run count (`agent_runs_used`, or the legacy
  meter where that will not read) below `handed`, which only ever rises; an unstarted `reserved` charge under the
  launch's own fingerprint is the run circuit's to honor rather than charge again. A
  launch that may have started is held to the subject resolved again, the evidence it claims, and the branch: a subject
  that moved, a claim no longer the settled evidence, a commit the pull request has not got, loose work in the checkout,
  or a remote that moved past it sets the record to `null` the same way, the anchor kept, and the next tick's own road
  publishes that work, or holds its bounce over it, and hands the pull request back, while a subject or branch nobody
  could read -- a fetch, a status, or a count that did not return -- writes nothing, the record kept for a later
  reading. Anything else parks under `agent_execution_failed` in one guarded commit, prepared before its notice as the
  record's own parks are (above), landing only behind an identified notice over the subject resolved again, the branch
  read again, and the comment read again behind that -- the last reading before the park's commit, so a record another
  road put in place
  during the branch's reading is kept -- still carrying the record, the report records, `pr_number`, and the
  `verification_evidence_*` records, the record set to `null` in the park's own write -- and only behind the anchor
  `/orchestrator continue` replays: `pending_fix_reviewer_comment_id` naming the record's `anchor`, or cleared -- before
  the notice or behind it -- and written back in that same write, so the continue replays the reviewer's feedback to a
  fresh developer. One naming another comment holds the launch: nothing is posted where it stands ahead of the notice,
  and no park lands where it lands behind it -- judged on the comment as read behind the notice, so a repoint there,
  over an anchor already cleared included, is kept as that road wrote it. A move proved behind the notice -- a commit
  that reached the branch, read again there, included -- sets the record to `null` with no park, for the stage's own
  road on the next tick, and the anchor is written as that reading spelled it -- cleared, where another road dropped the
  record and cleared it there; a park another road recorded there is kept as it wrote it, with no park landing over it
  and the record waiting; and a subject or branch that would not read, a notice nothing identified, or an anchor moved
  there writes what moved and the notice's ledger entry and leaves the record for a later tick -- as does a run ledger
  that reads there as the launch owed again, its start written away and its charge standing unstarted under the
  launch's own fingerprint, which the next tick launches, honoring that charge. That commit is decided
  on those records, the anchor, `awaiting_human` and `park_reason`, and the run ledger as that reading spells them, so
  one another road moves after it refuses it with nothing written or reported, and one GitHub never confirmed is found
  by the next tick, standing or not, with no second notice or developer. Before either hook
  launches a record's developer, a `pending_fix_reviewer_comment_id` something cleared since -- the fixing stage's
  bookmark clear, a report settlement writing the bookkeeping it froze -- is written back from the record's `anchor`,
  once the subject is established -- a subject nobody could read writes nothing -- in a guarded commit over the comment
  read again, since the record names the very post: where the report records, `pr_number`, or the record itself moved
  there -- a record another road put in its place -- or a park stands there, or they, the anchor, or the park's flags
  move under the commit, the tick ends with nothing written, posted, or launched. An anchor another road pointed at
  another comment is still held.
  An approval record is acted on only over evidence proved current (`stages/validating/unverified_approvals.py`), and
  only the record of the run's own round, `approved` verdict, and subject -- a run whose record another road replaced
  or dropped is refused, having nothing to prove -- over the claim that record names, never one handed in beside it,
  so a record whose `evidence` is `null` is refused however valid the evidence the pull request carries. Its
  `evidence` claim has to name `verification_evidence_current` exactly -- receipt, revision, and digest -- that
  evidence has to prove current again, its artifact re-read at the recorded `comment_id` has to be the one that
  settled with `passed` holding there, and its commands have to cover every configured `VERIFY_COMMANDS` command
  exactly, exiting 0 -- the proof `stages/validating/approved_evidence.py` takes, and takes again for the arc behind
  the verify gate and behind the approval comment, since the artifact can be deleted or edited on the pull request
  where no record shows it. The claim's own `passed` and `covers` refuse it early and never stand in for the artifact; a
  claim still named by `verification_evidence_pending` refuses as evidence never published; and the pinned comment is
  read last behind the proof, a report record, `pr_number`, the record, or a `verification_evidence_*` record moved
  there refusing it too. A refusal comes back in the words a `reviewer_unverified` park carries, and a proof nobody
  could read -- the pull request, the artifact's thread, or the comment -- holds the record untouched for a later tick.
  The service parks a refused record only once it has held it to its subject and claim again, measured from the comment
  its readiness was proved over, and sets it to `null` where either moved there, for a fresh reviewer; an approval whose
  declaration earned no evidence parks, in the tick its reviewer returned, with no proof asked and in the words that
  tick has for why -- a later tick's refusal names only what is true of every such declaration.
  The approval arc a proved record reaches holds only the record of its own run's round, `approved` verdict, and
  subject, and sets it to `null` in whichever write it makes -- the park a failed verify gate or squash lands, the
  write recording its run where the subject moved behind the gate or behind the approval comment, the squash tail's
  handoff write, or, where the records the tail holds moved behind one of its requests, a write of the comment as read
  with nothing else in it but the ledger entries of what the tail posted -- save where the subject would not read,
  which keeps it; a record another road put in its place is left as it stands. The squash recovery holds none, and a
  record waiting beside the handoff it finishes holds the move to `workflow:documenting` while the handoff record
  ends. One persisted while that move runs lands past it, and the `workflow:documenting` tick that finds a readable
  record waiting hands the issue back to `workflow:validating` before any docs pass. Only the disposition service hands
  a record to that proof -- in the tick its reviewer returned, or in a later one finishing a verdict left waiting
  (`stages/validating/review_resume.py`) -- so every approval the arc acts on is one that proof passed.
- **Verification evidence.** Four additive records and a revision floor, the developer report's shape extended rather
  than forked (`workflow/engine/verification_records.py`). The dispatcher reconciles a recorded transaction, and its
  live producers are three: the returned-verdict disposition, which records the transaction a reviewer's declared
  commands were minted as in the write persisting its verdict; the approval's squash, which records a carry onto
  the head it published -- of its verify gate's run where that binds, or of the evidence the approval rests on -- in
  the write settling its handoff (`stages/validating/squash_evidence.py`); and the finish of a landed automatic base
  rewrite, which records a fresh run of the rewritten head or a carry onto it in the write ahead of its route, the
  evidence it moved past invalidated in the same write (`workflow/engine/rewrite_finish_evidence.py`). The verify
  gate records nothing on its own
  account, and the recovery of a waiting verdict records none, so an issue whose reviewer declared no run and whose
  rewrites recorded none carries none of these keys. `verification_evidence_pending` is one transaction,
  written BEFORE its
  artifact is posted: a receipt (`issue-<n>-verification-<revision>-<nonce>`, which every record's reader holds to that
  record's own revision) and a revision past every one the issue has spent; the report subject's own `repo` / `pr` /
  `branch` / `sha` / `requirements` members, where `sha` is the head the evidence is written for; the review subject
  exactly as `review_subject` spells it (`subject`), about that same pull request and requirements and naming a
  developer report, since evidence answers for the report a reviewer was handed; the witness (`source`,
  `orchestrator-executed` or `reviewer-reported`); the tested commit and its full tree (`tested`, `tree`), which stay
  the commit that actually ran when evidence is carried to another head; the verification context (`context`, the verify
  runner's digest of `VERIFY_COMMANDS` and `VERIFY_TIMEOUT`); the commands that ran as `[command, exit status,
  transcript]`, each one the artifact would publish; and, only on a carry that copied the current evidence's
  transcript, that evidence's receipt (`copied_from`, absent on every other transaction, and damage where it is there
  and not a receipt, `null` included, or missing from a `reviewer-reported` record tested on another commit than its
  `sha`, which only such a copy ever is), which the reconciliation re-reads ahead of the post and again at the
  settlement: that evidence still current, its artifact still the one that settled and carrying exactly the commands
  copied, or the carry is refused. `verification_evidence_current` is the evidence the pull request
  carries: the same binding without the commands, plus the artifact's evidence digest (`content`), the comment it landed
  as (`comment`), and whether at least one command ran and every one exited 0 (`passed`); `null` once invalidated.
  `verification_evidence_history` is the five highest-revision retired records, in revision order rather than the order
  they retired -- each with its receipt, revision, whole binding (the report revision and digest and the complete review
  subject included, since the artifact names only the subject's head), digest, `passed`, `comment` (`null` exactly for
  an abandoned transaction, which never held one), and `retired` (`superseded`, `invalidated`, or `abandoned`) -- an
  index of artifacts that all stay on the pull request. `verification_evidence_handoff` is the receipt of the last
  settled transaction with its pull request (`pr`), revision, target head (`head`), and, where it could be read, the
  label the issue carried as it settled (`under`). `verification_evidence_revision` is the highest revision any
  transaction on the issue was recorded under, raised in the same write as each record, so a revision whose artifact may
  already be on the pull request stays spent after its record is damaged, dropped, or evicted from the history.
  An issue without any of the keys owes, holds, and has spent nothing, and every reader is fail-closed: a record short
  of any member, or holding a value its writer never spells (a receipt naming another revision than its own included),
  reads as none, a history that is `null`, longer than five, or whose revisions do not strictly rise reads as none, and
  an unreadable history is replaced by the next write that indexes a retired record. What an issue has spent is the
  floor raised to any readable record's revision; over a comment that did not parse, a floor present and unreadable
  (`null` included), or a floor missing beside any record (`null` ones included), nobody can say, and nothing is minted
  or recorded. Recording under the receipt already recorded is a retry, accepted as it stands only where it is identical
  and the floor can be read, since its artifact may already be on the thread under that receipt. Any other record is
  accepted only as a new transaction -- a revision past everything spent, so a mint another settlement overtook is
  refused -- that reads back identically, whose artifact renders, and the comment has room for it AND for its whole
  settling write and the later invalidation of the evidence that installs, measured at the widest comment id and label
  with the artifact's ledger entry reserved; a later record abandons a readable earlier one into history in the same
  write, and drops one nobody can read. A settlement is ONE composed write onto the comment the transaction was recorded
  on, and only of the transaction that comment records -- the earlier current record superseded into history, the new
  one and the handoff installed, and the pending record set to `null` -- and a comment id past what the records carry
  settles nothing. A retirement (the current record invalidated, or the stored pending record, named whole, abandoned)
  is composed on a copy and writes nothing where the comment could not carry it; a transaction minted and never
  recorded, or one a later record replaced, is never abandoned. A local `VERIFY_COMMANDS` run binds
  (`workflow/engine/verification_local_runs.py`) only where `is_reusable` vouches for it, it ran on the head its target
  answers for, and its transcript is one the artifact would publish in one comment, measured at the widest receipt and
  revision a record carries -- the room on the pinned comment is left to the recorder; a failed, empty, timed-out,
  dirty, or moved run, or one on another head, binds nothing. The one run asked is the approval's verify gate, by its
  squash (`stages/validating/squash_evidence.py`).
  The dispatcher reconciles the pending record directly behind the developer-report transaction and ahead of the reuse
  guard and the handler (`workflow/engine/verification_transaction.py`), so it is behind every pause, terminal,
  adjudication, outstanding-publication, lease, and auto-rebase-anchor guard, and stands aside -- publishing and
  dropping nothing -- on an issue that is closed, labelled `done` or `rejected`, held by a hard-skip control label, or
  unlabelled. It publishes only once it has PROVED the pull request -- the one `pr_number` pins -- open on the recorded
  branch and standing on the target head, the branch and checkout standing there too, the tested commit and the target
  head each a readable commit in its own right (never an annotated tag peeling to one) carrying the recorded tree, the
  configured context the recorded one, no developer report still owed (by the validating hold's own rule), the bound
  review subject about the target head and equal to the applicable record (`review_returned_subject` for
  reviewer-reported evidence, `review_subject` for orchestrator-executed), the settled report re-read exactly as a
  reviewer is handed it -- `developer_report_current` and `developer_report_handoff` agreeing, and the report at its
  recorded location unchanged under its author -- named by that subject, which passes that reader's own rules
  (requirements the round was due, and a report about the subject's head written against `user_content_hash`, or older
  than a `user_content_hash` that is the subject's own requirements, which only the settlement of the reply that bought
  the round leaves), and the issue's requirements the bound revision. The post is scoped by the receipt, so an
  accepted write whose response was lost is found rather than repeated, and it is made only once the settlement it owes
  is proved to fit: staged at its widest -- the widest comment id and label, the artifact's ledger entry reserved
  against the ledger the comment carries now rather than the one the tick read, and room left to invalidate what it
  installs -- and prepared as the settlement's own guarded commit over the pinned
  comment read afresh (`workflow/engine/verification_publishing.py`), so a comment another road filled since the tick
  read it, or one whose bound records moved, posts nothing. Before the settlement the issue and the pinned comment are
  read afresh: the issue has to be live work still, by the same rule as above, or nothing at all is written; the
  comment has to carry every bound record -- `pr_number`, the `developer_report_*` group (`developer_report_owed`
  included) and `park_reason`, whose report debt a review subject stands only without, `review_subject`,
  `review_returned_subject`, `review_approved_subject`, the four evidence records, and `verification_evidence_revision`
  -- exactly as the tick held them, the whole proof above is taken again over it, and the artifact re-read at the
  comment it landed as has to be exactly this transaction's, not edited or deleted since
  (`workflow/engine/verification_settling.py`) -- and a carry's `copied_from` source still current and as copied
  (`verification_current.copied_source_verdict`). Those are requests of their own, so the comment is read once more
  behind them and has to still carry every bound record as the proof read it -- a subject removed or replaced meanwhile
  refuses the settlement and is kept. Only then is the settlement committed, composed over that last reading as one
  guarded commit whose prerequisites are those bound records and which owns the four evidence records, the revision
  floor -- left as the transaction's record raised it -- and the artifact's entry in `orchestrator_comment_ids`, merged
  into whatever ledger the comment carries: read once more, the comment has to still carry every bound record as that
  reading did, every field the settlement does not own -- a usage total, a watermark, another road's verdict or
  comment ids -- is kept as it reads then, and the whole rendered comment has to fit. A record that moved there, a
  comment that moved under the edit, or a settlement that no longer fits leaves the transaction owed; a comment that
  will not read or was replaced holds the tick with nothing written; and a commit that went out unconfirmed holds it
  too, for the next tick to find either nothing owed or the same transaction to settle over the same artifact, with no
  second history entry. Wherever the settlement does not land over a comment that still reads, the artifact's ledger
  entry is committed alone, where that fits; where that entry finds the comment unreadable, replaced, or no longer
  parsing, or goes out unconfirmed, the tick holds. A reading nobody could take holds the tick; anything a push, a drift
  resume, a fresh reviewer, or fresher evidence answers stands down with the transaction owed. Nothing here parks: a
  record whose revision a settled or retired record already carries --
  a replay its own handoff names, or one a restored comment brought back -- is dropped without a second post or history
  entry, an unreadable record is dropped, and one whose pull request ended, past which a revision was spent, or beside a
  floor nobody can read is abandoned into history. Every retirement the reconciliation makes is one guarded commit
  staged on the pinned comment read afresh -- which has to carry the same bound records as the tick held them -- and
  guarded by that reading: it owns only what it retires (`verification_evidence_pending` and
  `verification_evidence_history`, with `review_approved_subject` for a carry's approval; the pending record alone for a
  replay dropped), so a transaction, an approval, a report or a report debt, a review subject, or a floor another road
  moved before that reading or under the commit -- `null` written where nothing was, or a number respelled, included --
  refuses it with nothing written and the record owed, and every field it does not own -- a usage total, a watermark, a
  returned verdict, another road's comment ids -- is kept as the comment carries it when it lands. A retirement the
  comment has no room for writes nothing and leaves the record owed, measured over that reading and again over the
  comment the commit reads; a comment that will not read or was replaced holds the tick with nothing written; and a
  retirement that went out unconfirmed holds it too, for the next tick to find the record gone or retire it again, with
  no second history entry. A reader relying on the current
  record re-proves all of that and its publication besides: no revision past it spent (`verification_evidence_revision`
  at its own), so a newer artifact posted and never settled supersedes it; the handoff describing it; and the comment it
  recorded still our artifact with every binding member the artifact encodes, the digest, and a `passed` its commands
  earn (`workflow/engine/verification_current.py`). Evidence answers for another head only through a carry-forward
  decision (`workflow/engine/verification_carry_forward.py`) exposed for a head other than the one it answers for when
  that head's full tree, read from the repository, is the tested tree and the configured context is the recorded one --
  patch ids, contribution fingerprints, topic diffs, and rewrite names are never consulted -- while the evidence carried
  is still the latest and published, and either a review subject about the new head is recorded or the review it
  already answers for is unchanged and is the one `review_approved_subject` covers; the carried record keeps naming the
  commit that was actually tested, with the new head as its target, and answers for that review. A local run bound to
  the head it tested is carried by the same rule, save the artifact it never had. The approval squash records one
  (`stages/validating/squash_evidence.py`) -- of its verify gate's run where it binds -- in the write settling its
  handoff, and points `review_approved_evidence` at it in that same write; it takes only the approved review,
  unchanged -- its report revision, digest, and requirements included -- so a review recorded about the new head
  since refuses it.
- **Final-docs handoff.** `docs_checked_sha` + `docs_verdict` (`updated` / `no_change`) set by `_handle_documenting`'s
  success exits, and the verdict an earlier pass left is dropped as the next one begins — every entry shape re-anchors
  `docs_checked_sha` to the head it is about, so a stale verdict beside it would say a pass has finished for a head one
  is only starting on, which the in_review merge gate reads as a head this orchestrator has documented and pings.
  Under `PR_REF_IN_SUBJECT` a pass that publishes re-anchors it once more before the size gate, on the commit whose
  subject it hands that gate, so the hold, the failed-push approval, and the receipt that gate writes each sit beside
  the commit the rest of the record names rather than beside the head the spawn began on; a hold the gate REFUSES
  rather than routes measures, records and publishes nothing, so that anchor goes back to the pre-spawn head. The
  success exits announce first, then persist, then relabel: the notice's id has to ride a write or nothing
  records it, and `in_review` repairs nothing it is handed — its merge gate pings only for a head `docs_checked_sha`
  names with a `docs_verdict` beside it, so a relabel taken ahead of the write would strand the issue there on the
  head the pass began on. `docs_settled_sha` is the head a docs pass produced, written inside the size gate's own
  routed write ahead of that gate's relabel to `workflow:decomposing`: the pass is finished and only the `in_review`
  handoff is still owed, so the tick a settled verdict hands the label back to finishes from the receipt rather than
  reading a branch in sync with its remote as an issue no docs pass has run for. The gate writes it whichever way the
  answer went, so it covers the other tick that can leave a handoff owed — a push the gate ALLOWED, which landed,
  whose process died before that write could record the pass. Read back only over a checkout standing ON the head it
  names — in sync is what a replacement host rebuilt at a moved pull request reads as too. Dropped by every terminal
  docs success in the same write that records it, including a republication that carries the held commit to the
  remote itself — held past that write to cover the relabel behind it, the receipt outlives the handoff whenever the
  write that would drop it does not land, and a later `validating` approval at the same head consumes it and skips
  the docs pass it just bought. So the relabel window keeps no receipt, and it does not need one: what it leaves is
  the record a same-head approval leaves, and the next tick runs the pass rather than handing off on evidence that
  could belong to either.
  `ready_ping_sha` records the head the in_review handler already posted a `:bell:` HITL ping for. Both it and
  `docs_verdict` are keyed on a head alone, so a recorded approval retires both (below): an approval of a new report
  on the head they name would otherwise be read as documented before its docs pass ran, and pinged by nobody.
  `docs_drift_unwind_pending` is set while `_handle_documenting`'s drift block is reconciling and cleared only on the
  relabel back to `workflow:validating`. `docs_drift_unwind_asked_at` rides beside it on the failure road: the id of
  the notice a git step that could not be proved parked with. It is NOT a delivery cursor — no agent runs on that
  road, so the comment that moved the requirements is still unread and `last_action_comment_id` is put back where the
  tick found it — it is the boundary the unwind's silence is kept behind, so only a trusted reply ABOVE that notice
  retries the reconcile rather than the triggering comment doing so on every poll. Additive: an issue parked before
  the field existed falls back to `last_action_comment_id`, which is where that park left its mark.
- **Fix routing.** `pending_fix_at` + per-namespace `pending_fix_issue_max_id` / `pending_fix_review_max_id` /
  `pending_fix_review_summary_max_id` recorded by the `in_review → fixing` route, plus the full
  `pending_fix_issue_ids` / `pending_fix_review_ids` / `pending_fix_review_summary_ids` batch lists. They are hints, not
  watermarks — the in_review watermarks are deliberately left behind so the `fixing` rescan can re-discover the
  triggering comments, and the id lists let `_reconstruct_pending_fix_batch` rebuild the exact triggering batch after
  every reader has advanced past it (falling back conservatively to the max ids for issues parked before the lists were
  recorded). Settling a delivered batch never touches them: an explicit `/orchestrator continue` retry and a genuine
  question or disagreement park both depend on the bookmarks outliving the readers the same round moved. The batch an
  accepted retry rebuilds keeps each surface apart, because the replay is delivered and so is settled: its issue-thread
  half advances `last_action_comment_id` beside the PR-side cursor and its PR-conversation half advances that PR-side
  cursor alone — and what the retry settles is that batch JOINED with the fresh rescan, so the bare
  `/orchestrator continue` the prompt deliberately drops is still recorded as answered.

  The `validating → fixing` route instead records a single `pending_fix_reviewer_comment_id` — the id of the
  PR conversation comment carrying the reviewer's CHANGES_REQUESTED feedback — and does NOT set `pending_fix_at` (that
  key is the route discriminator that drives the review-round reset). `_reconstruct_pending_fix_batch` re-fetches that
  exact comment by id — onto the PR conversation, the surface it was posted on, and outside `filter_trusted`, since it
  is the orchestrator's own reviewer output the author allowlist would otherwise drop — as the validating-route replay
  anchor, quoted with the findings it carries formatted (`validating/feedback_posts.py`), so a post made before
  findings were formatted is replayed concise while the comment and its id stay as posted. The rebuilt batch is what
  the `/orchestrator continue` operator command replays when retrying a session-failure park (see
  [`_handle_fixing`](delivery-stages.md#_handle_fixing-label-workflowfixing)); the anchor is cleared on a
  pushed fix and inside `_clear_pending_fix_bookmarks`. A persisted change request's handoff stages it only in the
  guarded commit that hands the request over, from a post whose id it read or, on a later tick, that it found in the
  words it posts, and launches its developer only while it names the comment the record's `anchor` does (see the
  returned reviewer verdict above).

  `fixing_round_settled` is a bare `true` a report transaction's settlement puts up when the record it settles froze
  it, and it says the one thing that write cannot do for itself: move a label. A settlement closes `pending_fix_at`,
  the bookmarks and `review_round` while the issue is still sitting on `workflow:fixing`, and nothing else on the
  comment says the round is over — the settled report and the code-publication receipt are persistent, so a head a
  pull request stands on for reasons of its own proves nothing about this transaction. It may only ever be RAISED by
  a record: what takes one down is the route that reads it. Two roads freeze it: every report-carrying round of the
  fixing stage, and the reviewer-requested round `_handle_validating` runs inline under `workflow:fixing`. That one
  relabels back to `workflow:validating` before its report is bound, so it ordinarily settles there, where no
  correlation places the mark and the next fixing tick retires it unspent; bound by the fixing stage after a relabel
  that never landed, the mark is what hands that round back. Before it is acted on it is CORRELATED against the
  handoff beside it (`workflow/stages/fixing/round_marks.py`) and refused on an outstanding report, a handoff this
  build cannot read, one settled under any label but `workflow:fixing`, or either route anchor standing — which says
  a newer round opened after the mark went up. Two owners read it, `reporting.py` for the hand-back every
  settlement-driven publication takes and `report_recovery.py` for the round that settled while nobody was looking,
  and both CONSUME it: a mark this stage may not act on comes down unspent, because it is the mark of a round that
  is over either way and only the relabel is withheld. `fixing_round_handed_back` beside it is the receipt of the
  transaction a hand-back already closed a round on, written by that hand-back in the write that takes the mark down and
  durable before the label moves, for the reason the mark is. Written only where a mark was RAISED and the correlation
  placed it: the reading that places one also places every road reaching a relabel on its own reasons, and such a road
  closes no transaction — stamped from there, an unrelated handoff is recorded as handed back and the mark a replay of
  it raises is then refused, over a write nothing reserved room for. It is what makes the mark a claim on ONE
  transaction: the mark falls with that write and the handoff beside it never does — nothing clears a handoff, a
  settlement only replaces it — so a comment whose round closed legitimately goes on carrying a readable
  `workflow:fixing` handoff with both route anchors cleared and no report owed, and a mark written back onto it by hand
  would otherwise be correlated into a second hand-back over whatever landed in between. The room for it is RESERVED
  when the transaction is accepted, beside the code-publication receipt and the comment-id ledger entry and for the same
  reason: it lands on the comment a settlement leaves, so a transaction accepted at the ceiling would settle, raise the
  mark, and then meet a hand-back GitHub refuses — with the mark raised, the relabel never taken, and every later tick
  failing in the same place. Reserved only where the record's own spends raise the mark, since no other route writes it.
  Additive: an issue without it has handed no round back under this record. Every road that can reach a relabel with
  the mark raised goes through that one hand-back: the round's own publication, the recovery's binding, the
  no-feedback bounce that republishes a stranded commit, the retry that lands a failed push, and the tick that finds
  a round settled elsewhere. The stamp is also what the relabel after that write is retaken on, since the relabel is
  not atomic with it: a comment carrying the stamp for its own `workflow:fixing` handoff, with no mark, no route
  anchor and no report owed, is a hand-back whose relabel may never have landed — or one that landed and a later
  anchorless move back onto `workflow:fixing`. `review_returned_subject` tells them apart: while no reviewer has
  returned over that handoff's report the round is still owed its review, and the fixing stage takes the relabel
  again ahead of its scan; once one has, the move back is answered like any other. `review_subject` cannot say this,
  since it names the report a launch the run budget refused as well as one a reviewer read.
- **Crash-recovery anchors.** `discussion_round_branch` + `discussion_round_sha` — the branch a discussion round
  opened on and the SHA it was at, written BEFORE the spawn and surviving every exit the stage takes; a published plan
  moves the pair onto the tip it pushed (that commit is what the stage now vouches for) and only a
  successful relabel out (`_clear_stale_read_only_park`) drops it. It answers two questions, and which one is
  being asked is settled by whether the discussion stage has the issue parked:
  on an unparked issue it means a round ended with no disposition (withheld by a mid-run `paused`, or cut short) and
  comparing it to the branch says whether that round committed; on a parked one it says everything the branch carries
  AT that SHA predates this stage — which is what `relabel_evidence.py` reads to let a discussion held on an
  inherited PR branch relabel to implementing. A park that *did* find a commit keeps the pair for that second reading:
  it is the tip the park tells the operator to reset back to, and the one the guard then certifies, so dropping it
  would strand a PR-backed issue whose only other remedies (reset to base, delete the branch) destroy the PR. The
  branch is recorded beside the SHA because an issue pinned to a legacy `orchestrator/issue-N` ref opens its round
  there, and answering for the slug-namespaced ref instead would report an unchanged tip while the commit sat
  elsewhere.
  `read_only_baseline_sha` — what that anchor becomes when the relabel clears. `_clear_stale_read_only_park` hands the
  certified tip to the implementing stage rather than dropping it, because the fresh-spawn path reads any branch ahead
  of base as a previous dev run whose publication was interrupted (`_has_new_commits`) — and the branch a discussion
  was held on may legitimately be ahead of base already. Without the handover the first implementing tick would skip
  the implementer and republish the inherited commits as the work the discussion just agreed to. It is the anchor
  except where the same handoff moved the branch onto a plan PR's live head, in which case it is that head: what this
  key has to name is where the branch REALLY sits, not which commit the record started from.
  `spawn._recovered_work_present` spends it: while HEAD still sits on that SHA the commits are inherited and the dev
  runs, and once the dev commits, HEAD moves off it and the key is dropped. That is a comparison, so it is spent only
  on a HEAD that was READ — `_head_sha` reports its own failure as `""`, which differs from the certified tip exactly
  as a commit does, and a baseline retired on that reading would skip the implementer and republish the design's
  predecessor as the work the discussion just agreed to. An unread head leaves the key standing and the dev runs, the
  same as a head still on it. `handoff._advance_to_validating`
  spends it too, since an issue leaving for `validating` has published and would otherwise carry the key — and
  everything the key holds — out of this stage with it.
  Standing beside `discussion_plan_sha`, it is also the record that says a handoff was ACCEPTED and nothing here has
  published since, which is a state a crash can leave an issue in for polls at a time: the write lands before the
  developer runs and an interruption drops everything staged after it. While it stands,
  `plan_handoff._reconcile_open_plan_handoff` takes the guard's own reading again on every tick — the same plan
  PR read, the same re-anchor onto what it carries, the same two records written — because the humans still have the
  design on an open pull request and can move its head. Left unwatched, an amendment made in that window reads as this
  stage having pushed: merged, the issue closes as `done` with no developer having run, and unmerged the developer is
  spawned on the checkout the handoff left and its ordinary push takes the amendment back out. A merge alone matters
  with nothing amended, since the freeze below would otherwise start the developer behind a base the plan has just
  landed in. What ENDS the reconcile is the branch and not a record, because a push reaches git before it reaches the
  issue: a tip past the baseline is a developer's work, and a tip that could not be read is no answer at all and holds
  the tick.
  `read_only_anchor_sha` — the head that reconcile is moving the branch onto, written before the move and retired by
  the write that records where it landed. The move has the same window the handoff itself does, one level down: the
  ref is put on the reviewers' head before anything says it was, and the branch a crash in between leaves is a tip
  past the baseline — which the reading above would call a developer's commit, handing their amendment to the
  recovered-work shortcut to push with no agent having run. A marker still standing says the branch is where this
  stage was putting it, so the move is simply made again; nothing is spawned between the two writes, so no developer
  can have committed under one. `handoff._advance_to_validating` clears it beside the baseline.
  `disposition._run_left_commits` reads the
  same floor at the other end of the tick, so a dev that answers with a question instead of committing parks on it
  rather than having the inherited commits published as its work. Both the cleared park and this key are written
  BEFORE the spawn, because a mid-run pause or a shutdown interruption returns without writing pinned state at all:
  staged, the acceptance would be lost and the next tick would read the park and anchor back and convict the
  developer's own commit. An unspent baseline also holds the branch out of the base refresh (`_issue_skips_base_sync`
  again), since a rebase would move HEAD off the certified SHA while the inherited commits it names are still there
  and the next spawn would read them as an interrupted dev run. `_publish_committed_work` retires it — there is
  committed work to publish either way at that point — so the freeze ends with the stage that needed it rather than
  following the issue through review.
  `pending_auto_base_rebase_push_sha` — set to the pre-rebase local HEAD immediately BEFORE
  `_rebase_base_into_worktree`; cleared on every exit that leaves the branch where the attempt found it. A non-empty
  value on entry means a previous tick rebased and died
  before the post-push write, and the workflow's recovery (`workflow/engine/rewrite_recovery.py`) keys off it to
  either no-op, push the recovered head, or park, on the record described below. While it stands, the dispatcher
  holds the stage handler back (`recovery_holds._recovery_holds_dispatch`): a refresh that could not reach the
  recovery — a failed base fetch, a pull request that would not read — would otherwise hand a reviewer, a developer,
  or a decomposer a replay no push has published. An anchor beside a live adjudication is first offered to it
  (`workflow/engine/rewrite_takeover.py`, see [Base refresh](#base-refresh)): a pair whose records describe one replay
  is handed over, the attempt and any `auto_base_rebase_*` park it left retired in one write with the replies that only
  asked that park for a retry recorded read, and the anchor no longer holds anything; a handoff write nobody confirmed
  holds the tick for the next to prove again, and a park the handoff leaves that nothing on the adjudication's road
  answers holds it until a human replies to that park. On a label the refresh
  does not drive — the read-only stages it skips and a generation an
  adjudication is still deciding included — nothing is waited on: the dispatcher takes the refresh's own ineligible
  road itself, a clear or the stranded park, and over a checkout that is not on disk goes straight to the park, since
  no reading of where the branch stands can be taken. The stranded park asks for the label back and a reply both,
  since that park is the refresh's own and a relabel alone never releases it -- save beside a live adjudication, whose
  guard restores its label: there it asks for the `pending_auto_base_rebase_*` and `late_rewrite_*` fields, and the
  park's own flags, to be reconciled by hand, past which the adjudication runs and asks for its usual decision. On a
  label the refresh drives, the hold
  is lifted only for a late claim the reconciliation answers — a frozen pair, an approved push — since that freezes
  the refresh out and the reconciliation is what ends it, and it is asked again once the reconciliation has run, so a
  claim it spends leaves the anchor holding the tick. Every other record and park holds, since each is ended by a
  stage handler the hold keeps back: a park some stage left is taken down on a reply by a handler that runs on into
  the agent it was holding back, and a timeout, a reading nobody could take, a read-only baseline, or a collapse
  mid-rewrite is ended the same way. Beside an anchor none of them freezes the refresh out, so it answers the anchor
  under them with the recovery alone — no reply spent, no rebase of its own started — and a finish leaves each where
  its owner put it. A pull request that merged or closed is asked for ahead of every park, the refresh's own
  included, and ends the attempt's whole handoff there rather than leaving the anchor to hold its handler back.
  A checkout whose HEAD names a commit this store cannot read is held until the refresh has
  answered it — a base lag it cannot count over a pinned anchor is reset and parked, trusting no comparison of what
  the attempt left, and a reset git refuses keeps every record — and one that is not on disk is restored for the
  next refresh to walk, since the handler that would recreate it rebuilds it from the local branch, which may still
  be the unpublished replay. The anchor is also what tells the approval that interrupted attempt wrote from a
  stage's, so the refresh is not frozen out of finishing its own route (see [Base refresh](#base-refresh)).
  `pending_auto_base_rebase_rewrite_pr` + `pending_auto_base_rebase_rewrite_stage` — the TERMS of the same attempt,
  written in the anchor's own statement, before `git rebase` is allowed to touch the branch. They say which
  publication the attempt was made for, which is not a thing the anchor can prove: read off the issue on the tick
  after a crash they would compare today with today, and a relabel or a repoint made while the process was down would
  pass as the dead tick's own.
  `pending_auto_base_rebase_rewrite_sha` — what that rebase produced, written on the reading the publication itself is
  decided from and before the first step that can leave the replay standing. It is the only thing that can say the
  divergent checkout a later tick finds is that attempt's own work: a rebase REPLAYS the branch, so a worktree
  somebody rebuilt, an operator's reset, and a branch pointed at other work all present the same shape and all satisfy
  the same lease.
  The group is read whole or not at all and typed against the same shapes every other late field is — an abbreviation
  or a value that is not a whole git object id is no head, a pull request that is not an identity is none, and a stage
  no publication is entered from describes an attempt this workflow never made. Absent, IN FLIGHT, and DAMAGED are
  three answers rather than one. A comment carrying none of the three is an attempt from before this record existed,
  or one whose anchor is all that was ever pinned. A comment carrying the terms and no head is the window between git
  returning and the write that records what it produced: nothing names the commit in the checkout, but the terms still
  say which publication the attempt in flight was for. And a comment that claims the record and cannot show it — a
  member taken out, terms missing under a head that is there, a head that is not a commit — is neither, because read
  as either one it resembles, exactly the state nobody can vouch for would take a road reserved for one that can.
  Because the write that ends an attempt blanks these fields rather than removing them, a group of nulls is the record
  nobody wrote and a member carrying something beside one that does not is the record something took apart.
  `pending_auto_base_rebase_rewrite_base` — the base tip that replay was made onto, written in the same write as its
  head and from the same reading, and blanked with the rest of the attempt. It sits outside the group above: an
  attempt recorded before it existed is still whole, and simply names no base. The evidence a landed head is routed
  with is held to it (`workflow/engine/rewrite_evidence_proof.py`): a head counted level with a base says nothing
  about which base, and one rewound or repointed under the head after the rebase leaves it level with a commit it was
  never replayed onto, so the base it is counted against has to be this very tip -- and an attempt naming none, or a
  value that is not a whole commit id, proves no base at all.
  `pending_auto_base_rebase_announced_sha` is the last member and covers the last window a finish has: everything a
  finish announces — the notice on the pull request, the `base_rebased` event on both sinks — goes out before the
  relabel, and the write that clears this record goes out after it, so the head it has already said it published is
  recorded in between, while the anchor and the replay still stand. A tick lost there comes back to a comment that
  says the announcement was made rather than to an attempt that looks unfinished, which is what stops a second
  `base_rebased` on the stream and a second notice on the pull request for one publication that happened once. BOTH
  finishes write it and for the same reason — the refresh's own publishing tail, which announces the rebase it just
  pushed, and the recovery, which announces one an earlier tick left — since neither is distinguishable afterwards
  from an attempt that never got that far. The report debt the landed head leaves (`developer_report_rewrite_debt`)
  rides the same write, so it is durable before the attempt is cleared or the issue relabelled. It is
  read by PRESENCE, like every other checkpoint here: the key standing at all says a finish announced THIS attempt's
  replay, so a value naming any other head — or naming no commit — is a mark something took apart rather than an
  answer a reader may give as "nothing was announced".
  `auto_base_rebase_failed_verification` sits beside the group without being a member of it: the notice a landed
  head's failed configured verification is owed — an object of `head`, the rewritten head the run failed on, and
  `notice`, the notice's whole text (the failing command, how it failed, and its output's tail) — written by the
  finish's evidence write before the notice is posted (`workflow/engine/rewrite_finish_failures.py`), so the failure
  outlives a post GitHub refused or never answered. A finish that finds it naming the head it finishes runs nothing
  again and posts the recorded notice only where no comment of ours on the pull request carries it already, and the
  retirement that routes the head writes it `null`. It is additive and read fail-closed: absent, `null`, or any other
  shape is no record, which a finish answers by deciding afresh, and one naming another head is no record of this
  landing's.
  The whole group is dropped by the one write that ends an attempt — the reset that puts the branch back, the no-op
  that moved nothing, the relabel that takes the issue out of the refresh's reach, the finalize that publishes, and
  the handoff of an unpublished replay to the late generation adjudicating it (which stages
  `late_auto_rebase_replay_sha` in that same write, and retires any `auto_base_rebase_*` park the attempt left) all go
  through the same clear — so no road can leave a member behind. That clear is held to the reset LANDING wherever one
  is made: a reset that failed abandoned nothing, and the comment is then the only account of where the checkout may
  be standing, so nothing is dropped and the next tick still has an anchor to come back with.
  **The whole record is live: every write, the clear, and the readings.** The terms and the anchor go down before
  `git rebase`, the replay goes down before the dirty check, both finishes mark what they announced, and every ending
  drops the group; the three answers and the presence test on the mark are what the workflow's recovery decides on.
  An unpublished checkout is
  classified on the three-valued read: absent falls back to the divergence counts, in flight is proved by what the
  contribution is — or, past the permit's own grant, by the permission that grant persisted, cross-bound to the
  anchor, the terms, and the accepted pair before it is called outstanding — and damaged and disowning both park. The
  terms are held to the publication the tick holds before any road that posts a notice or files an event, forgiving
  only the `validating` relabel a finish makes beside a mark naming the head in hand. The MARK is read by presence on
  every road that would push, call an attempt unstarted, or clear one under a relabel: it stands only where a
  publication landed, and no finish announces the anchor. A checkout back ON the anchor with a replay recorded, a
  permission unspent, or any mark standing is a rebase something undid, finished as that rollback rather than
  cleared. An issue relabelled off the refresh-driven set is cleared only where the attempt left nothing a clear would
  strand — a checkout still on the anchor, no replay or damaged record, no mark, and no permission still owed — and
  parks once otherwise. A settled rotation a later adjudication moved the exemption past is not a permission owed:
  it is never cleared, and read as one it would strand every untouched attempt the issue makes. Its parks read
  `auto_base_rebase_push_failed` where the push, the remote, or an announced publication the remote lost is what
  refused, and `auto_base_rebase_failed` where the pinned comment is; the foreign-publication, the
  unfinished-route, and the stranded relabel parks leave HEAD and every record exactly where they stand.
  **The post-publication route is live too.** The recovery hands every head the pull request already carries, beside
  how far the transfer got, to the workflow's landed road (`workflow/engine/rewrite_landed.py`), which asks
  `landed_recovery` why it may not finish one, and eligibility's open-PR gate hands `terminal_handoff` every
  anchored attempt whose pull request merged or closed. A landed head is finished only where something the attempt wrote
  vouches for it — the record naming the head, or, for a replay the permit alone published, a permission bound to this
  attempt — and only where the comment accounts for it: a foreign publication, a mark naming another head, a tree not
  provably clean beneath a verdict, a mark beside a permission still outstanding, and a receipt or debt that does not
  account for the transfer each park with HEAD and the anchor where they stand. A landing the road no longer finds where
  the recovery's fetch classified it -- the branch moved since that fetch, or the checkout and the branch moved together
  onto another head before the checkout was read as the candidate -- makes nothing and parks nothing, since every
  voucher above is about the head the fetch classified, and the next tick classifies what it then finds. An OUTSTANDING
  permission over a landed head is settled through the leased no-op, entered on the anchor with the permit as its only
  licence and read back for the rotation, so the exemption, its identity, the receipt, the paid debt, and the settlement
  proof go down in the push tail's one write; that receipt is leased against the commit itself, and a SETTLED transfer's
  bound permission is what dates it on a later poll. A settlement whose `late_transfer` record never reached the sinks
  is reported before any finish, from the proof the comment kept, and the proof is dropped durably behind it, so a later
  poll reports it again only where that drop did not land. A mark
  naming the head in hand owes only the route and the clearing write — no second notice and no second `base_rebased` —
  spending a released reply, relabelling only where that relabel did not already land, and leaving the route to the
  rebase a base that advanced again still owes. A pull request that merged or closed over an attempt ends its whole
  handoff in one write: the attempt and its debt go, a permission whose rewrite is the head the pull request ended on,
  pushed from this anchor onto that pull request, settles from that head with its receipt, and any other permission is
  dropped on the rollback's rule. Both permit-only roads, the reissued push and the leased no-op, are entered into the
  size gate whatever `DECOMPOSE` says, since the permit is asked over the publication entry only the gate freezes.
  The whole journey is proved on a real repository:
  [`tests/git/base_sync/test_real_git_journey.py`](../../tests/git/base_sync/test_real_git_journey.py) takes an
  oversized `workflow:validating` candidate through the real gate, a `single`, and its authorization, advances the
  base, and has the reviewer re-run over the leased replay with the exemption and receipt rotated onto it and nothing
  measured, adjudicated, run, or said on the issue a second time; and
  [`tests/git/base_sync/test_real_git_journey_recovery.py`](../../tests/git/base_sync/test_real_git_journey_recovery.py)
  loses the tick at every durable boundary of that rebase and requires the next refresh to reach the same finish.
  [`tests/git/base_sync/test_real_git_journey_handoff.py`](../../tests/git/base_sync/test_real_git_journey_handoff.py)
  advances the base under the file the change edits instead, so the replay contributes something else: over
  consecutive production ticks the gate adjudicates it afresh with the pull request left on the authorized head, the
  human's authorization of the replay publishes it under the lease with its report owed, and the reviewer runs on
  over it -- while somebody else's push to the pull request refuses that publication, and a tick lost at each write of
  the handoff comes back to the same adjudication with no reset, no reused verdict, and no developer run -- an
  operator's retry before it included, on the publication's road and the recovery's. A pair an earlier build stranded
  under its park comes back to it too, the retry that park asked for spent with the attempt rather than resuming the
  developer, while a reply that says more reaches the developer as guidance; and a park another owner left, stood
  before the gate measured the replay or after, holds the adjudication until a human answers it.
- **Counters / timestamps.** `retry_window_start` + `retry_count` (24h fresh-spawn budget shared between implementing
  and decomposing, with `retry_cap_stage`, `retry_cap_continued`, and the sentence the park owes the thread beside
  them once it runs out — `retry_cap_notice`, or `late_park_notice` where a late adjudication is what ran out, since
  that park is taken by the late owner and rides its write; see [The retry budget](#the-retry-budget)),
  `silent_park_count` (dev-session silent-park counter), `dev_resume_count` (per-dev-session resume budget; once it
  reaches `DEV_SESSION_MAX_RESUMES` the session is retired and respawned fresh from durable state, reset to 0 on every
  fresh spawn), `merged_at` / `closed_without_merge_at` terminal stamps, and the per-round stamps `last_question_at` /
  `last_discussion_at` the two operator-applied conversation stages set on every run they settle.
- **Usage meter.** `issue_agent_runs` + `issue_total_tokens` + `issue_total_cost_usd` + `issue_cost_sources` are
  per-issue cumulative counters folded in by `engine/issue_usage.py`'s `_accumulate_issue_usage` at each developer
  (implementing), reviewer
  (validating), decomposer (decomposing), question, and discussion run site from the `UsageMetrics` that
  `_run_agent_tracked` parses. `issue_total_tokens` sums input +
  output + cache-read + cache-write (codex `cached_tokens` is excluded — it is already part of `input_tokens`, so
  summing it would double-count); `issue_total_cost_usd` sums each run's `cost_usd` (`None` costs from `no-usage` /
  `unknown-price` runs add nothing); `issue_cost_sources` is the sorted distinct `cost_source` set a terminal verdict
  reads to mark `(est.)` (any `estimated`) or unpriced `unknown` (any `unknown-price`). The increment rides the
  handler's existing single `write_pinned_state`, so an `interrupted` run that returns without writing never accrues.
  Where a returned reviewer's write is laid over the pinned comment read again (`stages/validating/review_comment.py`)
  and committed over that reading (`stages/validating/review_writes.py`), a total another road folded a run into since
  the tick read the comment -- while the reviewer's subject was resolved, while it ran, or between that reading and the
  commit -- is added to the reviewer's own fold, and the tags join, rather than either road's fold being written away.
  The decomposer / question / discussion stages additionally skip the fold for `interrupted` runs, so even
  their dirty/commits inspection park (which does write pinned state) records no counter.
- **Agent-run ledger.** `agent_run_allowance` + `agent_runs_used` + `agent_run_reservation` are read by
  [`run_ledger_values.py`](../../orchestrator/workflow/engine/run_ledger_values.py) and mutated by
  [`run_ledger.py`](../../orchestrator/workflow/engine/run_ledger.py). The
  [`run_ledger_models.py`](../../orchestrator/workflow/engine/run_ledger_models.py) owner supplies the typed
  `AgentRunLedger` snapshot (the configured ceiling, the allowance in force, the count spent, the launch
  outstanding, and what is left of the allowance). `agent_run_allowance` is the ceiling this issue is held to; absent
  — which is every issue nobody decided anything special about — `MAX_AGENT_RUNS_PER_ISSUE` governs and is read live,
  and a recorded `0` says unlimited exactly as a configured `0` does. `agent_runs_used` is monotonic: it is charged
  upward and never decremented, zeroed, or rolled over, it goes on counting while the ceiling is off (an unlimited
  setting stops nothing turning runs away, not the runs), and a missing one starts from the `issue_agent_runs` meter
  above rather than from zero — the two count the same unit, so the larger of the pair is what a read answers.
  `agent_run_reservation` is the launch currently holding a charge, as one of two stable phases: `reserved` (charged,
  not yet spawned) and `started` (the spawn happened), with `agent_run_fingerprint` naming which launch that is — the
  digest of the request's own identity (role, stage, backend, spec, resumed session, review round, retry count), never
  of its prompt, which is rebuilt every tick and would make one launch look like a new one every poll. The charge is
  taken before the spawn, so a run that crashed, timed out, or was killed mid-flight is still spent; settling a
  reservation drops the phase and the fingerprint together, never the charge. `agent_run_owed_started` is the count
  the last launch owed exactly once was owed at — a persisted change request's developer, at its `handed` count —
  written in the very write that moves that launch to `started` and by nothing else, so it says that launch reached a
  process whatever other runs were charged beside or after it; additive, absent until such a launch starts, and not
  kept by a projection, which rebuilds an issue with no launch outstanding. This owner decides nothing and posts
  nothing — the reading is taken and acted on at the tracked spawn boundary
  ([The agent-run circuit](#the-agent-run-circuit)), and the one writer of `agent_run_allowance` is the operator
  command below.
- **The agent-run-limit park.** `awaiting_human` + `park_reason="agent_run_limit"` + `agent_run_limit_notice` +
  `agent_run_limit_displaced` are
  staged by [`run_limit_state.py`](../../orchestrator/workflow/engine/run_limit_state.py), then persisted and reported
  by [`run_limit.py`](../../orchestrator/workflow/engine/run_limit.py), which is handed the ledger reading — so the
  park quotes the numbers the refusal was made on rather than
  whatever the setting has become since. It is the human-intervention state a spent lifetime ledger leaves, and
  unlike the retry cap beside it there is no window under it to elapse: a lifetime total is spent once and no clock
  returns it, so the park IS the ending rather than a pause in it. The durable half goes down before a word of it is
  said, for the reason the retry cap's does — a notice on a thread no pinned state backs is one nothing would ever
  reconcile. `agent_run_limit_notice` is a record rather than a bare sentence: the message, the `allowance` in force,
  and the runs `spent` against it. The reason under this park never varies, so the pair of counts is the only thing
  that can tell one exhaustion from another — a recorded sentence about the reading the ledger still shows is kept
  **verbatim** (the thread is searched for exactly that text, so rewording it would find nothing and say it twice),
  and one about any other reading is replaced, since it quotes an allowance or a spend the issue has moved off.
  `agent_run_limit_displaced` is the park this one went up in front of — `{"awaiting_human": bool, "park_reason":
  str | null}`, read off the durable state the circuit refused on and recorded only when the park is TAKEN (a park
  re-taken over itself would record itself). It is what the grant below puts back.
  Before it is said again the thread is read for it, and only a comment **this orchestrator wrote** above the
  `last_action_comment_id` watermark counts as the receipt (`github.comments.authored_by_us`, the same author check
  every park-notice reconciliation gates on); a thread that could not be READ is its own answer and the tick says
  nothing, since the sentence it may already carry is the one about to go out. The park is held by the DISPATCHER
  (`_run_limit_holds_the_tick`), one step behind the pair that run — an authorized restart and a cancelled cycle's
  own cleanup — and ahead of everything else, because every road below it is a stage's and each answers
  `awaiting_human` with the park it was written against: a resume on the next trusted reply, a hold waiting on
  guidance, a classifier that refuses a command carrying none. None of those buys back a run. The hold replays the
  sentence the park still owes before it returns, since nothing below it runs to say one, and it is the one guard
  there that steps aside for work that has ENDED — what an ending reaches below is a terminal that ends the issue
  rather than a road that spends anything on it, and refusing it would leave the issue permanently mid-ending. Two
  facts say so: a closed ISSUE, which the object in hand shows, and the recorded PULL REQUEST having merged or been
  closed, which it cannot. What the second means depends on the **label** the tick was routed on: on
  `workflow:implementing` a settled `discussion` plan is the agreement that licensed the build rather than the build
  ending, so it is carved out there and nowhere else — `discussion` itself drains that same pull request through its
  own terminal, and behind a permanent park nothing comes back for it. That reading costs a request per parked poll,
  fails *open*, and is taken **before** the command below, which mutates. A later tick
  that meets the same explained park says nothing and records `standing`. All three fields are additive and default
  safe: an issue recorded before them, or hand-edited into a shape none fits, reads back as unparked, owing nothing,
  and displacing no park rather than as a tick that raises.
- **The one command that lifts it.** `/orchestrator add-agent-runs N`, owned by
  [`orchestrator/workflow/engine/run_grant.py`](../../orchestrator/workflow/engine/run_grant.py) over the request
  [`run_grant_request.py`](../../orchestrator/workflow/engine/run_grant_request.py) hands it, and asked by the
  same dispatcher hold, because the ledger is spent by every role at every stage and no one handler is where a human
  would say it. It is read only while THIS park stands on an OPEN issue (a command on any other park, or on a running
  issue, is a ceiling nobody was held to; a closed one is let past to its terminal before the read is taken), only
  past `last_action_comment_id` from an author `ALLOWED_ISSUE_AUTHORS` trusts, only
  once the park's own sentence has been said (a command read before it would be a command written before the question
  was put), and only as an exact positive whole number no
  larger than `MAX_RUNS_PER_COMMAND` (50) — leading zeros are dropped first, so `007` is seven and a digit string too
  long to be inside the bound is turned away *before* `int()` sees it, since the interpreter refuses to convert one
  past its own limit and a request that raised would be neither granted nor refused. The last command in the unread
  batch is the request. A valid one writes
  `agent_run_allowance` = `used + N` — an absolute ceiling rather than an increment, so a tick that dies between the
  receipt and the write buys the same runs again rather than a second `N` on top of them — puts `awaiting_human` and
  `park_reason` back to the park `agent_run_limit_displaced` recorded (none, where nothing was recorded) and drops that
  record and any `agent_run_limit_notice` beside it, ratchets the watermark past both the
  command and its own acknowledgement, records `granted`, and returns the tick to the stage handler its label names.
  Putting the displaced park back is what makes the run a human just paid for the one the issue was stopped for: a
  resume the circuit refused on a reply finds that reply still unread and is run again on it, from its own frozen
  batch — rather than an ordinary spawn quoting it with no record, or a reviewer on `workflow:validating`.
  That watermark is derived from what the tick actually read — the last comment of the batch the command came out of,
  walked forward only over comments this orchestrator wrote (by recorded `orchestrator_comment_ids`, else by
  `_ORCH_COMMENT_MARKER` + author) and stopped by the first that is not. A comment posted between the batch read and
  the receipt is therefore left above the mark for the next tick, since a watermark is how every stage decides what
  is unread and a comment swept under it is lost rather than delayed. And the batch is not answered at all where it
  BEGINS below a notice of ours: the bounded run-limit notice leaves a reply a refused resume was handed under the
  mark, and the watermark is one number, so the walk starts at the mark, crosses our own comments, and stops at that
  reply. The command is left unread with its receipt on the thread, and every later reader cuts it out: the
  `workflow:implementing` roads through `implementing/parked_replies.py` (so a later bare `/orchestrator continue` is
  still the retry or refusal it would be alone, and it is no last word on the authorization park), the frozen reply
  batch on both stages, the in_review seed walk at approval, and the in_review and fixing feedback scans.
  Every other request leaves `agent_runs_used` and `agent_run_allowance` exactly as it found them, keeps the park,
  and posts one receipt carrying `<!--orchestrator-add-agent-runs-refused:issue=N:comment=M-->`. Both answers are
  marked that way — the acknowledgement carries `<!--orchestrator-add-agent-runs-granted:issue=N:comment=M-->`; each
  is scoped to the comment that asked and checked for on the thread (author included) before it is written again,
  so a write that failed after a post that landed is recognized rather than answered twice. An untrusted request is
  answered with nothing at all: a reply is a comment somebody else's word paid for, and consuming the thread for one
  would spend the watermark a trusted operator's command is read against. A bare command is also kept out of the
  `user_content_hash` (`run_grant_request._is_bare_command`, one of the filters in
  [the drift hash](delivery-stages.md#user-content-drift-detection)), since the tick that answers it is the tick the
  stage handler runs on, and out of the guidance a late adjudication resumes its developer on (`late_content_replies`),
  since a number is no requirement to revise against. Nothing here returns a spent run.
- **Terminal usage verdict.** `_format_issue_usage_verdict` renders those counters into one visible receipt line
  (`:receipt: this issue: N agent runs · T tokens · $X.XX`, `(est.)` appended when any `estimated` contributed,
  `unknown` in place of the figure when an `unknown-price` run leaves the total incomplete). It returns nothing when
  no run was counted, so a terminal with an empty meter posts no receipt. Every terminal surface renders it before its
  single `write_pinned_state`: the PR merged / rejected finalizers (`_finalize_if_pr_merged` and the
  `_pr_terminal_stops_the_tick` that decides both endings off one reading,
  `_drain_review_pr_terminals` — all three arcs, including the open-PR/manually-closed-issue rejection — and
  `_finalize_if_issue_closed`, all on the `workflow/engine/terminals.py` owner the stage leaves import
  directly) post it as a standalone `_post_issue_usage_verdict` comment, the `umbrella`
  all-children-done branch appends it to its close comment, the closed-`question` terminal posts it when
  question-stage counters accrued, and the `discussion` stage's plan-PR terminal posts it on each of its three
  endings — the merged plan, the plan closed unmerged, and a close with no plan PR at all — since that owner
  composes those same three arcs directly rather than through either entry point. Reusing `_post_issue_comment`
  keeps the receipt's comment id tracked in
  `orchestrator_comment_ids`. This is a read-only verdict — no budget breaker or control behavior gates on it.
- **Late generation.** The additive `late_*` group an oversized committed candidate is adjudicated under — cycle and
  generation identity, root / current issue and lineage depth, the declared scope, the frozen candidate and base SHAs,
  the measurement and the readings that did not produce one, the reconciliation phase, the local content fingerprints,
  the held pull request, how the gate was entered and what it was entered from, the external-resource ledgers, the
  owner read a finished run still owes, the cancellation marker, and the pending-restart marker. The one commit an
  accepted candidate publishes under sits beside that group rather than in it, since clearing the generation is
  exactly what it has to survive. Every key, and what an absent one means, is in
  [Late generation state](#late-generation-state) below.

The legacy `codex_session_id` key (written before `dev_agent` existed) is still honored on read by `_read_dev_session`:
it round-trips to `spec="codex"` with no args so an older orchestrator's pin keeps running on codex.

### The retry budget

Fresh agent spawns are charged to one per-issue budget — implementing and decomposing share it, because both spend
the same issue's day of tokens — and it is decided on
[`retry_ledger.py`](../../orchestrator/workflow/engine/retry_ledger.py), which every stage's gate reads.
[`retry_budget.py`](../../orchestrator/workflow/engine/retry_budget.py) owns the shared parking form and continuation;
[`retry_park_state.py`](../../orchestrator/workflow/engine/retry_park_state.py) holds the durable obligation and
[`retry_notices.py`](../../orchestrator/workflow/engine/retry_notices.py) delivers and reconciles it.
The ledger answers a decision and posts nothing: what a refusal
implies durably is staged into the caller's own pinned state and rides the write that caller was going to make
anyway, so a tick that dies between the two leaves the budget as it found it. What a caller then DOES with a refusal
is written once beside the gate (`_charge_or_park`) for the stages whose park carries nothing of their own — the
initial decomposer's and the implementer's fresh spawns — and by the stage itself where the park has to carry state
the budget never sees, which is the late adjudication and its live generation.

- **The accounting.** `retry_window_start` + `retry_count`, against the bound `MAX_RETRIES_PER_DAY` sets. The window
  opens at the first counted attempt and reopens once 24h have elapsed. Only fresh spawns count: a resume on a human
  reply and a recovered worktree's push are an unblock signal and carry-over work. An unbounded budget (`0`) counts
  nothing and drops the pair as it passes, so turning the budget off is not a pause on a window — turning it back on
  opens a fresh one rather than refusing out of a count nobody could spend while there was no budget to spend it
  against.
- **The park.** `awaiting_human` + `park_reason="retry_cap"` + `retry_cap_stage` (the stage whose spawn ran out; the
  budget is shared, so the flag alone cannot say what the human is being asked about). The gate asks that park before
  it asks anything else, and while it stands nothing gets past it that is not a human — not the clock reaching the
  end of the window, and not an operator widening `MAX_RETRIES_PER_DAY` or turning it off, which is a setting change
  rather than an answer to the notice. What ends it depends on which stage the parked issue is in. Where a stage
  routes the park to a resume, a reply on the thread takes the flag down as its own side effect. The two stages that
  spend this budget hold it instead, each ahead of every road of its own that would walk past a park — the drift
  reset, the kill switch and the resume on `workflow:decomposing`; the parked-continue classifier, the drift check
  and the resume on `workflow:implementing`, the last of which would take the flag down on any reply at all and start
  a session nothing charges. On both, nothing but the renewal below lifts it, and the issue keeps untouched
  everything the tick never reached: the manifest, the children, the locked session and its spec, the `pr_number`,
  the frozen candidate, and a late generation's whole record
  ([decomposing](delivery-stages.md#_handle_decomposing-label-workflowdecomposing),
  [implementing](delivery-stages.md#_handle_implementing-label-workflowimplementing)). The late adjudication that
  runs under `workflow:decomposing` holds it a third time, on its own road and for its own reasons — the tick that
  meets one there never proves the frozen pair, never re-marks the pull request the candidate stands under, and
  never reads the thread as an answer to a question about the requirements
  ([the late run](#the-late-run)).
- **The notice.** `retry_cap_notice` — the sentence the park still owes the thread, written **before** a word of it is
  said and dropped only by a post that landed or by the park ending. The order is the point: a notice on a thread that
  no pinned state backs is one nothing would ever reconcile, and the window under it would roll over a day later with
  the issue running again beneath a comment saying it had stopped. What the park routes the tick past is what makes
  the record load-bearing, so the sentence is replayed at stage entry (`_replay_owed_notice`, called by
  `_handle_implementing` and `_handle_decomposing` ahead of every gate) until the thread carries it — and a stage that
  answers a command on this park waits for that sentence before it reads the thread at all, since a delivery moves the
  response boundary past everything written under the old one and words that predate the question are no answer to it.
  Spelled without the mention the delivery prefixes, and kept verbatim for as long as the park stands: the thread is
  searched for exactly that text, so a later refusal under another stage or a retuned cap may not reword it. Before it
  is said again the thread is read for it, so a comment that landed under a pinned write that then failed is recorded
  as said rather than repeated — and only a comment **this orchestrator wrote** counts as that receipt, since the
  sentence is plain text anybody on a public thread can copy (the comment-side receipt rule in
  [`security.md`](../security.md#the-snapshot-ref-namespace); the author is read through
  `github.comments.authored_by_us`, the author check the marker lookup and both park-notice reconciliations gate on). A
  thread that could not be READ is its own answer, distinct from one read and found empty: the notice stays owed and
  the tick says nothing, because a request that failed inside the window where the sentence is already posted would
  otherwise produce exactly the duplicate this protocol exists to stop.

  A park the LATE adjudication takes carries the same sentence in `late_park_notice` instead — that mode already owns
  a notice field, because everything one of its parks leaves standing is a generation's record that has to ride the
  same write ([late generation state](#late-generation-state)). The persist-before-post order, the verbatim match,
  and the authorship rule are the same there; a sentence carrying no marker is one anybody could otherwise paste back
  to mark a park explained that nobody ever explained. The unreadable-thread reading is the one thing that is **not**
  the same, and deliberately: that field answers a failed read the way it answers an empty one, so the sentence is
  said again. It costs one repeated comment where this owner would have stayed silent, and it buys the property the
  late mode needs more — the notice always reaches the thread, which is what moves the response boundary before any
  command on that thread is read as an answer. Its own reasoning is under [late generation
  state](#late-generation-state).

  Which field a `retry_cap` park under `workflow:decomposing` carries therefore depends on which owner took it, and
  the hold that keeps that park reads **both**. A park the shared parking form took — on an issue that had not
  entered the size gate, or before the late owner existed — is said by the stage-entry replay, and that replay is the
  one step that can stand down leaving the sentence unsaid. The late hold runs immediately after it, so treating its
  own field as the whole question would find the park explained, take a second read that may succeed where the first
  failed, and buy an adjudication with words written before the human was ever asked.
- **The renewal.** One explicit step on this owner, and the only thing that renews a budget while its park stands. It
  routes no comment itself: a caller establishes that the park stands and that the words it is answering are a trusted
  `/orchestrator continue`, and then calls it. The three `retry_cap` owners are the callers that do
  (`_park_owns_the_tick` under `decomposition/`, `decomposition/late_retry_cap.py`, and `implementing/`, each taking
  the command with whatever else its comment carries and consuming the batch it read); under a stage that has no such
  caller a park is lifted by the reply that resumes the session instead. What the step grants is a single attempt: it
  reopens the window at that moment and clears the park with its stage and notice, and the caller retires the locked
  session in the same write, keeping the agent spec — a fresh spawn is what was bought, and the spawn pins an id of
  its own only when the run hands one back, so an id left standing is one the next reply would resume. The late
  adjudication is the one caller that retires nothing there, and for the same reason rather than a different one: its
  pre-spawn record already drops `late_session_id` for every run that is not continuing a question a human has
  answered, so the attempt a command buys opens a fresh conversation before the agent starts. On
  `workflow:implementing` the gate asks that again for every spawn a grant pays for, since a grant outlives the tick
  that took it and the budget is shared: a restart, or a continuation bought on a `decomposing` park, reaches the
  spawn with a session no `implementing` park ever saw. A whole fresh day would let one reply spend the cap over again
  with nobody watching. The attempt is written down as itself — `retry_cap_continued`, a count of granted spawns
  nobody has spent — rather than as a counter to compare against the setting when the spawn is finally asked for,
  which would make it worth nothing once an operator turns `MAX_RETRIES_PER_DAY` off and several attempts once they
  widen it. An issue carrying that count is answered from it and from nothing else: no window is renewed under it and
  no cap is read, and a grant with nothing left refuses like any other exhausted budget, so the next attempt is a
  human's word again. Until it is spent, the stage's other roads to an agent stand down for the gate — on
  `workflow:implementing`, the body-edit resume — since a resume passes no gate and would run the attempt while
  leaving it on the issue to be bought again. The count is dropped where the rest of the budget is — the handoff the
  publication reaches once the issue moves on (`handoff._reset_implementing_counters`) — and refunded with the
  counters by the one write that goes out before an agent starts: the late adjudication's pre-spawn record
  (`_ACCOUNTING_FIELDS`), so a run the close latch, a pause, or a shutdown declines leaves the attempt there to be
  taken again. The two initial-spawn `retry_cap` owners need no refund for that case: the grant is written before the
  spawn and the spend rides the tick's own later write, which a mid-run `paused` or a shutdown never makes.
- **The audit.** One `retry_cap` event per step, `phase` distinguishing them — see
  [`observability/event-streams.md`](../observability/event-streams.md#audit-event-log-event_log_path).

`retry_cap_stage`, `retry_cap_notice`, and `retry_cap_continued` are additive and default safe: an issue recorded
before they existed, or hand-edited into a shape none of them fits, reads back as no park stage, nothing owed, and no
spawn handed out — never as a tick that raises. The grant is the strictest of the three, since it is the one field
that hands out a spawn, and it is the one whose ABSENCE is the safe reading rather than its content. Absent — never
continued, or cleared back to null by the handoff reset — the issue is answered by the configured budget, as
every issue that never hit the cap is. Present, it governs: a number is read into the range a continuation writes (a
bigger one buys the same single attempt, a negative buys nothing), and a value that is not a number at all proves no
attempt and hands out none, which parks the issue and asks a human rather than falling through to a whole window's
worth of spawns off the strength of something somebody typed.

### The agent-run circuit

The lifetime ledger is charged at the one place every role reaches an agent through:
[`orchestrator/workflow/engine/run_circuit.py`](../../orchestrator/workflow/engine/run_circuit.py), asked immediately
around the sole low-level `run_agent` call inside `_run_agent_tracked`. A gate written into each spawning handler
would be a gate the next handler is added without; there is exactly one call that starts an agent process, so a
charge around it is one every role, stage, and cycle pays. Every launch names the `AgentRunBudget` defined in
`engine/run_charge_state.py` — the issue a
charge is written on, and the caller's own `PinnedState` — and the parameter is **required**, so a spawn road that
omitted it would not compile rather than quietly spend runs nothing counts. All eight spawn sites (the decomposer's
fresh and resumed runs, the late adjudicator, the question and discussion rounds, the developer's fresh spawn and
its resume, and the reviewer) pass one, and
[`tests/workflow/engine/test_spent_ledger_spawns.py`](../../tests/workflow/engine/test_spent_ledger_spawns.py)
drives the real handlers against a spent ledger so an unwired road is caught as a spawn that happened.

- **Two durable writes, both before a process exists.** `reserved` (charged, nothing invoked) then `started` (the
  invocation is what happens next). A charge taken behind the spawn is one a crash, a timeout, or a shutdown kill
  collects for free. A tick that dies between the two writes leaves `reserved`, and the launch it was taken for
  reuses that charge; a tick that dies anywhere after `started` leaves a run nobody can prove did not happen, so the
  next launch charges a new attempt. Nothing settles a charge by giving it back. A spawn spends one pinned read and
  one or two pinned writes on this — two when it charges, one when it takes over a pending `reserved` — which is
  work proportional to agent runs rather than to ticks, so it does not move the idle per-tick floor in
  [`configuration.md`](../configuration.md#github-rate-limits).
- **The launch is matched, not just the phase.** A standing `reserved` is reused only when `agent_run_fingerprint`
  names this same request; a charge some other road recorded is one this launch never paid for.
- **Durable state is re-read, and only the circuit's own fields come back.** The charge is written onto a fresh
  `read_pinned_state`, and exactly the keys that write changed are merged into the caller's object. Everything else
  the caller is holding is mid-tick — a reviewer spec staged ahead of the spawn, a moved reply watermark, a charged
  retry slot, a session id about to be replaced — and belongs to the handler's own single write at the end of the
  run. The merge is what keeps that write from putting the charge back the way its read found it.
- **Nothing is invoked unless the charge landed.** An unreadable or unparsable pinned comment, a refused write, and a
  spent allowance all return an `AgentResult` with `interrupted=True` **and `invoked=False`**, and emit no
  `agent_spawn` / `agent_exit`: there is no run to bookend. Handlers already read the first through
  `_ignore_if_interrupted` and return without writing durable state. Only the spent allowance is a decision about
  the issue, so only it takes the park above — on the freshly read state, whose durable write the park owner makes
  itself — and the dispatcher's hold stops the issue on the next tick.
- **`invoked=False` is not the same claim as `interrupted`, and four roads need the difference.** The initial
  decomposer, the late adjudicator, `question`, and `discussion` inspect the checkout *before* they ask about
  interruption, deliberately: a run the shutdown sweep killed can have written before it died, and a contaminated
  tree is an operator's to see whether or not the run counted. A launch that never started wrote nothing, so a tree
  dirty from an earlier run — or a `HEAD` that will not resolve — is not its doing, and a `decomposer_dirty` /
  `late_worktree_mutated` / `question_dirty` / `discussion_unreadable_worktree` park in its name would **replace the
  durable `agent_run_limit` park the refusal had just taken** with a reason about a process that never existed. Each
  of those roads therefore asks `guards._ignore_if_never_invoked` first, ahead of every reading it would otherwise
  classify the run by.
- **A launch owed once is held to it on the circuit's own readings.** A caller whose launch is owed exactly once names
  it (`OwedLaunch`): the lifetime count it is owed at — a persisted change request's developer, handed at `handed` —
  and the caller's hold on it, the requests its standing takes beyond the pinned comment (`resolves`) and a judgment
  of each reading of the comment (`stands`). The circuit writes that count as
  `agent_run_owed_started` in the same write that moves such a launch to `started`, and on the fresh read the charge is
  taken on, that record naming the count it is owed at — where the caller's own state does not carry it — is that launch
  already made by another road after the caller last looked: nothing is charged, written, or invoked, and the answer is
  `invoked=False`, as it is where the caller's hold says the launch no longer stands on that reading. A count merely
  past it proves nothing, since a reviewer or any other road's run moves it just the same. The starts this circuit
  merged onto the caller's state are its own, so a continuation of the same launch — a poisoned session's fresh retry,
  an AGY recovery prompt — is charged as usual, and a `reserved` charge taken for this very launch is still honored. The
  start is written over a reading of its own, taken behind the charge and behind the requests the caller's hold
  resolves, and only while that reading still carries this launch's `reserved` charge, records no start of it by another
  road, and still stands by the caller's hold: staged over the reading the charge was taken on, it would write back a
  start or a charge another road landed in between — a second process invoked, the count run backwards. A refusal there
  invokes nothing and leaves the charge standing `reserved` for the launch it was taken for.
- **What is charged is a process, not a tick.** A developer resume that lands on a transcript the backend has lost
  buys a second spawn in the same tick — a fresh one, in the same worktree — and pays for it, because it is a second
  run. A run the shutdown sweep killed and a run an operator paused mid-flight are charged too: both cost the same
  compute as one that finished, and only the disposition is thrown away.
  [`tests/workflow/engine/test_charged_launches.py`](../../tests/workflow/engine/test_charged_launches.py) drives
  every developer road — the fresh implementation, the resumes `implementing`, `fixing`, `documenting`, `in_review`
  and `resolving_conflict` make, and the poisoned-session retry behind them — plus the fresh reviewer round, and
  reads the spend back off each issue's own pinned comment on the far side of the handler's write.
- **The caps that were already there still refuse first.** The 24h retry budget, `MAX_REVIEW_ROUNDS`, and
  `MAX_CONFLICT_ROUNDS` each park ahead of the spawn, so a tick they turn away reaches no boundary and spends
  nothing; `DEV_SESSION_MAX_RESUMES` refuses the resume rather than the tick, retiring the transcript before the
  charge so what is paid for is one fresh spawn. The lifetime ledger is the backstop under them, not a replacement
  for any of them, and a cap that fired only after the charge would spend a run on work nothing ran.
  [`tests/workflow/engine/test_capped_launches.py`](../../tests/workflow/engine/test_capped_launches.py) drives each
  one against an issue whose ledger has room to spare.
- **The three roles that talk pay the same meter.** The decomposer's fresh spawn and its awaiting-human resume, the
  question stage's opening round and its resume, and the discussion stage's opening round and its resume are six
  roads to an agent, and a road can reach the boundary naming an issue that is not the one it is spending.
  [`tests/workflow/engine/test_charged_conversations.py`](../../tests/workflow/engine/test_charged_conversations.py)
  drives all six through their real handlers and reads the spend back off each issue's own pinned comment — on a run
  that finished, one the shutdown sweep killed, and one an operator paused mid-flight. The late adjudicator is a
  seventh road and not a dispatched handler, so its case sits beside it in
  [`tests/workflow/stages/decomposition/test_late_charged_run.py`](../../tests/workflow/stages/decomposition/test_late_charged_run.py).
- **The charge carries nothing else out of the tick with it.** Each resumed round marks the batch of replies it quotes
  as read BEFORE it spawns and leaves that watermark unpersisted on purpose: a round that never reports is replayed,
  and it has to be replayed against the same replies rather than against an answer already recorded as read. The late
  coordinator holds the retry slot it charged out of its own pre-spawn write for the same reason. Both sit inside the
  window the two charge writes land in, so the merge that carries back only the circuit's own fields is what keeps
  them unpublished — the paused-round cases in the two modules above are what hold it.
- **Each durable step is reported to both observability sinks.** `reserved`, `started`, the park a spent allowance
  takes, and the wider ceiling an operator command buys are one `agent_run_budget` family written by
  [`orchestrator/workflow/engine/run_budget.py`](../../orchestrator/workflow/engine/run_budget.py) — always *after*
  the write that makes the step durable, so a refused write records nothing and a launch reusing a standing
  `reserved` records only the start it paid for. Every record carries the whole ledger reading it was taken on, and
  the two charge phases carry a `reservation_id` pairing the bounded head of the same fingerprint the phase is
  matched by with the `used` count that charge moved — the fingerprint alone repeats across charges of one launch
  shape, and the count is what makes the id name a charge — so the tick that charged a run and the tick that spawned
  on it join. The contract is in
  [`../observability/event-streams.md`](../observability/event-streams.md#agent-run-budget-records-both-sinks).
- **What the number actually buys is measured end to end.** Every owner above answers for its own step, and none of
  them answers the question the setting is written in: how many agent processes one issue can start before something
  stops it.
  [`tests/workflow/engine/test_lifetime_journeys.py`](../../tests/workflow/engine/test_lifetime_journeys.py) walks a
  real issue through the loops that have no natural end — a fix answered by a review answered by a fix, a review round
  reset by a recovered conflict, a review round reset by a base synchronization, a session retired and replaced every
  round, and an issue moved back to `workflow:decomposing` and out again — running it once per tick under a small
  allowance and summing what each tick spawned. The two reset loops are entered on a round the reviewer has already
  spent and the tick itself is what puts it back, so what is asserted is a reset that happened rather than one a
  fixture staged; the base refresh in particular rebases, force-pushes, hands the issue back to `workflow:validating`
  and resets the round while starting no process at all, and the ledger is exactly where it found it. Every other cap
  is pinned wide for the length of a walk, because each of them is a setting the environment can carry and any of them
  left live could be the thing that ended the walk instead. The runner stops at exactly the configured total on every
  journey — under the issue's own allowance and under `MAX_AGENT_RUNS_PER_ISSUE` for an issue carrying none — the
  park's sentence is said once however many ticks reach it afterwards, a trusted `/orchestrator add-agent-runs N` buys
  exactly N further starts and no more, and a request past `MAX_RUNS_PER_COMMAND` buys none. The total is read back off
  the issue's own pinned comment through a client rebuilt from nothing else, which is what a restarted process would
  have.
  [`tests/workflow/engine/test_lifetime_compatibility.py`](../../tests/workflow/engine/test_lifetime_compatibility.py)
  holds the three things the ceiling may not change: an issue that predates it starts from `issue_agent_runs` rather
  than from zero, a stage cap that is spent at the same time still parks its own way with the lifetime count
  untouched, and a closed issue's terminal still drains — posting the receipt for what the whole issue spent and
  leaving both meters and the park exactly as it found them. The adjudicator's own sequence is
  [`tests/workflow/stages/decomposition/test_late_lifetime.py`](../../tests/workflow/stages/decomposition/test_late_lifetime.py),
  which freezes one fresh candidate after another over the same issue and shows the ledger — rather than the day's
  spawn budget, pinned wider than the sequence is long — ending it, plus the restart that projects a new cycle and no
  new runs; the exact-SHA exemption policy is asked of an issue with runs to spare and of one with none in
  [`tests/workflow/stages/implementing/test_late_gate.py`](../../tests/workflow/stages/implementing/test_late_gate.py),
  since a spent lifetime is neither a way past the size gate nor a reason to re-adjudicate an accepted commit.
- **There is no second road to a process.** The gate is worth what the number of places a run can start makes it
  worth, so the shape is also read off the source rather than only driven:
  [`tests/repository/test_agent_spawn_boundary.py`](../../tests/repository/test_agent_spawn_boundary.py) holds the
  whole chain — `run_subprocess` named only by the backends, `run_claude` / `run_codex` / `run_agy` named only by
  the runner that dispatches between them, and `run_agent` named only by the tracked
  boundary that calls it — and holds that call to `_run_agent_tracked` itself, with the circuit asked on a line above
  it. A reference counts rather than a call, because a spawn bound into a variable is invoked where its name is no
  longer written.

### Late generation state

The `late_*` keys are the late size gate's own group, and they are **additive**: an issue that never entered the gate
carries none of them and reads back as an absent generation, so no migration reaches a live issue and a handler that
reads and writes late state on every issue leaves a legacy pinned comment exactly as it found it. The keys are spelled
once, on [`orchestrator/workflow/late_split/keys.py`](../../orchestrator/workflow/late_split/keys.py) —
`LATE_STATE_KEYS` is the whole of what one GENERATION owns inside the pinned comment, `read_late_generation` /
`write_late_generation` on the [`state`](../../orchestrator/workflow/late_split/state.py) owner beside it are the
round trip through them, and `clear_late_generation` is defined as dropping exactly
that list and nothing else. The late keys that deliberately sit outside it all do for the same reason — each is
written so the generation CAN be cleared and would be worthless if the clear took it. `late_exempt_sha` and the
semantic identity beside it, both described below and mapped against the rotation between them in
[Exemption identity and rotation](#exemption-identity-and-rotation), live on the
[`exemption`](../../orchestrator/workflow/late_split/exemption.py) owner; the `late_rewrite_*` authorization that
says a rewrite was allowed to carry one of those exemptions over lives on the
[`rewrites`](../../orchestrator/workflow/late_split/rewrites.py) owner, and outlives the generation for the same
reason the exemption does — the grant is written a whole publication before the receipt that would spend it; the
`late_override_*` terms an operator authorized one oversized publication on live on the
[`overrides`](../../orchestrator/workflow/late_split/overrides.py) owner, and outlive it because they are what a
generation is cleared AGAINST — a clear that took them would send the authorized candidate back into the
adjudication a human already answered; `late_retired_cycle_id` and the two-phase terminal record beside it live on the
[`endings`](../../orchestrator/workflow/late_split/endings.py) owner. The typed record the
group round-trips through is `LateGeneration` on the `models` owner beside
it, containing frozen `PublicationContext` and `LateObligations` records. The state reader and encoders map those
components onto the flat pinned keys below. A write with no `late_cycle_id` records only what the issue still owes —
the two external ledgers, if either
holds anything — and drops the rest rather than keeping a half-record no audit line or child lineage could be
correlated to. Every field is read defensively: a hand-edited or older value that cannot be typed reads back as
absent rather than raising on a tick that has committed work to reconcile. Which reader a field goes through
is the field's own contract rather than its Python type — an identity has to be positive, a measurement non-negative,
a depth inside the lineage, a flag literally `true`, a source stage one of this workflow's own labels, a measurement
failure one of the steps `git/measurement/` names, a restart target one of the two labels a restart may apply, and a
rewrite kind or phase one of the bounded vocabularies the `rewrites` owner publishes — with that owner's source
stage narrower still, since only the five stages that push onto a pull request the remote already carries can be
the stage a rewrite was entered from.
The hex fields are read at their exact lengths: a frozen commit is a whole git object id (40 or 64), because nothing
here ever records an abbreviation, and a local fingerprint is a whole SHA-256 digest (64), because a truncated one is
not a hash anything could be compared against. Only a real integer counts as a number at all: a bool, a float, and
a numeric string are each a value nothing wrote. So a `late_threshold` of `-1` beside a `late_additions` of `0` does
not make an unmeasured candidate report as oversized, a `"false"` string does not arm a cancellation or a pending
restart, and prose in a `late_candidate_sha` never becomes live state — and what a read refuses, the next write drops
rather than preserving.

- **Identity.** Minted by the size gate, at the moment it freezes a candidate: the cycle is this issue's own while
  one is live and the number after `late_retired_cycle_id` otherwise, and the generation counter advances with every
  candidate frozen inside a cycle — which is what keeps a verdict recorded against an earlier commit from reading as
  an answer to this one. The lineage beside them comes off `late_ancestry_*` wherever a split wrote one, so the bound
  applies at the depth the issue was really born at.
  `late_cycle_id` and `late_generation` are monotonic and never reused, so a record naming cycle 2
  always names the same attempt; `late_root_issue` and `late_current_issue` place the issue in its lineage; and
  `late_lineage_depth` is 0 at the root and bounded by `MAX_LINEAGE_DEPTH` (3, a safety invariant no configuration
  reads). A depth at or past the bound — including one an edit put there — reads as "may not split", so the deepest
  child a split can create must resolve as one change or ask a human. A depth that cannot be read *at all* is the
  same answer rather than the root's 0: it reads back as unknown, an unknown depth may not split, and the write
  leaves it unknown, so a damaged field on a lineage already at the bound cannot buy it another generation and the
  next pass cannot normalize the gap away. The only thing that puts a depth back to 0 is a restart, whose fresh cycle
  is a root again.
- **Frozen evidence.** `late_scope` is the declared scope this generation owns; `late_candidate_sha` and
  `late_base_sha` are the exact commits a reconciliation may act on (a recorded SHA is the evidence, never the current
  HEAD or base); `late_threshold` and `late_additions` are the measurement, which trips strictly above the threshold,
  so a candidate exactly at the configured value is accepted. The threshold is `MAX_ADDED_LINES`
  ([`configuration.md`](../configuration.md#cadence-and-budgets)) as it stood when the generation was recorded, and
  the additions are what `git/measurement/` counted between those two commits, so a retuned setting cannot re-judge a
  generation already under adjudication. `late_phase` names the reconciliation boundary reached —
  `measuring`, `holding_plan_pr`, `adjudicating`, `owner_check`, `snapshotting`, `splitting`, `superseding`,
  `cleaning_up`, `cancelling`, `restarting` — so a tick that crashed mid-step reconciles that step rather than
  starting a new one. It is a boundary marker rather than a resume token: the owner-read claim every retry passes
  through rewrites it to `owner_check`, so a step that has to know whether it already ran keys on its own durable
  fact instead — the ledger entry for the snapshot and the branch, the recorded `children` for the children, and
  `decomposed_at` for the one comment a split owes its parent.
- **Measurement retries.** `late_measurement_miss_count` and `late_measurement_failure` are the record of a reading
  that did *not* happen: how many consecutive readings this CANDIDATE has lost — across generations, since a base the
  remote would not name records none and the next reading of that same commit freezes afresh under a new one — and the
  `MeasurementFailure` step a NOTICE about it named (`base_unreadable`, `base_absent`, `candidate_unreadable`,
  `candidate_absent`, `diff_unpinnable`, `diff_failed`, `diff_unreadable` — one of the two vocabularies
  [`orchestrator/git/measurement/models.py`](../../orchestrator/git/measurement/models.py) owns). The second is
  written by the roads that TELL somebody and by no other, so it reads as "the sentence on this thread names this
  step" rather than "the last reading stopped here": recorded by a quiet miss instead, it would be a notice nobody
  made, and the miss that finally spends the bound would find its own step already there and hand the issue over
  without a word. The `measurement_failure` on the emitted record is a different field answering the other question,
  and the two are deliberately not kept in step: every `late_failure` this gate writes — the quiet misses included —
  names the step THAT reading stopped at. A stream is read by somebody counting causes, so it reports every reading;
  the pinned field is read by the guard deciding whether to speak, so it reports what was said
  ([`../observability/event-streams.md`](../observability/event-streams.md#late-split-records-both-sinks)).
  They are durable because nothing else remembers a miss — every tick is a fresh process, so a gate counting in memory
  would either re-read a permanently broken pair forever or spend a human on the first reading a fetch happened to
  interrupt — and the ceiling a bounded retry is held to is `_MEASUREMENT_MISSES_BEFORE_PARK` (3),
  spelled on
  [`orchestrator/workflow/stages/implementing/state.py`](../../orchestrator/workflow/stages/implementing/state.py)
  beside the silent-park bound. Only the two steps that name the TRANSPORT are counted against it — `base_unreadable`
  and `base_absent`, a remote that would not answer for the base branch and a fetch that did not bring the object back
  — because those are the ones that clear themselves. Misses 1 through 3 write the pair and the incremented count,
  emit the typed `late_failure`, log at WARNING and stop, with no `awaiting_human`, no `park_reason`, no comment and no
  step on the PINNED record — the emitted one names it either way — so the next tick re-enters the same pair by itself
  on both roads and spawns nothing; the fourth takes the `late_measurement_failed` park, records the step it is about to
  name in the same write as that count, and mentions a human once. What that mention says is the member and a line
  written for the operator holding the issue — which of a remote, a token, a throttled request, a checkout, or a planted
  attribute file they are looking at, and, for the remote read, the fetch and the two diff steps, the
  `orchestrator.git_plumbing` channel their invocation is logged under — with whatever the failing step wrote for itself
  carried up beside it, already scrubbed of the credential by the transport that ran it. Every other member still parks
  on its first miss, since re-reading a candidate this host does not hold or a diff nothing can pin buys the same
  answer, and so does a record nobody may act on at all: the pair is proved usable before its transport is retried —
  everything a reuse needs except the base itself, which is the one field the failure being retried leaves absent. The
  retry WRITES the record back, and the
  mint behind it keeps the record's cycle, scope and spent readings while re-stamping the issue number, the ceiling
  and the boundary from the process running now — so unproved it would adopt a reading taken against another issue
  under this one's identity, or re-judge a generation that lost its ceiling against whatever `MAX_ADDED_LINES` has
  been retuned to since, either of them ready to publish here the moment the base came back. Past a measurement park
  of ANY cause the pair goes on being re-read once a poll on ONE of the two roads: the post-publication
  reconciliation, which runs ahead of every handler on the five stages that publish onto a pull request the remote
  already carries and asks nobody first. A park taken before publication is re-read by nothing at all — it owns every
  tick until a trusted bare `/orchestrator continue`, which clears the latch and the reason ahead of the gate and so
  buys one more counted attempt, whose own miss is answering a human and is said out loud. Each reading retaken with
  nobody asked is announced at most once per thing there is to say: one that stops at the step
  `late_measurement_failure` already names repeats a sentence the human cannot answer any faster, so the tick is held
  silently and no further miss is counted. That is the whole reason the field is written by the roads that ANNOUNCE —
  without it a candidate this host cannot peel, or a diff nothing here can pin, would mention the same people once a
  poll for as long as it took them to fix it. A reading that stops at a *different* member is not a repeat: it is a
  different next move, and nothing else would ever say so, so it is announced once and takes that field's place in the
  write the notice rides out on, which makes the reading after it a repeat rather than a second announcement; no miss
  is counted for it either. Silent to the THREAD and to nothing else: the typed `late_failure` still reaches both
  sinks on every one of those readings, each naming the step that reading stopped at, since the stream is the only
  place they exist at all and a run nobody can break down by cause reads like a pair nobody is looking at; and a base
  id the remote finally names is written down even then, because it is the exact object every retry after it asks
  for. And the silence is scoped twice over: to a park a human is still WAITING behind — the latch rather than the
  reason beside it, since a resume consumes the one and leaves the other standing — and to the pair that park was
  taken over. A handoff made UNDER a park is the one road where those flags cannot answer at all: the park held
  across it is put back whatever the seam refused for, so a measurement park taken inside one never outlives the
  tick that took it. There `late_measurement_failure` alone carries the silence, and it has to — every poll of an
  authorization park re-enters that seam, so a base that never comes back would mention the same people once a
  poll for as long as the park stood, and those notices alone would fill `orchestrator_comment_ids` until the
  earliest evicted from it read back as somebody's guidance: a developer paid to answer the orchestrator's own
  sentence, over a watermark that swallowed the operator's command on the way. A
  fresh candidate, which is what guidance answered with, retires it and starts its own bound rather than having its
  first miss swallowed by one; so does a reason whose latch a resume already spent. That retirement rides the durable
  write that records the fresh candidate, because the two are read back as one: nothing on the comment says which
  commit a park was taken over, so a crash between that write and the verdict would leave a park over one commit
  beside a record naming another, and every later reading of that pair would be held silently against a bound it never
  reaches. A base that IS reached puts the count — and only the count — back to zero in the write that records the
  pair: reaching the base is not the last step a reading can stop at, and the member beside the count says what the
  thread was TOLD, so dropping it there would announce the diff failure behind it afresh on every poll. The member
  goes where every one of those steps is behind it — the verdict a reading that HAPPENED settles, which clears it and
  the count together in the write it settles on, before that record becomes the one an oversized candidate is
  adjudicated from — and it goes with the record itself wherever a small candidate retires one. Until then a notice
  naming another step is what replaces it. The park is retired by that same verdict rather than by the gate's own
  door, since entering the gate is not answering the question the park was taken for and a retirement there would
  durably unpark an issue whose next reading can miss again, as
  [`delivery-stages.md`](delivery-stages.md#_handle_implementing-label-workflowimplementing) describes. The count is
  read as a non-negative whole number and the failure as one of that vocabulary's own members, so a hand-edited count,
  a bool, or a `LateFailure` spelling in the failure field reads back as no miss recorded rather than as one a retry
  would count. Both are scoped to the pair frozen beside them and go with `clear_late_generation`: a candidate that
  moved is fresh work whose reading nobody has lost yet, so its misses start at zero rather than inheriting a count
  taken over commits nobody measures any more — while a base the remote would not name records no base at all, so the
  same commit frozen afresh under the next generation keeps the count it has already spent and the bound stays
  reachable. Absence is the same answer — no misses and no failure is what every pinned comment written before the
  pair says, so the write leaves both off rather than spelling that state a second way.
- **Local fingerprints.** `late_title_body_hash`, and `late_comment_hash` beside the `late_comment_watermark_id` it
  covers from, are what tell a scope edit apart from a trusted answer arriving after the late baseline. They are local
  by design: the global `user_content_hash` above keeps its single baseline and its meaning unchanged, so no fingerprint
  moves a baseline the re-decompose and dev-resume routes read. Who counts is that hash's own trust filter, asked
  through the same predicate — the pinned-state comment, the orchestrator's marker and its recorded ids, third-party
  bots, and every author outside `ALLOWED_ISSUE_AUTHORS` are dropped before anything is digested, so nothing an outsider
  posts shifts a fingerprint, becomes guidance, or moves the watermark. A comment with no usable id is dropped beside
  them, because the watermark is the only thing that ever consumes one. The three fields move together or not at all:
  advancing the watermark without the digest would leave a prefix nothing had hashed, and advancing the digest alone
  would let the comments it covers arrive as fresh guidance a second time. The watermark only ever rises, so a deleted
  comment cannot lower it and replay conversation an agent already answered, and the digest is taken over the counted
  prefix rather than trusted to the watermark — a comment rewritten in place moves no id at all, and reading that as
  drift is what keeps an edit with no new comment behind it from being lost. Both fingerprints absent is a generation
  whose baseline has still to be taken, which is why "no baseline" is a separate answer from "the requirements moved":
  an absent digest equals nothing, and reading that as an edit would park the first tick of every adjudication. What
  that first tick takes is held to the issue-wide `user_content_hash` instead: the baseline covers the longest prefix of
  the thread that, beside the title and body as they now read, reproduces the recorded hash, so a comment past it — one
  no stage has consumed — stays uncounted and reaches the developer whole, while a reading no prefix of which reproduces
  it moved since the developer last worked against it and parks as `late_content_drift` — on a baseline that counts no
  comment and holds `late_title_body_hash` to the recorded `user_content_hash` itself, so the reading stays drifted
  until a human answers and every trusted comment reaches the developer whole with that answer. The one exception is
  the edit taken back: a hash that covered a comment is one no title and body alone reproduce, so a drifted reading of
  that baseline is searched for the covering prefix again, and one found retakes the baseline on it and clears the
  park as any revert does. An issue with no
  recorded hash has recorded nothing as read, so its first baseline counts no comment at all, and every trusted comment
  on the thread reaches an agent whole before anything records it read. Nothing records `user_content_hash` for it,
  since nothing was consumed; a quiet reading the adjudication carries on over is kept as `observed_user_content_hash`
  instead, which leaves every later comment or edit as drift for the stage the issue reaches next rather than something
  that stage's first poll takes as its initial baseline. Every late baseline taken this way, and every consumption,
  sets `late_baseline_bounded`. A generation without it was baselined over the whole thread and may count comments no
  stage consumed, which cannot be told once the title or body has moved, so it gives up what it counts before anything
  is compared — drifted or not. With a hash recorded it is baselined again as a first reading is, over the covered
  prefix or as a drift park counting no comment; with none it keeps its title and body fingerprint and counts no
  comment. Either way those comments reach an agent before a split, handed on by the reading or by whatever answers
  the drift park, rather than certified over, lost to the umbrella's first poll, or orphaning its children. Every path
  that ACTS on a reply moves the shared
  `last_action_comment_id` with the local watermark, because two readers walk the same thread: a question answered, a
  candidate certified, a stalled revision re-read, or a developer resumed are all comments this mode has spent, and
  leaving the shared one behind would hand them to the later validating → in_review handoff as fresh PR feedback —
  routing the pull request to `fixing`, or resuming the developer on input it already handled. It moves to the highest
  *trusted* comment folded in, so an untrusted one sitting above it stays unconsumed exactly as it does on every other
  resume, and it is a one-way ratchet. The same write records `user_content_hash` too, for a reader past both of them:
  the drift check of whatever stage the issue reaches next. It is the hash the late reading itself froze over the title,
  body, and comment batch it was taken from — under the global filter, so operator commands the local digest counts are
  left out — and never a second read, so a comment or edit that arrived after the reading is still drift for that stage.
  Without it an umbrella a late split made would read guidance a developer revision already answered as an edit on its
  first poll, orphan the children it was just handed, and decompose the same work again. Only a consumption moves it,
  and each of these leaves it unchanged: a first baseline, which records the local fingerprints alone;
  an unanswered `late_content_drift` park, whose notice may move the shared watermark past itself; and a developer run
  that was paused, killed by a shutdown, refused by the run circuit, or ended by a close latched before the resume or
  during the run — or whose CLI stopped before it worked, on its quota, any provider refusal (`API Error:` of any
  status), or a failed exit with nothing said, which is reconciled and parks over guidance still unread.
  Nothing writes it without a consumption: an issue with none has the reading an adjudication carries on over kept as
  `observed_user_content_hash` (above), which moves no baseline.
  The trusted continue that lifts a `retry_cap` park consumes its reading whole — the words beside the command are owed
  the adjudicator it buys (below), and a generation whose first late baseline is still to be taken takes it here, over
  what the issue-wide baseline covers — unless the reading shows drift under a baseline that exists, withholds guidance,
  or is one the recorded hash no longer reproduces, where it moves the shared watermark alone. What counts as a *reply*
  is a third reading again, taken against the higher of `late_comment_watermark_id` and the shared
  `last_action_comment_id` above — which every announced park advances past the notice it posted, making it the response
  boundary a park needs. A comment written before a park is not an answer to it, so a park that fires while somebody is
  mid-sentence is not resolved on the next tick by the sentence they had already sent. The trusted guidance in that gap
  — past the local watermark, at or below the shared one, on a generation that has taken its baseline — is *withheld*,
  and no consumption folds it until a developer has been handed it: every developer revision quotes it, and whatever
  ends the park it sat under — a revert, a certificate, an answered question, a retry-cap continue, an authorization, a
  continue on a stalled revision — or finds no park standing resumes the developer with it, rather than spending it on
  an adjudication consumed for ahead of spawn gates that may stop it or on a publication whose next agent reads only a
  bounded excerpt. A continue refused while its park stands moves the shared watermark alone, leaving the local
  fingerprints and `user_content_hash` where they were. What each comparison earns is in
  [`../workflow/roles.md`](../workflow/roles.md#what-a-late-adjudication-is-asked-and-what-it-may-answer).
- **Owed replies.** `late_owed_replies` is the ordered list of trusted comment ids this generation consumed on an
  adjudication's behalf — the answer that reopened a categorized question, and the words beside a retry-cap continue —
  that no run has yet been handed whole. The adjudicator reads the thread through the bounded excerpt of its tail every
  conversation-carrying prompt shares, and both consumptions land ahead of its spawn gates, so without the list a long
  reply would be recorded as read — `user_content_hash` included — while the agent it was spent on saw only its end, or
  nothing if a gate refused the run. Every late run quotes the owed replies whole after that excerpt until one has
  answered them. An adjudicator repays them only with a verdict recorded over them, in the write that records it; a
  developer revision only with the candidate its reconciliation re-measures off its answer, in that write, and never
  where it timed out or its CLI stopped before it worked. Every other run repays nothing — refused at a gate, paused,
  killed, timed out, stopped on its quota or a provider refusal, answering with a reply nothing could parse, or a
  revision whose reconciliation parked, a question over an unchanged commit among them — so the run its park earns is
  quoted them again. A recorded answer is not reused while any reply is owed, since it was taken without it. The list
  lives on the generation, so a revision carries it forward and the retirement a split's handoff writes drops it, and it
  is read all-or-nothing like the split register.
- **Held PR.** `late_plan_pr_number`, `late_plan_pr_head`, and `late_plan_pr_body` — the pull request whose body a
  cycle-marked hold replaced, the head it was standing on when that happened, and the body it replaced, kept so the
  original can be restored. The `plan_pr` spelling is what live pinned comments carry and stays for that reason; what
  the group NAMES is whichever pull request the cycle holds — the plan one a design discussion left standing where the
  generation was entered before publication, and the implementation one the work is already on where it was entered
  past it. Which of the two it names can CHANGE inside a cycle: a generation whose publication entry names a pull
  request the hold does not is one the adjudication has moved off — guidance resumed the developer, their push landed,
  and the re-measurement entered the gate on the pull request the work is now on. The old hold is released, the slot
  freed, and the new one taken, in that order and never both at once, since there is one identity and one preserved
  body to hold them in; a release that could not be made on a reusable pull request parks the tick instead of
  spawning. A `pr_number` somebody re-aimed is deliberately not that signal — it names whichever pull request the
  issue currently records rather than the change under adjudication. All three go down in one write before the pull
  request is edited, so the only thing a crash can lose is the edit — and a head this orchestrator cannot name refuses
  the hold outright rather than being recorded absent, since the write drops an empty one and what it would leave is
  an identity and a body with no head between them, on a change already wearing the notice. What restores the body is
  the release the `single` reconciliation runs: the identity says which pull request this cycle marked, and the body
  has to BE that hold verbatim before it is written over, so a description a human rewrote — or edited a sentence of,
  leaving the hidden marker in place — is left as theirs. The hold text is keyed to the cycle and quotes nothing that
  moves inside one precisely so that comparison is possible: the generation counter advances on every reconciliation
  that lands, and a body keyed to it could never be reconstructed after a re-measurement. What the notice SAYS differs
  by side of publication, because the sentence has to be true of the change its author is looking at: one nothing has
  pushed to is adjudicated *before anything is published*, while the one the work is already on was published long ago
  and its notice names the push the adjudication stands in front of instead. Both spellings are recognized and only
  ever one written, so a record that crosses publication mid-cycle has the notice already standing rewritten rather
  than read as somebody's own words. `late_plan_pr_head` is a reading rather than a claim, and neither the retry nor
  the release is decided by it: it says which change wore the notice, so a pull request somebody pushed to under the
  hold is reported and left holding the same notice against the same recorded reading. It is **not**
  `late_published_sha` below — that one is the head the gate was entered on and what a settlement pins its push to,
  and the hold never writes it.
- **Publication provenance.** `late_post_publication`, `late_source_stage`, `late_published_pr_number`, and
  `late_published_sha` say how the gate was entered and what it was entered from — one durable write puts all four
  down together, and a comment carrying only some of them is damage read from either end: the marker gone would say
  the entry was taken before publication, and any of the other three gone would leave the marker over nothing. Asked
  as a group ahead of every handler, on the five stages that publish onto a pull request and on `workflow:decomposing`
  too: the adjudication decides which pull request the verdict was taken over, which head to pin the push it licenses
  to, and which stage to hand the issue back to, entirely from this group — so a partial one there would settle a
  post-publication candidate as though nothing had published it, route it to `workflow:implementing`, and retire the
  evidence behind it.
  What writes them is the gate standing in front of every push onto a pull request the remote already carries — the
  shared dev-fix publication and the no-feedback bounce behind it, both validating recoveries, the three conflict
  publications, the base sync's auto-rebase and its crash recovery, and the final docs pass; the implementing seam,
  which opens the pull request rather than pushing onto one, writes none of them. They are additive inside an additive
  group, and their absence is the answer rather than a gap: a generation carrying none of them was entered *before*
  the work was published, which is what every record written without this group describes — so a live pinned comment
  answers the question with no migration having reached it, and the write leaves the group off rather than spelling
  that one state a second way. `late_post_publication` is read off the literal `true` and written only while it is
  set, for the reason the cancellation marker is: `bool("false")` is `True`, and reading the flag for its truthiness
  would tell a reconciliation there is a pull request to act on. The three fields beside it are what a
  pre-publication entry has no need of and a post-publication one could not re-derive. `late_source_stage` is the
  workflow label the issue was taken out of and the state a settled adjudication continues at -- save a taken-over
  auto-rebase replay, which continues at `workflow:validating` as every published rebase does — read through the label
  vocabulary, so a value that is not one of them reads back absent rather than as a state a later tick would obey, and
  the adjudication runs under `decomposing` rather than the label it came from, so a stage that was not recorded is
  not one anything could recover. Being a label is not enough: the group is written and read as context only while
  this field names one of the five that publish onto a pull request the remote already carries. `workflow:ready`,
  `workflow:blocked`, and `workflow:umbrella` each own an edge to the adjudication for reasons of their own and have
  no pull request behind them, and `workflow:implementing`'s own push is what *opens* the pull request — so a group
  naming one of them is refused at the write and reads back as no publication context, rather than sending a later
  reconciliation to measure and push a candidate no post-publication stage committed. It is also where an authorized
  settlement puts the issue BACK, which is what the five `workflow:decomposing → <published state>` edges
  exist for: that stage is the only owner of the completion the candidate still owes — a docs watermark and its
  `in_review` handoff, a conflict round, another reviewer look — and returning every one of them to `implementing`
  instead would walk the issue back to a point it had already passed.
  The push itself is not left to that stage: the settlement makes it, because the settlement is the last tick holding
  the head the verdict was measured over. `late_published_pr_number` is the pull request the work already has, and
  `late_plan_pr_number` beside it is whichever pull request this cycle's hold marked, and on a generation entered past
  publication the two settle on the same change: a cycle that held a plan pull request and was then re-measured on the
  far side of a push reads back with them disagreeing only until the next tick, which releases the first hold and
  takes the second (see *Held PR* above). `late_published_sha` is the head that pull request was left on, frozen at
  entry like every other late SHA because the branch moves under a reconciliation that re-read it. It is the late
  group's own copy rather than a reading of `implementing_published_sha` above: that key is the publishing stage's
  live record and is overwritten by the next push, while this one is evidence one generation is reconciled against.
  Which generation drops it matters: an authorized settlement retires the whole record, and so does an umbrella's own
  terminal, but the **split's** retirement onto `workflow:umbrella` keeps the group where it drops the measurement.
  Everything that supersession licensed is still to come at that point — the children the umbrella's walk releases
  and the branch its terminal reclaims, both on later ticks — and this group is the only thing left on the issue
  naming which pull request was closed and the head it was closed over, so the walk, the reclamation, and the
  terminal each re-read it before they act. The terminal's retirement drops it last, immediately behind the barrier
  that asks it one final time. The flag alone proves none of it — `PublicationContext.is_complete` holds
  only while the stage, the pull request, and the head are all readable beside it, so a group a hand edit half-damaged
  reads as context nothing may act on rather than as a publication with no pull request to name, and
  `PublicationContext.enter` refuses to record one that cannot name all three. A restart's fresh cycle keeps
  none of the group and needs none: what it puts the issue back into is `decomposing` or `implementing`, which is a
  pre-publication attempt again.
- **Taken-over auto-rebase replay.** `late_auto_rebase_replay_sha` names the unpublished replay of
  `late_published_sha` an auto rebase made and this generation took over from the attempt that made it
  (`workflow/engine/rewrite_takeover.py`, see [Base refresh](#base-refresh)). It rides the publication group as
  provenance rather than as a fourth term: written only by that handoff, as its own key in the one write that retires
  the attempt, and answered (`PublicationContext.replayed_as`) only while the group is whole and the value is this
  generation's own `late_candidate_sha` -- so a later candidate frozen into the same cycle, a value that is not a whole
  commit id, and a record from before the key existed are no takeover. It licenses no push and no route: an authorized
  `single` publishes the replay exactly as it publishes any post-publication candidate, leased to
  `late_published_sha`, and what the field adds is the report debt that push leaves (`developer_report_rewrite_debt`),
  recorded before the label with the spent `review_round` put back to zero, as the rewrite finish does. Additive and
  written only while set, it is inside the generation's own key group, so the retirement that ends the cycle drops it.
- **External-resource ledgers.** `late_resources` holds one `{kind, target, state}` entry per obligation the remote is
  owed — kind `snapshot_ref` / `branch` / `plan_pr` / `child`, state `pending` / `retained` / `reclaiming` /
  `reconciled` / `failed`
  — keyed on kind and target, so a reconciliation repeated after a crash updates the entry it already wrote instead
  of appending a second one. `reclaiming` is the decision, written *before* the delete that carries it out, so a tick
  that died between the push and the record of it has something durable to retry. What the retry does not get is a
  pass on the proof: the consumers are read again on every visit, immediately ahead of the delete, and one that came
  back keeps the ref and leaves the entry `reclaiming`. The single exception is a ref the remote no longer has: the
  delete has already happened, what is left is finishing it, and a consumer that came back to it is answered by the
  receipt and the child's own guard rather than by keeping a ref nobody holds. Every
  state but `reconciled` is still owed. `late_consumers` is the direct snapshot consumers, deduplicated and ordered,
  since the reclamation rule asks about each of them once — and it is read from the other end too, as the one record
  that can vouch for a child claiming this split in a body marker anybody can paste. It is not `children`, and a drift
  reroute that replaces that manifest leaves it naming the originals the ref was preserved for: the proof reads any
  consumer the parent's scan of the replacements was not asked about afresh. The ordinary split that answers the
  reroute adds each replacement it points at the ref, in the same write that records the replacement in `children`,
  so the ref waits on those too, answered off that scan; it is the only road outside the split transaction that adds
  to this ledger, and it writes no other late key. Because each joins behind the create that opened it, the ledger is
  not proved whole at any phase while the record carries that split's `split_attempt` and its register is short of
  `expected_children_count` or names a child this ledger lost: no pass reclaims the ref then, the closed-owner sweep
  included. Both hand-offs past which
  nothing revisits these ledgers settle them first — the umbrella's close, and the all-children-resolved flip of a
  parent the re-decomposition left `blocked` with work of its own, which stays `blocked` while a recorded consumer still
  holds the ref or while `late_consumers` cannot be read at all. Only a positive whole number is one — `True`, `2.5`,
  and `"7"` are not issues anything can ask GitHub about, and neither the reader nor `with_consumers` will convert one
  into a consumer id. Neither ledger is ever *reduced* to what this binary understood: an entry it cannot type, or a
  consumer list it cannot read, is carried through verbatim beside the typed view and written back exactly as it came,
  and `LateObligations.is_opaque` says so — and while it does, `with_resource` and `with_consumers` refuse an update to
  that ledger rather than returning a record the next write would silently drop back to the verbatim copy. The two are
  preserved and written **independently**, and the reclamation refuses them independently: an untypable entry on
  `late_resources` means no reclamation can be recorded at all, while one on `late_consumers` means only that no
  snapshot's proof can be taken — the superseded branch, which owes no consumer anything, is still deleted and still
  retried. "Typed" is strict there, because the alternative to preserving an entry is rewriting it from what was
  understood — an entry counts as one this binary wrote only when it carries exactly the three fields it writes, each
  holding a value this vocabulary knows, so a state it cannot read is **not** `pending`, a field it never wrote is not
  noise to drop, and a target that is not a usable identifier is not one to re-encode. The damaged-identity case is
  preserved the same way: a record whose `late_cycle_id` cannot be read writes its two ledgers and nothing else, because
  an obligation does not stop being owed when the identity beside it is damaged — and either hand-off is held on any
  entry such a record carries, a `late_consumers` list alone included, unless `late_retired_cycle_id` says a retirement
  left it and both ledgers are readable, when only an entry still owed holds. Dropping any of it would be an obligation
  deleted from the issue that still owes it — a cleanup that looks complete, or a snapshot reclaimed as though nobody
  were waiting on it — so a generation holding an opaque ledger is one nothing may treat as settled.
- **The split's own registers.** `late_split_children` is the ordered, positional list of the children THIS
  generation created — entry `i` is the child that owns slice `i` of its manifest — and `late_links_announced` says
  the forward-link comment has been made. Both live on the generation rather than beside the stage's shared keys
  because both have to be scoped to one adjudication. The stage's `children` list and `dep_graph` belong to
  whichever decomposition last wrote them, and an issue that was decomposed, saw its children resolve, and then
  implemented an oversized candidate still carries the old ones — so a transaction reading `children` would adopt
  **completed** issues by manifest index, and `decomposed_at` would suppress the very announcement the split owes.
  The stage's list and graph are written *from* the register instead, which replaces the earlier decomposition's
  rather than leaving one standing. The register answers one thing more, and to a reader outside the transaction: a
  non-empty one says this generation's candidate has already become children, which is what tells a settled split's
  retained publication group from a pair somebody froze and never counted (see
  [`delivery-stages.md`](delivery-stages.md#the-size-gate-on-a-published-pull-request-every-push-onto-an-open-pr)).
  `late_phase` carries that answer in the window the register cannot — a child is created before the write that
  records it — and the register carries it from there on, including through a retry that rewound the phase to the
  boundary it started from. The register is read all-or-nothing: an entry this binary did not write makes
  the whole field read back empty, because skipping one would shift every child after it onto somebody else's slice
  — and an empty answer costs a marker lookup rather than a wrong adoption. That lookup is the other half: every
  child is created carrying `<!--orchestrator-late-child:issue=…:cycle=…:generation=…:index=…-->`, so a child created
  into a crash before its number was recorded is adopted rather than opened twice. The issue is part of that identity
  because a cycle is minted per issue and repeats across them, while the lookup is not scoped to one parent's
  children — without it, two parents on their first candidate would each carry `cycle=1:generation=1:index=0` and one
  would adopt the other's child. Both fields are also cleared whenever the generation counter advances: they are the
  split transaction's own one-shot receipts, so a register carried into a revision would have the new manifest adopt
  an old child by index and a link receipt would swallow the announcement the new split owes. Neither external ledger
  is cleared with them — a ref the remote holds is owed whatever the next generation decides — and the counter is
  refused from advancing at all once either a child or a snapshot obligation is recorded, since the commit a
  recorded ref was created for is the one its reclamation compares against.
- **Inherited lineage.** `late_ancestry_root_issue`, `late_ancestry_depth`, `late_ancestry_parent`,
  `late_ancestry_cycle_id`, `late_ancestry_generation`, `late_ancestry_snapshot_ref`,
  `late_ancestry_snapshot_sha`, `late_ancestry_mirror_first`, `late_ancestry_base_branch`, and `late_declared_scope`
  are what a child born of a
  late split carries, and they are a separate group from the generation above because they answer a separate
  question and outlive it: a generation is minted, adjudicated, and retired inside one issue, while an ancestry is
  written once when the child is created and is still true after that child has been implemented, split again, and
  closed. The depth and the root are what the child's own size gate mints its generation from, so automatic
  splitting stops at the same bound three generations down as it does at the root — a child that could not say how
  deep it is would read as a root and buy the lineage another generation, which is why an unreadable depth reads
  back unknown rather than 0. This group is also the WHOLE of what descends. A child is created with a pinned comment
  of its own and seeded with exactly these keys, the parent link and the creation stamp — never with the parent's
  `late_exempt_sha`, never with the `late_override_*` terms an operator authorized that parent's publication on, and
  never with its measurement — so the first candidate a child commits reaches the size gate carrying no record that
  skips a reading, and is measured from the frozen base across every path, over however many commits the slice took.
  A bypass that descended would publish the one thing a split exists to prevent: bulk nobody adjudicated, under a
  permission granted for a different change on a different issue. That absence is driven from the split that really
  creates one, in
  [`tests/workflow/stages/test_late_child_ceiling.py`](../../tests/workflow/stages/test_late_child_ceiling.py):
  a fixture writing an ancestry onto an ordinary issue could not tell a seed that copied the parent's records from
  one that did not. The cycle, the generation, and the parent issue are what a record about this child is
  correlated back to the adjudication that created it by. The snapshot ref and commit are the only durable pointer
  to the work the child is meant to reuse, since the branch it was committed on is superseded and the pull request
  that carried it is closed — both halves or neither, because a ref with no commit cannot be verified against
  anything and a commit with no ref names work nothing can fetch. `late_ancestry_mirror_first` travels with that pair
  and is a claim about the world rather than about the child: that any reclamation which can take this ref drops
  **this host's copy of it first**. The child's own reuse guard reads a surviving copy as proof no reclamation has
  happened, and that reading holds only against an orchestrator ordering the two — a pointer written before this one
  did (the remote ref first, the mirror best-effort behind it) can leave a copy standing beside a ref that is gone.
  Written `true` by the split that seeds the child and absent otherwise, so an unstamped pointer is answered with one
  read-only `ls-remote` instead of the free local read. Nothing migrates: the stamp is written by the binary that
  would do the reclaiming, so its absence is the whole question answered. `late_declared_scope` is the slice the
  adjudication assigned, and it is what the child's own late prompt states rather than an issue body somebody has
  since edited. Every field is additive and read fail-closed like the generation's own: an issue that reached this
  workflow another way carries none of these keys, and a hand-edited one reads back absent rather than becoming a
  lineage nobody wrote. The ref is checked against the namespace that owns it rather than merely for being a string
  — a value outside `refs/orchestrator/late-split/` names a branch, a tag, or nothing, and handing one to a child is
  worse than handing it none. The record is READ where it matters most: a split refuses outright when the ancestry
  disagrees with the generation's own lineage, because a generation naming a shallower depth or a different root is
  one minted without this record — and a shallower depth is exactly how a lineage would buy itself a generation past
  `MAX_LINEAGE_DEPTH`. It is read once more for an ordinary re-decomposition: `late_split/provenance.py` decides
  which late lineage that issue's replacement children inherit, and `stages/decomposition/replacement_lineage.py`
  asks it before the split creates a child, again before a recovered split is finalized, and again in front of every
  walk that releases one. An issue no late split charged inherits none. A descendant inherits this group's root
  and depth, and a root whose own
  late record proves a split made children is that lineage's root at depth 0. Only a record of the children
  themselves proves one — the register, or a consumer or child entry on the ledgers, which a retirement keeps after
  it drops the identity. No phase does: `splitting` is written before the first child exists, and a cancelled cycle
  that created none is rebuilt at `cleaning_up`. A snapshot entry, recorded before the first child, or a ledger this
  binary cannot type proves nothing either way; `late_links_announced`, raised once the children's links are
  announced, says children were made and names none of them. Each of those beside no child record is refused, and
  so is a child entry that names no issue or any entry naming the issue itself. The snapshot it names is, for an
  issue that split itself, its own split's while the ledger names that ref exactly once and as `retained`, and none
  otherwise; for any other descendant it is this group's pointer, and only where that is the ref the group's own
  parent, cycle, and generation mint. A pinned comment that would not parse (it reads back empty, like an issue
  nothing touched), any key of this group its reader would drop — a generation that is no count, a ref outside the
  namespace, a flag that is not `true`, a `null` — a group with no readable parent and cycle, a child receipt in the
  body with no group beside it, a group whose root, depth, and parent disagree, a late record carrying a cycle,
  counter, root, current issue, depth, phase, `late_cancelled_phase`, split register, announcement, or ledger its
  reader would drop (`null` included), a live cycle with no root, current issue, or depth, a record whose cycle is
  gone beside the fields it still carries, and one written for another issue, still creating children, cancelled
  while it was (the interrupted boundary `late_cancelled_phase` keeps), naming a root other than the group's whether
  or not it split, or, having split, naming another depth are each a refusal rather than depth 0. What an inherited
  lineage seeds on each replacement is this group and nothing more: the root, one past the depth already charged, the
  parent, and a cycle and generation to correlate by — the parent's own where its record keeps one, its ancestry's where
  it has none, and `late_retired_cycle_id` where neither stands. A parent already at `MAX_LINEAGE_DEPTH` has no room for
  a child, and one naming no cycle anywhere has nothing to correlate one by. The snapshot pair and
  `late_ancestry_mirror_first` are seeded only on a replacement `late_consumers` records, and only for the ref the
  parent's own split holds: a pointer another issue's ledger protects is one this issue cannot record a consumer on, so
  its replacements are born with the lineage and without it. A replacement given the pointer is also given the late
  split's reuse instructions for that ref after its declared body, since the body — not this group — is what its
  implementer reads. Which records refuse — an unprovable lineage, the bound, a held snapshot neither settled nor
  recorded with a base, a slice naming another ref — what a recovered split repairs or refuses on each recorded child,
  how it attributes an unrecorded one, and what every release and the child's own dispatch hold a child to — its parent
  link, this group, its pointer, its text, and its receipt — are kept in one place as
  [the split's contract](../workflow/roles.md#what-an-ordinary-re-decomposition-holds-its-children-to). On this group
  the upshot is three facts. A refusal parks before `expected_children_count` is written, so nothing is created. A
  recovery writes the owed group over a recorded child carrying none of it — the pointer and
  `late_ancestry_mirror_first` only while this split still holds the ref and records the child on `late_consumers`,
  dropped together once the ref has passed to a reclamation, a stamp standing alone left as it is — and refuses one
  carrying any other group, with nothing written over it. And a child whose seed no longer matches the receipt in its
  body is held at dispatch, parked `replacement_lineage_unproved` once, until the split, a recovery, or a human writes
  the seed; the split and the recovery lift that park in the same write, and a restart keeps the seed whole.
- **Pending owner check.** `late_owner_check_pending` says a completed run's outcome has not yet been cleared by a
  fresh read of the issue it belongs to. It is written *before* that read is taken and dropped when one succeeds or
  the cycle is cancelled, and while it is set no later tick may treat the generation as settled, however small,
  decided, or parked it looks: reconciling it is the FIRST thing a tick does, ahead of the size gate, the hold, and
  any spawn — and while it is set the generation counts as live for the kill switch and the hand-relabel
  guard too, since an undersized revision is exactly the state a size-keyed gate would route out of this mode with
  the read still owed.
  It is durable because nothing else would bring the workflow back to that read — a revision that came back under the
  ceiling routes past the gate and an issue parked for a human routes past everything, so a retry hung off either
  would never run — and it is written ahead of the read rather than out of its failure because a process killed
  mid-read never sees the failure at all. It is written by the COMPLETION rather than by the guard, in the one write
  that records what the run left, and that holds for every completion: a verdict, a re-measured candidate, a timeout,
  an unusable reply, an outcome too large to record, a moved candidate, and a developer reconciliation nobody could
  make. A tick dying on the way to the guard therefore leaves the park standing and the read owed, rather than a
  generation still reading as `adjudicating` that the next tick pays for another agent against. That same write
  carries whatever else the completion staged, which is how the
  durable half of a park gets out ahead of the comment announcing it. See
  [`../workflow/roles.md`](../workflow/roles.md#the-owner-read-a-finished-run-has-to-pass).
- **Accepted candidate.** `late_exempt_sha` is the one commit an authorized settlement let past the size gate — an
  adjudicator's own `single` writes nothing here, since what a verdict earns is the
  [`late_single_decision` park](#the-late-run) a human's decision to publish the candidate unsplit is owed on, and
  the settlement is what an operator's `/orchestrator authorize-oversized <commit>` on that park licenses. It is
  the whole of what that settlement is worth durably: the gate measures whatever a stage is about to publish, so a
  candidate handed back with its generation cleared and nothing else would be measured past the ceiling again and
  adjudicated again. It names exactly the commit that was measured, which is also the whole invalidation rule —
  anything committed on top of it is work nobody adjudicated, does not match, and is measured as the fresh candidate
  it is. There is no clearing step to remember and no window in which a stale exemption covers a moved head. The one
  thing that MOVES it is an authorized rewrite — a squash on approval, the clean base rebase the per-tick refresh
  publishes, or the clean replay `workflow:resolving_conflict` runs, whose contribution fingerprints identically to the
  accepted one, granted by `late_transfer` and recorded by the `late_rewrite_*` group below — and that move is a write
  of its own rather than a widening of the match: it belongs to the receipt of the push that landed rather than to the
  grant before it, so a verdict is never left on a commit no remote carries. `late_rotation` stages it into the push
  tail's own write, so the exemption, the identity, the phase, and the account of what the remote holds land together
  or not at all. That
  is also why the pre-tick base refresh reads the CHECKOUT and the LABEL before it decides whether this record
  freezes the branch: a rebase while the head is still the accepted commit, and the gate has still to act on it,
  would have the gate measure the rewrite past the ceiling and re-route a decision a human has already made — while
  freezing on the record's presence alone would take every issue that ever earned a verdict out of the base refresh
  for the rest of its life, review and its rebases included.

  It shares that window with `late_approved_sha`, and the two are not duplicates of each other. The approval is
  written in the same breath and answers a different question: *this commit is owed a push, and no other may be pushed
  in its place*. Which is also why it carries `late_approved_basis` — `reading`, `unmeasured`, `adjudication`, or
  `authorization`, written by whichever owner granted it. The gate spends an approval after a crash without asking
  anybody, so what one RESTS on is the only thing that can decide whether it may be spent. `reading` is this gate's
  own count coming back at or below the ceiling, written by `late_verdict`. `unmeasured` is a publication that
  skipped the count on a record this workflow made for itself and re-derives on the next tick — a rewrite permit, a
  switched-off candidate, a receipt already on the remote — so each answers for its own bypass. The other two are
  the ones an operator's gesture is behind, and they are named as one group because what a reader decides is whether
  a debt has to be revalidated rather than which owner granted it: `adjudication` is the publication debt an
  authorized settlement records beside the exemption it writes, and `authorization` is the debt a candidate past the
  ceiling earns where a human authorizes it at the gate itself — the count behind that one really was this gate's,
  so recording it as an ordinary `reading` would be true and useless. `implementing/late_verdict.py` writes it
  where a command ends the `late_unauthorized_exemption` park, in the same close-safe retirement a small
  candidate earns — the generation this gate froze has to be dropped before the push either way.

  Inferred from the records standing around them — *an approval naming a commit some exemption also names is the
  settlement's* — it is wrong in both directions: a candidate the gate measured at or below the ceiling on an issue
  still carrying an older build's exemption would have its own approval refused and be re-judged against a base that
  has moved, and a settlement's debt whose exemption somebody hand-edited would read as the gate's own. So the owner
  granting one says which it is. Read fail-closed like every other late field, so a value from outside that
  vocabulary is no basis this build can act on — and the two ways a record fails to say are told APART rather than
  read alike, since only one of them earns the compatibility. An approval an older build wrote carries no field at
  all, and there the exemption beside it is the only evidence there ever was, so it is the one that is read. One
  whose field a hand edit or a half-written crash left unreadable is the opposite record: it CLAIMS grounds and
  cannot name them, so it is refused outright rather than handed to the exemption. Read as the absence, that
  truncated value is the single edit a bypass turns on — the one field the fallback keys off, touched, and the
  approval beside it answers as the gate's own. The claim an unproven landing puts back reads the standing basis
  BEFORE the write that pays and drops the debt it replaces, since read after it that claim would say `unmeasured`
  for a debt an operator's gesture was behind. Written, dropped, and spent with the approval it describes, never on
  its own — including on the **implementing** seam, where nothing froze a publication head to lease a push against,
  so the gate's own debt writer declines and the seam mints its own. That happens in one place for two callers: the
  publication that names the commit it is about to push, and the guard that refuses a checkout which has left the
  approved commit, which stands exactly where that publication would have recorded one. Neither invents grounds.
  An approval already standing for that very commit is carried exactly as it reads — an absence as an absence,
  since promoting a legacy record to `unmeasured` would turn "fall back to the exemption" into debt this workflow
  owns and nothing would ever revalidate, and an unreadable value VERBATIM, since rewriting one as an absence would
  launder the damage onto the legacy road and the next tick would spend the debt without asking anybody. Where none
  stands, the grounds come off the exemption CLAIM: presence rather
  than readability, so a field a hand edit truncated still leaves the adjudication's debt, and only an issue
  carrying no such field at all leaves `unmeasured`. So it
  freezes by presence — as the whole pair, `late_approved_lease` included, because the two go
  down in one write and a lease standing alone is the damage the dispatcher parks on a tick later, by which time a
  hold keyed to the commit alone would have rebased and force-pushed the branch that park is about. One approval is
  set aside all the same, and it is the refresh's own rather than a stage's: where `late_approved_lease` IS a
  still-pinned `pending_auto_base_rebase_push_sha`, the freeze would shut the interrupted auto rebase out of the
  recovery that anchor exists for ([Base refresh](#base-refresh)). The late reading freezes the same way, on any of
  the fields the write that mints a generation puts down rather than on `late_candidate_sha` alone, and is never set
  aside. It is proved before anything spawns, and is spent by the publication that lands — durably ahead of the
  relabel that hands the issue to `validating`, since past that label implementing never runs on the issue again and
  nothing else would ever drop it. `late_approved_lease` rides with it and is spent by the same write: the head the
  pull request stood on when the approval was taken, for an approval on the **published** side. The generation that
  froze that head is retired by the very write that approves the commit, and the push it licenses has not run yet — so
  if that push fails, or the settlement hands the candidate to another stage, the only head left to read is whatever
  the pull request has become since, and the retry skips the measurement because the commit is already approved.
  Pinned to what was frozen, a pull request somebody moved in between rejects the push; pinned to what can be read
  now, it is force-overwritten by work measured against the head it used to be on. Read fail-closed like every other
  late commit field, and refused where it cannot be read: an approval on the published side whose lease is absent or
  hand-edited has nothing left to pin against, and the one head still available is the one the lease exists to catch,
  so it parks `late_measurement_failed` with nothing pushed. The one exception is a pull request already standing ON
  the approved commit: the push it licenses has already been made, so there is nothing left to pin and the debt is
  settled instead of parked. Empty is the ordinary answer for a pre-publication approval — which is what every
  implementing-seam approval is, and whose push correctly takes its own reading of the remote. After that the
  exemption is what is left, saying *an adjudication ruled this commit one coherent change* for every later tick that
  finds the branch where the verdict left it — a claim the gate goes on reading and the base refresh stops honouring,
  since past the handoff the branch is review's. It is not on its own a reason to skip a reading: that takes the
  `late_override_*` authorization naming the same commit beside it, and the contribution between the pair that record
  names re-fingerprinted to what it says. Each covers what the other cannot: the approval covers the wait for the
  push and could not survive it without freezing the branch for good, and the exemption covers every tick past it and
  could not be read by presence for the same reason. Read and written fail-closed like every other late field: only a
  whole git object id is one, a `record_exemption` handed anything else refuses rather than writing a value the gate
  would read as a bypass, and a hand-edited field reads back as no exemption at all. The one write that does drop it
  is a restart's projection, which keeps nothing about the attempt that ended: the branch that commit was on goes
  with it, so an exemption left behind would name work the fresh cycle has no way to reach and never adjudicated.

  **What that commit carries.** `late_exempt_base_sha`, `late_exempt_candidate_sha`, `late_exempt_fingerprint`, and
  `late_exempt_fingerprint_format` are the semantic identity of the accepted change, written with the exemption in
  the same pinned write and outside `LATE_STATE_KEYS` on the same terms — the exemption says which COMMIT was
  adjudicated, and these say which CHANGE was, which is the only question left once that commit has been rebased,
  squashed, or made afresh. What licenses a publication is `is_exempt` — the exact SHA compared whole against the
  commit in hand — asked together with the operator authorization the `late_override_*` group records and held to a
  contribution re-fingerprinted from the pair THAT group names, since an exemption is an adjudicator's answer and
  half a bypass on its own; what this group licenses is the exemption MOVING onto the commit an equivalent workflow
  rewrite replaced the accepted one with, which the rewrite authorization group below records and nothing else
  grants.
  The pair is the generation's own frozen base and the accepted candidate, and the digest is the canonical
  fingerprint of the contribution between them
  ([`../architecture.md`](../architecture.md#fingerprinting-a-prospective-contribution-gitmeasurementfingerprintpy)),
  taken from the frozen pair the decomposer inspected rather than from the checkout's head or a base read at
  settlement time: the worktree is writable for the whole of an adjudication, so what it stands on is not evidence
  of what a human ruled on. The format version travels with the digest because two ids taken under different rules
  are not comparable and nothing about the ids themselves would say so. The group is read whole or not at all: a
  missing member, a member that is not the shape its field takes (an abbreviated end, a truncated digest, a version
  spelled as text), a candidate that is not the commit `late_exempt_sha` names, a version this build does not
  compute, and a pinned comment written before the group existed each read back as no transferable identity — while
  the exact-SHA exemption beside them goes on exempting the matching commit exactly as it did. A settlement whose
  fingerprint reading could not be taken records none of them and settles anyway, for the same reason: what an
  absent identity costs a later tick is the transfer, never the decision a human already made.
  `record_semantic_identity` refuses on the way in too — a field that is not a whole object id or a whole digest,
  and an identity naming any commit but the exempt one, are not written at all.

  The group is read by PRESENCE as well, and the difference is which caller is asking. A road whose move is to
  MEASURE is right to take a damaged group for an absent one, since it counts the candidate afresh either way; a road
  whose move is to walk PAST an issue as though no verdict were in flight is not, and a half-written group, a
  hand-edited digest, and a field carrying `null` all read as nothing there. `unreadable_exemption` on the
  [`exemption_reading`](../../orchestrator/workflow/late_split/exemption_reading.py) owner tells the two apart: a
  comment carrying a member of the group whose exempt commit cannot be read back claims one it cannot show, as does
  an identity group with a member present that does not read back whole. The legacy shape is neither, which is why
  the identity half is asked by presence rather than by truth — a comment written before the group existed carries
  the exempt commit alone and is complete for what it says. It is read by the transfer classification below, on
  the base refresh's crash recovery.

  The group belongs to the commit `late_exempt_sha` named when it was written, so `record_exemption` **drops it
  whenever it moves that field to another commit**. Nothing else would: a verdict whose fingerprint could not be read
  records the commit alone and writes nothing over the fields beside it, and those fields match by name — an issue
  that accepts A with an identity, then B with none, then A again with none would otherwise hand A's first digest
  back as what the last adjudication decided, over a base that generation never measured. Re-recording the SAME
  commit keeps it, which is what a settlement resumed between the exemption write and its handoff needs: the identity
  standing there is one its own earlier pass derived from the pair this generation is still frozen on.

  **What authorized it to move.** `late_rewrite_kind`, `late_rewrite_phase`, `late_rewrite_from_sha`,
  `late_rewrite_from_base_sha`, `late_rewrite_to_sha`, `late_rewrite_to_base_sha`, `late_rewrite_fingerprint`,
  `late_rewrite_fingerprint_format`, `late_rewrite_pr_number`, `late_rewrite_source_stage`, and `late_rewrite_lease`
  are the evidence one transfer was granted on. Their keys and encodings live in
  [`rewrite_fields`](../../orchestrator/workflow/late_split/rewrite_fields.py), their whole-record reads in
  [`rewrite_reading`](../../orchestrator/workflow/late_split/rewrite_reading.py), and their coordinated writes in
  [`rewrites`](../../orchestrator/workflow/late_split/rewrites.py). They stay outside `LATE_STATE_KEYS` on the same
  terms as the two groups above. They go down BEFORE the push they license and they move **nothing**: the exemption
  and its identity stay on the commit a human ruled on, because the object the rewrite produced is on no remote yet
  and a verdict rotated onto it there would be stranded by a push that failed or a process that died. What this
  group records is the *permission* for a later write to move it — and that later write is the one that receipts the
  landed push, where the exemption, the identity, and the account of what the remote holds go down together or not
  at all. `record_rewrite_publication` is that write, staged by `late_rotation` into the push tail's settlement, and
  it moves them in one statement, the `late_override_*` authorization that made the exemption a bypass included —
  a reader is entitled to find them agreeing, and any two of them apart is a comment nothing here can tell from a
  hand edit. The authorization is the one member that may be absent: a comment carrying none has none to carry, and
  the move is silent there rather than minting one. It is held to the record rather than to its caller: only a
  permission this build can read back whole and still finds `authorized` is spent, so a damaged group, one bound to
  a commit this issue does not exempt, and one already `published` each refuse instead of being repaired. Being
  readable is not being *valid*, and the settlement is held to the second as well: what licenses the move is the
  permit `late_transfer` re-asked on that same tick, carried down the push tail beside the commit it proved out for.
  A refusal there is not a hold — the rewrite falls through to the ordinary cumulative gate, and a count under the
  ceiling publishes the same commit — so a settlement reading this group alone would rotate a verdict onto a rewrite
  nothing revalidated and install the digest the permit had just declined. A permission no permit vouched for is
  left exactly where it stands: not spent, and not dropped either, since the remote is now on a head the permit
  accounts for and a later tick whose refusal has cleared can still settle it. A permission the publication went
  PAST — the push put some other commit on the pull request, so the head it was granted against is gone — is dropped
  on the rollback's own terms instead, since what is left is a claim about a push that cannot happen. The one
  settlement with no permit to re-ask is a pull request that merged or closed on the rewritten commit before its
  receipt was written: that push is behind it, so the attempt's terminal handoff settles the permission on its own
  binding instead — the commit the pull request ended on, the anchor it was pushed from, and that pull request.
  `late_approved_sha` and its lease ride the GRANT's own write instead, and they have to: by then the rewrite has
  already replaced the branch's commits with one, so a comment that explains that commit and does not say a push is
  outstanding is one the next squash reads as *nothing to squash* — reported as success, never measured, never
  pushed. The kind and `late_rewrite_source_stage` are held TOGETHER rather than one at a time, since each is a
  value this build knows and only the pair says whether the record describes a rewrite anything here produced: a
  `conflict_rebase` recorded against `validating`, or a `squash` against `resolving_conflict`, types in both halves
  and names a rewrite that stage does not make. The kind is bounded to rewrites this workflow makes itself, and
  there are three: `squash`, the collapse a reviewer's approval earns; `auto_clean_rebase`, the replay the pre-tick
  base refresh force-pushes once the stage that had to act on the exempt commit has handed the issue on; and
  `conflict_rebase`, the one `workflow:resolving_conflict` runs when a branch has stopped merging cleanly. Each is
  held to the stages its own producer names -- `validating` for the squash, `resolving_conflict` for the conflict
  rebase, and the four the refresh drives for its own -- so a pairing no owner here produces reads back as no
  authorization at all. None of them claims the contribution SURVIVED either: a replay that resolved content
  conflicts and a squash of work nobody adjudicated both carry a kind this build authorizes over evidence that
  fingerprints to something else, and the permit refuses them on the fingerprints rather than on the kind. Nor do
  those fingerprints answer for the base they are read over. What their equality says is that the rewrite
  contributes what was adjudicated *over the base `late_rewrite_to_base_sha` names*, and choosing that base is what
  a rebase does: read over one carrying work no remote has, the rewritten pair fingerprints to the accepted digest
  while the object it names carries that work and the adjudicated change together. `refs/remotes/<remote>/<base>`
  is no proof of it either, since that ref lives in the object store the issue's agent writes to. So the permit
  freezes the base branch from what the REMOTE says it is at and holds the recorded base to being a commit that
  tip's history reaches — reachability rather than equality, because the branch advances on its own and a squash
  collapses over a fork point the branch has had for days, while a commit only this host has ever seen is on no
  branch at all.
  The publication group scopes the whole claim to one push onto one pull request. `late_rewrite_phase` is what says
  whether the move has happened, and every other reading turns on it. It binds the group to the exemption, and which
  end binds follows from it: `late_rewrite_from_sha` while the record stands at `authorized`, `late_rewrite_to_sha`
  once the receipt has moved it to `published`. It is also what a rollback reads — a force-push the remote refuses
  resets the branch back onto the head the rewrite found it on, which the record names as `late_rewrite_from_sha`
  for a squash (it collapsed that commit) and as `late_rewrite_lease` for a rebase (it read the anchor for itself),
  so what the reset owes is dropping the permission it will never spend; an `authorized` record is therefore
  droppable and a `published` one is not. An *outstanding* permission is read two more ways on the tick after a
  crash: it says a push is owed for the commit it names, so the approval beside it defers to the permit rather than
  being spent on the object id, and it says the receipt has not landed, so a remote already standing on
  `late_rewrite_to_sha` is that permit's own push rather than a move somebody else made. Both are asked of the
  phase, not of the commit — the permission and the debt go down in one write for one commit, and a hand-edited
  target would otherwise make the permit invisible. The group is read whole or not at all on the same terms as the
  identity: a missing member, a value that is not the shape its field takes, a kind or a phase this build cannot
  account for, a digest scheme it does not compute, a stage that does not make the kind recorded beside it, and a
  bound end that is not the commit `late_exempt_sha` names each read back as no authorization, which costs a
  rollback the drop and never lets one happen on evidence nobody can check. `late_rewrite_fingerprint` is held to
  the same standard from the other side: a permit re-derives both contributions for itself and refuses where the
  digest already recorded is not the one it took, since a grant that carried on would write its own reading over the
  record — a repair of evidence nobody checked.

  Being unreadable is not being absent, and the difference is what a WRITER asks. A grant replaces the whole group
  rather than adding beside it, so a group that CLAIMS the commit currently exempt and cannot be read back is
  evidence a transfer may not overwrite to repair: the permit refuses, the exemption stays where the adjudication
  put it, and the rewrite is measured by the ordinary gate until a human settles the comment. A group whose
  `late_rewrite_to_sha` names some other commit is the one exception, and it is not a claim about anything a
  transfer is doing — the exemption moved on since, which dropped the identity and left this group describing a
  commit nothing exempts — so it is replaced without ceremony. Read as a claim it would refuse every transfer the
  issue could ever earn again.

  **Which window a crash left the transfer in.** The grant sits between the rebase and the push, and both of those
  sit between the anchor and the receipt, so a tick coming back to an interrupted attempt has five durable moments
  with four windows between them and has to say which one it is looking at before it finishes anything.
  [`git/base_sync/transfers.py`](../../orchestrator/git/base_sync/transfers.py) is where that is read, off the pinned
  comment alone — no git and no request, so the issues that never earned a verdict pay nothing for a question that is
  not about them — and the answers are closed. *Nothing*: no exemption at all, which is the ordinary interrupted
  rebase. *Unrecorded*: an exemption and no permission, so the grant was still ahead of the crash and the evidence is
  re-derived exactly as the dead tick would have taken it — both pairs, the base the REMOTE names, the anchor as the
  lease, and the pull request and stage `pending_auto_base_rebase_rewrite_pr` / `_stage` recorded, never the ones the
  issue reads as now. *Outstanding*: a permission for this very head whose `late_approved_sha` and lease agree with
  it, so the record IS the evidence and the receipt is what is still owed. *Settled*: the receipt landed and the
  exemption is already on the head, so one write has finished the transfer and a second claim about it would be a
  second move. *Unvouched*: everything else — a group this build cannot read whole, an exemption CLAIMED and not
  shown, a proof nothing can be reported from, an outstanding permission naming another commit, or one whose lease,
  publication, stage, digest, accepted pair, or paired debt belongs to some other attempt — and, with no permission
  standing at all, a `late_approved_*` debt that is not the one this attempt's own gate records before its push: one
  naming another commit or another lease, or one this build cannot read back whole. The refresh's freeze lets an
  approval leased to the anchor through as this attempt's own work, so that debt has to be held to the replay here
  rather than measured past and overwritten. Only *unrecorded* is
  handed freshly reconstructed evidence, and that asymmetry is the safety rule: a grant replaces the whole group rather
  than adding beside it, so assembling a claim over one already standing would repair a record nobody checked under
  the authority of the transfer being decided. A *settled* record whose `late_rewrite_to_sha` is this attempt's own
  anchor is passed over rather than refused — it is the PREVIOUS rotation, which is never cleared and whose lease
  belongs to the attempt before this one. So is a group the exemption has moved PAST, asked through
  `claims_the_exemption` exactly as the grant asks it: nothing but the next grant clears that group, so a later
  adjudication accepting fresh work leaves a settled rotation standing over a commit nothing exempts, and the
  fail-closed reader answers for it with the same bare None a damaged record gets. Read as damage, one finished
  transfer would park every rebase the issue could ever earn again.

  Two more questions belong to the roads that publish nothing new. Whether a rewrite the pull request already
  carries can be ACCOUNTED for, asked because finishing that road clears the anchor and the anchor is the only thing
  that brings the tick back: *settled* and *unrecorded* both leave a receipt naming the commit, read whole — the
  commit, the head it was pinned to, and the publication it went onto, held against this attempt's own anchor and
  pull request, and every member through the fail-closed reader that answers a hand edit as the absence — with the
  debt beside it asked as well, and asked by PRESENCE: an approval still standing over a receipted commit is a write
  that did not land whole, and so is one this build cannot read back whole, which `_unreadable_approval` on the
  [`late_approval_reading`](../../orchestrator/workflow/stages/implementing/late_approval_reading.py) owner
  tells from the group of nulls the write that pays a debt leaves. Anything else parks with the anchor left pinned
  and a human settles the comment.
  And whether the record says a replay reached a remote that no longer has it, which a *settled* transfer says
  outright and a whole receipt says for a replay no permit ever licensed: the head they rolled back to is the very
  head a retry would lease its force-push against, so the lease would be satisfied and the rollback would be gone.
  **Every one of these readings is on a running road.** The publisher's own evidence is what the size gate is handed
  on every exempt rebase, the classification, the re-derivation, and the rollback answer are what the crash recovery
  the refresh enters decides on, and the accounting is what `landed_recovery` holds a rewrite the pull request already
  carries to before the workflow finishes that road. On the recovery, a checkout the pull request is not standing on is
  classified off the pair of SHAs the attempt recorded — the anchor the remote must still be on, the replay the
  checkout must still be — and off the handoff above: a *settled* transfer or a whole receipt over a remote that has
  moved is somebody's rollback and parks, an *unvouched* record parks, and a record that disowns the checkout parks.
  What is left is licensed by the permit and by nothing else — re-asked over the record where there is one and over
  the re-derived evidence where the grant never landed, ahead of the gated push rather than through it, with
  `permit_only` telling the gate the same so a refusal on either side is a refusal rather than a fall-through to the
  cumulative reading. The one exception is a replay the attempt's own record names whose evidence was re-derived
  because the crash came before any grant: the record vouches for that checkout and nothing was granted on it, so a
  refusal there is a contribution the base advance changed, and the retry enters it with that evidence and without
  `permit_only`, as the interrupted publication would have — measured, and adjudicated afresh past the ceiling, with
  the replay left standing (see [Base refresh](#base-refresh)). The rotation is read back past the push, since a permit
  that stopped holding in between leaves the push landed and the verdict where it was. Every park there that resets is
  held to the reset landing like any other: a reset git refuses keeps the anchor, the replay, the mark, the permission,
  and the debt.

  `late_rewrite_proof` sits beside that group and deliberately outside it. It records which reading proved the push a
  settlement was taken on had landed — `pushed` for the leased force-push that moved the pull request off the head the
  permit was granted against, `already_published` where the rewritten commit was found there already — by the leased
  no-op a recovery makes, or by the terminal handoff of a pull request that merged or closed on it — and it is the one
  fact nothing later could re-derive, since the receipt looks identical either way.
  `record_rewrite_publication` writes it in the same statement as the move, and the reporting owner drops it in a
  write of its own ordered after the `late_transfer` record it feeds, so a process lost between the settlement and
  that record leaves the next reader something to report from rather than a verdict that moved with nothing anywhere
  saying so. That drop is the reporting owner's own last step rather than a caller's, because a comment still
  carrying a proof MEANS a report is owed: left standing it would say a settled transfer had never been announced for
  as long as the issue lives. A drop GitHub refuses is logged and walked past — the record has been made and a later
  tick reading that comment may make it again, which is the safe way round. The reconciliation ahead of every handler
  is where a lost record is made, since every settled rewrite's crash — the squash, the conflict replay, the base
  refresh — comes back through it, and a proof standing over a permission, a phase, or a reading nothing can account
  for is a claim that reconciliation parks once rather than a record it walks past. It is outside the group a reader is
  held to WHOLE because the transfer is settled whether or not it has been reported, and a record short of this member
  is not one to refuse. It is read by PRESENCE all the same: the key standing over a proof this build does not know, a
  phase the settlement never reached, or an authorization it cannot read whole is a comment saying two things at once,
  which `stranded_transfer_proof` answers as the damage it is rather than as nothing owed. A rollback drops it with
  the permission it described, and a fresh grant drops it with the transfer it replaces, since the phase going back to
  `authorized` is what would leave it unreadable beside the new one.

  Its LIFECYCLE, its presence reading, and its REPORT are all live. The settlement writes the proof and the reporting
  owner drops it behind the record it feeds, so a comment carries one only inside that window — and a process lost
  inside it is answered on the next dispatched tick: `late_reconcile` asks `_reports_a_settled_transfer` ahead of every
  other answer, which reads `unreported_transfer` and makes the one record still owed before the drop. The presence
  reading is taken on two roads: that reconciliation's claim check parks once on a proof nothing can report from, and
  the recovery's transfer classification above answers the same proof *unvouched*. The post-publication and
  terminal-handoff routes call the same reporter, so wherever a settled transfer is reached it is reported from the
  one proof — best effort, since a sink that refuses the record loses it, and repeated only where the drop behind it
  does not land.
- **Operator-authorized publication.** `late_override_candidate_sha`, `late_override_base_sha`,
  `late_override_fingerprint`, `late_override_fingerprint_format`, `late_override_additions`,
  `late_override_threshold`, and `late_override_comment_id` are the terms an operator authorized one oversized
  candidate to publish on, written on the [`overrides`](../../orchestrator/workflow/late_split/overrides.py) owner and
  outside `LATE_STATE_KEYS` on the same terms as the groups above. An oversized candidate has two ways past the size
  gate, and both are a human's. The first is an authorized settlement, which `late_exempt_sha` records — an
  adjudicator ruling the change one coherent whole is not itself one of them, since a `single` verdict parks for the
  decision rather than making it. The second is this group: an operator who has read the change says in a comment on
  the issue that it publishes unsplit, and that gesture has to outlive the process that read it, the generation it was
  made under, and the tick that would act on it, or the gate measures the same candidate past the same ceiling on the
  next poll and asks the same question again. What writes it is
  [`late_authorize`](../../orchestrator/workflow/stages/decomposition/late_authorize.py), from a trusted
  whole-comment `/orchestrator authorize-oversized <commit>` posted while the `late_single_decision` park stands —
  proved against the frozen candidate and the recorded `single`, with the digest recomputed between the frozen pair
  rather than taken from anything stored, and written in the same statement as that park coming down and the reply
  being consumed. What ends the group is the answer it was given for ending. What an operator authorized was ONE
  adjudication, taken against the requirements as they then read, and no term of the record can say which — the
  frozen pair, the measurement and the digest all survive an answer being thrown away and re-earned. So the group is
  dropped wherever that answer stops being the answer: with the recorded result, which a certificate over an edited
  scope and a real answer to a question both discard, and again with the run that REPLACES that result — the
  statement no road gets around, since every way an answer can stop being the answer ends at a fresh spawn
  ([`late_session`](../../orchestrator/workflow/stages/decomposition/late_session.py)) — and one step earlier with
  the re-freeze a developer revision makes, which mints a fresh generation an acknowledged-but-unchanged candidate
  would otherwise match every term of
  ([`late_revision_reconciliation`](../../orchestrator/workflow/stages/decomposition/late_revision_reconciliation.py)).
  A record outliving either would license the NEXT adjudication's `single` on a permission nobody granted it. Beyond
  those it ends the way the exemption above it does — a restart's projection, which keeps a whitelist of what is true
  about the ISSUE rather than about the attempt, so these keys go the way the branch and the candidate they name do.
  A fresh cycle that inherited one would carry a bypass nobody granted it, over work no operator ever read.

  Every term follows from what the record IS — a bypass of the one gate that stops unreviewed bulk reaching a pull
  request. A bypass may license exactly what a human looked at, so it is bound to the candidate rather than declared
  over the issue: a flag would authorize whatever the worktree ends on next, and a commit alone would authorize
  whatever that commit turns out to contribute once a base moved under it. So the group names the exact candidate,
  the frozen base it was read over, the canonical digest of the contribution between them
  ([`../architecture.md`](../architecture.md#fingerprinting-a-prospective-contribution-gitmeasurementfingerprintpy))
  and the format version that digest was taken under, and the measurement that made the candidate oversized at all.
  Those last two are recorded here rather than read off the generation beside them, and that is the point of them:
  the generation is cleared when the cycle that earned this record ends, and the ceiling is a knob an operator
  retunes, so a record pointing at either would answer differently later about a decision made once. What was
  authorized is a change of *this* size against *that* ceiling. `late_override_comment_id` is what makes the
  authorization attributable — a bypass is licensed by a gesture somebody made at an address anybody can go and
  read. Whether that author was trusted is proved before the write rather than stored beside it, since an allowlist
  is an operator's own and moves, and the durable half of the evidence is which comment was acted on.

  Read whole or not at all, and more strictly than the exemption above. There the exact-SHA field is a claim that
  stands alone and a damaged member costs only the transfer; here every member IS the authorization. A missing
  member, a value that is not the shape its field takes (an abbreviated end, a truncated digest, a version or a
  comment id spelled as text, a count nothing measured), a digest scheme this build does not compute, and a reading
  at or under its own recorded threshold — which describes a candidate the gate publishes untouched, and so a
  decision nobody had to make — each read back as no authorization, and so does a whole record asked about any
  commit but the one it names. What every one of those costs is a measurement: the candidate goes to the gate the
  way an unauthorized one does, and a human whose comment nothing could read is asked again.
  `record_publication_override` refuses the same terms on the way in rather than recording them, and writes the
  whole group in one statement so a record is never half about one candidate and half about the one before it. It
  touches the fields this owner names and no others, so an unknown field and an exemption group an older binary
  wrote are preserved verbatim by both the write and the clear.

  It MOVES with the exemption. `record_rewrite_publication` carries it onto the pair a workflow rewrite produced in
  the same statement that rotates the exemption and the identity, because the two are one claim in two halves: the
  exemption says which commit may publish without a reading, and this says whose gesture licensed it. Left behind, a
  rewrite nobody has to decide about again would be held for a decision that was already made. What moves is the
  candidate and the base and nothing else — the additions, the ceiling they were counted against, and the comment
  the authorization was written in are what a human decided rather than facts about an object, and the digest
  already describes the rewritten pair, since a transfer is granted only over contributions that fingerprint alike.
  `carry_publication_override` is silent where there is nothing to move: a comment carrying no authorization this
  build can read whole has none to carry, which is the legacy record's answer and the right one, and one whose
  authorization is about some other commit is left exactly as found rather than redirected onto a commit nobody
  granted it for.

  What the group outlives is the generation and the process, and those are the only two. A cleared generation leaves
  it standing — it is what a generation is cleared AGAINST, so a clear that took it would send an authorized
  candidate back into the adjudication a human already answered — and so does a crash, since the terms are on the
  pinned comment rather than in the tick that proved them. A **`late_restart`** is neither: its projection
  (`late_restart._projected`) is a whitelist keeping only the orchestrator's own comment ids and the cumulative
  spend and run-ledger counters — beside a split child's own seed, which is no claim about any candidate — so this
  group goes with `late_exempt_sha`, the generation, the parks, and everything else the cancelled cycle wrote. That is
  the right answer rather than an oversight — the fresh cycle has adjudicated nothing, so there is no verdict for an
  authorization to be half of, and a bypass carried across a cancellation would license a candidate nobody has read.

  It is also what the `late_unauthorized_exemption` park (see [the HITL park](#pinned-state)) is
  waiting for, and the group a trusted whole-comment `/orchestrator authorize-oversized <commit>` on that park
  writes — from the size gate's OWN reading rather than from anything already on the comment.

  The record is durable evidence and nothing more: what a candidate publishes under is decided by the gate, which
  asks this group and `late_exempt_sha` beside it TOGETHER through
  [`late_authority`](../../orchestrator/workflow/stages/implementing/late_authority.py) — the exemption is an
  adjudicator's answer, so a commit only it names is measured — and re-fingerprints the pair this group records
  before it lets one publish. The rewrite transfer asks the same owner the same question before it moves an
  exemption, and the write that moves one carries this group with it. What recording an authorization buys is that
  a human's gesture survives a crash, a cleared generation, and a fresh process. The settlement that publishes
  reads it back, compares every frozen term — the candidate, the base, the additions and the threshold — against the
  generation in hand, and then fingerprints the contribution AGAIN and holds it to `late_override_fingerprint`. That
  last comparison is what the digest is recorded for: the other terms are the pinned comment agreeing with itself,
  while the digest is answered by the objects, and the publication can be reached by a later poll on a host that
  never held the content between the pair. A record the candidate has moved under, a digest that disagrees, and a
  reading nobody could take each authorize nothing, and the issue goes on waiting on its park with the record intact.
- **Pending collapse.** `late_collapse_head`, `late_collapse_base_sha`, and `late_collapse_count` are what a
  squash-on-approval says it is about to do — whether that is collapsing a history or rewriting the subject of the
  one commit already on the branch — written on the
  [`collapses`](../../orchestrator/workflow/late_split/collapses.py) owner and outside `LATE_STATE_KEYS` on the same
  terms as the four groups above — the gate retires the generation a squash is measured under the moment it
  approves the commit, so a record cleared with one would be gone before the push it exists to recover ever
  happened. They go down **before** the reset, and they have to: a squash replaces the approved commits with one
  object carrying the same tree, so past that reset the head it replaced is off the branch, the base it was read over
  is not derivable from the object that replaced it, and the count is gone with the commits it counted — while what
  is left on the branch is indistinguishable from a branch nobody ever squashed. Read as the second, an interrupted
  rotation takes the *nothing to rewrite* road and is reported as a success that measured nothing and pushed nothing,
  with reviewer-approved work reaching the merge button neither counted nor on the remote. A one-commit branch
  rewritten for its subject is the sharpest case of that and records exactly the same three fields: one commit before
  the reset and one after, so not even the shape of the branch changed.

  Three fields and no more, because what a recovery may act on is what it can check: the pull request is re-read,
  the checkout is re-proved, the contribution is re-fingerprinted, and the ceiling is this build's own. What the
  record supplies is only what no reading taken afterwards could. The head is the rollback target and the head the
  force-push is leased against; the base is the end both contributions are read from when
  [`late_transfer`](../../orchestrator/workflow/stages/implementing/late_transfer.py) decides whether an
  adjudication's exemption may move onto the rewrite; the count is what the walk proving the record is held to and
  what the handoff's `:package: squashed N commits` notice is worded from — the notice being owed only where history
  was replaced by less of it, so a recorded count of `1` announces nothing.

  Read whole or not at all, like every other late record: a missing member, an end that is not a whole object id,
  and a count no squash replaces (zero replaces nothing, so it describes no rewrite anybody made) each read back as
  no pending collapse. Being unreadable is not being absent here either, and the caller asks both — a comment
  CARRYING one of those members is claiming a rewrite it cannot produce, and the branch behind that claim is exactly
  the one commit that reads as having nothing left to rewrite, so the squash refuses rather than reporting success.

  Shape is not enough to ACT on either. Before a resumed publication runs, both recorded ends are peeled as objects
  this host really holds, the base has to be a commit the head was really built on — a walk between two histories
  that never met reports a number like any other, so the count is no ancestry proof — the history between them is
  walked against the recorded count, and the commit on the branch has to carry both the tree the recorded head left
  and that base as its one parent, which is what a squash produces by construction. The parent matters as much as
  the tree: the same tree re-parented onto a base that has since advanced is a commit that *reverts* whatever that
  base added. A record failing any of those is one somebody could have written and this repository never produced,
  so the branch is left exactly where it was found and the tick refuses.

  `late_collapse_count` is the number of commits the branch really carried, walked rather than counted from their
  subjects: `git commit --allow-empty-message` makes a commit that contributes no subject, so a count taken from
  the subjects is short by however many of those there are — and the recovery would then refuse a collapse this
  workflow really made as miscounted. `1` is the subject rewrite of a one-commit branch, and it is a record like any
  other: the same walk proves it, the same resume finishes it, and the only thing it does not buy is the notice.

  The record is ended by the write that ends what it claims and by no other: the reset a rollback made, the reset
  that never ran, and — for a push that landed — the approval handoff's own write, which is deliberately the write
  taken **before** the relabel. That last one is the transition below: the claim is cleared first and the settled
  handoff staged second, so no comment a write could land from ever carries both. The count is what the
  `:package: squashed N commits to 1` notice is worded from, so a notice that was owed and did not post leaves it
  standing; and past the relabel the issue belongs to `documenting`, which never runs the recovery that would
  answer a claim left there. A tick that dies before that write comes back to the same branch and the same answer —
  an already-published collapse is finished as the leased no-op it is, and an untouched branch is squashed afresh.
- **Settled handoff.** `late_collapse_handoff_sha` is what that write leaves in the claim's place, on the
  [`handoffs`](../../orchestrator/workflow/late_split/handoffs.py) owner beside the group above rather than among
  it, and it exists for the one boundary that group cannot cover: the relabel is a second call, and an issue left on
  `workflow:validating` with the record simply dropped is one the next tick runs a second reviewer on, over a branch
  already approved, squashed, and published. It names the commit the move is owed over, which is the whole of what
  the move needs and the only thing that says it is owed. The validating recovery route reads it ahead of the
  reviewer, moves the label, and drops it in a guarded commit of its own behind that label — laid over the comment
  read again once the label has moved, and only where it still names the commit that handoff finished beside the report,
  `pr_number`, verdict, and evidence records the move was taken over and the review subjects the comment carried
  just ahead of it, so a record another road wrote during the relabel stands, and so does this one where those
  records moved; the `workflow:documenting` tick that finds either
  hands the issue back here without ending it — and spends it only while the
  pull request is still standing on the commit it names, since anything that moved the publication on has moved the
  work past the round the record was about, and the branch then goes to the reviewer rather than on to
  `documenting` unread. It is deliberately NOT a member of the group above: nothing about the rewrite is
  outstanding by then, so it freezes no branch out of base sync and refuses no resume. An approval that collapsed
  nothing leaves one too, over the head it was given, since a relabel that fails -- or the handoff's write landing
  with its response lost -- would otherwise leave nothing saying its move is owed and the next tick would pay a second
  reviewer for it. One whose commit is not a whole object id leaves none: the value is spent on a
  comparison against the head the pull request stands on, so one no commit could equal is one that comparison can
  never catch — and on an issue with no pull request to read, nothing else stands between such a value and a label
  moved past the reviewer. Such a value is dropped rather than refused, which is the opposite of what the claim it
  succeeds does with one: that claim is written before the reset, where a refusal costs a rewrite nobody has made
  yet, while this one is written past the push and past the notice, where there is nothing left to call off. It is
  read for a usable value rather than for presence, the opposite of the group above and for the opposite reason —
  the worst an unreadable one can cost is the reviewer round the route would have saved, so it is dropped and that
  round runs.
  The record left by a relabel that DID land is ended by `documenting`, at the top of its own tick, and that stage
  is the only owner that can end one: having the issue is the proof the move happened, and the label history cannot
  tell a move that never happened from one a drift unwind later reversed. Left standing there, the unwind's
  re-review would be answered by relabelling the unchanged head straight back to `workflow:documenting`.
- **Sealed consumer ledger.** `split_ledger_sealed` says the register of children a split recorded is FINAL. The
  count written before the first create (`expected_children_count`) is what tells a partial ledger from a whole one,
  and a loop a cancellation stopped can never reach it — so the ref its children were cut from would be held on a
  proof no pass could complete, and the owner's terminal with it. The seal is written only by that loop, and only
  where every child that exists is already on the register: every barrier that ends it is asked after the write
  recording the child in hand, and no further one will be opened. A **resumed** walk stopped before it reached the
  first unrecorded index writes none, because a child an earlier attempt created and never recorded would not be
  on the register and only the adoption lookup can say otherwise. The field holds the **cycle** the seal belongs to
  rather than a bare flag, and is believed by that cycle alone. It is a decomposition key, so the write that clears
  late mode leaves it exactly where it was: read as a bare "yes", a later split stopped mid-loop would look complete
  and release the ref its own unrecorded children were cut from. A drift reset drops it beside the count it is a
  fact about, and so does a restart's projection, which keeps nothing about the cycle whose register it sealed.
  Anything that is not a positive identity reads back as no seal at all — which holds the ref rather than releasing
  it.
- **Applied terminal.** `late_terminal_cycle_id` and `late_terminal_confirmed` are one two-phase record of a cycle's
  `rejected`, and they sit outside `LATE_STATE_KEYS` with the retired cycle for the same reason: clearing late mode
  drops exactly the generation's own group, and this is a fact about that generation an ending writes and a later
  tick reads back. Together they are the only durable evidence that the label an operator removes to authorize a
  restart was ever applied — without it an issue whose workflow label a human stripped mid-cleanup, and one whose
  terminal write GitHub refused, are both indistinguishable from one whose `rejected` was taken off deliberately, and
  the fresh cycle would start on a gesture nobody made.

  Two phases exactly as an external obligation has them. The **decision** — the identity alone — goes down before the
  label write, so a tick that dies in between has something durable to come back to. The **proof** goes down only for
  a `rejected` that actually landed. Only the pair authorizes a restart; an attempt is not a terminal. Recording the
  decision drops any proof standing beside it, since the same field is reused by every cycle an issue ends.

  The proof is reached three ways. `_retired` takes the write **returning**, and has to: reading the label back proves
  no more than what that write left on the issue object it went through, and on any other object answers with the one
  the issue wore a moment ago — and a closed owner leaves the sweep on that write with no second visit to correct it.
  `_terminal_proved` takes the other side, recording the proof for any visit that *finds* the label on the issue,
  which is what makes the record compatible with cancellations that ended before it existed: such an issue wears
  `rejected` and records nothing, and the first pass to see it writes the proof down.

  `_terminal_recovered` covers what neither reaches. Two records look identical and mean opposite things: the label
  landed and the process died before the receipt, and the label write GitHub *refused*. Nothing revisits the closed
  `rejected` owner the first leaves, so the operator's reopen is the next thing that happens, and their removal makes
  the two indistinguishable locally. A cancellation that ended before this record existed is a third, carrying
  neither half. So the remote's own label history is asked, and the decision is deliberately **not** required to ask
  it — demanding one would leave every pre-field cancellation needing a second removal. What gates the read instead
  is that the issue is unlabeled over a cancelled cycle that owes nothing and has no proof, which also bounds the
  cost: an unlabeled owner whose cleanup is unfinished is visited every tick, while one that owes nothing is written
  back to `rejected` on the same tick it gets no proof, so the walk costs one request per removal rather than one per
  tick.

  What that read asks is which workflow label **this orchestrator** applied **last**, not whether `rejected` was ever
  applied. The actor narrows it because a terminal is a write this orchestrator makes, and a collaborator is free to
  apply and remove the same name by hand — reading one of those back would let somebody outside the workflow forge
  the record of a write it never made, so the events are filtered on the same account the pinned comment is
  authenticated under, and a client that could not establish one answers nothing. The newest narrows it because an
  issue reaches this terminal once per cycle, so a repeat carries an older one in its history, and adopting that
  would authorize a fresh cycle off a removal an operator made a cycle ago. The cycles are separated by construction:
  a cycle exists only because a restart retired its marker, and a restart retires only once its own target label has
  landed as one of *this orchestrator's* applications — which is why a restart that finds the target already applied
  by somebody else takes the name off and puts it back — so a stale `rejected` always has a later application of its
  own standing after it. Control
  labels are excluded too, since a `paused` applied over a terminal is a modifier rather than a state this workflow
  moved the issue to. A history whose newest application is some other state, one naming nothing this vocabulary
  recognizes, and one that could not be read all fall the same way: the terminal is written again rather than a fresh
  cycle started on a removal nobody made.

  The read happens from **behind** the reconciliation, in the same pass and after `_reconciled` has run, because what
  decides whether anything is still owed is the record the ending has just settled rather than the one it found. An
  obligation the ending *discovers* — the branch a supersession left behind and never wrote down, derived from the
  announcement's own receipt — is on no ledger until that pass puts it there, so adopting a proof in front of it
  would let the restart project the branch away with the receipt it was derived from. The cost is one tick: the pass
  that recovers the proof is the one before the pass that restarts. With all three proof paths, the operator's first
  removal is still the one that authorizes the fresh cycle.

  Both fields are read fail-closed (a hand-edited identity, or a `"true"` string, is no proof at all) and both
  are dropped by a restart's projection, with the fresh cycle's own ending writing them again.
- **Approved commit.** `late_approved_sha` is the commit this issue owes a publication and no push has carried yet. It
  goes down in the same write that approves one — the retirement a small candidate earns, the exemption an
  authorized settlement records, and the grant that authorizes a rewrite to carry one of those exemptions over,
  where the
  permission and the debt have to be one write or neither — and is dropped by whichever handoff spends it (the
  recovery that republishes, or the ordinary
  `validating` advance, which writes the drop durably ahead of the relabel), by an adjudication that supersedes it,
  and by any publication naming a different commit: a debt recorded for work nothing is going to push would freeze the
  branch for the rest of the issue's life. It is a floor as well as a debt — a run resumed on top of that commit has
  to move the head to have committed anything. Like `late_exempt_sha` it names one commit and is deliberately outside
  `LATE_STATE_KEYS`: the generation it came from is retired before the push it licenses, so a record cleared with the
  group would leave nothing on the issue naming the work — which is exactly what a replacement host would then publish
  over. It is proved before anything spawns and it is what the `late_candidate_moved` park is answered by, together
  with a status read that has to prove the tree around it carries nothing. What either
  read does with it is a comparison, never a substitution — a head that cannot be peeled, or one that peels to
  anything else, leaves the park exactly where it is. It freezes the branch out of the pre-tick base refresh for as
  long as it stands, and there the freeze IS the remedy: what settles this park is an operator putting the worktree
  back, so a rebase between their `git checkout` and the tick that would have noticed moves the head off the approved
  commit again and leaves the one park answerable without a comment with nothing left to answer it. It never stands
  alone: `late_approved_basis` goes down, is carried, and is dropped with it by every write named above, and says
  which owner granted the debt — spelled out beside the accepted candidate it shares its window with, under
  [late generation state](#late-generation-state).
- **Incomplete run.** `implementing_incomplete_run_sha` is the commit a developer run left when it did not COMPLETE — a
  timeout, a provider refusal, a nonzero exit — and so recorded no report by design rather than by loss. The publication
  seam writes it from the checkout's head for every such run, and the timeout-park recovery for the commit a timeout
  stranded, durably and before the size gate; a run that COMPLETES retires it in the same write that records its report
  — or parks it for the one it lacks — since that report describes the branch it leaves, and a crash between two writes
  would leave the new report beside a waiver that reads it as an older run's. A recovery that republishes exactly this
  commit later — a measurement retried, an approval paid — is owed no report either; any other commit is not covered,
  and a value that is not the commit a recovery proved matches nothing, so a hand edit waives nothing. The one waiver it
  does not grant is over a delivery or transaction an earlier run recorded and has not settled: that report describes
  the branch before this commit, so the commit parks under `report_undeliverable` before the size gate, the record kept,
  rather than going out beneath it. Owing no report is not owing no reading: the requirements such a commit was written
  against are still read again before its handoff, and an edit since holds it for the drift resume. Additive: an issue
  without it simply has no incomplete run recorded.
- **Published pull request.** `implementing_published_pr` is the pull request the recorded publication went onto,
  written with the receipt below and never on its own. The receipt says a commit reached a remote and the head it
  replaced dates that to one attempt; neither says which pull request now carries the work, which is what the
  bookkeeping behind a landed push is bound by. `pr_number` cannot stand in: that is the relabel's write, so it is
  missing for exactly the window the receipt exists for — a push that landed and a process that died before it —
  and the only other way to name one is a lookup by branch, which answers with whatever is open on that ref. A
  replacement somebody opened after closing the original satisfies such a lookup, so recovery would bind the
  relabel, the debt and the receipt to a publication this stage never made. Read fail-closed like every other late
  identity, and absent or unreadable the delivery proof refuses rather than searching. It is also the third term the
  own-push carve-out is held to: every owner that freezes or proves a publication refuses a head somebody else moved,
  and the one exception is a receipt saying this issue's own push put it there. The commit and the head it replaced
  cannot establish that between them — a branch pushed from that head onto a pull request since closed and *replaced*
  by another on the same ref satisfies both — so the number the receipt names has to be the publication the caller is
  proving against. The size gate's entry freeze, the settlement's proof and the squash resume all ask it that way.
- **Published commit.** `implementing_published_sha` is the commit the last gated push carried — the one that passed
  the gate, or the checkout's own head on a push the switch named none for, since `DECOMPOSE` keeps candidates out of
  the gate rather than off the remote and is an operator's to turn back on. It keeps the implementing spelling it was
  minted under, but it is written by every seam the gate stands in front of, the pushes onto an already-open pull
  request included: each of those has the same window behind it, and a receipt naming what reached the remote is what
  tells a candidate a later tick still owes a push from one it has already made. On that side it is read together with
  the head the gate froze, because it is a local note about a remote fact: a receipt naming a commit the pull request
  has since moved off is a record of a publication that is over, and the candidate goes back through the ordinary
  reading rather than being waved past as already published. The frozen pull request is compared with it on the same
  terms, because a head says the work is *there* and nothing about how it got there: a receipt naming some other
  publication — an earlier one of this issue's, a replacement opened after the original closed — vouches for nothing.
  On the implementing seam neither was frozen, so the same question is put to the *remote*: the pull request the
  record names, open, on the branch that seam would push, with its head in this repository, standing on this exact
  commit, and with the receipt recording no LEASE — a lease names the head a push replaced and is written only by a
  call that froze one, so a receipt carrying one was left by some other call entirely and its commit matching the
  candidate is a coincidence the proof may not spend, since the fresh receipt behind the push clears the very field
  that said which attempt the record was about. The repository is asked because a fork carries these ref names over
  these commits and would otherwise agree on
  everything else, asked through `github/client.py` against the name GitHub uses and matched case-insensitively, so
  a setting typed in another casing is not read as a stranger's. A receipt GROUP this build cannot read whole is asked
  apart from that comparison and refused first — from either seam, since the three are one record — because every late
  field is read fail-closed and a hand-edited one comes back as no receipt: published over, the push writes a fresh
  group across the damaged field. Three shapes are damage. A member whose KEY has gone while its siblings are there is
  the first, and it is why presence is asked of every member rather than of the commit alone: the write puts all three
  keys down, `null` included, so one that is missing is a hand edit and not the empty lease an initial publication
  records. A member carrying a value nothing can read is the second. An ORPHAN lease or number with no readable commit
  beside it is the third, and it is the one a commit-only check walks straight past. Only `null` and `""` read as an
  empty member — the payload is JSON, so `false`, `0`, `[]` and `{}` are all present damage that an "empty means
  absent" reading would wave straight through. An empty LEASE is the one member that is not damage where its key is
  there: an initial publication froze no head and records `null`. Anything short of the
  proof PARKS rather than falling through to the reading: measured and found small the commit would simply be
  published, which force-pushes a branch nothing could confirm and opens a second pull request over work the first one
  already carries. The park writes nothing else — the receipt, the recorded number and any debt beside them stand for
  the terminal that drains finished work or for the retry behind a repair. Nothing is outside it — a commit an
  exemption names or an approval owes a push for least of all: each answers whether a fresh *reading* is needed and
  says nothing about where the work went, and the delivered road records the commit as a debt before it pushes, so a
  crash there leaves an approval with no lease to publish under.

  What the answer then carries is the pull request *number*, because a reading is a moment: the push behind it is
  leased against that exact commit, so a branch moved in the window rejects it rather than being force-overwritten,
  and the bookkeeping is bound to that pull request, so one closed in the window holds the tick rather than earning a
  second one over the same work. For the same reason it is not evidence that
  a pull request found somewhere OTHER than where a caller entered it got there by this issue's own push: it is never
  cleared, so a branch a revert or a rewrite rewound onto a commit published rounds ago would be measured and
  force-pushed over. Only the three readings a live window drops — the candidate a caller names, `late_approved_sha`,
  and a live generation's `late_candidate_sha` — answer that question. It is the same commit the push was named
  against rather than a second reading of the checkout, which could have moved while the push and the pull request
  were in flight; the pre-push half of that decision is durable as `late_approved_sha`, so a tick that died in the
  window leaves a receipt either way. It is written in the same pinned
  write that spends every record the gate decided by and ahead of the relabel that hands the issue to `validating`.
  It exists for the window between those two: a relabel GitHub would not take, or a process that died before it,
  leaves an implementing issue whose branch is on the remote and whose pull request carries it, with the approval and
  the generation both already gone. Read as work nobody has ruled on, that branch is measured again against a base
  that has moved and a ceiling that may have been retuned, and an oversized answer would route it to adjudication —
  with the push and the pull request already made, which is the one outcome the size gate exists to prevent. Recorded,
  the next tick recognizes the commit, publishes it without a reading, reuses the pull request that already carries
  it, and lands the label. Like `late_exempt_sha` it names one commit and only it, which is the whole invalidation
  rule and why there is no clearing step: work committed on top is work this stage has not published and is measured
  as the fresh candidate it is, and the next publication overwrites it. It freezes the base refresh on exactly the
  terms `late_exempt_sha` does, and for exactly as long: the refresh reads the CHECKOUT and the LABEL, so the branch
  is held still only while the head is still this commit *and* the issue still carries a deciding-stage label. That
  window is the one the record exists for — between the push and the relabel the branch is on the remote, its pull
  request carries it, and a rebase there would move the head off the commit the next tick has to recognize, leaving
  it to re-decide a published branch. The freeze ends with the handoff: past `workflow:validating` the label no
  longer matches, and keeping a pushed branch in step with base is the PR-aware sync's own job, which is the only
  route that can move it without stranding the reviewer's SHA.
- **The head that publication replaced.** `implementing_published_lease` is written with the receipt above and never
  on its own, exactly as `late_approved_lease` is written with its approval: it names the head the recorded push was
  PINNED to — the one the gate's entry froze, or, for the accepted push a `single` settlement makes from its own
  approval, the lease beside that approval. An initial publication froze no head and records none. It exists because
  the receipt cannot date itself. Read alone the receipt goes on naming a commit this stage pushed rounds ago and so
  vouches for any pull request somebody rewound onto it; read with the head it replaced it answers for one window and
  no other — a push made from the head a caller froze, on a tick that died before the relabel behind it. Both the
  size gate's entry and the `single` settlement's own reconciliation ask for the whole group — this head and
  `implementing_published_pr` beside it — and a receipt whose head is absent or names some other commit forgives no
  moved head at all. Cleared with every receipt that is written rather
  than left for the next one to inherit, since a receipt wearing an earlier attempt's head is the one that vouches
  for a publication somebody else moved.
- **Retired cycle.** `late_retired_cycle_id` is the one fact about a dropped generation that outlives the drop: the
  write that clears late mode records which cycle it was clearing. It exists for a single window — a poll observing
  the close *inside* that write leaves a cycle-scoped receipt on the thread, and the record it would be adopted
  against has just stopped naming a cycle, so a process that dies before its own post-write barrier would strand the
  observation with nothing left to correlate it to. A record carrying the stamp and no generation is asked once per
  owner and cycle — and again once another poller on the host has held the issue since — whether the thread has that
  cycle's receipt, unless this process already holds a close scoped to that cycle; one that does gets the cycle put
  back, cancelled, with the ledgers the retirement carried across, and the ordinary ending runs from there. Every
  retirement that drops
  a cycle records it — an authorized settlement's publication, the umbrella terminal's, a settled `blocked` parent's
  hand-back to its own work, and the size gate's own drop of a candidate it measured at or below the ceiling, which
  needs it for the same reason: the barrier behind each write belongs to the process that made it. All four take the
  same window around that write — the hand-back keeping `workflow:blocked` where the umbrella's terminal keeps
  `workflow:umbrella` — and the gate's is the
  one with the most to lose behind it: past its retirement come a pushed branch, an opened pull request, and a relabel
  to `workflow:validating`, so a close dropped in that interval would hand a closed issue to review. The latch is
  asked ahead of the write and the window's own answer behind it, and a close either side of it ends the cycle instead
  — cancelled, from the generation still in the call's own memory, with nothing published to take back. It is also
  what the next candidate on the issue mints its cycle after, so a measurement taken after one that published cannot
  answer to the number that one did. It names **one** window and outlives no other, because the receipt it reads is a
  comment and comments are append-only: a correlation left standing would let a cycle-scoped receipt be adopted
  against a record whose cycle is two generations newer, moving a completed owner from `done` to `rejected`. Two rules
  end it. A generation written with an *identity* supersedes it — which is both the adoption consuming its own marker
  (the mark it writes puts the cycle back) and an operator's authorized restart superseding it. So a terminal that
  retires cycle N names N and nothing else, and a receipt for any earlier cycle on the same thread matches nothing an
  adoption would read. - **Cancellation.** `late_cancelled`, `late_cancelled_at`, and `late_cancelled_phase` are
  irreversible within a cycle: once the owner has been observed closed, a later tick that sees it reopened re-marks
  the same cancellation and moves none of the three. Two passes observe it. The post-agent owner guard is one — a
  fresh read taken after every completed late run, before anything it earns happens, and taken again inside the split
  transaction before every step the remote keeps: each child it creates, and the announcement, supersession, and
  activation behind them. A child is the one thing created here that nothing takes back, and a close a poll saw while
  that worker held the issue reaches no other pass on the tick it happened. The closed-owner cleanup sweep is the
  other, and it is what catches a close at any of the boundaries no agent was running at — a measurement, a hold, and
  everything past the transaction — as well as one the scheduler could admit no worker for, which the dispatcher holds
  and this sweep takes on a later tick. Either writes the mark durably *before* any external effect and emits
  `late_cancellation` from that write, so the record is one per cycle rather than one per visit. What the remote is
  still owed stays on the two ledgers for the [cleanup
  path](delivery-stages.md#closed-owner-cleanup-sweep-no-label-of-its-own) to settle, and only once it has does the
  owner reach `rejected`. A cancelled cycle is nobody's to adjudicate, relabel, or route, so a reopened issue does not
  get this cycle back. The dispatcher's own pinned-state guard catches a reopened owner, runs the same cleanup, hands
  it to no stage handler, and writes the same `rejected`
  ([delivery-stages.md](delivery-stages.md#the-reuse-guard-every-dispatch-ahead-of-every-handler)) — reaching that
  terminal is the only way back into ordinary work, and what authorizes the fresh attempt is an operator removing the
  label rather than a human reopening the issue. That guard refuses a cancelled cycle under *every* label it can be
  wearing, since each one names a handler that would act on the issue rather than end it, and it writes the terminal
  wherever the graph declares the edge from — plus `ready` and `blocked`, which the cycle's own decomposer writes as
  its ordinary outcome and which no query would ever bring a tick back to. The unlabeled state is refused with the
  rest of them: the [restart](#late-generation-state) is asked one guard ahead, so an issue reaching the refusal with
  no label is one the restart already declined — and letting it fall through would hand a cancelled cycle to the
  pickup path, which greets it as new. That ordering is also what keeps a restart between its label write and its
  retirement safe: it wears a live-looking label over a record that still says cancelled, and the refusal would answer
  that by handing the issue `rejected` again.

  What the unlabeled state still decides is whether the terminal may be written from it, and the RECORD answers
  rather than the label, because three different issues wear the same nothing. One is the handshake — an operator
  took `rejected` off, and re-applying it would undo the only authorization a restart has. Another never got the
  terminal at all: a human who strips a workflow label mid-cleanup leaves the ending owed under a state it cannot be
  written from, so every visit since has settled obligations and stopped. The third had it attempted and refused. The
  *proof* half of the terminal record separates the first from the other two.

  `late_cancelled_phase` is the boundary the cancellation interrupted, kept because `late_phase` becomes
  `cancelling` and that answers nothing: whether the consumer ledger accounts for every child cut from this
  generation's snapshot is read off the phase whenever the record cannot prove that for itself, so a record that
  forgot where it was cancelled from could never prove a ref reclaimable again. A cancelled record carrying no such
  boundary — one an older binary marked, or one whose own field was damaged — reads as unprovable and keeps the
  ref. The boundary an interrupted transaction stood at is kept rather than rewound: no boundary before a split --
  `measuring`, `holding_plan_pr`, `adjudicating`, `owner_check` -- is ever written over `snapshotting`,
  `splitting`, or `superseding`, and the record refuses that move itself rather than each writer remembering to,
  since a transaction re-entered after a crash comes back through every retry above it. A child is created before
  the write that records it, so the phase is the only thing that says a loop was in flight when nothing is recorded
  yet. Beside that, a pre-split phase is believed only as far as the record bears it out: one standing beside a
  recorded consumer, a split child,
  or the stage's own `expected_children_count` — written in the same durable step as `splitting` — is a partial
  split wearing an earlier name, and its ref is kept. The count is asked of every boundary before the phase is
  consulted at all, since a record it proves finished is whole wherever it stands — which is what answers both
  `splitting`, written before the first create and again beside every child recorded, and a `snapshotting` a
  retry rewrote over a split that had already finished. It is also what upgrades a pinned comment an earlier
  binary rewound, since nothing migrates records already in flight.
- **Pending restart.** `late_restart_pending`, `late_restart_target`, `late_restart_cycle_id`, and
  `late_restart_predecessor` are written before the restart's own external effects by the
  [`restart`](../../orchestrator/workflow/late_split/restart.py) owner, and beginning a restart is create-or-keep — a
  marker already names the cycle it intends, so a crash between the write and the label resumes that cycle rather
  than minting a second one. *Believable* is the condition on both halves, and it takes the whole marker: the pending
  flag is set, the target is one of the two labels a restart may apply (`workflow:decomposing` /
  `workflow:implementing`), the predecessor is exactly the cycle the record is on, and the pending cycle is exactly
  the next one after it. A marker failing any of those is a damaged field rather than a restart in flight and is
  re-minted from the current cycle — honoring one would hand the fresh attempt a number an audit record never issued
  (cycle 2 with a pending 99), an ancestry nothing wrote (a predecessor of 500 under cycle 2), or a label nobody
  chose. The *requested* target is checked before any of that, so a marker already standing never excuses an argument
  outside the pair. Retiring is the one step that refuses instead of re-deriving: the fresh cycle keeps no ledger, so
  `retire_restart` raises while any obligation is still pending, retained, failed, or of a shape this binary could
  not read — restart is reachable only from a cancellation whose cleanup completed, and retiring over an unsettled
  ledger would discharge the obligation by forgetting it. `restart.obligations_settled` is the same question a caller
  can ask first. What it projects when it does retire is a fresh cycle keeping only the identities that link it to
  the one before: the cycle it is, the issue and root it belongs to, and the cycle it succeeds — with the lineage
  depth back at the root's 0 and the generation counter back at 0, because a restarted issue is a fresh attempt with
  room to split rather than a cancelled one wearing a new number.

  Who writes those fields is
  [`late_restart.py`](../../orchestrator/workflow/stages/decomposition/late_restart.py), the stage owner the
  dispatcher asks ahead of the cancelled-cycle refusal. What it requires before it writes anything is a *settled*
  cancellation — a cycle that exists, one a close already ended, and one that owes nothing — plus proof the terminal
  was applied (`late_terminal_confirmed` beside this cycle's `late_terminal_cycle_id`) and the gesture that removed
  it: an OPEN issue wearing no workflow label at all. Both halves are needed, because the gesture, a workflow label a
  human stripped mid-cleanup, and a terminal write GitHub refused all leave the issue looking identical, and only the
  record separates them.

  "Owes nothing" is both readings, not either: the ending's own outstanding list and `obligations_settled` overlap
  without containing each other, so the guard asks the cancellation owner as well as the domain. Only the ending
  reports a `late_plan_pr_number` standing with no `late_plan_pr_body` beside it — a hold nothing can prove, carried
  on no ledger, and repairable only by a human — and projecting the fresh cycle over one would delete the last thing
  on the issue naming a pull request this orchestrator left marked and open. Only the domain counts an undischarged
  child receipt or a consumer ledger this binary could not type, and a restart that reached its retirement over one
  of those would be refused there with the marker already down and the label already applied. Asking both is also
  what keeps this guard and the refusal behind it exactly complementary: the tick one stops is the tick the other
  runs its ending on. A marker already standing answers the gesture for itself
  whatever label the issue now wears, since only this owner writes one and only after the authorization was proved.
  Everything else is inert: an unlabeled issue with no late cycle is an ordinary pickup under the ordinary rules, a
  cancellation still owing the remote is the cleanup path's, and a closed issue is the sweep's.

  `ALLOWED_ISSUE_AUTHORS` is deliberately not asked on this path. It guards the one route a stranger reaches on
  their own — an unlabeled issue picked up automatically — and nobody reaches a restart that way: it takes a pinned
  comment only this orchestrator writes and a label removal GitHub grants only to a repository's own people. The
  fresh attempt is authorized by whoever made that gesture rather than by whoever filed the issue, so an outsider's
  issue an operator has decided to restart is restarted.

  Two identities are repaired before anything is written, and neither is the cycle: `late_current_issue` becomes the
  issue the pinned comment was read off, because a field naming another one would file the fresh cycle — and both
  sinks' records of it — under an issue the pass is not about; and `late_root_issue` is kept where the record is this
  issue's own and re-derived from `late_ancestry_root_issue` (falling back to the issue itself) otherwise, because a
  root naming no issue is a record the telemetry contract refuses outright, which would let a restart run to
  completion saying nothing about itself. On a healthy record both are the values already there.

  The transaction is three ordered steps over the one pinned comment, and each is idempotent so a crash resumes at
  the step that is still owed. The marker goes down first, `late_phase` moving to `restarting` with it. Then the two
  external effects: one notice on the thread, suppressed by a marker scoped to the cycle being minted, and the
  target label, skipped where the issue already wears it *and this orchestrator is what applied it*. Where somebody
  else applied that same name, it is taken off and put back instead: what the write leaves behind is not only the
  label but the bot-authored application separating this cycle from its predecessor's terminal, which
  `_terminal_recovered` reads below, and GitHub records no event for a label already present. A notice an earlier
  pass posted is *adopted* rather than
  merely recognized — posting tracks its id in memory and the write that would make it durable is the retirement two
  steps later, so a pass whose label or retirement then failed left the id nowhere, and the marker suppresses the
  repost that would have tracked it again. Only once both effects have reconciled is the marker retired.
  Which label is applied is the current `DECOMPOSE` setting's answer at the moment the marker is written and the
  *record's* answer from then on, so a restart begun under one setting and resumed under the other finishes the
  label its own notice announced. A refusal from either effect is logged, recorded as a `late_failure` carrying
  `restart_failed`, and left for the next visit with the marker standing; `backlog` / `paused` defer the whole of it,
  since the authorization sits on the issue's own surface and cannot be lost.

  The retirement's own write is the **projection**, and it is a whitelist rather than a list of deletions: every
  stage shares this comment and each adds keys of its own, so naming what to drop would carry whatever the naming
  was not written for. What survives is the pinned comment's own identity (the payload is rewritten in place rather
  than a second comment minted), `orchestrator_comment_ids`, the four cumulative `issue_*` usage counters, the two
  agent-run ledger fields the `run_ledger.py` owner names as its projected group (`agent_run_allowance` and
  `agent_runs_used` — a lifetime ceiling a restart handed back would be no lifetime ceiling at all, and the allowance
  travels beside the count so a fresh cycle is not parked on its first run by a ceiling the projection dropped), and
  the fresh generation's own identity — and, on an issue this orchestrator opened whose body carries an ordinary
  split's child receipt, the seed that receipt holds it to: `parent_number` and whatever of the `late_ancestry_*`
  group it carries, pointer included, kept exactly as carried (`split_seeds.carried_seed`), since the dispatcher holds
  that child to its seed on every later dispatch. Everything else goes — every session id, `pr_number` and `branch`,
  `children` / `dep_graph` / `expected_children_count` / `split_ledger_sealed`, the whole `late_ancestry_*` group on
  any other issue and the exemption beside it with the identity it carries, `awaiting_human` / `park_reason`,
  `user_content_hash`, the retry, review-round and park counters, `agent_run_reservation` (a launch, not a fact about
  the issue — the fresh cycle has none), `agent_run_limit_notice` beside the park it explains (an obligation is a claim
  about one park, and the sentence it carries quotes a spend the fresh cycle will re-read for itself),
  `agent_run_limit_displaced` with it (the park it names is one the fresh cycle is not on), and every timestamp.

### Exemption identity and rotation

An oversized change an operator authorized is recorded three ways, and each answers a different question. All three
are pinned-state compatibility contracts on the same terms as the rest of the late group — additive, read fail-closed,
and never migrated on a live issue — and each is described in full in the
[late generation state](#late-generation-state) entries above. This section is the map between them.

- **Exact publication identity** — which COMMIT was accepted: `late_exempt_sha`. A publication of exactly that commit
  skips the reading, asked together with the `late_override_*` authorization naming it, whose recorded pair is
  re-fingerprinted first. A later settlement records it for another commit, and a settled rotation moves it.
- **Semantic identity** — which CHANGE was accepted: `late_exempt_base_sha`, `late_exempt_candidate_sha`,
  `late_exempt_fingerprint`, and `late_exempt_fingerprint_format`. It licenses nothing on its own: it is the evidence
  a rewrite is proved against. It is dropped when the exemption is recorded for another commit, and moved with it by
  a settled rotation.
- **Proven rotation** — which workflow rewrite carried the exemption over: the `late_rewrite_*` group, with
  `late_rewrite_proof` beside it. It licenses moving the exemption, its identity, and the operator authorization from
  one exact commit onto one other. The next grant replaces it, and an `authorized` one is dropped by a rollback that
  landed or by a publication that went past it.

A restart's projection drops all three with the branch they describe.

**Two phases, each one write.** `late_rewrite_phase` is a closed vocabulary of two:

1. **`authorized`** — the grant. `late_transfer` writes it before the push, in the same write as the
   `late_approved_sha` / `late_approved_lease` debt that push is owed, and it moves nothing: the exemption and its
   identity stay on the accepted commit, which the group is bound to through `late_rewrite_from_sha`, because the
   rewritten commit is on no remote yet.
2. **`published`** — the settlement. `late_rotation` stages it into the write that receipts the landed push, so the
   exemption, the semantic identity, the operator authorization, the `implementing_published_*` receipt and its lease,
   the paid debt, the route bookkeeping the landing closes, and `late_rewrite_proof` (`pushed` or `already_published`)
   land together or not at all, and the group is bound through `late_rewrite_to_sha` from then on.

On every publication still to be made, only a permit `late_transfer` re-asked on the settling tick spends a grant.
A grant no permit vouched for is left standing for a later tick to settle, a grant the publication went past is
dropped, and a refused permit is never read as equivalence: the rewrite goes to the ordinary cumulative gate, or, on
the base refresh's permit-only crash recovery, parks — save the retry of a replay its attempt's record names with no
grant made before the crash, which goes to the cumulative gate as the interrupted publication would have. The one
settlement with no permit to re-ask is a pull request that merged or closed on the rewritten commit before the receipt
was written: a permit licenses a push about to be made and this one is behind it, so the attempt's terminal handoff
holds the grant to its own binding instead — read back whole, still `authorized`, and naming the commit the pull request
ended on, the anchor it was pushed from, and that pull request — and settles it as `already_published`. A grant that
fails those terms is dropped only on the rollback's own rule — read back whole, still `authorized`, and granted over
that same anchor — while a damaged group, a `published` one, and one bound to some other head are left standing,
fail-closed.

**Who may present a rewrite.** Only the owner that RAN it, since nothing read off a branch tells a replay from work
somebody else wrote. The kind and the stage it was entered from are one claim, and a pairing no owner produces reads
back as no authorization.

- `squash`, entered from `validating`: the squash on approval (`implementing/late_rewrite`), which reads the head it
  collapses and its merge base before the reset. Its recovery is the recorded collapse (`late_collapse_*`), answered
  ahead of every `validating` route.
- `auto_clean_rebase`, entered from `validating`, `documenting`, `in_review`, or `fixing`: the base refresh's clean
  rebase (`workflow/engine/rewrite_publication.publishes`). Its recovery is the refresh's own crash recovery — the
  reissued push (`workflow/engine/rewrite_retry.retries`) and the leased no-op
  (`workflow/engine/rewrite_landed.recovers`), both `permit_only` save where the reissued push is of a replay the
  attempt's record names with no grant made before the crash, whose refused evidence it measures instead — and the
  terminal handoff of a pull request that merged or closed.
- `conflict_rebase`, entered from `resolving_conflict`: the clean rebase `conflicts/publication._publish_clean_rebase`
  runs. Its recovery is `conflicts/divergence._push_recovered_commits`, over the `conflict_replay_*` record written
  before the replay.

A caller that presents nothing is answered from an outstanding grant already on the comment, re-asked in full; with
none standing there is no transfer to ask about.

**What a permit is granted on.** A rewrite is a transfer question at all only where it is of the candidate in hand and
comes from the commit a whole semantic identity names as exempt; anything else is answered in silence. Past that,
every term below is asked in this fixed order, and a reading that could not be taken is a refusal rather than a pass:

1. Evidence naming both pairs and a kind its stage produces.
2. No rewrite group already claiming the exempt commit that this build cannot read back whole — a grant replaces the
   whole group, so overwriting that claim would repair evidence nobody checked.
3. The publication this call froze naming the pull request the rewrite and the issue record, and standing on a head
   the permit accounts for: the lease, or — only while the permission for this rewrite is still outstanding — the
   rewritten commit itself, which is that permit's own push having landed with its receipt lost.
4. A provably clean checkout standing on the rewritten commit.
5. A lease this host holds as an object.
6. The issue re-read open, carrying no `paused` or `backlog`, and still on the stage the rewrite recorded.
7. A rewritten base the remote's own base branch reaches.
8. An operator authorization standing behind the exemption, proved by re-fingerprinting the pair it records.
9. The contribution proof: the semantic identity re-fingerprints to its own digest over its own recorded pair, and the
   claimed and the rewritten contributions fingerprint to that same digest.
10. No permission already standing for the exempt commit whose recorded digest disagrees with the one just taken — a
    grant carried forward over it would write its own reading over evidence nobody checked.

**What a crash leaves.** The base refresh's journey is proved at every durable boundary on a real repository
([`tests/git/base_sync/test_real_git_journey_recovery.py`](../../tests/git/base_sync/test_real_git_journey_recovery.py)),
and every case of an unchanged contribution finishes without an agent run, a measurement, or a second adjudication, or
parks:

- **After the anchor, before `git rebase`**: the checkout is still on the anchor, so the attempt is dropped and
  rebased afresh.
- **After the local rewrite, before it was recorded**: the checkout diverges from the pull request with no
  `pending_auto_base_rebase_rewrite_sha`, so the replay is vouched for by what it contributes over the pinned terms
  and pushed under the lease.
- **After the replay was recorded, before the grant**: an exemption and no permission (*unrecorded*), so the evidence
  is re-derived from the recorded terms, the permit is asked, and the push goes out under the lease -- or, where the
  permit refuses it, the base advance changed the contribution, and the replay is measured as the publication would
  have measured it, adjudicated afresh past the ceiling.
- **After the grant, before the push**: an *outstanding* permission with the remote still on the lease, so the push is
  reissued on the permit alone.
- **After the push, before the receipt**: an outstanding permission with the remote already on the rewrite, so the
  leased no-op receipts it and settles the rotation as `already_published`.
- **After the receipt, before the record**: a settled transfer with `late_rewrite_proof` standing, so the one
  `late_transfer` record is made from that proof and the proof is dropped.
- **Before the notice, the mark, or the relabel**: a settled transfer, with or without the announcement mark, so the
  finish announces only where no mark records it — the one window before the mark repeats the notice and
  `base_rebased` — and relabels only where the relabel did not land.
- **After somebody else moved the remote**: a permit the lease no longer satisfies, or an *unvouched* record, so the
  attempt parks for a human with nothing spent, nothing reported, and no unleased push.
- **After the pull request merged or closed**: the attempt's terminal handoff settles a permission whose rewrite the
  pull request ended on (`already_published`) on the record's own binding, with no permit left to re-ask. Any other
  grant is dropped only where it reads back whole, is still `authorized`, and was granted over that anchor; a damaged,
  `published`, or otherwise bound group is left standing.

The squash and the conflict rebase reach the same two phases through their own records and share the rules around the
push: an outstanding grant makes the approval beside it defer to the permit, a remote already on the rewrite is
receipted by a leased no-op, and a re-ask the permit refuses falls through to the ordinary gate. They part at a push
the remote refuses. The **squash** rolls back: the branch goes back on the head it collapsed, and an `authorized`
permission is dropped once that reset has landed, since nothing will ever push the object it names. The **conflict
rebase** does not: `conflicts/publication._publish_clean_rebase` and `conflicts/divergence._push_recovered_commits`
each park `push_failed` with the rewritten commits still on the branch, and leave the `conflict_replay_*` record and
any permission beside it standing, so the push a later tick retries is the same replay that record and permission
describe.

**Legacy and damaged records fail closed.** None of them is repaired or deleted to reach its answer:

- `late_exempt_sha` with no identity beside it — a settlement an older build wrote, or one whose fingerprint reading
  could not be taken — keeps exact-SHA behavior and never permits a transfer: a rewrite of that commit is measured.
- An identity group with a member missing, a field that is not a whole object id or digest, a format this build does
  not compute, or a candidate other than the exempt commit reads back as no transferable identity. The exact-SHA
  exemption beside it goes on working, and the base refresh's crash recovery asks `unreadable_exemption` and answers
  such a claim *unvouched* rather than walking past it as though no verdict were in flight.
- A `late_rewrite_*` group that does not read back whole — a missing member, an unknown kind or phase, a kind its
  stage does not make, a bound end that is not the exempt commit — is no authorization. A grant may not overwrite a
  group that claims the exempt commit, so the permit refuses; a rollback cannot drop it; the refresh's recovery
  classifies it *unvouched* and parks.
- A `late_rewrite_proof` standing beside a proof, phase, or authorization nothing can account for is
  `stranded_transfer_proof`: the reconciliation parks once on it and the recovery answers *unvouched*.
- A reading that could not be taken — an object this host does not hold, a checkout `git status` cannot report on,
  a remote that will not answer — refuses, and is never read as equivalence or answered with an unleased push.

**What earns no waiver.** The exemption names one commit, and a rotation moves it only onto another exact commit a
workflow owner rewrote itself and proved — a recovery finishing a replay that owner pinned, or a grant it already
persisted, included. A descendant of the exempt commit, a developer's or reviewer's fix, the documentation pass, an
agent's conflict resolution, commits a recovery finds that nothing the rewriting owner pinned vouches for, a child a
split creates, and a replay that changed a single covered byte are each measured by the ordinary cumulative gate, and
an oversized one is adjudicated afresh. Equivalence is never inferred: an addition count, a commit subject, a
timestamp, tree or rename similarity, and `git patch-id` can each agree over a different change, and only the
canonical fingerprint is compared
([`../architecture.md`](../architecture.md#fingerprinting-a-prospective-contribution-gitmeasurementfingerprintpy)).

**What it reports.** One `late_transfer` record per settled rotation — both pairs, the publication, the rewrite kind,
and the proof — and no second `late_verdict`, since nothing was adjudicated again. Delivery is best effort: a sink
that refuses the record loses it, and a proof drop that does not land lets a later tick emit it again, identical
apart from `ts`. Its fields and its duplicate rule are in
[`../observability/event-streams.md`](../observability/event-streams.md#late-split-records-both-sinks).

### The late run

The keys above are the late-split DOMAIN's, and they describe the generation. Beside them sit the `decomposing`
stage's own, which describe the RUN that adjudicates one:

- `late_agent` and `late_session_id` — the locked spec and the session it opened.
- `late_agent_role` — the role the run was recorded under (`decomposer` for the adjudication itself).
- `late_run_cycle_id`, `late_run_generation`, and `late_source_sha` — the cycle, the generation, and the exact commit
  the run was spawned against.
- `late_result_verdict`, `late_result_category`, `late_result_question`, `late_result_split_blocker`,
  `late_result_children`, and `late_result_rationale` — what it completed with: the verdict, the category beside it,
  the sentence a `question` asked, the explanation a `single` gave for what stopped a split, the ordered child
  manifest a `split` decided on, each slice of it carrying the addition budget it was proposed at, and the bounded
  rationale a `single` or a `split` argued with.

They are written by [`late_session.py`](../../orchestrator/workflow/stages/decomposition/late_session.py) and are
deliberately NOT in `LATE_STATE_KEYS`: clearing late mode drops exactly the domain's group, and a locked backend
outlives that reset the same way `decomposer_agent` outlives a drift-driven session reset.

How much of a held PR's description may be preserved is decided by what the run still has to record beside it. The
write that starts the run has no safe failure — parking is another write of the same oversized comment — so before a
description is replaced, the whole prospective comment is rendered with the run's record already in it: the spec this
issue is locked to (an operator's command line, bounded by nothing here), the identities, and the bounded session id
a finished run pins. A description too long to hold with that beside it is refused while nothing has been touched.

`late_session_id` is dropped by a fresh spawn and KEPT by a resume. One late run in three is a resume: a human's
substantive answer to a categorized question continues the conversation that asked it, so the pinned id survives the
pre-spawn write and is passed to the CLI. Every other run drops it, so a backend that surfaces no id of its own
cannot leave the next tick resuming the run this one replaced. Which it is takes both halves — the caller says it is
carrying an answer, and the record says that session really ran against this cycle, generation, and commit, since a
session opened before a revision replaced the candidate holds a conversation about work nobody is adjudicating.

The identity fields are written before the agent starts, and that write deliberately carries the retry accounting
unchanged. `retry_count` and `retry_window_start` are incremented in memory to gate the spawn, but they become
durable only on a path that records what the run decided — so a run the tick then declines (an operator's `paused`
label, a shutdown sweep) costs the issue's daily budget nothing, exactly as a declined run in every other stage does.
The session id is pinned at the two exits that persist, a timeout and a completed reply, and at neither of the two
that do not.

The three identities beside the result are what makes a recorded verdict believable. A run's answer decides the
candidate it names — its own cycle, its own generation, AND its own source commit. The cycle is required because the
generation counter is not unique without one: a restart mints a fresh cycle and puts the counter back where it
started, and these run keys are outside `LATE_STATE_KEYS`, so they survive the clear that ends the old cycle. Without
it, generation 1 of a restarted cycle would read generation 1 of the cancelled one's verdict as its own. A result
taken against a commit that has since been replaced is not this candidate's either, and a fresh spawn drops the
previous result before it starts. Together they are what keeps a tick that crashed after a finished agent run from
paying for a second one — a second run is not free, and it is free to decide differently — and what keeps it from
acting on the wrong answer instead.

A result records the WHOLE of what its verdict decided, and is read back as an answer only while it does. A `single`
carries the explanation of what stopped a split, because that is the one thing somebody deciding what to do about an
oversized candidate cannot get from anywhere else once the run is over. A `question` carries the category it was
asked under and the sentence it asked, because announcing it is that outcome's own external effect. A `split` carries
the ordered child manifest, because the manifest *is* what a split decided — a marker without it would refuse to
re-run the adjudicator while the answer it stood for was gone. Beside a `single` or a `split` the record also keeps
the agent's rationale, the argument it gave for the verdict, on the looser terms described below, since nothing acts
on it. A recorded manifest is rewritten from the fields a child issue is created out of, so nothing an agent put
beside them travels into the comment humans read. The per-child addition budget is one of them: the child issue
created from a slice states the size that slice was proposed at, so a manifest recorded without the number would
leave a tick that crashed between the verdict and the transaction creating children that say nothing about their own
size — and the only way back to it would be a second adjudication, free to propose a different split entirely.

The budget is written only where the reply declared one, and read back the same way. A manifest on a live issue was
recorded before this domain kept budgets, and the rules a record is read through are the shared split rules, which
ask for none: requiring one there would read every such manifest as no split at all and send an adjudicated candidate
round again. Those children are created exactly as they always were, and their issues state no size, because nothing
here invents a number an agent did not give. A value that is not a whole count of at least one line is not one
either — a bool, a float, a numeric string, and zero are each a size nobody estimated — so a hand edit cannot put
prose where a child issue states a budget.

The explanation is the one of those a result may be missing and still be an answer, and the compatibility rule is the
same in both directions. `late_result_split_blocker` is written only where the reply gave one, so results recorded
before this key existed carry nothing under it, and no live issue is migrated to say so; a fresh reply that declares
the verdict without explaining it is refused where it is read, so it never becomes a record at all. Read back, that
absence answers with a fixed stand-in sentence rather than with an empty string, and the `single` stays actionable:
reading it as incomplete would send the adjudicator round again to recover prose, at the price of a second run free
to decide something else entirely. Nothing writes the stand-in into the comment, so a record that never had an
explanation stays distinguishable from one that does.

The rationale is looser still, because it decides nothing. `late_result_rationale` is written only beside a `single`
or a `split`, and only where the reply gave one: a `question` asks rather than argues, and a split refused at the
lineage bound is recorded as the question it became. It is optional, and it never stands in for the explanation: a
fresh `single` whose reply names no obstacle is refused whatever rationale it carries, and the late prompt tells the
agent both. It is bounded on its own. One longer than `MAX_RATIONALE` —
2,048 characters, counted on the value rather than on what JSON escaping makes of it — is stored as its prefix, a
space, and `[... rationale truncated by the orchestrator]`, with the marker inside the bound, so no recorded
rationale is longer than that and a reader shown one can tell a shortened argument from a whole one (both constants
live in [`late_result_models.py`](../../orchestrator/workflow/stages/decomposition/late_result_models.py), and the
prompt states the bound read off the same owner). It is the
only result field ever shortened, and it is cut before the record is measured. Read back, a missing, blank, or
non-string value, one longer than the bound, and one beside a `question` all read as no rationale while the verdict
stays actionable — re-adjudicating to recover an argument would buy a second run free to decide differently — and
nothing rewrites the comment or writes a stand-in into it, nor anything derived from the explanation or the category,
so an absent key stays distinguishable from a value nobody can use. It is written and dropped with the rest of the
result: a fresh spawn and every road that throws an answer away remove it, which is what binds it to the same cycle,
generation, and commit. A recovered outcome carries it back beside the verdict as the text the record kept
(`_recovered_adjudication`, in
[`late_run_reading.py`](../../orchestrator/workflow/stages/decomposition/late_run_reading.py)), so a process that died
past the result write — before the authorization or after it — settles with the same rationale and pays for no second
run.

It is issue prose, and the one place it reaches the thread is the notice an authorized publication posts
([`late_handback.py`](../../orchestrator/workflow/stages/decomposition/late_handback.py)). Beneath the sentence naming
the accepted commit, its measured additions and the recorded ceiling, the human operator's authorization, and the
exemption's scope, that notice quotes it under `Decomposer rationale:` off this record rather than off any reply — so
the authorization's own tick and a retry after a crash, onto either publication, show the same bounded text, a cut
one with its marker. The quote is fenced the way a park notice quotes an explanation, so a fence line or an
HTML-comment opener in it is shown rather than obeyed, and it is held inside one comment by the room a delivered quote
may take (`MAX_QUOTED_BLOCK`), which is far larger than the rationale's own bound. Wherever the reading above answers
none, the notice says `Decomposer rationale was not recorded.` — a sentence that exists only on the thread. Keeping
the rationale moves none of the contracts around it: a `single` still parks `late_single_decision` until a trusted
`/orchestrator authorize-oversized <commit>`, the settlement keeps its order and hands on the label the record names,
and the notice is posted where it always was, immediately before the write that retires the generation. It is
outside the closed late-event and analytics schemas: no late-split record on either sink has a field for it, and no
argument reaches one
([`../observability/event-streams.md`](../observability/event-streams.md#late-split-records-both-sinks)).

Half of an outcome is not one, in either direction. On the way in, what is measured is the whole comment the write
would produce — the preserved held-PR body and every other stage's keys included, since a result small on its own can
still be the one that pushes the comment past what GitHub accepts — and an outcome past that budget
(`MAX_RECORDED_BODY`: GitHub's limit, less headroom for the keys other stages still write) is refused *whole* rather
than shortened: a truncated question asks something nobody said, a truncated explanation gives a reason nobody wrote,
and a truncated manifest names children nobody proposed. The rationale has already been cut to its own bound by then,
so what is measured is the record exactly as it would be rendered — JSON and Unicode escapes and the escaped
HTML-comment terminator included — and a record that still does not fit is refused with its rationale, nothing of it
written. Every verdict is held to that one budget, and what a verdict goes on to OWE the thread is not taken out of
it. A `single` earns the park a human's decision to publish the
candidate unsplit is owed on; the refusal a smaller budget would produce is one the next attempt supersedes, so
charging it for its own sentence would buy another decomposer run against a candidate already adjudicated and leave
that `single` short of the park it earns. Its durable obligation is written into the headroom this budget leaves under
GitHub's limit afterwards (`MAX_NOTICE_BODY`, a fixed figure because that sentence NAMES the recorded explanation
rather than copying it), and what the sentence quotes is bounded by the delivery rather than by the record. The issue
parks instead of being left decided in a way no later tick
could see, and learning the same thing from a failed write would mean the agent had already been paid for. On the way
out, an incomplete record reads back unanswered: a `question` with no sentence or no category, and a `split` with no
manifest or one the split validator refuses, would each suppress the next spawn and then have nothing to announce or
create. Every field is read through the same defensive readers the domain's are, so a damaged `late_result_verdict`
reads back the same way — unanswered — because publishing on a verdict nobody recorded is not recoverable.

A park this mode leaves is attributed durably, because the next attempt has to tell its own park from another stage's.
Most of them are *superseded* by the attempt that follows: a hold that failed has been reconciled by the time the
retry gets there, a missing worktree is back, a run that timed out or answered unusably is about to be re-run, and
each of the three split-transaction steps — `late_snapshot_failed`, `late_children_failed`, and
`late_supersession_failed` — is about to be reconciled again from the same recorded verdict, at no agent's cost.
Those
are
retired — `awaiting_human` and `park_reason` cleared — the moment the hold reconciles, ahead of both the spawn and the
reuse of a recorded answer, because `awaiting_human` is exactly what suppresses the announcement a question verdict
earns. A stale one would silence a question durably recorded and never said out loud — whether this attempt produced it
or a crashed run recorded one whose comment never reached the issue. Eight are not retired, because none of them is a
step that failed. `late_question` is the announcement itself, and the issue really is waiting on the human it names;
`late_content_drift`, `late_revision_dirty`, `late_revision_unmeasured`, and `late_revision_unanswered` are the
workflow waiting to be told what an edited scope, a worktree the developer left changed, a candidate nobody could
measure, or a developer that changed nothing and vouched for nothing now means. Retiring one of
those would drop the very state the next tick reads to tell a human's answer from the silence before it.
`late_single_decision` is the sixth, and the attempt that would supersede it does not exist: the verdict is
recorded, so every later tick reuses the same answer and reaches the same park at no agent's cost. Retiring it would
clear the flag and re-take it one step later, saying the same sentence to the same thread once a poll while the human
it is addressed to reads it. What clears it is that human answering — guidance, which resumes the developer, or the
trusted `/orchestrator authorize-oversized <commit>` that publishes the candidate as it stands, whose record is the
`late_override_*` group below. One refusal clears it too, and has to: an authorization arriving over an adjudication
the record can no longer show is answered and the park retired together, since what the issue stops for next is
whatever the replacement run decides — a flag left standing over that run would suppress the announcement its
`late_question` earns and would have a `split` create children under a claim that the issue is waiting.
The shared `retry_cap` is the seventh and the plainest: a retry is exactly what it refuses, so an attempt that
superseded it would clear the flag and meet the same spent budget one step later — saying the same sentence once a
poll and taking down, in between, the park a human has to answer. It is held at the top of the adjudication instead,
behind only the reconciliations an earlier tick left owed and the live-generation gate, and while it stands the tick
ends there having proved no evidence, re-marked no pull request, read no thread as an answer, spawned nothing, and
written nothing. What lifts it is a trusted `/orchestrator continue` and nothing else — not an edited body, not the
clock reaching the end of the window, not an untrusted account's copy of the command, and not a `paused` tick, which
never reaches a handler at all.
`late_owner_unreadable` is the eighth and is left out for a different reason again: it IS answered by a retry, but by
the pending-check reconciliation that runs ahead of all of this, and that step reads the standing reason to decide
whether it owes the thread a follow-up — so retiring it here would erase the only durable evidence that this mode had
said anything to retire — and what each of those answers earns is in
[`../workflow/roles.md`](../workflow/roles.md#what-the-humans-can-still-change-while-a-candidate-is-frozen). The same
attribution is what keeps a park idempotent: reconciliation is retried on every eligible tick, so a park already
standing for the reason being taken again — including one this tick retired and is re-taking unchanged — is written
but not announced a second time. What is suppressed is the notice, not the park. "Unchanged" is the whole claim, so
the two things that could change it end the suppression: an agent RUN, after which a second categorized question or a
second unusable reply says something the first notice did not, and a human's ANSWER, after which whatever parks next
is news even under the same reason. Only the reconciliation retries that spawn nothing and find the same wall stay
quiet — suppressing the others would leave an outcome recorded, durable, and never said out loud. A retirement is a
state change like any other, so the one branch that would otherwise return without writing — the reuse of a recorded
answer that owes no announcement — persists it rather than clearing a park only in memory.

A revised candidate nobody could measure is this mode's own reading, and it parks on the FIRST miss whatever step it
stopped at. `late_revision_unmeasured` is the reason, neither guard reads the other's — the size gate's silence is
scoped to a standing `late_measurement_failed`, and this mode's to its own list — so the bounded quiet retry the two
transport steps earn at the gate buys nothing here: a remote that would not answer for the base asks a human on the
tick it happens, and `late_measurement_miss_count` and `late_measurement_failure` above go on describing the gate's
own readings, so a miss taken once the issue is back there starts a bound of its own. What the two reading roads do
share is the record: the same `late_failure` carrying `measurement_failed`, with the same `measurement_failure` step
and `detail` line beside it, under `stage: decomposing` because that is where a re-measurement is taken
([`../observability/event-streams.md`](../observability/event-streams.md#late-split-records-both-sinks)). And what
each suppression is keyed on follows what re-takes the park: here a reconciliation that spawned nothing and met the
same wall, which is the same sentence under the same REASON, and at the gate the pair the post-publication
reconciliation re-reads once a poll, which is the same sentence only while those readings go on stopping at the same
STEP.

The record goes out before the effect it earns, and the owner read goes out between them. A question is written and
persisted BEFORE the comment announcing it, so a crash between them costs one repeated comment — the window every
park in this repository has — and never a second run of an agent that already answered; and the announcement itself
is made past the guard, so a question is not posted to a thread somebody closed while the agent was answering it. The
next tick reconciles the announcement from `awaiting_human`: a recorded question the issue is not yet waiting on a
human for is posted from the question the record kept, rather than re-earned.
