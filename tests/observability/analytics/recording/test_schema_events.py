# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Analytics event indexes and agent-run view schema tests."""

import re
import unittest
from pathlib import Path

from orchestrator.observability.analytics.sync import columns

_SCHEMA_DIR = Path(__file__).resolve().parents[4] / "analytics-db" / "init"


_SCHEMA_PATH = _SCHEMA_DIR / "01-schema.sql"

# How the view reads a row the sync stored before it derived evidence.
_UNDERIVED_READINGS = (
    r"COALESCE\(cost_completeness, 'unknown'\) AS cost_completeness",
    r"CASE WHEN cost_completeness IS NULL THEN cost_usd ELSE cost_unknown_basis_usd END AS cost_unknown_basis_usd",
    r"COALESCE\(token_cache_overlap, 'unknown'\) AS token_cache_overlap",
)

# What the agent-run view adds after `cost_source`, in its select-list order.
_VIEW_EVIDENCE_COLUMNS = (
    "cost_completeness",
    "cost_cli_reported_usd",
    "cost_anthropic_estimate_usd",
    "cost_openai_estimate_usd",
    "cost_gemini_estimate_usd",
    "cost_unknown_basis_usd",
    "anthropic_rates_verified_on",
    "openai_rates_verified_on",
    "gemini_rates_verified_on",
    "token_cache_overlap",
)


def _schema_text() -> str:
    return _SCHEMA_PATH.read_text(encoding="utf-8")


def _normalize(sql: str) -> str:
    """Collapse runs of whitespace so multi-line DDL matches regex."""
    return re.sub(r"\s+", " ", sql).strip()


def _normalized_schema() -> str:
    """Whitespace-collapsed schema DDL, shared across the contract tests."""
    return _normalize(_schema_text())


def _agent_runs_view_body() -> str:
    match = re.search(
        r"CREATE OR REPLACE VIEW analytics_agent_runs AS\s+(.*?);",
        _normalized_schema(),
    )
    assert match is not None, "analytics_agent_runs view missing"
    return match.group(1)


class SchemaIndexesTest(unittest.TestCase):
    """The dashboard's hot queries rely on these indexes; assert they
    are present and idempotent (`IF NOT EXISTS`) so a re-applied DDL
    against an existing instance does not raise.
    """

    def test_agent_exit_partial_index_present(self) -> None:
        text = _normalized_schema()
        self.assertRegex(
            text,
            r"CREATE INDEX IF NOT EXISTS analytics_events_agent_exit_idx "
            r"ON analytics_events\s*\([^)]*\)\s*"
            r"WHERE event = 'agent_exit'",
        )

    def test_stage_enter_partial_index_present(self) -> None:
        text = _normalized_schema()
        self.assertRegex(
            text,
            r"CREATE INDEX IF NOT EXISTS analytics_events_stage_enter_idx "
            r"ON analytics_events\s*\([^)]*\)\s*"
            r"WHERE event = 'stage_enter'",
        )

    def test_has_composite_event_repo_stage_ts_index(self) -> None:
        # The column order matters: equality on event / repo / stage
        # then range on ts. A reorder is a behavior change.
        text = _normalized_schema()
        self.assertRegex(
            text,
            r"CREATE INDEX IF NOT EXISTS analytics_events_event_repo_stage_ts_idx "
            r"ON analytics_events\s*\(\s*event,\s*repo,\s*stage,\s*ts\s*\)",
        )

    def test_indexes_are_idempotent(self) -> None:
        # Every CREATE INDEX in this DDL must be guarded with IF NOT
        # EXISTS so an operator running `psql -f` against an existing
        # instance does not see a duplicate-index error. Catches a
        # future contributor who copy-pastes without the guard.
        text = _schema_text()
        unguarded = re.findall(
            r"^\s*CREATE\s+(?:UNIQUE\s+)?INDEX(?!\s+IF\s+NOT\s+EXISTS)",
            text,
            flags=re.MULTILINE | re.IGNORECASE,
        )
        self.assertEqual(unguarded, [])


class AnalyticsAgentRunsViewTest(unittest.TestCase):
    """The `analytics_agent_runs` view is the backend shape the
    dashboard / read model consume. These tests pin the columns and
    derivations so a future schema change cannot silently drop a
    field the read model expects.
    """

    def test_view_is_idempotent(self) -> None:
        # CREATE OR REPLACE so re-running the init script (or a
        # `psql -f` against an instance that already has the view)
        # does not error -- mirrors the IF NOT EXISTS guard on
        # tables / indexes.
        text = _normalized_schema()
        self.assertRegex(
            text,
            r"CREATE OR REPLACE VIEW analytics_agent_runs AS",
        )

    def test_view_filters_to_agent_exit(self) -> None:
        # The view's whole point is to narrow to agent_exit rows so
        # downstream consumers do not have to repeat the predicate.
        text = _normalized_schema()
        # match the view body up to its terminating semicolon
        match = re.search(
            r"CREATE OR REPLACE VIEW analytics_agent_runs AS\s+(.*?);",
            text,
        )
        assert match is not None, "analytics_agent_runs view missing"
        body = match.group(1)
        self.assertRegex(body, r"FROM analytics_events")
        self.assertRegex(body, r"WHERE event = 'agent_exit'")

    def test_view_exposes_required_columns(self) -> None:
        # Pin every column the dashboard / read model wants -- a
        # silently-renamed column would break the dashboard, not the
        # ingest path, so the contract has to live in tests.
        text = _normalized_schema()
        expected_columns = (
            "id",
            "ts",
            "repo",
            "issue",
            "stage",
            "agent_role",
            "backend",
            "agent_spec",
            "resume_session_id",
            "session_id",
            "review_round",
            "review_round_bucket",
            "retry_count",
            "duration_s",
            "exit_code",
            "timed_out",
            "failed",
            "input_tokens",
            "output_tokens",
            "cached_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "total_tokens",
            "total_cache_tokens",
            "models",
            "model",
            "turns",
            "cost_usd",
            "has_cost",
            "cost_source",
            *_VIEW_EVIDENCE_COLUMNS,
        )
        for col in expected_columns:
            # AS-aliased derived columns end in ` AS <col>`; plain
            # passthroughs appear as a bare identifier in the select
            # list. Match either form so the assertion does not have
            # to know which is which.
            with self.subTest(column=col):
                pattern = rf"(?:\bAS {col}\b|\b{col}\b)"
                self.assertRegex(text, pattern)

    def test_view_derives_model_from_models_jsonb(self) -> None:
        # The model fallback is `models->>0` with a COALESCE so
        # GROUP BY model never blows up on a NULL key.
        text = _normalized_schema()
        self.assertRegex(text, r"COALESCE\(models->>0,\s*'unknown'\)\s+AS\s+model")

    def test_view_has_cost_is_cost_usd_not_null(self) -> None:
        # The dashboard splits "coverage-known" from "coverage-gap"
        # runs by this flag; keep it tied to cost_usd presence so a
        # cost_source semantics change cannot decouple them.
        text = _normalized_schema()
        self.assertRegex(
            text,
            r"\(cost_usd IS NOT NULL\)\s+AS\s+has_cost",
        )

    def test_view_total_cache_tokens_sums_all_three(self) -> None:
        # cache totals roll up cached + cache_read + cache_write so a
        # dashboard can plot one number; missing one of the three
        # would silently understate the figure.
        text = _normalized_schema()
        self.assertRegex(
            text,
            r"COALESCE\(cached_tokens,\s*0\)\s*"
            r"\+\s*COALESCE\(cache_read_tokens,\s*0\)\s*"
            r"\+\s*COALESCE\(cache_write_tokens,\s*0\)\s+"
            r"AS\s+total_cache_tokens",
        )


class UsageEvidenceSchemaTest(unittest.TestCase):
    """The columns the sync derives from a record's usage evidence, and what
    the agent-run view says a run cost and spent in tokens off them.
    """

    def test_each_derived_column_is_created_and_added(self) -> None:
        # Every derived column exists on a fresh table and is added to an
        # existing one, so the INSERT naming it never meets a table without it
        # after a reapply.
        text = _normalized_schema()
        table = re.search(r"CREATE TABLE IF NOT EXISTS analytics_events \((.*?)\);", text)
        assert table is not None, "analytics_events table missing"
        for column in columns.DERIVED_COLUMNS:
            with self.subTest(column=column):
                self.assertRegex(table.group(1), rf"\b{column} [A-Z]")
                self.assertRegex(text, rf"ADD COLUMN IF NOT EXISTS {column} [A-Z]")

    def test_total_tokens_is_the_stored_total(self) -> None:
        # The view's total is the non-overlapping one the sync stored, never
        # the raw counters added up again, so a cache counter already inside
        # input is not counted twice and an unknown total stays NULL.
        body = _agent_runs_view_body()
        self.assertRegex(body, r"cache_write_tokens, total_tokens, COALESCE\(cached_tokens")
        self.assertNotRegex(body, r"\bAS total_tokens\b")

    def test_evidence_trails_cost_source(self) -> None:
        # `CREATE OR REPLACE VIEW` only appends, so the evidence trails every
        # column an earlier view already had, in the order the columns stand.
        body = _agent_runs_view_body()
        positions = [body.index(f"{column}") for column in ("cost_source", *_VIEW_EVIDENCE_COLUMNS)]
        self.assertEqual(positions, sorted(positions))

    def test_an_underived_row_reads_unknown(self) -> None:
        # A row the sync stored before it derived evidence states none: it
        # reads `unknown`, its recorded amount kept under the `unknown` basis
        # rather than dropped or attributed to any provider.
        body = _agent_runs_view_body()
        for pattern in _UNDERIVED_READINGS:
            with self.subTest(pattern=pattern):
                self.assertRegex(body, pattern)
