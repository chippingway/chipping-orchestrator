# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a filtered run set is totalled into for the page's KPI strip."""
from __future__ import annotations

import unittest

from orchestrator.observability.trajectory_viewer import models, summaries
from orchestrator.observability.usage import cost_evidence as usage_cost
from tests.observability.trajectory_viewer.trajectory_viewer_test_support import (
    TOOL_BASH,
    TOOL_CALL,
    TOOL_EDIT,
    TOOL_RESULT,
    cost,
    run,
    step,
)

_REPO_A = "a/a"

_REPO_B = "b/b"

_REPORTED_COST = 0.8

_ESTIMATED_COST = 0.2

_TURN_COST = 0.5

_REPORTED = cost(usage_cost.COMPLETE, (usage_cost.CLI_REPORTED, _REPORTED_COST))

_ANTHROPIC = cost(
    usage_cost.COMPLETE, (usage_cost.ANTHROPIC_API_ESTIMATE, _ESTIMATED_COST),
)

_GEMINI = cost(
    usage_cost.COMPLETE, (usage_cost.GEMINI_API_ESTIMATE, _ESTIMATED_COST),
)

# A record an earlier build wrote: its amount, on no basis it states.
_UNATTRIBUTED = cost(
    usage_cost.UNKNOWN, (usage_cost.UNKNOWN_BASIS, _REPORTED_COST),
)


def _costing(issue: int, stated: usage_cost.CostEvidence):
    """A run whose summary states `stated` as its own cost."""
    return run(issue=issue, run_usage=models.RunUsageView(cost_evidence=stated))


class HeadlineCountTest(unittest.TestCase):
    """Runs are summed, issues and repositories counted once each."""

    def test_counts_over_a_filtered_set(self) -> None:
        summary = summaries.summarize([
            run(
                issue=1,
                repo=_REPO_A,
                steps=(
                    step(TOOL_CALL, name=TOOL_BASH),
                    step(TOOL_RESULT, tool_id="t"),
                ),
                truncated=True,
            ),
            run(issue=1, repo=_REPO_A, steps=(step(TOOL_CALL, name=TOOL_EDIT),)),
            run(issue=2, repo=_REPO_B),
        ])
        self.assertEqual(summary.total_runs, 3)
        # Two runs share (a/a, 1); (b/b, 2) is the second distinct issue.
        self.assertEqual(summary.distinct_issues, 2)
        self.assertEqual(summary.distinct_repos, 2)
        # Only `tool_call` steps count; the result beside one does not.
        self.assertEqual(summary.total_tool_calls, 2)
        self.assertEqual(summary.truncated_runs, 1)

    def test_an_empty_set_totals_to_zero(self) -> None:
        summary = summaries.summarize([])
        self.assertEqual(
            (
                summary.total_runs,
                summary.distinct_issues,
                summary.distinct_repos,
                summary.total_tool_calls,
                summary.truncated_runs,
                summary.incomplete_cost_runs,
                summary.unknown_cost_runs,
            ),
            (0, 0, 0, 0, 0, 0, 0),
        )
        # Nothing ran, so nothing was used -- never a priced zero.
        self.assertEqual(summary.total_cost, cost(usage_cost.NO_USAGE))


class TotalCostTest(unittest.TestCase):
    """Each basis is totalled on its own, and a gap leaves a subtotal."""

    def test_agy_only_runs_stay_gemini_estimates(self) -> None:
        summary = summaries.summarize([_costing(1, _GEMINI), _costing(2, _GEMINI)])
        self.assertEqual(summary.total_cost.basis, usage_cost.GEMINI_API_ESTIMATE)
        self.assertEqual(summary.total_cost.completeness, usage_cost.COMPLETE)
        self.assertAlmostEqual(summary.total_cost.complete_usd, 2 * _ESTIMATED_COST)

    def test_mixed_runs_keep_each_basis_apart(self) -> None:
        summary = summaries.summarize([_costing(1, _REPORTED), _costing(2, _ANTHROPIC)])
        self.assertEqual(summary.total_cost.basis, usage_cost.BLENDED)
        self.assertEqual(
            {part.basis: part.amount_usd for part in summary.total_cost.contributions},
            {
                usage_cost.ANTHROPIC_API_ESTIMATE: _ESTIMATED_COST,
                usage_cost.CLI_REPORTED: _REPORTED_COST,
            },
        )
        self.assertEqual(summary.total_cost.completeness, usage_cost.COMPLETE)

    def test_a_gap_in_the_runs_leaves_a_subtotal(self) -> None:
        # An unpriced run is a known gap, which outranks a run stating no
        # evidence -- a damaged line with no summary included -- and each is
        # counted, so the tile can say what the subtotal is missing.
        for name, gaps, completeness, counts in (
            ("unpriced", (cost(usage_cost.INCOMPLETE),), usage_cost.INCOMPLETE, (1, 0)),
            ("absent basis", (_UNATTRIBUTED,), usage_cost.UNKNOWN, (0, 1)),
            (
                "both",
                (cost(usage_cost.INCOMPLETE), _UNATTRIBUTED),
                usage_cost.INCOMPLETE,
                (1, 1),
            ),
        ):
            with self.subTest(name):
                summary = summaries.summarize([
                    _costing(1, _REPORTED),
                    *(_costing(2, gap) for gap in gaps),
                    run(issue=3),
                ])
                self.assertEqual(summary.total_cost.completeness, completeness)
                self.assertIsNone(summary.total_cost.complete_usd)
                self.assertEqual(
                    (summary.incomplete_cost_runs, summary.unknown_cost_runs),
                    (counts[0], counts[1] + 1),
                )

    def test_a_reported_run_outranks_its_turns(self) -> None:
        # The turns' estimates are a detail of the run; the total is the
        # run's own CLI-reported amount, not their sum.
        summary = summaries.summarize([run(
            run_usage=models.RunUsageView(cost_evidence=_REPORTED),
            turns=(
                models.TurnUsageView(turn=0, cost_evidence=cost(
                    usage_cost.COMPLETE,
                    (usage_cost.ANTHROPIC_API_ESTIMATE, _TURN_COST),
                )),
            ),
        )])
        self.assertEqual(summary.total_cost, _REPORTED)


if __name__ == "__main__":
    unittest.main()
