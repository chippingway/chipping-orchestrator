# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The numbers a window is summarized by, beneath the banners it opens with.

Each is a reduction a headline tile is drawn from rather than a series a chart
is plotted from: how a total moved against the window before it, how that
window's agent runs came out, where its spend went, and how much of that spend
was a second pass over work already done. All four take read-model rows or a
window's own aggregates and hand back plain numbers, strings, and tuples, so
what a tile reports is decided here rather than inside a Streamlit run.

Two of them carry a decision a caller cannot re-derive. The tile triples read
every count off the window's own totals rather than off the capped recent-runs
read, because a window holding more rows than that cap would otherwise report a
failure and timeout count that stops at the newest hundred. The rework share
decides which runs are a second pass by naming the review-round buckets rather
than comparing a round number, because the breakdown that produces them keeps
rounds 3, 4, and 5 apart and groups only 6 and above.

Ordering is the third, and it is total down to the row: issues that tie on cost
fall back to run count and then to the repository and issue number that name
them, and an issue with no recorded cost sorts below every priced one rather
than beside the cheapest. A table redrawn on the same window is the same table,
which is what makes the ranking readable at all.
"""
from __future__ import annotations

from collections.abc import Sequence

from orchestrator.observability.analytics.query.cost_models import ReviewRoundBucketRow
from orchestrator.observability.analytics.query.overview_models import Summary
from orchestrator.observability.analytics.query.run_models import IssueSummaryRow

DEFAULT_EXPENSIVE_LIMIT = 8

# Bucket strings the review-round breakdown emits whose runs are
# "rework" (i.e. happened after the initial pass). Used to compute the
# rework share KPI. `get_review_round_breakdown` keeps rounds 3, 4 and
# 5 separate (only 6+ is grouped), so every post-initial round is
# listed explicitly here.
REWORK_BUCKETS: frozenset[str] = frozenset(
    ("1", "2", "3", "4", "5", "6+")
)


def kpi_delta(
    current: float, previous: float
) -> float | None:
    """Relative change vs the previous window.

    Returns `(current - previous) / previous` (e.g. `0.25` = +25%) or
    `None` when `previous` is zero / negative so the dashboard hides
    the delta indicator rather than rendering an infinity. Negative
    `previous` values are not expected in this column set (counts,
    spend, tokens are all non-negative) but the guard keeps the
    helper safe to call from anywhere.
    """
    if previous <= 0:
        return None
    return (current - previous) / previous


def reliability_tile_data(
    summary: Summary,
    *,
    resolved: int = 0,
    rejected: int = 0,
) -> list[tuple[int, str, str]]:
    """`(value, label, tone)` triples for the six reliability tiles.

    The wiring stays testable without a live Streamlit run: every tile
    sources its number from a full-window aggregate on `Summary`
    (`total_agent_runs`, `failed_agent_runs`, `timed_out_agent_runs`)
    so a long window with more than `DEFAULT_RECENT_AGENT_EXITS` rows
    never silently undercounts the tile.

    `resolved` / `rejected` are the per-day rollups summed by the
    caller from `get_throughput_breakdown`; they default to zero so
    callers that only care about the agent-run tiles can ignore the
    throughput axis.

    Tones (`"good"` / `"warn"` / `"bad"` / `""`) drive the CSS class
    applied to the tile; the caller never has to recompute them.
    """
    total_runs = int(summary.total_agent_runs or 0)
    failed = int(summary.failed_agent_runs or 0)
    timed_out = int(summary.timed_out_agent_runs or 0)
    success_pct = (
        (1.0 - failed / total_runs) * 100
        if total_runs > 0 else float(0)
    )
    return [
        (total_runs, "Agent runs", ""),
        (f"{success_pct:.0f}%", "Success rate", "good"),
        (int(resolved), "Resolved", "good"),
        (int(rejected), "Rejected", "warn" if rejected else ""),
        (failed, "Failures", "warn" if failed else ""),
        (timed_out, "Timeouts", "bad" if timed_out else ""),
    ]


def top_expensive_issues(
    rows: Sequence[IssueSummaryRow],
    *,
    limit: int = DEFAULT_EXPENSIVE_LIMIT,
) -> list[IssueSummaryRow]:
    """Issues sorted by total cost desc for the "where did spend go" table."""
    if limit <= 0:
        return []
    return sorted(rows, key=_expensive_issue_key)[:limit]


def _expensive_issue_key(row: IssueSummaryRow) -> tuple:
    cost = row.total_cost_usd
    if cost is None:
        cost = -1.0
    event_count = -int(row.event_count)
    issue_number = int(row.issue)
    return (-cost, event_count, row.repo, issue_number)


def rework_totals(
    rows: Sequence[ReviewRoundBucketRow],
) -> tuple[float, float]:
    """Return `(total_cost, rework_cost)` across review-round buckets.

    `rework_cost` sums the cost of every row whose `bucket` is in
    `REWORK_BUCKETS` (i.e. review round >= 1). `total_cost` sums
    every row, including the initial pass.
    """
    total = sum(row.total_cost_usd for row in rows)
    rework = sum(
        row.total_cost_usd for row in rows if row.bucket in REWORK_BUCKETS
    )
    return float(total), float(rework)
