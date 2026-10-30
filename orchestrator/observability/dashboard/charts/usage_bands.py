# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a day of usage is counted into before any of it is drawn.

The series a usage figure is built from arrives as one row per `(day, event)`,
so several rows land on the same date. The roll-up here is the single place
those rows become a day: every point is added into the bands its day already
carries, together with the runs whose token total is unknown and the amount
its runs state.

The bands split each row's known non-overlapping token total, never its raw
counters: the cache band is the cache counters inside that total, the output
band its output, and the input band what is left -- the input no cache
answered. A stack of the three is therefore exactly as tall as the known total
the token tile reports, and a Codex run's cached tokens, which its provider
counts inside its input, sit in the cache band alone rather than in both. A run
whose total the evidence leaves unknown is in no band, since nothing says
whether its cache counts sit inside its input; it is counted under
`UNKNOWN_TOTALS` instead, so the day can be marked as a subtotal.

The per-backend stack arrives from a read of its own, issued in a later wave
than the series, so it carries its own count of the runs whose total is
unknown: `BackendDailyTokens` reads as a mapping of each day to its backends'
known totals -- what the stack, its axis, and its day span walk -- with that
read's unknown runs per day beside it. A sync landing between the two waves can
leave the series and the per-backend read disagreeing about a day, so the
marker over a stack is counted off the read that stack was drawn from.

The band names are declared here rather than spelled at each call site,
because the same keys are the accumulator's slots, the stack's trace order, and
the input to the axis maximum -- a second spelling of "cache" would roll up
into a band no trace reads. `BACKEND_MODE` sits with them because the mode a
page switches the stack with is compared in more than one owner.

A day's cost is its runs' cost cohort, folded across the day's events with
`fold_cohorts` so the hover can word it with its basis and completeness. The
amount it plots at is every basis's contribution added -- the amount the
headline states -- and a day whose runs stated none plots at zero only where
there was nothing to price; an unpriced day, or one whose runs recorded an
amount nowhere, leaves a gap in the line rather than a zero that reads as free
work.

The daily total is tokens only. Cost rides the figure's secondary axis under
its own range, so folding it into the stack's height would scale the token
axis by a number drawn in dollars.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from orchestrator.observability.analytics.query.cost_cohorts import CostCohort, fold_cohorts
from orchestrator.observability.analytics.query.overview_models import (
    TimeSeriesPoint,
)
from orchestrator.observability.usage import cost_evidence as usage_cost

INPUT_BAND = "input"
OUTPUT_BAND = "output"
CACHE_BAND = "cache"
COST_BAND = "cost"
UNKNOWN_TOTALS = "unknown_totals"
BACKEND_MODE = "backend"

DailyTokenValues = dict[date, dict[str, float]]


@dataclass(frozen=True)
class BackendDailyTokens(Mapping[date, Mapping[str, float]]):
    """Each day's known token total per backend, and the runs of unknown total the per-backend read counted that day.

    It reads as the mapping of day to backend totals the per-backend stack is drawn from; `unknown_runs` is that same
    read's count of the runs each day's stack leaves out.
    """

    tokens: Mapping[date, Mapping[str, float]]
    unknown_runs: Mapping[date, int]

    def __getitem__(self, day: date) -> Mapping[str, float]:
        return self.tokens[day]

    def __iter__(self) -> Iterator[date]:
        return iter(self.tokens)

    def __len__(self) -> int:
        return len(self.tokens)


def empty_token_bucket() -> dict[str, float]:
    """Return a fresh zeroed token and cost accumulator."""
    return dict.fromkeys(
        (INPUT_BAND, OUTPUT_BAND, CACHE_BAND, COST_BAND, UNKNOWN_TOTALS),
        float(0),
    )


def roll_up_time_series(
    points: Sequence[TimeSeriesPoint],
) -> DailyTokenValues:
    """Fold the series' rows into one bucket per day."""
    daily: DailyTokenValues = {}
    for point in points:
        bucket = daily.setdefault(point.day, empty_token_bucket())
        bucket[INPUT_BAND] += float(point.uncached_input_tokens)
        bucket[OUTPUT_BAND] += float(point.output_tokens or 0)
        bucket[CACHE_BAND] += float(point.cache_tokens or 0)
        bucket[COST_BAND] += point.cost.evidence.total_usd or 0
        bucket[UNKNOWN_TOTALS] += float(point.unknown_token_runs or 0)
    return daily


def series_unknown_runs(daily: DailyTokenValues) -> dict[date, int]:
    """Each day's runs of unknown token total, as the series counted them."""
    return {day: int(bucket[UNKNOWN_TOTALS]) for day, bucket in daily.items()}


def daily_cost_cohorts(
    points: Sequence[TimeSeriesPoint],
) -> dict[date, CostCohort]:
    """Fold each day's cost cohorts, one per event, into the day's own."""
    by_day: dict[date, list[CostCohort]] = {}
    for point in points:
        by_day.setdefault(point.day, []).append(point.cost)
    return {day: fold_cohorts(cohorts) for day, cohorts in by_day.items()}


def plotted_spend(cohort: CostCohort) -> float | None:
    """Where a day's cost line point sits: its stated amount, zero where nothing was priced, a gap where unpriced."""
    stated = cohort.evidence.total_usd
    if stated is not None:
        return stated
    return float(0) if cohort.evidence.completeness == usage_cost.NO_USAGE else None


def daily_token_total(bucket: dict[str, float]) -> float:
    """Add up a day's token bands, leaving its cost out of the height."""
    return sum(
        bucket[token_type]
        for token_type in (INPUT_BAND, OUTPUT_BAND, CACHE_BAND)
    )
