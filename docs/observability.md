---
description: >-
  The audit, analytics, and trajectory logs, the database and dashboards built over them, and the parser that reads
  agent usage from CLI stdout.
---
# Observability

The authority of these surfaces and the audit recovery exception are recorded in
[Contracts and invariants](contracts.md#c-12-observation-and-the-audit-recovery-exception).

The orchestrator emits three independent JSONL sinks plus an optional Postgres aggregation target. Workflow correctness
keys off the pinned `<!--orchestrator-state ...-->` JSON comment on the issue (and the workflow label), never off
these. The one read-back is the audit log's: before a base-rewrite finish files its `base_rebased`, it asks the log and
its rotated copies whether that event is already there, so a lost finish files it once, and a log it cannot read holds
that finish until it reads. With no log configured, the attempt's record of that event is taken as the event filed
unless this process still owes it, so it is filed once at most. Every other surface here is observation-only and safe
to truncate, rotate, or delete at any time. The audit log is safe to rotate too, but deleting a rotated copy, or
truncating the log with no copy kept, while a lost finish is still to retry can let that retry file its `base_rebased`
again ([below](#audit-event-log-event_log_path)).

This page is the map over those surfaces. Each one has a reference page of its own, and the section for it below is a
summary that names that page — so a link written against this page still lands beside the material it pointed at:

- **[Event streams](observability/event-streams.md)** — the **audit event log** (`EVENT_LOG_PATH`), an opt-in JSONL
  audit of workflow events written through `GitHubClient.emit_event`, and the **analytics sink**
  (`ANALYTICS_LOG_PATH`), the project-local JSONL of raw metric records the database and dashboard aggregate. Both
  record envelopes, every event kind, the `agent_exit` fields, and the by-age retention prune are documented there.
- **[Agent trajectories](observability/trajectories.md)** — the opt-in, default-off **trajectory sink**
  (`TRAJECTORY_LOG_PATH`) of per-run agent reasoning, the operator workflow that mirrors and prunes that file, and the
  file-backed **trajectory viewer** (`orchestrator/apps/trajectory_dashboard.py`) that renders it as its own Streamlit
  page.
- **[Analytics database](observability/analytics-database.md)** (`analytics-db/`) — the operator-deployed Postgres
  service the analytics sink is replayed into: the compose layout, the endpoint knob, the schema, the sync CLI, and
  the cron shape an unattended replay runs under.
- **[Read model and dashboard](observability/analytics-dashboard.md)** — the connection-injectable read layer over
  those tables (`orchestrator/observability/analytics/query/`) and the Streamlit page composed on top of it
  (`orchestrator/apps/analytics_dashboard.py`), down to the banner every empty or misconfigured case surfaces as.
- **[Usage parser](observability/usage.md)** (`orchestrator/observability/usage/`) — decoder for the agent CLI JSONL
  stdout. It runs once the audit `agent_exit` event has already fired, and `record_agent_exit` writes what it returns
  as the token / cost detail on the analytics `agent_exit` record and the `run_usage` summary on the trajectory
  record.

Which package owns what across these four surfaces — the responsibility each holds and the boundaries between
them — is mapped in
[`architecture/observability-modules.md`](architecture/observability-modules.md); the packages they observe are
mapped on [`architecture/platform-modules.md`](architecture/platform-modules.md) and
[`architecture/workflow-modules.md`](architecture/workflow-modules.md) beside it. The pages above name an owner only
where the behavior under discussion turns on which module a caller reaches. Neither Streamlit page
is one of those owners: both sit beside the tree, at `orchestrator/apps/analytics_dashboard.py` and
`orchestrator/apps/trajectory_dashboard.py`.

## Audit event log (`EVENT_LOG_PATH`)

Summarized here; the reference is
[`observability/event-streams.md`](observability/event-streams.md#audit-event-log-event_log_path).

Opt-in JSONL audit of workflow events, appended through the single `GitHubClient.emit_event` chokepoint and a no-op
when the knob is unset (the default). Every record carries the `ts` / `repo` / `issue` / `event` envelope with
`sort_keys=True` ordering, and `stage` carries the **bare stage tag** (`implementing`, `fixing`, …) rather than the
`workflow:`-prefixed GitHub label — so a grep or a dashboard filter matches on the tag. There is no built-in rotation
and an append failure is downgraded to a warning; pinned GitHub state is what every dispatch decision reads, and the
file -- with the rotated copies logrotate leaves beside it -- is read back only before a base-rewrite finish files its
`base_rebased`, so a lost finish files that event once.
That page lists every emitted kind and its extras, the `agent_spawn` / `agent_exit` fields, and the opt-in
`skill_triggered` event.

## Analytics sink (`ANALYTICS_LOG_PATH`)

Summarized here; the reference is
[`observability/event-streams.md`](observability/event-streams.md#analytics-sink-analytics_log_path).

Project-local JSONL of raw metric records — the raw foundation layer the Postgres aggregation below replays — opting
in and out independently of the audit log via `ANALYTICS_LOG_PATH` / `ANALYTICS_RETENTION_DAYS`. It shares the audit
sink's envelope and bare-stage-tag spelling, so `WHERE stage = 'validating'` is the form that matches both here and in
the Postgres column the sync loads it into. Five kinds are written today — `stage_enter`, `stage_evaluation`,
[`agent_exit`](observability/event-streams.md#agent_exit-records),
[`repo_skill_catalog`](observability/event-streams.md#repo_skill_catalog-records), and the one record each candidate
of the daily terminal-artifact maintenance pass earns,
[`terminal_artifact_cleanup`](observability/event-streams.md#terminal_artifact_cleanup-records) (analytics only: that
pass writes no workflow state, so it has no audit twin) — beside three families written to
this sink and the audit log alike, so the JSONL copy answers offline what the database answers: human-wait
transitions (`park_awaiting_human`), the per-issue lifetime ledger's
[`agent_run_budget`](observability/event-streams.md#agent-run-budget-records-both-sinks) transitions, and the late
size gate's eight [late-split families](observability/event-streams.md#late-split-records-both-sinks). That page
carries each one's fields, the opt-in `TRACK_SKILL_TRIGGERS` skill evidence on `agent_exit`, the
[session-aware adoption model](observability/event-streams.md#session-aware-skill-adoption) built over it, and the
once-per-tick retention prune that bounds the file.

## Trajectory sink (`TRAJECTORY_LOG_PATH`)

Summarized here; the reference is
[`observability/trajectories.md`](observability/trajectories.md#trajectory-sink-trajectory_log_path).

Opt-in, **default-off** sibling sink holding one `agent_trajectory` record per tracked run: the ordered timeline of
tool calls / results interleaved with the assistant / user text turns, the offered tools and skills, a denormalized
`run_usage` summary, a codex run's per-item accounting, and the final output. It is deliberately kept out of the
analytics sink, its Postgres sync, and
the analytics dashboard, because the free-text bodies do not belong in the numeric rollup. `record_agent_exit`
produces it from the same stdout the usage parser reads, behind its own fail-open guard, so a trajectory failure can
never cost the baseline `agent_exit` record. Every free-text field is redacted and head/tail truncated and the whole
record is budget-bounded — but **redaction is not anonymization**: issue content, quoted source, diffs, and the
agent's own text turns survive in cleartext (a run's hidden reasoning payloads never enter the record), so scope the
file like the repositories it describes. That page carries the record shape, the join keys back to the numeric sinks,
the caps, the privacy contract, and the file-backed trajectory viewer that reads it.

### Trajectory operator workflow

Summarized here; the reference is
[`observability/trajectories.md`](observability/trajectories.md#trajectory-operator-workflow).

Trajectories are file-backed only — there is no trajectory equivalent of the analytics sync CLI, and the Postgres
schema never ingests their bodies. To browse them on another host, mirror the JSONL file (a locked, key-restricted
`rsync` over SSH) and point the viewer at the copy; to bound it, drive `prune_trajectory_records` yourself, since the
polling loop does not call it. The prune helper runs in the installed pipx environment and reads the installed
configuration. That page carries the receiver setup, the `authorized_keys` restriction, the sync and
prune cron entries, and the mirror-versus-archive decision retention forces.

## Analytics database (`analytics-db/`)

Summarized here; the reference is
[`observability/analytics-database.md`](observability/analytics-database.md).

Operator-deployed local Postgres service that is the aggregation target for the analytics sink, reached through one
libpq URL (`ANALYTICS_DB_URL`) so moving it off-host later is a one-line repoint. The compose service pins its port to
`127.0.0.1` and keeps its data on a gitignored host bind; the schema is an `analytics_events` table with an `extras
JSONB` catch-all that ingests a new record field with no DDL, a `content_hash` unique index that makes a repeated
replay idempotent, the `analytics_daily_rollup` materialized view the window-bounded dashboard widgets read, and the
`analytics_agent_runs` view over `agent_exit` rows. Each run's cost is stored by basis beside its completeness and its
non-overlapping token total, read through the usage parser's own readers, so the views and rollup sum each basis
apart and keep unpriced, unattributed, and unknown-total runs visible. The JSONL→Postgres replay and the CLI an
operator drives it through are owned by `orchestrator/observability/analytics/sync/` and are NOT wired into the
polling tick, so orchestrator correctness never depends on database availability. That page carries the compose
commands, the full column and index inventory, the batching / dedup / malformed-line contract, and the
credential-stripped operator feedback.

### Operator workflow

Summarized here; the reference is
[`analytics-database.md`](observability/analytics-database.md#operator-workflow).

Replay cadence is operator-chosen: the JSONL sink is already the authoritative analytics surface on disk.
The sync runs directly from the installed pipx environment, including its runtime Postgres driver, and reads
`~/.config/chipping-orchestrator/.env`. The reference above carries launch commands and an hourly `flock`-guarded
cron example. `--log-path` and `--db-url` override the settings for one-off replays of archived JSONL files.

### Read model (`orchestrator/observability/analytics/query/`)

Summarized here; the reference is
[`analytics-dashboard.md`](observability/analytics-dashboard.md#read-model-orchestratorobservabilityanalyticsquery).

Thin, testable data-access layer over `analytics_events`, the `analytics_agent_runs` view, and the
`analytics_daily_rollup` materialized view. Window-bounded aggregates read the rollup; per-row drill-downs and widgets
the rollup cannot reconstruct exactly stay on the base table or the agent-run view. Nothing here imports Streamlit, so
the read path can be wired into any UI. An unset `ANALYTICS_DB_URL` short-circuits every reader to an empty result
with no connection attempt, mirroring the sync's no-op contract, and every failure surfaces as one
`AnalyticsReadError`. Every read interprets only what the current producers write, so a field no record reported
stays unknown — a session that reported no offered skills joins no adoption denominator — while a NULL column, an
unpriced cost, and a malformed `extras` blob keep their current readings. That page carries all twenty reads, the owner
each is defined on, the typed request and filter contract they share, and the thread-local connection cache a caller
reuses a socket through.

### Dashboard (`orchestrator/apps/analytics_dashboard.py`)

Summarized here; the reference is
[`analytics-dashboard.md`](observability/analytics-dashboard.md#dashboard-orchestratorappsanalytics_dashboardpy).

Streamlit app over that read model, available as a source-checkout developer tool with the optional `dashboard`
dependency group. pipx installs the polling runtime without these optional dependencies. Setup and launch commands
are in the [developer guide](development.md#analytics-sync-and-dashboard).

The page is composed entirely from owners under `observability/dashboard/`, stages its 16 widget reads into two cached
waves around the chrome it draws between them, and never raises at the operator — every missing-data or
misconfiguration case surfaces as a labeled banner. The dashboard process is independent of the polling tick: it opens
no GitHub session, writes no Postgres row, and can be deployed off-host by repointing `ANALYTICS_DB_URL`. Its topbar,
headline tiles, sparklines, and usage chart name every amount's basis — an AGY-only one a Gemini API token estimate, a
mixed one blended with its parts beside it — never pass an incomplete subtotal or an amount of unknown basis off as
complete spend, keep those qualifications on every move against the window before, and count each token once. The
costliest-issues table words each issue's cost the same way and is drawn in the order SQL ranked it, ahead of its cap,
on every amount the issue's runs state — a subtotal at its known part, an issue stating none last and worded unpriced
rather than free — and the recent-runs listing and per-issue drill-down word each run's stored cost, an estimate's
rate dates beside it, never repriced from its tokens. The stage, review-round, and repository bars and the backend
cards word each group's spend the same way: its basis and any shortfall under a bar's label or beneath a card's spend,
a blended amount's parts on hover, in the note closing each chart panel, and on the card, and a group stating no
amount worded unpriced, no usage, or cost unknown rather than drawn as a zero. The cache and non-cache segments of a
stage or review-round bar split its stated amount by the runs' declared token share — an allocation, never a measured
cache charge — leaving the amount of a run whose token total is unknown unsplit, and a backend's cost per token, cost
per run, and cache share are qualified, or shown as unavailable, wherever the cost or token total behind them falls
short. That page carries the module layout, the caching and fan-out contracts, the body layout top to bottom, the
chart builders and theme owners, and the empty / error banner inventory.

## Usage parser (`orchestrator/observability/usage/`)

Summarized here; the reference is [`observability/usage.md`](observability/usage.md).

Pure-Python, dependency-free decoder for the agent CLI's JSONL stdout, producing a `UsageMetrics` dataclass — backend,
distinct model(s), turn count, the five token totals, `cost_usd`, and a `cost_source` tag of `reported` / `estimated`
/ `unknown-price` / `no-usage`. A `total_cost_usd` the CLI reported itself always wins; otherwise the parser estimates
from an active row of the dated first-party API price catalogue, matched only by exact model ID, documented alias, or
published snapshot, and a model with no active row — unknown, or catalogued but still dormant — yields `unknown-price`
with `cost_usd=None` rather than a guess. A Claude estimate prices each API message on its own, each cache write at
the lifetime its usage block reports and Haiku 5.5's tier on that message's own prompt, and a write of no reported
lifetime, a block whose lifetime split contradicts its aggregate, or a tiered row of no established prompt is unpriced
too. Beside those fields the run records its cost
evidence — monetary contributions by basis (`cli-reported`, or a provider's token-only API list-price estimate) and
their completeness — and its token evidence, which counters were observed and whether the cache counters sit inside
the input, with shared readers that fold costs per basis and total tokens without counting one twice. Malformed JSONL
lines are skipped, so one bad line never invalidates a stream. Two siblings ride the same
stream under the same contract: the opt-in skill-trigger extractor behind `TRACK_SKILL_TRIGGERS`, and the trajectory
classifier that reconstructs a run's timeline. That page carries the module layout, the per-backend parsers and their
dispatcher, the cost-precedence rule, the per-issue verdict line a terminal posts, and the evidence model both
siblings return. The per-issue counters that verdict reads are not these sinks: each invoked exit is counted on the
pinned comment once, by the accounting checkpoint the tracked spawn asks as the run returns, a held or killed run's
included, and an exit no checkpoint landed is never reconstructed from the analytics or audit records, which stay
observational.

## Summary of "what runs when"

- `retention.prune_with_retention_logging` (function call) — trigger: end of each `runtime.ticks.run_tick` after every
  configured repo drains; cadence: once per tick (process-wide, not per-repo); no-op when the sink is disabled or
  `ANALYTICS_RETENTION_DAYS <= 0`.
- `scheduler.reap` (method call) — trigger: end of each `runtime.ticks.run_tick` after every configured repo drains,
  immediately before the analytics prune; cadence: exactly once per polling pass regardless of repo count; nonblocking
  drain of any worker completions since the last poll. `_dispatch_via_scheduler` deliberately does NOT call `reap`.
