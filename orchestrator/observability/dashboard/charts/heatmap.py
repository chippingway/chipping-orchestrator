# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The weekday-by-hour grid a window's activity rhythm is read off.

One 7x24 figure: a row per weekday, a column per hour, and the token volume
that landed in the cell where the two meet. Volume rather than event count is
what a cell is worth, because counting events would weigh the cheap
`stage_enter` and `stage_evaluation` rows the same as the agent exits that
drive spend, and the hours that looked busiest would be the ones that cost
nothing. `HourlyHeatmapPoint.count` stays on the row for a caller that wants
the count itself. A cell's volume is the runs' known token totals, so a cell
holding a run whose total is unknown says so on hover rather than passing its
subtotal off as the hour's whole volume.

Postgres `EXTRACT(DOW FROM ts)` numbers Sunday 0, and the rows are drawn in
that order rather than re-mapped, so the row a point lands in is the number the
read handed over. A point naming a cell the grid does not have is dropped
instead of raising: one out-of-range weekday is not worth a page that fails to
load.

The hour axis is annotated with the zone the caller says the cells are already
in. Nothing here shifts a timestamp, so passing `get_hourly_heatmap` the offset
that matches the label is what makes the label true.

Plotly lives in the optional `dashboard` dependency group, so it is imported
inside the call that builds the figure: importing this owner has to work in the
default install, which does not carry it.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from orchestrator.observability.analytics.query.activity_models import (
    HourlyHeatmapPoint,
)
from orchestrator.observability.dashboard.layout import base_layout
from orchestrator.observability.dashboard.palette import (
    ACCENT,
    BORDER,
    CARD_BG,
    MUTED_TEXT,
)
from orchestrator.observability.dashboard.tokens import FONT_SIZE

if TYPE_CHECKING:
    from plotly import graph_objects as go

# The label row the y-axis is read off, Sunday-first to match the weekday
# numbering the read arrives under.
WEEKDAY_LABELS: tuple[str, ...] = (
    "Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat",
)

# What a cell's hover adds after its volume when some of its runs have no known
# token total, which leaves that volume a subtotal.
_UNKNOWN_TOTAL_NOTE = " (subtotal; token total unknown for {runs:,} {noun})"

# The grid is a fixed weekday-row x hour-column matrix. Its row count follows
# `WEEKDAY_LABELS` so the cells and the y-axis labels cannot drift apart; the
# column span is the hours in a day.
HOURS_PER_DAY = 24


def valid_heatmap_point(point: HourlyHeatmapPoint, weekdays: int) -> bool:
    """Whether the point names a cell this grid actually has."""
    valid_weekday = 0 <= int(point.weekday) < weekdays
    valid_hour = 0 <= int(point.hour) < HOURS_PER_DAY
    return valid_weekday and valid_hour


def heatmap_matrix(
    points: Sequence[HourlyHeatmapPoint],
) -> list[list[int]]:
    """The weekday x hour token-volume cells, zero where nothing ran."""
    weekdays = len(WEEKDAY_LABELS)
    matrix = [
        [0 for _ in range(HOURS_PER_DAY)] for _ in range(weekdays)
    ]
    for point in points:
        if valid_heatmap_point(point, weekdays):
            matrix[int(point.weekday)][int(point.hour)] = int(
                getattr(point, "total_tokens", 0) or 0
            )
    return matrix


def unknown_total_note(unknown_runs: int) -> str:
    """What a cell's hover adds after its volume; empty where every run's total is known."""
    if not unknown_runs:
        return ""
    noun = "run" if unknown_runs == 1 else "runs"
    return _UNKNOWN_TOTAL_NOTE.format(runs=unknown_runs, noun=noun)


def heatmap_hover_notes(
    points: Sequence[HourlyHeatmapPoint],
) -> list[list[str]]:
    """The weekday x hour hover notes, empty where every run's total is known."""
    weekdays = len(WEEKDAY_LABELS)
    notes = [
        ["" for _ in range(HOURS_PER_DAY)] for _ in range(weekdays)
    ]
    for point in points:
        if valid_heatmap_point(point, weekdays):
            notes[int(point.weekday)][int(point.hour)] = unknown_total_note(
                int(point.unknown_token_runs or 0),
            )
    return notes


def heatmap_layout(title: str | None) -> dict[str, object]:
    """The page's shared layout, retuned for a grid of square cells."""
    layout = base_layout(title=title)
    top_margin = layout["margin"]["t"]
    layout["margin"] = {"l": 48, "r": 24, "t": top_margin, "b": 32}
    # 7 rows x 24 columns: ~240px keeps the cells close to compact
    # squares instead of stretching them into tall rectangles at
    # Plotly's 450px default.
    layout["height"] = 240
    layout["plot_bgcolor"] = BORDER
    return layout


def hour_weekday_heatmap(
    points: Sequence[HourlyHeatmapPoint],
    *,
    title: str | None = None,
    tz_label: str = "UTC",
) -> go.Figure:
    """7x24 weekday-by-hour token-volume heatmap.

    `tz_label` only annotates the x-axis -- the caller is responsible for
    passing the matching offset to `get_hourly_heatmap` so the cells already
    reflect that zone.
    """
    from plotly import graph_objects as go

    fig = go.Figure(
        go.Heatmap(
            z=heatmap_matrix(points),
            customdata=heatmap_hover_notes(points),
            x=[format(hour, "02d") for hour in range(HOURS_PER_DAY)],
            y=list(WEEKDAY_LABELS),
            colorscale=[
                [0, CARD_BG],
                [0.05, "#eae8fb"],
                [1.0, ACCENT],
            ],
            showscale=False,
            xgap=2,
            ygap=2,
            hovertemplate="%{y} %{x}:00 -- %{z:,} tokens%{customdata}<extra></extra>",
        )
    )
    # Paint the plot background the border colour so the `xgap`/`ygap`
    # between cells reads as a weekday x hour grid. Zero-volume cells
    # are white (colorscale[0] == CARD_BG), so without a contrasting
    # backdrop the gaps vanish and the sparse right-hand hours look
    # like missing data rather than empty cells.
    fig.update_layout(**heatmap_layout(title))
    fig.update_xaxes(
        title_text=f"hour ({tz_label})", type="category", showgrid=False,
    )
    fig.update_yaxes(title_text="", autorange="reversed", showgrid=False)
    if not points:
        fig.add_annotation(
            text="No events match the current filters.",
            x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
            font={"color": MUTED_TEXT, "size": FONT_SIZE},
        )
    return fig
