# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a usage figure draws over its stack rather than in it: the subtotal marker, the cost line, and its gaps.

Both stacks are the runs' known non-overlapping token totals, so a day holding
a run whose total the evidence leaves unknown is a subtotal however it is
stacked. Such a day is marked with an open marker on top of its stack, saying
on hover how many runs it leaves out. The count is the one the shaping took off
the read the drawn stack came from -- the series' under the token bands, the
per-backend read's own under a per-backend stack -- since the two are read in
separate waves and need not agree. A window with no such day draws no marker
and adds no legend entry.

Cost is the one trace that leaves the token axis. It is added against the
secondary axis so it can be labelled in dollars, and drawn as a line with
markers rather than a band so it reads as an overlay over the stack instead of
another layer of it. Each day's hover words its cost cohort as the headline
does -- the basis, each part of a blended amount, and why the amount falls
short of complete spend -- and a day short of complete spend is drawn with an
open marker, so a subtotal never passes for the day's spend at a glance either.
A day whose runs stated no amount plots at zero only where there was nothing to
price, and leaves a gap where its usage went unpriced. A day only the
per-backend read saw has no cost reading at all -- the series that cost is read
off never reached it -- so it is a gap too, never the zero and the "no agent
runs" an empty cohort reads as.

A gap is a point Plotly neither draws nor hovers, so the line alone would let an
unpriced day pass with no cost reading at all. Each such day is therefore
marked apart from the line: a cross on the cost axis' baseline, legended as a
cost not stated rather than joined into the line as a zero, whose hover says
why -- unpriced, cost unknown, or no cost reading for this day. A window where
every day stated an amount draws no such marker and adds no legend entry.

Plotly lives in the optional `dashboard` dependency group, so it is imported
inside the calls that add a trace: importing this owner has to work in the
default install, which does not carry it.
"""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from orchestrator.observability.dashboard import spend_text
from orchestrator.observability.dashboard.charts.usage_bands import (
    BackendDailyTokens,
    plotted_spend,
)
from orchestrator.observability.dashboard.charts.usage_series import (
    UsageChartData,
    date_axis,
    usage_stack_totals,
)
from orchestrator.observability.dashboard.palette import INK, MUTED_TEXT
from orchestrator.observability.usage import cost_evidence as usage_cost

if TYPE_CHECKING:
    from plotly import graph_objects as go

_COLOR_KEY = "color"

# The completeness a day's spend is drawn with a filled marker at: all of its
# usage priced, or none to price. Any other day is drawn open.
_FILLED_COMPLETENESS = (usage_cost.COMPLETE, usage_cost.NO_USAGE)

_FILLED_MARKER = "circle"

_OPEN_MARKER = "circle-open"

# What a day the series never reached reads as on the cost line's hover.
UNREAD_COST = "no cost reading for this day"


def add_unknown_totals_trace(
    figure: go.Figure,
    usage: UsageChartData,
    backend_rows_by_day: BackendDailyTokens | None,
    mode: str,
) -> None:
    """Mark each day whose stack leaves out a run of unknown token total, on top of that stack."""
    from plotly import graph_objects as go

    unknown = [int(usage.unknown_runs.get(day, 0)) for day in usage.days]
    if not any(unknown):
        return
    heights = usage_stack_totals(
        usage.days,
        usage.daily,
        backend_rows_by_day=backend_rows_by_day,
        mode=mode,
    )
    marked = zip(heights, unknown, strict=True)
    figure.add_trace(
        go.Scatter(
            x=date_axis(usage.days),
            y=[height if runs else None for height, runs in marked],
            customdata=[spend_text.token_note(runs) for runs in unknown],
            name="Token total unknown",
            mode="markers",
            marker={"symbol": "triangle-down-open", "size": 9, _COLOR_KEY: MUTED_TEXT},
            hovertemplate="%{x}<br>Tokens: %{customdata}<extra></extra>",
        )
    )


def add_usage_cost_trace(
    figure: go.Figure,
    usage: UsageChartData,
) -> None:
    """Overlay the day's spend on the secondary axis, worded and marked by its completeness."""
    from plotly import graph_objects as go

    readings = [_cost_reading(usage, day) for day in usage.days]
    figure.add_trace(
        go.Scatter(
            x=date_axis(usage.days),
            y=[reading[0] for reading in readings],
            customdata=[reading[1] for reading in readings],
            name="Cost",
            mode="lines+markers",
            line={_COLOR_KEY: INK, "width": 2},
            marker={"size": 5, _COLOR_KEY: INK, "symbol": [reading[2] for reading in readings]},
            yaxis="y2",
            hovertemplate="%{x}<br>Cost: %{customdata}<extra></extra>",
        )
    )


def add_unstated_cost_trace(
    figure: go.Figure,
    usage: UsageChartData,
) -> None:
    """Mark each day whose cost states no amount on the cost axis' baseline, so its hover still says why."""
    from plotly import graph_objects as go

    readings = [_cost_reading(usage, day) for day in usage.days]
    unstated = [reading[0] is None for reading in readings]
    if not any(unstated):
        return
    figure.add_trace(
        go.Scatter(
            x=date_axis(usage.days),
            y=[float(0) if missing else None for missing in unstated],
            customdata=[reading[1] for reading in readings],
            name="Cost not stated",
            mode="markers",
            marker={
                "symbol": "x-thin-open",
                "size": 10,
                _COLOR_KEY: MUTED_TEXT,
                "line": {"width": 2, _COLOR_KEY: MUTED_TEXT},
            },
            yaxis="y2",
            cliponaxis=False,
            hovertemplate="%{x}<br>Cost: %{customdata}<extra></extra>",
        )
    )


def _cost_reading(usage: UsageChartData, day: date) -> tuple[float | None, str, str]:
    """Where one day's cost point sits, what its hover says, and the marker it is drawn with."""
    cohort = usage.costs.get(day)
    if cohort is None:
        return None, UNREAD_COST, _OPEN_MARKER
    filled = cohort.evidence.completeness in _FILLED_COMPLETENESS
    return plotted_spend(cohort), spend_text.spend_line(cohort), _FILLED_MARKER if filled else _OPEN_MARKER
