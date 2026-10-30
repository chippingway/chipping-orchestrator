# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The ranked issues and the backends that ran them, drawn side by side.

The cases name what the section decides rather than what the table and the two
card builders under it draw: the split the columns are laid out in, which
reading lands in the wider one, the depth the ranking is cut to, and that it is
drawn in the order the read ranked it. The coverage bar is here for where it lands rather than for what
it says -- it closes the backend column because it qualifies the money the
cards above it report, and a window with no cost-source split leaves it undrawn
rather than claiming a coverage reading nothing supports.

Both empty states are driven too, because the two columns are empty for
different reasons: the ranking lists every issue the filters leave, priced or
not, and a window with no `agent_exit` row has no run to card. Each is pinned
against the whole sentence spelled out here rather than against the constant the
render reads it from: a case that
compares a notice to its own source passes whatever that source is reworded to,
which is the one thing an empty-state assertion exists to catch. The published
constant is held to the same literal separately, because the page imports it
under a spelling of its own and a rewording there lands on a caller this owner
never sees.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from orchestrator.observability.analytics.query.cost_models import (
    BackendEfficiencyRow,
    CostCoverageRow,
)
from orchestrator.observability.analytics.query.run_models import (
    IssueSummaryRow,
)
from orchestrator.observability.dashboard import issue_cost_panel
from orchestrator.observability.dashboard.kpis import DEFAULT_EXPENSIVE_LIMIT
from orchestrator.observability.usage import cost_evidence as usage_cost
from tests.observability.analytics import analytics_cohorts as cohort_cases, analytics_usage_cases as cases
from tests.observability.dashboard.card_test_support import (
    BACKEND_CLAUDE,
    BACKEND_CODEX,
    CLAUDE_COLOR,
    CODEX_COLOR,
    COST_SOURCE_REPORTED,
    REPORTED_COLOR,
    card_theme,
)
from tests.observability.dashboard.cost_panel_test_support import (
    COLUMN_RATIO,
    LEFT,
    RIGHT,
    CostPanelStreamlit,
    markup_in,
    notices_in,
)

_REPO = "acme/orchestrator"

_YEAR = 2026

_SEEN = datetime(_YEAR, 5, 1, tzinfo=UTC)

# One issue per cost, handed over in the order the read ranked them, which is
# the order the section draws them in.
_COSTS = (3.0, 2.0, 1.0)

_RANKED_TEXT = ("$3.00", "$2.00", "$1.00")

_RANKING_MEASURE = "Ranked by stated cost, a subtotal at its known part"

_NO_ISSUES = "No issues match the current filters."

_NO_AGENT_EXITS = "No `agent_exit` rows match the current filters."

# One row of markup per issue plus the heading row above them.
_HEADING_ROWS = 1

# The Streamlit option every payload here has to carry to be read as markup
# rather than printed as its own source.
_MARKUP_OPTION = "unsafe_allow_html"


def issue_row(number: int, cost: float | None) -> IssueSummaryRow:
    """One issue whose one run reported `cost`, or, for `None`, could not be priced."""
    spent = cases.UNPRICED if cost is None else cases.cost(
        usage_cost.COMPLETE, cases.contribution(usage_cost.CLI_REPORTED, cost),
    )
    return IssueSummaryRow(
        repo=_REPO,
        issue=number,
        event_count=1,
        first_seen=_SEEN,
        last_seen=_SEEN,
        latest_stage="implementing",
        agent_exits=1,
        cost=cohort_cases.cohort(spent),
        stated_cost_usd=cost,
    )


def issue_rows(*costs: float | None) -> list[IssueSummaryRow]:
    """One issue per cost, numbered in the order they are handed over."""
    return [issue_row(number, cost) for number, cost in enumerate(costs, start=1)]


def backend_rows(*backends: str) -> list[BackendEfficiencyRow]:
    """One efficiency row per named backend, priced so a card renders.

    The three readings a card reports are the card owner's own arithmetic, so
    a row here carries only what makes the card render at all.
    """
    return [
        BackendEfficiencyRow(backend=backend, runs=1, total_cost_usd=1.0)
        for backend in backends
    ]


def render_panel(
    *,
    costs: tuple[float | None, ...] = _COSTS,
    backends: tuple[str, ...] = (BACKEND_CLAUDE, BACKEND_CODEX),
    coverage: tuple[str, ...] = (COST_SOURCE_REPORTED,),
) -> CostPanelStreamlit:
    """Draw the whole section for that window onto a fake page."""
    page = CostPanelStreamlit()
    issue_cost_panel.render_issues_and_backends(
        st=page,
        theme=card_theme(),
        issues_rows=issue_rows(*costs),
        backend_rows=backend_rows(*backends),
        cost_coverage_rows=[
            CostCoverageRow(cost_source=source, runs=1, total_tokens=100)
            for source in coverage
        ],
    )
    return page


class IssueCostLayoutTest(unittest.TestCase):
    """The ranking takes the wider column; the cards and bar take the other."""

    def test_the_ranking_takes_the_wider_column(self) -> None:
        page = render_panel()
        self.assertEqual(page.column_request, COLUMN_RATIO)
        self.assertIn("Most expensive issues", markup_in(page, LEFT))
        self.assertIn(_RANKING_MEASURE, markup_in(page, LEFT))
        self.assertIn("Backend efficiency", markup_in(page, RIGHT))

    def test_the_reads_ranking_is_drawn_in_order(self) -> None:
        drawn = markup_in(render_panel(), LEFT)
        placements = [drawn.index(amount) for amount in _RANKED_TEXT]
        self.assertEqual(placements, sorted(placements))

    def test_an_unpriced_issue_is_listed_unpriced(self) -> None:
        # An issue nobody could price ran all the same, so the read ranks it
        # after every priced one rather than dropping it, and it is worded
        # unpriced rather than as a free issue.
        drawn = markup_in(render_panel(costs=(1.0, None)), LEFT)
        self.assertLess(drawn.index("$1.00"), drawn.index(">unpriced<"))
        self.assertNotIn("$0.00", drawn)

    def test_the_ranking_stops_at_the_owners_cap(self) -> None:
        # The depth is the KPI owner's decision, so the section must not list
        # every issue a wide window carries.
        deep = tuple(
            float(rank)
            for rank in range(DEFAULT_EXPENSIVE_LIMIT + 3, 0, -1)
        )
        drawn = markup_in(render_panel(costs=deep), LEFT)
        self.assertEqual(
            drawn.count("</tr>"), DEFAULT_EXPENSIVE_LIMIT + _HEADING_ROWS,
        )

    def test_each_backend_gets_its_own_card(self) -> None:
        drawn = markup_in(render_panel(), RIGHT)
        self.assertIn(CLAUDE_COLOR, drawn)
        self.assertIn(CODEX_COLOR, drawn)

    def test_the_coverage_bar_closes_the_column(self) -> None:
        drawn = markup_in(render_panel(), RIGHT)
        self.assertLess(drawn.index(CLAUDE_COLOR), drawn.index(REPORTED_COLOR))

    def test_a_window_without_coverage_omits_it(self) -> None:
        drawn = markup_in(render_panel(coverage=()), RIGHT)
        self.assertNotIn(REPORTED_COLOR, drawn)


class IssueCostRenderOptionTest(unittest.TestCase):
    """Every payload is handed over the way it has to be to be seen."""

    def test_each_column_is_drawn_in_a_bordered_card(self) -> None:
        # The outline is what makes the ranking and the cards beside it read as
        # two panels rather than one run-on stretch of page.
        page = render_panel()
        self.assertEqual(page.borders, [(LEFT, True), (RIGHT, True)])

    def test_every_payload_is_handed_over_as_markup(self) -> None:
        # The headers, the ranking table, the backend cards, and the coverage
        # bar are all HTML their owners built, so a column handed any of them
        # without this flag prints the tags instead of what they draw.
        page = render_panel()
        self.assertTrue(page.markdowns)
        for drawn in page.markdowns:
            with self.subTest(column=drawn.column):
                self.assertIs(drawn.options[_MARKUP_OPTION], True)


class IssueCostEmptyStateTest(unittest.TestCase):
    """Each column says why it is empty in its own terms."""

    def test_a_window_with_no_issue_says_so(self) -> None:
        page = render_panel(costs=())
        self.assertEqual(notices_in(page, LEFT), [_NO_ISSUES])
        self.assertEqual(notices_in(page, RIGHT), [])

    def test_a_window_with_no_runs_says_so(self) -> None:
        page = render_panel(backends=())
        self.assertEqual(notices_in(page, RIGHT), [_NO_AGENT_EXITS])
        self.assertEqual(notices_in(page, LEFT), [])

    def test_the_published_notice_is_that_sentence(self) -> None:
        # A page has imported this one under its own spelling since the backend
        # cards were first drawn, so what it says is a surface rather than an
        # implementation detail of the column that renders it.
        self.assertEqual(
            issue_cost_panel.NO_AGENT_EXITS_MESSAGE, _NO_AGENT_EXITS,
        )


if __name__ == "__main__":
    unittest.main()
