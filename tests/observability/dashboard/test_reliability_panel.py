# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The repository ranking, beside whether the runs behind it held up.

The cases name what the section decides rather than what the two chart
families draw: the split the columns are laid out in, which reading lands in
the wider one, and -- the reading the pairing is bounded by -- the two days the
throughput strip is handed. The page's window is half-open, so the day an
operator's filter closes on is the one before its end, and a case drives a
window whose two ends are seven days apart and reads the bounds straight back
off the builder.

Both builders are the section's own module-scope imports rather than a handle
it is passed, so a recorder stands in for them under `patch.object` on this
owner -- and the page state the render is handed carries no chart handle at
all, which is what says the section reaches the two families directly rather
than through anything the caller threaded down.

The run-health strip is driven for real rather than stubbed, because what the
section decides about it is which readings reach the reduction and whose
formatter renders them: a case builds the same strip off the two owners and
asserts the column carries it.

The Plotly configuration is likewise reached rather than handed, so a case
patches it on the owner that holds it and drives the render, which is what says
the toolbar decision is resolved at call time rather than captured when this
module was imported.
"""

from __future__ import annotations

import unittest
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from orchestrator.observability.analytics.query.activity_models import (
    ThroughputDayRow,
)
from orchestrator.observability.analytics.query.cost_models import (
    RepoBreakdownRow,
)
from orchestrator.observability.analytics.query.overview_models import Summary
from orchestrator.observability.dashboard import (
    card_html,
    kpis,
    page_models,
    reliability_panel,
    render_config,
    windows,
)
from orchestrator.observability.dashboard.charts import cost_repo, throughput
from tests.observability.analytics import analytics_cohorts as cohort_cases, analytics_usage_cases as cases
from tests.observability.dashboard.reliability_panel_test_support import (
    COLUMN_RATIO,
    LEFT,
    RIGHT,
    RecordingCharts,
    ReliabilityStreamlit,
    markup_in,
)

_REPO_BUILDER = "cost_by_repo"

_DAY_BUILDER = "done_per_day_bars"

_YEAR = 2026

# A week-long window, spelled as the half-open pair every read below the page
# is issued under so the last day an operator asked for is not its end.
_WINDOW = windows.DateWindow(
    start=datetime(_YEAR, 3, 1, tzinfo=UTC),
    end=datetime(_YEAR, 3, 8, tzinfo=UTC),
)

_LAST_DRAWN_DAY = date(_YEAR, 3, 7)

# Six readings no two of which are equal, so a keyword handed to the wrong
# tile shows up as a number in the wrong place rather than as nothing.
_SUMMARY = Summary(
    total_agent_runs=8,
    failed_agent_runs=2,
    timed_out_agent_runs=1,
)

_RESOLVED = 5

_REJECTED = 3

# One repository whose runs blend a CLI-reported amount with a Gemini API
# token estimate, so the note under the ranking lists both parts.
_REPO_COST = cohort_cases.cohort(cases.REPORTED, cases.GEMINI_ESTIMATE)

_PANEL = page_models.ReliabilityPanelData(
    repos=(RepoBreakdownRow(repo="owner/one", issues=2, events=9, agent_exits=2, cost=_REPO_COST),),
    summary=_SUMMARY,
    throughput=(ThroughputDayRow(day=date(_YEAR, 3, 2), resolved=2),),
    window=_WINDOW,
    resolved=_RESOLVED,
    rejected=_REJECTED,
)

_TOOLBAR_KEY = "displayModeBar"

# The Streamlit options each call carries, named rather than spelled at every
# assertion.
_MARKUP_OPTION = "unsafe_allow_html"

_WIDTH_OPTION = "use_container_width"

_CONFIG_OPTION = "config"


def marked_number(number: int) -> str:
    """Format a tile the way nothing but the caller's own theme would."""
    return f"[{number}]"


def render_panel() -> tuple[ReliabilityStreamlit, RecordingCharts]:
    """Draw the whole section for that window onto a fake page."""
    page = ReliabilityStreamlit()
    charts = RecordingCharts()
    modules = page_models.DashboardModules(
        st=page,
        pd=None,
        theme=SimpleNamespace(fmt_num=marked_number),
    )
    with (
        patch.object(reliability_panel, _REPO_BUILDER, charts.cost_by_repo),
        patch.object(reliability_panel, _DAY_BUILDER, charts.done_per_day_bars),
    ):
        reliability_panel.render_repo_and_reliability(modules, _PANEL)
    return page, charts


class ChartBindingTest(unittest.TestCase):
    """Both figures are the chart owners' own builders, not a handed-in hub."""

    def test_each_column_is_bound_to_its_family(self) -> None:
        # A section is the card and the figure inside it together. Reaching a
        # builder through a handle the caller passed down would let the
        # ranking and the strip beside it be assembled from chart families the
        # panels around them are not.
        self.assertIs(
            getattr(reliability_panel, _REPO_BUILDER), cost_repo.cost_by_repo,
        )
        self.assertIs(
            getattr(reliability_panel, _DAY_BUILDER),
            throughput.done_per_day_bars,
        )


class ReliabilityRenderOptionTest(unittest.TestCase):
    """Each payload is handed over the way it has to be to be seen."""

    def test_each_column_is_drawn_in_a_bordered_card(self) -> None:
        # The outline is what makes each column read as its own panel rather
        # than as two halves of one strip drawn across the gutter.
        page, _ = render_panel()
        self.assertEqual(page.borders, [(LEFT, True), (RIGHT, True)])

    def test_every_payload_is_handed_over_as_markup(self) -> None:
        # A header and a tile strip are both HTML the markup owner built, so a
        # column handed either without this flag prints the tags an operator
        # was meant to read through.
        page, _ = render_panel()
        for drawn in page.markdowns:
            with self.subTest(column=drawn.column):
                self.assertIs(drawn.options[_MARKUP_OPTION], True)

    def test_each_figure_fills_the_column_it_is_in(self) -> None:
        # Both figures are sized by the 7:5 split above them, so one left at
        # Plotly's own width would sit in a column measured for something else.
        page, _ = render_panel()
        for drawn in page.figures:
            with self.subTest(column=drawn.column):
                self.assertIs(drawn.options[_WIDTH_OPTION], True)


class RepoAndReliabilityTest(unittest.TestCase):
    """The section lays both readings out and bounds the day strip."""

    def test_the_repo_ranking_takes_the_wider_column(self) -> None:
        page, charts = render_panel()
        self.assertEqual(page.column_request, COLUMN_RATIO)
        drawn_in = {
            drawn.column: drawn.payload.builder for drawn in page.figures
        }
        self.assertEqual(
            drawn_in, {LEFT: _REPO_BUILDER, RIGHT: _DAY_BUILDER},
        )
        self.assertEqual(len(charts.requests), len(page.figures))

    def test_each_column_is_headed_by_its_own(self) -> None:
        # The markup owner escapes what a header was titled with, so the
        # ampersand the narrow column is named by reaches a browser encoded.
        page, _ = render_panel()
        self.assertIn("Cost by repository", markup_in(page, LEFT))
        self.assertIn("Reliability &amp; throughput", markup_in(page, RIGHT))

    def test_the_ranking_is_closed_by_its_basis(self) -> None:
        # What the repository bars add up to is worded beneath them, a blended
        # amount with each basis's own, rather than left to the hover alone.
        page, _ = render_panel()
        self.assertIn(
            "Bars total $0.54 (blended: CLI-reported $0.42 + Gemini API token estimate $0.12)",
            markup_in(page, LEFT),
        )

    def test_the_day_strip_ends_inside_the_window(self) -> None:
        # The window is half-open, so drawing through its end would add a
        # trailing day no read beneath the page covered. The strip is titled by
        # the card above it rather than by itself.
        _, charts = render_panel()
        strip = charts.requests[-1]
        self.assertEqual(strip.rows, _PANEL.throughput)
        self.assertEqual(
            strip.bounds,
            {
                "window_start": _WINDOW.start.date(),
                "window_end": _LAST_DRAWN_DAY,
                "title": None,
            },
        )

    def test_the_tiles_are_rendered_by_the_caller(self) -> None:
        # What the section decides about the strip is which readings reach the
        # reduction -- the window's own totals, with the two throughput counts
        # named rather than positional -- and that the numbers are written by
        # the theme the page resolved rather than by a formatter of its own.
        page, _ = render_panel()
        self.assertIn(
            card_html.reliability_tiles_html(
                kpis.reliability_tile_data(
                    _SUMMARY, resolved=_RESOLVED, rejected=_REJECTED,
                ),
                fmt_num=marked_number,
            ),
            markup_in(page, RIGHT),
        )

    def test_the_toolbar_choice_is_read_at_call(self) -> None:
        # Every figure on the page is drawn under one configuration, and the
        # owner publishes it as a proxy Plotly cannot serialize -- so each
        # chart is handed a plain-dict copy of whatever that owner holds when
        # the section runs.
        sentinel = {_TOOLBAR_KEY: True}
        with patch.object(render_config, "PLOTLY_CONFIG", sentinel):
            page, _ = render_panel()
        handed = [drawn.options[_CONFIG_OPTION] for drawn in page.figures]
        self.assertEqual(handed, [sentinel, sentinel])
        for config in handed:
            self.assertIsInstance(config, dict)
            self.assertIsNot(config, sentinel)


if __name__ == "__main__":
    unittest.main()
