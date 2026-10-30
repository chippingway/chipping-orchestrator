# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a usage figure's stack is drawn as: one band per token type or per backend.

A window is shaped before any of it is drawn, and that is also where a window
holding nothing is answered: a series with no rows and no per-backend rows has
no chart at all, and the caller draws the shared placeholder rather than a
figure whose axes are labelled for data that is not behind them. The backend
view completes its day span first, because the two reads are windowed alike but
grouped differently and a day only one of them saw still belongs on the axis.
Each day's cost cohort is folded across its events while the window is shaped,
and each day's runs of unknown token total are taken from the read the drawn
stack comes from -- the per-backend read is issued in a later wave than the
series, so a sync between them can leave the two disagreeing about a day.

The stack is one mode or the other, never both: per backend when the page asked
for that and the per-backend read came back with rows, and the three token
bands otherwise -- the uncached input, output, and cache inside each day's
known non-overlapping total, the input band named for what it holds. A
backend's color is picked off its position among the sorted backends, so the
band an operator followed last week is the same hue this week, while a token
band takes the fixed hue its name is spelled in. What is drawn over the stack
rather than in it -- the marker on a day the stack leaves a run out of, the
cost line, and the marker on a day whose cost states no amount -- belongs to
`usage_overlays`.

Plotly lives in the optional `dashboard` dependency group, so it is imported
inside the calls that add a trace: importing this owner has to work in the
default install, which does not carry it.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import TYPE_CHECKING

from orchestrator.observability.analytics.query.overview_models import (
    TimeSeriesPoint,
)
from orchestrator.observability.dashboard.charts.usage_bands import (
    BACKEND_MODE,
    CACHE_BAND,
    INPUT_BAND,
    OUTPUT_BAND,
    BackendDailyTokens,
    daily_cost_cohorts,
    roll_up_time_series,
    series_unknown_runs,
)
from orchestrator.observability.dashboard.charts.usage_series import (
    UsageChartData,
    backend_names,
    date_axis,
    ensure_backend_days,
)
from orchestrator.observability.dashboard.palette import (
    BACKEND_COLORS,
    TOKEN_TYPE_COLORS,
    color_for,
)

if TYPE_CHECKING:
    from plotly import graph_objects as go

_COLOR_KEY = "color"


def add_token_stack_trace(
    figure: go.Figure,
    *,
    days: Sequence[date],
    token_series: Sequence[float],
    name: str,
    color: str,
) -> None:
    """Add one band of the token stack, filled in the color given."""
    from plotly import graph_objects as go

    figure.add_trace(
        go.Scatter(
            x=date_axis(days),
            y=list(token_series),
            name=name,
            mode="lines",
            stackgroup="tokens",
            line={"width": 0.5, _COLOR_KEY: color},
            fillcolor=color,
            hovertemplate=f"%{{x}}<br>{name}: %{{y:,}} tokens<extra></extra>",
        )
    )


def prepare_usage_data(
    points: Sequence[TimeSeriesPoint],
    backend_rows_by_day: BackendDailyTokens | None,
    mode: str,
) -> UsageChartData | None:
    """Shape the window into a figure's days, or nothing to draw.

    The runs of unknown token total each day's stack leaves out are counted by the read that stack is drawn from: the
    per-backend read's own count under a per-backend stack, the series' under the token bands.
    """
    if not points and not backend_rows_by_day:
        return None
    daily = roll_up_time_series(points)
    backend_stack = mode == BACKEND_MODE and bool(backend_rows_by_day)
    if backend_stack:
        ensure_backend_days(daily, backend_rows_by_day)
    days = sorted(daily)
    if not days:
        return None
    unknown_runs = (
        backend_rows_by_day.unknown_runs if backend_stack
        else series_unknown_runs(daily)
    )
    return UsageChartData(
        daily=daily,
        days=days,
        costs=daily_cost_cohorts(points),
        unknown_runs=unknown_runs,
    )


def add_backend_usage_traces(
    figure: go.Figure,
    usage: UsageChartData,
    backend_rows_by_day: BackendDailyTokens,
) -> None:
    """Stack one band per backend, each in the hue its position picks."""
    backends = backend_names(backend_rows_by_day)
    for backend in backends:
        backend_color = color_for(
            backend,
            backends,
            explicit=BACKEND_COLORS,
        )
        add_token_stack_trace(
            figure,
            days=usage.days,
            token_series=[
                backend_rows_by_day.get(day, {}).get(backend, 0)
                for day in usage.days
            ],
            name=backend,
            color=backend_color,
        )


def add_token_type_usage_traces(
    figure: go.Figure,
    usage: UsageChartData,
) -> None:
    """Stack the uncached input, output, and cache bands of every day.

    The triples are listed in the order they stack in, so input is the band at
    the bottom of every day's column and cache the one on top. The input band
    is named for what it holds -- the input no cache answered -- and painted in
    the input hue.
    """
    for band, label, hue in (
        (INPUT_BAND, "Uncached input", "Input"),
        (OUTPUT_BAND, "Output", "Output"),
        (CACHE_BAND, "Cache", "Cache"),
    ):
        add_token_stack_trace(
            figure,
            days=usage.days,
            token_series=[usage.daily[day][band] for day in usage.days],
            name=label,
            color=TOKEN_TYPE_COLORS[hue],
        )


def add_usage_stack_traces(
    figure: go.Figure,
    usage: UsageChartData,
    backend_rows_by_day: BackendDailyTokens | None,
    mode: str,
) -> None:
    """Stack the window in the mode the page asked for, where it can."""
    if mode == BACKEND_MODE and backend_rows_by_day:
        add_backend_usage_traces(figure, usage, backend_rows_by_day)
        return
    add_token_type_usage_traces(figure, usage)
