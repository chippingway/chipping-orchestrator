# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The cohorts, scans, and database calls the live usage-evidence test is driven by.

Each cohort is one issue's `agent_exit` records, so a scan narrowed to the issue reads the cohort, and each scan pairs
a cost fragment with a token fragment over one target. The expected answer for a cohort is what the Python readers
fold its records to, so a scan that agrees with it agrees with every other usage surface.
"""
from __future__ import annotations

import os
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from orchestrator.observability.analytics.query import breakdown_reads, cost_cohorts, rollup_reads, token_totals
from orchestrator.observability.analytics.sync import run
from orchestrator.observability.usage import cost_evidence as usage_cost, token_evidence as usage_tokens
from tests.observability.analytics import analytics_usage_cases as cases
from tests.observability.analytics.sync.sync_test_support import ENCODING, jsonl_log

TEST_DB_URL_ENV = "ANALYTICS_TEST_DB_URL"

_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]

SCHEMA_PATH = _REPOSITORY_ROOT / "analytics-db" / "init" / "01-schema.sql"

_LEGACY_COST = 0.07

UNDERIVED_ISSUE = 16

_CLAUDE = "claude"

_CODEX = "codex"

_AGY = "agy"

_AGY_ISSUE = 11

_MIXED_ISSUE = 12

_INCOMPLETE_ISSUE = 13

_ABSENT_BASIS_ISSUE = 14

_NO_USAGE_ISSUE = 15

_THREE_DATES_ISSUE = 17

_PROVIDER_ISSUE = 21

COHORTS = (
    (
        _AGY_ISSUE,
        (
            cases.usage_record(_AGY_ISSUE, cases.GEMINI_ESTIMATE, cases.UNSETTLED),
            cases.usage_record(_AGY_ISSUE, cases.LATER_GEMINI_ESTIMATE, cases.UNSETTLED),
        ),
    ),
    (
        _MIXED_ISSUE,
        (
            cases.usage_record(_MIXED_ISSUE, cases.REPORTED, cases.DISJOINT, backend=_CLAUDE),
            cases.usage_record(_MIXED_ISSUE, cases.OPENAI_ESTIMATE, cases.WITHIN_INPUT, backend=_CODEX),
            cases.usage_record(_MIXED_ISSUE, cases.BLENDED, cases.WITHIN_INPUT, backend=_CODEX),
        ),
    ),
    (
        _INCOMPLETE_ISSUE,
        (
            cases.usage_record(_INCOMPLETE_ISSUE, cases.ANTHROPIC_ESTIMATE, cases.DISJOINT),
            cases.usage_record(_INCOMPLETE_ISSUE, cases.INCOMPLETE_SUBTOTAL, cases.DISJOINT),
            cases.usage_record(_INCOMPLETE_ISSUE, cases.UNPRICED, cases.DISJOINT),
        ),
    ),
    (
        _ABSENT_BASIS_ISSUE,
        (
            cases.usage_record(_ABSENT_BASIS_ISSUE, cases.COMPLETE_ZERO, cases.DISJOINT),
            cases.unevidenced_record(_ABSENT_BASIS_ISSUE, cost_usd=_LEGACY_COST, cache_read_tokens=9),
        ),
    ),
    (
        _NO_USAGE_ISSUE,
        (cases.usage_record(_NO_USAGE_ISSUE, cases.NO_USAGE, cases.NOTHING_OBSERVED),),
    ),
    (
        _THREE_DATES_ISSUE,
        tuple(
            cases.usage_record(_THREE_DATES_ISSUE, estimate, cases.WITHIN_INPUT)
            for estimate in cases.THREE_DATED_ESTIMATES
        ),
    ),
)

# One run per provider, so a token read shows each overlap: Claude's cache counters add, Codex's cached input is
# already inside its input, and Antigravity's cache reads overlap nothing known.
_PROVIDER_RUNS = (
    cases.usage_record(_PROVIDER_ISSUE, cases.REPORTED, cases.DISJOINT, backend=_CLAUDE),
    cases.usage_record(_PROVIDER_ISSUE, cases.OPENAI_ESTIMATE, cases.WITHIN_INPUT, backend=_CODEX),
    cases.usage_record(_PROVIDER_ISSUE, cases.GEMINI_ESTIMATE, cases.UNSETTLED, backend=_AGY),
)

# The bands the overview's series splits those runs' known total into -- the total, its unknown runs, the cache and
# output inside it, and the uncached input left -- so Codex's cached input is stacked once.
PROVIDER_BANDS = (
    cases.CLAUDE_TOTAL + cases.CODEX_TOTAL,
    1,
    cases.CLAUDE_CACHE + cases.CODEX_CACHED,
    cases.CLAUDE_OUTPUT + cases.CODEX_OUTPUT,
    cases.CLAUDE_INPUT + cases.CODEX_UNCACHED_INPUT,
)

# What the three token reads answer over those runs: each backend's known total and unknown runs, the one hour they
# fell in, and each cost source's runs and unknown runs.
PROVIDER_TOKEN_ANSWERS = (
    {
        _AGY: (0, 1),
        _CLAUDE: (cases.CLAUDE_TOTAL, 0),
        _CODEX: (cases.CODEX_TOTAL, 0),
    },
    [(cases.CLAUDE_TOTAL + cases.CODEX_TOTAL, 1)],
    {usage_cost.REPORTED_SOURCE: (1, 0), usage_cost.ESTIMATED_SOURCE: (2, 1)},
)

_SCANS = (
    ("analytics_agent_runs", cost_cohorts.RUN_COST_COHORT_SQL, token_totals.RUN_TOKEN_TOTAL_SQL),
    ("analytics_events", cost_cohorts.EVENT_COST_COHORT_SQL, token_totals.EVENT_TOKEN_TOTAL_SQL),
    ("analytics_daily_rollup", cost_cohorts.ROLLUP_COST_COHORT_SQL, token_totals.ROLLUP_TOKEN_TOTAL_SQL),
)

# Each target's cost and token cells for one issue, in the order `_scan_answer` reads them.
_COHORT_READS = MappingProxyType({
    target: f"SELECT {cost_cells}, {token_cells} FROM {target} WHERE issue = %s"
    for target, cost_cells, token_cells in _SCANS
})

SCAN_TARGETS = tuple(_COHORT_READS)

_UNDERIVED_RUN = (
    "INSERT INTO analytics_events (ts, repo, issue, event, cost_usd, cost_source, input_tokens, output_tokens) "
    + f"VALUES (now(), 'owner/repo', {UNDERIVED_ISSUE}, 'agent_exit', {_LEGACY_COST}, 'estimated', 10, 5)"
)

_UNDERIVED_STAGE = (
    "INSERT INTO analytics_events (ts, repo, issue, event) "
    + f"VALUES (now(), 'owner/repo', {UNDERIVED_ISSUE}, 'stage_enter')"
)

UNDERIVED_ROWS = (_UNDERIVED_RUN, _UNDERIVED_STAGE, "REFRESH MATERIALIZED VIEW analytics_daily_rollup")


@dataclass(frozen=True)
class LiveDatabase:
    """The disposable database one live test runs against, and the calls it is driven through."""

    db_url: str

    @classmethod
    def from_environment(cls) -> LiveDatabase:
        """The database `ANALYTICS_TEST_DB_URL` names, or a skip when none is named or no driver is installed."""
        db_url = os.environ.get(TEST_DB_URL_ENV, "").strip()
        if not db_url:
            raise unittest.SkipTest(f"{TEST_DB_URL_ENV} not set; live Postgres integration test skipped.")
        database = cls(db_url)
        database.execute(("SELECT 1",))
        return database

    def execute(self, statements: tuple[str, ...]) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                for statement in statements:
                    cur.execute(statement)
            conn.commit()

    def reset(self) -> None:
        """Apply the schema an operator applies, then empty the events table under it."""
        self.execute((SCHEMA_PATH.read_text(encoding=ENCODING), "TRUNCATE analytics_events RESTART IDENTITY"))

    def replay_twice(self) -> tuple:
        """Replay every cohort and a stage row in one of their issues, then the same file again."""
        written = [record for _issue, cohort in COHORTS for record in cohort]
        # A stage row states no usage, so no scan may count it.
        written.append(cases.stage_record(_MIXED_ISSUE))
        with jsonl_log(written) as path:
            run.sync_jsonl_to_postgres(log_path=path, db_url=self.db_url)
            return len(written), run.sync_jsonl_to_postgres(log_path=path, db_url=self.db_url)

    def scan_answers(self, issue: int) -> dict[str, tuple]:
        """Each scan's answer for one issue: the runs counted, their reduced cost, and the known and unknown tokens."""
        with self._connect() as conn, conn.cursor() as cur:
            return {
                target: _scan_answer(cur.execute(query, (issue,)).fetchone())
                for target, query in _COHORT_READS.items()
            }

    def provider_token_answers(self) -> tuple:
        """What the three token-only reads answer once the provider runs are replayed."""
        with jsonl_log(list(_PROVIDER_RUNS)) as path:
            run.sync_jsonl_to_postgres(log_path=path, db_url=self.db_url)
        backend_cells = breakdown_reads.get_backend_daily_tokens(db_url=self.db_url, issue=_PROVIDER_ISSUE)
        hour_cells = breakdown_reads.get_hourly_heatmap(db_url=self.db_url, issue=_PROVIDER_ISSUE)
        coverage = breakdown_reads.get_cost_coverage(db_url=self.db_url, issue=_PROVIDER_ISSUE)
        return (
            {cell.backend: (cell.total_tokens, cell.unknown_token_runs) for cell in backend_cells},
            [(cell.total_tokens, cell.unknown_token_runs) for cell in hour_cells],
            {row.cost_source: (row.runs, row.unknown_token_runs) for row in coverage},
        )

    def _connect(self):
        try:
            import psycopg
        except ImportError as exc:
            raise unittest.SkipTest(f"psycopg not available: {exc}") from exc
        return psycopg.connect(self.db_url)


def folded_answer(records: tuple[dict, ...]) -> tuple:
    """What the Python readers fold `records` to, in the shape a scan's answer is read in."""
    folded = usage_cost.reduce_costs(map(usage_cost.recorded_cost, records))
    totals = [usage_tokens.non_overlapping_total(record) for record in records]
    known = sum(total for total in totals if total is not None)
    return len(records), _rounded(folded), (known, totals.count(None))


def overview_answers(database: LiveDatabase, issue: int) -> tuple:
    """What the overview's three rollup reads answer for one issue, each in the shape `folded_answer` is read in.

    The window's summary, the window a delta is measured against, and the day series folded back into one cohort.
    """
    summary = rollup_reads.get_summary(db_url=database.db_url, issue=issue)
    previous = rollup_reads.get_kpi_prev(db_url=database.db_url, issue=issue)
    points = rollup_reads.get_time_series(db_url=database.db_url, issue=issue)
    day = cost_cohorts.fold_cohorts(point.cost for point in points)
    day_tokens = (
        sum(point.total_tokens for point in points),
        sum(point.unknown_token_runs for point in points),
    )
    return (
        (summary.cost.runs, _rounded(summary.cost.evidence), (summary.total_tokens, summary.unknown_token_runs)),
        (previous.cost.runs, _rounded(previous.cost.evidence), (previous.total_tokens, previous.unknown_token_runs)),
        (day.runs, _rounded(day.evidence), day_tokens),
    )


def overview_bands(database: LiveDatabase) -> tuple:
    """The provider runs' series, after `provider_token_answers` replayed them, as the bands a stack draws."""
    points = rollup_reads.get_time_series(db_url=database.db_url, issue=_PROVIDER_ISSUE)
    return tuple(
        sum(getattr(point, field) for point in points)
        for field in ("total_tokens", "unknown_token_runs", "cache_tokens", "output_tokens", "uncached_input_tokens")
    )


def underived_answer() -> tuple:
    """A row stored with no evidence columns: one `unknown` run holding its amount, its token total unknown."""
    underived = usage_cost.CostEvidence(
        usage_cost.UNKNOWN,
        (usage_cost.CostContribution(usage_cost.UNKNOWN_BASIS, _LEGACY_COST),),
    )
    return 1, _rounded(underived), (0, 1)


def _scan_answer(row: tuple) -> tuple:
    cohort = cost_cohorts.cost_cohort(row)
    tokens = tuple(int(cell) for cell in row[cost_cohorts.COST_COHORT_WIDTH:])
    return cohort.runs, _rounded(cohort.evidence), tokens


def _rounded(evidence: usage_cost.CostEvidence) -> tuple:
    """The evidence with each amount rounded past the float noise a NUMERIC sum and a Python sum differ by."""
    parts = (
        (part.basis, round(part.amount_usd, 9), part.rates_verified_on)
        for part in evidence.contributions
    )
    return evidence.completeness, tuple(parts)
