---
description: >-
  How chipping-orchestrator's GitHub-backed polling process is built: its module map, process model, agent subprocess
  boundary, and hardened git and push path.
---
# Architecture

Single-process **polling orchestrator** that drives GitHub issues through a label-based state machine, delegating coding
work to a configurable coding-agent CLI (`codex`, `claude`, or `agy`) running as a subprocess in isolated git worktrees.

State lives in GitHub: a workflow label exposes the current stage and a pinned JSON comment holds per-issue durable
state. The orchestrator process can restart at any time. Beside GitHub it keeps one per-issue record on the host, an
Antigravity launch's quota retirement record, and -- while that record will not take a write -- the resolution its
poller holds in memory until it does; both are covered under [Design constraints](#design-constraints).

This page owns the design constraints, process and agent boundaries, hardened git and push model, and system diagram.
The sections below connect those concepts to the focused module, state-machine, agent, and observability references.

## Design constraints

GitHub Issues are the orchestrator's task tracker and durable state surface. The process intentionally avoids an
internal database: workflow labels expose the current stage, and the pinned JSON comment holds the per-issue state that
the next tick needs. This keeps progress visible to humans on github.com and lets the process restart without
reconstructing hidden local state. The exception is the quota retirement record
(`workflow/stages/implementing/quota_record.py`) beside each issue's writer claim on the host: every Antigravity
developer launch arms it before it runs, and every developer launch reads it first, since a retirement the pinned
comment has not yet taken is owed from it. Each change to it is flushed to the host's disk before anything a later
launch rests on goes on, so a restart -- a host crash included -- on the same host keeps it, while another host, or a
fresh `WORKTREES_DIR`, never sees it. A resolution the record would not take lives only in its poller's memory until
it does, holding that issue's launches meanwhile. And an arming whose outcome never reached the record -- its poller
killed mid-run -- holds that issue's developer launches until an operator writes the retirement it owes or settles
it, as the [operations runbook](configuration/operations.md#running-more-than-one-poller) describes, so such a restart
is not recovered from GitHub alone ([what survives a restart](configuration/operations.md#what-survives-a-restart);
[backups](security.md#backup-and-restore-drills)).

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

The per-package inventories own the module-level map:

- [Platform modules](architecture/platform-modules.md): launch forms, `runtime/`, `service/`, `config/`, `github/`,
  `agents/`, `scheduler/`, `git/`, and `skills/`.
- [Workflow modules](architecture/workflow-modules.md): state vocabulary, dispatch, late splitting, and stage handlers.
- [Observability modules](architecture/observability-modules.md): analytics, usage parsing, dashboards, and app targets.

```
orchestrator/
  __init__.py       distribution version
  cli.py            console-script entry point and command composition
  __main__.py       python -m orchestrator launch form
  runtime/          polling process, shutdown, self-restart, artifact maintenance
  service/          installed setup, packaged templates, systemd service management
  config/           settings, target selection, credentials, and redaction
  github/           GitHub API surfaces and pinned-state model
  agents/           CLI backends, subprocess lifecycle, and result parsing
  scheduler/        shared issue scheduler and host-local writer claims
  workflow/         label state machine, tick engine, late splitting, stage handlers
  git/              hardened transport, worktrees, base sync, publication, snapshots
  skills/           repository skill catalog
  observability/    recording, usage parsing, database reads, and page composition
  apps/             Streamlit launch targets
```

Other repository roots hold `tests/`, `docs/`, operator-owned `analytics-db/`, and human working notes under `plans/`.
Tests mirror the package layout. The development wrapper is `run.sh`; metadata and locked dependencies live in
`pyproject.toml` and `poetry.lock`.

Imports run from configuration through domain packages to workflow decisions and finally application composition.
Callers name defining owners; most initializers are markers, with explicit public surfaces on declared publishers.
Repository checks enforce package inventories, mirrored tests, absolute imports, and the absence of compatibility
facades, resolver hooks, and export manifests. The per-package pages above own their boundary exceptions; the
[CI reference](configuration/operations.md#continuous-integration) owns repository-wide checks and naming rules.

## Workflow labels

Workflow labels expose an issue's current stage. `workflow:<tag>` is the GitHub spelling for orchestrator-owned states;
bare tags identify handlers and analytics stages. Conversation and terminal labels retain their bare spelling.
The [label reference](state-machine/labels-and-state.md#workflow-labels) owns the vocabulary and control labels,
including [migration from legacy spellings](state-machine/labels-and-state.md#legacy-labels-and-the-migration-off-them).

## Process model

There is **only one long-lived process**: `chipping-orchestrator run`, the polling command of the package installed
by pipx. The systemd user service `init` installs supervises it, launched as `-m orchestrator run` under that
installation's own interpreter. Developer source checkouts also offer a module launcher and `run.sh`
so the loop can self-exit and be restarted with new source code; those launch commands are in the
[developer guide](development.md). The bare command, `--help`, and `--version` poll nothing: they print and exit 0
before any configuration is read, and a polling flag given before any command is refused with the `run` form that
means it. `configure` and `add-repo` poll nothing either: one writes an installed package's `.env` and the other adds
a repository to it, and each exits reading no configuration ([basic setup](configuration.md#basic-setup)). Nor does
`init`, which writes and enables the service's unit and exits without starting it
([user service](configuration.md#running-under-systemd-user-service)), or the commands that manage that service:
they ask the user manager to start, stop, restart, show, or remove it, `start` and `restart` once a local check in an
interpreter of its own finds nothing wrong, and exit.

- **Trigger**: started manually (or by a wrapper) as `run`. Optional `run --once` for a single tick, or
  `run --cleanup-terminal-artifacts` for a maintenance-only run: it connects read-only clients (no label bootstrap)
  *before* claiming the host, since a client that lands in a rate-limit backoff sleeps for as long as the reset takes
  and nothing unbounded may sit inside the claim, then reclaims the artifacts of finished issues and exits without
  polling. It writes no *workflow* state — no label, no
  pinned state, no comment — and does delete the orchestrator-owned branches it proved reclaimable, in the clone and
  on the remote, which is what it is for. The form a nightly service timer runs.
- **Configuration refusal** (`orchestrator.config`, at import): once the options are read, the first runtime owner
  `cli.py` imports loads the configuration, and an invalid setting stops every launch mode there with exit status 1
  and the error on stderr, before any GitHub client, label bootstrap, poll, or maintenance pass. That covers the
  targets: an installed package without `REPOS`, and every selected target that is not a git checkout, all of them
  named in one error. Which targets a start selects and what counts as a checkout are under
  [`configuration.md#developer-fallback-and-target-checks`](configuration.md#developer-fallback-and-target-checks).
- **Startup refusal** (`runtime.startup.require_issue_authors`): every launch mode reads its options and then stops
  with exit status 1 while `ALLOWED_ISSUE_AUTHORS` names nobody, before logging, the signal handler, the host claim,
  any GitHub client, or the scheduler exists, because an empty allowlist would trust every author. The `run` options
  are defined by `runtime.options`, which loads no configuration, and `cli.py` imports every other runtime owner --
  each of which resolves and validates the settings as it is imported -- only after the command line is parsed, so
  `--help`, `--version`, and `run --help` answer on a host with no configuration or a malformed `REPOS`, while a
  launch that goes on to run still meets that validation first. The
  setting is under [`configuration.md#required`](configuration.md#required).
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
- **Issue writer claims** (`scheduler.writer_claims`): one exclusive `flock` per repository issue under
  `WORKTREES_DIR/.issue-writer-claims/`, keyed by the repository's numeric GitHub id (the client's `repo_id`, never a
  name: neither the configured slug nor the `owner/name` a poller fetched before a rename) and the issue number. The
  same namespace keeps each issue's quota retirement record beside its claim file, written only under the claim and
  host state rather than lock bookkeeping ([design constraints](#design-constraints)). Every
  dispatch path takes it before anything it does for the issue — the worker's refetch, the pinned-state guards, the
  close recovery wrapped around the pass, and the handler — and the enumeration takes it for the close receipt it posts,
  so two pollers sharing a checkout root never write one issue's pinned comment and labels at once. A family handler's
  writes to a child take the child's claim the same way, and the walk that releases children reads each again behind it
  rather than trusting its scan; an ordinary split that meets a child another poller holds leaves it unseeded and the
  parent `workflow:decomposing`, for `stages/decomposition/recovery.py` to seed it, post the summary, and finalize. The
  pre-tick base refresh takes the same claim on the same key for each worktree it syncs, behind the scheduler's
  active-issue skip and before it reads the issue, and holds it through the whole route — the pre-PR rebase, the PR
  rebase and its push, the unreadable-checkout park, and an interrupted attempt's recovery and settlement — so a refresh
  contends with a dispatch, and with another poller's refresh, as two dispatches do. Nothing under it takes the claim
  again: the anchor answer the dispatcher reaches too runs there under the dispatch claim. A refresh refused the claim
  reads and writes nothing for the issue, and syncs it on a later tick. The claim is never waited for: a contender
  skips the issue with no effect but a close it
  read, which it keeps in its own latch and retries on a later tick; different issues never contend. That latch is tied
  to a late cycle only where the record is read first, the issue still reads closed behind it, and the record read again
  behind the issue names the same cycle, or where the holder noted on the claim that it is retiring the cycle the record
  has just dropped (`scheduler.claim_notes`) — so a cycle the holder settles and an operator restarts meanwhile is not
  ended by it, and a close of the fresh cycle the holder restarted between those reads is tied to that cycle rather than
  dropped. A restart this process writes, which no claim note records, is fenced the same way: a close read before that
  write ended ends nothing of the fresh cycle (`engine/retiring_cycles.py`). Every acquisition reads what the last hold
  left, empties the file, and signs it with a per-process token, and a hold its own process lets go of stamps the moment
  it did on the host's monotonic clock, so a poll that later passes the issue can tell whether another poller held it
  after the moment the poll took before listing it; only where none did does a close no read tied to a cycle end the one
  the record names. A hold a restarted poller's predecessor stamped before that moment costs nothing, while a killed
  hold, one whose last line was cut short, and the empty file an issue's first claim on the host finds each count as
  ending when found, so a reading taken before them is tied to no cycle by that alone. A note of a retiring cycle is
  read only off a hold that has not stamped its release. Inside one process it is exclusive between threads too, except
  that a close receipt or a consumer notice is let in alongside this process's own worker, which it was built to land
  beside. A claim that cannot be worked at all — an unopenable namespace, a filesystem without `flock` — withholds the
  issue too, where the presence above lets a poller go on unclaimed: a tidying job can be given up, an issue's record
  cannot be written uncoordinated. Released however the dispatch or refresh route ends and by the kernel when the
  process dies; the files
  are never unlinked. It is host-local and separate from the presence: neither says anything about the other, and
  nothing coordinates pollers on different hosts or checkout roots. The supported topology and the namespace's access
  assumptions are in the [operations runbook](configuration/operations.md#running-more-than-one-poller).
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
- **Self-restart guard** (`runtime.self_update.self_modifying_merge_happened`): each recurring tick with a resolvable
  startup HEAD fetches `origin/<ORCHESTRATOR_BASE_BRANCH>` (default `main`). If it advanced past the startup SHA *and*
  the new commits touch `orchestrator/`, the loop exits 0 so the wrapper can re-exec the new code. The branch is
  decoupled from `BASE_BRANCH` so a target repo with a different default branch does not interfere with self-update
  detection. The guard runs only in the orchestrator's own source checkout — an ordinary clone, a linked worktree, or
  an editable install — as `service.paths.is_source_checkout` proves it at the package root itself. An installed
  package has no startup HEAD, even inside an enclosing git repository, so it runs no git for this guard, never
  fetches, and never exits for a self-modifying merge; its version changes only through an explicit pipx upgrade or
  reinstall.
- **Developer checkout self-update resilience** (`run.sh self_update`): before each launch — at startup and after every
  self-modifying-merge restart — the wrapper fast-forwards the orchestrator checkout to
  `origin/<ORCHESTRATOR_BASE_BRANCH>`. It skips the pull and warns to stderr if a non-base branch is checked out, and
  warns and continues (rather than exiting) if the fast-forward fails (diverged base branch, rebase in progress, network
  error); either way it launches the existing working tree. A clean fast-forward still updates the tree before launch,
  so the self-modifying-merge flow keeps picking up new code. This is deliberate: under a development systemd unit
  (`Restart=always`) exiting on a self-update failure silently crash-loops the service with the orchestrator never
  running, so a stale-but-running process plus a journal warning is preferred — the warning is the operator's signal
  to restore the checkout.
- **Developer checkout dependency refresh** (`run.sh refresh_dependencies`): before every Python launch, the wrapper
  checks the checkout's dependency files against its successful install stamp and refreshes the environment when
  they differ.
  The [developer guide](development.md#launcher-dependency-refresh) documents the stamp, timeout and
  child-process caveat, optional-group handling, sync requirements, and retry policy.
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

`runtime.ticks.run_tick` calls the workflow tick for each configured repository: one runs in-thread, while several
fan out through a `ThreadPoolExecutor`. All share one long-lived `IssueScheduler`, so global and per-repository caps
bound the deployment as a whole.

Within a repository, the tick refreshes base and worktrees, sweeps community pull requests, emits the skill catalog,
and dispatches issues. Family-aware work drains sequentially in one bucket; independent work can run concurrently.
Each issue executes under its host-local writer claim, including family writes to children and base refreshes.
The [per-tick reference](state-machine/labels-and-state.md#per-tick-flow-workflowengineticktick) owns the sequence,
[pinned-state reference][pinned-state] owns durable writes, and
[base-refresh reference](state-machine/labels-and-state.md#base-refresh) owns rebase and publication recovery.

## Stage handlers

The dispatcher resolves handlers on their defining modules at call time. Twelve active workflow labels map to nine
stage packages; unlabeled pickup is an engine entry, while `done` and `rejected` have no ordinary handler. The
[workflow module map](architecture/workflow-modules.md) owns those locations and import boundaries.

Shared guards reconcile unfinished transactions before a handler runs. Closed family owners take a cleanup route;
other issues dispatch by label. The [delivery-stage reference](state-machine/delivery-stages.md) owns these guards,
drift routing, and the implementation/review loop. The
[conversation-stage reference](state-machine/conversation-stages.md) owns `question` and `discussion`.

<a id="agent-subprocess-agentsrun_agent"></a>

## Agent subprocess (`agents.runner.run_agent`)

`run_agent(backend, prompt, cwd, ...)` dispatches to the per-backend runner (`codex.run_codex` /
`claude.run_claude` / `agy.run_agy`); `backend` is one of `"codex"` / `"claude"` / `"agy"` and is re-validated
at call time so misuse fails loudly. All runners return a unified
`AgentResult(session_id, last_message, exit_code, timed_out, stdout, stderr,`
`interrupted, usage, invoked, unfinished_steps, terminal_failure)`.
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
and the result is forced non-zero so recovery can act on it. `terminal_failure` (default `None`) is the
`TerminalFailure` record a backend attaches to a run it normalized to a failure, so a consumer can tell why the run
stopped without reading `last_message`; only Antigravity fills it, as its command entry below describes.
`CodexResult` is kept as a transitional alias.

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
  per-spawn context manager (`codex.codex_last_message_file`). A failed turn writes nothing there, so `stdout` keeps
  the JSONL event stream beside the empty `last_message`: `agents/codex_events.py` reads the error the last turn's
  closing `turn.failed` carried, and `agents/provider_failures.py`'s `codex_usage_limit_failure` turns a usage-limit
  stop into a diagnostic with the provider message and its reset time, which a reviewer round parks on under
  `reviewer_usage_limit` rather than reading as a crash.
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
  diagnostics in `stderr`; `INTERRUPTED` and `CANCELED` also mark the run interrupted, though one whose failure record
  names the exhausted quota is not read as a shutdown-sweep kill (`agents/models.py`'s
  `is_shutdown_sweep_interrupted`), so it reaches disposition rather than being dropped. Partial text remains available
  in the trajectory. Neither a response step, on either side of the terminal, nor a `DOCS: NO_CHANGE` response
  overrides an error, interrupted, or missing terminal, and no later step is trusted to repair a stale one. Every
  run that fails the gate also carries `AgentResult.terminal_failure`, read by `agents/agy_failures.py`:
  `process_exit_code` keeps what the subprocess returned, since a zero return is normalized to `exit_code == 1`, or
  `None` where nothing was captured -- a run the timeout killed carries the runner's `-1` sentinel instead;
  `status` (`None` when no terminal result named one) and `error` are the terminal's, each redacted with
  `redact_secrets` before it is cut to a 1,024-character budget; `quota_exhausted` is the account-quota verdict and
  `quota_reset` the reset interval as AGY phrased it (`2h42m39s`), or `None`. The verdict reads failure evidence
  only: the `error` of an unsuccessful terminal and the CLI's own stderr diagnostic lines. An `AGY_ERROR:` line is
  settled by its structure alone (`status` `RESOURCE_EXHAUSTED`, `error_code` `429`, `code_kind` `http`, and
  `retryable` `true`, each matched by JSON type), while the terminal error and an `error:` line are matched on AGY's
  `Individual quota reached` wording. An exit code, the terminal response, and step or tool text never decide it, so
  a successful answer about a quota stays an answer and an unrelated failure keeps its classification. The reset is
  read from the complete diagnostic, so a wrapped message keeps it: the whole terminal error, the decoded strings of
  the structured payload, or an `error:` line with the lines continuing it up to a blank line or the next
  diagnostic, where only the opening line decides the verdict. The shared question park
  (`workflow/stages/implementing/parks.py`) takes the session-limit park on the quota verdict, asked through
  `session_read.py`'s quota classifier, and `workflow/engine/agent_diagnostics.py` reads `quota_reset` and
  `process_exit_code` for the notices it renders. The developer run coordinator
  (`workflow/stages/implementing/execution.py`) asks the same verdict of every attempt as it returns, through
  `quota_retirement.py`: the conversation the quota stopped is retired for good (`dev_session_retirement`) before the
  result is handed back, and earns no AGY command continuation.
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

- **Inherited virtualenv activation** (`_INHERITED_ENVIRONMENT_MARKERS`: `VIRTUAL_ENV`) is stripped for every managed
  repository, including its `bin` directory on `PATH`. Conda activation is preserved. The
  [environment selection policy](configuration/operations.md#dependency-tooling) covers target-repository setup
  and verification requirements.
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
- Every push onto a pull request the remote ALREADY carries uses the gated publication path. It names the candidate
  for the push, receipt, and post-push proof, subject to the disabled-gate fallback below. These are the docs pass,
  the `validating` dev-fix and both its transient-park recoveries, the `fixing` bounce, the three `conflicts`
  publications, the squash rewrite, and the base-sync auto rebase and its crash recovery. A caller-supplied lease
  is retained; otherwise a frozen entry supplies the lease. A moved remote refuses that lease. With neither a frozen
  entry nor a caller-supplied lease, the transport reads the remote itself.
- **HEAD fallback with the gate disabled.** When `DECOMPOSE=off` keeps a fresh existing-PR candidate out of measurement,
  `stages/implementing/late_publication.py`'s `_unentered` uses the checkout head if the gate supplied no candidate.
  If that read also fails, the revision stays empty and `late_push.py`'s `_pushed` calls `_push_branch(revision=None)`,
  publishing `HEAD:refs/heads/<branch>`. The publication receipt and post-push checkout proof are skipped because
  neither has an identified commit to describe or compare against.
- A typed boundary carries the base-sync auto rebase's push. The workflow's ordinary publication of a clean rebase
  (`workflow/engine/rewrite_publication.py`) reads the candidate through it, has the size gate and the transfer permit
  rule on that candidate before any push, and hands the git owner exactly that candidate to publish through the gate's
  two-step transport seam (`stages/implementing/late_transport.py`): the git owner's fresh reading, then the push,
  with the gate's ending barrier between them, asked whatever the reading answered, so a close or merge landing
  during that reading holds the tick rather than letting a push or a rollback through.
  `late_push.py` keeps the receipt, the debt it settles, the exemption's rotation, and the post-push checkout proof
  the gate's own. `git/base_sync/rewrite_handoffs.py` defines the frozen,
  data-only candidate and landed records
  — the original and rewritten heads and trees, the branch, the base and remote readings, the worktree status, the
  attempt's anchor, pull request, and stage, and the lease-pinned push's outcome, an uncertain answer included — with
  no GitHub client, issue, pinned state, or callback in them. `rewrite_facts.py` reads a candidate and
  `rewrite_transport.py` publishes exactly its rewritten head under its original lease once the checkout and the
  remote, read again, refuse nothing. A head that left the candidate, a tree dirtied or made unreadable, a base ref
  rewound so it no longer contains the tip the replay sits over, or a remote off the anchor refuses before anything is
  sent; a remote already on the candidate is one of those, so a publication that landed is never pushed again, even
  for the same frozen candidate. That claim of a landing is read afresh too, never answered off the reading a
  candidate was prepared with, and it excuses none of the other refusals: a head, tree, or base that fails the fresh
  reading refuses the candidate as it would any other. Before a finish is built on it the workflow proves it at the
  remote with a push of
  the candidate leased to itself, which has nothing to send and which git refuses once somebody has pushed over it; an
  answer that proof lost is settled by reading the remote, and a landing still standing there is announced as found,
  never as a push this tick made. A base that only advanced still publishes. The lease refuses a remote moved after
  that reading, and a push git answered with a failure is classified by reading the remote again: one the remote is
  shown standing on is finished as the publication it was, and anything else the publication sent nothing for or
  could not show landed resets the checkout onto its anchor and parks `auto_base_rebase_push_failed`. The crash
  recovery's retry of a replay nothing published (`workflow/engine/rewrite_retry.py`) crosses the same boundary: it
  reads the candidate the attempt left, in the attempt's own terms and over the remote head its fetch verified
  (`git/base_sync/recovery_push.py`), asks the transfer permit first where a transfer licenses the push -- a refusal
  resets and parks rather than falling through to the cumulative reading, save for a replay the attempt's record names
  with no grant made before the crash, whose refused contribution the base advance changed and which is measured as
  the publication would have measured it -- and publishes and finishes exactly as the ordinary publication does. A push
  the recovery finds already landed (`workflow/engine/rewrite_landed.py`) crosses it too, without a second push: the
  same candidate is read and held to the head the recovery's fetch classified -- a checkout and branch moved together
  onto another head since make nothing, for the next tick to classify -- and `git/base_sync/landed_recovery.py` names
  why the pinned record may not account for the landing -- a foreign mark, a head nothing this attempt vouches for, a
  checkout not provably clean beneath a verdict, a transfer the receipt and debt do not account for -- and a refusal
  parks with HEAD and the anchor kept. Past those the landing is observed where the remote stands, or, for a transfer
  whose permission is still outstanding, proved by the permit-only leased no-op the gate settles that transfer through,
  and either is handed to the same finish. The attempt freezes the base tip its rebase replays onto before git runs
  (`git/base_sync/startup.py`), blank where that ref moved while git ran, and the publication records it beside the
  replay (`pending_auto_base_rebase_rewrite_base`); whether a landed head still stands on that very tip -- standing,
  moved, dropped, unread, or unproven where no tip was recorded -- is `rewrite_facts.py`'s to read
  (`_standing_on_the_remote_base`).
- The finish a landed rewrite still owes sits on the workflow side of that boundary.
  `workflow/engine/rewrite_finish.py` takes the landed record beside the issue it finishes and applies one policy to
  the ordinary publication, a recovered one, and a finish whose announcement is already out: the report debt staged
  and measured on the whole announcement write, a debt with no room parked `auto_base_rebase_unrecorded_debt` with the
  attempt kept, the notice and the `base_rebased` event said once behind the announcement mark, the round reset, a
  human's retry spent, and the route to `workflow:validating` taken only for a head the base has not advanced past
  again -- the announcement, the round reset, and the route all made only once the head's evidence is resolved. A
  landing the pinned record does not account for — one that moved nothing, a publication a guard refused,
  a replay record naming another head, a lag against the base nobody could count — makes nothing, and a head this
  tick pushed nothing for is announced as one found standing. Every write is a guarded commit, so a refused or
  unconfirmed one stops the finish with nothing behind it made. Its post-push, pre-announcement step is where the
  evidence a landed head is routed with is decided (`workflow/engine/rewrite_evidence.py`) and made durable before
  the announcement and the route (`workflow/engine/rewrite_finish_evidence.py`), once the debt is measured to fit:
  current evidence the rewrite moved past invalidated into history,
  and a fresh run or a proved carry recorded as the evidence transaction's pending record, which the finish then
  publishes and settles itself, through the reconciliation's own answer, with the attempt still standing, its proof
  held to the base, and the anchor's landing and base, the issue's requirements, and the configuration read again
  behind every request ahead of the post and of the settlement (`workflow/engine/verification_unguarded.py`), the
  artifact re-read behind the settlement's whole proof, and every write it makes decided on the
  attempt too, so a replacement attempt refuses them (`workflow/engine/rewrite_finish_settlement.py`) -- or nothing
  recorded, and the fresh
  reviewer owes the evidence, a failed run's notice recorded first and put on the pull request once
  (`workflow/engine/rewrite_finish_failures.py`). A decision nobody could take, an evidence write that did not land or
  fit, a failure notice nobody could confirm published, or a recorded transaction whose post or settlement did not
  resolve holds the route with nothing announced and the attempt standing, as does a base that moved after the head
  was counted against it,
  and every route that carries or follows a recorded decision ends in a last word over everything that moves
  (`workflow/engine/rewrite_evidence_proof.py`). The finish that completes it runs the commands again only where no
  run was captured, settles a captured one only once it proves again -- over an artifact an earlier post landed,
  found under its receipt, and routing one already settled with nothing posted or settled again while nothing beside
  it says otherwise -- and abandons it
  unrun, then or after, where something it is bound to -- or the base -- moved
  since: refused for good, its base tip blanked, where the comment has no room
  (`workflow/engine/rewrite_finish_captured.py`). Which run is that captured one is the receipt the finish puts on
  the attempt in the write that records it (`pending_auto_base_rebase_evidence_receipt`), since no announcement mark
  is down yet; it outlives the bounded evidence history, so a run records another road wrote pushed out of it is
  still never run again, and any other pending transaction is that road's, kept as written. The recovery abandons
  the captured run the same way where its snapshot reads the
  landing on another head, or its reset takes the checkout off it (`workflow/engine/rewrite_landing_moved.py`), the
  git owner's reset tail asking every recovery context for that answer (`settles_over_a_reset`), and every recovery
  park that keeps the attempt asking it first to prove a captured run again (`proves_before_a_park`). Evidence a
  finish already settled for the landed head has dormant primitives beside these, which no production finish, recovery,
  or park road asks yet (`workflow/engine/rewrite_finish_readiness.py`): proving it ready again before a route takes it
  -- the base readings that made a continuation excused over a head the base advanced past again, and proved once more
  behind any stop of a write the finish makes after it -- and invalidating it into history whole where anything it is
  bound to moved -- over the comment read afresh or the tick's own copy, the attempt's base tip blanked where the
  invalidation cannot land, so nothing put back revives it. In a finish only the dormant settled-evidence policy
  asks them: a caller selects it by building the finish with `proves_settled` and handing it directly to the
  coordinator (`rewrite_finish.finalizes`) or to its evidence phase (`rewrite_finish_settlement.resolves`, which
  announces, relabels, parks, and retires nothing), and no production road builds such a finish
  (`workflow/engine/rewrite_finish_settled.py`). That phase proves settled evidence
  ready before the route goes on, abandons a continuation's captured transaction before proving the settled evidence
  beside it, takes in a settlement and announcement another finish made beside its answer and invalidates that
  settlement over movement read under it, reads the comment afresh behind every invalidation it lands so a newer
  transaction or another attempt written right behind that write holds the route
  (`workflow/engine/rewrite_finish_rechecks.py`), and has the primitives read and retire more: an announcement of the
  landing taken in and a refused write retried over a fresh reading, the same receipt retired over whatever attempt now
  stands, and movement history has no room for recorded under the evidence's own receipt -- a mark in its handoff's
  place, its whole compact retirement, or a revision spent past it -- however the attempt or the comment moved since
  (`workflow/engine/rewrite_finish_marks.py`, `workflow/engine/rewrite_finish_outranking.py`,
  `workflow/engine/rewrite_finish_unconfirmed.py`). The coordinator held to the policy proves the evidence again
  before every out-of-step hold, unfinishable landing beside a standing attempt, and debt park, ahead of and behind
  the relabel, and behind every stop of the announcement, the park, or the retirement -- a refusal over a record the
  evidence's binding rests on, or one whose comment, its preparation's fresh reading or the strict edit's own, was read
  recording movement under the evidence, a mark, a revision spent past it, or a blank of the attempt's base tip,
  invalidating it however soon that comment is put back -- decides the checkpoint, the event's record, and the park on
  every record the evidence is bound through, puts back an attempt a
  retirement nobody confirmed took before invalidating over it, and announces, relabels, or parks nothing another
  finish of the landing already did (`workflow/engine/rewrite_finish_stops.py`,
  `workflow/engine/rewrite_finish_announced.py`, `workflow/engine/rewrite_finish_writes.py`). Dormant guarded
  recovery operations are built on the readiness
  primitives,
  and no recovery context the workflow builds carries them yet: the settled-aware answer to a landed reset and proof
  before a park that keeps the attempt (`workflow/engine/rewrite_landing_retirement.py`), which retire settled
  evidence whole beside a captured run and refuse the attempt's release where history has no room for it; and the
  reset recorded against captured or settled evidence before git moves the checkout, with every recovery park landed
  through the guarded commit over the comment read afresh and proving what it keeps once more behind its notice
  (`workflow/engine/rewrite_recovery_parks.py`), each an optional answer the git owner transports
  (`records_before_a_reset`, `lands_a_park`). It runs under its caller's issue writer claim.
  The ordinary publication, the recovery's retry, and the recovery of a push already landed all hand their landings
  there, so the three share one post-push policy and one evidence decision -- the recovery's two on the recovery road
  (`rewrite_finish.finishes_the_recovery`), with the reply that brought the attempt back, and over an attempt from
  before its replay record existed the push a retry made is that retry's own. Nothing in `git/base_sync` announces,
  routes, stages report debt, or enters the size gate for a landing any more.
## Observability

Independent audit, analytics, and trajectory logs observe the workflow; an operator-run replay feeds analytics into
Postgres. Two Streamlit pages read the database and trajectory file respectively. The
[observability reference](observability.md) owns these surfaces and the audit log's once-only event read-back;
the [observability module map](architecture/observability-modules.md) owns their package boundaries.

## Summary of "what runs when"

| Work | Trigger and cadence |
|---|---|
| Polling process | `run`, supervised manually or by systemd; repeats every `POLL_INTERVAL` |
| Target checks | Once at startup, before GitHub clients |
| Repository tick | Once per polling pass per configured repository |
| Base refresh, community sweep, skill catalog | Once per repository tick, before issue dispatch |
| Issue handler | Each eligible poll, under shared scheduler caps and an issue writer claim |
| Blocked/umbrella dependency walk | First poll and every `DEPENDENCY_POLL_EVERY_N_TICKS` thereafter |
| Agent subprocess | When a stage needs a new run or an allowed resume; transient, never a daemon |
| Branch publication | After the candidate passes its stage's report, size, and verification gates |
| Scheduler reap and analytics prune | Once per process-wide pass, after repositories drain |
| Self-restart probe | At each tick boundary in a source checkout |

[Agent roles](workflow/roles.md) defines which stages launch each role;
[operations](configuration/operations.md#run-modes) defines launch modes and maintenance-only runs.

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
   │  orchestrator process  (chipping-orchestrator)                       │
   │  ───────────────────────────────────────────────────                 │
   │   cli.main over orchestrator/runtime/                                │
   │     startup: refuse an ALLOWED_ISSUE_AUTHORS naming nobody (exit 1); │
   │              then build per-spec [(spec, GitHubClient), ...] from    │
   │              config.default_repo_specs(); ensure_workflow_labels;    │
   │              build one shared IssueScheduler(global_cap, per_repo)   │
   │     loop every POLL_INTERVAL s:                                      │
   │       1. self-restart check (origin/<ORCHESTRATOR_BASE_BRANCH>       │
   │          moved & touches orchestrator/?; source checkout only)       │
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
   │       worktrees whose handler is still in flight in scheduler,       │
   │       then sync each other one under its issue's writer claim        │
   │       (held by another poller → skipped, retried next tick)          │
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
   │     accepted workers take the issue's host-local writer claim        │
   │       (held by another poller → skipped, retried next tick),         │
   │       call gh._for_worker_thread() + refetch the Issue, then         │
   │       run _process_issue → dispatch by label                         │
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
