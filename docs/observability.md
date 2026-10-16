---
description: >-
  The audit, analytics, and trajectory logs, the database and dashboards built over them, and the parser that reads
  agent usage from CLI stdout.
---
# Observability

Three independent JSONL sinks and an optional Postgres aggregation target record what the orchestrator did and what
its agent runs cost. GitHub workflow labels and pinned state remain the source of workflow progress; the audit log's
recovery read-back is described in its section below.

The sections below connect each surface to its reference. Package responsibilities and import boundaries live in
[observability modules](architecture/observability-modules.md); sink paths, retention windows, and database settings
live in [observability settings](configuration/observability.md).

## Audit event log (`EVENT_LOG_PATH`)

The opt-in audit log records workflow events through `GitHubClient.emit_event`; an unset path disables it. It also
supports once-only filing of a recovered base rewrite's `base_rebased` event by reading the log and rotated copies.
The [audit-log reference](observability/event-streams.md#audit-event-log-event_log_path) owns the envelope, event
inventory, read-back behavior, and rotation contract.

## Analytics sink (`ANALYTICS_LOG_PATH`)

The independent analytics JSONL sink records stage, agent, budget, and cleanup metrics for offline analysis and
Postgres replay. Its [reference](observability/event-streams.md#analytics-sink-analytics_log_path) owns record fields,
skill-adoption semantics, and the once-per-tick retention prune.

## Trajectory sink (`TRAJECTORY_LOG_PATH`)

The opt-in, default-off trajectory sink records each run's tool calls, visible text, usage, and final output. It stays
separate from numeric analytics and is never synced to Postgres. Redaction and truncation bound records but leave
repository content in cleartext. The
[trajectory reference](observability/trajectories.md#trajectory-sink-trajectory_log_path)
owns the schema, privacy contract, budgets, and file-backed viewer.

### Trajectory operator workflow

Operators mirror trajectory JSONL for off-host viewing and schedule pruning themselves; the polling loop does not
prune this sink. The [trajectory runbook](observability/trajectories.md#trajectory-operator-workflow) owns receiver
setup, restricted SSH access, cron commands, and mirror-versus-archive retention.

## Analytics database (`analytics-db/`)

An operator-deployed Postgres service aggregates analytics JSONL through an explicitly run replay. `ANALYTICS_DB_URL`
selects its endpoint; the polling process never depends on its availability. The
[database reference](observability/analytics-database.md) owns deployment, schema, and replay behavior.

### Operator workflow

Run the sync CLI from the installed environment or schedule it independently. Replaying a file is idempotent, and
one-off path and URL overrides support archived logs. The
[sync runbook](observability/analytics-database.md#operator-workflow) owns commands and the guarded cron example.

### Read model (`orchestrator/observability/analytics/query/`)

The read model serves typed analytics results without importing Streamlit. An unset database URL returns empty data;
read failures surface as `AnalyticsReadError`. The
[read-model reference](observability/analytics-dashboard.md#read-model-orchestratorobservabilityanalyticsquery)
owns queries, filters, connection reuse, and rollup selection.

### Dashboard (`orchestrator/apps/analytics_dashboard.py`)

The independent Streamlit page draws analytics from that read model and reports empty or misconfigured states as
banners. The [dashboard reference](observability/analytics-dashboard.md#dashboard-orchestratorappsanalytics_dashboardpy)
owns layout and caching; the [developer guide](development.md#analytics-sync-and-dashboard) owns setup and launch.

## Usage parser (`orchestrator/observability/usage/`)

The dependency-free parser turns agent CLI JSONL into token and cost metrics, skill evidence, and trajectories. The
[usage reference](observability/usage.md) owns provider decoding, cost precedence, result types, and historical
accounting limits.

## Summary of "what runs when"

Recording follows workflow and agent events. Scheduler completion reaping and analytics retention run once after all
repositories drain; database replay and trajectory pruning are operator-scheduled. The process-wide
[cadence summary](architecture.md#summary-of-what-runs-when) connects these tasks to the polling loop.
