# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The panel a window's costliest issues are ranked into.

The cases name what the panel decides rather than what the shared table draws:
the six columns an operator reads across, the bar each row's spend is sized
against the costliest row by, the tone a review round crosses into once an
issue has been round-tripped past what the flow expects, and the pill that
answers whether the issue needs looking at rather than counting the runs it
took. An empty window is here too, because the panel is what a page opened to
find out that a window is empty renders.

Each row's spend is the cohort the read hands back for runs stating a set of
costs, so the cost cell is read for what an operator sees: a CLI-reported
amount, one provider's estimates, a blended total with each part, a subtotal
beside unpriced usage, an issue nobody priced, an amount stored with no basis,
and an issue with no run -- none of them passing for complete spend or a zero
it is not.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import UTC, datetime

from orchestrator.observability.analytics.query.run_models import (
    IssueSummaryRow,
)
from orchestrator.observability.dashboard import issue_table
from orchestrator.observability.usage import cost_evidence as usage_cost
from tests.observability.analytics import analytics_cohorts as cohort_cases, analytics_usage_cases as cases

_YEAR = 2026

_FIRST_SEEN = datetime(_YEAR, 5, 1, tzinfo=UTC)

_LAST_SEEN = datetime(_YEAR, 5, 2, tzinfo=UTC)

_REPO = "acme/orchestrator"

_OTHER_REPO = "acme/tooling"

_STAGE = "implementing"

_AGENT_EXITS = 4

# The costliest row in a case and the one drawn at half its width, so the two
# widths are readable off the rendered markup.
_TOP_COST = 10.0

_HALF_COST = 5.0

_HALF_COST_TEXT = "$5.00"

_HALF_PCT = 50

_FULL_WIDTH = "width:100.0%"

_HALF_WIDTH = "width:50.0%"

_EMPTY_WIDTH = "width:0.0%"

# The round an issue is toned at, and the one below it that stays plain.
_WARN_ROUND = 3

_PLAIN_ROUND = 2

_FAILED_RUNS = 3

_NOTE_CLASS = "orch-issue-cost-note"

_PARTIAL_BAR = 'class="partial"'


def _reported(amount: float) -> usage_cost.CostEvidence:
    return cases.cost(usage_cost.COMPLETE, cases.contribution(usage_cost.CLI_REPORTED, amount))


@dataclass(frozen=True)
class _IssueCase:
    repo: str = _REPO
    issue: int = 1
    costs: tuple[usage_cost.CostEvidence, ...] = (_reported(_TOP_COST),)
    failed: int = 0
    max_round: int | None = None
    max_retry: int | None = None


# What each kind of issue's cost cell reads: the figure, the note beneath it,
# and whether its bar is drawn open for an amount short of complete spend.
_WORDED_ISSUES = (
    ("reported", (cases.REPORTED,), ("$0.42", "CLI-reported", False)),
    (
        "antigravity only",
        (cases.GEMINI_ESTIMATE, cases.LATER_GEMINI_ESTIMATE),
        ("$0.32", "Gemini API token estimate", False),
    ),
    (
        "mixed",
        (cases.BLENDED,),
        ("$0.15", "blended: CLI-reported $0.10 + OpenAI API token estimate $0.05", False),
    ),
    (
        "incomplete",
        (cases.ANTHROPIC_ESTIMATE, cases.INCOMPLETE_SUBTOTAL, cases.UNPRICED),
        (
            "$0.50",
            "Anthropic API token estimate · incomplete subtotal: 2 of 3 runs unpriced or partly priced",
            True,
        ),
    ),
    ("unpriced", (cases.UNPRICED,), ("unpriced", "1 of 1 runs unpriced or partly priced", False)),
    (
        "missing basis",
        (cases.ABSENT_BASIS,),
        ("$0.07", "basis unknown · completeness unknown: 1 of 1 runs state no cost evidence", True),
    ),
    ("complete zero", (cases.COMPLETE_ZERO,), ("$0.00", "CLI-reported", False)),
    ("no runs", (), ("—", "no agent runs", False)),
)


def _row(case: _IssueCase) -> IssueSummaryRow:
    """One read row, carrying only the fields a cell is drawn from."""
    cohort = cohort_cases.cohort(*case.costs)
    return IssueSummaryRow(
        repo=case.repo,
        issue=case.issue,
        event_count=10,
        first_seen=_FIRST_SEEN,
        last_seen=_LAST_SEEN,
        latest_stage=_STAGE,
        agent_exits=_AGENT_EXITS,
        cost=cohort,
        stated_cost_usd=cohort.evidence.total_usd,
        max_review_round=case.max_round,
        failed_agent_runs=case.failed,
        max_retry_count=case.max_retry,
    )


def _rendered(*cases: _IssueCase) -> str:
    """The panel those issues are ranked into."""
    return issue_table.issues_table_html([_row(case) for case in cases])


class IssuesTableHtmlTest(unittest.TestCase):
    """What the panel reports across its six columns, and how it is sized."""

    def test_every_column_is_headed(self) -> None:
        rendered = _rendered(_IssueCase())
        for header, _aligned in issue_table.ISSUES_TABLE_COLUMNS:
            with self.subTest(header=header):
                self.assertIn(f">{header}<", rendered)

    def test_a_bar_is_a_share_of_the_costliest_row(self) -> None:
        rendered = _rendered(
            _IssueCase(costs=(_reported(_TOP_COST),)),
            _IssueCase(repo=_OTHER_REPO, issue=2, costs=(_reported(_HALF_COST),)),
        )
        self.assertIn(_FULL_WIDTH, rendered)
        self.assertIn(_HALF_WIDTH, rendered)
        self.assertNotIn(_PARTIAL_BAR, rendered)

    def test_a_window_nobody_priced_draws_empty_bars(self) -> None:
        # There is no costliest row to be a share of, so the panel divides by
        # one rather than raising on the page opened to find that out -- and
        # the issue reads unpriced, never as a zero.
        rendered = _rendered(_IssueCase(costs=(cases.UNPRICED,)))
        self.assertIn(_EMPTY_WIDTH, rendered)
        self.assertIn(">unpriced<", rendered)
        self.assertNotIn("$0.00", rendered)

    def test_a_subtotal_is_noted_and_drawn_open(self) -> None:
        # The bar is the subtotal's known part, sized like any other, but open,
        # and the note under the figure says what it falls short of.
        rendered = _rendered(
            _IssueCase(costs=(cases.ANTHROPIC_ESTIMATE, cases.INCOMPLETE_SUBTOTAL)),
        )
        self.assertIn(f'<span {_PARTIAL_BAR} style="{_FULL_WIDTH}">', rendered)
        self.assertIn(
            f'$0.50<span class="{_NOTE_CLASS}">Anthropic API token estimate · incomplete subtotal: '
            + "1 of 2 runs unpriced or partly priced</span>",
            rendered,
        )

    def test_an_empty_window_is_headers_and_no_rows(self) -> None:
        rendered = _rendered()
        self.assertIn("<tbody></tbody>", rendered)
        self.assertIn(">Issue<", rendered)

    def test_the_repository_is_named_and_escaped(self) -> None:
        rendered = _rendered(_IssueCase(repo="acme/we<b>ird"))
        self.assertIn("we&lt;b&gt;ird", rendered)
        self.assertNotIn("we<b>ird", rendered)


class IssueRowReadingsTest(unittest.TestCase):
    """The two readings a row's rework and run health are drawn from."""

    def test_the_status_pill_answers_clean_or_a_count(self) -> None:
        clean = issue_table.issue_status_pill(0)
        failing = issue_table.issue_status_pill(_FAILED_RUNS)
        self.assertIn('class="orch-pill ok"', clean)
        self.assertIn(">clean<", clean)
        self.assertIn('class="orch-pill bad"', failing)
        self.assertIn(f">{_FAILED_RUNS} fail<", failing)

    def test_a_round_is_toned_from_the_third_pass_on(self) -> None:
        toned = issue_table.review_round_html(_WARN_ROUND)
        self.assertEqual(
            toned, f'<span class="orch-badge-warn">{_WARN_ROUND}</span>',
        )
        self.assertEqual(
            issue_table.review_round_html(_PLAIN_ROUND), str(_PLAIN_ROUND),
        )

    def test_a_row_reduces_to_what_its_cells_read(self) -> None:
        # A read answers an issue that never reached review or a retry with a
        # null, and both columns are right-aligned numerals.
        view = issue_table.issue_row_view(
            _row(_IssueCase(costs=(_reported(_HALF_COST),))), _TOP_COST,
        )
        self.assertEqual(view.short_repo, "orchestrator")
        self.assertEqual(view.cost_figure, _HALF_COST_TEXT)
        self.assertEqual(view.bar_pct, _HALF_PCT)
        self.assertEqual(view.review_rounds, 0)
        self.assertEqual(view.retries, 0)

    def test_each_issue_cost_says_what_it_is(self) -> None:
        for name, costs, worded in _WORDED_ISSUES:
            with self.subTest(issue=name):
                view = issue_table.issue_row_view(_row(_IssueCase(costs=costs)), _TOP_COST)
                self.assertEqual((view.cost_figure, view.cost_note, view.partial), worded)


if __name__ == "__main__":
    unittest.main()
