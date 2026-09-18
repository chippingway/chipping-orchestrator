# Analytics read model and dashboard

Everything that reads the [analytics database](analytics-database.md) back: the connection-injectable query layer the
page is built on, the page composition itself, and the labeled banner every empty or misconfigured case surfaces as
instead of an exception. Both are observation-only and independent of the polling tick — the dashboard opens no GitHub
session, writes no Postgres row, and can be pointed at a managed endpoint without touching the orchestrator's
deployment.

The tables these reads scan, the sync that fills them, and the operator cron around it are on
[`analytics-database.md`](analytics-database.md). Where the read and render paths sit in the package tree, and what
each package there is responsible for, is in
[`architecture/observability-modules.md`](../architecture/observability-modules.md); the knobs are in
[`configuration/observability.md`](../configuration/observability.md). The Streamlit page itself sits beside the
package tree, at `orchestrator/apps/analytics_dashboard.py`.

## Read model (`orchestrator/observability/analytics/query/`)

Thin, testable data-access layer over `analytics_events`, the `analytics_agent_runs` view, and the
`analytics_daily_rollup` materialized view. The dashboard's window-bounded aggregates read from the rollup; per-row
drill-downs and widgets the rollup cannot reconstruct exactly stay on the base table or the agent-run view. Nothing
here imports Streamlit, so the read path can be wired into any UI.

The raw, rollup, breakdown, and skill reads are owned by `raw_reads.py`, `rollup_reads.py`, `breakdown_reads.py`, and
`skill_reads.py`, with one projection owner per read beside them and the frozen result models every family returns by
the five result-family owners there. Each caller names the owner its read is defined on: the three skill-panel
adapters in `observability/dashboard/skills.py` reach `skill_reads.py` directly, the six comparison-panel adapters in
`observability/dashboard/breakdowns.py` reach `rollup_reads.py` and `breakdown_reads.py` the same way, and the seven
headline and lifecycle adapters in `observability/dashboard/rollups.py` reach those two plus `raw_reads.py` and the
`SORT_BY_COST` spelling `issue_summaries.py` declares.

The shared call boundary is a `ReadRequest` composed of `ReadFilters`, `ReadConnection`, and `ReadOptions`, declared by
`observability/analytics/query/request_models.py`. Its sibling `requests.py` binds every historical keyword signature
into that typed request before the family leaf executes, so existing calls and error behavior are unchanged while
implementation helpers no longer thread large argument lists. Every family leaf reaches `execution.py`'s `ReadQuery`
for the connection inputs one read carries. Both connection paths resolve a caller's omitted `db_url=` through
`observability/analytics/config.py`'s `resolve_db_url`, so the URL-source policy has one home.

**Input owners.** `filters.py` owns `WindowFilters` — the selection a read narrows by, plus the three scoped
projections (`without_events` for a view with no `event` column, `catalog_scope` for repo-level catalog rows,
`historical_scope` for a session's evidence from before the window) — and the builder that accumulates a clause and its
bindings together. `predicates.py` owns the one `WHERE` builder behind all three scan targets, so the events table, the
agent-run view, and the daily rollup read a filter the same way. `conditions.py` owns the two splices that add a
table's own required condition to either end of a generated clause (which fixes whether its operand binds first or
last) and `agent_event_excluded`, the probe view-backed readers short-circuit on.

**Connection owners.** `connections.py` decides what a read dials with — the deferred psycopg import, the per-query and
persistent connect factories over it, `AnalyticsReadError`, and the two judgments a caller makes about a socket rather
than a query (whether a close failed, whether an escaped error means the socket is gone). `connection_cache.py` decides
how long a socket lives: the thread-local entry, the URL it is keyed on, the two evictions, and the
`analytics_connection` / `close_thread_local_connection` pair over them. `execution.py` decides whose connection a
SELECT runs on, and closes only the descriptor it opened itself.

**Result owners.** One module per result family, each a plain frozen-dataclass module that reaches nothing — importing
a row never costs a connection factory, the configuration behind an omitted `db_url=`, or the driver behind those.
`activity_models.py` owns the time-bucketed cells (`BackendDailyTokensRow`, `HourlyHeatmapPoint`, `ThroughputDayRow`);
`overview_models.py` what a page frames a window with — `FilterOptions`, `DataExtent`, and `Summary` construct bare so
an unset `ANALYTICS_DB_URL` still renders a page, while `TimeSeriesPoint` requires the `(day, event, count)` key its
cost and token aggregates hang off; `cost_models.py` the spend breakdowns
(`ReviewRoundBucketRow`, `BackendEfficiencyRow`, `RepoBreakdownRow`, `CostCoverageRow`); `run_models.py` the run,
issue, and traced-event rows (`StageBreakdown`, `EventBreakdown`, `AgentExitRow`, `IssueSummaryRow`, `IssueEventRow`)
plus `public_event_result`, the accessor installed as the trace row's `result` property over its stored `event_result`
column; and `skill_models.py` the skill cells (`SkillTriggerRateRow`, `SkillTriggerMatrixRow`, `SkillAdoptionRow`) with
the zero-denominator-guarded share each derives.

**Raw-read owners.** `raw_reads.py` owns the six reads that stay on `analytics_events` rather than the day-bucketed
rollup above it — `get_filter_options`, `get_data_extent`, `get_event_breakdown`, `get_recent_agent_exits`,
`get_issues`, and `get_issue_events`. It also decides the answers that need no database: an unconfigured URL with no
caller-owned `conn=`, a non-positive `limit`, and a cleared multiselect each return the empty result without dialing,
while an unknown `sort_by` raises before the connect. Each read hands its filtered window to a projection owner:
`filter_options.py` (the tagged union behind the five dropdowns, plus the in-Python bucketing and sort it is read back
through), `event_breakdowns.py` (the per-event count), `agent_exits.py` (the pinned `event = 'agent_exit'` spliced
ahead of the generated predicate, so its operand binds first and the `LIMIT` last), `issue_summaries.py` (the
per-`(repo, issue)` aggregate scan, `SORT_BY_LAST_SEEN` / `SORT_BY_COST`, and the SQL ordering each becomes), and
`issue_events.py` (one issue's trace, `ORDER BY ts ASC, id ASC`). Beneath them, `query_rows.py` names the columns of
the four SELECT lists read back by field rather than by index — recent exits, issue summaries, one issue's trace,
review-round buckets — and the trace's named row is its SELECT list, so the two cannot disagree about where a column
sits. All but the first pad a row shorter than the list to the full width, which is what lets an older, narrower
fixture round-trip with its missing columns unset; the recent-exit row unpacks strictly, so a row short of its fifteen
columns raises. `raw_values.py` owns the NULL-preserving scalar coercions, the decode of a JSONB cell a driver hands
back either adapted or as text, plus the probe for a cleared multiselect.

**Rollup-read owners.** `rollup_reads.py` owns the seven reads that scan `analytics_daily_rollup` instead —
`get_summary`, `get_kpi_prev`, `get_time_series`, `get_stage_breakdown`, `get_backend_efficiency`,
`get_repo_breakdown`, and `get_throughput_breakdown`. A window bounded by whole days is what they have in common, and
what lets them read the rollup rather than a row's own `ts`. It decides the same no-database answers the raw hub does,
plus the agent-run event-filter short-circuit `get_backend_efficiency` returns on. One projection owner sits under
each read: `summary_queries.py` (the `WITH win AS (...)` CTE and its three `UNION ALL` branches) with
`summary_results.py` beside it (the in-Python `count DESC, label ASC` ranking, and the cast list that leaves a short
totals row's trailing fields at their model defaults), `kpi_totals.py` (the trimmed previous-window scalars),
`time_series.py` (the per-`(day, event)` cell), `stage_breakdowns.py`, `backend_efficiency.py`, `repo_breakdowns.py`,
and `throughput_days.py` (the `done` / `rejected` terminals, the stage-selection intersection, and the two
short-circuits that leave nothing to count).

**Breakdown-read owners.** `breakdown_reads.py` owns the remaining four, the ones whose grouping key the rollup threw
away — `get_review_round_breakdown`, `get_cost_coverage`, `get_backend_daily_tokens`, and `get_hourly_heatmap`. The
first three read per-run facts a day bucket aggregated over, so they scan `analytics_agent_runs`; the fourth needs the
hour that bucket rounded off, so it stays on `analytics_events`. It decides the same unconfigured-database answer the
other two hubs do, and the agent-run event-filter short-circuit applies to the three view-backed reads only — the
heatmap's scan has an `event` column, so the selection becomes an ordinary bound predicate there instead. One
projection owner sits under each: `review_rounds.py` (the bucket labelling, the two roles, and each role's cache /
no-cache split), `cost_coverage.py` (the per-source rollup that keeps `unknown-price` distinct from `unknown`),
`backend_tokens.py` (the per-`(day, backend)` token cell), and `hourly_heatmaps.py` (the UTC normalization and the
bound offset).

**Skill-read owners.** `skill_reads.py` owns the last three — `get_skill_trigger_rates`, `get_skill_trigger_matrix`,
and `get_skill_adoption`. Their fact is not a column: a skill name, a repository's offered set, and one run's load
count ride in an `agent_exit` row's `extras` JSONB, which neither the rollup nor the agent-run view carries. All three
therefore scan `analytics_events` and pin `conditions.py`'s `AGENT_EXIT_CONDITION` themselves, so an events selection
that excludes `agent_exit` returns without dialing rather than running a query whose two conditions contradict; the
two capped reads pass a non-positive `limit` through as "every cell". One aggregate owner sits under each:
`skill_trigger_rates.py` (the whole-cohort denominator, the key-presence probe, and the summed trigger count),
`skill_matrices.py` (the window-scoped runs scan, the zero-padding over it, and the ranking the cap keeps the top
of), and `skill_adoption.py` (the per-session ratio and the invocation / load / incidental diagnostics beside it).
Beneath both of the last two, `skill_provenance.py` owns the repository-scoped catalog scan the padding is drawn
from, the narrower filtering that repo-level record takes, and the level lookup over it — an unclassified name is
filed at the level that repository offers it at, where it offers exactly one, and a name it never offered or offers
at two levels stays `unknown`; `repo_skill_provenance` / `SkillProvenance` are what both aggregates resolve through,
and `SkillProvenance.resolve_row` is the one step each takes over a name array and the level map beside it. Beneath
the adoption aggregate, `skill_sessions.py` owns the resume-then-session-then-row-id session key and the two session
scans' scopes — the window one picks which sessions count, the history one drops the start bound and the stage filter
while keeping the end bound — and applies the fill to every category either scan gathers: the window loads, the
incidental references, and a history row's offered set and loads alike. Beneath both aggregates, `skill_values.py`
owns the two JSONB coercions (the name array and the name-to-source-level map), the pairing that reads each name's
level off the same row and defaults an uncovered name to `unknown`, the `(repo, role, backend)` cohort with its
`"unknown"` bucketing, and the `(repo, agent_role, backend, skill, level)` cell both aggregates accumulate under.

Beneath the rollup and breakdown families, `cache_shares.py` owns the token-share SQL the cache / no-cache split is
weighted by — spelled once for the rollup's `total_*` sums and once for the agent-run view's per-run columns — and
`row_cells.py` the readings a cell from any family passes through: a positional read with a default for a row
narrower than the SELECT list, a nullable cost column read as a float, and a driver-widened `day` narrowed back to a
date. The NULL-preserving float coercion the stage and backend projections share is `raw_values.py`'s, so both sides
of the read path narrow a nullable duration the same way.

- `get_summary` (rollup) — date-bounded totals + per-event / per-stage breakdowns + token / cost sums, plus
  `total_agent_runs` / `failed_agent_runs` / `timed_out_agent_runs` scoped to `event='agent_exit'`. `distinct_issues` is
  `COUNT(DISTINCT (repo, issue))`. Single round-trip via `WITH win AS (...)` CTE with three `UNION ALL` branches tagged
  by a `kind` discriminator.
- `get_kpi_prev` (rollup) — stripped variant of `get_summary` returning only the cost / token / agent-run scalars the
  dashboard reads off `prev_summary` for KPI deltas. Skips the `COUNT(DISTINCT)`s and `GROUP BY` follow-ups; ~one
  aggregate scan instead of three.
- `get_time_series` (rollup) — daily `(day, event, count)` rollups with per-cell cost / input / output / cache_read /
  cache_write token aggregates.
- `get_stage_breakdown` (rollup) — per-stage counts + weighted `AVG(duration_s)` recovered as `SUM(duration_s_sum) /
  NULLIF(SUM(duration_s_count), 0)`, rolled-up cost / token totals, and a `runs` agent-exit subset count. The total cost
  is further split into cache vs no-cache (`cache_cost_usd` + `no_cache_cost_usd`); each rollup row's `total_cost_usd`
  is weighted by `(total_cached_tokens + total_cache_read_tokens + total_cache_write_tokens) / (total_input_tokens +
  total_output_tokens + total_cache_read_tokens + total_cache_write_tokens)` into the cache stack and the complement
  into no-cache. `total_cached_tokens` is the Codex "portion of input served from cache" counter and is already inside
  `total_input_tokens`, so it stays out of the denominator to avoid double-counting. Token-less rollup rows attribute
  their full cost to no-cache.
- `get_repo_breakdown` (rollup) — per-`repo` rollup of issues / events / agent-exits / cost.
- `get_backend_efficiency` (rollup) — per-backend runs / failed / avg duration / cost / token totals with NULL
  backends surfaced as `"unknown"`. `event = 'agent_exit'` is pinned in the WHERE clause.
- `get_throughput_breakdown` (rollup) — daily resolved / rejected counts over `stage_enter` rows whose `stage` is
  `done` or `rejected`. Short-circuits when the events multiselect excludes `stage_enter` or the stages selection
  excludes both terminals.
- `get_filter_options` (base table) — distinct repos / events / stages / backends / agent_roles for dropdowns. All
  five columns pulled in a single `UNION`'d round-trip with rows tagged by their column.
- `get_data_extent` (base table) — min / max `ts` so the sidebar date picker defaults to a window that contains rows.
- `get_event_breakdown` (base table) — per-event counts (the rollup pre-aggregates more finely than `event` alone, so
  the base-table read is cheaper here).
- `get_recent_agent_exits` (base table) — newest rows filtered to `event='agent_exit'`.
- `get_skill_trigger_rates` (base table) — per-`(agent_role, backend)` skill-trigger aggregate: `runs`, `skill_runs`
  (rows whose `extras` carries a `skills_triggered` key), and `total_triggers` (`SUM` of `skills_triggered_count`), with
  a derived `rate` property. Reads the base table because the skill fields live in `extras JSONB`, which the rollup does
  not carry — no DDL. `event = 'agent_exit'` is pinned and the agent-exit event-filter short-circuit applies. NULL
  `agent_role` / `backend` bucket under `"unknown"`. A `0` rate is a real "no trigger observed" signal but cannot tell a
  tracked-but-quiet run from one whose `TRACK_SKILL_TRIGGERS` was off.
- `get_skill_trigger_matrix` (base table) — per-`(skill, level)` × `(repo, agent_role, backend)` trigger-run matrix.
  Two
  base-table reads combined in Python: the `repo_skill_catalog` records (the `skills_available` universe a repo offers;
  date/repo-filtered only, since those records are repo-level with `issue = 0` / NULL stage) and the filtered
  `agent_exit` rows (each run's `skills_triggered` list). Both scans read the recorded `skill_levels` map beside the
  names, so a name defined at two levels is two cells rather than one blended average: a catalog name the record left
  unclassified pads at `project` (that scan enumerates a repository's own checked-in definitions), while an
  unclassified run name — a record written before levels existed, or a claude run whose stream names no source
  directory — is filed at the level that repository's catalog offers the name at whenever it offers exactly one, so
  the load merges into the padded cell instead of splitting off an `unknown` one beside it; a name the catalog never
  offered, or one it offers at two levels, keeps `unknown`, and a level the run itself recorded is never overwritten
  (`skill_provenance.py`). Each cell carries `skill_runs` (runs *containing* the skill,
  one per run per distinct name — not total invocations) and `runs` (the total agent-exit runs in the cell's cohort,
  so a low/zero trigger count reads against the cohort size). Every catalog skill is zero-padded across the cohorts
  observed for its repo so the matrix carries explicit "offered but never triggered" cells (e.g. `developer / claude /
  review`, `skill_runs = 0`); with the catalog missing it degrades to just the observed-trigger cells. decomposer /
  question cohorts get the same catalog-backed zero rows as developer / reviewer whenever they have agent-exit runs.
  Rows are ordered by `skill_runs` DESC, then cohort `runs` DESC, then a stable
  `(repo, agent_role, backend, skill, level)`
  tiebreak, and the list is capped at `limit` rows (default `SKILL_MATRIX_ROW_LIMIT` = 100; a non-positive `limit`
  disables the cap). The agent-exit event-filter short-circuit applies (no catalog read either). NULL `agent_role` /
  `backend` bucket under `"unknown"`. Same `extras JSONB` / no-DDL and `TRACK_SKILL_TRIGGERS`-off caveats as
  `get_skill_trigger_rates`.
- `get_skill_adoption` (base table) — per-`(skill, level)` × `(repo, agent_role, backend)` adoption aggregated by
  **logical**
  agent session rather than by raw agent run, so a resume chain that pulled `develop` across several ticks counts as one
  adopting session, not several. Three base-table scans combine in Python. The first applies the full
  reporting-window filters and selects the *active* sessions plus the window-scoped diagnostics; the second reads each
  active session's evidence from every `agent_exit` row *before the window end*, deliberately dropping the window start
  and the stage filter (`WindowFilters.historical_scope`) so a load from a prior stage or from before the window stays
  visible, while the retained `end` bound stops a later load from leaking backward. The third reads the repos'
  `repo_skill_catalog` records under `WindowFilters.catalog_scope` (date and repo only — an issue or stage pushed onto
  a repository-level record would drop every row), and the two `agent_exit` scans resolve against it.
  A session is keyed by `resume_session_id`, then `session_id`, then the row's primary key (an ID-less row is its own
  session, never merged into one anonymous bucket). Both session scans read each row's `skill_levels` map beside its
  names, so an offer and a load are matched by source level as well as by name and a session offered a repository's
  own `develop` is counted apart from one offered a global skill of that name. A name no level map covers is filled
  from the catalog scan (`skill_provenance.py`): the level the row's repository offers that name at, where it offers
  exactly one, so a claude session's unclassified offer and load land in the same cell a codex session's classified
  ones do (`develop` / `project` reading 3 of 26 sessions rather than that cell beside a `develop` / `unknown` one).
  A name the catalog never offered, or one it offers at two levels, stays `unknown` on both sides — so a legacy
  session's load still counts as adoption of what it was offered — and a level the row itself recorded is never
  overwritten. The fill is applied to all three evidence categories alike (window loads, incidental references, and
  the historical availability and loads), since filling one and not another would strand a session outside its own
  denominator; it is a read-side resolution, so a past window's rows correct themselves the next time the page is
  drawn and no record is rewritten.
  `sessions` is the denominator — sessions in the
  cohort with the skill available (its
  `skills_available` listed it, or a legacy load with the `skills_available` key absent implied it — an explicit empty
  set does not) — and `adopted` counts the sessions that loaded it, once per session, with a derived `adoption_rate`.
  `invocations` is the cohort's window `agent_exit` run count (every run, so a low `load_rows` reads against it);
  `load_rows` counts the window runs that loaded the skill and `incidental` the window runs that made a path-only
  reference to it — independent buckets, so a run that both loaded and inspected a `SKILL.md` increments both. All
  three are window-scoped, so a pre-window load counts toward `adopted` but not toward them. Rows are
  ordered by `sessions` DESC, then `adopted` DESC, then
  `invocations` DESC, then a stable `(repo, agent_role, backend, skill, level)` tiebreak, and the list is capped at
  `limit`
  (default `SKILL_ADOPTION_ROW_LIMIT` = 100; a non-positive `limit` disables the cap). The agent-exit event-filter
  short-circuit (no scans at all, the catalog one included), NULL `"unknown"` bucketing, and `extras JSONB` / no-DDL /
  `TRACK_SKILL_TRIGGERS`-off caveats match `get_skill_trigger_matrix`.
- `get_issues` (base table) — date / repo-bounded one-row-per-`(repo, issue)` overview: event count, first / last
  activity, latest non-null stage, agent-exit count, cost / token totals, `max_review_round`, `failed_agent_runs`,
  `max_retry_count`. Bounded by `limit` and ordered by `sort_by` (`"last_seen"` default, `"cost"` orders by
  `SUM(cost_usd) DESC NULLS LAST`; unknown `sort_by` raises `ValueError`).
- `get_issue_events` (base table) — full event trace for a single `(repo, issue)` pair, oldest first. Beyond the nine
  columns the drill-down tabulates, each `IssueEventRow` carries the promoted run columns a human-wait record is
  correlated by (`agent_spec`, `session_id`, `resume_session_id`, `review_round`, `retry_count`, `timed_out`) and the
  row's decoded `extras` blob, where a park's `reason`, `route`, `pr_number`, and `sha` ride — see
  [`event-streams.md`](event-streams.md#analytics-sink-analytics_log_path). A NULL column reads as `None`, and a NULL,
  damaged, or non-object blob as an empty mapping, so a legacy row still reads. The page renders none of them.
- `get_hourly_heatmap` (base table) — 7×24 weekday/hour activity cells from `EXTRACT(DOW)` / `EXTRACT(HOUR)` over
  `(ts AT TIME ZONE 'UTC') + tz_offset_hours * INTERVAL '1 hour'` (normalizing first guards against a non-UTC session
  timezone re-shifting the buckets) with per-cell event count + `input + output + cache_read + cache_write` token total.
  `tz_offset_hours` (default `0`, parameter binding only — never spliced) lets the dashboard bucket in a non-UTC zone.
- `get_review_round_breakdown` (agent-run view) — per `review_round_bucket` runs / failed counts + `total_cost_usd`,
  plus per-role (`developer_*` / `reviewer_*`) run counts and cost, each role's cost further split into cache vs
  no-cache (`*_cache_cost_usd` + `*_no_cache_cost_usd`). The split is proportional: each run's cost is weighted by
  `(cached_tokens + cache_read_tokens + cache_write_tokens) / (input_tokens + output_tokens + cache_read_tokens +
  cache_write_tokens)` into the cache stack and the complement into no-cache. `cached_tokens` is the Codex "portion of
  input served from cache" counter and is already inside `input_tokens`, so it stays out of the denominator to avoid
  double-counting. Token-less rows attribute their full cost to no-cache. NULL buckets surface as `"unknown"`.
- `get_backend_daily_tokens` (agent-run view) — per `(day, backend)` token totals feeding the hero chart's "By
  backend" stacked-area toggle.
- `get_cost_coverage` (agent-run view) — per `cost_source` rollups carrying both runs and `total_tokens`. The
  `unknown-price` cohort is exposed verbatim (never collapsed into a generic "unknown") because it is the maintenance
  signal for the price tables in `observability/usage/prices.py`. NULL `cost_source` buckets under `"unknown"`.

**Filter contract.** The agent-run view has no `event` column (its WHERE `event = 'agent_exit'` is baked in), so
view-backed functions cannot push an `event IN (...)` clause down. They honor the dashboard's event-filter contract by
short-circuiting to empty when the operator's events selection excludes `agent_exit` (or is cleared). Rollup readers
preserve the same contract through `build_rollup_window_where`, which emits a tautologically-false predicate on a
cleared multiselect and a parameterised `IN (...)` on a non-empty one.

The rollup window helper translates the dashboard's midnight-aligned UTC `[start, end)` datetimes to `day >=
start.date() AND day < end.date()` predicates so the `(day, repo)` index drives a date-range scan. Sub-day-aligned
bounds collapse to day granularity (the rollup carries no finer resolution), but the dashboard never passes those.

**Connection model.** Each function returns a frozen dataclass or list of dataclasses. `ANALYTICS_DB_URL` unset
short-circuits every function to an empty / zero-valued result with no connection attempt, mirroring the sync's no-op
contract. Connection or query failures (driver-level psycopg errors, schema mismatches, network unreachable) are wrapped
in a single `AnalyticsReadError` whose `__cause__` preserves the underlying exception. The psycopg import is deferred to
call time inside `default_connect`; tests inject a fake `connect(db_url) -> connection` factory.

Every public reader accepts an optional `conn=` so a caller (typically the dashboard, inside an `analytics_connection`
scope) can run many reads on a single shared connection instead of paying the ~1 s psycopg handshake per call; absent
`conn=`, the open-per-call / close-in-`finally` path runs unchanged. A caller-supplied `conn=` always wins over the URL
short-circuit.

`analytics_connection(*, db_url=None, connect=None)` is a context manager that maintains a single thread-local
persistent connection. The first `with` block opens the socket (real psycopg connections open with `autocommit=True`);
subsequent `with` blocks on the same thread reuse it; a broken-connection error (`OperationalError` / `InterfaceError`)
inside the scope close-and-replaces the cached socket before re-raise. `close_thread_local_connection()` drains it
explicitly for shutdown hooks or test teardown. The thread-local cache is keyed on the resolved URL: a later `with`
block on the same thread requesting a different `db_url=` closes the stale socket first. The connection is not part of
any Streamlit cache key (a raw `psycopg.Connection` is not hashable). Close-time exceptions are logged and swallowed,
through the `orchestrator.analytics.connection` logger. That name is spelled out literally in
`observability/analytics/query/connections.py` rather than derived from the module path, so an operator log filter
selects on it regardless of which module the close lives in.

The read model is deliberately separate from the sync: `observability/analytics/sync/` owns the JSONL → Postgres write
path, while reads have a different error story and injection shape.

## Dashboard (`orchestrator/apps/analytics_dashboard.py`)

Streamlit app over the read model. Opt-in via the `dashboard` dependency group so the default `uv sync --locked` keeps
installing only the polling runtime plus `pytest`, `ruff`, and `wemake-python-styleguide`. Streamlit (and its transitive
pandas), `plotly`, and every dashboard owner the page composes — the chart owners that reach Plotly and the
plotly-free theme among them — are imported inside the pass
that reaches them — importing the launch path from a test or non-dashboard caller does not require the group to be
installed. A regression-guard test in `tests/apps/test_analytics_dashboard_launch.py` asserts that loading
`orchestrator.apps.analytics_dashboard` keeps `streamlit`, `pandas`, `plotly`, and
`orchestrator.observability.dashboard.charts` out of `sys.modules`.

**Module layout.** `orchestrator/apps/analytics_dashboard.py` is the canonical `streamlit run` target, the only one,
and the whole
page composition: the entrypoint, the three handles every pass draws with, the chrome, the unconfigured-database
refusal, the pass that opens the page on the two reads no filter narrows, and the one that draws the window they
allow. Everything beneath it is an owner under `observability/dashboard/`: no root-level module answers for any part
of this page, so a name is reached where it is defined and there is no second site a mock could be left on.
Where a patch has to land follows the call path, which
runs entirely through `observability/dashboard/`: the page reaches the
controls it opens on, the staged plan, the wave dispatch, and the render passes those drive on the owners that hold
them, so a test intercepts them with
`patch.object(page_controls | read_plan | dispatch | page_pipeline | chart_sections | page_sections, ...)`. The
Plotly toolbar every figure is drawn under is `render_config`'s own mapping, and the shapes
the pipeline
threads are `page_models`'. A card builder follows the same rule, so a case intercepting the banner stack the
first-wave pass draws patches
`patch.object(card_html, "insights_html", ...)`, and one intercepting the topbar or the filter line patches
`summary_html`. Each panel below sits the same way. Its
render is intercepted on the section owner that orders it — `chart_sections` for the five figure cards,
`page_sections` for the four beneath them — while what one draws with is the panel owner's own module-scope import, so
a case that has to intercept the adoption table, the trigger-rate one, the matrix, or either sort
parse patches `skill_panel` or `skill_trigger_panel`, and one that has to intercept the issues table, the efficiency
card, the coverage bar, or the ranking depth patches `issue_cost_panel`. The paired lifecycle bars, the
repository-spend pair beneath them, and the activity grid under both sit there too, and a figure builder is on that
list beside the card ones: the
per-stage and per-review-round builders are `stage_cost_panel`'s own module-scope imports off `charts/cost_stage.py`
and `charts/cost_review.py`, the per-repository ranking and per-day strip are `reliability_panel`'s off
`charts/cost_repo.py` and `charts/throughput.py`, and the weekday-by-hour grid is `activity_panel`'s off
`charts/heatmap.py`, rather than a
handle the pipeline hands down, so a case intercepting any of the five patches the owner that names it. Those
three read `PLOTLY_CONFIG` off `render_config` as a module attribute at call time, so a case pinning the toolbar for
any of them patches that owner as well. The
zone selectbox inside that last card is `activity_panel`'s too — the options it offers and the formatter each is
written by are its module-scope import of `filters` — so a case naming either patches there. The recent-run listing
sits
the same way as the panels: the render is intercepted on `recent_runs`, and the offset shift each `ts` is converted
through is that same owner's module-scope import of
`filters`, so a case that has to intercept that shift patches there rather than the widget module. So does the
per-issue trace beneath it: its render is intercepted on `drilldown`, while the scope its one uncached read is issued
inside
is that owner's import of `scoped_reads`, so a case that has to answer that read patches
`patch.object(scoped_reads, "scoped_read", ...)`. The hero
usage card sits that way too: the render is intercepted on `usage_panel`, and the card header it is titled by, the
usage
figure it draws, and
the Plotly defaults it hands that figure are that owner's own module-scope imports.
The repo-root `sys.path` shim that lets `streamlit run` resolve the absolute `orchestrator.*` imports comes from
`orchestrator/apps/bootstrap.py` (`ensure_repo_root_on_path`), the one both pages take it from.
`tests/apps/test_analytics_dashboard_launch.py` reproduces the analytics page's launch shape without
installing Streamlit: the file executes with only its own directory on `sys.path` (Streamlit's shape, not the repo
root's), a decoy `orchestrator` package sitting behind it on the path cannot answer for the real one, and a package
import resolves its shim qualified — so a stray top-level `bootstrap` is never probed.
The state a run carries
lives under
`orchestrator/observability/dashboard/`, split by what it decides: `windows.py` for the reported span and the presets
that name one, `filters.py` for the offset, issue, stage, and cache key it is narrowed and displayed by,
`date_controls.py` for the five slots the bar that window is picked in is laid out across together with the label and
the inline presets drawn in the first two of them, `date_filter.py` for the bar itself — the window a preset
opens the pickers on, the inclusive days they hand back, and the half-open window plus the filter-line slot the caller
leaves with — `page_controls.py` for the band that bar sits in and the load the choices made there open — the sidebar
a run is narrowed in, the offset its timestamps are displayed against, the filters those raw selections normalize
into, the controls the band is read back as, and the staged plan beneath it — `read_mode.py` for the parallel-read
knob, the flag its import binds, and the unconfigured-database
message,
`read_plan.py` for the two waves a load is staged into, the minute each cached entry is held for, and the current /
previous key pair they are issued under,
`fanout.py` for running one wave of named readers the way that flag said, `dispatch.py` for driving both waves around
the render between them — one spinner over the pair, one banner and a stop when a read cannot reach the database, and
one `dashboard.load:` line when the load comes back — `rollups.py` for the seven of those readers a
headline or lifecycle section is drawn from — with the hundred-row cap the run list among them is read under, and the
ranking depth the spend table borrows from the KPI owner — `breakdowns.py` for the six a comparison panel is drawn
from, each naming the rollup or breakdown query owner that answers it, and `skills.py` for the three a skill panel is
drawn from, each naming the skill query owner. What one read of that wave then goes through
lives beside them: `scoped_reads.py` for the thread's analytics connection it is issued inside, `filter_binding.py`
for the filters its cache key is read back as, and `static_metadata.py` for the extent and filter vocabulary a page
opens on, the TTL both are cached for, and the banner a failed one stops the run with. Above every panel that wave
feeds, `insights.py` holds the two observations a window is worth interrupting for — runs exiting non-zero, and runs
the parser could not price — the ratio each is raised at, and the banner line a crossing is rendered as; directly
beneath those, `kpis.py` holds the four numbers the headline tiles report — the move against the window before it,
the run-health tiles, the order and depth a spend table is cut to, and the share of spend that was a second pass.
Beside it, `kpi_series.py` holds the per-day spend, token, and resolved lines drawn under three of those tiles,
together with the two token totals they are counted by and the throughput pair reported beside them, and
`kpi_strip.py` the strip itself — what one is built from, the scalars a window and the one before it are reduced to,
and the four
display entries a page opens with. `sparkline_points.py` and `sparkline_html.py` are how one of those lines reaches
the tile above it — three of the strip's four tiles carry one. The first places each day in a box too narrow for an
axis, scaled to the window's own range, floored at an epsilon where a window has none, and left unprojected where the
window reported nothing at all; the second writes that projection as one polyline and the same trace closed along the
bottom edge of the box into the tint under it, holds the tile's room with an empty box where there was nothing to
project, and binds the `values` / `color` / `w` / `h` surface a caller asks for one through.
`summary_html.py` is the band that strip sits in — the banner naming what the database holds, the line under the
filter bar restating what a run narrowed it to, the pill one tile's move against the window before it is annotated
with, and the four tiles assembled around them. A rise reads red and a drop green, because these numbers are costs;
`invert` swaps the hue for the readings where up is the good direction without moving the arrow off the value's sign,
and a window with nothing to compare against or one that did not move renders no pill at all. What reaches the markup
as caller text is escaped — the banner's span label and spend figure, and each tile's label, value, and sub-line —
while the counts beside them and the filter line's own dates carry nothing to escape; the pill's `value` keyword and the
banner's six keyword-only readings are bound as explicit signatures so both still answer the call every caller spells.
`card_html.py` is what the banners and the run-health tiles reach the browser as, together with the header every panel
beneath them is titled by: the hidden mark `css.py` selects a card's container by, the banner stack whose severity
picks a class and a glyph, and the reliability strip whose numbers the calling page's own formatter renders.
`tables.py` is the markup beside it —
the compact table the four hand-rolled panels are listed in: the stylesheet each scopes to its own class, the header
and body they are assembled from, and the bar width, short repository name, missing count, and unpriced amount a cell
reports. `issue_table.py` is the first of those four: the six columns a window's costliest issues are ranked into,
the rules their in-row bars and status pills are painted by, and the readings one issue is reduced to and rendered
as — its bar a share of the widest row in that table, its review round toned from the third one on, and its run
health a `clean` pill wherever nothing failed. `skill_trigger_table.py` is the second: the six columns a
`(role, backend)` cohort's skill use is reported in, its rate bar a share of the busiest cohort in that table, and
`unknown` the label a category the sink left empty is read under. The last two are the panels an operator can reorder,
so each arrives across five owners. The third is the per-session adoption table, the page's primary skill metric:
`skill_adoption_columns.py` for the ten columns it is read across, the key each is ordered by, and the `adopt_sort` /
`adopt_dir` pair a heading writes — with the two invocation diagnostics among those columns counted apart from the
session pair so neither can be read into the rate between them; `skill_adoption_sort.py` for the parse that reads the
pair back and the repository-then-rate order a table nobody sorted opens in; `skill_adoption_headers.py` for the
header row each column is an in-tab sort link in; `skill_adoption_rows.py` for what one cell says under its five
naming columns — the source level among them, so two rows the other four read alike stay legible as the two
definitions they are — keeping the undefined rate of a skill nobody was offered apart from the real
zero of one nobody loaded; and `skill_adoption.py` for the panel those cells are sorted into, the
`TRACK_SKILL_TRIGGERS`-naming notice a window with no session evidence renders instead, and the message a caller
drawing one slice of a window's cells names in that notice's place. The fourth is the trigger
matrix, split the same way: `skill_matrix_columns.py` for the eight columns it is read across, the key
each is ordered by, and the `mtx_sort` / `mtx_dir` pair a heading writes; `skill_matrix_sort.py` for the parse that
reads that pair back — a stale column or a lone direction degrading to the default rather than raising — and the
repository-then-rate order a matrix nobody sorted opens in; `skill_matrix_headers.py` for the header row each column
is an in-tab sort link in, with the arrow only the active one carries; `skill_matrix_rows.py` for what one cell says
under those same five naming columns, its zero and derived rate toned down together while the cohort's run total
stays plain; and `skill_matrix.py` for the panel those cells are sorted into and the `TRACK_SKILL_TRIGGERS`-naming
notice a window with no catalog-backed cell renders instead.
`skill_panel.py` and `skill_trigger_panel.py` are the two cards three of those four panels are reported on. The first
is the one the page draws: the aggregate rates and the trigger matrix open it in one collapsed expander, adoption
follows in a collapsed section per source level — project, user, harness, and a fourth section for the cells no record
classified rather than a split that drops them — one notice answers a window with no `agent_exit` row for the whole
card rather than for each table in it, and the caption under those sections qualifies a window nobody adopted anything
in — naming whichever of availability, loads, or incidental references it did carry — instead of recommending a
`TRACK_SKILL_TRIGGERS` the presence of a row already proves is on. Whether that evidence was there is what the fold
above is handed, so a window where no run triggered reads as a genuine no-trigger or as a prompt to switch tracking
on accordingly. The second is the card the section led with before adoption did; nothing in the render pipeline
draws it now, and its prompt is unconditional, since trigger rates alone carry no per-session evidence to tell those
two windows apart.
`recent_runs.py` is the listing under those four panels rather than a fifth among them — the runs behind the readings
above it, projected into the columns one is scanned by and the offset the sidebar picked, drawn as `st.dataframe`
because a raw listing carries no bar, pill, or sortable heading Streamlit's own table cannot already handle. It opens
collapsed so a window's worth of rows does not push the per-issue drill-down off the screen the page ends on, and a
window with no `agent_exit` row renders the notice rather than an empty frame.
`drilldown.py` is that drill-down — one issue's events in the order they happened, which is where an operator lands
once a run in the listing raised a question the row cannot answer. It is the one page read issued outside the cached
wrappers, because it is scoped by an issue on top of the window and filters those keys are hashed from, and it still
goes through the scope owner so it runs on the socket the waves above it opened. A repository has to be picked before
a number narrows anything, since GitHub issue numbers repeat across repositories, and the section names the control
that answers it; an empty window names the repository, issue, and filters it found nothing under; and a failed read
banners itself and returns rather than stopping a page whose panels already rendered.
`drilldown_request.py` is the call shape that section is still reachable under: the seven keyword arguments a caller
outside the render pipeline names, the declared signature they are bound through — the same object the adapter
reports, so the historical shape stays one description — and the typed request they are read back as before the page
state is rebuilt from it.
`page_states.py` is what is drawn where none of those panels can be, and it holds two dead ends of different kinds. A
database nobody has ingested into has no extent to pick a window from, so there is no filter bar to offer: the banner
is drawn with every count it carries zeroed, the notice names the sync command that fills the table, and the script
stops where it stands. A window that merely matched nothing still has a page around it, so that one keeps the chrome
already rendered above it, says which way to broaden, and hands the page on to the trace at the foot of it — an
operator narrowing to one issue is exactly who lands on an empty window, and that trace is scoped by the issue on top
of the window rather than by the cache key the skipped reads share. Emitting the load line is the other half of that
hand-off: `dispatch.py` times a load off the line `run_read_waves` ends on, and a window that short-circuits the
second wave never reaches it, so this owner reports the load off the plan's own clock and the first wave alone rather
than the full inventory nobody paid for. The third render is the footer beneath a page that did draw, restating the
window span and the run count everything above it was measured over — closed on the day before the window's end,
since the reads beneath the page are issued under `ts < end` and restating `end` itself would name a day none of
those numbers covered.
`usage_panel.py` is the card above every one of those panels — the first one under the KPI strip, so it answers the
question the page is opened with: whether a day's cost tracks the work behind it. The figure carrying both readings is
the usage chart family's; this owner decides the card around it — the header naming it, the toggle deciding what it
stacks, and the rows the chart is handed for the mode an operator picked. The toggle is a two-value radio because
neither stack is the drilldown of the other: by token type is what a day's tokens went on, by backend is who spent
them. Streamlit reruns the whole script on every interaction, so the picked mode is kept in the page's own session
state under a key apart from the radio's own and the radio is seeded from it by index, since the widget takes an
option's position rather than its value. The per-backend rows are totalled per day here — the same `(day, backend)`
cell can arrive more than once, and only when the backend stack is the one being drawn, because the token-type bands
already ride on the time-series points.
Two more panels are drawn as markup rather than as a figure: `backend_card.py` for what a run on one backend
is worth — the cost of a million tokens, the cost of a run, and the share of billable input the cache answered, each
divided through one guard so a window a backend barely ran in reads zero rather than raising — and `coverage_card.py`
for how much of a window's spend the parser could price, sized by token share whenever the window carries any and by
run share only when it does not, drawn as one bar and the legend beneath it.
`stage_cost_panel.py`, `issue_cost_panel.py`, and `reliability_panel.py` are the three sections that spend is compared
across, each a pair of
7:5 columns rather than a single panel. The first pairs the two lifecycle axes — spend by workflow stage beside spend
by review cycle, each figure built by naming `charts/cost_stage.py` and `charts/cost_review.py` directly rather than
by reaching a builder off a handle — and pins both to one height taken off whichever of the two reads returned more
buckets, because a horizontal bar family sizes itself by its own row count and two panels left to size themselves
would put bars of two different thicknesses either side of one gutter. The second pairs the work with the agent that
did it:
the window's costliest issues ranked on the left, one efficiency card per backend on the right, and the coverage bar
closing that column because it qualifies the money the cards above it report — drawn only where the window carries a
cost-source split. Its two columns answer an empty window differently, since a window can carry runs the parser could
not price while a window with no `agent_exit` row had nothing to run at all. The third pairs the money with whether
the runs behind it held up: the window's spend by repository on the left, the six run-health tiles over the per-day
strip of the issues those runs resolved on the right, each figure built by naming `charts/cost_repo.py` and
`charts/throughput.py` directly. That strip is handed the window's bounds so a day nothing resolved on stands as a
zero bar, and the closing bound is the day before the window's end — the reads beneath the page are issued under
`ts < end`, so drawing through `end` itself would add a trailing day none of them covered.
`activity_panel.py` closes that run with the one card that keeps the clock instead of reducing the window to a
reading: the weekday-by-hour grid off `charts/heatmap.py`, headed by the zone its hours are read in and carrying the
selectbox that picks that zone. The control sits in the card because it changes what the figure means rather than
which rows reach it, and the offset is formatted once so the header and the x-axis cannot name different zones over
one set of cells. Nothing there shifts a timestamp: the cells arrive bucketed by the read, which is issued under the
offset the page reads back off the same session key the selectbox writes.
`page_models.py` holds the seven frozen shapes a render carries between all of that: the caller's Streamlit, pandas,
and theme handles, the selections every read is narrowed by, the controls and page they open on, what one load
answers with, and the rows, totals, and counts the paired repository-spend and run-health section is drawn from.
Streamlit reruns the whole script on every interaction, so a render is one pass and freezing those
shapes is what keeps a section from narrowing the window the sections beside it were handed. Two readings are derived
rather than stored: the issue scope answers nothing until a repository is picked, since GitHub issue numbers repeat
across repositories, and the window span is measured in whole days and floored at one, since it is the divisor of
every per-day rate.
`render_config.py` holds the Plotly configuration each figure below is handed — the hover toolbar switched off once
for the whole page rather than per call site, published as a read-only proxy every call site copies before handing it
to Plotly.
What those reads are drawn as sits one level down, under `charts/`, where `primitives.py` holds what every figure
family is built out of, `cost_layout.py` the frame the horizontal cost families share, `cost_horizontal.py` the
generic spend ranking, `cost_repo.py` the per-repository one drawn through it, `cost_stage.py` the per-stage cache
split, `cost_review.py` the per-review-round one beside it, `heatmap.py` the weekday-by-hour grid,
`throughput.py` the per-day resolved-issue strip, and
`usage_bands.py` / `usage_series.py` / `usage_axis.py` / `usage_traces.py` / `usage.py` the bands, day span, stack
heights, aligned axes, traces, and assembled hero figure the usage family draws its reads as (see **Chart builders**
below).
Nothing above these owners re-exports them: the page names each where it is defined, so a name has one home and a
mock has one place to land. Streamlit is never imported in these
helpers — `st`, the theme, and the pandas handle beside them are passed in as parameters, and the figures are the
chart owners' own rather than a handle threaded down.

```sh
uv sync --group dashboard                                  # install streamlit + plotly alongside the runtime + dev deps
uv run streamlit run orchestrator/apps/analytics_dashboard.py   # launches a local browser tab
```

**Page chrome.** A sticky topbar carries the page title with the data extent / repo / event summary on the left and the
in-range spend pill on the right. A sticky filter bar exposes `3D` / `7D` / `30D` / `All` inline presets (anchored at
the data extent's max timestamp and clamped to its min) plus two date inputs for arbitrary windows within the extent.
The sidebar surfaces a `Custom` preset fallback, a repo selector, event / stage multi-selects, and a `#123` / `123`
issue-number input.

**Caching.** Every per-filter read is wrapped in `st.cache_data` keyed by the immutable `DashboardCacheKey(start, end,
repo, events, stages, issue)`, so a filter change invalidates every cached query in lockstep. `dashboard/read_plan.py`
builds those wrappers under `WIDGET_CACHE_TTL_SECONDS = 60` (1 min), so a window nobody changes goes back to Postgres
on the first rerun after that minute rather than on every widget interaction. `get_data_extent` and
`get_filter_options` carry no filter inputs and live in argument-less wrappers under the longer
`STATIC_METADATA_TTL_SECONDS = 300` (5 min) TTL so the sidebar / topbar only re-hit Postgres when a sync run
ingests new events.

**Two-wave loading.** The 16 widget reads are staged into two waves by `dashboard/read_plan.py`:

- **First wave (6 reads).** `summary`, `prev_summary`, `ts_points`, `review_round_rows`, `throughput_rows`,
  `cost_coverage_rows` — feeds the topbar, filter meta, insight banners, and KPI strip.
- **Second wave (10 reads).** `stage_rows`, `agent_exits`, `issues_rows`, `backend_rows`, `repo_rows`, `heatmap_rows`,
  `backend_daily_rows`, `skill_adoption_rows`, `skill_rows`, `skill_matrix_rows` — feeds the rest of the body.

`dashboard/dispatch.py` drives both waves and renders the above-the-fold chrome between them on the main thread
(worker threads only return data through futures, so every `st.*` write runs on the main thread). The second wave is
skipped on an empty window. A single inline `st.spinner("Loading analytics…")` brackets both waves; a read error from
either wave surfaces as one `st.error` + `st.stop`.

**Body layout, top to bottom:**

1. Computed insight banners (failure rate ≥ 10 %, unpriced cost coverage ≥ 10 %).
2. Four-tile KPI strip — total spend, total tokens (`input + output + cache_read + cache_write`), cost / resolved
   issue, rework share — each with an inline-SVG sparkline and previous-window delta where applicable.
3. Hero `usage_over_time` stacked-area + cost-line chart with a "By token type / By backend" toggle.
4. Side-by-side `cost_by_stage` and `cost_by_review_round` cards; the stage card stacks each stage bar into no-cache +
   cache cost, and the review-round card groups development and review cost bars per round with each role's bar further
   stacked into no-cache + cache cost — so the operator can see how much per-stage and per-round spend still bypasses
   prompt caching.
5. 7/5 split: top-cost issues table (Issue with in-row cost bar, Cost, Runs, Review rds, Retries, status pill) +
   backend-efficiency cards (`$ / 1M tok`, `% cache hit`, `$ / run`) above the cost-source coverage bar (sized by token
   share).
6. Another 7/5 split: `cost_by_repo` bars + six-tile reliability panel (agent runs / success rate / resolved / rejected
   / failures / timeouts — all sourced from the same `Summary` window-wide aggregate) above the
   issues-resolved-per-day bar chart with explicit zero days backfilled.
7. 7 × 24 weekday × hour activity heatmap rendering token volume, with an in-card `UTC` offset selectbox (range `-12
   … +14`, default `UTC+7`) that controls both the heatmap bucketing and the wall-clock conversion of the `ts` column
   in the recent agent-runs table below. The widget binds to `st.session_state["tz_offset_hours"]`; the offset is read
   before the second-wave fan-out so the heatmap query buckets in the chosen zone, and the card subtitle / x-axis title
   render the matching `UTC±N` label.
8. "Skill adoption" panel — a fold-out invocation-level diagnostic above the primary per-session adoption matrix,
   which is itself split into one collapsed section per source level. The card opens on a collapsed `st.expander`
   ("Invocation-level diagnostics · per-run skill triggers") carrying the older per-run views as a clearly named
   diagnostic: the per-`(agent_role, backend)` aggregate table (`_skill_triggers_html` over
   `get_skill_trigger_rates`, showing runs, skill runs, a trigger-rate bar, and total trigger count) and, below it,
   the per-skill **trigger matrix** (`_skill_matrix_html` over `get_skill_trigger_matrix`) with columns Repo / Role /
   Backend / Skill / Level / Runs / Runs with skill / Trigger rate — the same `Level` column the adoption table
   beneath it carries, so a catalog-padded `project` row can sit beside an `unknown`-level row for a skill whose
   level neither the run nor the repository's catalog settles. The matrix folds each repo's `repo_skill_catalog` into
   the observed triggers so a skill the repo offers but no cohort fired surfaces as an explicit (muted) `0` "Runs with
   skill" cell (and a matching muted `0%` trigger rate) rather than a missing row (the cohort `Runs` total is never
   muted); its headers write `mtx_sort` / `mtx_dir` params (parsed by `parse_skill_matrix_sort`) and default to Repo
   ascending, then Trigger rate descending.
   Under that fold-out the adoption cells are drawn in one collapsed `st.expander` per source level, in the order one
   definition shadows another: "Project-level skills · defined in the repository", "User-level skills · installed for
   the operator", and "Harness-level skills · built into the CLI", each rendering the same sortable table over its own
   `level` rows. A fourth section ("Unclassified skills · no source level recorded") is drawn only when the window
   carries a cell neither the record nor the repository's catalog classified — a claude run's load of a name the repo
   never offered, or offers at two levels — so such a cell is reported rather than dropped by the split. A cell whose
   blank level the catalog does settle lands in that level's section instead, which is what keeps a claude cohort's
   sessions inside the "Project-level skills" table rather than in this one. A named level the window has no cell of
   renders a short line saying
   only that (`No user-level skill was recorded in this window.`), never the switch-naming notice, since a sibling
   section's rows already prove tracking is on.
   The table each section draws (`_skill_adoption_html` over `get_skill_adoption`) renders one row per `(repo,
   agent_role, backend, skill, level)` read-model cell with columns Repo / Role / Backend / Skill / Level / Sessions /
   Sessions using skill / Adoption rate / Invocation loads / Incidental references. `Level` is the source level the
   skill was defined at (`project` / `user` / `harness`, or `unknown` where neither the record nor the repository's
   catalog classified it) and is what decides the section a row lands in, so two rows carrying the same four names
   ahead of it are legible as the two definitions they are — a repository's own `develop` beside a same-named global
   one. A claude session, whose stream names no source directory, does not add a third such row: its unclassified
   offers and loads are filled from the catalog and merge into the cell for the definition they came from. The table
   counts skill use by **logical agent session**, not by raw run: `Sessions` is how many sessions in the cohort had
   the skill available, `Sessions using skill` the subset that loaded it, and `Adoption rate` their share
   (`adopted / sessions`, once per session). The two trailing columns are the window-scoped invocation diagnostics:
   `Invocation loads` counts the window runs that loaded the skill and `Incidental references` the window runs that
   made a path-only reference to its `SKILL.md`. The load and incidental buckets are independent, so a run that both
   loaded and inspected it increments both, and an incidental mention is a separate column that can never raise the
   adoption rate (a cell with no available session renders a muted `—` rate rather than a misleading `0%`). The read
   model caps the list at 100 rows (Sessions DESC then Sessions-using DESC then Invocations DESC) across the window's
   cells as a whole, before the level split; by default rows display sorted by Repo ascending, then Adoption rate
   descending. Each column header is a clickable sort control writing `adopt_sort` / `adopt_dir` query params (parsed
   by `parse_skill_adoption_sort`), with a ▲ / ▼ indicator; an unknown / absent param falls back to that default
   order, and every section reads that one pair, so a click reorders all of them at once.
   The three tables degrade differently with the switch off: per-session adoption only carries signal once
   `TRACK_SKILL_TRIGGERS` has recorded per-run skill fields, but the trigger-rate table still counts every
   `agent_exit` run and the matrix still shows catalog-backed zero rows (the `runs` denominator and
   `repo_skill_catalog` records do not depend on the switch). When rows are present a zero-adoption window captions a
   neutral genuine-0% result beneath the level sections (a present row proves tracking is on), an adoption window with
   no cell at all renders the adoption table's fallback notice naming the switch once, in place of those sections
   rather than inside each of them, and the matrix shows its own fallback notice when no catalog-backed matrix can be
   built (no catalog records matched and no run fired a skill).
9. Recent agent-runs table as a collapsible expander; the `ts` column is shifted to the wall-clock of the selected UTC
   offset via `shift_ts`.
10. Per-issue drill-down when a number is entered.

**Filter contract.** `build_window_where` distinguishes three cases for the event / stage selections: `None` is "no
filter on this column", a non-empty sequence emits a parameterised `IN (...)`, and an empty sequence emits a
tautologically-false predicate (`FALSE`). The event multiselect maps straight through (`event` is `NOT NULL` in the
schema). The stage multiselect routes through `resolve_stage_filter(selected, available)` because `options.stages` only
lists non-null stages: the all-selected default collapses to `None` so NULL-stage rows are included; an explicitly
cleared selection still emits `[]`; a proper subset passes through verbatim. Without this asymmetry the default
dashboard would silently exclude `stage_evaluation` rows on issues with no workflow label — and two families that
carry no `stage` at all: the repo-level `repo_skill_catalog` snapshot, and the `terminal_artifact_cleanup` result,
which is about a finished issue's artifacts rather than a workflow state. A *narrowed* stage selection still drops
all three, which is the filter working as asked rather than a gap. The issue number acts as a
SQL-level filter when a specific repo is selected AND triggers the drill-down section; with the repo filter on "All" it
stays inert (GitHub issue numbers are not unique across repos).

**Parallel read fan-out.** Setting `DASHBOARD_PARALLEL_READS=on` (or `1` / `true` / `yes`, case-insensitive) flips the
16 widget reads from sequential to a `ThreadPoolExecutor` capped at eight workers. Each worker opens its own
thread-local psycopg connection via `query/connection_cache.py`'s `analytics_connection()` — `psycopg.Connection` is
not thread-safe,
so sharing one socket across workers would corrupt the wire protocol. `dashboard/dispatch.py` emits a single INFO log
line on every dashboard load — `dashboard.load: total=X.Xs reads=16 parallel=true|false` on a full render, or
`reads=6` when the empty-window short-circuit skips the second wave — so the two paths can be A/B'd with `grep
dashboard.load streamlit.log`. That line's logger is named `orchestrator._dashboard_read_dispatch` as a pinned
literal rather than after the module holding the emit, so a handler or level selection aimed at it keeps working
across a move. An `AnalyticsReadError` raised by any worker propagates verbatim from the first failing future.

**Chart builders.** `observability/dashboard/charts/` holds pure Plotly figure builders: `usage_over_time`
(stacked-area + cost-line overlay with `mode="type"` / `mode="backend"` switch), `cost_horizontal_bars` (shared
primitive), `cost_by_repo` (thin adapter over `cost_horizontal_bars`), `cost_by_stage` (per-stage horizontal bars with
each bar stacked into no-cache + cache cost under `barmode="stack"`; the cache segment uses a translucent shade of the
stage's base color so the pair stays visibly tied to the stage, and only the outer cache segment carries the per-stage
dollar text), `cost_by_review_round` (grouped development/review bars per round, each role's bar further stacked into
no-cache + cache cost via `offsetgroup` + `barmode="relative"`; the cache segment uses a translucent shade of the role's
base color so the pair stays visibly tied to the role), `hour_weekday_heatmap` (faint-to-saturated accent gradient over
per-cell token totals, Sunday-first, with a `tz_label` parameter that annotates the x-axis — the caller passes the
matching offset to `get_hourly_heatmap` so cells already reflect that zone), and `done_per_day_bars` (resolved-per-day
bars with explicit `window_start` / `window_end` for zero-day backfill). Each builder is defined by the owner named
for its family -- `usage_over_time` / `backend_per_day` by `charts/usage.py`, the three cost adapters (`cost_by_repo` /
`cost_by_stage` / `cost_by_review_round`) by `charts/cost_repo.py`, `charts/cost_stage.py`, and
`charts/cost_review.py` with `cost_horizontal_bars` under them in `charts/cost_horizontal.py`,
`hour_weekday_heatmap` by `charts/heatmap.py`, and `done_per_day_bars` by `charts/throughput.py` --
and a panel names that owner directly. The shared low-level chart
primitives
(`empty_figure`, the money / mono-textfont / two-line-tick and panel-height / legend helpers) live under
`orchestrator/observability/dashboard/charts/primitives.py`. Every chart family names that owner directly, so the
dependency
runs one way and a direct import of any chart module is cycle-free. The frame the three horizontal cost families are
drawn in (the panel margin, the `USD` axis, the
height, and the `CostBarTrace` request one series of bars is built from) lives beside it in
`orchestrator/observability/dashboard/charts/cost_layout.py`, and `cost_horizontal_bars` itself -- with the ordering,
tinting, and flip behind its bars, and the pinned `Signature` that keeps `items` its first parameter -- in
`charts/cost_horizontal.py`. `cost_by_repo` sits on top of that ranking in `charts/cost_repo.py`, deciding only how a
repository reads: the short name its bar is labelled by with the `owner/` prefix dropped, the agent-run count on the
sub-line rather than an event count, the page accent on every bar, and the shared placeholder in its own words for a
window matching no repository. `cost_by_stage` sits beside the ranking in `charts/cost_stage.py` -- the ranking, the
full-price fallback that lets a row carrying only a total still draw at its true length, the `runs` sub-line, and the
lightening that shades a cache half from the stage's own hue, which is also where the per-review-round split gets the
shading for its own cache halves. `cost_by_review_round` is that split, in `charts/cost_review.py` -- the round order
and labels the rows are laid out and read by, the two-role sub-line beside them, the totals each role's bar is
labelled by, the four series the two roles and their two halves are described as, and the row height a panel carrying
two bars per row is sized with. The heatmap and
throughput families sit under the same package:
`orchestrator/observability/dashboard/charts/heatmap.py` builds the grid -- and draws its own empty-state annotation
over it rather than routing through the shared placeholder, because an empty heatmap is still legible -- and
`orchestrator/observability/dashboard/charts/throughput.py` the per-day strip, naming the shared placeholder for the
case that reaches it -- a caller who passed no rows and not both window bounds, since only both of them turn the
window into a calendar to draw zero bars across. A test that has to intercept a builder patches the owner named for
its family, and every builder reports that owner as its defining module.
No owner under `charts/` names Plotly at module scope: the ones that assemble a figure import it inside that call,
and an adapter like `charts/cost_repo.py`, which only shapes rows and hands them to another builder, never imports it
at all -- `from __future__ import annotations` leaves its `go.Figure` return annotation unevaluated. Either way every
owner there stays importable without the optional `dashboard` dependency group. The usage family's own shaping sits
beside those primitives:
`orchestrator/observability/dashboard/charts/usage_bands.py` holds the four bands a day is counted into, the mode its
stack is switched with, the `DailyTokenValues` table they are accumulated in, and the roll-up of a `TimeSeriesPoint`
series into one bucket per day, while `orchestrator/observability/dashboard/charts/usage_series.py` holds the day span
that roll-up produced, the `UsageChartData` / `UsageAxisRanges` shapes it travels in, the completion that gives a day
only the per-backend read saw a bucket of its own, and the height each mode measures a stack by. Above that pair,
`orchestrator/observability/dashboard/charts/usage_axis.py` holds the step count and pinned height the hero panel is
drawn at, the rounding that raises each maximum to a number the axis divides into equal steps, and the layout the
token and cost scales are assembled in -- both from zero and both cut into the same steps, so one horizontal rule
means something on either scale, with only the token axis drawing the rules -- and
`orchestrator/observability/dashboard/charts/usage_traces.py` holds what is drawn against them: the shaping that
answers a window holding nothing with no chart at all, the band a stack is added one of at a time, the two modes it is
stacked in, and the cost line overlaid on the secondary axis. Over all four,
`orchestrator/observability/dashboard/charts/usage.py` is the assembly `usage_over_time` returns -- the window shaped,
the stack added in the mode the page asked for, the cost line overlaid, and the layout merged last so the token axis
is scaled to the stack that was actually drawn, or the shared placeholder at the same pinned height when the shaping
came back with nothing to draw -- with the `backend_per_day` stub published beside it. The hero card names that one
owner and the four beneath it are reached through it. No module on that path names
Plotly at module scope, so the whole usage family imports in the default install -- and so
does every other chart family.
The compact table the most-expensive-issues and skill-trigger-rates panels — and the two sortable skill panels named
below — are drawn as lives at `observability/dashboard/tables.py`: the stylesheet each panel scopes to
itself under its own class, the header and body they are assembled from, and the bar width, short repository name,
missing count, and unpriced amount a cell reports. The most-expensive-issues panel drawn in that table is
`observability/dashboard/issue_table.py` — its six columns, the rules its in-row bars and status pills are painted
by, and the readings one issue is reduced to and rendered as. The skill-trigger-rates panel beside it is
`observability/dashboard/skill_trigger_table.py` — its own six columns, the busiest cohort its rate bars are sized
against, and the `unknown` a category the sink left empty reads as, which the adoption table's and the trigger
matrix's row projections both read off that owner directly. The sparkline drawn inside a KPI
tile is `observability/dashboard/sparkline_points.py` for where each day of a window sits — its own range, the epsilon
a flat one is floored at, and the window left unprojected — and
`observability/dashboard/sparkline_html.py` for the polyline, the tint that trace is closed into along the bottom of
the box, the empty box a window with nothing to draw still holds, and the historical
`values` / `color` / `w` / `h` surface a caller asks for one through. The chrome around that strip — the topbar, the
filter-meta line, the delta pill one tile is annotated
with, and the strip itself — is `observability/dashboard/summary_html.py`, which reaches the sparkline owner directly
for the line a tile carries. The bar the filter line sits under is `observability/dashboard/date_controls.py` for
the five slots it is laid
out across, the label naming it, and the presets it offers inline, and
`observability/dashboard/date_filter.py` for the window a preset opens its pickers on, the inclusive days they hand
back, and the bar assembling all of it; the page pipeline calls the bar on its
owner, so a test intercepting it patches `date_filter`. The band that bar sits in and the load the choices made there
open is `observability/dashboard/page_controls.py` — the sidebar a run is narrowed in and the selections it answers
with, the offset that run's timestamps are displayed against, the filters those selections normalize into, the
controls the band is read back as, and the staged plan beneath it; the app prepares its page on that owner, so a test
intercepting it patches `page_controls`.
Beside them, the insight banners, per-card header, and reliability-tile strip are built by
`observability/dashboard/card_html.py`, and the backend-efficiency cards and cost-source coverage bar by
`observability/dashboard/backend_card.py` and
`observability/dashboard/coverage_card.py`; the primary per-session skill-adoption table is
`observability/dashboard/skill_adoption_columns.py`, `skill_adoption_sort.py`, `skill_adoption_headers.py`,
`skill_adoption_rows.py`, and `skill_adoption.py` — its ten columns and the `adopt_sort` / `adopt_dir` pair its
headings write, the parse and the two orders behind a click, the header row those clicks come from, what one cell
says, and the sorted panel with the notice a window carrying no session evidence renders instead. The
invocation-level per-skill trigger matrix is
`observability/dashboard/skill_matrix_columns.py`, `skill_matrix_sort.py`, `skill_matrix_headers.py`,
`skill_matrix_rows.py`, and `skill_matrix.py` — its eight columns and the `mtx_sort` / `mtx_dir` pair its headings
write, the parse and the two orders behind a click, the header row those clicks come from, what one cell says, and
the sorted panel with the notice a window carrying no catalog-backed cell renders instead. The two cards those
tables are reported on are
`observability/dashboard/skill_panel.py` — the adoption card, the invocation views it opens on, the per-level sections
adoption is folded into beneath them, and the caption qualifying a window nobody adopted anything in — and
`observability/dashboard/skill_trigger_panel.py` — the
trigger-rate card the section led with before adoption did, and its own fold-out matrix. The listing under all four
panels is
`observability/dashboard/recent_runs.py` — the columns one run
is scanned by, the offset its timestamp is read on, the collapsed expander it is drawn inside, and the notice a window
with no `agent_exit` row renders instead — and the trace under it is `observability/dashboard/drilldown.py` — the one
page read issued outside the cached wrappers, the columns one event is traced in, and the notices a number typed
before a repository, an empty window, and a failed read are answered with. The historical call
shape that trace is still reachable under is `observability/dashboard/drilldown_request.py`. The three sections that
listing's window is
compared across are `observability/dashboard/stage_cost_panel.py` — the paired lifecycle bars, the 7:5 columns they
are laid out in, and the one height both figures are pinned to together with the row and base measurement behind it —
`observability/dashboard/issue_cost_panel.py` — the window's costliest issues ranked beside one efficiency card
per backend, the coverage bar closing that column, and the notice those cards answer a window with no run with —
and `observability/dashboard/reliability_panel.py` — the window's spend by repository beside the six run-health tiles
and the per-day strip of the issues its runs resolved, bounded by the last day the window covers rather than by its
half-open end. The card closing that run is `observability/dashboard/activity_panel.py` — the weekday-by-hour grid a
window's tokens are laid out on, the zone its hours are headed and annotated in, and the selectbox picking that zone,
keyed under the name the page reads the offset back off. The card above all of them is
`observability/dashboard/usage_panel.py` — the header it is titled by, the two-value toggle deciding what a day's
tokens are stacked by, the session key that mode survives a rerun in, and the per-day per-backend totals the second
stack is drawn from. What is drawn where none of those panels can be is
`observability/dashboard/page_states.py` — the startup state an un-ingested database is answered with and stopped on,
the notice a window matching no row renders together with the load line its skipped second wave would have carried
and the hand-off to the trace beneath, and the footer a page that did draw closes on.
What draws every one of those, and in what order, is three owners. `observability/dashboard/page_pipeline.py` holds
what the page puts on screen between its two read waves — the banner and filter line written back into the slots the
controls left, the banners a window is worth interrupting the page for, the four-tile strip beneath them, and the
staged load all three are drawn inside, whose first pass reports nothing back on a window that matched no row and is
therefore what ends a load before the second wave is paid for. `observability/dashboard/chart_sections.py` holds the
five cards a figure is drawn on in the order the page stacks them, and `observability/dashboard/page_sections.py` the
four panels beneath those cards together with the single call the whole second wave is drawn by. The app opens its
load and draws its wave on those owners, so a test intercepting either patches
`page_pipeline` or `page_sections`.
What a whole render of that page is threaded
through is `observability/dashboard/page_models.py` — the seven frozen shapes, with the issue scope and window span
read off the filters among them — and the Plotly configuration every
figure it draws is handed is `observability/dashboard/render_config.py`.

**Theme.** The plotly-free theme lives under `orchestrator/observability/dashboard/`, split by what a value is.
`palette.py` holds the chrome colors (cool gray `#f4f5f8` page, white cards, indigo accent, muted ink tints), the
semantic trio the delta pills and insight banners are tinted from, the per-token-type / per-backend / per-agent-role /
per-review-round / per-stage / per-`cost_source` maps, and the `color_for(...)` fallback a value no map covers resolves
through. `tokens.py` holds the spacing tokens, the `1480px` content max-width, and the IBM Plex Sans / Mono stacks.
`layout.py` builds the shared `base_layout(title=...)` Plotly dict; `css.py` interpolates both token owners into the
`PAGE_CSS` string the dashboard injects through `st.markdown(unsafe_allow_html=True)`; and `formatting.py` holds the
`fmt_money` / `fmt_money_exact` / `fmt_tokens` / `fmt_num` formatters. `theme.py` is the sixth owner beside them and
implements nothing: it reads all five back under one name, which is the object the analytics app hands every panel it
draws. Every value on it is the style owner's own.
`.streamlit/config.toml` mirrors the palette into Streamlit's `[theme]` and disables the `[browser]
gatherUsageStats` POST so the launch stays local-observability-only.

**Independence.** The dashboard process is independent of the polling tick: it does not open a GitHub session, does not
write to Postgres, and can be deployed off-host by repointing `ANALYTICS_DB_URL` at a managed Postgres endpoint without
changing the orchestrator's deployment.

## Empty and error states

The dashboard never raises an unhandled exception at the user — every missing-data or misconfiguration case surfaces
as a labeled banner.

- `` `ANALYTICS_DB_URL` is not configured. … `` (top-level `st.warning`, app stops) — *env* — `ANALYTICS_DB_URL`
  is unset, empty, or set to `off` / `disabled` / `none`. Set it in `.env` and **relaunch** `uv run streamlit run
  orchestrator/apps/analytics_dashboard.py` (the URL is parsed once, when the analytics settings holder is first
  imported, so a browser reload alone will not pick up the new value).
- `Could not load analytics filter options: …` (top-level `st.error`, app stops) — *DB connectivity* — The
  dashboard could not reach Postgres at startup. Confirm `docker compose ps` shows `analytics-db` healthy, that the host
  / port / credentials in `ANALYTICS_DB_URL` match `analytics-db/.env`, and that the user can connect with `psql`.
- `Analytics query failed: …` (top-level `st.error`, app stops) — *DB schema / I/O* — A read query raised
  mid-render. Most commonly the `analytics_events` table is missing — either the volume is fresh and the init script
  has not been applied (`docker compose down && docker compose up -d`) or a manual schema reapply is needed (see
  [Service layout](analytics-database.md#service-layout)).
- `No analytics events have been recorded yet. …` (top-level `st.info`, app stops) — *data* — The
  `analytics_events` table holds zero rows. Confirm the JSONL sink is on (`ANALYTICS_LOG_PATH`), that recent workflow
  activity produced records, and run `python -m orchestrator.observability.analytics.sync.cli` to populate Postgres.
- `No analytics events match the current filters.` (page banner) — *data* — The data extent is non-empty but every
  row was filtered out. Widen the window preset, pick `All` for the repo, blank the issue-number input, and confirm the
  event / stage multi-selects still have **every option selected** (an empty multi-select is the documented "show
  nothing" signal).
- `No stage data matches the current filters.` (chart annotation) — *data* — Scoped to the stage breakdown chart.
  Also empty when the only matching rows have a NULL stage (`stage_evaluation` records on issues with no workflow
  label).
- `` No `agent_exit` rows match the current filters. `` — *data* — The window contains `stage_enter` /
  `stage_evaluation` rows but no agent invocations — surfaces in the review-round chart, backend cards, cost coverage
  bar, and recent-runs expander.
- `No agent runs with recorded cost in this window.` — *data* — The top-cost issues table fell back to its empty
  state — no `(repo, issue)` pair in the window has any priced agent runs.
- `No repos match the current filters.` — *data* — The per-repo activity chart is empty for this filter combination.
- `Pick a specific repo in the sidebar before drilling into an issue number …` — *UI guard* — The issue-number
  input is inert with the repo filter on `All` because GitHub issue numbers are not unique across repos.
- ``No analytics events recorded for `<repo>#<n>` under the current filters.`` — *data / filter* — The drill-down
  query returned nothing. Either the issue number is wrong for that repo, the orchestrator has not processed it yet, or
  the event / stage multi-selects exclude every row for that issue.
- `Issue drill-down failed: …` — *DB I/O* — The drill-down query raised but the headline metrics rendered first.
  Same fixes as `Analytics query failed: …`.

If a sidebar multi-select is **explicitly cleared** (no items selected), every dependent widget falls back to "no data"
— that is the documented "show nothing for this dimension" signal. Re-select the items (or hit the `↺` reset chip
Streamlit renders on the widget) to restore the default unfiltered shape.

If `python -m orchestrator.observability.analytics.sync.cli` runs cleanly (non-zero `inserted=`) but the dashboard
still shows zero rows, double-check the `ANALYTICS_DB_URL` the sync used — passing `--db-url postgresql://other/db`
(or a different shell environment) populates a different database than the one the dashboard is reading.
