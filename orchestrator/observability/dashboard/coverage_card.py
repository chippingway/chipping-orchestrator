# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How much of a window's spend was attributed, drawn as one bar.

The bar answers whether the money everywhere else on the page can be trusted:
each segment is one `cost_source` -- what the parser could price, and what it
could not -- and its width is that source's share of the window. Share is read
in tokens whenever the window carries any and every run in it has a known token
total, because a handful of high-token runs can dominate spend while looking
like a thin slice of the run count. A window holding a run whose total the
evidence leaves unknown falls back to run share instead: its source's known
subtotal would otherwise shrink that segment toward nothing, hiding exactly the
runs nobody could measure. So does a window with no token volume at all, and a
window with neither falls back to a denominator of one so an empty bar renders
flat rather than raising on a page opened to find out why it is empty.

A segment carries both of the strings it appears in -- the slice of the bar and
the entry in the legend beneath it -- because the two share a color and a
percentage, and building them apart is where a legend could start naming a
width the bar above it does not have. The tint comes off the theme the caller
hands in, resolved against the sources present in this window, so the caller's
own palette is what a source is recognized by across both.

Every cost source reaches this owner off the sink rather than out of this
repository, so the name is escaped into the bar's tooltip and the legend line
alike.
"""
from __future__ import annotations

import html
from collections.abc import Sequence
from dataclasses import dataclass

from orchestrator.observability.analytics.query.cost_models import (
    CostCoverageRow,
)


@dataclass(frozen=True)
class CoverageSegment:
    bar_html: str
    legend: str


def cost_coverage_weights(
    rows: Sequence[CostCoverageRow],
) -> tuple[list[int], int]:
    total_tokens = sum(int(row.total_tokens or 0) for row in rows)
    tokens_known = not any(row.unknown_token_runs for row in rows)
    if total_tokens > 0 and tokens_known:
        return [int(row.total_tokens or 0) for row in rows], total_tokens
    weights = [int(row.runs or 0) for row in rows]
    return weights, sum(weights) or 1


def cost_source_color(
    cost_source: str,
    cost_sources: Sequence[str],
    theme,
) -> str:
    return theme.color_for(
        cost_source,
        cost_sources,
        explicit=theme.COST_SOURCE_COLORS,
    )


def coverage_segment(
    row: CostCoverageRow,
    weight: int,
    total: int,
    cost_sources: Sequence[str],
    theme,
) -> CoverageSegment:
    percentage = weight / total * 100
    color = cost_source_color(row.cost_source, cost_sources, theme)
    return CoverageSegment(
        bar_html=(
            f'<span style="width:{percentage:.1f}%;background:{color}" '
            f'title="{html.escape(row.cost_source)}"></span>'
        ),
        legend=(
            f'<span><span class="dot" style="background:{color}"></span>'
            f"{html.escape(row.cost_source)} "
            f'<b style="color:{theme.TEXT};'
            f'font-family:{theme.MONO_FONT_FAMILY}">{percentage:.1f}%</b>'
            "</span>"
        ),
    )


def coverage_segments(
    rows: Sequence[CostCoverageRow],
    weights: Sequence[int],
    total: int,
    cost_sources: Sequence[str],
    theme,
) -> list[CoverageSegment]:
    return [
        coverage_segment(row, weight, total, cost_sources, theme)
        for row, weight in zip(rows, weights)
    ]


def cost_coverage_bar_html(
    rows: Sequence[CostCoverageRow],
    *,
    theme,
) -> str:
    """Render the cost-attribution coverage bar to inline HTML."""
    weights, total = cost_coverage_weights(rows)
    segments = coverage_segments(
        rows,
        weights,
        total,
        [row.cost_source for row in rows],
        theme,
    )
    bars = "".join(segment.bar_html for segment in segments)
    legends = "".join(segment.legend for segment in segments)
    return (
        '<div class="orch-cov-title">Cost attribution coverage</div>'
        f'<div class="orch-cov-bar">{bars}</div>'
        f'<div class="orch-cov-legend">{legends}</div>'
    )
