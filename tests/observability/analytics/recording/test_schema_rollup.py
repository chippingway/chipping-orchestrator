# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Analytics daily-rollup definition, aggregation, and index tests."""

import re
import unittest
from pathlib import Path

_SCHEMA_DIR = Path(__file__).resolve().parents[4] / "analytics-db" / "init"


_SCHEMA_PATH = _SCHEMA_DIR / "01-schema.sql"

_BASIS_AMOUNTS = (
    "cost_cli_reported_usd",
    "cost_anthropic_estimate_usd",
    "cost_openai_estimate_usd",
    "cost_gemini_estimate_usd",
)

_UNKNOWN_RUNS_PATTERN = (
    r"WHEN event = 'agent_exit' AND COALESCE\(cost_completeness, 'unknown'\) = 'unknown' "
    r"THEN 1 ELSE 0 END\)\s+AS\s+cost_unknown_runs"
)

_UNKNOWN_AMOUNT_PATTERN = (
    r"WHEN cost_completeness IS NULL THEN cost_usd ELSE cost_unknown_basis_usd END\)"
    r"\s+AS\s+cost_unknown_basis_usd"
)

_UNKNOWN_TOTAL_RUNS_PATTERN = (
    r"WHEN event = 'agent_exit' AND total_tokens IS NULL THEN 1 ELSE 0 END\)"
    r"\s+AS\s+total_tokens_unknown_runs"
)

_RATE_DATE_ARRAYS = (
    "anthropic_rates_verified_on",
    "openai_rates_verified_on",
    "gemini_rates_verified_on",
)

_DATE_UNION_AGGREGATE = (
    r"CREATE OR REPLACE AGGREGATE analytics_rate_dates\(DATE\[\]\) \( SFUNC = array_cat, STYPE = DATE\[\], "
    r"FINALFUNC = analytics_sorted_dates \)"
)

# The date union the rollup and the read model fold verification dates by, defined so a reapply replaces it.
_DATE_UNION_DEFINITIONS = (
    r"CREATE OR REPLACE FUNCTION analytics_sorted_dates\(days DATE\[\]\) RETURNS DATE\[\]",
    r"SELECT array_agg\(DISTINCT day ORDER BY day\) FROM unnest\(days\) AS day",
    _DATE_UNION_AGGREGATE,
)

# Every additive evidence column a reader regroups the rollup by.
_EVIDENCE_AGGREGATES = (
    "cost_complete_runs",
    "cost_incomplete_runs",
    "cost_no_usage_runs",
    "cost_unknown_runs",
    *_BASIS_AMOUNTS,
    "cost_unknown_basis_usd",
    *_RATE_DATE_ARRAYS,
    "total_tokens",
    "cache_tokens_in_total",
    "output_tokens_in_total",
    "total_tokens_unknown_runs",
)


def _schema_text() -> str:
    return _SCHEMA_PATH.read_text(encoding="utf-8")


def _normalize(sql: str) -> str:
    """Collapse runs of whitespace so multi-line DDL matches regex."""
    return re.sub(r"\s+", " ", sql).strip()


def _normalized_schema() -> str:
    """Whitespace-collapsed schema DDL, shared across the contract tests."""
    return _normalize(_schema_text())


def _rollup_view_body() -> str:
    # Materialized views terminate at the SELECT's semicolon; isolate
    # the body so column-presence assertions cannot accidentally
    # match text from the surrounding `analytics_agent_runs` view or
    # the index DDL.
    match = re.search(
        r"CREATE MATERIALIZED VIEW IF NOT EXISTS "
        r"analytics_daily_rollup AS\s+(.*?);",
        _normalized_schema(),
    )
    assert match is not None, "analytics_daily_rollup view missing"
    return match.group(1)


class AnalyticsDailyRollupDefinitionTest(unittest.TestCase):
    """The `analytics_daily_rollup` materialized view is the pre-aggregated
    target the dashboard reads from instead of scanning the raw run
    tables. These tests pin the create statement's idempotency, the key
    columns, and the aggregate columns so a refactor that drops the
    timeout/failure counts or token sums (which the dashboard's
    reliability tiles and KPI strip read from) fails in the hermetic
    suite -- before an operator sees a broken dashboard.
    """

    def test_view_is_idempotent_create(self) -> None:
        # `CREATE MATERIALIZED VIEW IF NOT EXISTS` matches the
        # idempotency contract every other CREATE in this DDL upholds:
        # an operator running `psql -f` against an existing instance
        # picks up the view on first apply and no-ops on every reapply.
        # Postgres CREATE MATERIALIZED VIEW does not support OR REPLACE,
        # so IF NOT EXISTS is the only available guard.
        text = _normalized_schema()
        self.assertRegex(
            text,
            r"CREATE MATERIALIZED VIEW IF NOT EXISTS analytics_daily_rollup",
        )

    def test_view_reads_from_analytics_events(self) -> None:
        body = _rollup_view_body()
        self.assertRegex(body, r"FROM analytics_events")

    def test_view_groups_by_required_key_columns(self) -> None:
        # The key has to include `issue` because every dashboard read
        # accepts an issue filter; without it an issue-scoped read
        # would double-count. `cost_source` is in the key so the
        # cost-coverage panel can read from the rollup without
        # decomposing the `unknown-price` / `no-usage` / `reported` /
        # `estimated` cohorts after the fact.
        body = _rollup_view_body()
        for key_col in (
            "repo",
            "issue",
            "event",
            "stage",
            "backend",
            "cost_source",
        ):
            with self.subTest(column=key_col):
                # GROUP BY column listed verbatim; the day expression
                # is asserted separately because it carries a cast.
                self.assertRegex(body, rf"\b{key_col}\b")
        # `day` is derived from `ts AT TIME ZONE 'UTC'`::date -- the
        # cast normalises naive / non-UTC timestamps so the rollup is
        # consistent across writers.
        self.assertRegex(
            body,
            r"\(ts AT TIME ZONE 'UTC'\)::date\s+AS\s+day",
        )

    def test_view_exposes_required_aggregate_columns(self) -> None:
        # Every aggregate the dashboard / read model wants to read off
        # the rollup must be present. A silently-dropped aggregate
        # would force a fallback to the raw events table, which is
        # what Layer 4 exists to avoid.
        body = _rollup_view_body()
        for col in (
            "total_input_tokens",
            "total_output_tokens",
            "total_cached_tokens",
            "total_cache_read_tokens",
            "total_cache_write_tokens",
            "total_cost_usd",
            "duration_s_sum",
            "duration_s_count",
            "failed_count",
            "timed_out_count",
            "event_count",
            *_EVIDENCE_AGGREGATES,
        ):
            with self.subTest(column=col):
                self.assertRegex(body, rf"\bAS\s+{col}\b")

    def test_every_verification_date_is_kept(self) -> None:
        # A group keeps each distinct date its estimates were priced at, not
        # only the earliest and latest: the aggregate unions the rows' sorted
        # arrays, and folds the rollup's own arrays again for a read
        # regrouping its rows.
        text = _normalized_schema()
        for pattern in _DATE_UNION_DEFINITIONS:
            with self.subTest(pattern=pattern):
                self.assertRegex(text, pattern)
        body = _rollup_view_body()
        for column in _RATE_DATE_ARRAYS:
            with self.subTest(column=column):
                self.assertRegex(body, rf"analytics_rate_dates\({column}\)\s+AS\s+{column}\b")
        self.assertLess(text.index("AGGREGATE analytics_rate_dates"), text.index("MATERIALIZED VIEW IF NOT EXISTS"))


class AnalyticsDailyRollupAggregationTest(unittest.TestCase):
    """The `analytics_daily_rollup` materialized view is the pre-aggregated
    target the dashboard reads from instead of scanning the raw run
    tables. These tests pin the create statement's idempotency, the key
    columns, and the aggregate columns so a refactor that drops the
    timeout/failure counts or token sums (which the dashboard's
    reliability tiles and KPI strip read from) fails in the hermetic
    suite -- before an operator sees a broken dashboard.
    """

    def test_view_duration_count_uses_not_null_filter(self) -> None:
        # `duration_s_count` is the row count where duration_s is
        # populated -- not the raw row count. Without that, a consumer
        # recovering `AVG(duration_s)` as `SUM/COUNT` would divide by
        # the wrong denominator on rows where duration was NULL.
        body = _rollup_view_body()
        self.assertRegex(
            body,
            r"SUM\(CASE WHEN duration_s IS NOT NULL THEN 1 ELSE 0 END\)\s+"
            r"AS\s+duration_s_count",
        )

    def test_failed_count_requires_nonzero_exit(self) -> None:
        body = _rollup_view_body()
        # Non-zero exit_code is the failure signal; NULL exit_code
        # stays excluded so a `stage_enter` row never counts as a
        # failure.
        self.assertRegex(
            body,
            r"SUM\(CASE WHEN exit_code IS NOT NULL AND exit_code <> 0 "
            r"THEN 1 ELSE 0 END\)\s+AS\s+failed_count",
        )

    def test_timeout_count_uses_agent_exit(self) -> None:
        body = _rollup_view_body()
        # The reliability "Timeouts" tile reads this aggregate; it must
        # be scoped to `event='agent_exit'` so a `stage_enter` row with
        # a stale `timed_out` JSONB extra (impossible today, but the
        # filter is the defensive layer) can never inflate the count.
        self.assertRegex(
            body,
            r"SUM\(CASE WHEN event = 'agent_exit' AND timed_out = TRUE "
            r"THEN 1 ELSE 0 END\)\s+AS\s+timed_out_count",
        )

    def test_view_event_count_is_row_count(self) -> None:
        body = _rollup_view_body()
        self.assertRegex(body, r"COUNT\(\*\)\s+AS\s+event_count")

    def test_each_basis_is_summed_on_its_own(self) -> None:
        # `cost_source` cannot say what a group cost, so every basis keeps its
        # own sum -- named as on the events table, so one reading serves both.
        body = _rollup_view_body()
        for column in _BASIS_AMOUNTS:
            with self.subTest(column=column):
                self.assertRegex(body, rf"SUM\({column}\)\s+AS\s+{column}\b")

    def test_an_underived_exit_counts_as_unknown(self) -> None:
        # An `agent_exit` row the sync stored before it derived evidence states
        # none: it counts as an `unknown` run and its recorded amount is summed
        # under the `unknown` basis, while the other events count as neither.
        body = _rollup_view_body()
        for pattern in (_UNKNOWN_RUNS_PATTERN, _UNKNOWN_AMOUNT_PATTERN):
            with self.subTest(pattern=pattern):
                self.assertRegex(body, pattern)

    def test_tokens_keep_the_unknown_beside_the_known(self) -> None:
        # A sum of the known totals is a subtotal wherever a run's total is
        # unknown, so the count of those runs rides beside it, and the cache
        # and output tokens a split of the total stacks are those inside known
        # totals.
        body = _rollup_view_body()
        for pattern in (
            r"SUM\(total_tokens\)\s+AS\s+total_tokens",
            r"WHEN total_tokens IS NOT NULL THEN COALESCE\(cached_tokens, 0\)",
            r"WHEN total_tokens IS NOT NULL THEN COALESCE\(output_tokens, 0\) END\)\s+AS\s+output_tokens_in_total",
            _UNKNOWN_TOTAL_RUNS_PATTERN,
        ):
            with self.subTest(pattern=pattern):
                self.assertRegex(body, pattern)


class AnalyticsDailyRollupIndexTest(unittest.TestCase):
    """The `analytics_daily_rollup` materialized view is the pre-aggregated
    target the dashboard reads from instead of scanning the raw run
    tables. These tests pin the create statement's idempotency, the key
    columns, and the aggregate columns so a refactor that drops the
    timeout/failure counts or token sums (which the dashboard's
    reliability tiles and KPI strip read from) fails in the hermetic
    suite -- before an operator sees a broken dashboard.
    """

    def test_unique_index_treats_nulls_as_equal(self) -> None:
        # `REFRESH MATERIALIZED VIEW CONCURRENTLY` requires a unique
        # index. NULLS NOT DISTINCT (Postgres 15+) collapses NULL
        # stage / backend / cost_source values into one row -- the same
        # way GROUP BY already does -- so the index is genuinely
        # unique across the view's contents. The current sync uses the
        # non-concurrent variant, so the index is forward-compat
        # plumbing rather than load-bearing today.
        text = _normalized_schema()
        self.assertRegex(
            text,
            r"CREATE UNIQUE INDEX IF NOT EXISTS "
            r"analytics_daily_rollup_key_idx\s+"
            r"ON analytics_daily_rollup\s*"
            r"\(\s*day,\s*repo,\s*issue,\s*event,\s*stage,\s*backend,"
            r"\s*cost_source\s*\)\s+NULLS NOT DISTINCT",
        )

    def test_supporting_day_repo_index_present(self) -> None:
        # Day-range scan support for the dashboard's window-bounded
        # reads. Without this, a `WHERE day BETWEEN x AND y` predicate
        # would fall back to a sequential scan over the rollup once it
        # grew past a few thousand rows.
        text = _normalized_schema()
        self.assertRegex(
            text,
            r"CREATE INDEX IF NOT EXISTS "
            r"analytics_daily_rollup_day_repo_idx\s+"
            r"ON analytics_daily_rollup\s*\(\s*day,\s*repo\s*\)",
        )
