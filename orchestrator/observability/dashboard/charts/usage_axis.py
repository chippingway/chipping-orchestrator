# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The two scales a usage figure's stack and its cost line are read off.

Tokens and dollars are orders of magnitude apart, so the stack keeps the left
axis and the cost line rides a secondary one on the right. Both are cut into
the same number of steps and both start at zero, which is what lets a single
horizontal rule mean something on either scale: an axis left at whatever the
busiest day reached would put the cost ticks between the token ticks and the
grid would say two things at once.

A maximum is rounded up to 1, 2, 2.5, 5, or 10 times the decade under the step
it would otherwise take, so an axis is labelled in the numbers an operator
reads off a ruler rather than in a day's arbitrary total. A window with nothing
in it is given a real span anyway, because a range of [0, 0] draws no gridlines
to read the empty state against.

The token axis is scaled to the stack the figure actually draws, which is why
the mode and the per-backend rows travel this far down: measuring the token
bands under a per-backend stack would leave the tallest band drawn past the top
of its own axis.
"""
from __future__ import annotations

import math

from orchestrator.observability.dashboard.charts.usage_bands import (
    COST_BAND,
    BackendDailyTokens,
)
from orchestrator.observability.dashboard.charts.usage_series import (
    UsageAxisRanges,
    UsageChartData,
    usage_stack_totals,
)
from orchestrator.observability.dashboard.layout import base_layout
from orchestrator.observability.dashboard.palette import GRID, MUTED_TEXT

# The step count both axes are divided into, so a gridline drawn for the token
# scale is a gridline the cost scale also has a tick for.
USAGE_GRID_STEPS = 5

# What the hero panel is pinned to (px). The placeholder a window with no rows
# is answered with mirrors it, so an empty chart keeps the slot the drawn one
# would have taken instead of collapsing to Plotly's own default.
USAGE_CHART_HEIGHT = 330


def nice_axis_max(data_max: float, steps: int) -> float:
    """Return a rounded axis maximum divisible into equal steps."""
    if data_max <= 0 or steps <= 0:
        return float(max(steps, 1))
    rough_step = data_max / steps
    magnitude = 10 ** math.floor(math.log10(rough_step))
    normalized = rough_step / magnitude
    if normalized <= 1:
        nice_step = 1
    elif normalized <= 2:
        nice_step = 2
    elif normalized <= 5 / 2:
        nice_step = 5 / 2
    elif normalized <= 5:
        nice_step = 5
    else:
        nice_step = 10
    return nice_step * magnitude * steps


def usage_axis_ranges(
    usage: UsageChartData,
    backend_rows_by_day: BackendDailyTokens | None,
    mode: str,
) -> UsageAxisRanges:
    """Scale each axis to the series that is drawn against it."""
    stack_totals = usage_stack_totals(
        usage.days,
        usage.daily,
        backend_rows_by_day=backend_rows_by_day,
        mode=mode,
    )
    token_max = max(stack_totals, default=0)
    cost_max = max(
        (usage.daily[day][COST_BAND] for day in usage.days),
        default=0,
    )
    return UsageAxisRanges(
        token_top=nice_axis_max(token_max, USAGE_GRID_STEPS),
        cost_top=nice_axis_max(cost_max, USAGE_GRID_STEPS),
    )


def usage_layout(
    usage: UsageChartData,
    backend_rows_by_day: BackendDailyTokens | None,
    mode: str,
    title: str | None,
) -> dict[str, object]:
    """Lay the page's shared layout out over the two usage axes."""
    layout = base_layout(title=title)
    ranges = usage_axis_ranges(usage, backend_rows_by_day, mode)
    layout["yaxis"] = {
        **layout.get("yaxis", {}),
        "title": {"text": "tokens"},
        "range": [0, ranges.token_top],
        "dtick": ranges.token_top / USAGE_GRID_STEPS,
        "rangemode": "tozero",
        "showgrid": True,
    }
    # The dollar axis carries the ticks but not the rules: two grids over one
    # plot would cross wherever the roundings disagree, so the token axis
    # draws the horizontal lines both scales are read against.
    layout["yaxis2"] = {
        "title": {"text": "USD"},
        "overlaying": "y",
        "side": "right",
        "range": [0, ranges.cost_top],
        "dtick": ranges.cost_top / USAGE_GRID_STEPS,
        "rangemode": "tozero",
        "gridcolor": GRID,
        "linecolor": GRID,
        "showgrid": False,
        "tickprefix": "$",
        "tickfont": {"color": MUTED_TEXT},
    }
    layout["margin"] = {**layout.get("margin", {}), "t": 28}
    layout["hovermode"] = "x unified"
    layout["legend"] = {
        **layout.get("legend", {}),
        "orientation": "h",
        "yanchor": "bottom",
        "y": 1.02,
        "xanchor": "left",
        "x": 0,
    }
    layout["height"] = USAGE_CHART_HEIGHT
    return layout
