# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the four tiles above a page report, off one window's first-wave rows.

The strip is read whole rather than helper by helper, because a tile is only
right while its value, its note, its move against the window before, its
sub-line, and the line drawn under it all describe the same window -- a spend
total paired with a token sparkline is the failure this owner exists to make
impossible.

Spend is a cohort, so the cases name the cohorts a window has to keep apart --
reported-only, AGY-only, mixed-provider, incomplete, missing-basis, empty, and
zero-valued -- and read back the figure, the note naming its basis and
shortfall, and the note its move is qualified by. Tokens are the runs' known
non-overlapping totals, and a window leaving some run's total out says so.

The two readings that are not a division sit beside them: a window that
resolved nothing reports an em dash rather than a cost no issue was charged,
and a window whose review rounds recorded no spend at all reports no rework
rather than failing to draw the tile.

The theme handed in carries the formatting and palette owners' own callables,
because the page hands its own module in and a stand-in rendering would leave
these cases pinning a second set of thresholds instead of which number a tile
reports.
"""

from __future__ import annotations

import unittest
from collections.abc import Sequence
from dataclasses import replace
from types import SimpleNamespace

from orchestrator.observability.analytics.query.activity_models import (
    ThroughputDayRow,
)
from orchestrator.observability.analytics.query.cost_models import (
    ReviewRoundBucketRow,
)
from orchestrator.observability.analytics.query.overview_models import (
    Summary,
    TimeSeriesPoint,
)
from orchestrator.observability.dashboard import formatting, kpi_strip, palette, spend_text
from tests.observability.analytics import analytics_cohorts as cohort_cases, analytics_usage_cases as cases
from tests.observability.dashboard.dashboard_test_support import MAY01, MAY07

_EVENT = "agent_exit"

_LABEL_KEY = "label"

_VALUE_KEY = "value"

_NOTE_KEY = "note"

_SPARK_KEY = "spark"

_DELTA_KEY = "delta"

_DELTA_NOTE_KEY = "delta_note"

_SUB_KEY = "sub"

_TOTAL_SPEND = "Total spend"

_TOTAL_TOKENS = "Total tokens"

_COST_PER_RESOLVED = "Cost / resolved issue"

_REWORK_SHARE = "Rework share"

_SUBTOTAL = "subtotal"

# A window that spent four reported runs' worth against the two the window
# before it spent, on twice the tokens, so both delta pills read the same whole
# number.
_WINDOW_COSTS = (cases.REPORTED,) * 4

_PREVIOUS_COSTS = (cases.REPORTED,) * 2

_WINDOW_TOKENS = 40

_PREVIOUS_TOKENS = 20

_WINDOW = Summary(cost=cohort_cases.cohort(*_WINDOW_COSTS), total_tokens=_WINDOW_TOKENS)

_PREVIOUS = Summary(cost=cohort_cases.cohort(*_PREVIOUS_COSTS), total_tokens=_PREVIOUS_TOKENS)

_DOUBLED = 1.0

_MIXED_COSTS = (cases.REPORTED, cases.GEMINI_ESTIMATE, cases.BLENDED)

_UNKNOWN_TOKEN_RUNS = 2

_ONE_REPORTED = cohort_cases.cohort(cases.REPORTED)

_TWO_REPORTED = cohort_cases.cohort(cases.REPORTED, cases.REPORTED)

_FIRST_ROW_TOKENS = 20

_SECOND_ROW_TOKENS = 3

_LAST_DAY_TOKENS = 7

# Two days of activity, the first of them recorded as two event rows.
_TS_POINTS = (
    TimeSeriesPoint(day=MAY01, event=_EVENT, count=1, cost=_ONE_REPORTED, total_tokens=_FIRST_ROW_TOKENS),
    TimeSeriesPoint(day=MAY01, event=_EVENT, count=1, cost=_ONE_REPORTED, total_tokens=_SECOND_ROW_TOKENS),
    TimeSeriesPoint(day=MAY07, event=_EVENT, count=2, cost=_TWO_REPORTED, total_tokens=_LAST_DAY_TOKENS),
)

_DAILY_COST = (2 * cases.REPORTED_USD, 2 * cases.REPORTED_USD)

_DAILY_TOKENS = (float(_FIRST_ROW_TOKENS + _SECOND_ROW_TOKENS), float(_LAST_DAY_TOKENS))

_AGY_COSTS = (cases.GEMINI_ESTIMATE, cases.LATER_GEMINI_ESTIMATE)

_SHORT_COSTS = (cases.ANTHROPIC_ESTIMATE, cases.UNPRICED)

# Each cohort a window can hold and the figure its spend tile reads as.
_SPEND_READINGS = (
    ("reported only", cohort_cases.cohort(*_WINDOW_COSTS), "$1.68"),
    ("agy only", cohort_cases.cohort(*_AGY_COSTS), "$0.32"),
    ("mixed providers", cohort_cases.cohort(*_MIXED_COSTS), "$0.69"),
    ("incomplete", cohort_cases.cohort(*_SHORT_COSTS), "$0.30"),
    ("missing basis", cohort_cases.cohort(cases.ABSENT_BASIS), "$0.07"),
    ("zero", cohort_cases.cohort(cases.COMPLETE_ZERO), "$0.00"),
    ("empty", cohort_cases.cohort(), spend_text.NO_RUNS_FIGURE),
)

# A window against the one before it, and what the move between them is read with.
_MOVES = (
    ("one basis", cohort_cases.cohort(*_WINDOW_COSTS), ""),
    (_SUBTOTAL, cohort_cases.cohort(cases.REPORTED, cases.UNPRICED), _SUBTOTAL),
    ("agy against reported", cohort_cases.cohort(cases.GEMINI_ESTIMATE), "bases differ"),
    ("missing basis", cohort_cases.cohort(cases.ABSENT_BASIS), "completeness unknown, bases differ"),
)

# The runs of unknown token total each window holds, and the notes the token
# tile and its move then carry.
_TOKEN_SUBTOTALS = (
    ("all known", 0, 0, ("", "")),
    ("current short", _UNKNOWN_TOKEN_RUNS, 0, ("subtotal: token total unknown for 2 runs", _SUBTOTAL)),
    ("previous short", 0, _UNKNOWN_TOKEN_RUNS, ("", _SUBTOTAL)),
)

_DAILY_DONE = (2, 0)

_THROUGHPUT_ROWS = (
    ThroughputDayRow(day=MAY01, resolved=2, rejected=1),
    ThroughputDayRow(day=MAY07, resolved=0, rejected=1),
)

_RESOLVED = 2

_REJECTED = 2

# Three of the eight review-round dollars were a second pass over work already
# done, which the tile rounds to a whole percent.
_INITIAL_ROUND_COST = 5.0

_REWORK_COST = 3.0

_REVIEW_ROWS = (
    ReviewRoundBucketRow(
        bucket="0", runs=2, total_cost_usd=_INITIAL_ROUND_COST,
    ),
    ReviewRoundBucketRow(bucket="1", runs=1, total_cost_usd=_REWORK_COST),
)

_REVIEW_COST = 8.0

_DAYS_IN_WINDOW = 2


# The theme handle a page hands in, as its formatters and hues.
_THEME = SimpleNamespace(
    ACCENT=palette.ACCENT,
    TOKEN_TYPE_COLORS=palette.TOKEN_TYPE_COLORS,
    fmt_money=formatting.fmt_money,
    fmt_money_exact=formatting.fmt_money_exact,
    fmt_tokens=formatting.fmt_tokens,
)


def _inputs(
    review_rows: Sequence[ReviewRoundBucketRow] = _REVIEW_ROWS,
    *,
    summary: Summary = _WINDOW,
    previous: Summary = _PREVIOUS,
) -> kpi_strip.KpiInputs:
    """One window's first-wave rows, as the page pipeline binds them."""
    return kpi_strip.KpiInputs(
        theme=_THEME,
        summary=summary,
        prev_summary=previous,
        ts_points=_TS_POINTS,
        throughput_rows=_THROUGHPUT_ROWS,
        review_round_rows=review_rows,
        days_in_window=_DAYS_IN_WINDOW,
    )


def _by_label(inputs: kpi_strip.KpiInputs) -> dict:
    """The strip's entries keyed by the label each tile is drawn under."""
    entries, _, _ = kpi_strip.build_kpi_strip_data(inputs)
    return {entry[_LABEL_KEY]: entry for entry in entries}


def _spend_tiles(cohort, previous=_PREVIOUS.cost) -> tuple[dict, dict]:
    """The spend and per-resolved tiles of a window whose spend is `cohort`."""
    inputs = _inputs(summary=Summary(cost=cohort), previous=Summary(cost=previous))
    entries = _by_label(inputs)
    return entries[_TOTAL_SPEND], entries[_COST_PER_RESOLVED]


class KpiTotalsTest(unittest.TestCase):
    """The window and the one before it, with the counts its tiles report."""

    def test_both_windows_are_reduced_together(self) -> None:
        totals = kpi_strip.kpi_totals(_inputs())
        self.assertIs(totals.current, _WINDOW)
        self.assertIs(totals.previous, _PREVIOUS)
        self.assertAlmostEqual(totals.spend, 4 * cases.REPORTED_USD)
        self.assertAlmostEqual(totals.spend_delta, _DOUBLED)
        self.assertEqual((totals.resolved, totals.rejected), (_RESOLVED, _REJECTED))
        self.assertAlmostEqual(totals.review_cost, _REVIEW_COST)
        self.assertAlmostEqual(totals.rework_cost, _REWORK_COST)

    def test_no_stated_amount_has_no_move(self) -> None:
        # A window whose runs stated no amount -- or a window before it that
        # did not -- has no percentage to report rather than a move to or from
        # a zero nobody stated.
        for current, previous in (
            ((cases.UNPRICED,), _PREVIOUS_COSTS),
            (_WINDOW_COSTS, ()),
            (_WINDOW_COSTS, (cases.NO_USAGE,)),
        ):
            inputs = _inputs(
                summary=Summary(cost=cohort_cases.cohort(*current)),
                previous=Summary(cost=cohort_cases.cohort(*previous)),
            )
            with self.subTest(current=len(current), previous=len(previous)):
                self.assertIsNone(kpi_strip.kpi_totals(inputs).spend_delta)


class SpendTileTest(unittest.TestCase):
    """The spend tiles name their basis and shortfall, and their move keeps both."""

    def test_spend_is_divided_by_the_resolved(self) -> None:
        self.assertEqual(
            _by_label(_inputs())[_COST_PER_RESOLVED][_VALUE_KEY], "$0.84",
        )

    def test_an_unresolved_window_has_no_ratio(self) -> None:
        # Nothing was resolved, so there is no per-issue cost to report: an em
        # dash says so, where a `$0.00` would read as issues resolved for free.
        totals = replace(kpi_strip.kpi_totals(_inputs()), resolved=0)
        self.assertEqual(kpi_strip.cost_per_resolved(totals), "—")

    def test_no_stated_amount_reads_as_its_spend(self) -> None:
        # Resolved issues whose runs went unpriced cost an amount nobody
        # stated, which is not a zero.
        _, per_resolved = _spend_tiles(cohort_cases.cohort(cases.UNPRICED))
        self.assertEqual(per_resolved[_VALUE_KEY], "unpriced")

    def test_each_cohort_reads_with_its_basis(self) -> None:
        for name, cohort, figure in _SPEND_READINGS:
            spend, per_resolved = _spend_tiles(cohort)
            with self.subTest(cohort=name):
                self.assertEqual(spend[_VALUE_KEY], figure)
                self.assertEqual(spend[_NOTE_KEY], spend_text.spend_note(cohort))
                self.assertEqual(per_resolved[_NOTE_KEY], spend_text.spend_note(cohort, amounts=False))

    def test_a_blended_window_lists_its_parts(self) -> None:
        mixed = cohort_cases.cohort(*_MIXED_COSTS)
        spend, per_resolved = _spend_tiles(mixed, previous=mixed)
        self.assertEqual(
            spend[_NOTE_KEY],
            "blended: CLI-reported $0.52 + Gemini API token estimate $0.12 + OpenAI API token estimate $0.05",
        )
        self.assertEqual(
            per_resolved[_NOTE_KEY],
            "blended: CLI-reported + Gemini API token estimate + OpenAI API token estimate",
        )
        self.assertEqual(spend[_DELTA_NOTE_KEY], "blended")

    def test_a_move_keeps_the_qualifications(self) -> None:
        # A percentage between a subtotal and a complete window, or between two
        # windows on different bases, is annotated rather than shown bare.
        for name, cohort, note in _MOVES:
            spend, _ = _spend_tiles(cohort)
            with self.subTest(pair=name):
                self.assertIsNotNone(spend[_DELTA_KEY])
                self.assertEqual(spend[_DELTA_NOTE_KEY], note)

    def test_an_empty_window_states_no_spend(self) -> None:
        spend, per_resolved = _spend_tiles(cohort_cases.cohort())
        self.assertEqual(
            (spend[_VALUE_KEY], spend[_NOTE_KEY], spend[_DELTA_KEY], spend[_SUB_KEY]),
            (spend_text.NO_RUNS_FIGURE, spend_text.NO_RUNS_NOTE, None, ""),
        )
        self.assertEqual(per_resolved[_VALUE_KEY], spend_text.NO_RUNS_FIGURE)


class KpiStripDataTest(unittest.TestCase):
    """The four tiles, and the throughput pair handed back beside them."""

    def test_the_four_tiles_report_the_window(self) -> None:
        entries = _by_label(_inputs())
        self.assertEqual(entries[_TOTAL_SPEND][_VALUE_KEY], "$1.68")
        self.assertEqual(entries[_TOTAL_SPEND][_NOTE_KEY], "CLI-reported")
        self.assertEqual(entries[_TOTAL_SPEND][_SUB_KEY], "$0.84/day")
        self.assertEqual(entries[_TOTAL_TOKENS][_VALUE_KEY], "40")
        self.assertEqual(entries[_TOTAL_SPEND][_DELTA_KEY], _DOUBLED)
        self.assertEqual(entries[_TOTAL_TOKENS][_DELTA_KEY], _DOUBLED)
        self.assertEqual(
            entries[_COST_PER_RESOLVED][_SUB_KEY], "2 resolved · 2 rejected",
        )
        self.assertEqual(entries[_REWORK_SHARE][_VALUE_KEY], "38%")
        self.assertEqual(
            entries[_REWORK_SHARE][_SUB_KEY], "$3 in review rounds >= 1",
        )

    def test_a_known_subtotal_and_its_move_say_so(self) -> None:
        # The token tile counts known totals, so a window leaving some run's
        # total out -- or a window before it that did -- says it is a subtotal.
        for name, current, previous, notes in _TOKEN_SUBTOTALS:
            tokens = _by_label(_inputs(
                summary=replace(_WINDOW, unknown_token_runs=current),
                previous=replace(_PREVIOUS, unknown_token_runs=previous),
            ))[_TOTAL_TOKENS]
            with self.subTest(case=name):
                self.assertEqual((tokens[_VALUE_KEY], tokens[_DELTA_KEY]), ("40", _DOUBLED))
                self.assertEqual((tokens[_NOTE_KEY], tokens[_DELTA_NOTE_KEY]), notes)

    def test_the_sparklines_follow_the_days(self) -> None:
        # Each line is plotted over the days the activity series recorded, so a
        # tile and the line under it describe the same window.
        entries = _by_label(_inputs())
        self.assertEqual(tuple(entries[_TOTAL_SPEND][_SPARK_KEY]), _DAILY_COST)
        self.assertEqual(
            tuple(entries[_TOTAL_TOKENS][_SPARK_KEY]), _DAILY_TOKENS,
        )
        self.assertEqual(
            tuple(entries[_COST_PER_RESOLVED][_SPARK_KEY]), _DAILY_DONE,
        )
        self.assertIsNone(entries[_REWORK_SHARE][_SPARK_KEY])

    def test_the_throughput_pair_comes_back(self) -> None:
        _, resolved, rejected = kpi_strip.build_kpi_strip_data(_inputs())
        self.assertEqual((resolved, rejected), (_RESOLVED, _REJECTED))

    def test_an_unreviewed_window_has_no_rework(self) -> None:
        # No review round recorded any spend, so there is nothing to take a
        # share of and the tile reports none rather than failing to divide.
        entries = _by_label(_inputs(review_rows=()))
        self.assertEqual(entries[_REWORK_SHARE][_VALUE_KEY], "0%")


if __name__ == "__main__":
    unittest.main()
