# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The per-day lines drawn under the headline tiles, and the totals beside them.

A tile reports one number for a whole window; the sparkline under it reports how
that number arrived. Both are reduced from the reads the window already issued
rather than from a second query cut a different way, which is what keeps a line
that disagrees with the number above it from being possible at all.

A day's spend is the amount its runs state -- every basis's contribution
added, the amount the headline figure states for the whole window -- and a
day's tokens are its runs' known non-overlapping totals, the count the token
tile reports. A day short of complete spend, or holding a run whose token total
is unknown, makes the window short too, so the tile above the line is where
that is said: the line itself is a shape too small to carry a qualifier, and
plotting a day's subtotal as zero would draw a dip that never happened. A day
whose runs stated no amount at all -- unpriced, or written before cost evidence
existed with none -- adds nothing to either.

The days a line is plotted over are the days the time series holds, not a
calendar over the window. Resolved counts are looked up against those days and
default to zero, so a day that ran agents without resolving anything draws a
gap in the throughput line instead of dropping the spend and token points beside
it, and a resolution recorded on a day no run was is not a fourth point on
three-point lines.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any


def throughput_totals(throughput_rows: Sequence[Any]) -> tuple[int, int]:
    """`(resolved, rejected)` across every day the throughput read returned."""
    resolved = sum(int(row.resolved or 0) for row in throughput_rows)
    rejected = sum(int(row.rejected or 0) for row in throughput_rows)
    return resolved, rejected


def daily_point_totals(ts_points: Sequence[Any]) -> dict[date, list[float]]:
    """Spend and known tokens per day, accumulated over the points on each.

    The series carries one point per day *and event*, so a day is several rows
    and the pair it maps to is filled in over all of them.
    """
    totals: dict[date, list[float]] = {}
    for point in ts_points:
        daily = totals.setdefault(point.day, [float(0), float(0)])
        daily[0] += point.cost.evidence.total_usd or 0
        daily[1] += float(point.total_tokens or 0)
    return totals


@dataclass(frozen=True)
class DailyKpiSeries:
    """The three sparklines, each already in the day order it is drawn in."""

    cost: Sequence[float]
    tokens: Sequence[float]
    done: Sequence[int]


def daily_kpi_series(
    *,
    ts_points: Sequence[Any],
    throughput_rows: Sequence[Any],
) -> DailyKpiSeries:
    """The three lines over the days the activity series recorded."""
    totals = daily_point_totals(ts_points)
    days = sorted(totals)
    done_index = {row.day: int(row.resolved or 0) for row in throughput_rows}
    return DailyKpiSeries(
        cost=[totals[day][0] for day in days],
        tokens=[totals[day][1] for day in days],
        done=[done_index.get(day, 0) for day in days],
    )
