# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a window's headline numbers say at the edges the arithmetic has.

Each of the four reductions is read where it can go wrong rather than on a
typical window: a delta with nothing to divide by, a window with no runs to
take a success rate over, a ranking whose ties the database broke under a
collation Python does not share, and a breakdown whose buckets sit on both
sides of the initial pass. The
plain window is pinned beside each, because an edge answer only means something
while the ordinary one is still right.

The tile cases read the tones as well as the counts, since the tone is what
paints the tile: a failure count that arrived correct under a neutral tone is a
panel reading as healthy while reporting failures. The ranking cases read whole
rows rather than a first one, because the order is the cost read's own, total
down to the pair that names an issue, and a check on the head alone would pass
while the tail was re-sorted under it.
"""

from __future__ import annotations

import unittest

from orchestrator.observability.analytics.query.cost_models import (
    ReviewRoundBucketRow,
)
from orchestrator.observability.analytics.query.overview_models import Summary
from orchestrator.observability.analytics.query.run_models import IssueSummaryRow
from orchestrator.observability.dashboard import kpis
from tests.observability.analytics import analytics_cohorts as cohort_cases
from tests.observability.dashboard.dashboard_test_support import (
    MAY01,
    MAY02,
    utc_midnight,
)

# The labels the six tiles are keyed by, which is also the order the panel
# renders them in.
_AGENT_RUNS = "Agent runs"

_SUCCESS_RATE = "Success rate"

_RESOLVED = "Resolved"

_REJECTED = "Rejected"

_FAILURES = "Failures"

_TIMEOUTS = "Timeouts"

# The CSS class each count is painted through once it crosses zero.
_WARN = "warn"

_BAD = "bad"

_NEUTRAL = ""

# A window holding far more agent runs than the recent-runs read is capped at,
# so a tile summing that read would miss most of both counts.
_WINDOW_RUNS = 250

_WINDOW_FAILURES = 4

_WINDOW_TIMEOUTS = 17

_WINDOW_RESOLVED = 12

_WINDOW_REJECTED = 2

# A quarter more and a quarter less than the window before it.
_GROWN = 125.0

_SHRUNK = 75.0

_BASELINE = 100.0

_QUARTER = 0.25

# A window with runs but nothing wrong with them.
_HEALTHY_RUNS = 20

_REPO_A = "acme/a"

_REPO_B = "acme/b"

# Two repositories PostgreSQL's default `en_US.utf8` collation orders by their
# letters, skipping the dot, so `acme/ab` comes first; Python's code-point order
# counts the dot, which sorts below every letter, and puts `acme/a.c` first.
_COLLATED_FIRST = "acme/ab"

_COLLATED_SECOND = "acme/a.c"

_STAGE = "implementing"

# The amounts the read ranked its rows by, costliest first.
_HIGH_COST = 1.0

_MID_COST = 0.5

# One initial-pass round, mixed across providers, and an incomplete review
# round beside it: each keeps its bases and the runs it leaves unpriced.
_INITIAL_COSTS = cohort_cases.NAMED_COSTS["mixed providers"]

_REWORK_COSTS = cohort_cases.NAMED_COSTS["incomplete"]

_ROUND_ONE = "1"

# The two buckets whose runs are not a second pass: the initial development
# round, and the runs whose review round was never recorded.
_NOT_REWORK_BUCKETS = ("0", "unknown")


def _summary(**counts: int) -> Summary:
    """A window whose agent-run totals are all the tiles read."""
    return Summary(**counts)


def _tiles(summary: Summary, **throughput: int) -> dict:
    """`reliability_tile_data` triples projected to `{label: (value, tone)}`."""
    return {
        label: (tile_value, tone)
        for tile_value, label, tone in kpis.reliability_tile_data(
            summary, **throughput,
        )
    }


def _issue(repo: str, number: int, cost: float | None) -> IssueSummaryRow:
    """An issue row carrying only the columns the ranking orders on."""
    return IssueSummaryRow(
        repo=repo,
        issue=number,
        event_count=1,
        first_seen=utc_midnight(MAY01),
        last_seen=utc_midnight(MAY02),
        latest_stage=_STAGE,
        agent_exits=1,
        stated_cost_usd=cost,
    )


class KpiDeltaTest(unittest.TestCase):
    """The relative move a tile is annotated with, against the window before."""

    def test_a_move_is_read_in_both_directions(self) -> None:
        moves = ((_GROWN, _QUARTER), (_SHRUNK, -_QUARTER))
        for current, expected in moves:
            with self.subTest(current=current):
                self.assertAlmostEqual(
                    kpis.kpi_delta(current, _BASELINE), expected,
                )

    def test_an_unusable_baseline_has_no_delta(self) -> None:
        # Nothing to divide by, so the page hides the indicator rather than
        # rendering an infinity. The negative baseline is listed beside zero
        # because these columns are counts and spend: one arriving below zero
        # is a broken read, not a window that shrank.
        for previous in (0, -_BASELINE):
            with self.subTest(previous=previous):
                self.assertIsNone(kpis.kpi_delta(_HEALTHY_RUNS, previous))


class ReliabilityTileTest(unittest.TestCase):
    """The six tiles a window's run health is read off."""

    def test_every_count_comes_off_the_window(self) -> None:
        tiles = _tiles(
            _summary(
                total_agent_runs=_WINDOW_RUNS,
                failed_agent_runs=_WINDOW_FAILURES,
                timed_out_agent_runs=_WINDOW_TIMEOUTS,
            ),
            resolved=_WINDOW_RESOLVED,
            rejected=_WINDOW_REJECTED,
        )
        self.assertEqual(tiles[_AGENT_RUNS][0], _WINDOW_RUNS)
        self.assertEqual(tiles[_FAILURES], (_WINDOW_FAILURES, _WARN))
        self.assertEqual(tiles[_TIMEOUTS], (_WINDOW_TIMEOUTS, _BAD))
        self.assertEqual(tiles[_RESOLVED][0], _WINDOW_RESOLVED)
        self.assertEqual(tiles[_REJECTED], (_WINDOW_REJECTED, _WARN))

    def test_an_empty_window_still_renders(self) -> None:
        # No runs to take a rate over: the panel reports 0% so an operator can
        # confirm the window really is empty, rather than failing to draw.
        tiles = _tiles(_summary())
        self.assertEqual(tiles[_AGENT_RUNS][0], 0)
        self.assertEqual(tiles[_SUCCESS_RATE][0], "0%")
        self.assertEqual(tiles[_TIMEOUTS][0], 0)

    def test_a_clean_window_reads_neutral(self) -> None:
        tiles = _tiles(_summary(total_agent_runs=_HEALTHY_RUNS))
        self.assertEqual(tiles[_SUCCESS_RATE][0], "100%")
        self.assertEqual(tiles[_FAILURES][1], _NEUTRAL)
        self.assertEqual(tiles[_TIMEOUTS][1], _NEUTRAL)
        self.assertEqual(tiles[_REJECTED][1], _NEUTRAL)


class TopExpensiveIssuesTest(unittest.TestCase):
    """The rows the "where did spend go" table is drawn from: the read's, in its order."""

    def test_the_reads_order_is_kept(self) -> None:
        # The read ranks in SQL and breaks a tie on the repository under the
        # database's collation. Sorting the rows again by code point would put
        # `acme/a.c` ahead of `acme/ab`, which tie on amount and activity, so
        # nothing here sorts them: the tie -- and an issue stating no amount,
        # below them -- is drawn as the database ranked it.
        rows = (
            _issue(_REPO_B, 2, _HIGH_COST),
            _issue(_COLLATED_FIRST, 1, _MID_COST),
            _issue(_COLLATED_SECOND, 1, _MID_COST),
            _issue(_REPO_A, 3, None),
        )
        self.assertEqual(kpis.top_expensive_issues(rows), list(rows))

    def test_the_ranking_is_cut_to_its_depth(self) -> None:
        rows = (
            _issue(_REPO_B, 2, _HIGH_COST),
            _issue(_REPO_A, 1, _MID_COST),
            _issue(_REPO_A, 3, None),
        )
        ranked_head = list(rows[:2])
        self.assertEqual(kpis.top_expensive_issues(rows, limit=2), ranked_head)
        self.assertEqual(kpis.top_expensive_issues(rows, limit=0), [])


class ReworkTotalsTest(unittest.TestCase):
    """Which review-round buckets the rework share is measured over."""

    def test_only_a_later_round_counts_as_rework(self) -> None:
        # The initial round and the unrecorded one are both spend the window
        # holds and neither is a second pass, so each lands in the total alone;
        # both halves are cohorts, so a share taken of them can say what its
        # amounts are short of.
        for bucket in _NOT_REWORK_BUCKETS:
            with self.subTest(bucket=bucket):
                total, rework = kpis.rework_totals((
                    ReviewRoundBucketRow(
                        bucket=bucket, runs=3, developer_cost=cohort_cases.cohort(*_INITIAL_COSTS),
                    ),
                    ReviewRoundBucketRow(
                        bucket=_ROUND_ONE, runs=3, reviewer_cost=cohort_cases.cohort(*_REWORK_COSTS),
                    ),
                ))
                self.assertEqual(total, cohort_cases.cohort(*_INITIAL_COSTS, *_REWORK_COSTS))
                self.assertEqual(rework, cohort_cases.cohort(*_REWORK_COSTS))

    def test_an_empty_breakdown_holds_no_run(self) -> None:
        # No round means no run rather than a zero of spend.
        total, rework = kpis.rework_totals(())
        self.assertTrue(total.is_empty)
        self.assertTrue(rework.is_empty)

if __name__ == "__main__":
    unittest.main()
