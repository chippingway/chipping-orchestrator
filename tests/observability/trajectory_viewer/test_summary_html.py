# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The banner and the five tiles a whole read is summarized in."""
from __future__ import annotations

import unittest

from orchestrator.observability.dashboard import cost_text
from orchestrator.observability.trajectory_viewer import (
    summaries,
    summary_html,
)
from orchestrator.observability.usage import cost_evidence as usage_cost
from tests.observability.trajectory_viewer.trajectory_viewer_test_support import (
    cost,
)

_TOTAL_RUNS = 10

_SHOWN_RUNS = 3

_TOOL_CALLS = 11

_TOTAL_COST = 12.5

_REPORTED_COST = 0.83

_ESTIMATED_COST = 0.4

_TOTAL_COST_LABEL = ">Total cost</span>"

_SUBTOTAL_LABEL = ">Cost subtotal</span>"

_UNKNOWN_BASIS_FOOT = (
    "blended: CLI-reported $0.83 + basis unknown $0.40 · "
    "2 runs without a cost basis"
)


class CardHeaderHtmlTest(unittest.TestCase):
    """A card's title line is caller text, so it is escaped."""

    def test_title_and_sub_escaped(self) -> None:
        rendered = summary_html.card_header_html("Title <b>", "Sub & more")
        self.assertIn("orch-card-title", rendered)
        self.assertIn("Title &lt;b&gt;", rendered)
        self.assertIn("Sub &amp; more", rendered)


class TopbarHtmlTest(unittest.TestCase):
    """The banner reports the whole file and the narrowing over it."""

    def test_carries_title_and_in_view_pill(self) -> None:
        rendered = summary_html.topbar_html(_TOTAL_RUNS, _SHOWN_RUNS)
        self.assertIn("orch-topbar", rendered)
        self.assertIn("Orchestrator Trajectories", rendered)
        self.assertIn("10 recorded", rendered)
        self.assertIn("3 / 10", rendered)


class KpiStripHtmlTest(unittest.TestCase):
    """The five tiles, their labels, and the two figures with a footnote."""

    def test_tiles_truncated_foot_and_cost(self) -> None:
        summary = summaries.TrajectorySummary(
            total_runs=5,
            distinct_issues=3,
            distinct_repos=2,
            total_tool_calls=_TOOL_CALLS,
            truncated_runs=1,
            total_cost=cost(
                usage_cost.COMPLETE, (usage_cost.CLI_REPORTED, _TOTAL_COST),
            ),
        )
        rendered = summary_html.kpi_strip_html(summary)
        self.assertIn("orch-kpis", rendered)
        for label in ("Runs", "Issues", "Repos", "Tool calls", "Total cost"):
            with self.subTest(label=label):
                self.assertIn(f">{label}</span>", rendered)
        self.assertIn("1 truncated", rendered)
        # Exact cents even above $10 -- the compact `fmt_money` would read
        # `$12`, dropping the recorded figure's cents -- on its named basis.
        self.assertIn(">$12.50</div>", rendered)
        self.assertIn("<span>CLI-reported</span>", rendered)

    def test_no_truncated_reads_none_and_no_usage(self) -> None:
        rendered = summary_html.kpi_strip_html(
            summaries.TrajectorySummary(total_runs=2),
        )
        self.assertIn("none truncated", rendered)
        # Nothing used reads as such, never as a priced zero.
        self.assertIn(">no usage</div>", rendered)
        self.assertIn(_TOTAL_COST_LABEL, rendered)


class CostKpiTest(unittest.TestCase):
    """The money tile names its basis and is a subtotal wherever it is short."""

    def test_a_covered_total_names_its_basis(self) -> None:
        for name, total, foot in (
            (
                "agy-only",
                cost(usage_cost.COMPLETE, (usage_cost.GEMINI_API_ESTIMATE, _ESTIMATED_COST)),
                "Gemini API token estimate",
            ),
            (
                "mixed",
                cost(
                    usage_cost.COMPLETE,
                    (usage_cost.ANTHROPIC_API_ESTIMATE, _ESTIMATED_COST),
                    (usage_cost.CLI_REPORTED, _REPORTED_COST),
                ),
                "blended: Anthropic API token estimate $0.40 + CLI-reported $0.83",
            ),
        ):
            with self.subTest(name):
                kpi = summary_html.cost_kpi(summaries.TrajectorySummary(total_cost=total))
                self.assertEqual(
                    (kpi.label, kpi.figure, kpi.foot),
                    ("Total cost", cost_text.cost_figure(total), foot),
                )

    def test_a_short_total_reads_as_a_subtotal(self) -> None:
        for name, summary, foot in (
            (
                "incomplete",
                summaries.TrajectorySummary(
                    total_cost=cost(
                        usage_cost.INCOMPLETE,
                        (usage_cost.CLI_REPORTED, _REPORTED_COST),
                    ),
                    incomplete_cost_runs=1,
                ),
                "CLI-reported · 1 run unpriced",
            ),
            (
                "absent basis",
                summaries.TrajectorySummary(
                    total_cost=cost(
                        usage_cost.UNKNOWN,
                        (usage_cost.CLI_REPORTED, _REPORTED_COST),
                        (usage_cost.UNKNOWN_BASIS, _ESTIMATED_COST),
                    ),
                    unknown_cost_runs=2,
                ),
                _UNKNOWN_BASIS_FOOT,
            ),
        ):
            with self.subTest(name):
                rendered = summary_html.kpi_strip_html(summary)
                self.assertIn(_SUBTOTAL_LABEL, rendered)
                self.assertNotIn(_TOTAL_COST_LABEL, rendered)
                self.assertEqual(summary_html.cost_kpi(summary).foot, foot)

    def test_a_total_with_no_amount_says_why(self) -> None:
        # Every run unpriced: there is no amount to mistake for spend, so the
        # tile reads as unpriced rather than as a subtotal of nothing.
        kpi = summary_html.cost_kpi(summaries.TrajectorySummary(
            total_cost=cost(usage_cost.INCOMPLETE),
            incomplete_cost_runs=3,
        ))
        self.assertEqual(
            (kpi.label, kpi.figure, kpi.foot),
            ("Total cost", "unpriced", "3 runs unpriced"),
        )


if __name__ == "__main__":
    unittest.main()
