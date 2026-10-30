# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where a window's spend landed across the lifecycle, as two paired bars.

The two figures answer the same question along different axes -- which stage of
the issue lifecycle the money went to, and which review cycle it went to -- so
they are drawn beside each other rather than one under the other, and an
operator reads them as one comparison. The columns are split 7:5 rather than
evenly because the stage axis carries the wider vocabulary: a full stage name
needs the room that a round bucket, which is a digit or `6+`, does not.

Each figure is closed by a note beneath it rather than left to its hover alone:
what its bars add up to, worded the way the overview words a window -- the
basis, each part of a blended amount by its own amount, and the runs that leave
it short of complete spend -- and that the cache and non-cache segments are an
allocation by token share rather than a measured cache charge, with the amount
of runs whose token total is unknown left unsplit. A panel with no bar to sum
notes nothing.

Both figures are pinned to one height: whichever of the two needs more, as
each chart owner measures its own -- a full row per bucket beneath the band its
legend lines take, a review row tall enough for two bars. A horizontal bar
family sizes itself by its own row count, so two panels left to size themselves
would stand at different heights the moment one axis had more buckets than the
other, and a height counted off the rows alone would hand the legend band out
of the rows' share, which is how a column's two-line labels come to overlap.

Streamlit is the caller's, handed in as a parameter, so this owner does not
name it. Both figures come off the chart owners directly, the way the header
above them comes off the markup owner: a panel is the card and the figure
inside it together, and a builder handed in would let the two be assembled from
different chart families -- which is how a pair pinned to one height ends up
drawn by two that measure it differently. Neither builder names Plotly at
module scope, reaching it inside its own call instead, so importing this owner
still works in the default install that does not carry it.

The Plotly configuration is read off the owner that holds it at call time
rather than bound here: it is the same decision for every figure on the page,
and it is handed over as a plain dict since that owner publishes a read-only
proxy Plotly cannot serialize.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from orchestrator.observability.analytics.query.cost_cohorts import CostCohort
from orchestrator.observability.analytics.query.cost_models import (
    ReviewRoundBucketRow,
)
from orchestrator.observability.analytics.query.run_models import StageBreakdown
from orchestrator.observability.dashboard import render_config
from orchestrator.observability.dashboard.breakdown_text import TOKEN_SHARE_NOTE, breakdown_note
from orchestrator.observability.dashboard.card_html import card_header_html, card_note_html
from orchestrator.observability.dashboard.charts.cost_review import (
    cost_by_review_round,
    review_panel_height,
)
from orchestrator.observability.dashboard.charts.cost_stage import cost_by_stage, stage_panel_height


def render_split_note(st: Any, cohorts: Sequence[CostCohort]) -> None:
    """Close a split's card on what its bars add up to and what its segments are; a split with no bar notes nothing."""
    if cohorts:
        st.markdown(
            card_note_html(breakdown_note(cohorts), TOKEN_SHARE_NOTE),
            unsafe_allow_html=True,
        )


def paired_bars_height(
    stage_rows: Sequence[StageBreakdown],
    review_rows: Sequence[ReviewRoundBucketRow],
) -> int:
    """The height both bar panels are pinned to: whichever needs more for its rows beneath its legend."""
    return max(stage_panel_height(stage_rows), review_panel_height(review_rows))


def render_stage_review_bars(
    *,
    st: Any,
    stage_rows: Sequence[StageBreakdown],
    review_round_rows: Sequence[ReviewRoundBucketRow],
) -> None:
    """Render aligned per-stage and per-review-round cost bars."""
    bars_height = paired_bars_height(stage_rows, review_round_rows)
    stage_column, round_column = st.columns([7, 5])
    with stage_column, st.container(border=True):
        st.markdown(
            card_header_html(
                "Cost by workflow stage",
                "Where spend lands across the issue lifecycle",
            ),
            unsafe_allow_html=True,
        )
        st.plotly_chart(
            cost_by_stage(stage_rows, height=bars_height),
            use_container_width=True,
            config=dict(render_config.PLOTLY_CONFIG),
        )
        render_split_note(st, [row.cost for row in stage_rows])
    with round_column, st.container(border=True):
        st.markdown(
            card_header_html(
                "Development and review by round",
                "Developer and reviewer spend per review cycle",
            ),
            unsafe_allow_html=True,
        )
        st.plotly_chart(
            cost_by_review_round(
                review_round_rows,
                height=bars_height,
            ),
            use_container_width=True,
            config=dict(render_config.PLOTLY_CONFIG),
        )
        render_split_note(st, [row.cost for row in review_round_rows])
