# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Who a window's spend went to: the costliest issues, and the backends run.

The pair beneath the lifecycle bars answers the other half of the same
question. The left column names the work -- the window's issues ranked by what
they cost -- and the right names the agent that did it, so an operator reading
an expensive issue can see in the same glance whether the backend behind it is
expensive per run or merely busy. The columns are split 7:5 the way the bars
above them are, because a ranked table of repositories and issue numbers needs
the room a stack of single-backend cards does not.

The ranking's header names the measure it is ordered by -- the cost an
issue's runs state, a subtotal at its known part -- because the rows beneath it
can hold a subtotal beside a complete amount, and each row's own note says
which it is.

The two columns render different empty states, because they are empty for
different reasons. The ranking lists every issue the filters leave, priced or
not, so it is empty only where no issue matched at all; the cards beside it are
drawn from `agent_exit` rows directly, so their absence is the window having no
run to report.

The coverage bar closes the right column rather than standing on its own,
because it is the qualification on the money the cards above it report: what
share of the window's spend the parser could attribute a price to at all. It is
drawn only when the window carries that split -- a bar with nothing to divide
would claim a coverage reading the window has no rows to support.

Streamlit and the theme are the caller's, handed in as parameters, so this
owner names neither: a page resolves one theme and passes it down, which is
what keeps a card tinted and set the way the chrome around it is.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from orchestrator.observability.analytics.query.cost_models import (
    BackendEfficiencyRow,
    CostCoverageRow,
)
from orchestrator.observability.analytics.query.run_models import (
    IssueSummaryRow,
)
from orchestrator.observability.dashboard.backend_card import (
    backend_efficiency_card_html,
)
from orchestrator.observability.dashboard.card_html import card_header_html
from orchestrator.observability.dashboard.coverage_card import (
    cost_coverage_bar_html,
)
from orchestrator.observability.dashboard.issue_table import issues_table_html
from orchestrator.observability.dashboard.kpis import top_expensive_issues

NO_AGENT_EXITS_MESSAGE = "No `agent_exit` rows match the current filters."

NO_ISSUES_MESSAGE = "No issues match the current filters."


def render_issues_and_backends(
    *,
    st: Any,
    theme: Any,
    issues_rows: Sequence[IssueSummaryRow],
    backend_rows: Sequence[BackendEfficiencyRow],
    cost_coverage_rows: Sequence[CostCoverageRow],
) -> None:
    """Render the top-cost issues and backend-efficiency columns."""
    issues_column, backend_column = st.columns([7, 5])
    with issues_column, st.container(border=True):
        st.markdown(
            card_header_html(
                "Most expensive issues",
                "Ranked by stated cost, a subtotal at its known part",
            ),
            unsafe_allow_html=True,
        )
        expensive = top_expensive_issues(issues_rows)
        if expensive:
            st.markdown(issues_table_html(expensive), unsafe_allow_html=True)
        else:
            st.info(NO_ISSUES_MESSAGE)
    with backend_column, st.container(border=True):
        st.markdown(
            card_header_html(
                "Backend efficiency",
                "Cost density, cache leverage, $/run",
            ),
            unsafe_allow_html=True,
        )
        if backend_rows:
            for row in backend_rows:
                st.markdown(
                    backend_efficiency_card_html(row, theme=theme),
                    unsafe_allow_html=True,
                )
        else:
            st.info(NO_AGENT_EXITS_MESSAGE)
        if cost_coverage_rows:
            st.markdown(
                cost_coverage_bar_html(cost_coverage_rows, theme=theme),
                unsafe_allow_html=True,
            )
