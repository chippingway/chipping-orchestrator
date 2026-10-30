# Analytics database

The local Postgres service (`analytics-db/`) the
[analytics sink](event-streams.md#analytics-sink-analytics_log_path) is replayed into: the compose service and schema
an operator deploys, the endpoint the replay dials, the sync CLI that drives it, and the feedback and cron shape
around it. The JSONL→Postgres replay and the CLI over it are both owned by
`orchestrator/observability/analytics/sync/` and are NOT wired into the polling tick — orchestrator correctness must
not depend on database availability. The JSONL file on disk stays the authoritative analytics surface; the database
is for aggregation and reporting.

The read model over these tables and the Streamlit dashboard above it are on
[`analytics-dashboard.md`](analytics-dashboard.md). Where the sync path sits in the package tree, and what the
package holding it is responsible for, is in
[`architecture/observability-modules.md`](../architecture/observability-modules.md); the knobs themselves are in
[`configuration/observability.md`](../configuration/observability.md).

## Service layout

If you installed with pipx, check the installed version with
`pipx runpip chipping-orchestrator show chipping-orchestrator`. Use the matching `vX.Y.Z` tag (including any prerelease
suffix) when cloning the repository or downloading `analytics-db/compose.yml`, `analytics-db/init/01-schema.sql`, and
`analytics-db/.env.example`, preserving that directory layout, before running the commands below. The installed sync
and database schema must agree on columns, so use files from that release.

[`../../analytics-db/compose.yml`](../../analytics-db/compose.yml) brings up a single `postgres:16` container with
the data directory on a host bind (`./data`, gitignored) and the init directory mounted read-only. The port binding is
pinned to `127.0.0.1` so the database is unreachable off-host regardless of firewall configuration; re-binding to
`0.0.0.0` is intentionally a code change rather than an env-var change. Credentials default to `orchestrator` /
`orchestrator` and are overridable via `analytics-db/.env` (`POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` /
`POSTGRES_PORT`). To customize these values, copy [`.env.example`](../../analytics-db/.env.example) to
`analytics-db/.env` and edit it before starting the service. `docker compose` reads `.env` from the compose-file
directory, not the orchestrator root.

Both binds set `create_host_path: false`: a missing source fails startup instead of silently creating an empty
directory. On a first deployment, the operator must create `analytics-db/data/` before starting the service. For an
existing deployment, retain the existing data directory; do not create a replacement to bypass a missing-source error.

```sh
cd analytics-db
mkdir -p data                         # operator setup for a new database only
docker compose up -d                  # start the local service (data lives in ./data, gitignored)
docker compose down                   # stop the container; data on the ./data bind mount is preserved
# `down -v` does not remove the host bind directory.
docker compose down && rm -rf ./data  # stop and wipe history; repeat `mkdir -p data` before the next `up`
```

To apply or re-apply the schema against an already-running compose service:

```sh
cd analytics-db
docker compose exec -T analytics-db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/01-schema.sql'
```

### Moving or renaming the checkout

Docker stores absolute bind-source paths in each container. Moving the checkout does not update them, and
`restart: unless-stopped` keeps using the saved paths. A container created with short volume syntax can recreate
missing directories at its original checkout path and initialize an empty database without the schema scripts.
Changing the Compose file takes effect only after the container is recreated.

Stop the service before moving an existing deployment. The operator must preserve its data directory and `.env` at
the destination. From the destination checkout, recreate the container to resolve the binds there:

```sh
cd analytics-db
docker compose up -d --force-recreate --wait analytics-db
docker inspect orchestrator-analytics-db --format '{{json .Mounts}}'
```

Check that both sources name the destination checkout. `docker compose restart` does not update the mount paths.
If Docker has already recreated directories at a former path, take a logical backup of the running cluster with
`pg_dumpall` before recreating the container, then back up and verify the database at the destination. Leave both host
data directories intact until the operator has reconciled the databases.

## Endpoint shape

The sync reads a single libpq URL — `ANALYTICS_DB_URL` (default unset, example
`postgresql://orchestrator:orchestrator@127.0.0.1:5432/orchestrator_analytics`) — rather than separate host / port /
user / password variables. Moving the database off-host later (managed Postgres, a different VM, a unix socket) is a
one-line repoint. Empty value and the sentinels `off` / `disabled` / `none` (case-insensitive) disable the sync,
matching `ANALYTICS_LOG_PATH`.

## Schema

[`../../analytics-db/init/01-schema.sql`](../../analytics-db/init/01-schema.sql) defines:

- **`analytics_events` table.** Columns mirror the JSONL record shape produced by `analytics.build_record`. `ts`,
  `repo`, `issue`, `event` are `NOT NULL`; everything else is nullable so a record of any kind the sink writes is a
  valid row. An `extras JSONB` column captures any field added to `build_record` before the DDL knows about it — the
  opt-in skill fields (`skills_triggered` / `skills_triggered_count` / `skills_available`, the per-load
  `skills_evidence` tier map, the name-to-source-level `skill_levels` map, and the `skills_incidental` /
  `skills_incidental_count` path-only references) are exactly such additions, so they need **zero DDL**: an
  operator-deployed database ingests them the moment
  `TRACK_SKILL_TRIGGERS` is enabled, with no migration and no schema reapply. The `agent_run_budget` family's payload
  is another: `stage` and `agent_role` are already promoted columns, and `phase`, `configured`, `allowance`, `used`,
  `remaining`, `reservation_id`, and `reason` all land in `extras` unchanged
  ([`event-streams.md`](event-streams.md#agent-run-budget-records-both-sinks)). The late size gate's eight families
  are a third, and the one with a test standing over it: `stage` is promoted, and every field of the bounded late
  payload lands in `extras` — the correlating identities, the frozen commits, the measurement, and the per-family
  details, including the `measurement_failure` step and the `detail` line a refused size reading names
  ([`event-streams.md`](event-streams.md#late-split-records-both-sinks)).
  `tests/observability/analytics/sync/test_live_postgres.py` replays one of those records against a real Postgres and
  reads both of those fields back out of the blob, so widening that payload stays an emitter change rather than a
  migration an operator has to apply. The daily terminal-artifact maintenance pass's per-candidate result is a
  fourth, and the smallest: `outcome`, `reason`, `layout`, and the `branch` it carries only where the reason names one
  are all outside the promoted set, so the whole payload rides in `extras`
  ([`event-streams.md`](event-streams.md#terminal_artifact_cleanup-records)). Like the repo-level skill catalog it
  passes no `stage`, so that promoted column is NULL on every one of its rows — which the schema already allows, and
  which the dashboard's stage filter is deliberately asymmetric about
  ([`analytics-dashboard.md`](analytics-dashboard.md#dashboard-orchestratorappsanalytics_dashboardpy)).
  Human-wait transitions (`park_awaiting_human`) are a fifth: the run columns a park shares with `agent_exit` are
  promoted, while its `reason`, `route`, pull request, commit, and the rest of its correlation ride in `extras`, and
  `get_issue_events` reads both back
  ([`event-streams.md`](event-streams.md#analytics-sink-analytics_log_path)).
  The `agent_exit` usage evidence is a sixth: `cost_evidence` and `token_evidence` ride in `extras` verbatim, as the
  objects the sink wrote ([`usage.md`](usage.md#usage-parser)), beside the promoted `cost_usd`, `cost_source`, and
  token columns they qualify — and, unlike the others, the sync also files what they mean in
  [columns of their own](#usage-evidence-columns), since SQL can neither validate nor fold the raw objects.
  `source_path` / `source_line` are
  forensic context; the authoritative dedup key is `content_hash` — SHA-256 over the canonical (`sort_keys=True`)
  JSON form of the record.
- **Indexes.** A plain (non-partial) unique index on `content_hash` plus `INSERT ... ON CONFLICT (content_hash) DO
  NOTHING` makes repeated sync runs idempotent. Additional indexes cover the expected query dimensions: `ts`; `(event,
  ts)`; `(repo, issue)`; a partial index on non-null `stage`; per-event-kind partial indexes on `(repo, ts DESC)` for
  `event='agent_exit'` and `event='stage_enter'`; and a composite `(event, repo, stage, ts)` index.
- **`analytics_daily_rollup` materialized view.** Keyed on `(day, repo, issue, event, stage, backend, cost_source)` and
  carrying the aggregates the dashboard's window-bounded widgets need without re-scanning `analytics_events`: token
  totals (`total_input_tokens`, `total_output_tokens`, `total_cached_tokens`, `total_cache_read_tokens`,
  `total_cache_write_tokens`), `total_cost_usd`, `duration_s_sum` + `duration_s_count` (so consumers recover
  `AVG(duration_s)` as `sum / count`), `failed_count` (rows with non-NULL non-zero `exit_code`), `timed_out_count`
  (scoped to `event='agent_exit'` with `timed_out=TRUE`), and `event_count`. `day` is `(ts AT TIME ZONE 'UTC')::date`. A
  unique index on the full key (`NULLS NOT DISTINCT`, Postgres 15+) backs the rollup; a `(day, repo)` supporting index
  keeps `WHERE day BETWEEN x AND y` predicates on a range scan. `cost_source` cannot say what a group cost, so the
  [usage evidence](#usage-evidence-columns) rides beside it, every column folding across rollup rows as it folds
  across the runs beneath: one amount per basis (`cost_cli_reported_usd`, `cost_anthropic_estimate_usd`,
  `cost_openai_estimate_usd`, `cost_gemini_estimate_usd`, `cost_unknown_basis_usd`), the `agent_exit` rows counted by
  the completeness each states (`cost_complete_runs`, `cost_incomplete_runs`, `cost_no_usage_runs`,
  `cost_unknown_runs`), every distinct rate-verification date per estimate basis (`anthropic_rates_verified_on`,
  `openai_rates_verified_on`, `gemini_rates_verified_on`, sorted arrays the schema's `analytics_rate_dates` aggregate
  unions, NULL where nothing in the group was priced at a dated row), the summed known non-overlapping `total_tokens`,
  the `cache_tokens_in_total` those known totals hold, and `total_tokens_unknown_runs`, the `agent_exit` rows whose
  total is unknown. A row with no derived evidence counts as an `unknown` run with its
  `cost_usd` summed under the `unknown` basis, as the agent-run view reads it.
- **`analytics_agent_runs` view.** `CREATE OR REPLACE VIEW` over `event = 'agent_exit'` rows that promotes derivations:
  `model` from `COALESCE(models->>0, 'unknown')`, `total_tokens` = the stored non-overlapping total (NULL where it is
  unknown), `total_cache_tokens` = `cached + cache_read + cache_write`, a categorical `review_round_bucket` (`0`, `1`,
  `2`, `3-5`, `6+`), `failed = exit_code <> 0` (NULL preserved), and `has_cost = cost_usd IS NOT NULL` (true for a
  complete cost, `cost_source` in {`reported`, `estimated`}). Raw nullable columns pass through alongside derived ones;
  `cost_source` passes through verbatim. The [usage evidence](#usage-evidence-columns) follows it, appended because
  `CREATE OR REPLACE VIEW` only appends: `cost_completeness`, the five per-basis amounts, the three estimate bases'
  `*_rates_verified_on` arrays, and `token_cache_overlap`, a row with no derived evidence reading as `unknown` with its
  `cost_usd` under the `unknown` basis.

The init script runs once when the data volume is empty. `IF NOT EXISTS` guards plus trailing `ALTER TABLE ... ADD
COLUMN IF NOT EXISTS` / `CREATE UNIQUE INDEX IF NOT EXISTS` for `content_hash` and the usage evidence columns keep it
idempotent for the operator-driven case (`psql -f` against an existing instance) and add those columns to an existing
data volume without dropping or converting data. MV column changes require `DROP MATERIALIZED VIEW
analytics_daily_rollup` followed by a reapply; the sync's refresh hook does NOT recover from a column mismatch.

### Usage evidence columns

`cost_usd` holds a run's complete amount alone and `cost_source` a coarse tag, and neither can say what a sum of them
means: a CLI-reported amount and each provider's API estimate are different things, an unpriced run states no amount
while its neighbours do, and a record an earlier build wrote names no basis at all. So for each `agent_exit` record the
sync (`sync/evidence.py`) reads the raw evidence through the readers every usage surface shares —
`usage.cost_evidence.recorded_cost` and `usage.token_evidence.recorded_tokens` ([`usage.md`](usage.md#usage-parser))
— and fills these `analytics_events` columns, NULL on every other event:

- `cost_completeness` — `complete`, `incomplete`, `no-usage`, or `unknown`.
- `cost_cli_reported_usd`, `cost_anthropic_estimate_usd`, `cost_openai_estimate_usd`, `cost_gemini_estimate_usd`,
  `cost_unknown_basis_usd` — each contribution under its own basis, NULL where the cost states none, so a complete
  zero (`0`) stays apart from no amount and an incomplete subtotal keeps the amounts it states while `cost_usd` stays
  NULL.
- `anthropic_rates_verified_on`, `openai_rates_verified_on`, `gemini_rates_verified_on` — an estimate's price-row
  verification dates, sorted and distinct.
- `token_cache_overlap` and `total_tokens` — how the cache counters relate to input, and the non-overlapping total:
  every observed counter once, a cache counter already inside input (Codex's `cached_tokens`) not added again, NULL
  where the evidence leaves it unknown (an Antigravity run's cache reads, whose overlap nothing establishes yet).

A record without evidence is read as those readers read it: `unknown` completeness with its `cost_usd` under the
`unknown` basis, never a provider's basis inferred from its `cost_source`, backend, or models, and a token total only
where no cache counter is nonzero. Nothing reprices a stored amount or backfills a breakdown. The raw evidence stays in
`extras`, and the record's `content_hash`, and so the replay's dedup, is unchanged by the derived cells. A row an
earlier sync stored before these columns existed carries none of them, and the replay skips its line as already
stored, so nothing re-derives it: the view and rollup read such a row as an `unknown` cost holding its `cost_usd` under
the `unknown` basis, with an unknown token total. The read model's
[cohort and token reductions](analytics-dashboard.md#read-model-orchestratorobservabilityanalyticsquery) are built over
these columns.

### Upgrading an existing database

This schema adds columns to `analytics_events`, appends columns to `analytics_agent_runs`, defines the
`analytics_rate_dates` aggregate, and changes the `analytics_daily_rollup` column list. Before the first sync of a
release that carries it — whose INSERT names the new columns and fails, committing nothing, on a table without them —
reapply the schema, drop the rollup, and reapply again so it is rebuilt with the new columns:

```sh
cd analytics-db
docker compose exec -T analytics-db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /docker-entrypoint-initdb.d/01-schema.sql'
docker compose exec -T analytics-db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "DROP MATERIALIZED VIEW IF EXISTS analytics_daily_rollup"'
docker compose exec -T analytics-db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /docker-entrypoint-initdb.d/01-schema.sql'
```

The first reapply adds the table columns and replaces the agent-run view in place; dropping the rollup loses nothing,
since the second reapply rebuilds it from `analytics_events`. Until the first reapply, a dashboard read naming a new
column raises its read-error banner, except that the earlier agent-run view still answers `total_tokens` as input
plus output, so the cost-coverage bar and the by-backend token stack read that earlier total rather than failing.
Rows already stored keep NULL evidence columns and read as described above.

## Sync CLI (`orchestrator/observability/analytics/sync/cli.py`)

The packaged sync CLI owns the argument parser, UTC-pinned log formatter, stdout summary, and exit code over the replay
`orchestrator/observability/analytics/sync/run.py` owns. It runs in the pipx environment with the runtime
`psycopg[binary]` dependency; Poetry and the optional dashboard group are not needed. Launch commands and one-off
replay examples are under [operator workflow](#operator-workflow).

**Batched inserts.** Reads `ANALYTICS_LOG_PATH` line by line, accumulates validated row tuples into a buffer sized by
`sync/ingest.py`'s `BATCH_SIZE` (default 500), and flushes each full batch via `cur.executemany("INSERT ... ON CONFLICT
(content_hash) DO NOTHING", batch)`. A multi-thousand-record replay pays one Postgres round-trip per batch instead of
one per row. A final partial batch is flushed at EOF so the tail still lands. The size is read off the owner as a pass
starts, so a caller that pins a smaller buffer drives the loop that actually runs.

**Pre-check dedup.** Before opening the input file the sync issues a single `SELECT content_hash FROM analytics_events`
and pulls the result into a Python set — every row the sync inserts carries its line's hash — so already-present rows
are filtered out before they enter the batch. Newly queued hashes are added to the same set as the loop iterates, so two
identical records inside one JSONL file are deduped against each other before reaching `executemany`. The pre-check
reads from the unique `analytics_events_content_hash_idx`. The server-side `ON CONFLICT (content_hash) DO NOTHING`
arbiter stays the authoritative dedup backstop for racing concurrent writers.

**Counters.** Per-batch `cur.rowcount` drives the cumulative `inserted` / `skipped_duplicate` totals. Duplicates =
`len(batch) - rowcount` for wire-side skips, plus the pre-skip counter for in-Python skips.

**Malformed-line tolerance.** Blank lines are silently skipped; lines that are not valid JSON, JSON that is not an
object, records missing one of the required (`ts` / `repo` / `issue` / `event`) keys, or carrying an unparseable `ts`
are counted as skipped and logged but never enter the batch buffer. The JSONL file is treated as read-only — the sync
never rewrites or truncates it, even when it sees malformed lines. Naive timestamps are interpreted as UTC.

**Transaction shape.** A `psycopg` driver-level error inside a batch flush rolls the transaction back and propagates so
the CLI exits non-zero rather than reporting "success" on a half-inserted run. After the insert transaction commits, the
sync issues `REFRESH MATERIALIZED VIEW analytics_daily_rollup` (non-concurrent) and commits again so the rollup-backed
dashboard widgets catch up. The refresh fires unconditionally on every successful commit — including all-duplicates
and all-malformed runs — so rerunning the sync is the documented recovery path for a stale rollup. A refresh exception
(MV not migrated yet, transient Postgres error, lock-wait timeout) is logged via `log.exception` and swallowed; the
committed inserts are durable, and the next sync's refresh recovers the rollup.

**No-op modes.** `sync_jsonl_to_postgres` is a no-op (no connection attempt, no row insertion, no error) when
`ANALYTICS_DB_URL` is unset or disabled, when `ANALYTICS_LOG_PATH` is explicitly disabled (note that the env var
defaults to `LOG_DIR/analytics.jsonl`, so only the empty value or `off` / `disabled` / `none` turns it off), or when the
JSONL file is absent. The CLI is safe to schedule before the operator deploys Postgres. The driver is `psycopg[binary]`;
the import is lazy inside the connect helper so the module load path remains driver-free for callers that only need
`SyncResult`.

**Module ownership.** Everything above is owned by `observability/analytics/sync/`, split by boundary. `columns.py`
owns the promoted / JSONB / required column inventory and the usage evidence columns derived beside them;
`records.py` owns canonical JSON, `content_hash`, the coercion each required field is narrowed by, and the routing of
everything else into `extras`; `evidence.py` owns what an `agent_exit` record's usage evidence fills on its row;
`rows.py` validates one line, builds the INSERT, and lays out the positional tuple that fills it. Those four are
driver-free, so a caller can hash a record or build a row with no psycopg installed. `models.py` owns `SyncResult` and
the mutable tallies behind it, `ingest.py` the pre-check, the in-file skip set, the batched flush, and the progress
and malformed records, `database.py` the lazily imported driver plus the quiet rollback / close and the rollup
refresh, `redaction.py` the credential stripping, `run.py` the resolved request, the no-op gate, the transaction shape,
and `sync_jsonl_to_postgres` itself, and `cli.py` the arguments, the UTC-pinned logging, the stdout summary, and the
exit code. Nothing above them answers for a replay: `cli.py` is the module `python -m` names, and a caller that drives
a run itself names `run.py`.

## Operator feedback

The sync surfaces feedback through one logger and the stdout summary. Every owner under
`observability/analytics/sync/` writes to `orchestrator.analytics.sync`, spelled out literally rather than derived
from the module path, so an operator's log filter keeps selecting the whole replay regardless of which module a line
comes from:

- Every log line is timestamped (UTC, with an explicit `UTC` suffix) via `configure_cli_logging`'s `%(asctime)s`
  formatter and `formatter.converter = time.gmtime`.
- A `connecting to <redacted-url>` / `connection established` pair brackets the connect call so a remote-Postgres
  reachability problem surfaces immediately.
- A `progress lines=N inserted=… duplicate=… malformed=… elapsed=…s` record drops after each batched
  `executemany` flush, so the progress cadence is the 500-row `BATCH_SIZE` itself.
- A final `completed in %.3fs (…)` line carries the wall-clock total.
- The CLI prints a UTC-stamped stdout summary at the end carrying `inserted=` / `duplicate=` / `malformed=` /
  `total_lines=` / `duration_s=`.
- `ANALYTICS_DB_URL` credentials are stripped before logging — both the `user:password@` netloc form and the libpq
  query-string form (`?user=`, `?password=`, `?sslpassword=`, `?passfile=`, case-insensitive per libpq parameter-name
  rules) collapse to `***`.

## Operator workflow

Run analytics sync from the installed poller's pipx environment on whatever cadence you prefer. It reads
`~/.config/chipping-orchestrator/.env` and the process environment; set `ANALYTICS_DB_URL` to the provisioned database's
libpq URL.
`ANALYTICS_LOG_PATH` defaults to the installed poller's `LOG_DIR/analytics.jsonl`. Use the same service user and any
process/service overrides as the poller. Launch from outside an orchestrator source checkout so Python imports the
installed package:

```sh
cd "$HOME"
"$(pipx environment --value PIPX_HOME)/venvs/chipping-orchestrator/bin/python" \
  -m orchestrator.observability.analytics.sync.cli
```

`--log-path /path/to/rotated.jsonl` and `--db-url postgresql://other/db` override the settings for one-off replays of
archived JSONL files. For local-only Postgres, storing the database password in `.env` as part of `ANALYTICS_DB_URL`
is acceptable: that credential is scoped to the analytics database and never grants write access to GitHub.
The default cadence is operator-chosen because the JSONL sink is already the authoritative analytics surface on disk
— the database is for aggregation and reporting, not durability.

For hourly unattended replay, run `pipx environment --value PIPX_HOME` as the service user and replace
`/absolute/pipx-home` below with that result. Replace `<user>` and adjust the output path if your external log
directory differs from the package setup example. Create the output directory before installing the cron entry:

```sh
mkdir -p "$HOME/.local/state/chipping-orchestrator/logs"
```

Cron does not inherit the poller's systemd `Environment=` or `EnvironmentFile=` settings. Copy any service-only
settings, including `REPOS`, `LOG_DIR`, `ANALYTICS_LOG_PATH`, and `ANALYTICS_DB_URL`, into the installed `.env`, or
uncomment and edit the matching assignments below. The command loads the full orchestrator configuration at startup,
so `REPOS` must name valid local clones even for analytics sync. Crontab assignments override `.env`; use literal
values and absolute paths because they do not expand `$HOME` or other variables.

```cron
# Optional overrides: uncomment and match the poller's service environment.
# REPOS=acme/api|/srv/clones/acme-api|main
# LOG_DIR=/home/<user>/.local/state/chipping-orchestrator/logs
# ANALYTICS_LOG_PATH=/absolute/path/analytics.jsonl
# ANALYTICS_DB_URL=postgresql://orchestrator:orchestrator@127.0.0.1:5432/orchestrator_analytics
00 * * * * cd / && /usr/bin/flock -n /tmp/chipping-orchestrator-analytics-sync.lock /absolute/pipx-home/venvs/chipping-orchestrator/bin/python -m orchestrator.observability.analytics.sync.cli >> /home/<user>/.local/state/chipping-orchestrator/logs/analytics-sync.cron.log 2>&1
```

The installed `.env` supplies settings not overridden in the cron environment; the cron command needs no tool checkout.
Rotate the cron log, and stop maintenance jobs as well as the poller before upgrading or replacing their shared pipx
environment.
Source-checkout commands for development are in the [developer guide](../development.md#analytics-sync-and-dashboard).
