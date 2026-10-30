# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The runs themselves, listed under the panels that summarize them.

Every other panel on the page reduces a window to a reading -- a total, a
ranking, a rate. This one is the rows, so it is the panel an operator lands on
after one of those readings raised a question the aggregate cannot answer:
which run, on which issue, at what cost. That is also why it is the one panel
drawn as `st.dataframe` rather than the hand-rolled table the four beside it
use: it carries no in-row bar, status pill, or sortable heading of its own, and
Streamlit's own table already sorts, widens, and scrolls a raw listing.

It opens collapsed, because the listing is as long as the read's cap allows and
a window's worth of rows expanded by default would push the per-issue
drill-down below it off the screen the page ends on. A window with no
`agent_exit` row renders the notice rather than an empty frame, so the
expander says why it holds nothing instead of showing a header with no rows
under it.

The timestamp is the one reading converted here. Every panel above this one
reports over a window rather than at an instant, so this is the only place a
stored UTC instant is read back as a wall clock -- and the clock it is read in
is the offset the sidebar picked rather than the server's, since the operator
asking which run this was is reading against their own day. The columns are
ordered the way that question is asked: when and where, then what ran, then how
it went, then what it cost.

What it cost is the run's stored evidence worded as the trajectory viewer words
a run: the amount with its basis -- CLI-reported, which is what the CLI printed
and never a verified bill, one provider's API token estimate, or a blended
amount with each part -- and why it falls short of complete spend, or unpriced,
no usage, or unknown where it states no amount. The dates the estimate's rates
were verified on sit beside it, and nothing is re-priced from the tokens. The
token total is the run's non-overlapping one, left empty where its evidence
cannot settle it, beside the raw input and output counters.

Streamlit and pandas are the caller's, handed in as parameters, so this owner
imports neither and the row projection stays readable without either installed.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from orchestrator.observability.analytics.query.run_models import AgentExitRow
from orchestrator.observability.dashboard import cost_text, filters

NO_AGENT_EXITS_MESSAGE = "No `agent_exit` rows match the current filters."
RECENT_RUNS_LABEL = "Recent agent runs"


def recent_run_row(
    exit_row: AgentExitRow,
    offset: timedelta,
) -> dict[str, Any]:
    """The readings one run is listed under, in the order they are columns."""
    return {
        "ts": filters.shift_ts(exit_row.ts, offset),
        "repo": exit_row.repo,
        "issue": exit_row.issue,
        "stage": exit_row.stage,
        "agent": exit_row.agent_role,
        "backend": exit_row.backend,
        "duration (s)": exit_row.duration_s,
        "exit": exit_row.exit_code,
        "timed out": exit_row.timed_out,
        "round": exit_row.review_round,
        "retry": exit_row.retry_count,
        "input tokens": exit_row.input_tokens,
        "output tokens": exit_row.output_tokens,
        "total tokens": exit_row.total_tokens,
        "cost": cost_text.cost_text(exit_row.cost),
        "rates": cost_text.rates_text(exit_row.cost),
    }


def render_recent_runs(
    *,
    st: Any,
    pd: Any,
    agent_exits: Sequence[AgentExitRow],
    tz_offset_choice: int,
) -> None:
    """Render recent agent runs in the selected timezone."""
    with st.expander(RECENT_RUNS_LABEL, expanded=False):
        if not agent_exits:
            st.info(NO_AGENT_EXITS_MESSAGE)
            return
        offset = timedelta(hours=int(tz_offset_choice))
        st.dataframe(
            pd.DataFrame(
                [recent_run_row(exit_row, offset) for exit_row in agent_exits],
            ),
            use_container_width=True,
        )
