# Architecture

Single-process **polling orchestrator** that drives GitHub issues through a label-based state machine, delegating coding
work to a configurable coding-agent CLI (`codex`, `claude`, or `agy`) running as a subprocess in isolated git worktrees.

State lives in GitHub: a workflow label exposes the current stage and a pinned JSON comment holds per-issue durable
state. The orchestrator process is stateless and can restart at any time.

This page is the system overview: the design constraints, the top-level module map, the process model, the agent
subprocess and the environment boundary around it, the hardened git and push path, and the schema diagram. Every
other area keeps its heading here as a summary that names the page owning it, so a link written against this file
still lands beside the material it pointed at. The per-package inventory under the map is in
[`architecture/platform-modules.md`](architecture/platform-modules.md),
[`architecture/workflow-modules.md`](architecture/workflow-modules.md), and
[`architecture/observability-modules.md`](architecture/observability-modules.md); the label set, per-stage internals,
what one tick reads and writes per issue, and the pinned-state schema in [`state-machine.md`](state-machine.md) and
the pages under it; agent roles, conversation contracts, and command-spec semantics in [`workflow.md`](workflow.md)
and the pages under it; and the observation-only sinks and the two pages over them in
[`observability.md`](observability.md).

## Design constraints

GitHub Issues are the orchestrator's task tracker and durable state surface. The process intentionally avoids an
internal database: workflow labels expose the current stage, and the pinned JSON comment holds the per-issue state that
the next tick needs. This keeps progress visible to humans on github.com and lets the process restart without
reconstructing hidden local state.

The orchestrator is not fully autonomous. When a stage hits uncertainty, an unsafe repository state, a malformed agent
response, or an exhausted retry cap, it parks with `awaiting_human` and mentions `HITL_HANDLE`; a later human issue
comment is the resume signal for the parked agent session. The exhausted retry cap is the one park an ordinary
comment does not answer under `workflow:decomposing` or `workflow:implementing`: what stopped the issue there is a
spent spawn budget rather than a question, so the tick holds everything it carries until a trusted
`/orchestrator continue` renews the budget for one more attempt. A spent lifetime agent-run ledger
(`MAX_AGENT_RUNS_PER_ISSUE`) parks the same way and answers to one thing only: the dispatcher holds such an issue
off every stage handler until a trusted, bounded `/orchestrator add-agent-runs N` widens the ceiling it is held to.
No window reopens a lifetime, and nothing returns a run it has already spent.

The workflow is deliberately fixed instead of planner-selected: decomposition, implementation, validation, and
acceptance are mandatory phases. Routing is explicit and label-driven.

Agents run on the host as CLI subprocesses with broad local permissions
(`codex --dangerously-bypass-approvals-and-sandbox`, `claude` / `agy --dangerously-skip-permissions`).
The host, container, or VM around the orchestrator is therefore the real sandbox boundary;
token handling and hardened git operations are
designed around that assumption.

## Top-level layout

A responsibility answers on the owner module that defines it and nowhere else — the workflow package, the whole
analytics tree, and both Streamlit pages included — so a patch targets that module and there is no second site a mock
could be left on. Where a leaf does resolve a name at call time it is to read a knob rather than to borrow a helper,
off the one holder every owner that reads it resolves through. Each of those boundaries is named where its owner is
described, on the pages named below.

A bare tag — `implementing`, `fixing`, `validating` — names the *stage*: the handler and the subpackage holding it,
mapped in [`architecture/workflow-modules.md`](architecture/workflow-modules.md). For a stage the orchestrator labels
itself, the GitHub label an issue carries is a different string, spelled `workflow:<tag>` here and everywhere else in
these docs. `in_review`, `question`, `discussion`, and
the `done` / `rejected` terminals were never namespaced, so for those the two coincide; see
[Workflow labels](#workflow-labels).

The map is split by area, and each page below is where the owners of the packages it names are described:

- [`architecture/platform-modules.md`](architecture/platform-modules.md) — the package root and both launch forms,
  `runtime/`, `config/`, `github/`, `agents/`, `scheduler/`, `git/`, and `skills/`.
- [`architecture/workflow-modules.md`](architecture/workflow-modules.md) — `workflow/`: the state and transition
  owners, the `engine/` owners one tick is composed of, the `late_split/` domain the late size gate is
  defined by, and the nine stage subpackages the label dispatch routes into.
- [`architecture/observability-modules.md`](architecture/observability-modules.md) — `observability/`: the analytics
  sink and everything downstream of it, the usage parser, the Streamlit analytics page, and the file-backed
  trajectory viewer, together with the two `streamlit run` targets under `apps/` that compose the pages.

The rules under the map hold for the whole tree, the packages on those pages included.

```
orchestrator/
  __init__.py           the distribution version, published as `__version__`, without loading runtime owners
  cli.py                `chipping-orchestrator` console-script entry point and
                        the polling process's composition point
  __main__.py           `python -m orchestrator` launch form over `cli.main`;
                        the target `run.sh` launches
  runtime/              the polling process's own owners: the state one run
                        carries, the log destinations, startup, one pass over
                        the configured repos, the polling loop, when the
                        finished issues' artifacts may be reclaimed, which
                        process on the host may reclaim them and the one
                        bounded record each candidate is reported as, the
                        self-restart probes, and shutdown
  config/               the bottom layer: the non-secret `.env` loader, the
                        env parsers and resolver behind the settings surface,
                        credential resolution and secret redaction, and the
                        repository-config types
  github/               the composed `GitHubClient` and the pinned durable-
                        state model over one owner per GitHub surface: issue
                        operations and the one walk over them a tick is served
                        from, labels, comments, pull requests, reviews,
                        checks, audit events, and which repository the client
                        speaks for
  agents/               the agent-CLI subprocess layer: shared dispatch and its
                        result models, credential filtering, the
                        backend-agnostic session-id walk and the Claude
                        final-message parsing beside it, the transient-provider
                        verdict read off that output, the process registry and
                        the group operations every teardown spends, and one
                        module per backend
  scheduler/            the `IssueScheduler` every tick shares and the typed
                        submissions it takes
  workflow/             the state machine: the label vocabularies and the
                        transition guard, the `engine/` owners one tick is
                        composed of, the `late_split/` domain a late generation
                        is recorded and reported by, and nine stage subpackages
                        holding the twelve labelled handlers the dispatch
                        routes into
  git/                  local git: execution, locks, and authenticated
                        transport, under the worktree lifecycle, the read-only
                        inventory of the checkouts and branches it leaves --
                        both layouts of each, widened by what the remote still
                        carries, so an issue this host holds nothing for is
                        still found -- the classification that says which of
                        them a finished issue may have reclaimed and the
                        bounded pass that spends one, re-reading every proven
                        tip immediately before the mutation it gates and
                        leaving whatever it did not reach for the next
                        discovery to find, the per-tick base sync, branch
                        publication, verify runs, the added-line measurement
                        of a committed candidate and the digest naming which
                        contribution it carries, and the immutable ref namespace
                        one is preserved under when a split supersedes it
  observability/        the four surfaces that watch a run without steering
                        it: the analytics sink and everything downstream of
                        it, the parser that meters one finished agent run, the
                        Streamlit page over the operator's Postgres target,
                        and the file-backed trajectory viewer beside it
  apps/                 the two Streamlit pages a `streamlit run` names; the
                        polling loop is launched at cli.py instead
  skills/               the two skill-enumeration owners: the per-tick repo
                        catalog and the per-run local discovery it reads its
                        marker back off
```

Five rules hold for the tree as a whole, each with a check under `tests/repository/` that finds its subjects on disk so
a module added anywhere is covered the day it lands. The root is the four files above plus the ten packages under
them, held to that exact inventory: a module parked beside them would be importable next to the package that owns the
responsibility, and both would answer. No module wears one of the retired domain families as a prefix. Every family is
forbidden in the private spelling its compatibility leaves carried (`_dashboard_read_core.py`), and the families whose
word names a domain package and nothing else — `dashboard_`, `workflow_`, `git_`, `state_machine` — in the public
spelling as well, so `workflow_state.py` fails one level down exactly as it would at the root. A word that also names a
responsibility *inside* a package keeps its public spelling: `charts/usage_axis.py` and `usage/trajectory_models.py`
are owners under the family's own package rather than that family flattened out of it. Nothing is named for an
inventory of names either — `exports.py`, `manifest.py`, `compatibility.py`, whole or as the tail of a prefixed one,
the decomposer's output manifest excepted — and nothing carries a `.pyi` stub or a module-level `__getattr__` /
`__dir__`: a re-export is the owner's own object bound at import, so a lookup lands on the module that defines the name
rather than on something answering for it.

Imports run one way through four layers — `config/` at the bottom, the domains that do the work above it, `workflow/`
deciding with them, and `cli.py` / `__main__.py` / `runtime/` / `apps/` composing the lot. The direction is read
twice, because deferring an import weakens where it lands but not whether it belongs. At module scope, where an import
decides what a package costs to load and whether it can be loaded at all, only `github/` and `git/` may reach the
workflow vocabulary: `state.py`, `label_reading.py`, `transitions.py`, and `transition_guard.py`, each named exactly.
Over every scope, the only other reaches
left are declared one by one in `tests/repository/test_layering.py`: three base-sync owners posting a notice or a park
through the workflow's comment and guard owners, deferred to a call because at module scope they would be a cycle. An
undeclared hop fails wherever it is written, and a declared one fails if it is bound at module scope after all. The
launch forms compose each other and are reached from nothing below them at any scope, and no import anywhere is
relative, because a relative target names its module by position and no layer can be read off it. Most package
initializers are markers that import and bind nothing. The declared public packages retain their explicit
`__all__` surfaces, including the root's version, reloadable `config` bindings, and the lazy `workflow.tick`
entry point. Other operations are imported from their defining modules. The source and namespace checks distinguish
these deliberate publishers from marker packages; the policy is described under
[`configuration/operations.md#continuous-integration`](configuration/operations.md#continuous-integration).


The test tree mirrors this one, and two more checks hold it there: every package above has a mirrored tests package,
and every directory the suite collects from carries an initializer of its own, with nothing at the tests root but the
suite-wide fixtures. The mirror is why the same short module name recurs once per domain — one `test_imports.py` per
package — and those initializers are what keep the recurrences distinct at collection.

## Workflow labels

An issue should have at most one workflow label at a time; where a pre-namespace spelling survives beside the
namespaced one, the namespaced label is the state and the bare one is outranked rather than counting as a second. The
names are part of the public contract because live GitHub issues already carry them. The `workflow:` prefix marks the
states the orchestrator writes itself, so a repository's own vocabulary cannot collide with them; the five a human
also applies or reads — `in_review`, `question`, `discussion`, and the `done` / `rejected` terminals — keep the bare
spelling, as do the `backlog` and `paused` control labels an operator types. Membership in `WorkflowLabel` /
`ControlLabel` is what closes both sets rather than the prefix, so a `workflow:`-prefixed name outside them —
Dependabot's service labels on its own update PRs — is not a state, routes nowhere, and survives a label write
untouched.

The namespace is a GitHub label spelling and stops at that boundary, which is the distinction the stage map in
[`architecture/workflow-modules.md`](architecture/workflow-modules.md) reads by: a bare tag there names the *stage* —
the handler, the subpackage under `orchestrator/workflow/stages/` holding it, and the identifier analytics rows,
audit event payloads, and agent-session attribution have always carried — while the wire label an issue carries is
spelled `workflow:<tag>`. `workflow/state.py` defines `stage_name`, which strips the prefix for those sinks;
`workflow/label_reading.py` defines `label_for_name`, which resolves either spelling back to its member.

The whole set, what each state means, and the control-label semantics are in
[`state-machine/labels-and-state.md#workflow-labels`](state-machine/labels-and-state.md#workflow-labels). The startup
bootstrap that migrates a repository off the pre-namespace spellings, and the three reads that still take a bare
label wherever that rename could not run, are in
[`state-machine/labels-and-state.md`](state-machine/labels-and-state.md#legacy-labels-and-the-migration-off-them).

## Process model

There is **only one long-lived process**: `python -m orchestrator`. It is wrapped by `run.sh` so the loop can
self-exit and be restarted with new code.

- **Trigger**: started manually (or by a wrapper). Optional `--once` for a single tick, or
  `--cleanup-terminal-artifacts` for a maintenance-only run: it connects read-only clients (no label bootstrap)
  *before* claiming the host, since a client that lands in a rate-limit backoff sleeps for as long as the reset takes
  and nothing unbounded may sit inside the claim, then reclaims the artifacts of finished issues and exits without
  polling. It writes no *workflow* state — no label, no
  pinned state, no comment — and does delete the orchestrator-owned branches it proved reclaimable, in the clone and
  on the remote, which is what it is for. The form a nightly service timer runs.
- **Host exclusivity** (`runtime.exclusion`): one `flock`-based claim on `WORKTREES_DIR/.artifact-maintenance.lock`
  decides which process may touch this host's artifacts. Every polling run holds it **shared** for its whole life (a
  presence: "a process that may be running work is live here"), and **every** maintenance pass holds it
  **exclusively** for as long as it acts — the one-shot mode takes it once it has connected and before it reads
  anything, and a polling run's own recurring pass hands its presence over, takes the host, and takes the presence
  back afterwards. So no pass
  anywhere reclaims an artifact while any process could be submitting work, including a second daemon on the same
  host. This is the one thing the in-process barrier below cannot answer: another process's workers are in its own
  scheduler and its claims in its own sets, so that run's barrier would grant the quiet of an empty process and its
  claim guard would report nothing running however busy the other one is.
- **The order between them** (`runtime.artifacts`): the barrier is taken **outside** the handover. A presence says
  work may be running in the process holding it, so a polling run may only give one up once its own admission is
  closed and its own workers have drained — dropping it first would publish the host with a worker mid-agent-run,
  and whatever took it then would sweep on the strength of its own empty scheduler. The presence also has to be back
  *before* admission reopens, or this run resumes submitting while another process is still free to take the host.
  Inside the barrier the window between the two locks is safe in both directions, because there is nothing of this
  run's left to race.
- **Which side waits**: a pass never waits. Refused the host it defers whole, which costs a finished issue's disk
  until the next scheduled attempt: the next interval with no window set, no sooner than 15 elapsed minutes later
  inside a window that is still open, or whenever a one-shot run is next asked for. A poller always waits, with no
  deadline: it may not start submitting while another process is
  deleting, and no length of wait makes doing so safe (giving up and polling would put a tick's fresh checkouts in a
  directory being torn down; giving up and refusing to poll would be a crash loop under `Restart=always`). Only a
  lock somebody *holds* is waited for: a lock that does not work at all — a filesystem without `flock`, a full lock
  table — is not contention and is answered at once, leaving a poller polling with no claim and a pass declining to
  act, both of them said out loud. What
  keeps that wait finite is the other side rather than a timeout — a pass stops spending candidates once it has
  held the host for 120s and gives it back at the next candidate boundary, so the hold is that budget (which the
  one host scan in front of the candidates spends too) plus the candidate in hand. The barrier's own ≤30s wait is
  outside the hold entirely: a run that cannot go quiet never takes the host at all. A pass whose process dies
  holds nothing, since the kernel drops the lock with the file description.
- **Tick cadence**: every `POLL_INTERVAL` seconds (default 60).
- **Artifact maintenance cadence** (`runtime.artifacts`, scheduled by `runtime.artifact_schedule`): at the end of the
  wait between two polling passes — never inside a tick, since a tick is what makes the host busy — and at most
  once every `TERMINAL_ARTIFACT_CLEANUP_INTERVAL_SECONDS` (default 86400), or once per local
  `TERMINAL_ARTIFACT_CLEANUP_WINDOW` where one is set, the worktrees and branches of finished
  issues are reclaimed under a scheduler maintenance barrier: admission is closed for counted workers and tracked
  claims alike, the work already admitted is waited out within a finite bound, and only a host that went quiet is
  acted on. A bound that expires, a shutdown that started, or a barrier that could not be taken defers the whole
  pass without touching an artifact; admission always reopens, since the hold is given back around the body whatever
  the body did. A granted hold is a snapshot, so it is not the last word either: whether the process may still act
  is re-read **twice per candidate** — before the candidate is looked at, and again as the last thing before its
  first mutation — from the run's own stop flag, from the scheduler that granted the hold, and from the pass's own
  host-hold budget. The second reading is what closes the window the first leaves open: everything expensive (the
  issue, its pull requests, the remote reads every deletion is pinned to) happens in between, so a signal that lands
  there ends the pass instead of being answered by a teardown. Past that reading one candidate is taken as a unit —
  its checkouts, then each of its branches on the remote and in the clone, every step pinned to the commit that was
  proved and idempotent — because a candidate half taken is the one state this vocabulary cannot report. The due
  gate lives in this process's memory, so nothing is persisted and a restart costs at most one extra pass — the pass
  reads the host again and reports whatever is already gone as done. The interval runs on the monotonic clock and
  spends its turn when it hands it out. A window is read off the wall clock and named by the local date it opened
  on, so neither midnight nor a repeated daylight-saving hour owes a second pass; the pass asks the gate again once
  it holds both the barrier and the host, and spends the window there, immediately before discovery. A window that
  closed during that wait starts nothing, only a deferral before that point is retried — no sooner than 15 elapsed
  minutes later — and nothing is caught up outside the window.
  What it did is reported per candidate and nowhere else: one line on the `orchestrator.worktree_lifecycle` log, and
  one bounded [`terminal_artifact_cleanup`](observability/event-streams.md#terminal_artifact_cleanup-records)
  analytics record (`runtime.artifact_records`) — never a label, a pinned state, or a comment. The operator runbook
  over both is
  [`configuration/operations.md#reclaiming-a-finished-issues-artifacts`](configuration/operations.md#reclaiming-a-finished-issues-artifacts).
- **Self-restart guard** (`runtime.self_update.self_modifying_merge_happened`): each tick fetches
  `origin/<ORCHESTRATOR_BASE_BRANCH>` (default `main`); if it advanced past the process's startup SHA *and* the new
  commits touch `orchestrator/`, the loop
  exits 0 so the wrapper can re-exec the new code. The branch is decoupled from `BASE_BRANCH` so a target repo with a
  different default branch does not interfere with self-update detection.
- **Self-update resilience** (`run.sh self_update`): before each launch — at startup and after every
  self-modifying-merge restart — the wrapper fast-forwards the orchestrator checkout to
  `origin/<ORCHESTRATOR_BASE_BRANCH>`. It skips the pull and warns to stderr if a non-base branch is checked out, and
  warns and continues (rather than exiting) if the fast-forward fails (diverged base branch, rebase in progress, network
  error); either way it launches the existing working tree. A clean fast-forward still updates the tree before launch,
  so the self-modifying-merge flow keeps picking up new code. This is deliberate: under the production systemd unit
  (`Restart=always`) exiting on a self-update failure silently crash-loops the service with the orchestrator never
  running, so a stale-but-running process plus a journal warning is preferred — the warning is the operator's signal
  to restore the checkout.
- **Signals**: SIGINT/SIGTERM set a flag and call `scheduler.shutdown(wait=False)` synchronously so the submit path is
  closed mid-tick; the loop then stops at the next tick boundary and drains. The drain terminates in-flight agent and
  verify subprocess groups up front (`agents.processes.terminate_all_running`) so a worker parked in a long agent /
  verify run
  unwinds in seconds instead of holding the process for up to `AGENT_TIMEOUT`. A daemon watchdog backstops the drain: if
  it overruns, the watchdog terminates those same groups and hard-exits (`os._exit(128+signum)`) so total signal→exit
  stays within `SHUTDOWN_GRACE_SECONDS` no matter what a thread is blocked on. A second Ctrl+C hits the re-armed kernel
  default handler and kills immediately.

The coding agent runs as a **transient child subprocess**, not a daemon — spawned per tick when work is needed.

<a id="per-tick-flow-workflowtick"></a>

## Per-tick flow (`workflow.engine.tick.tick`)

Each tick the polling loop fans `workflow.engine.tick.tick(gh, spec, scheduler=...)` out across
**every configured repo** via
`runtime.ticks.run_tick`: single-repo deployments stay in-thread, multi-repo deployments use a `ThreadPoolExecutor`
sized to the repo count. A single long-lived `IssueScheduler` (global cap `MAX_PARALLEL_ISSUES_GLOBAL`, per-repo cap
`MAX_PARALLEL_ISSUES_PER_REPO`) is shared across all `tick` calls, so those caps bound the whole deployment rather
than one repo's thread.

One repo's pass is owned by `workflow/engine/tick.py` — the base refresh, the community-contribution PR sweep
(`workflow/engine/community.py`), the skill-catalog emission, and then either the scheduler handoff or the in-tick
execution, in that order. That last step is the sequential loop on `tick.py` itself at `parallel_limit=1`, and the
bounded thread pool on `workflow/engine/parallel.py` beside it at any higher limit. The refresh runs first because
every step after it reads what that fetch left behind, and the sweep and the catalog emission both precede the
scheduler / in-tick split so each fires exactly once per tick on either path.
The dispatch behind that split first drops each open `workflow:blocked` / `workflow:umbrella` issue on the ticks
`DEPENDENCY_POLL_EVERY_N_TICKS` skips — a classification filter taken before any partition, so a skipped dependency
walk is neither submitted nor handed a worker client — and then folds every remaining family-aware issue
(`workflow:decomposing` / `workflow:blocked` / `workflow:umbrella` / unlabeled — the labels that write cross-issue
parent ↔ child state) into ONE bucket submit per repo that drains sequentially on a single worker, so a stale child
cannot starve the parent umbrella issue, and submits everything else one callable per issue.

Per-issue durable state lives in a single **pinned comment** on the issue (`<!--orchestrator-state {...json...}-->`).
The orchestrator process is stateless; the label and the pinned JSON are the entire dispatch input.

For the full per-tick sequence — eligible-issue enumeration, the cap exemption a no-agent bucket earns, what the base
refresh rebases and pushes, the read-only skip the `question` and `discussion` labels take, the per-tick
external-merge sweeps, and the complete pinned-state JSON schema — see
[`state-machine/labels-and-state.md#per-tick-flow-workflowengineticktick`](state-machine/labels-and-state.md#per-tick-flow-workflowengineticktick).

## Stage handlers

Twelve workflow labels dispatch to a `_handle_<label>` function under `orchestrator/workflow/stages/`, spread over
nine stage subpackages: `decomposition/` answers for `workflow:decomposing`, `workflow:ready`, `workflow:blocked`,
and `workflow:umbrella`, while `implementing`, `documenting`, `validating`, `in_review`, `fixing`, `conflicts`,
`question`, and `discussion` answer for one label each. The thirteenth dispatch target is the unlabeled entry, which
`workflow/engine/pickup.py` answers rather than a stage package; the `done` / `rejected` terminals are no-ops the
dispatch leaves alone. Each subpackage is a set of responsibility-named owners with nothing flat beside them,
and the dispatcher reaches a handler by importing the module its label is paired with in `_STAGE_HANDLER_TARGETS` and
reading the handler off it — as `pickup.py` does for the stage it starts an issue on — so a patch that has to
intercept a dispatched handler targets that module. A stage-to-stage call is named the same way: the decomposition
disabled-rollout and `ready` paths name `stages/implementing/handler.py` for `_handle_implementing`.

Two things sit ahead of that table, and both can end a tick before any handler runs. One is the only route where the
label does **not** choose the handler: a CLOSED issue on `workflow:decomposing`, `workflow:umbrella`,
`workflow:ready`, or `workflow:blocked` goes to the cleanup sweep (`stages/decomposition/late_sweep.py`) instead of
the stage its label names, because that stage would spawn the decomposer, activate children, or hand the issue to a
developer on an issue a human ended — so the close is read first, and on the sequential path an owner on either of
the two labels an adjudication RUNS under is refetched so neither reading of it is taken from the poll. The other
two are asked about only while closed, so an open `workflow:ready` issue costs nothing it did not already. It is
also the one route the `backlog` / `paused` hard skip steps aside for: discarding a closed owner there discards the
close itself, so the route is taken and the control label defers only the external work behind it. The other is one
read of the issue's own pinned comment, which answers eight questions that stop a dispatch outright: a live late
adjudication the label was moved out from under, a child of a split whose snapshot has since been reclaimed, an
owner whose cancelled cycle has not reached its ending — which settles the cycle and writes its `rejected`
terminal from wherever the owner has been left, so a reopen can neither resume the cycle nor slip past the ending
it owes — the restart an operator authorizes by taking that `rejected` back off, asked one step ahead of that one,
which projects a fresh cycle onto the same pinned comment and puts the issue back on the label `DECOMPOSE` chooses,
an issue standing on `agent_run_limit` because it has spent every agent run its lifetime ceiling allows — held
behind that pair and ahead of everything else, since each stage below reads `awaiting_human` as the park it was
written against and none of those buys back a run, lifted only by the bounded operator command the same hold reads
off the thread, and stepping aside for work that has ENDED — a closed issue, and a recorded pull request that has
merged or been closed, which the issue's own flag cannot show — so a terminal arc can still finish
([`state-machine/delivery-stages.md`](state-machine/delivery-stages.md#the-agent-run-limit-hold-every-dispatch-ahead-of-every-handler))
— an auto-rebase anchor no recovery has ended, since the base refresh answers one ahead of every handler only on a
tick that reaches it: the handler is held while the anchor stands, under a stage's own park and on the live
adjudication's road too, and asked again once the late reconciliation has run; a label the refresh does not drive is
answered on its ineligible road by the dispatcher itself, and a missing checkout on one it drives is restored for the
refresh to walk
([`state-machine/labels-and-state.md`][pinned-state])
— a developer report the issue recorded and never finished publishing, which is answered last of the
reconciliations and ahead of the reuse guard below: the record is durable and the publication that follows it is
not, so a tick that died in between leaves a pull request without the report the next reviewer is meant to read,
and no stage would go back for it. It proves the world the record froze, publishes or re-reads the report, and
settles the whole obligation in one write; short of that it holds a read nobody could take, stands down on
anything a route behind it would fix, retires a transaction whose pull request is over, and parks once on a record
it may not act on
([`state-machine/delivery-stages.md`](state-machine/delivery-stages.md#the-developer-report-transaction-every-dispatch))
— and, last, an unlabeled issue that already carries a pinned comment, which is one this orchestrator has met
before: the pickup handler behind it *greets* an issue and mints its pinned comment, so a second greeting writes a
second comment that every later read shadows
([`state-machine/delivery-stages.md`](state-machine/delivery-stages.md#the-reuse-guard-every-dispatch-ahead-of-every-handler)).

Most stage handlers run the user-content drift hook (`_compute_user_content_hash` → `_detect_user_content_change`) so
an out-of-band human edit re-routes the issue back to `workflow:decomposing` (when no dev session exists yet), resumes
the locked dev session with the updated body (implementing, validating, in_review, resolving_conflict), or unwinds
back to `workflow:validating` without resuming dev (documenting). Both halves of that hook sit on the
`workflow/engine/drift.py` owner the stage leaves import directly, so a patch aimed at the hook targets that owner.
`_handle_fixing`, `_handle_question`, and `_handle_discussion` skip the drift hook.

Which owner holds each decision inside a stage, which helpers it borrows from a sibling stage or from `git/`, and the
checks that keep a stage answering on one module are in
[`architecture/workflow-modules.md`](architecture/workflow-modules.md). For per-stage internal flow — pickup, drift
handling, decomposing, ready, blocked, umbrella, implementing, documenting, validating, in_review, fixing, and
resolving_conflict — see [`state-machine/delivery-stages.md`](state-machine/delivery-stages.md), with the two
operator-applied conversation stages in
[`state-machine/conversation-stages.md`](state-machine/conversation-stages.md) and the drift hook's filters and
per-handler routing in
[`state-machine/delivery-stages.md#user-content-drift-detection`](state-machine/delivery-stages.md#user-content-drift-detection).

<a id="agent-subprocess-agentsrun_agent"></a>

## Agent subprocess (`agents.runner.run_agent`)

`run_agent(backend, prompt, cwd, ...)` dispatches to the per-backend runner (`codex.run_codex` /
`claude.run_claude` / `agy.run_agy`); `backend` is one of `"codex"` / `"claude"` / `"agy"` and is re-validated
at call time so misuse fails loudly. All runners return a unified
`AgentResult(session_id, last_message, exit_code, timed_out, stdout, stderr,`
`interrupted, usage, invoked, unfinished_steps)`.
`interrupted`
(default `False`) flags a run the runner observed exiting on SIGTERM/SIGKILL, in either form: the negative
returncode `Popen` reports when the child itself dies from the signal (`-15` / `-9`), or the shell-convention
128+N exit (`143` / `137`) of a CLI that traps the signal or a wrapper reporting a signal-killed child. Either is
the shape the orchestrator's shutdown sweep (`terminate_all_running`) produces when it kills an in-flight agent
group; `exit_code` preserves signal exits, and `interrupted` is distinct
from `timed_out` (the orchestrator's own `AGENT_TIMEOUT` firing). `invoked` (default `True`) says whether a process
existed at all: every result any backend produced carries `True`, including the killed and timed-out ones, while a
launch the agent-run circuit turned away before the spawn carries `False` — and so does a result an implementing
recovery SYNTHESIZES to publish committed work an earlier run left (the restart shortcut, the timeout recovery, the
approved and frozen candidate recoveries). The two are not the same question, and the stages that read a worktree
*before* they ask about interruption need both — see
[The agent-run circuit](state-machine/labels-and-state.md#the-agent-run-circuit). A third reader is the
developer-report contract on `workflow/engine/report_delivery.py`: a result no process produced has nobody to hold
to it — a sentence the orchestrator wrote for itself is not a run declining to report — so it records no report and
is held against none. `usage` (default `None`) is the parsed
`UsageMetrics` -- the one on `observability/usage/metrics.py` -- that `recording.record_agent_exit` attaches during a
tracked run so callers can read token / cost metrics off the result without re-parsing stdout; it stays `None` for a
result that never flowed through
`_run_agent_tracked` or whose usage parse failed (fail-open). What the spawning handlers do with it — the per-issue
counters `_accumulate_issue_usage` folds each run into, and the one visible receipt comment
`_format_issue_usage_verdict` reads them back out of at a terminal — is in
[`state-machine/labels-and-state.md#pinned-state`][pinned-state] and
[`observability/usage.md`](observability/usage.md); nothing gates on the figure. `unfinished_steps` (default `()`)
carries structured diagnostics (`ToolLifecycle`) for any tool steps left unfinished when a backend emits terminal
output (such as Antigravity active commands); when present, the terminal response is suppressed from `last_message`
and the result is forced non-zero so recovery can act on it. `CodexResult` is kept as a transitional alias.

Being the only call that starts an agent process is also what makes `_run_agent_tracked` the place the lifetime
agent-run ledger is charged. `workflow/engine/run_circuit.py` is asked immediately around it: two durable writes
(`reserved`, then `started`) land before a process exists, so a run that crashed, timed out, or was killed
mid-flight is still spent and a tick that died between the two is recognized rather than charged twice. A launch it
refuses — an unreadable pinned comment, a write that failed, or an allowance with nothing left — invokes nothing and
returns an `interrupted` result, which is the answer spawning handlers already return without writing durable state
for. Each durable step of that charge, the park a spent lifetime takes, and the operator command that widens one are
recorded to both observability sinks by `workflow/engine/run_budget.py` as one `agent_run_budget` family, always
after the write that makes the step durable
([`observability/event-streams.md`](observability/event-streams.md#agent-run-budget-records-both-sinks)). That "only
call" is held rather than assumed:
[`../tests/repository/test_agent_spawn_boundary.py`](../tests/repository/test_agent_spawn_boundary.py) reads the
production tree and fails on any second module that so much as names `run_agent`, on anything but `runner.py` naming
a backend entry, and on anything but the three backends naming `run_subprocess`. Details in
[`state-machine/labels-and-state.md`](state-machine/labels-and-state.md#the-agent-run-circuit).

The role command specs (`DEV_AGENT` / `REVIEW_AGENT` / `DECOMPOSE_AGENT`), their parsing, the durable per-session
lock, and the resume mechanic are documented in
[`workflow/command-specs.md`](workflow/command-specs.md). Which stage spawns which role is in
[`workflow/roles.md`](workflow/roles.md). What follows is the subprocess shape only.

- **Codex command**:
  `codex exec [-C cwd | resume <sid>] --dangerously-bypass-approvals-and-sandbox --json -o <tempfile> <prompt>`. The
  `-o` path is a per-spawn `tempfile.mkstemp` outside the worktree (so target repos without `.codex-*` in `.gitignore`
  don't see it as untracked); `last_message` is read from it and the tempfile is cleaned up on any exit path by a
  per-spawn context manager (`codex.codex_last_message_file`).
- **Claude command**:
  `claude -p --dangerously-skip-permissions --output-format stream-json --include-partial-messages --verbose <prompt>`
  (with `--resume <sid>` when resuming). `last_message` is parsed from the stream-json: prefers the terminal
  `{"type":"result","result":...}` event (honored regardless of how the run ended), falls back to the last
  `assistant`/`message` text content for schema-drift forward-compat. The fallback is gated to clean, completed runs
  (`exit_code == 0`, not timed out, not interrupted); an interrupted or non-zero run with no terminal `result` event
  exposes an empty `last_message` rather than a partial transcript chunk. That same terminal event is read once more,
  for its `is_error` flag: it is what tells a provider refusal the run ENDED on from an answer that merely quotes one,
  and `agents/provider_failures.py`'s transient-provider classifier prefers it over any text match (falling back to a
  narrow message prefix beside a non-zero exit only where no flag is present).
- **Antigravity command**:
  `agy --dangerously-skip-permissions --output-format stream-json --input-format text --print-timeout <seconds>s`
  followed by `--conversation <sid>` on resumes and `--print <prompt>`. The timeout matches the process budget.
  `agy.py` reads `event: result` through `observability/usage/agy_events.py`; only a `SUCCESS` response becomes the
  final message, and only when the structured lifecycle reducer reports no unfinished tool steps. When unfinished steps
  remain, the terminal response is suppressed, the outcome is forced non-zero, and `AgentResult.unfinished_steps`
  carries the step identities for recovery. Missing or failed terminal results produce a nonzero outcome, with
  diagnostics in `stderr`; `INTERRUPTED` and `CANCELED` also mark the run interrupted. Partial text remains available
  in the trajectory.
- **Input**: prompt string; optional resume session id; timeout (`AGENT_TIMEOUT` / `REVIEW_TIMEOUT`).
- **Output**: `AgentResult(...)`. `session_id` is harvested by `agents/session_ids.py` walking the JSONL events for
  any UUID-shaped value at `session_id` / `conversation_id` / etc. (shared across all backends).
- **Timeout cleanup** (`process_groups.terminate_process_group`): on timeout expiry the runner SIGTERMs the agent's
  whole process group (every spawn uses `start_new_session=True`), waits for the leader, then — mirroring the
  shutdown sweep (`terminate_all_running`, which spends the same escalation over every registered group) — probes
  the group with `killpg(_, 0)` and SIGKILLs any surviving descendant. Without the probe a build grandchild the
  agent forked (Maven, gradle, a JVM test runner) could keep mutating the worktree after the timeout was recorded —
  the failure mode that stranded a late clean commit behind the implementing-stage `agent_timeout` park.

### Environment filtering (`agents.environment.filter_agent_env`)

The agent subprocess env is filtered to keep host secrets and the orchestrator's own GitHub credentials out of agent
reach. The same filter runs for the verify-command runner (with `allow_provider_auth=False`, which also strips provider
keys).

- **GitHub-token-bearing env vars** are stripped (`GITHUB_TOKEN`, `GH_TOKEN`, etc. — the `_FORBIDDEN_AGENT_ENV`
  exact-match set) so a prompt-injected agent cannot push or call the GitHub API.
- **Production-secret-shaped env vars** are stripped by name shape: anything matching `_AGENT_SECRET_SUFFIXES`
  (`_TOKEN`, `_KEY`, `_SECRET`, `_PASSWORD`, `_PAT`, `_CREDENTIAL`) or the bare-name set (`TOKEN`, `KEY`, `SECRET`,
  `PASSWORD`, `PAT`, `CREDENTIAL`). Without this a `STRIPE_API_KEY` / `DATABASE_PASSWORD` set on the host would ride
  into a sandbox-bypassed agent or into the operator-configured verify shell.
- **Credential-file locators** are stripped too (`*_TOKEN_FILE`, `*_KEY_FILE`, `*_SECRET_FILE`, `*_PASSWORD_FILE`,
  `*_CREDENTIAL_FILE`, `*_CREDENTIALS`, `*_CREDENTIALS_FILE`, plus bare `TOKEN_FILE` / `CREDENTIALS` /
  `CREDENTIALS_FILE`). The most important case is `ORCHESTRATOR_TOKEN_FILE`, the orchestrator's own write-credential
  locator.
- **Write-credential locators** (`_AGENT_WRITE_CREDENTIAL_LOCATORS`: `SSH_AUTH_SOCK`, `SSH_ASKPASS`, `GIT_ASKPASS`,
  `GIT_SSH_COMMAND`) are stripped by exact name. The orchestrator's own push path constructs its own `GIT_ASKPASS`
  tempfile.
- **Provider auth** required to reach the agent's own model is allowlisted by exact name in
  `_AGENT_PROVIDER_AUTH_ALLOWLIST` (`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`,
  `OPENAI_API_KEY`) for agent subprocesses only. The verify runner passes `allow_provider_auth=False` and strips them
  too — a verify shell executes untrusted agent-produced code, and the verify-failure park comment publishes the
  offending command verbatim. Advanced deployments (Bedrock, Vertex, custom proxies) extend the allowlist explicitly.
- **`GIT_AUTHOR_*` / `GIT_COMMITTER_*`** are injected from `AGENT_GIT_NAME` / `AGENT_GIT_EMAIL` (default
  `chipping-orchestrator <chipping-orchestrator@users.noreply.github.com>`) so agent commits are stamped with the
  orchestrator's identity regardless of the host's `~/.gitconfig`.

### Hardened local git (`git.commands._git_hardened`)

Every local git operation inside a worktree the agent can write to runs through this envelope: the `-c` overrides
that neutralize `core.hooksPath` / `core.fsmonitor` / `credential.helper` / commit signing, `GIT_CONFIG_GLOBAL` and
`GIT_CONFIG_SYSTEM` detached from `~/.gitconfig` and `/etc/gitconfig`, and the orchestrator's committer identity.

The commits the orchestrator creates itself — the squash on approval, and the documenting pass's replacement of its
docs commit with one whose subject ends in ` (#N)` — are made through `git/publication/commits`, under the same `-c`
overrides for hooks, fsmonitor, and signing, the same detached global and system config, and `AGENT_GIT_*` as the
identity. The replacement keeps the developer's author: `git commit-tree` rebuilds it from the docs commit's own
tree, parents, and author, and a hardened `git update-ref` moves HEAD onto it only as a compare-and-swap against that
commit, so a checkout something committed on in the meantime refuses the move instead of having the newer commit
rewritten and published in its place.

Git's own output is decoded with `surrogateescape` rather than strictly, for the same class of reason. A repository
path is bytes, and a committed file whose name is not valid UTF-8 makes a strict decode raise inside `subprocess`
before any caller sees a return code -- taking the tick out where the probe should have reported the extra path and
parked the artifact it invalidates.

Two callers cannot afford to decode at all, so the same envelope has an undecoded form
(`_git_hardened_bytes`). Text capture folds a CR LF pair and a lone CR into a single LF, and a carriage return is a
byte a committed path may contain: a listing read as text names two different paths identically, which is harmless
for a probe comparing against a permitted set and fatal for a digest. A commit message is the other: the documenting
pass reads its docs commit's message to rewrite the subject and writes the rest back, and a CR LF body read as text
would go back as an LF body nobody wrote. A third form lives in `git.streaming`:
`_git_hardened_streamed` takes the request on stdin and hands stdout to a caller-supplied consumer a chunk at a time,
assembling none of it, for output whose size an agent decides. Its other two streams are files rather than pipes, so
reading stdout to exhaustion cannot deadlock against a stderr nobody is draining, and what git wrote there still comes
back on the record. That owner is spawned on the prefix and the environment `commands` assembles rather than on copies
of them, so all three forms take the same `env_extra` and build their environment through the one `_hardened_env`:
none can drift into keeping a protection the others have lost, and a caller pinning a reading pins every call of it.

It also turns object replacement off — `GIT_NO_REPLACE_OBJECTS=1` for `refs/replace/<oid>` and
`GIT_GRAFT_FILE=/dev/null` for the graft file. Neither of those is config, so nothing above reaches them, and each is
writable by an agent whose linked worktree shares the clone's refs and git dir. Left on, they change what git says a
commit's tree and parents ARE without changing the commit anyone named: a decomposer could stand a synthetic commit
carrying its code in for the base and have the plan check measure against that, while the push — which names the real
SHA — carries the code as well. Both are disabled for every hardened read, so a probe and the push it gates are
talking about the same objects.

Two more sit on the working-tree operations themselves rather than in the envelope, because neither is config either.
`core.worktree` in a linked worktree's own `config.worktree` — which an agent
enables by writing `extensions.worktreeConfig` into the clone it shares — points every path operation at any directory
it likes, and a `-c core.worktree=` override does NOT win against it, so the tree is named with `--work-tree` instead:
by `verification/status._worktree_status`, which would otherwise report on a clean shadow checkout, and by the
`reset --hard` in `worktrees/creation._move_branch_onto`, which would otherwise report success and move the ref while
writing the reviewed commit's files into that other directory -- leaving the issue's checkout on the plan it had, the
handoff baseline naming a tip the tree is not on, and whatever was in the redirected directory overwritten.
Both build the flag through `commands._work_tree_arg`, which spells the path absolutely: every command carrying it
runs with its cwd set to the worktree, and git resolves a relative `--work-tree` against THAT cwd — so a relative
`WORKTREES_DIR` would name a directory beneath the worktree, and git would refuse to run the command at all.
And `assume-unchanged` / `skip-worktree` are bits on an index entry: git honours them by not comparing the file, so a
tracked path the agent rewrote reports clean. Those entries are read separately (`git ls-files -v`) and answered as
paths AND as a withheld `readable`, so a caller refusing on what git listed and one that has to prove the tree empty
both fail closed on them.

One flag on the status read protects the tree from the reader rather than the reader from the tree. `git status`
refreshes the index as it goes and writes the refreshed stat data back, taking `index.lock` while it does, so a probe
that was only asked a question would leave a change in the repository it is asking about and could fail on a lock
neither it nor the agent running beside it needed. `_worktree_status` spells `--no-optional-locks` for that: nothing
about the answer changes, only whether taking it leaves a trace, and its callers are deciding whether to publish or to
reclaim rather than editing what they are deciding about.

One more class sits on the individual call, and for the opposite reason: these ARE settings git reads, but it reads
them from the environment, where a `-c` on the command line does not win. `_git_hardened` therefore takes an
`env_extra` a caller applies over both the process environment and the hardening above, and one reading spends it.

The added-line measurement (`git/measurement/additions.py`) pins `GIT_ATTR_SOURCE` to the candidate commit, so
the `.gitattributes` the count honours are the ones inside what is being measured rather than whatever the agent left
uncommitted in the checkout (an inherited value beats the `attr.tree` config a `-c` could set, and a `* -diff` planted
either way makes a textual candidate measure as zero), plus `GIT_ATTR_NOSYSTEM=1` so the host's own attributes stay
out of a number two hosts have to agree on. On the argv beside them the same reading pins what config CAN answer for:
`core.attributesFile` at `/dev/null`, `core.bigFileThreshold` at git's default, `--diff-algorithm=myers`,
`--no-renames`, `--no-relative`, and `--ignore-submodules=none` — the algorithm because git's algorithms pair a change
with repeated lines in it differently and disagree by whole lines, which would let a `git config` beside the work
retune the size ceiling from below it.

What no pin reaches is refused rather than reported on. `$GIT_DIR/info/attributes` is a file rather than a setting, so
nothing on the command line overrides it and it outranks every attribute source; a diff driver declared in the shared
repository's own config turns a path binary the moment any attribute assigns it. Both are writable from the agent's
worktree, so a measurement that finds either records a typed `diff_unpinnable` failure instead of a count — and it
inspects that path without opening it (`lstat`, no link followed, anything but a regular file refused), since a FIFO
or a `/dev/zero` symlink planted there would otherwise block or exhaust the tick that read it.

### Fingerprinting a prospective contribution (`git/measurement/fingerprint.py`)

The same three-dot range answers a second question — not how large a candidate is but which contribution it is — and
`_fingerprint_contribution` is the SHA-256 digest that answers it for a pair of already-proven commits. Everything
cheaper is wrong in a way somebody can arrange: an added-line count is equal for any two candidates of the same size,
a subject is prose the agent writes, a rename similarity score says nothing about what was written, tree equality
ignores the base the work will be reviewed against, and `git patch-id` survives rebases precisely by discarding
binary content, file modes, and whitespace.

What is hashed is git's raw listing (`--raw -z --no-abbrev`) followed by the content of every object that listing
names — neither of them a patch. Raw format renders no content, so the whole surface the added-line count has to pin
one setting at a time — attributes, attribute files, textconv, external helpers, the diff algorithm, the big-file
threshold, a diff driver — decides nothing here, and none of it needs refusing; the content behind the ids is read
through `cat-file`, which applies no filter and converts no line ending. Each record carries the pre- and post-image
modes and object ids, the status, and the path bytes, which is what makes path moves, mode-only changes, and
deletions move the digest, while the streamed content is what makes a changed byte move it — binary included.
`--no-renames` is what makes a rename representable the same way twice: with detection on, whether one record or two
come back is decided by a similarity threshold and a rename limit that a `git config` beside the work can retune. The
remaining pins are `--no-abbrev` against `core.abbrev`, `--ignore-submodules=none`, `--no-relative`, and an empty
`-O/dev/null` order file against `diff.orderFile` — a digest over a permutation of the same records is a different
digest for the same work.

Two more pins sit in the environment, where a `-c` on the command line does not reach them, and both are about what
this store is allowed to be while the reading is taken. `$GIT_DIR/shallow` is a file the agent's checkout shares
rather than a setting, and a commit named there is walked as though it had no parents — which moves the base a
three-dot range resolves to, or removes it, so the same two objects read as another contribution or as none; it is
pointed at `/dev/null`. And a clone made with a filter keeps a promisor remote, so git answers an id it is missing by
fetching it rather than by failing: left alone, a store that does not hold this contribution would go and get it
mid-reading, turning a local digest into a network call whose answer depends on what the remote still serves and
leaving packs behind in a store the tick was only reading. `GIT_NO_LAZY_FETCH=1` turns that off.

Both pins ride every call of the reading, the endpoint presence probes included: a commit made after a filtered clone
is precisely what a lazy fetch would supply, and precisely what `fingerprint_candidate_absent` is for, so an unpinned
probe would fetch the end and let the reading fingerprint a contribution the store never held. Neither pin goes in
the envelope every hardened call shares, because a shallow clone and a partial clone are things a repository
legitimately IS — a rebase in one needs its objects fetched, and `git/measurement/commits.py` probes for an object
precisely so it can go and fetch it — while this reading has to be answerable from this store alone, over the whole
history these commits have, or refuse.

The content is in the digest rather than merely named by it because an object id is a claim about content only where
something checks the two against each other, and git does not: a loose object swapped for a different, perfectly
valid one is served under the name its file sits at, and nothing short of `fsck` notices. The store here is the one
the agent works in. Hashing the bytes git actually produces settles that without a verification step — substituted
content is not the same contribution and does not fingerprint like one.

The bytes are hashed behind a label naming what they are — `chipping-orchestrator/prospective-diff/<version>` — so a
digest taken here cannot collide with one something else in this system takes over some other listing, and a later
representation is a different scheme rather than a silently different answer under the same name. That version is
published as `FINGERPRINT_FORMAT` on the record owner beside it, and it is what any caller persisting a digest records
next to it: two ids taken under different rules are not comparable and nothing about the ids themselves would say so,
so a stored fingerprint naming a scheme this build does not compute is one it declines to read rather than one it
silently compares. The late-split exemption, the rewrite authorization beside it, and the operator-authorized
oversized publication are all such callers
([`state-machine/labels-and-state.md`](state-machine/labels-and-state.md#late-generation-state)).

The two endpoints decide what is fingerprinted and are deliberately not in the digest, so the same work over the same
base fingerprints alike no matter which commits carry it. That is also the limit of what comparing two digests
settles: they agree that the same work was contributed over the bases each was taken between, and say nothing about
whether either base is one the repository's base branch really has. Where a rewrite CHOOSES that base — which is what
a rebase does — the permit carrying an exemption across proves it separately, freezing the base branch from the remote
and refusing a recorded base that tip does not reach
([`security.md`](security.md#what-a-trusted-pinned-record-still-cannot-license)).
Both commits are proven present before the listing runs, so
an end this host does not hold is reported as `fingerprint_base_absent` / `fingerprint_candidate_absent` rather than
surfacing as a diff error, and a listing that failed records `fingerprint_diff_failed` with no digest beside it —
what a failed `git diff` writes to stdout is nothing, which is also what a candidate that changes nothing writes.

Proving the commits is not proving the contribution, and closing that gap is the last step before anything is hashed.
A raw listing is walked out of trees and never opens a blob, so a repository holding both commits and every tree under
them — but missing the content at one changed path, from a fetch that half-arrived, a store pruned under a running
tick, or an object file that will not inflate — produces the same listing a complete repository does and git exits 0.
The listing is therefore parsed before anything is read — a stream whose records this build cannot account for is
`fingerprint_diff_unreadable`, and that includes a non-empty listing not ending in the NUL every one of its fields is
terminated by, which is a last path cut short rather than a whole record. Every object id it names on either side —
the pre-image as much as the post-image — is then asked for in one `git cat-file --batch`, and that single read is
where the content is both taken and checked. Asking one command whether the objects are there and reading them with
another would leave a window between the two answers wide enough for a `gc` in the checkout or an agent still running
beside the tick, and what falls into it does not surface as an error: `--batch` reports an object it cannot find as
the bare word `missing` on the same stdout the digest is taken over, and exits 0. So the answer is read as a protocol
— every id asked for, in the order asked, answered as a blob of the length its header claims — with the content
folded into the digest as it passes that check, and anything else is `fingerprint_content_absent`. A blob corrupt
past a header that inflated fine is caught by the same read, since git stops mid-stream and exits non-zero. Gitlinks
are excluded: mode `160000` names a commit in the submodule's repository, which this store has no reason to hold, so
requiring it would refuse a fingerprint to every candidate that touches a submodule.

## Push path (`git.branch_transport._push_branch`)

The orchestrator (not the agent) pushes. The push is hardened against the agent-controlled worktree:

- Token delivered via `GIT_ASKPASS` tempfile, never argv.
- Detaches from `~/.gitconfig` and `/etc/gitconfig` (`GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_SYSTEM=/dev/null`).
- Disables `core.hooksPath`, `credential.helper`, `core.fsmonitor`.
- Refuses to push if the config the push resolves — the worktree's local config plus any `include.path` file or
  per-worktree `config.worktree` it pulls in, with global/system detached — carries any `url.*.insteadOf` /
  `pushInsteadOf` rewrite or any `http.*` proxy/TLS setting (e.g. `http.proxy`, `http.sslVerify=false`) that could
  tunnel the token-bearing push through an attacker proxy or disable certificate verification. Env-var proxies
  (`https_proxy`) are operator-set and stay honored — only agent-writable config-file transport is rejected.
- Pushes via an explicit refspec (no upstream stored): `HEAD:refs/heads/<branch>` by default, or
  `<revision>:refs/heads/<branch>` when the caller names the commit it means. Every caller that decided to push by
  INSPECTING a commit names it, because `HEAD` between the reading and the push is not necessarily the commit that
  was checked. Two publish for the FIRST time: the discussion stage's plan publication, which proves the branch
  carries the agreed plan and nothing else; and the implementing stage's publication, which decides on one commit
  before the push and names the push, the record it leaves, and the proof it takes afterwards against that same one
  — the commit the size gate measured or the exemption accepted where there is one, and the commit the checkout is
  standing on where the gate proved none (a new candidate while `DECOMPOSE=off`), since the switch keeps candidates
  out of the measurement rather than making them unnameable. **Neither of those two falls back to `HEAD`**: a
  checkout that cannot name the commit it is on is refused rather than published as it stands — the plan
  publication reads an unread tip as
  unpublishable, and the implementing publication parks (`late_candidate_moved`), because a push named against
  nothing sends whatever the branch has become by the time git runs it, records no receipt, and leaves the proofs
  around it with no commit to compare against. Implementing additionally refuses the handoff when the checkout has
  left that commit — before the push and again once the pull request is open, since every stage past it works from
  the checkout rather than from the refspec.
- Every push onto a pull request the remote ALREADY carries names its commit too, and the size gate is what names
  it: the gate measures before each of them and hands back the commit it measured, which is what the push publishes,
  what the receipt records, and what the proof behind it compares against. Those are the docs pass, the `validating`
  dev-fix and both its transient-park recoveries, the `fixing` bounce, the three `conflicts` publications, the squash
  rewrite, and the base-sync auto rebase and its crash recovery. Each of them refuses a moved REMOTE as well — the
  rewrite, the conflict publications, and the base-sync rebases pin `force_with_lease` to the SHA they observed
  before the rewrite, and the rest are pinned to the head the gate's own entry froze.
- The bare `HEAD` form is left for the one push that could name no commit at all: a gated push on an install running
  with `DECOMPOSE=off` whose checkout would not prove its own head. The switch keeps candidates out of the
  MEASUREMENT and not out of a push that knows what it is publishing, so the commit is named off the checkout there
  too — only a reading that failed outright falls through, publishing whatever the worktree currently is with the
  receipt and the post-push proof skipped, since neither has a commit to be about.

## Observability

Three independent JSONL sinks plus an optional Postgres aggregation target watch a run without steering it: an opt-in
audit event log, a project-local analytics sink, an opt-in (default-off) trajectory sink that `record_agent_exit`
fills with redacted, head/tail-truncated per-run reasoning trajectories, and the operator-deployed database the
analytics sink is replayed into. Two Streamlit pages read them: the analytics dashboard over that database, and the
file-backed trajectory viewer, which reads its JSONL directly (usage and cost included) and needs no database at all.
None of them feed back into dispatch — workflow correctness keys off the pinned state JSON and the workflow label —
so every surface is observation-only and safe to truncate, rotate, or delete.

They are not all owned in one place. The audit sink belongs to `github/events.py`, since `GitHubClient.emit_event` is
the single chokepoint it is appended from, and the Postgres service is the operator's own `analytics-db/` deployment.
Everything else — the analytics sink and what is downstream of it, the trajectory writers, the usage parser, and both
read models — lives under `orchestrator/observability/`, whose own four owner areas are mapped together with the two
`apps/` pages composed over them in
[`architecture/observability-modules.md`](architecture/observability-modules.md).

[`observability.md`](observability.md) is the map over the surfaces themselves, and each has a reference page behind
it: the two JSONL sinks in [`observability/event-streams.md`](observability/event-streams.md), the trajectory sink
and its viewer in [`observability/trajectories.md`](observability/trajectories.md), the compose layout and sync CLI
in [`observability/analytics-database.md`](observability/analytics-database.md), the read model and dashboard wiring
in [`observability/analytics-dashboard.md`](observability/analytics-dashboard.md), and the usage parser's
cost-precedence rules in [`observability/usage.md`](observability/usage.md).

## Summary of "what runs when"

- **`cli.main` polling loop** — long-lived Python process. Trigger: manual start (or wrapper). Cadence: every
  `POLL_INTERVAL`s.
- **`workflow.engine.tick.tick(gh, spec)`** — function call. Trigger: each loop iteration. Cadence: once per tick per
  configured `RepoSpec`; multi-repo fans out across a `ThreadPoolExecutor`, single-repo stays in-thread.
- **`_refresh_base_and_worktrees(gh, spec)`** — function call. Trigger: start of each `workflow.engine.tick.tick`.
  Cadence: once
  per tick per repo: one `git fetch <spec.remote_name> <spec.base_branch>`, then per-worktree dispatch — a pre-PR
  worktree rebases locally, and a PR-having one behind base is rebased and pushed in the refresh itself.
- **`_handle_*` per issue** — function call. Trigger: the issue's workflow label. Cadence: once per tick per pollable
  issue, except an open `workflow:blocked` / `workflow:umbrella` issue, which is dispatched only on the ticks
  `DEPENDENCY_POLL_EVERY_N_TICKS` makes due (default every fifth, the first included); concurrent up to
  `spec.parallel_limit` per repo and `MAX_PARALLEL_ISSUES_GLOBAL` across all repos. No-agent family buckets
  (`workflow:blocked` / `workflow:umbrella`) are cap-exempt.
- **decomposer agent (`DECOMPOSE_AGENT`)** — subprocess (fresh or resumed). Trigger: `_handle_decomposing` (retry
  budget OK) or HITL resume. Cadence: one shot per tick when needed. The same role spec also backs both conversation
  stages, which pin their own agent and session keys rather than a decomposing one.
- **implementer agent (`DEV_AGENT`)** — subprocess. Trigger: `_handle_implementing` (no commits yet, retry budget OK)
  or HITL resume. Cadence: one shot per tick when needed.
- **reviewer agent (`REVIEW_AGENT`)** — subprocess (fresh session). Trigger: `_handle_validating`, round < max, over
  a developer report the pull request carries, which the prompt quotes whole. Cadence: one shot per tick.
- **dev-fix agent** — subprocess (resumed dev session). Trigger: a reviewer `CHANGES_REQUESTED` verdict (dispatched
  from `_handle_validating` after the relabel to `workflow:fixing`) or fresh in_review PR feedback (dispatched from
  `_handle_fixing` after the quiet window) — both run with `stage="fixing"` and bounce back to `workflow:validating`
  for re-review. Cadence: one shot per tick.
- **dev-conflict agent** — subprocess (resumed dev session). Trigger: `_handle_resolving_conflict` and `git rebase`
  left conflicts. Cadence: one shot per tick.
- **question / discussion agent (`DECOMPOSE_AGENT` backend)** — subprocess. Trigger: `_handle_question` or
  `_handle_discussion` on the conversation's opening round or on a trusted human reply to a parked one. Cadence: one
  shot per tick when needed. `question` is read-only for the whole conversation; `discussion` is read-only until a
  human confirms the design on the thread, and from there is allowed exactly one commit of
  `plans/issue-<number>.md` for the stage to publish. Neither ever spawns a developer or reviewer.
- **`git push`** — subprocess. Trigger: after dev produces clean commits, or after a discussion round commits the
  confirmed plan and the branch reads as exactly that one file. Cadence: per fix; per discussion, once the humans
  have confirmed the design.
- **self-restart check** — git fetch + diff. Trigger: start of each tick. Cadence: every tick.

## Architecture schema

```
                     ┌──────────────────────────────────────┐
                     │   GitHub repo(s) (REPO or REPOS)     │
                     │   ─ issues (with workflow labels)    │
                     │   ─ pinned state comment per issue   │
                     │   ─ branches / PRs                   │
                     └──────────────┬───────────────────────┘
                                    │ PyGithub (one token per slug)
                                    │
   ┌────────────────────────────────┴─────────────────────────────────────┐
   │  orchestrator process  (python -m orchestrator)                      │
   │  ───────────────────────────────────────────────────                 │
   │   cli.main over orchestrator/runtime/                                │
   │     startup: build per-spec [(spec, GitHubClient), ...] from         │
   │              config.default_repo_specs(); ensure_workflow_labels;    │
   │              build one shared IssueScheduler(global_cap, per_repo)   │
   │     loop every POLL_INTERVAL s:                                      │
   │       1. self-restart check (origin/<ORCHESTRATOR_BASE_BRANCH>       │
   │          moved & touches orchestrator/?)                             │
   │       2. run_tick(state, clients, scheduler):                        │
   │            N == 1 → in-thread engine_tick.tick(gh, spec, scheduler)  │
   │            N  > 1 → ThreadPoolExecutor fans engine_tick.tick across  │
   │                     one worker thread per repo                       │
   │       3. scheduler.reap()  (drain completions; surface failures)     │
   │       4. retention.prune_with_retention_logging()                    │
   │     shutdown: scheduler.shutdown(wait=True) drains workers on        │
   │               --once / self-restart; a signal stop first kills       │
   │               in-flight agent+verify groups, and a watchdog          │
   │               hard-exits within SHUTDOWN_GRACE_SECONDS on overrun    │
   │                    │                                                 │
   │                    ▼                                                 │
   │   engine_tick.tick(gh, spec, scheduler) →                            │
   │     _refresh_base_and_worktrees(gh, spec, scheduler): skip           │
   │       worktrees whose handler is still in flight in scheduler        │
   │     classify each pollable issue and submit to scheduler:            │
   │       open `workflow:blocked` / `workflow:umbrella` on a tick        │
   │         DEPENDENCY_POLL_EVERY_N_TICKS skips → dropped first          │
   │       family-aware (`workflow:decomposing` / `workflow:blocked` /    │
   │         `workflow:umbrella` / unlabeled) →                           │
   │         ONE bucket submit per repo that drains sequentially          │
   │         (cap-exempt when every family issue is                       │
   │         `workflow:blocked` or `workflow:umbrella`)                   │
   │       fan-out (everything else) →                                    │
   │         one submit per issue, concurrent up to per-repo / global     │
   │         caps                                                         │
   │     scheduler rejects duplicate active / cap hit / family-slot       │
   │       conflict → skipped this tick AND logged with reason            │
   │     accepted workers call gh._for_worker_thread() + refetch the      │
   │       Issue, then run _process_issue → dispatch by label             │
   │                                                                      │
   └─────────┬───────────────────────────────────────┬────────────────────┘
             │ subprocess                            │ subprocess (hardened)
             ▼                                       ▼
   ┌─────────────────────────────┐         ┌─────────────────────────────┐
   │  coding-agent CLI           │         │  git push                   │
   │  (codex / claude / agy,     │         │  ─ GIT_ASKPASS tempfile     │
   │   per-issue worktree)       │         │  ─ no global/system config  │
   │  ─ env: GH tokens stripped  │         │  ─ hooks/helper disabled    │
   │  ─ env: GIT_AUTHOR/COMMITTER│         │  ─ refuses url/http cfg     │
   │     stamped (orchestrator)  │         └──────────────┬──────────────┘
   │  ─ provider auth left alone │                        │
   │  ─ --bypass / --skip perms  │                        │
   │  ─ JSONL → session_id       │                        │
   │  ─ last_message: -o (codex) │                        │
   │     or stream-json          │                        │
   └──────────────┬──────────────┘                        │
                  │ commits to                            │ pushes branch to
                  ▼                                       ▼
   ┌─────────────────────────────────────────────────────────────────────┐
   │  git worktree:  <WORKTREES_DIR>/<owner>__<name>/issue-<n>           │
   │  branch:        orchestrator/<owner>__<name>/issue-<n>              │
   │  ─ slug subdir + slug-namespaced branch keep two repos sharing a    │
   │    target_root from colliding on the same `orchestrator/issue-<n>`  │
   │  ─ created from <spec.remote_name>/<spec.base_branch>               │
   │    in spec.target_root                                              │
   │    (or reused if has unpushed commits)                              │
   └─────────────────────────────────────────────────────────────────────┘
```

## State transition (label lifecycle)

The compact label-lifecycle diagram for every forward, fix-loop, terminal, and HITL-park transition lives in
[`state-machine/lifecycle.md`](state-machine/lifecycle.md).

[pinned-state]: state-machine/labels-and-state.md#pinned-state
