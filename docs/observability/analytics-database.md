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

[`../../analytics-db/compose.yml`](../../analytics-db/compose.yml) brings up a single `postgres:16` container with
the data directory on a host bind (`./data`, gitignored) and the init directory mounted read-only. The port binding is
pinned to `127.0.0.1` so the database is unreachable off-host regardless of firewall configuration; re-binding to
`0.0.0.0` is intentionally a code change rather than an env-var change. Credentials default to `orchestrator` /
`orchestrator` and are overridable via `analytics-db/.env` (`POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` /
`POSTGRES_PORT`). `docker compose` reads `.env` from the compose-file directory, not the orchestrator root.

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
  keeps `WHERE day BETWEEN x AND y` predicates on a range scan.
- **`analytics_agent_runs` view.** `CREATE OR REPLACE VIEW` over `event = 'agent_exit'` rows that promotes derivations:
  `model` from `COALESCE(models->>0, 'unknown')`, `total_tokens` = `input + output`, `total_cache_tokens` = `cached +
  cache_read + cache_write`, a categorical `review_round_bucket` (`0`, `1`, `2`, `3-5`, `6+`), `failed = exit_code <> 0`
  (NULL preserved), and `has_cost = cost_usd IS NOT NULL` (true for `cost_source` in {`reported`, `estimated`}). Raw
  nullable columns pass through alongside derived ones; `cost_source` passes through verbatim.

The init script runs once when the data volume is empty. `IF NOT EXISTS` guards plus trailing `ALTER TABLE ... ADD
COLUMN IF NOT EXISTS` / `CREATE UNIQUE INDEX IF NOT EXISTS` for `content_hash` keep it idempotent for the
operator-driven case (`psql -f` against an existing instance) and migrate a pre-`content_hash` data volume without
dropping data. MV column changes require `DROP MATERIALIZED VIEW analytics_daily_rollup` followed by a reapply; the
sync's refresh hook does NOT recover from a column mismatch.

## Sync CLI (`orchestrator/observability/analytics/sync/cli.py`)

The command lives here — the argument parser, the UTC-pinned log formatter, the stdout summary, and the exit code —
over the replay `orchestrator/observability/analytics/sync/run.py` owns. Run on demand:

```sh
uv run python -m orchestrator.observability.analytics.sync.cli   # uses configured env vars
uv run python -m orchestrator.observability.analytics.sync.cli --log-path /path/to/rotated.jsonl --db-url postgresql://other/db
```

**Batched inserts.** Reads `ANALYTICS_LOG_PATH` line by line, accumulates validated row tuples into a buffer sized by
`sync/ingest.py`'s `BATCH_SIZE` (default 500), and flushes each full batch via `cur.executemany("INSERT ... ON CONFLICT
(content_hash) DO NOTHING", batch)`. A multi-thousand-record replay pays one Postgres round-trip per batch instead of
one per row. A final partial batch is flushed at EOF so the tail still lands. The size is read off the owner as a pass
starts, so a caller that pins a smaller buffer drives the loop that actually runs.

**Pre-check dedup.** Before opening the input file the sync issues a single `SELECT content_hash FROM analytics_events
WHERE content_hash IS NOT NULL` and pulls the result into a Python set, so already-present rows are filtered out before
they enter the batch. Newly queued hashes are added to the same set as the loop iterates, so two identical records
inside one JSONL file are deduped against each other before reaching `executemany`. The pre-check reads from the unique
`analytics_events_content_hash_idx`. The server-side `ON CONFLICT (content_hash) DO NOTHING` arbiter stays the
authoritative dedup backstop for racing concurrent writers.

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
owns the promoted / JSONB / required column inventory; `records.py` owns canonical JSON, `content_hash`, the coercion
each required field is narrowed by, and the routing of everything else into `extras`; `rows.py` validates one line,
builds the INSERT, and lays out the positional tuple that fills it. Those three are driver-free, so a caller can hash a
record or build a row with no psycopg installed. `models.py` owns `SyncResult` and the mutable tallies behind it,
`ingest.py` the pre-check, the in-file skip set, the batched flush, and the progress and malformed records,
`database.py` the lazily imported driver plus the quiet rollback / close and the rollup refresh, `redaction.py` the
credential stripping, `run.py` the resolved request, the no-op gate, the transaction shape, and
`sync_jsonl_to_postgres` itself, and `cli.py` the arguments, the UTC-pinned logging, the stdout summary, and the exit
code. Nothing above them answers for a replay: `cli.py` is the module `python -m` names, and a caller that drives
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

Run `uv run python -m orchestrator.observability.analytics.sync.cli` on whatever cadence you prefer; `--log-path` and
`--db-url` override the env values for one-off replays of archived JSONL files. The default cadence is operator-chosen
because the JSONL sink is already the authoritative analytics surface on disk — the database is for aggregation and
reporting, not durability.

For an unattended deployment, drive the sync from `cron`. A typical entry runs hourly, guards against overlap with
`flock`, and captures output:

```cron
00 * * * * cd /path/to/chipping-orchestrator && /usr/bin/flock -n /tmp/chipping-orchestrator-analytics-sync.lock /home/<user>/.local/bin/uv run python -m orchestrator.observability.analytics.sync.cli --log-path /path/to/chipping-orchestrator/logs/analytics.jsonl --db-url 'postgresql://<user>:<password>@<host>:<port>/<database>' >> /path/to/chipping-orchestrator/logs/analytics-sync.cron.log 2>&1
```

- `cd /path/to/chipping-orchestrator` so `uv run` finds the project's `pyproject.toml`.
- Absolute `/home/<user>/.local/bin/uv` because cron's `PATH` does not include `~/.local/bin`.
- `flock -n` makes the run a no-op when a previous invocation is still holding the lock, so a long replay never overlaps
  with the next tick.
- `--log-path` and `--db-url` are explicit CLI overrides, so the cron entry does not depend on `.env` being loadable
  from cron's environment.
- `>> ...analytics-sync.cron.log 2>&1` keeps stdout and stderr in the project log area instead of routing failures to
  local `mail`.
