# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How an operator gets from a whole read down to the one run they want.

Two surfaces over the same narrowed set, and they answer different questions.
The overview table answers "which run do I want", so it is capped at the most
recent rows a page can be read at a glance -- and it says so, naming how many
matched, because a silently truncated table reads as a complete one. The
picker answers "that one", and it is deliberately *not* capped: it cascades
repository, then issue -- highest number first -- then run, so every match
stays reachable however long the list is.

The fixture caption is the toggle's receipt. It is worded for whichever way the
toggle is set, so an operator reading a shorter table than they expected is told
why, and one reading tagged rows is told how to drop them. It is drawn only
where the read actually held fixtures, since there is nothing to explain
otherwise.

Streamlit is the caller's, handed in rather than imported, so this owner stays
loadable in an install carrying no viewer dependencies at all.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from orchestrator.observability.trajectory_viewer.page_setup import (
    NO_TRAJECTORIES_MESSAGE,
)
from orchestrator.observability.trajectory_viewer.run_html import (
    REPO_LABEL,
    run_picker_label,
    runs_table_html,
)
from orchestrator.observability.trajectory_viewer.run_render import render_run
from orchestrator.observability.trajectory_viewer.runs import TrajectoryRun

RUN_TABLE_LIMIT = 200


def render_no_trajectories(st: Any, log_path: Path | None) -> None:
    """Say that the file held no records, and name the file it read."""
    st.info(NO_TRAJECTORIES_MESSAGE)
    if log_path is not None:
        st.caption(f"Reading `{log_path}`.")


def fixture_caption(fixture_total: int, hide_fixtures: bool) -> str:
    """Word the fixture receipt for whichever way the toggle is set."""
    noun = "run" if fixture_total == 1 else "runs"
    if hide_fixtures:
        return f"{fixture_total} synthetic fixture {noun} hidden."
    return (
        f"{fixture_total} synthetic fixture {noun} flagged; "
        "tick *Hide synthetic fixtures* in the sidebar to drop them."
    )


def render_run_list(
    st: Any,
    shown: Sequence[TrajectoryRun],
    fixture_total: int,
    hide_fixtures: bool,
) -> None:
    """Draw the overview table, capped, and say so where it was capped."""
    with st.expander("Recorded runs", expanded=True):
        st.caption("Most recent first · pick a run below to inspect it")
        st.markdown(
            runs_table_html(shown[:RUN_TABLE_LIMIT]),
            unsafe_allow_html=True,
        )
        if len(shown) > RUN_TABLE_LIMIT:
            st.caption(
                f"Table shows the {RUN_TABLE_LIMIT} most recent of "
                f"{len(shown)} matching runs; the picker below lists all of "
                "them. Narrow the filters to shorten the list."
            )
        if fixture_total:
            st.caption(fixture_caption(fixture_total, hide_fixtures))


def pick_repo(st: Any, shown: Sequence[TrajectoryRun]) -> str:
    """Offer the repositories the narrowed set actually holds."""
    repos = sorted({run.repo for run in shown})
    return st.selectbox(REPO_LABEL, repos)


def pick_issue(st: Any, shown: Sequence[TrajectoryRun], repo: str) -> int:
    """Offer that repository's issues, highest number first.

    Issue numbers grow with time, so the newest work leads the list rather
    than sitting at the bottom of a long one.
    """
    issues = {run.issue for run in shown if run.repo == repo}
    return st.selectbox(
        "Issue",
        sorted(issues, reverse=True),
        format_func=lambda issue: f"#{issue}",
    )


def pick_run(
    st: Any,
    shown: Sequence[TrajectoryRun],
    repo: str,
    issue: int,
) -> TrajectoryRun:
    """Offer that issue's runs, labeled the way the read model labels one."""
    candidates = [
        run
        for run in shown
        if run.repo == repo and run.issue == issue
    ]
    selected = st.selectbox(
        "Run",
        range(len(candidates)),
        format_func=lambda index: run_picker_label(candidates[index]),
    )
    return candidates[selected]


def render_run_picker(st: Any, shown: Sequence[TrajectoryRun]) -> None:
    """Cascade repository, issue, and run, then draw the one that was picked."""
    st.markdown(
        '<p class="orch-card-sub" style="margin:14px 0 4px">Inspect run</p>',
        unsafe_allow_html=True,
    )
    columns = st.columns(3)
    with columns[0]:
        repo = pick_repo(st, shown)
    with columns[1]:
        issue = pick_issue(st, shown, repo)
    with columns[2]:
        run = pick_run(st, shown, repo, issue)
    render_run(st=st, run=run)
