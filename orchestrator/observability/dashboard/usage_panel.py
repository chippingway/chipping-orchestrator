# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The card the page opens with, and the toggle that decides its stack.

This is the first panel under the KPI strip, so it answers the question the
page is opened with -- whether a day's cost tracks the work behind it -- and
the figure it draws carries both readings at once. What this owner decides is
the card around that figure: the header naming it, the one control an operator
has over it, and the rows the chart is handed for the mode they picked.

The toggle is a two-value radio rather than a checkbox because neither stack is
the drilldown of the other: by token type is what a day's tokens were spent on,
by backend is who spent them, and an operator switches between the two readings
rather than opening one out of the other. The picked mode is kept in the page's
own session state so it survives the rerun Streamlit performs on every
interaction -- a filter change would otherwise snap the hero card back to the
default stack while every panel below it kept the window the operator asked
for. The radio is seeded from that remembered mode by index, since Streamlit
takes the option's position rather than its value.

The per-backend rows are totalled here rather than read that way, because the
same `(day, backend)` cell can arrive more than once and a stack drawn off the
raw rows would show only the last of them. What is totalled is each row's known
non-overlapping total, the volume the token-type stack and the token tile count
too, and beside it each day's runs whose total is unknown -- this read's own
count, since it is issued in a later wave than the series and a sync between
the two can leave them disagreeing about a day, so the marker over the
per-backend stack is counted off the rows that stack was drawn from. They are
totalled only when the backend stack is the one being drawn: the token-type
stack is already carried by the time-series points, so accumulating a window's
backend rows for it would be work no trace uses.

The header, the figure, and the Plotly defaults all come off their owners
directly, so what this card is titled by, drawn as, and configured with are the
same objects every other panel on the page uses. Streamlit is the caller's,
handed in as a parameter, and the figure builder reaches Plotly inside its own
call, so importing this owner costs neither.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from orchestrator.observability.analytics.query.activity_models import (
    BackendDailyTokensRow,
)
from orchestrator.observability.analytics.query.overview_models import (
    TimeSeriesPoint,
)
from orchestrator.observability.dashboard.card_html import card_header_html
from orchestrator.observability.dashboard.charts.usage import usage_over_time
from orchestrator.observability.dashboard.charts.usage_bands import BackendDailyTokens
from orchestrator.observability.dashboard.render_config import PLOTLY_CONFIG

TOKEN_TYPE_MODE = "type"

BACKEND_MODE = "backend"

# Where the picked mode is remembered across a rerun, and the widget the radio
# itself is keyed by. They are distinct: Streamlit owns the widget key and
# resets it with the widget, so the mode is read back off a key of the page's
# own.
STACK_MODE_STATE_KEY = "stack_mode"

STACK_MODE_WIDGET_KEY = "_stack_mode_radio"

STACK_MODE_LABEL = "Stack mode"

CARD_TITLE = "Spend & token usage over time"

CARD_SUBTITLE = "Daily token consumption with cost trend overlaid"


def backend_tokens_by_day(
    backend_daily_rows: Sequence[BackendDailyTokensRow],
) -> BackendDailyTokens:
    """Total a window's known tokens per day and backend, and its runs of unknown total per day, over repeated cells."""
    backend_by_day: dict[date, dict[str, float]] = {}
    unknown_runs: dict[date, int] = {}
    for row in backend_daily_rows:
        by_backend = backend_by_day.setdefault(row.day, {})
        by_backend[row.backend] = (
            by_backend.get(row.backend, 0) + float(row.total_tokens or 0)
        )
        day_unknown = unknown_runs.get(row.day, 0)
        unknown_runs[row.day] = day_unknown + int(row.unknown_token_runs or 0)
    return BackendDailyTokens(backend_by_day, unknown_runs)


def stack_mode_label(mode: str) -> str:
    """Name one stack mode the way the toggle offers it."""
    return "By token type" if mode == TOKEN_TYPE_MODE else "By backend"


def stack_mode_index(mode: str) -> int:
    """Place a remembered mode among the options the radio offers."""
    return 0 if mode == TOKEN_TYPE_MODE else 1


def select_stack_mode(st: Any) -> str:
    """Draw the toggle on the mode the page remembers, and remember it."""
    if STACK_MODE_STATE_KEY not in st.session_state:
        st.session_state[STACK_MODE_STATE_KEY] = TOKEN_TYPE_MODE
    stack_mode = st.radio(
        STACK_MODE_LABEL,
        options=(TOKEN_TYPE_MODE, BACKEND_MODE),
        format_func=stack_mode_label,
        index=stack_mode_index(st.session_state[STACK_MODE_STATE_KEY]),
        horizontal=True,
        label_visibility="collapsed",
        key=STACK_MODE_WIDGET_KEY,
    )
    st.session_state[STACK_MODE_STATE_KEY] = stack_mode
    return stack_mode


def render_hero_usage(
    *,
    st: Any,
    ts_points: Sequence[TimeSeriesPoint],
    backend_daily_rows: Sequence[BackendDailyTokensRow],
) -> None:
    """Render the hero spend and token-usage card."""
    with st.container(border=True):
        st.markdown(
            card_header_html(CARD_TITLE, CARD_SUBTITLE),
            unsafe_allow_html=True,
        )
        stack_mode = select_stack_mode(st)
        backend_by_day = (
            backend_tokens_by_day(backend_daily_rows)
            if stack_mode == BACKEND_MODE
            else None
        )
        st.plotly_chart(
            usage_over_time(
                ts_points,
                backend_rows_by_day=backend_by_day,
                mode=stack_mode,
                title=None,
            ),
            use_container_width=True,
            config=dict(PLOTLY_CONFIG),
        )
