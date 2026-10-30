# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pieces every chart family on the page is drawn out of.

A figure is only a chart while there are rows behind it. Plotly answers an
empty series with a blank canvas rather than an error, which reads as a card
that failed to load, so every builder routes its no-data branch through
`empty_figure` and an operator meets one "nothing matches this window" sentence
across the page instead of a different silence per panel. The height travels
with the message because a placeholder falling back to Plotly's own default
would stand half again as tall as the cards beside it.

The label helpers are what keeps those panels one page rather than several. A
bar's text is set in the mono stack so the amounts down a column line up on the
decimal point, and a tick is the label with its subtitle beneath it in the muted
tint, built here rather than per family because a subtitle spelled a second way
is a different chart.

The horizontal-bar helpers settle the shape those families share: a panel is
one row height per bar over the fixed margin and axis base underneath, unless
the caller pinned a height, and its legend is listed one entry per line in the
figure's top-left corner, in a band of its own above the plot. A legend Plotly
lets wrap across the plot area takes more lines the narrower the column it is
drawn in, and every line comes out of a pinned panel's rows until their two-line
labels overlap; anchored to the figure and held to one entry a line, the band is
as tall as its entry count says at any width, so it is reserved as the top
margin and counted into the panel's height. A family sizing itself would drift
from the ones beside it the first time a row was added.

Plotly lives in the optional `dashboard` dependency group, so the one helper
here that builds a figure imports it at call time: importing this owner has to
work in the default install, which does not carry it.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from orchestrator.observability.dashboard.layout import base_layout
from orchestrator.observability.dashboard.palette import MUTED_TEXT, TEXT
from orchestrator.observability.dashboard.tokens import (
    FONT_SIZE,
    MONO_FONT_FAMILY,
)

if TYPE_CHECKING:
    from plotly import graph_objects as go

# Horizontal-bar panel sizing (px): per-row height plus the fixed
# margin / axis base every horizontal cost bar adds on top.
HORIZONTAL_BAR_ROW_HEIGHT = 40
HORIZONTAL_BAR_EXTRA_HEIGHT = 80

# A stacked legend's line at the page font, and the room the band it sits in
# keeps above its first line and below its last.
LEGEND_ENTRY_HEIGHT = 20
LEGEND_BAND_PAD = 24


def empty_figure(message: str, *, height: int) -> go.Figure:
    """Return a placeholder figure with a centered annotation.

    `height` mirrors the builder's pinned non-empty height so empty cards do
    not snap to Plotly's 450px default and dwarf surrounding cards.
    """
    from plotly import graph_objects as go

    fig = go.Figure()
    layout = base_layout()
    layout["height"] = height
    fig.update_layout(**layout)
    fig.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font={"color": MUTED_TEXT, "size": FONT_SIZE},
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def monospace_textfont() -> dict[str, object]:
    """Return the font a bar's own value label is set in."""
    return {
        "color": TEXT,
        "size": 12,
        "family": MONO_FONT_FAMILY,
    }


def two_line_y_ticks(
    labels: Sequence[str], subs: Sequence[str]
) -> list[str]:
    """Pair each label with its subtitle, dropping an empty one."""
    ticks: list[str] = []
    for label, sub in zip(labels, subs):
        label_html = f"<b>{label}</b>"
        if sub:
            ticks.append(
                f"{label_html}<br>"
                f"<span style='color:{MUTED_TEXT};font-size:11px'>"
                f"{sub}</span>"
            )
        else:
            ticks.append(label_html)
    return ticks


def horizontal_panel_height(
    row_count: int,
    *,
    height: int | None,
    row_height: int = HORIZONTAL_BAR_ROW_HEIGHT,
    extra_height: int = HORIZONTAL_BAR_EXTRA_HEIGHT,
) -> int:
    """Size a bar panel to its rows, unless the caller pinned a height."""
    if height is not None:
        return height
    return row_height * max(row_count, 1) + extra_height


def stacked_legend(*, traceorder: str | None = None) -> dict[str, object]:
    """Return the legend a horizontal-bar panel lists one entry per line in its top-left corner, above the plot."""
    legend: dict[str, object] = {
        "orientation": "h",
        "xref": "container",
        "yref": "container",
        "x": 0,
        "y": 1,
        "xanchor": "left",
        "yanchor": "top",
        "entrywidth": 1,
        "entrywidthmode": "fraction",
    }
    if traceorder is not None:
        legend["traceorder"] = traceorder
    return legend


def legend_band_height(entries: int) -> int:
    """The band a stacked legend of `entries` lines is given above the plot, as the panel's top margin."""
    return LEGEND_ENTRY_HEIGHT * entries + LEGEND_BAND_PAD
