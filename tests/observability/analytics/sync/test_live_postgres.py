# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the replay and the schema agree on, against a real Postgres."""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from typing import NamedTuple

from orchestrator.observability.analytics.sync import run
from tests.observability.analytics.analytics_assertions import assert_row_fields
from tests.observability.analytics.sync.sync_test_support import (
    AGENT_EXIT,
    ENCODING,
    jsonl_log,
    sample_record,
)

# Opt-in: most CI runners and dev shells have no Postgres, and a hermetic suite
# must never assume one.
_TEST_DB_URL_ENV = "ANALYTICS_TEST_DB_URL"

# Four levels up from this module: the schema the assertions are written
# against is the one an operator applies out of the repository.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]

_ISSUE_KEY = "issue"

_STAGE_IMPLEMENTING = "implementing"

_ROLLUP_ISSUE = 7

_VIEW_ISSUE = 42

_LATE_FAILURE_ISSUE = 71

# One size reading the gate could not take, as it reaches this sink: the
# family every refused reading is written under, the step it stopped at, and
# the line that step wrote once the transport had scrubbed its own stderr.
_LATE_FAILURE = "late_failure"

_MEASUREMENT_FAILED = "measurement_failed"

_MEASUREMENT_STEP = "base_absent"

_FAILURE_DETAIL = "fatal: could not read Username for 'https://github.com'"

_VIEW_DURATION_S = 12.5

_VIEW_INPUT_TOKENS = 300

_VIEW_OUTPUT_TOKENS = 150

_VIEW_CACHED_TOKENS = 50

_VIEW_CACHE_READ_TOKENS = 20

_VIEW_COST_USD = 0.0042

_ROLLUP_DURATION_S = 4.0

_ROLLUP_DURATION_S_SECONDARY = 6.0

_ROLLUP_INPUT_TOKENS = 200

_ROLLUP_OUTPUT_TOKENS = 50

_ROLLUP_OUTPUT_TOKENS_SECONDARY = 80

_ROLLUP_COST_USD = 0.2

_DEDUP_DURATION_S = 3.0

_DEDUP_DURATION_S_SECONDARY = 1.5


class _AgentRunProjection(NamedTuple):
    model: str
    total_tokens: int | None
    total_cache: int
    bucket: str
    failed: bool
    has_cost: bool
    cost_source: str


class _DailyRollupProjection(NamedTuple):
    total_in: int
    total_out: int
    total_cached: int
    total_cache_read: int
    total_cache_write: int
    total_cost: object
    duration_sum: float
    duration_count: int
    failed_count: int
    timed_out_count: int
    event_count: int


def _sync_live_records(test_case, db_url: str, records: list[dict]) -> None:
    """Replay `records` into the live database and assert they all landed."""
    with jsonl_log(records) as path:
        test_case.assertEqual(
            run.sync_jsonl_to_postgres(log_path=path, db_url=db_url).inserted,
            len(records),
        )


def _fetch_live_row(db_url: str, query: str, issue: int):
    import psycopg

    with psycopg.connect(db_url) as connection, connection.cursor() as cursor:
        cursor.execute(query, (issue,))
        return cursor.fetchone()


def _expected_rollup(records: list[dict]) -> dict[str, object]:
    return {
        "total_in": sum(record["input_tokens"] for record in records),
        "total_out": sum(record["output_tokens"] for record in records),
        "total_cached": sum(record["cached_tokens"] for record in records),
        "total_cache_read": sum(record["cache_read_tokens"] for record in records),
        "total_cache_write": sum(record["cache_write_tokens"] for record in records),
        "duration_sum": sum(record["duration_s"] for record in records),
        "duration_count": len(records),
        "failed_count": sum(record["exit_code"] != 0 for record in records),
        "timed_out_count": sum(record["timed_out"] for record in records),
        "event_count": len(records),
    }


class LiveSchemaTest(unittest.TestCase):
    """End-to-end DDL, insert, and derivation against a real Postgres, opted
    into with `ANALYTICS_TEST_DB_URL=<libpq URL>`.

    The dedup pass is what makes the partial-versus-plain index distinction
    concrete: Postgres only accepts `ON CONFLICT (content_hash)` as the arbiter
    when the index is non-partial, so a change that re-partials it fails the
    second run here rather than in an operator's cron log. The two view passes
    compile what the text checks over the schema can only match: a typo in a
    derivation or a wrong CASE predicate fails here even where the regex still
    passes.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.db_url = os.environ.get(_TEST_DB_URL_ENV, "").strip()
        if not cls.db_url:
            raise unittest.SkipTest(
                f"{_TEST_DB_URL_ENV} not set; live Postgres integration "
                "test skipped. Set it to a libpq URL pointing at the "
                "compose service (or any disposable Postgres) to run."
            )
        try:
            import psycopg
        except ImportError as exc:
            raise unittest.SkipTest(f"psycopg not available: {exc}")
        assert psycopg is not None

    def test_a_replayed_file_inserts_once_and_dedupes(self) -> None:
        self._apply_schema()
        records = [
            sample_record(issue=1, stage="ready"),
            sample_record(issue=2, event=AGENT_EXIT, duration_s=_DEDUP_DURATION_S),
            sample_record(
                issue=3,
                event="stage_evaluation",
                stage="validating",
                duration_s=_DEDUP_DURATION_S_SECONDARY,
                result="ok",
            ),
        ]
        with jsonl_log(records) as path:
            first = run.sync_jsonl_to_postgres(log_path=path, db_url=self.db_url)
            self.assertEqual(first.inserted, len(records))
            self.assertEqual(first.skipped_duplicate, 0)
            self.assertEqual(self._row_count(), len(records))

            second = run.sync_jsonl_to_postgres(log_path=path, db_url=self.db_url)
            self.assertEqual(second.inserted, 0)
            self.assertEqual(second.skipped_duplicate, len(records))
            self.assertEqual(self._row_count(), len(records))

    def test_the_agent_runs_view_derives_its_fields(self) -> None:
        self._apply_schema()
        agent_run = sample_record(
            issue=_VIEW_ISSUE,
            event=AGENT_EXIT,
            stage=_STAGE_IMPLEMENTING,
            agent_role="developer",
            backend="codex",
            review_round=4,
            retry_count=1,
            duration_s=_VIEW_DURATION_S,
            exit_code=0,
            timed_out=False,
            input_tokens=_VIEW_INPUT_TOKENS,
            output_tokens=_VIEW_OUTPUT_TOKENS,
            cached_tokens=_VIEW_CACHED_TOKENS,
            cache_read_tokens=_VIEW_CACHE_READ_TOKENS,
            cache_write_tokens=10,
            models=["gpt-5-codex"],
            cost_usd=_VIEW_COST_USD,
            cost_source="estimated",
        )
        _sync_live_records(self, self.db_url, [agent_run])
        row = _fetch_live_row(
            self.db_url,
            "SELECT model, total_tokens, total_cache_tokens, "
            "review_round_bucket, failed, has_cost, cost_source "
            "FROM analytics_agent_runs WHERE issue = %s",
            agent_run[_ISSUE_KEY],
        )
        self.assertIsNotNone(row)
        assert_row_fields(
            self,
            _AgentRunProjection(*row),
            {
                "model": agent_run["models"][0],
                # The record states no token evidence and carries nonzero
                # cache counters, so nothing settles whether they overlap its
                # input: the total is unknown rather than either guess.
                "total_tokens": None,
                "total_cache": (
                    agent_run["cached_tokens"]
                    + agent_run["cache_read_tokens"]
                    + agent_run["cache_write_tokens"]
                ),
                "bucket": "3-5",
                "failed": False,
                "has_cost": True,
                "cost_source": "estimated",
            },
        )

    def test_a_refused_reading_lands_in_extras(self) -> None:
        # The table has no column for either field and needs none: anything
        # outside `PROMOTED_COLUMNS` lands in `extras JSONB`, so widening the
        # late record is an emitter change rather than a migration. The stage
        # beside them is the control -- it IS promoted, so a row carrying it
        # in its own column and these two in the blob is the split working.
        self._apply_schema()
        refused = sample_record(
            issue=_LATE_FAILURE_ISSUE,
            event=_LATE_FAILURE,
            stage=_STAGE_IMPLEMENTING,
            failure=_MEASUREMENT_FAILED,
            measurement_failure=_MEASUREMENT_STEP,
            detail=_FAILURE_DETAIL,
        )
        _sync_live_records(self, self.db_url, [refused])
        row = _fetch_live_row(
            self.db_url,
            "SELECT stage, extras->>'failure', "
            "extras->>'measurement_failure', extras->>'detail' "
            "FROM analytics_events WHERE issue = %s",
            refused[_ISSUE_KEY],
        )
        self.assertEqual(
            row,
            (
                _STAGE_IMPLEMENTING,
                _MEASUREMENT_FAILED,
                _MEASUREMENT_STEP,
                _FAILURE_DETAIL,
            ),
        )

    def test_the_daily_rollup_catches_up(self) -> None:
        # Two runs on the same UTC day with matching key columns: the post-
        # commit rebuild is what the summed token, cost, and duration columns
        # and the reliability counts the dashboard reads come from.
        self._apply_schema()
        successful_run = sample_record(
            issue=_ROLLUP_ISSUE,
            event=AGENT_EXIT,
            stage=_STAGE_IMPLEMENTING,
            backend="claude",
            cost_source="reported",
            duration_s=_ROLLUP_DURATION_S,
            exit_code=0,
            timed_out=False,
            input_tokens=100,
            output_tokens=_ROLLUP_OUTPUT_TOKENS,
            cached_tokens=5,
            cache_read_tokens=3,
            cache_write_tokens=2,
            cost_usd=0.1,
        )
        failed_run = sample_record(
            issue=successful_run[_ISSUE_KEY],
            event=AGENT_EXIT,
            stage=_STAGE_IMPLEMENTING,
            backend="claude",
            cost_source="reported",
            ts="2026-05-25T13:30:00+00:00",
            duration_s=_ROLLUP_DURATION_S_SECONDARY,
            exit_code=1,
            timed_out=True,
            input_tokens=_ROLLUP_INPUT_TOKENS,
            output_tokens=_ROLLUP_OUTPUT_TOKENS_SECONDARY,
            cached_tokens=10,
            cache_read_tokens=4,
            cache_write_tokens=1,
            cost_usd=_ROLLUP_COST_USD,
        )
        runs = [successful_run, failed_run]
        _sync_live_records(self, self.db_url, runs)
        row = _fetch_live_row(
            self.db_url,
            "SELECT total_input_tokens, total_output_tokens, "
            "total_cached_tokens, total_cache_read_tokens, "
            "total_cache_write_tokens, total_cost_usd, "
            "duration_s_sum, duration_s_count, "
            "failed_count, timed_out_count, event_count "
            "FROM analytics_daily_rollup WHERE issue = %s",
            successful_run[_ISSUE_KEY],
        )
        self.assertIsNotNone(row)
        projection = _DailyRollupProjection(*row)
        assert_row_fields(self, projection, _expected_rollup(runs))
        # The schema stores cost as NUMERIC(20, 10), so the sum comes back as a
        # Decimal; compare as floats rather than on exact decimal equality.
        self.assertAlmostEqual(
            float(projection.total_cost),
            sum(run_record["cost_usd"] for run_record in runs),
            places=6,
        )

    def _apply_schema(self) -> None:
        # The `IF NOT EXISTS` guards make this safe to re-run; the truncate is
        # what gives the dedup assertions a known starting state.
        import psycopg

        schema_path = _REPOSITORY_ROOT / "analytics-db" / "init" / "01-schema.sql"
        with psycopg.connect(self.db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(schema_path.read_text(encoding=ENCODING))
                cur.execute("TRUNCATE analytics_events RESTART IDENTITY")
            conn.commit()

    def _row_count(self) -> int:
        import psycopg

        with psycopg.connect(self.db_url) as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM analytics_events")
            row = cur.fetchone()
        return int(row[0]) if row else 0


if __name__ == "__main__":
    unittest.main()
