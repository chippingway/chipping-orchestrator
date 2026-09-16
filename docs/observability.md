# Observability

The orchestrator emits three independent JSONL sinks plus an optional Postgres aggregation target. None are read by
the polling tick — workflow correctness keys off the pinned `<!--orchestrator-state ...-->` JSON comment on the issue
(and the workflow label). Every observability surface here is observation-only and safe to truncate, rotate, or delete
at any time.

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
and an append failure is downgraded to a warning; pinned GitHub state, never this file, is what the tick reads back.
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
polling loop does not call it. That page carries the receiver setup, the `authorized_keys` restriction, the sync and
prune cron entries, and the mirror-versus-archive decision retention forces.

## Analytics database (`analytics-db/`)

Summarized here; the reference is
[`observability/analytics-database.md`](observability/analytics-database.md).

Operator-deployed local Postgres service that is the aggregation target for the analytics sink, reached through one
libpq URL (`ANALYTICS_DB_URL`) so moving it off-host later is a one-line repoint. The compose service pins its port to
`127.0.0.1` and keeps its data on a gitignored host bind; the schema is an `analytics_events` table with an `extras
JSONB` catch-all that ingests a new record field with no DDL, a `content_hash` unique index that makes a repeated
replay idempotent, the `analytics_daily_rollup` materialized view the window-bounded dashboard widgets read, and the
`analytics_agent_runs` view over `agent_exit` rows. The JSONL→Postgres replay and the CLI an operator drives it
through are owned by `orchestrator/observability/analytics/sync/` and are NOT wired into the polling tick, so
orchestrator correctness never depends on database availability. That page carries the compose commands, the full
column and index inventory, the batching / dedup / malformed-line contract, and the credential-stripped operator
feedback.

### Operator workflow

Summarized here; the reference is
[`analytics-database.md`](observability/analytics-database.md#operator-workflow).

Run `uv run python -m orchestrator.observability.analytics.sync.cli` on whatever cadence you prefer — the JSONL sink
is already the authoritative analytics surface on disk, so the replay cadence is operator-chosen rather than pinned.
`--log-path` and `--db-url` override the env values for one-off replays of archived JSONL files. That page carries the
hourly `flock`-guarded `cron` entry for an unattended deployment and why each part of it is spelled the way it is.

### Read model (`orchestrator/observability/analytics/query/`)

Summarized here; the reference is
[`analytics-dashboard.md`](observability/analytics-dashboard.md#read-model-orchestratorobservabilityanalyticsquery).

Thin, testable data-access layer over `analytics_events`, the `analytics_agent_runs` view, and the
`analytics_daily_rollup` materialized view. Window-bounded aggregates read the rollup; per-row drill-downs and widgets
the rollup cannot reconstruct exactly stay on the base table or the agent-run view. Nothing here imports Streamlit, so
the read path can be wired into any UI. An unset `ANALYTICS_DB_URL` short-circuits every reader to an empty result
with no connection attempt, mirroring the sync's no-op contract, and every failure surfaces as one
`AnalyticsReadError`. That page carries all twenty reads, the owner each is defined on, the typed request and filter
contract they share, and the thread-local connection cache a caller reuses a socket through.

### Dashboard (`orchestrator/apps/analytics_dashboard.py`)

Summarized here; the reference is
[`analytics-dashboard.md`](observability/analytics-dashboard.md#dashboard-orchestratorappsanalytics_dashboardpy).

Streamlit app over that read model, opt-in via the `dashboard` dependency group so the default `uv sync --locked`
keeps installing only the polling runtime plus the dev tools:

```sh
uv sync --group dashboard                                       # install streamlit + plotly alongside the runtime
uv run streamlit run orchestrator/apps/analytics_dashboard.py   # launches a local browser tab
```

The page is composed entirely from owners under `observability/dashboard/`, stages its 16 widget reads into two cached
waves around the chrome it draws between them, and never raises at the operator — every missing-data or
misconfiguration case surfaces as a labeled banner. The dashboard process is independent of the polling tick: it opens
no GitHub session, writes no Postgres row, and can be deployed off-host by repointing `ANALYTICS_DB_URL`. That page
carries the module layout, the caching and fan-out contracts, the body layout top to bottom, the chart builders and
theme owners, and the empty / error banner inventory.

## Usage parser (`orchestrator/observability/usage/`)

Summarized here; the reference is [`observability/usage.md`](observability/usage.md).

Pure-Python, dependency-free decoder for the agent CLI's JSONL stdout, producing a `UsageMetrics` dataclass — backend,
distinct model(s), turn count, the five token totals, `cost_usd`, and a `cost_source` tag of `reported` / `estimated`
/ `unknown-price` / `no-usage`. A `total_cost_usd` the CLI reported itself always wins; otherwise the parser estimates
from the first-party price tables, and an unpriced SKU yields `unknown-price` with `cost_usd=None` rather than a
guess. Malformed JSONL lines are skipped, so one bad line never invalidates a stream. Two siblings ride the same
stream under the same contract: the opt-in skill-trigger extractor behind `TRACK_SKILL_TRIGGERS`, and the trajectory
classifier that reconstructs a run's timeline. That page carries the module layout, the per-backend parsers and their
dispatcher, the cost-precedence rule, the per-issue verdict line a terminal posts, and the evidence model both
siblings return.

## Summary of "what runs when"

- `retention.prune_with_retention_logging` (function call) — trigger: end of each `runtime.ticks.run_tick` after every
  configured repo drains; cadence: once per tick (process-wide, not per-repo); no-op when the sink is disabled or
  `ANALYTICS_RETENTION_DAYS <= 0`.
- `scheduler.reap` (method call) — trigger: end of each `runtime.ticks.run_tick` after every configured repo drains,
  immediately before the analytics prune; cadence: exactly once per polling pass regardless of repo count; nonblocking
  drain of any worker completions since the last poll. `_dispatch_via_scheduler` deliberately does NOT call `reap`.
