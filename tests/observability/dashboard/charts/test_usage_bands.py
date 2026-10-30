# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How a window's series rows become one bucket of bands per day.

The bands split each row's known non-overlapping total, so a day's stack is as
tall as the known total the token tile reports: a Codex run's cached input sits
in the cache band alone, never once in its input and again in its cache, and a
run whose total is unknown is counted beside the bands rather than drawn in
them. A day's cost is its runs' cohort, folded across the day's events.
"""
from __future__ import annotations

import math
import unittest
from datetime import date
from types import MappingProxyType

from orchestrator.observability.analytics.query.overview_models import (
    TimeSeriesPoint,
)
from orchestrator.observability.dashboard.charts import usage_bands
from orchestrator.observability.usage import cost_evidence as usage_cost
from tests.observability.analytics import analytics_cohorts as cohort_cases, analytics_usage_cases as cases

_YEAR = 2026

_DAY = date(_YEAR, 5, 1)

_NEXT_DAY = date(_YEAR, 5, 2)

# The rows a usage chart is drawn from are `agent_exit` cells; the event is
# part of the key the read grouped on, not something a band is split by.
_EVENT = "agent_exit"

# One Claude run, whose cache reads and writes sit beside its input, and one
# Codex run, whose cached tokens sit inside its input: each row's known total
# with the cache and output counters inside it.
_LATER_TOKENS = 2_000


def _point(day: date, *costs, **aggregates: object) -> TimeSeriesPoint:
    """Build one series row whose runs state `costs`, defaulting the key the read grouped on."""
    cohort = cohort_cases.cohort(*costs)
    return TimeSeriesPoint(day=day, event=_EVENT, count=cohort.runs, cost=cohort, **aggregates)


_CLAUDE_POINT = _point(
    _DAY,
    cases.REPORTED,
    total_tokens=cases.CLAUDE_TOTAL,
    cache_tokens=cases.CLAUDE_CACHE,
    output_tokens=cases.CLAUDE_OUTPUT,
)

_CODEX_POINT = _point(
    _DAY,
    cases.OPENAI_ESTIMATE,
    total_tokens=cases.CODEX_TOTAL,
    cache_tokens=cases.CODEX_CACHED,
    output_tokens=cases.CODEX_OUTPUT,
    unknown_token_runs=1,
)

_TOKEN_KEYS = (
    usage_bands.INPUT_BAND,
    usage_bands.OUTPUT_BAND,
    usage_bands.CACHE_BAND,
    usage_bands.UNKNOWN_TOTALS,
)

# The day the two rows fold into: Claude's input and the input Codex's cache
# did not answer, both outputs, both caches, and the one run of unknown total.
_FOLDED_BUCKET = MappingProxyType({
    usage_bands.INPUT_BAND: float(cases.CLAUDE_INPUT + cases.CODEX_UNCACHED_INPUT),
    usage_bands.OUTPUT_BAND: float(cases.CLAUDE_OUTPUT + cases.CODEX_OUTPUT),
    usage_bands.CACHE_BAND: float(cases.CLAUDE_CACHE + cases.CODEX_CACHED),
    usage_bands.UNKNOWN_TOTALS: float(1),
})

# A bucket whose cost and unknown runs dwarf its tokens, so a height counting
# either is off by a distinguishable amount.
_LOPSIDED_BUCKET = MappingProxyType({
    **usage_bands.empty_token_bucket(),
    usage_bands.INPUT_BAND: float(cases.CLAUDE_INPUT),
    usage_bands.OUTPUT_BAND: float(cases.CLAUDE_OUTPUT),
    usage_bands.CACHE_BAND: float(cases.CLAUDE_CACHE),
    usage_bands.COST_BAND: float(_LATER_TOKENS),
    usage_bands.UNKNOWN_TOTALS: float(_LATER_TOKENS),
})


class RollUpTest(unittest.TestCase):
    """Several rows a day, the bands and the unknown runs out."""

    def test_rows_sharing_a_day_fold_into_one_bucket(self) -> None:
        daily = usage_bands.roll_up_time_series((_CLAUDE_POINT, _CODEX_POINT))
        self.assertEqual(tuple(daily), (_DAY,))
        bucket = daily[_DAY]
        self.assertEqual({band: bucket[band] for band in _TOKEN_KEYS}, _FOLDED_BUCKET)
        day_cost = cases.REPORTED_USD + cases.OPENAI_USD
        self.assertTrue(math.isclose(bucket[usage_bands.COST_BAND], day_cost))

    def test_the_stack_is_as_tall_as_the_known_total(self) -> None:
        # Cache-inclusive input is not stacked with the same cache tokens
        # again, so the three bands add up to the non-overlapping total.
        daily = usage_bands.roll_up_time_series((_CLAUDE_POINT, _CODEX_POINT))
        self.assertEqual(
            usage_bands.daily_token_total(daily[_DAY]),
            float(cases.CLAUDE_TOTAL + cases.CODEX_TOTAL),
        )

    def test_each_day_accumulates_into_its_own_bucket(self) -> None:
        daily = usage_bands.roll_up_time_series((
            _CLAUDE_POINT,
            _point(_NEXT_DAY, total_tokens=_LATER_TOKENS),
        ))
        self.assertEqual(
            [usage_bands.daily_token_total(daily[day]) for day in (_DAY, _NEXT_DAY)],
            [float(cases.CLAUDE_TOTAL), float(_LATER_TOKENS)],
        )

    def test_a_row_with_nothing_known_counts_as_zero(self) -> None:
        # A row whose runs all have an unknown total, and a row of stage events,
        # add no tokens and state no amount.
        daily = usage_bands.roll_up_time_series((
            _point(_DAY, cases.UNPRICED, unknown_token_runs=1),
            _point(_DAY),
        ))
        expected = usage_bands.empty_token_bucket()
        expected[usage_bands.UNKNOWN_TOTALS] = float(1)
        self.assertEqual(daily[_DAY], expected)


class DailyCostTest(unittest.TestCase):
    """What a day's cost is folded into, and where its line point sits."""

    def test_a_day_folds_its_events_cohorts(self) -> None:
        costs = usage_bands.daily_cost_cohorts((
            _point(_DAY, cases.REPORTED),
            _point(_DAY, cases.GEMINI_ESTIMATE, cases.UNPRICED),
            _point(_NEXT_DAY),
        ))
        self.assertEqual(costs[_DAY].runs, 3)
        self.assertEqual(costs[_DAY].evidence.basis, usage_cost.BLENDED)
        self.assertEqual(costs[_DAY].evidence.completeness, usage_cost.INCOMPLETE)
        self.assertTrue(costs[_NEXT_DAY].is_empty)

    def test_a_day_without_an_amount_plots_by_why(self) -> None:
        # Nothing to price plots at zero; usage nobody priced, or an amount
        # nobody recorded, leaves a gap rather than a zero that reads as free.
        for name, costs, plotted in (
            ("complete zero", (cases.COMPLETE_ZERO,), 0),
            ("subtotal", (cases.INCOMPLETE_SUBTOTAL,), cases.SUBTOTAL_USD),
            ("no usage", (cases.NO_USAGE,), 0),
            ("no run", (), 0),
            ("unpriced", (cases.UNPRICED,), None),
            ("unknown with no amount", (usage_cost.CostEvidence(usage_cost.UNKNOWN),), None),
        ):
            with self.subTest(day=name):
                self.assertEqual(usage_bands.plotted_spend(cohort_cases.cohort(*costs)), plotted)


class DailyTotalTest(unittest.TestCase):
    """What one day's stack is as tall as."""

    def test_cost_and_unknown_runs_stay_out(self) -> None:
        # Cost rides the secondary axis under its own range, so a total
        # carrying it would scale the token axis by a number drawn in dollars;
        # the unknown runs are a count, not tokens.
        self.assertEqual(
            usage_bands.daily_token_total(dict(_LOPSIDED_BUCKET)),
            float(cases.CLAUDE_TOTAL),
        )


if __name__ == "__main__":
    unittest.main()
