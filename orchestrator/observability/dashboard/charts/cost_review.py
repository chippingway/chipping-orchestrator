# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The per-review-round split of a window's spend, first pass on top.

One row per review round carrying two bars side by side: what development
spent reaching that round and what review spent judging it. Each bar is as
long as the amount its role's runs state and cut three ways by token share --
the cache tokens' share of the runs' declared totals, the rest of them, and the
amount of the runs whose total is unknown -- an allocation of the stated amount
rather than a measured cache charge, named as such in the legend. The segments
stack within their own bar, and only the outer one carries the text past it:
the amount, or the word standing where the role's runs state none. The two
roles are offset into groups of their own so they share a row rather than
stacking into each other, and the legend is read back to front so its entries
fall in the order the bars are drawn in.

Rounds are ordered by the round itself rather than by spend, because a round
number is an ordinal and what the panel is read for is the shape of the rework
curve -- ranking the rows by cost would hide it. A bucket the window holds no
rows for drops out rather than drawing an empty row, and the runs that carried
no round at all come last under a label of their own: they are unattributed
rather than late. The sub-line counts the two roles' runs separately, because
the bars beside it are drawn from two different populations and one combined
count would explain neither, then names the basis the round's amount is stated
on and any shortfall. Each bar's hover carries its role's whole cost for the
round, worded as the overview words it, each part of a blended amount by its
own.

Both split segments of a role's bar are tinted from that role's one hue, the
same treatment the per-stage split gives its own and reached from there rather
than restated, so a cache share here and one on the panel beside it are the
same shade. A row carries two bars rather than one, so the panel is sized by a
row height of its own rather than the shared default, and the rows are laid
out bottom-up, because a Plotly bar axis draws the first row at the bottom and
the initial pass belongs on top. Both roles' segments make up to six legend
lines, listed one a line in a band above the bars; `review_panel_height` is the
height a window's rounds need beneath that band, which is what a caller pinning
this split beside another sizes the pair by, since a band taken out of a pinned
height the rows were counted into would leave their two-line labels too little
room to stay apart.

A window with nothing to draw is the shared placeholder at the height the
ranking owner pins an empty cost panel to, which is the one value taken from
there. It answers in two ways rather than one: no rows at all is a filter that
matched no agent exits, while rows carrying neither development nor review
runs is a window whose spend was all something else. An operator told "no
data" for the second would go looking for a broken query.

Plotly lives in the optional `dashboard` dependency group, so the figure is
built with an import inside the call: importing this owner has to work in the
default install, which does not carry it.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

from orchestrator.observability.analytics.query import (
    cache_shares as _cache_shares,
    cost_cohorts as _cost_cohorts,
)
from orchestrator.observability.analytics.query.cost_models import (
    ReviewRoundBucketRow,
)
from orchestrator.observability.dashboard import breakdown_text, spend_text
from orchestrator.observability.dashboard.charts import (
    cost_horizontal as _cost_horizontal,
    cost_layout as _cost_layout,
    cost_stage as _cost_stage,
    primitives as _primitives,
)
from orchestrator.observability.dashboard.palette import AGENT_ROLE_COLORS

if TYPE_CHECKING:
    from plotly import graph_objects as go

# A row here carries two bars where a ranking row carries one, so it is given
# more of the panel than the shared default allows.
REVIEW_BAR_ROW_HEIGHT = 44

# How a bucket is read on the axis. The raw keys are what the read model
# buckets on; an operator reads the round rather than the key.
REVIEW_ROUND_LABELS = MappingProxyType({
    "0": "Initial",
    "1": "Round 1",
    "2": "Round 2",
    "3": "Round 3",
    "4": "Round 4",
    "5": "Round 5",
    "6+": "Rounds 6+",
    "unknown": "No review round",
})

# The order the rows are laid out in before the flip for the axis: by round,
# with the runs that carried none of them last.
REVIEW_ROUND_ORDER = ("0", "1", "2", "3", "4", "5", "6+", "unknown")


@dataclass(frozen=True)
class ReviewCostBars:
    """The split's rows, labelled and counted, and each role's bars, all in render order."""

    labels: Sequence[str]
    subs: Sequence[str]
    developer: _cost_layout.TokenShareBars
    reviewer: _cost_layout.TokenShareBars


def role_cost_bars(
    costs: Sequence[_cost_cohorts.CostCohort],
    bands: Sequence[_cache_shares.TokenShareBands],
) -> _cost_layout.TokenShareBars:
    """One role's bars across the rounds: its token-share segments, the figure past them, and its hover."""
    return _cost_layout.TokenShareBars(
        no_cache=[band.no_cache_usd for band in bands],
        cache=[band.cache_usd for band in bands],
        unsplit=[band.unsplit_usd for band in bands],
        figures=[breakdown_text.bar_figure(cost) for cost in costs],
        notes=[spend_text.spend_line(cost) for cost in costs],
    )


def review_cost_bars(
    rows: Sequence[ReviewRoundBucketRow],
) -> ReviewCostBars | None:
    """Order the rounds bottom-up, label them, and split each role, or answer nothing."""
    by_bucket = {row.bucket: row for row in rows}
    ordered = [
        by_bucket[bucket]
        for bucket in reversed(REVIEW_ROUND_ORDER)
        if bucket in by_bucket
    ]
    if not ordered:
        return None
    return ReviewCostBars(
        labels=[REVIEW_ROUND_LABELS.get(row.bucket, row.bucket) for row in ordered],
        subs=[
            breakdown_text.sub_line(f"{row.developer_runs:,} dev / {row.reviewer_runs:,} review runs", row.cost)
            for row in ordered
        ],
        developer=role_cost_bars(
            [row.developer_cost for row in ordered],
            [row.developer_bands for row in ordered],
        ),
        reviewer=role_cost_bars(
            [row.reviewer_cost for row in ordered],
            [row.reviewer_bands for row in ordered],
        ),
    )


def review_cost_traces(
    bars: ReviewCostBars,
    y_ticks: Sequence[str],
) -> tuple[_cost_layout.CostBarTrace, ...]:
    """Describe both roles' segments, review first so development reads above it."""
    developer_color = AGENT_ROLE_COLORS["developer"]
    reviewer_color = AGENT_ROLE_COLORS["reviewer"]
    review = _cost_layout.token_share_traces(
        bars.reviewer,
        y_ticks,
        role="Review",
        colors=(reviewer_color, _cost_stage.lighten_hex(reviewer_color, _cost_stage.CACHE_LIGHTEN)),
        offsetgroup="reviewer",
    )
    development = _cost_layout.token_share_traces(
        bars.developer,
        y_ticks,
        role="Development",
        colors=(developer_color, _cost_stage.lighten_hex(developer_color, _cost_stage.CACHE_LIGHTEN)),
        offsetgroup="developer",
    )
    return (*review, *development)


def cost_by_review_round(
    rows: Sequence[ReviewRoundBucketRow],
    *,
    height: int | None = None,
) -> go.Figure:
    """Build grouped token-share cost bars by review round."""
    from plotly import graph_objects as go

    if not rows:
        return _primitives.empty_figure(
            "No `agent_exit` rows match the current filters.",
            height=height or _cost_horizontal.DEFAULT_CHART_HEIGHT,
        )
    bars = review_cost_bars(rows)
    if bars is None:
        return _primitives.empty_figure(
            "No development or review runs match the current filters.",
            height=height or _cost_horizontal.DEFAULT_CHART_HEIGHT,
        )
    y_ticks = _primitives.two_line_y_ticks(bars.labels, bars.subs)
    figure = go.Figure()
    for trace in review_cost_traces(bars, y_ticks):
        figure.add_trace(_cost_layout.cost_bar_trace(trace))
    _cost_layout.apply_horizontal_cost_layout(figure, review_cost_layout(bars, height))
    return figure


def review_cost_layout(bars: ReviewCostBars, height: int | None = None) -> _cost_layout.HorizontalCostLayout:
    """The frame the split is drawn in: a two-bar row per round beneath the band both roles' legend lines take."""
    return _cost_layout.HorizontalCostLayout(
        row_count=len(bars.labels),
        height=height,
        barmode="relative",
        legend_entries=bars.developer.legend_entries + bars.reviewer.legend_entries,
        legend_order="reversed",
        row_height=REVIEW_BAR_ROW_HEIGHT,
    )


def review_panel_height(rows: Sequence[ReviewRoundBucketRow]) -> int:
    """The height the split of `rows` needs for a full row per round beneath its legend; the placeholder's for none."""
    bars = review_cost_bars(rows)
    if bars is None:
        return _cost_horizontal.DEFAULT_CHART_HEIGHT
    return review_cost_layout(bars).panel_height
