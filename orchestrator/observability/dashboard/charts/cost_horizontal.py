# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The generic cost ranking, largest bar on top.

Rows of `(label, subtitle, cost, color)` become one bar each, a row optionally
carrying the figure drawn past its bar and the line its hover adds, for a
caller that words its own amounts. They are ordered by spend unless the caller
has already ranked them, a row whose cost is `None` -- one stating no amount --
below every row that states one, a zero included. The whole series is then
flipped on the way out, because a Plotly bar axis draws the first row at the
bottom, and every column together, or a label would part company with the
amount beside it. A row that names no color falls back to the caller's accent
and then to the page's, so a ranking is one hue rather than a striped chart,
and a row that words no figure is labelled by its amount on the shared money
label.

The builder takes `*args` / `**kwargs` and binds them through a pinned
`Signature`, so `items` stays the name the rows may be passed by, the four
options stay keyword-only with their defaults, and `inspect.signature` reports
that call shape rather than the pair the body actually receives.

Plotly lives in the optional `dashboard` dependency group, so the figure is
built with an import inside the call: importing this owner has to work in the
default install, which does not carry it.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from inspect import Parameter, Signature
from typing import TYPE_CHECKING, Any, NamedTuple

from orchestrator.observability.dashboard.charts.cost_layout import (
    HorizontalCostLayout,
    apply_horizontal_cost_layout,
)
from orchestrator.observability.dashboard.charts.primitives import (
    empty_figure,
    monospace_textfont,
    two_line_y_ticks,
)
from orchestrator.observability.dashboard.formatting import fmt_money
from orchestrator.observability.dashboard.palette import ACCENT

if TYPE_CHECKING:
    from plotly import graph_objects as go

# The height an empty ranking is drawn at, which is what a single-row panel
# comes to: an empty card the size of one bar rather than of the window it
# would have filled.
DEFAULT_CHART_HEIGHT = 120


class RankedCost(NamedTuple):
    """One row of a ranking; a plain `(label, subtitle, cost, color)` tuple reads as one with nothing worded."""

    label: str
    sub: str
    cost: float | None
    color: str | None = None
    figure: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class HorizontalBars:
    """The columns of a ranking, each already in render order."""

    labels: Sequence[str]
    subs: Sequence[str]
    costs: Sequence[float]
    colors: Sequence[str]
    figures: Sequence[str]
    notes: Sequence[str]


@dataclass(frozen=True)
class HorizontalBarRequest:
    """One call to the builder, after its pinned signature is bound."""

    rows: Sequence[tuple]
    title: str | None
    accent: str | None
    preserve_order: bool
    height: int | None


def horizontal_bars_data(
    rows: Sequence[tuple],
    accent: str | None,
    preserve_order: bool,
) -> HorizontalBars:
    """Rank the rows, unless the caller ordered them, and flip them."""
    ranked = [RankedCost(*row) for row in rows]
    if not preserve_order:
        ranked.sort(key=cost_item_sort_key)
    ordered = list(reversed(ranked))
    costs = [float(row.cost or 0) for row in ordered]
    return HorizontalBars(
        labels=[row.label for row in ordered],
        subs=[row.sub for row in ordered],
        costs=costs,
        colors=[row.color or accent or ACCENT for row in ordered],
        figures=[
            fmt_money(cost) if row.figure is None else row.figure
            for row, cost in zip(ordered, costs, strict=True)
        ],
        notes=[row.note or "" for row in ordered],
    )


def cost_item_sort_key(row: tuple) -> tuple[bool, float]:
    """Rank a row by spend descending, one stating no amount below every one that states any."""
    cost = RankedCost(*row).cost
    return cost is None, -(cost or 0)


def cost_horizontal_bars(*args: Any, **kwargs: Any) -> go.Figure:
    """Render generic horizontal cost bars through the stable call shape."""
    from plotly import graph_objects as go

    bound = HORIZONTAL_BAR_SIGNATURE.bind(*args, **kwargs)
    bound.apply_defaults()
    request = HorizontalBarRequest(
        rows=bound.arguments["items"],
        title=bound.arguments["title"],
        accent=bound.arguments["accent"],
        preserve_order=bound.arguments["preserve_order"],
        height=bound.arguments["height"],
    )
    if not request.rows:
        return empty_figure(
            "No data matches the current filters.",
            height=request.height or DEFAULT_CHART_HEIGHT,
        )
    bars = horizontal_bars_data(
        request.rows,
        request.accent,
        request.preserve_order,
    )
    worded = any(bars.notes)
    figure = go.Figure(
        go.Bar(
            x=bars.costs,
            y=two_line_y_ticks(bars.labels, bars.subs),
            orientation="h",
            marker_color=bars.colors,
            text=list(bars.figures),
            textposition="outside",
            textfont=monospace_textfont(),
            cliponaxis=False,
            customdata=list(bars.notes) if worded else None,
            hovertemplate="%{y}: %{customdata}<extra></extra>" if worded else "%{y}: $%{x:,.2f}<extra></extra>",
        )
    )
    apply_horizontal_cost_layout(
        figure,
        HorizontalCostLayout(
            title=request.title,
            row_count=len(bars.costs),
            height=request.height,
        ),
    )
    return figure


# The call shape the builder answers for. `items` is positional-or-keyword and
# the four options are keyword-only, which is how every caller and adapter above
# has always spelled a ranking.
HORIZONTAL_BAR_SIGNATURE = Signature(
    (
        Parameter("items", Parameter.POSITIONAL_OR_KEYWORD),
        Parameter("title", Parameter.KEYWORD_ONLY, default=None),
        Parameter("accent", Parameter.KEYWORD_ONLY, default=None),
        Parameter("preserve_order", Parameter.KEYWORD_ONLY, default=False),
        Parameter("height", Parameter.KEYWORD_ONLY, default=None),
    ),
)
cost_horizontal_bars.__signature__ = HORIZONTAL_BAR_SIGNATURE
