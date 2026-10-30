# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where a window's money went, beside whether the runs behind it held up.

The two columns are paired because the second qualifies the first: a
repository leading the window's spend reads one way on its own and another
once the runs that spend came from are known to have failed or timed out. The
split is 7:5 the way the comparisons above it are, with the repository ranking
in the wider column, since a bar labelled by a repository needs the gutter that
six short tiles and a day strip do not.

The repository ranking closes on a note beneath it: what its bars add up to,
worded the way the overview words a window, so the bases behind them -- each
part of a blended amount by its own amount -- and the runs leaving the amount
short of complete spend are read beside the chart rather than only on hover.

The narrow column carries a strip of tiles over a per-day figure rather than
one or the other, because run health and delivery are the same question asked
twice: the tiles say what the window's runs came to, and the bars beneath them
say when the issues those runs resolved actually landed.

That figure is handed the window's own bounds so a day nothing resolved on
stands as a zero bar rather than dropping off the axis. The closing bound is
the day before the window ends, because the window is half-open -- every read
beneath the page is issued under `ts < end` -- so drawing through `end` itself
would add a trailing empty day no read covered.

Streamlit and the theme are the caller's, carried in the page-state shape this
section is handed rather than named here, which is what keeps a card set and
tinted the way the chrome around it is. Both figures come off the chart owners
directly, the way the headers come off the markup owner and the tiles' numbers
off the KPI owner: a panel is the card and the figure inside it together, and a
builder handed in would let one column be assembled from a chart family the
column beside it was not. Neither builder names Plotly at module scope, so
importing this owner still works in the default install that does not carry it.

The Plotly configuration is read off the owner that holds it at call time
rather than bound here: it is the same decision for every figure on the page,
and it is handed over as a plain dict since that owner publishes a read-only
proxy Plotly cannot serialize.
"""
from __future__ import annotations

from datetime import timedelta

from orchestrator.observability.dashboard import page_models, render_config
from orchestrator.observability.dashboard.breakdown_text import breakdown_note
from orchestrator.observability.dashboard.card_html import (
    card_header_html,
    card_note_html,
    reliability_tiles_html,
)
from orchestrator.observability.dashboard.charts.cost_repo import cost_by_repo
from orchestrator.observability.dashboard.charts.throughput import (
    done_per_day_bars,
)
from orchestrator.observability.dashboard.kpis import reliability_tile_data


def render_repo_and_reliability(
    modules: page_models.DashboardModules,
    panel: page_models.ReliabilityPanelData,
) -> None:
    """Render repository spend and reliability throughput."""
    repo_column, reliability_column = modules.st.columns([7, 5])
    with repo_column, modules.st.container(border=True):
        modules.st.markdown(
            card_header_html(
                "Cost by repository",
                "Spend across managed repos",
            ),
            unsafe_allow_html=True,
        )
        modules.st.plotly_chart(
            cost_by_repo(panel.repos),
            use_container_width=True,
            config=dict(render_config.PLOTLY_CONFIG),
        )
        if panel.repos:
            modules.st.markdown(
                card_note_html(breakdown_note(repo.cost for repo in panel.repos)),
                unsafe_allow_html=True,
            )
    with reliability_column, modules.st.container(border=True):
        modules.st.markdown(
            card_header_html(
                "Reliability & throughput",
                "Run health and issues resolved per day",
            ),
            unsafe_allow_html=True,
        )
        raw_tiles = reliability_tile_data(
            panel.summary,
            resolved=panel.resolved,
            rejected=panel.rejected,
        )
        modules.st.markdown(
            reliability_tiles_html(
                raw_tiles,
                fmt_num=modules.theme.fmt_num,
            ),
            unsafe_allow_html=True,
        )
        modules.st.plotly_chart(
            done_per_day_bars(
                panel.throughput,
                window_start=panel.window.start.date(),
                window_end=(panel.window.end - timedelta(days=1)).date(),
                title=None,
            ),
            use_container_width=True,
            config=dict(render_config.PLOTLY_CONFIG),
        )
