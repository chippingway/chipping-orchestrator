# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The per-repository spend ranking, one bar per repo in the window.

An adapter over the generic ranking rather than a figure of its own: each row
becomes a label, a subtitle, an amount, a tint, and the words the ranking draws
past the bar and adds on hover, and the order, flip, and frame are the
ranking's. What is decided here is how a repository reads. The label drops the
owner prefix, which is the same across every bar an operator is comparing and
would spend the gutter the amounts have to fit beside; the full slug stays on
the row for a caller that needs it. The subtitle counts agent runs rather than
events, because the amount beside it is the spend those runs came to and the
cheap stage rows would overstate a quiet repository, and it names the basis
that amount is stated on and any shortfall -- an Antigravity repository's
amount a Gemini API token estimate, a mixed one blended, a subtotal one. The
bar is as long as the amount the repository's runs state, the figure past it
is that amount or the word standing where they state none, and the hover words
the repository's cost whole, each part of a blended amount by its own.

Every bar takes the page's accent: a repository is not a category the page
tints by, so a striped ranking would suggest a distinction the rows do not
carry. A window matching no repository is answered with the shared placeholder
at the ranking's own empty height, and says so in its own words -- an operator
who filtered the repositories away is told that rather than that no data
exists.

Plotly is named only for the return annotation, which `from __future__ import
annotations` leaves unevaluated, so importing this owner has to work in the
default install -- the one that does not carry the optional `dashboard`
dependency group -- and does.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from orchestrator.observability.analytics.query.cost_models import (
    RepoBreakdownRow,
)
from orchestrator.observability.dashboard import breakdown_text, spend_text
from orchestrator.observability.dashboard.charts.cost_horizontal import (
    DEFAULT_CHART_HEIGHT,
    RankedCost,
    cost_horizontal_bars,
)
from orchestrator.observability.dashboard.charts.primitives import empty_figure
from orchestrator.observability.dashboard.palette import ACCENT

if TYPE_CHECKING:
    from plotly import graph_objects as go


def cost_by_repo(rows: Sequence[RepoBreakdownRow]) -> go.Figure:
    """Build per-repository cost bars."""
    if not rows:
        return empty_figure(
            "No repos match the current filters.",
            height=DEFAULT_CHART_HEIGHT,
        )
    ranked = [
        RankedCost(
            label=repo_short_name(row.repo),
            sub=breakdown_text.sub_line(f"{row.agent_exits:,} runs", row.cost),
            cost=row.cost.evidence.total_usd,
            color=ACCENT,
            figure=breakdown_text.bar_figure(row.cost),
            note=spend_text.spend_line(row.cost),
        )
        for row in rows
    ]
    return cost_horizontal_bars(ranked)


def repo_short_name(repo: str) -> str:
    """The name a bar is labelled by, without the owner that hosts it."""
    if "/" not in repo:
        return repo
    return repo.rsplit("/", maxsplit=1)[-1]
