# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The page a render pass is driven against, and what it draws onto.

Streamlit lives in the optional `dashboard` dependency group, so the render
cases hand a page stand-in recording the markup written into it. The chrome
goes into two slots rather than the page body, so each region is its own
recorder and a case can say which of the three a pass wrote into rather than
only that it wrote.

The theme marks every reading a formatter was handed, so a count reaching the
markup raw can be told from one the page shortened, and the reads are answered
with their own names, so a case can say which read family reached which panel.

A pass driven end-to-end rather than against stubs needs the rest of the page
surface and rows the panels can actually draw; both live beside this module in
`section_render_test_support`, which reads its window, theme, and page state
back off the names here so the two sets of cases stay comparable.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import ExitStack
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

from orchestrator.observability.analytics.query.overview_models import DataExtent
from orchestrator.observability.dashboard import page_models, windows

_YEAR = 2026

_MAY = 5

WINDOW_START = datetime(_YEAR, _MAY, 1, tzinfo=UTC)

WINDOW_END = datetime(_YEAR, _MAY, 8, tzinfo=UTC)

WINDOW = windows.DateWindow(start=WINDOW_START, end=WINDOW_END)

# The half-open window's own dates, and the last day any read beneath the page
# covered: every one of them is issued under `ts < end`.
WINDOW_START_DATE = "2026-05-01"

WINDOW_END_DATE = "2026-05-08"

LAST_COVERED_DATE = "2026-05-07"

# The offset the sidebar picked, which two of the panels are handed.
TZ_OFFSET = 3

# The theme, with each formatter marking what it was handed so a case can say
# which readings reached the markup shortened rather than raw.
THEME = SimpleNamespace(
    fmt_num=lambda number: f"<{number}>",
    fmt_money=lambda amount: f"[{amount}]",
    fmt_money_exact=lambda amount: f"[[{amount}]]",
    fmt_tokens=lambda count: f"{{{count}}}",
    ACCENT="#a11e11",
    TOKEN_TYPE_COLORS={"Input": "#111111", "Cache": "#222222"},
)

# Every read the two section owners hand a panel, answered with its own name so
# a case reads back which family reached which card.
SECTION_READS = (
    "agent_exits",
    "backend_daily_rows",
    "backend_rows",
    "cost_coverage_rows",
    "heatmap_rows",
    "issues_rows",
    "repo_rows",
    "review_round_rows",
    "skill_adoption_rows",
    "skill_matrix_rows",
    "skill_rows",
    "stage_rows",
    "summary",
    "throughput_rows",
    "ts_points",
)


class RecordingRegion:
    """One region of the page, recording the markup written into it."""

    def __init__(self) -> None:
        self.markup: list[tuple[str, dict]] = []

    def markdown(self, body: str, **options) -> None:
        self.markup.append((body, options))


def markup_in(region: RecordingRegion) -> str:
    """Everything written into one region, joined for a substring check."""
    return "".join(body for body, _ in region.markup)


def modules(st: Any, *, frames: Any = None) -> page_models.DashboardModules:
    """The caller's handles, with the marking theme among them."""
    return page_models.DashboardModules(
        st=st, pd=frames, theme=THEME,
    )


def page(
    *,
    topbar: Any = None,
    meta: Any = None,
    reads: Any = None,
    issue: int | None = None,
) -> page_models.DashboardPage:
    """A page opened on the window above, with the two chrome slots given.

    `issue` is the number an operator typed into the sidebar, which is what
    opens the trace at the foot of the page.
    """
    return page_models.DashboardPage(
        extent=DataExtent(min_ts=WINDOW_START, max_ts=WINDOW_END),
        controls=page_models.DashboardControls(
            filters=page_models.DashboardFilters(
                window=WINDOW,
                repo=None,
                issue_input=issue,
                events=None,
                stages=None,
            ),
            topbar_slot=topbar,
            meta_slot=meta,
            timezone_offset=TZ_OFFSET,
        ),
        reads=reads,
    )


def loaded(
    read_results: dict[str, Any],
    *,
    resolved: int = 0,
    rejected: int = 0,
) -> page_models.LoadedDashboard:
    """What one completed load hands the sections beneath the strip."""
    return page_models.LoadedDashboard(
        read_results=read_results,
        kpis=page_models.DashboardKpis(
            tiles=(), resolved=resolved, rejected=rejected,
        ),
    )


def section_reads() -> dict[str, str]:
    """Every read a section names, each answering with its own key."""
    return {name: name for name in SECTION_READS}


def draw_sections(
    panels: Sequence[tuple[Any, str]],
    render: Callable[[], None],
) -> tuple[list[str], Mock]:
    """Run one section pass with every panel stubbed on the owner it lives on.

    The stubs are attached to one recorder, so the order the pass reached them
    in is read back off a single call list rather than assembled from five
    mocks that each only know their own turn.
    """
    recorder = Mock()
    with ExitStack() as sections:
        for owner, attribute in panels:
            recorder.attach_mock(Mock(), attribute)
            sections.enter_context(
                patch.object(owner, attribute, getattr(recorder, attribute)),
            )
        render()
    return [drawn for drawn, _, _ in recorder.mock_calls], recorder
