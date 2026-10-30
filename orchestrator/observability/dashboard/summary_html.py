# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The chrome a page opens with, and the four tiles beneath it.

The banner naming what the database holds, the line under the filter bar
restating what a run narrowed that to, the pill one tile's move against the
window before it is annotated with, and the strip all four tiles are assembled
into sit in one owner because they are one band of markup: a tile carries the
pill, and every class name across the band is one `css.py` writes rules for. A
pill spelled in one module and the tile that carries it in another are two
places the strip can stop agreeing with the stylesheet painting it.

The banner's spend is the window's cost cohort, worded by ``spend_text``: the
amount the runs state beside the basis it is stated on -- each part of a
blended amount listed by its own -- and why it falls short of complete spend,
so the figure an operator reads first never passes an incomplete subtotal, an
amount of unknown basis, or a window with no run off as the window's spend. A
tile carries the same kind of note under its value where the entry names one.

What reaches the markup as caller text is handed to ``html.escape`` first: the
banner's span label, spend figure, and spend note, and each tile's label,
value, note, sub-line, and the note its pill is qualified by. A page writes
this with ``unsafe_allow_html=True``, and a KPI label or an already-formatted
amount is text the dashboard was given rather than text it owns. The readings
beside them -- the repository, event, day, and run counts -- are integers and
ISO dates a formatter rendered, so there is nothing in them to escape.

A rise is painted red and a drop green, because the numbers a window is
summarized by are costs. ``invert`` is for the readings where up is the good
direction -- issues resolved, success rate -- and it swaps the color only: the
arrow keeps following the value's sign, so which way a tile moved is never read
off the hue alone. A pill's ``note`` is what the move has to be read with -- a
subtotal on either side, two windows on different bases -- and it rides inside
the pill, so the qualification cannot be dropped from the percentage it
qualifies. A window with no prior to compare against, or one that did not move,
renders no pill at all, because a placeholder in that slot reads as a control
that does nothing.

The keyword surfaces the pill and the banner are reached through are bound as
explicit signatures rather than spelled as parameters. The pill's is `value`,
which a parameter here may not be named, and the banner's is five keyword-only
readings -- so the banner takes one request object underneath while both keep
answering a call spelled the way every caller spells it.
"""
from __future__ import annotations

import html
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from inspect import Parameter, Signature
from typing import Any

from orchestrator.observability.analytics.query.cost_cohorts import CostCohort
from orchestrator.observability.dashboard import sparkline_html, spend_text


@dataclass(frozen=True)
class TopbarRequest:
    """One banner as the caller asked for it: its span, counts, spend, and format."""

    extent: Any
    distinct_repos: int
    total_events: int
    spend_in_range: CostCohort
    fmt_num: Any

    def range_label(self) -> str:
        """The span of recorded data the banner reports under its title."""
        if self.extent.min_ts is None or self.extent.max_ts is None:
            return "no data recorded yet"
        first_day = self.extent.min_ts.date().isoformat()
        last_day = self.extent.max_ts.date().isoformat()
        return f"{first_day} → {last_day} available"

    def spend_html(self) -> str:
        """The window's spend figure, and the note qualifying it wherever there is one."""
        figure = html.escape(spend_text.spend_figure(self.spend_in_range))
        note = spend_text.spend_note(self.spend_in_range)
        note_html = f'<span class="note">{html.escape(note)}</span>' if note else ""
        return f'<span class="value">{figure}</span>{note_html}'


def plural_s(count: int) -> str:
    """The suffix a counted noun beside one of these figures takes."""
    return "" if count == 1 else "s"


def delta_style(delta_value: float, invert: bool) -> tuple[str, str]:
    """Pick the tone a move is painted in and the arrow it points with."""
    if delta_value > 0:
        return ("down" if invert else "up"), "▲"
    return ("up" if invert else "down"), "▼"


def delta_pill(*args: Any, **kwargs: Any) -> str:
    """Render a KPI delta pill through the historical keyword surface."""
    bound = DELTA_SIGNATURE.bind(*args, **kwargs)
    bound.apply_defaults()
    delta_value = bound.arguments["value"]
    if not delta_value:
        return ""
    css_class, arrow = delta_style(delta_value, bound.arguments["invert"])
    reading = " · ".join(filter(None, (
        format(abs(delta_value), ".1%"),
        html.escape(bound.arguments["note"]),
    )))
    return f'<span class="orch-delta {css_class}">{arrow} {reading}</span>'


def topbar_html(*args: Any, **kwargs: Any) -> str:
    """Render the topbar through its historical keyword-only surface."""
    request = TopbarRequest(**TOPBAR_SIGNATURE.bind(*args, **kwargs).arguments)
    range_label = request.range_label()
    subtitle = (
        f"{html.escape(range_label)} · "
        f"{request.distinct_repos} repo{plural_s(request.distinct_repos)} · "
        f"{request.fmt_num(request.total_events)} events"
    )
    spend = request.spend_html()
    return (
        '<div class="orch-topbar"><div class="orch-brand">'
        '<span class="orch-brand-mark">OA</span><div>'
        f'<h1>Orchestrator Analytics</h1><p class="orch-sub">{subtitle}</p>'
        '</div></div><div class="orch-spend">'
        '<span class="label">Spend in range</span>'
        f"{spend}</div></div>"
    )


def filter_meta_html(
    *,
    from_d: date,
    to_d: date,
    days: int,
    runs: int,
    fmt_num,
) -> str:
    """Restate the window a run of the filter bar actually selected."""
    return (
        '<div class="orch-filter-meta">'
        f"{from_d.isoformat()} → {to_d.isoformat()} · "
        f"{days} day{plural_s(days)} · {fmt_num(runs)} runs</div>"
    )


def kpi_strip_html(kpis: Sequence[dict]) -> str:
    """Render the four-tile KPI strip."""
    cells = []
    for kpi in kpis:
        delta_html = delta_pill(
            kpi.get("delta"),
            invert=kpi.get("invert", False),
            note=kpi.get("delta_note", ""),
        )
        note_html = (
            f'<div class="kpi-note">{html.escape(kpi["note"])}</div>'
            if kpi.get("note") else ""
        )
        spark_html = ""
        if kpi.get("spark") is not None:
            spark_html = sparkline_html.sparkline_svg(
                kpi["spark"],
                color=kpi.get("spark_color", "#5b54e0"),
            )
        cells.append(
            '<div class="orch-kpi"><div class="kpi-top">'
            f'<span class="kpi-label">{html.escape(kpi["label"])}</span>'
            f"{delta_html}</div>"
            f'<div class="kpi-value">{html.escape(str(kpi["value"]))}</div>'
            f"{note_html}"
            '<div class="kpi-foot">'
            f'<span>{html.escape(str(kpi.get("sub", "")))}</span>'
            f"{spark_html}</div></div>"
        )
    return '<div class="orch-kpis">{}</div>'.format("".join(cells))


DELTA_SIGNATURE = Signature(
    (
        Parameter("value", Parameter.POSITIONAL_OR_KEYWORD),
        Parameter("invert", Parameter.KEYWORD_ONLY, default=False),
        Parameter("note", Parameter.KEYWORD_ONLY, default=""),
    ),
)
TOPBAR_SIGNATURE = Signature(
    tuple(
        Parameter(parameter_name, Parameter.KEYWORD_ONLY)
        for parameter_name in (
            "extent",
            "distinct_repos",
            "total_events",
            "spend_in_range",
            "fmt_num",
        )
    ),
)
delta_pill.__signature__ = DELTA_SIGNATURE
topbar_html.__signature__ = TOPBAR_SIGNATURE
