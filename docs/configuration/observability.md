# Observability configuration

The settings that turn each observability sink on and point it somewhere: the audit event log, the analytics JSONL
sink and the Postgres database it feeds, the trajectory sink, skill-trigger tracking, and the dashboard read mode.
Every other setting is in [`../configuration.md`](../configuration.md); what the sinks record is in
[`../observability/event-streams.md`](../observability/event-streams.md) and
[`../observability/trajectories.md`](../observability/trajectories.md), and how the database, dashboards, and usage
parser read them back is in [`../observability/analytics-database.md`](../observability/analytics-database.md),
[`../observability/analytics-dashboard.md`](../observability/analytics-dashboard.md), and
[`../observability/usage.md`](../observability/usage.md), which [`../observability.md`](../observability.md) maps.

## Settings

- `EVENT_LOG_PATH` — default _(unset)_. optional JSONL audit sink, one event per line, no built-in rotation. See
  [`event-streams.md#audit-event-log`](../observability/event-streams.md#audit-event-log-event_log_path).
- `ANALYTICS_LOG_PATH` — default `LOG_DIR/analytics.jsonl`. project-local analytics JSONL sink. Set to empty / `off` /
  `disabled` / `none` to disable. Which kinds land here — the per-tick and per-run records, the one bounded record
  each candidate of the daily terminal-artifact maintenance pass earns, and the three families
  written to this sink and the audit log alike (human-wait transitions, agent-run budget, and late-split events) — is
  inventoried on
  [`event-streams.md#analytics-sink`](../observability/event-streams.md#analytics-sink-analytics_log_path) rather than
  repeated here, so the list has one home as it grows. Two of them answer different questions and are not to be read
  as one: a `stage_evaluation` with `result="ok"` says the stage handler completed without raising, not that the
  issue moved — a handler that parked the issue for a human evaluates `ok` — while a `park_awaiting_human` record
  says the workflow is now waiting on a human and why. A park is a workflow-progress record, not an execution error.
- `ANALYTICS_RETENTION_DAYS` — default `90`. retention window for `ANALYTICS_LOG_PATH`. The polling loop calls
  `retention.prune_with_retention_logging()` once per tick. Set to `0` (or any non-positive value) to keep raw data
  indefinitely.
- `ANALYTICS_DB_URL` — default _(unset)_. libpq connection string for the analytics Postgres service in
  [`../../analytics-db/compose.yml`](../../analytics-db/compose.yml). NOT read by the polling loop — orchestrator
  correctness does not depend on database availability. Empty / `off` / `disabled` / `none` disables both the sync CLI
  and dashboard reads. See
  [`analytics-database.md`](../observability/analytics-database.md).
- `TRAJECTORY_LOG_PATH` — default _(unset, off)_. opt-in path switch for the trajectory sink — an independent JSONL
  file for per-run agent reasoning trajectories, separate from `ANALYTICS_LOG_PATH`. Defaults off: unset / empty / `off`
  / `disabled` / `none` (case-insensitive) all disable it; any other value is the explicit opt-in path. When enabled,
  `record_agent_exit` writes one redacted, head/tail-truncated `agent_trajectory` record per tracked run (the
  orchestrator prompt lands as `user_input`); when off, no trajectory work runs and the `agent_exit` record is
  unchanged. Never touches `ANALYTICS_LOG_PATH`, the analytics Postgres sync, or the analytics dashboard. Local
  filesystem only and observation-only — the polling loop never reads it back, so the file is safe to delete without
  affecting workflow state. A dedicated Streamlit viewer (`orchestrator/apps/trajectory_dashboard.py`, launched with
  `uv run streamlit run orchestrator/apps/trajectory_dashboard.py`) reads this JSONL file directly — no Postgres or sync
  — when you want to browse the recorded trajectories. **Privacy:** redaction masks only secret-shaped env values (and
  the GitHub token), **not** issue/repo content, so an enabled trajectory file can carry issue titles/bodies, quoted
  source, and the agent's own text turns in cleartext; scope its permissions accordingly. See
  [`trajectories.md#trajectory-sink`](../observability/trajectories.md#trajectory-sink-trajectory_log_path).
- `TRAJECTORY_RETENTION_DAYS` — default `90`. retention window for `TRAJECTORY_LOG_PATH`, same semantics as
  `ANALYTICS_RETENTION_DAYS`: `prune_trajectory_records()` removes older records and `0` (or any non-positive value)
  keeps trajectories indefinitely. Parsed from `.env`, but not yet called from the polling loop, so it affects the file
  only when an operator-driven prune process runs; do not overlap an external prune with live trajectory appends. See
  the trajectory cron examples in
  [`trajectories.md`](../observability/trajectories.md#trajectory-operator-workflow).
- `TRACK_SKILL_TRIGGERS` — default _(unset, off)_. opt-in switch for skill-trigger tracking. `1` / `true` / `on` /
  `yes` (case-insensitive) makes `record_agent_exit` parse the agent's triggered skills and fold `skills_triggered` /
  `skills_triggered_count` / `skills_available`, the per-load evidence tier `skills_evidence` (`confirmed` for a claude
  `Skill` call, `inferred` for a codex direct `SKILL.md` read), and the incidental pair `skills_incidental` /
  `skills_incidental_count` (path-only codex references — `git diff` / `git status` / `rg`, a redirect target, any
  non-reader command — recorded independently of loads and kept out of the trigger fields/events) into each
  `agent_exit` record. It also makes `_run_agent_tracked` emit one `skill_triggered` audit event per distinct triggered
  skill to `EVENT_LOG_PATH` (when that sink is set); incidental references never emit one. Default off so a default
  install's records and audit log stay shape-compatible with today's, and needs no Postgres DDL — the `extras JSONB`
  column absorbs the new fields. Both backends' triggered-skill shapes are now pinned against captured streams (claude
  `Skill` tool-use blocks; codex `skills/<name>/SKILL.md` reads, a heuristic file-open signal — see
  [`usage.md`](../observability/usage.md)). The offered-skills set (`skills_available`) is read from claude's
  `system`/`init` frame `skills` array (confirmed against a real stream
  capture); codex's stream carries no such frame, so it is backfilled out-of-band from the filesystem via
  `skills.discovery.discover_local_skill_sources(cwd)` (a scan of the run's worktree `.agents/skills` /
  `.claude/skills` roots plus the global `$CODEX_HOME/skills`), whose per-name `project` / `user` / `harness` source
  level is recorded beside the names as `skill_levels` — dropped for a claude run, whose stream names no source
  directory to classify. Both per-skill read models file a cell under that level as well as the name, and both first
  fill a name no recorded map covers from the repository's own `repo_skill_catalog`, so a claude run's load — and,
  for adoption, the incidental reference and the historical offer beside it — of a name the repository offers at
  exactly one level lands in that level's cell instead of an `unknown` one beside it. Only an uncatalogued or
  two-level name keeps `unknown`, and a level the record itself carried is never overwritten. Both skill tables render
  that level as a sortable `Level` column of their own.
  Once on, the dashboard's "Skill adoption" panel opens on a collapsed invocation-level diagnostic carrying the
  per-role/backend trigger rate (`skill_reads.get_skill_trigger_rates`) and the per-skill trigger matrix
  (`skill_reads.get_skill_trigger_matrix`) pairing each repo's offered-skill catalog with the skills its runs
  triggered, and reports per-session adoption (`skill_reads.get_skill_adoption`, under
  `observability/analytics/query/`) beneath it — how many logical sessions had each skill available and how many
  loaded it, with incidental references kept as a separate column that never raises the rate — split into a collapsed
  section per source level (project, user, harness, plus one for the cells no record classified), all over the
  accumulated fields. The `skills_evidence` tier carries only the emitted `confirmed` /
  `inferred` load values; the *incidental* bucket and the read-side *legacy* availability inference (a load whose
  session reported no `skills_available` metadata) are described alongside the per-session adoption semantics in
  [`event-streams.md#session-aware-skill-adoption`](../observability/event-streams.md#session-aware-skill-adoption).
  See also [`event-streams.md#agent_exit-records`](../observability/event-streams.md#agent_exit-records) and the
  [audit event log](../observability/event-streams.md#audit-event-log-event_log_path).
- `DASHBOARD_PARALLEL_READS` — default _(unset, off)_. opt-in switch for the Streamlit dashboard's parallel read
  fan-out. `1` / `true` / `on` / `yes` (case-insensitive) flips the dashboard's widget reads from sequential to a
  `ThreadPoolExecutor` (eight workers). Parsed once per Streamlit process, when the page's read-mode owner is first
  imported; the polling loop never reads it.

`ANALYTICS_LOG_PATH`, `ANALYTICS_RETENTION_DAYS`, `ANALYTICS_DB_URL`, `TRACK_SKILL_TRIGGERS`, `TRAJECTORY_LOG_PATH`, and
`TRAJECTORY_RETENTION_DAYS` are parsed by `orchestrator/observability/analytics/environment.py` and bound on
`orchestrator/observability/analytics/settings.py`, the one holder every analytics owner reads them off (the analytics
surfaces own their own configuration rather than the `orchestrator/config` resolver). `EVENT_LOG_PATH` is resolved by
the `orchestrator/config` resolver and bound on the config package because the audit event log is a general-purpose
audit surface rather than analytics-specific.

## Analytics dashboard quickstart

The pipeline is opt-in and layered: the orchestrator writes JSONL (`ANALYTICS_LOG_PATH`), a local Postgres aggregates it
(`ANALYTICS_DB_URL`), and Streamlit reads from Postgres. Each layer is independent — the polling loop never touches
Postgres or Streamlit, so deferring or disabling the dashboard never affects workflow correctness.

1. **Confirm the JSONL sink is producing records.** `ANALYTICS_LOG_PATH` defaults to `logs/analytics.jsonl`.
   `wc -l logs/analytics.jsonl` and `tail -1 logs/analytics.jsonl | python -m json.tool` sanity-check it.
2. **Start the local Postgres service.** For a new database, the operator first creates `analytics-db/data/`;
   an existing deployment must keep its data directory. Start the service from `analytics-db/` with
   `docker compose up -d`. The init script
   ([`../../analytics-db/init/01-schema.sql`](../../analytics-db/init/01-schema.sql)) creates the `analytics_events`
   table on first start; the data volume lives at `analytics-db/data/` (gitignored). The port binding is pinned to
   `127.0.0.1` and credentials default to `orchestrator` / `orchestrator`; override `POSTGRES_PASSWORD` (and any
   other field) in `analytics-db/.env` before exposing the port off-host or storing real data. Missing bind sources
   fail startup. After moving the checkout, follow the
   [container recreation steps](../observability/analytics-database.md#moving-or-renaming-the-checkout).
3. **Point the orchestrator at the database.** Set `ANALYTICS_DB_URL` in `.env`:

   ```sh
   ANALYTICS_DB_URL=postgresql://orchestrator:orchestrator@127.0.0.1:5432/orchestrator_analytics
   ```

   Putting the database password in `.env` is acceptable — the URL is the only credential, it is scoped to local-only
   Postgres, and never grants write access to GitHub. The polling loop does not re-read this setting.
4. **Populate Postgres from JSONL.** Run the sync on demand:

   ```sh
   uv run python -m orchestrator.observability.analytics.sync.cli
   ```

   Inserts dedupe by `content_hash`, so re-running is idempotent. No-op when `ANALYTICS_DB_URL` is unset/disabled,
   `ANALYTICS_LOG_PATH` is explicitly disabled, or the JSONL file is absent. Schedule on whatever cadence you prefer;
   see [`analytics-database.md#operator-workflow`](../observability/analytics-database.md#operator-workflow) for a
   sample `cron` entry.
5. **Launch the dashboard.** Install the optional `dashboard` group once, then run Streamlit:

   ```sh
   uv sync --group dashboard
   uv run streamlit run orchestrator/apps/analytics_dashboard.py
   ```

   Streamlit prints a `http://localhost:8501` URL. The dashboard is independent of the polling tick and can be killed
   and relaunched without affecting workflow progress. Re-run step 4 to pick up new records.

   `orchestrator/apps/analytics_dashboard.py` is the only entrypoint the page has, and the one to name in shell
   history, scripts, and service units.

See [`analytics-database.md`](../observability/analytics-database.md) for the schema and the sync internals, and
[`analytics-dashboard.md`](../observability/analytics-dashboard.md) for the read-model split, the dashboard layout,
and the in-app empty / error banners.
