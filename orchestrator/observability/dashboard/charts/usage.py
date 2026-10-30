# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The hero figure a window's spend and token usage is read off.

One figure carries both: the day's tokens as a stack of bands and the day's
spend as a line over them. They are drawn together because the question the
page is opened with is whether a day's cost tracks the work behind it, and two
panels side by side would make that a comparison across two axes rather than a
reading of one.

Assembly is the whole of what this owner decides. The window is shaped first,
the stack is added in the mode the page asked for, the days that stack leaves a
run of unknown token total out of are marked on top of it, the days whose cost
states no amount are marked on the cost axis' baseline, the cost line is
overlaid on the secondary axis, and the layout is merged last -- after the
traces, because the token axis is scaled to the stack that was actually drawn. A
window with nothing behind it never becomes a figure at all: the shared
placeholder answers it instead, at the same pinned height, so an empty hero
panel keeps the slot the drawn one would have taken.

`backend_per_day` is the stub beside it, answering with an empty mapping. No
panel calls it: the per-backend stack takes its rows through
`usage_over_time`'s own parameter, so what this owner publishes under that name
is the shape a per-backend daily aggregate would be read back in.

Plotly lives in the optional `dashboard` dependency group, so it is imported
inside the call that builds the figure: importing this owner has to work in
the default install, which does not carry it.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from orchestrator.observability.analytics.query.cost_models import (
    BackendEfficiencyRow,
)
from orchestrator.observability.analytics.query.overview_models import (
    TimeSeriesPoint,
)
from orchestrator.observability.dashboard.charts.primitives import empty_figure
from orchestrator.observability.dashboard.charts.usage_axis import (
    USAGE_CHART_HEIGHT,
    usage_layout,
)
from orchestrator.observability.dashboard.charts.usage_bands import (
    BackendDailyTokens,
)
from orchestrator.observability.dashboard.charts.usage_overlays import (
    add_unknown_totals_trace,
    add_unstated_cost_trace,
    add_usage_cost_trace,
)
from orchestrator.observability.dashboard.charts.usage_traces import (
    add_usage_stack_traces,
    prepare_usage_data,
)

if TYPE_CHECKING:
    from plotly import graph_objects as go


def usage_over_time(
    points: Sequence[TimeSeriesPoint],
    *,
    backend_rows_by_day: BackendDailyTokens | None = None,
    mode: str = "type",
    title: str | None = "Spend & token usage over time",
) -> go.Figure:
    """Build stacked daily token usage with a cost-line overlay."""
    from plotly import graph_objects as go

    usage = prepare_usage_data(points, backend_rows_by_day, mode)
    if usage is None:
        return empty_figure(
            "No events match the current filters.",
            height=USAGE_CHART_HEIGHT,
        )
    figure = go.Figure()
    add_usage_stack_traces(figure, usage, backend_rows_by_day, mode)
    add_unknown_totals_trace(figure, usage, backend_rows_by_day, mode)
    add_unstated_cost_trace(figure, usage)
    add_usage_cost_trace(figure, usage)
    figure.update_layout(
        **usage_layout(usage, backend_rows_by_day, mode, title)
    )
    return figure


def backend_per_day(
    rows: Sequence[BackendEfficiencyRow],
) -> dict[str, dict[str, float]]:
    """Keep the historical placeholder for a future backend-day aggregate."""
    return {}
