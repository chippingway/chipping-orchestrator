# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The panel every horizontal cost family is laid out in, and a bar in it.

Three families draw dollars along a horizontal axis -- the generic ranking, the
per-stage split, and the per-review-round split -- and they read as one page
only while they share a frame. This owner is that frame: the same left gutter
wide enough for a two-line label, the same `USD` axis under a `$` tick prefix,
and one row height per bar over the fixed base unless the caller pinned a
height. A panel carrying a legend lists it one entry per line in a band above
the plot that is part of that height, so the panel a split asks for is the
height its rows need beneath its legend -- the number a caller pinning two
splits to one height reads off each. A family assembling its own layout would
part company with the ones beside it the first time a margin or a row height
moved.

A bar arrives as a frozen request rather than a pile of keyword arguments,
because what differs between the families is which segments are present: a
side-by-side split names an offsetgroup so its bars share a y bucket, and only
the outer trace of a stack carries the figure drawn past it -- the amount the
group's runs state, or the word standing where they state none -- so a bar is
labelled once rather than once per segment. A segment's hover adds the group's
whole cost as worded beside it, since a share alone would read as its spend.

The two splits share their segments as well. A group's stated amount is cut by
token share into a non-cache segment, a cache one, and the amount no declared
token total splits, drawn outermost in the muted tint every panel shares.
`token_share_traces` describes the three, named as token shares so neither
reads as a measured cache charge, and adds the unsplit one to the legend only
where some group has an amount left in it -- the count of lines the series adds
to a legend, which `TokenShareBars` reports so a panel can reserve them.

Plotly lives in the optional `dashboard` dependency group, so the helper that
builds a trace imports it at call time: importing this owner has to work in the
default install, which does not carry it.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

from orchestrator.observability.dashboard.charts.primitives import (
    HORIZONTAL_BAR_EXTRA_HEIGHT,
    HORIZONTAL_BAR_ROW_HEIGHT,
    horizontal_panel_height,
    legend_band_height,
    monospace_textfont,
    stacked_legend,
)
from orchestrator.observability.dashboard.layout import base_layout
from orchestrator.observability.dashboard.palette import MUTED_TEXT_SOFT

if TYPE_CHECKING:
    from plotly import graph_objects as go

# The gutter a two-line label is drawn in, plus the room the outside value
# label needs past the longest bar. The top margin stays whatever the shared
# layout set, so a titled panel keeps its heading clear.
HORIZONTAL_BAR_MARGIN = MappingProxyType({"l": 160, "r": 64, "b": 32})

# What each of the three token-share segments is called: two shares of a
# declared total, and the amount no declared total splits.
NO_CACHE_BAND = "non-cache token share"

CACHE_BAND = "cache token share"

UNSPLIT_BAND = "token share unknown"


@dataclass(frozen=True)
class HorizontalCostLayout:
    """What one horizontal cost panel is framed and sized by.

    A panel listing `legend_entries` entries carries them as a stacked legend, in `legend_order`, in a band of its own
    above the plot: the band is the top margin and is added to the height a panel sizes itself to, so every row keeps
    its full height beneath the legend whatever width the panel is drawn at.
    """

    row_count: int
    height: int | None = None
    title: str | None = None
    barmode: str | None = None
    legend_entries: int = 0
    legend_order: str | None = None
    row_height: int = HORIZONTAL_BAR_ROW_HEIGHT
    extra_height: int = HORIZONTAL_BAR_EXTRA_HEIGHT

    @property
    def legend_band(self) -> int:
        """The height reserved above the plot for the legend; none for a panel without one."""
        return legend_band_height(self.legend_entries) if self.legend_entries else 0

    @property
    def panel_height(self) -> int:
        """The caller's pinned height, or one row height per bar over the base and the legend band."""
        return horizontal_panel_height(
            self.row_count,
            height=self.height,
            row_height=self.row_height,
            extra_height=self.extra_height + self.legend_band,
        )


def apply_horizontal_cost_layout(
    figure: go.Figure,
    options: HorizontalCostLayout,
) -> None:
    """Frame a built figure as one of the horizontal cost panels."""
    layout = base_layout(title=options.title)
    if options.barmode is not None:
        layout["barmode"] = options.barmode
    if options.legend_entries:
        layout["legend"] = stacked_legend(traceorder=options.legend_order)
    layout["margin"] = {
        **HORIZONTAL_BAR_MARGIN,
        "t": options.legend_band or layout["margin"]["t"],
    }
    layout["height"] = options.panel_height
    figure.update_layout(**layout)
    figure.update_xaxes(
        title_text="USD",
        tickprefix="$",
        showline=False,
        zeroline=False,
    )
    figure.update_yaxes(automargin=True, showline=False, ticks="")


@dataclass(frozen=True)
class CostBarTrace:
    """One series of bars: what it is called, costs, and is tinted by.

    `labels` is the text drawn past each bar, set only on a stack's outer series. `notes` is what a bar's hover adds
    under its own amount -- the whole of the group's cost, worded -- since a segment's share alone would read as the
    group's spend.
    """

    name: str
    amounts: Sequence[float]
    y_ticks: Sequence[str]
    color: object
    hover_label: str
    offsetgroup: str | None = None
    labels: Sequence[str] | None = None
    notes: Sequence[str] | None = None
    show_legend: bool = True


@dataclass(frozen=True)
class TokenShareBars:
    """One series of groups split by token share, each column already in render order.

    The three amounts stack back to what each group's runs state; `figures` is what is drawn past the stack and
    `notes` the group's cost as its hover words it.
    """

    no_cache: Sequence[float]
    cache: Sequence[float]
    unsplit: Sequence[float]
    figures: Sequence[str]
    notes: Sequence[str]

    @property
    def shows_unsplit(self) -> bool:
        """Whether some group has an amount no declared total split, which is what lists that segment."""
        return any(self.unsplit)

    @property
    def legend_entries(self) -> int:
        """The lines the series adds to a legend: its two shares, and the unsplit amount where there is one."""
        return 3 if self.shows_unsplit else 2


def cost_bar_trace(options: CostBarTrace) -> go.Bar:
    """Build the requested series as a horizontal bar trace."""
    from plotly import graph_objects as go

    noted = "" if options.notes is None else "<br>Total: %{customdata}"
    trace_kwargs = {
        "x": list(options.amounts),
        "y": list(options.y_ticks),
        "name": options.name,
        "orientation": "h",
        "marker_color": options.color,
        "cliponaxis": False,
        "showlegend": options.show_legend,
        "hovertemplate": (
            f"%{{y}}<br>{options.hover_label}: $%{{x:,.2f}}{noted}<extra></extra>"
        ),
    }
    if options.offsetgroup is not None:
        trace_kwargs["offsetgroup"] = options.offsetgroup
    if options.notes is not None:
        trace_kwargs["customdata"] = list(options.notes)
    if options.labels is not None:
        trace_kwargs["text"] = list(options.labels)
        trace_kwargs["textposition"] = "outside"
        trace_kwargs["textfont"] = monospace_textfont()
    return go.Bar(**trace_kwargs)


def token_share_traces(
    bars: TokenShareBars,
    y_ticks: Sequence[str],
    *,
    role: str = "",
    colors: tuple[object, object],
    offsetgroup: str | None = None,
) -> tuple[CostBarTrace, ...]:
    """Describe one series' three token-share segments, the unsplit one outermost and labelled with the figure.

    `colors` tints the non-cache and cache segments; the unsplit one is the muted tint every panel shares, and it
    joins the legend only where some group has an amount left in it. A `role` names the series its segments belong to.
    """
    no_cache_name = _band_name(role, NO_CACHE_BAND)
    cache_name = _band_name(role, CACHE_BAND)
    unsplit_name = _band_name(role, UNSPLIT_BAND)
    return (
        CostBarTrace(no_cache_name, bars.no_cache, y_ticks, colors[0], no_cache_name, offsetgroup, notes=bars.notes),
        CostBarTrace(cache_name, bars.cache, y_ticks, colors[1], cache_name, offsetgroup, notes=bars.notes),
        CostBarTrace(
            unsplit_name,
            bars.unsplit,
            y_ticks,
            MUTED_TEXT_SOFT,
            unsplit_name,
            offsetgroup,
            labels=bars.figures,
            notes=bars.notes,
            show_legend=bars.shows_unsplit,
        ),
    )


def _band_name(role: str, band: str) -> str:
    return f"{role} ({band})" if role else band.capitalize()
