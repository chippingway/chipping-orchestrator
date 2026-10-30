# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The per-stage split of a window's spend, dearest stage on top.

One bar per workflow stage, as long as the amount the stage's runs state and
cut three ways by token share: the cache tokens' share of the runs' declared
totals, the rest of them, and the amount of the runs whose total is unknown,
which nothing splits. The segments are an allocation of the stated amount, not
what any cache was charged, and are named as token shares so the legend never
says otherwise. They are stacked rather than drawn side by side, so a bar's
length is still the stage's whole stated amount. Only the outer segment
carries the text past the bar -- the amount, or the word standing where the
stage's runs state none -- which labels a bar once instead of once per segment.

The line under a stage's name counts its `runs` -- the agent exits
`StageBreakdown.count` is a superset of, since the spend is what those exits
stated -- and names the basis the amount is stated on and any shortfall, so an
Antigravity stage reads as a Gemini API token estimate, a mixed one as
blended, and a subtotal as one. Every segment's hover carries the stage's
whole cost as the overview words it, each part of a blended amount by its own.

The two split segments are tinted from one hue -- the stage's own color, and a
translucent shade of it for the cache share -- because a separate palette for
the cache segments would read as eight stages rather than four stages split
two ways. That shading is the color treatment the per-review-round split
reaches for as well, which is why the lightening lives here rather than inside
the stacking.

Stages are ranked by stated amount, a stage stating none below every one that
states an amount -- a zero included -- and the whole series is flipped on the
way out, every column together, because a Plotly bar axis draws the first row
at the bottom and the dearest stage belongs on top. The legend lists the
segments one a line in a band above the bars, and `stage_panel_height` is the
height a window's stages need beneath it, which is what a caller pinning this
split beside another sizes the pair by.

A window with no stages is the shared placeholder at the height the ranking
owner beside this one pins an empty cost panel to, which is the one value taken
from there: a split with nothing to draw and a ranking with nothing to rank sit
in the same card on the same row of the page.

Plotly lives in the optional `dashboard` dependency group, so the figure is
built with an import inside the call: importing this owner has to work in the
default install, which does not carry it.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from orchestrator.observability.analytics.query.run_models import StageBreakdown
from orchestrator.observability.dashboard import breakdown_text, spend_text
from orchestrator.observability.dashboard.charts.cost_horizontal import (
    DEFAULT_CHART_HEIGHT,
)
from orchestrator.observability.dashboard.charts.cost_layout import (
    HorizontalCostLayout,
    TokenShareBars,
    apply_horizontal_cost_layout,
    cost_bar_trace,
    token_share_traces,
)
from orchestrator.observability.dashboard.charts.primitives import (
    empty_figure,
    two_line_y_ticks,
)
from orchestrator.observability.dashboard.palette import STAGE_COLORS, color_for

if TYPE_CHECKING:
    from plotly import graph_objects as go

# How far towards transparent a stage's hue is taken for its cache share. Far
# enough that the two split segments of a bar are told apart at a glance, near
# enough that they still read as one stage.
CACHE_LIGHTEN = 0.45

HEX_BASE = 16


@dataclass(frozen=True)
class StageCostBars:
    """The split's columns, each already in render order."""

    labels: Sequence[str]
    subs: Sequence[str]
    split: TokenShareBars
    colors: Sequence[str]
    cache_colors: Sequence[str]


def stage_cost_bars(rows: Sequence[StageBreakdown]) -> StageCostBars:
    """Rank the stages, tint the split of each, and flip them."""
    ranked = sorted(rows, key=stage_cost_sort_key)
    # Flipped whole, ties included, so the axis reads top-down in ranked order.
    ordered = list(reversed(ranked))
    colors = [color_for(row.stage, explicit=STAGE_COLORS) for row in ordered]
    return StageCostBars(
        labels=[row.stage for row in ordered],
        subs=[breakdown_text.sub_line(f"{row.runs:,} runs", row.cost) for row in ordered],
        split=TokenShareBars(
            no_cache=[row.bands.no_cache_usd for row in ordered],
            cache=[row.bands.cache_usd for row in ordered],
            unsplit=[row.bands.unsplit_usd for row in ordered],
            figures=[breakdown_text.bar_figure(row.cost) for row in ordered],
            notes=[spend_text.spend_line(row.cost) for row in ordered],
        ),
        colors=colors,
        cache_colors=[lighten_hex(color, CACHE_LIGHTEN) for color in colors],
    )


def stage_cost_sort_key(row: StageBreakdown) -> tuple[bool, float]:
    """Rank a stage by stated amount descending, one stating none below every one that states any."""
    stated = row.cost.evidence.total_usd
    return stated is None, -(stated or 0)


def cost_by_stage(
    rows: Sequence[StageBreakdown],
    *,
    height: int | None = None,
) -> go.Figure:
    """Build stacked token-share cost bars per workflow stage."""
    from plotly import graph_objects as go

    if not rows:
        return empty_figure(
            "No stage data matches the current filters.",
            height=height or DEFAULT_CHART_HEIGHT,
        )
    bars = stage_cost_bars(rows)
    y_ticks = two_line_y_ticks(bars.labels, bars.subs)
    figure = go.Figure()
    for trace in token_share_traces(bars.split, y_ticks, colors=(bars.colors, bars.cache_colors)):
        figure.add_trace(cost_bar_trace(trace))
    apply_horizontal_cost_layout(figure, stage_cost_layout(bars, height))
    return figure


def stage_cost_layout(bars: StageCostBars, height: int | None = None) -> HorizontalCostLayout:
    """The frame a split is drawn in: a row per stage beneath the band its legend lines take."""
    return HorizontalCostLayout(
        row_count=len(bars.labels),
        height=height,
        barmode="stack",
        legend_entries=bars.split.legend_entries,
    )


def stage_panel_height(rows: Sequence[StageBreakdown]) -> int:
    """The height the split of `rows` needs for a full row per stage beneath its legend; the placeholder's for none."""
    if not rows:
        return DEFAULT_CHART_HEIGHT
    return stage_cost_layout(stage_cost_bars(rows)).panel_height


def lighten_hex(hex_color: str, alpha: float) -> str:
    """Restate a hex color as the same hue at the given opacity."""
    hex_digits = hex_color.lstrip("#")
    red = int(hex_digits[:2], HEX_BASE)
    green = int(hex_digits[2:4], HEX_BASE)
    blue = int(hex_digits[4:6], HEX_BASE)
    return f"rgba({red},{green},{blue},{alpha:.2f})"
