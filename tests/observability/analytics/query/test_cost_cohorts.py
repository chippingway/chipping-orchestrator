# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a cohort of runs cost, read back off the cells a cohort fragment reduces them to.

A fragment sums each basis on its own, bounds each estimate's verification dates, and counts the runs by the
completeness each states; `cost_cohort` turns those cells back into evidence. The cohort read off a cohort's cells is
held to what `usage.cost_evidence.reduce_costs` folds the same runs' costs to, so a display reading a cohort words it
the way it words one run -- and the four answers a single summed amount would merge stay apart.
"""
from __future__ import annotations

import re
import unittest

from orchestrator.observability.analytics.query import cost_cohorts, token_totals
from orchestrator.observability.usage import cost_evidence as usage_cost
from tests.observability.analytics import analytics_cohorts as cohort_cases, analytics_usage_cases as cases

_EMPTY_CELLS = (None,) * cost_cohorts.COST_COHORT_WIDTH

_COHORTS = (
    ("reported", (cases.REPORTED, cases.COMPLETE_ZERO)),
    ("anthropic estimates", (cases.ANTHROPIC_ESTIMATE, cases.ANTHROPIC_ESTIMATE)),
    ("antigravity only", (cases.GEMINI_ESTIMATE, cases.LATER_GEMINI_ESTIMATE)),
    ("mixed providers", (cases.REPORTED, cases.OPENAI_ESTIMATE, cases.BLENDED)),
    ("incomplete", (cases.ANTHROPIC_ESTIMATE, cases.INCOMPLETE_SUBTOTAL, cases.UNPRICED)),
    ("absent basis", (cases.REPORTED, cases.ABSENT_BASIS)),
    ("complete zero", (cases.COMPLETE_ZERO,)),
    ("no usage", (cases.NO_USAGE, cases.NO_USAGE)),
    ("three verification dates", cases.THREE_DATED_ESTIMATES),
)


def _top_level_cells(fragment: str) -> list[str]:
    """Split a select-list fragment at the commas no parenthesis encloses.

    A comma inside a call is followed by its closing parenthesis before any opening one, which is what the lookahead
    refuses; every cell a fragment selects opens with a call.
    """
    return [cell.strip() for cell in re.split(r",(?![^()]*\))", fragment)]


class CostCohortReadingTest(unittest.TestCase):
    """A cohort's cells read back as the evidence its runs' costs fold to."""

    def test_a_cohort_reads_as_its_runs_fold(self) -> None:
        for name, costs in _COHORTS:
            with self.subTest(cohort=name):
                cohort = cost_cohorts.cost_cohort(cohort_cases.cohort_cells(costs))
                folded = usage_cost.reduce_costs(costs)
                self.assertEqual(cohort.runs, len(costs))
                self.assertEqual(self._rounded(cohort.evidence), self._rounded(folded))

    def test_the_four_answers_stay_apart(self) -> None:
        # No run at all, a complete zero, an incomplete subtotal, and an amount
        # nothing states the basis of: one summed amount would read the first
        # two as $0 and the last two as spend, each as complete.
        empty = cost_cohorts.cost_cohort(_EMPTY_CELLS)
        zero = cost_cohorts.cost_cohort(cohort_cases.cohort_cells((cases.COMPLETE_ZERO,)))
        subtotal = cost_cohorts.cost_cohort(cohort_cases.cohort_cells((cases.INCOMPLETE_SUBTOTAL,)))
        unattributed = cost_cohorts.cost_cohort(cohort_cases.cohort_cells((cases.ABSENT_BASIS,)))
        answers = [
            (cohort.is_empty, cohort.evidence.completeness, cohort.evidence.total_usd, cohort.evidence.basis)
            for cohort in (empty, zero, subtotal, unattributed)
        ]
        self.assertEqual(
            answers,
            [
                (True, usage_cost.NO_USAGE, None, None),
                (False, usage_cost.COMPLETE, 0, usage_cost.CLI_REPORTED),
                (False, usage_cost.INCOMPLETE, cases.SUBTOTAL_USD, usage_cost.ANTHROPIC_API_ESTIMATE),
                (False, usage_cost.UNKNOWN, cases.LEGACY_USD, usage_cost.UNKNOWN_BASIS),
            ],
        )
        self.assertIsNone(subtotal.evidence.complete_usd)

    def test_a_run_alone_reads_as_its_own_cost(self) -> None:
        # A run's own cells are a cohort of that run, so a listing reads back
        # the evidence the sync filed -- a reported amount as the one its record
        # ranked first, an estimate with its rate dates -- rather than any
        # figure re-derived from the run's tokens.
        for spent in dict.fromkeys(cost for _name, costs in _COHORTS for cost in costs):
            with self.subTest(cost=spent):
                run = cost_cohorts.cost_cohort(cohort_cases.cohort_cells((spent,)))
                self.assertEqual((run.runs, run.evidence), (1, spent))

    def test_cells_read_from_offset_and_whole(self) -> None:
        cells = cohort_cases.cohort_cells((cases.REPORTED,))
        leading = ("day", "backend")
        self.assertEqual(
            cost_cohorts.cost_cohort((*leading, *cells), start=len(leading)),
            cost_cohorts.cost_cohort(cells),
        )
        # A row narrower than the fragment is a broken query, never a cohort
        # whose missing cells read as NULL.
        with self.assertRaises(ValueError):
            cost_cohorts.cost_cohort(cells[:-1])

    def test_cohorts_read_apart_fold_as_one(self) -> None:
        # A reader regrouping cells it read apart -- a window's days, or a day's
        # events -- answers what one cell over all their runs would, and the
        # fold of none is the empty cohort a window with no run reads as.
        for name, costs in _COHORTS:
            with self.subTest(cohort=name):
                apart = [cohort_cases.cohort(spent) for spent in costs]
                folded = cost_cohorts.fold_cohorts(apart)
                whole = cohort_cases.cohort(*costs)
                self.assertEqual(folded.runs, whole.runs)
                self.assertEqual(
                    (folded.complete_runs, folded.incomplete_runs, folded.no_usage_runs, folded.unknown_runs),
                    (whole.complete_runs, whole.incomplete_runs, whole.no_usage_runs, whole.unknown_runs),
                )
                self.assertEqual(self._rounded(folded.evidence), self._rounded(whole.evidence))
        self.assertEqual(cost_cohorts.EMPTY_COST_COHORT, cost_cohorts.cost_cohort(_EMPTY_CELLS))
        self.assertTrue(cost_cohorts.EMPTY_COST_COHORT.is_empty)

    def _rounded(self, evidence: usage_cost.CostEvidence) -> tuple:
        """The evidence with each amount rounded past the float noise a SQL sum and a Python sum differ by."""
        parts = tuple(
            (part.basis, round(part.amount_usd, 9), part.rates_verified_on) for part in evidence.contributions
        )
        return evidence.completeness, evidence.basis, parts


class CohortFragmentTest(unittest.TestCase):
    """Each scan target's fragment selects the same cells in the order the reader reads them."""

    def test_cost_fragments_select_the_width(self) -> None:
        for fragment in (
            cost_cohorts.RUN_COST_COHORT_SQL,
            cost_cohorts.EVENT_COST_COHORT_SQL,
            cost_cohorts.EVENT_RUN_COST_SQL,
            cost_cohorts.ROLLUP_COST_COHORT_SQL,
        ):
            with self.subTest(fragment=fragment):
                self.assertEqual(len(_top_level_cells(fragment)), cost_cohorts.COST_COHORT_WIDTH)

    def test_targets_read_underived_runs_unknown(self) -> None:
        # The view already folds a run with no derived evidence into `unknown`;
        # the events table has to spell that reading, and keep its counts to
        # the `agent_exit` rows; the rollup holds both pre-summed.
        run_cells = _top_level_cells(cost_cohorts.RUN_COST_COHORT_SQL)
        event_cells = _top_level_cells(cost_cohorts.EVENT_COST_COHORT_SQL)
        rollup_cells = _top_level_cells(cost_cohorts.ROLLUP_COST_COHORT_SQL)
        self.assertEqual(run_cells[3], "SUM(CASE WHEN cost_completeness = 'unknown' THEN 1 ELSE 0 END)")
        self.assertIn("WHEN event = 'agent_exit' THEN COALESCE(cost_completeness, 'unknown')", event_cells[3])
        self.assertEqual(rollup_cells[3], "SUM(cost_unknown_runs)")
        self.assertEqual(run_cells[8], "SUM(cost_unknown_basis_usd)")
        self.assertIn("WHEN cost_completeness IS NULL THEN cost_usd", event_cells[8])
        # Every target stores the dates as a sorted distinct array, so all three fold them alike, every date kept.
        dated = slice(-len(cohort_cases.DATED_BASES), None)
        self.assertEqual(run_cells[dated], rollup_cells[dated])
        self.assertEqual(event_cells[dated], rollup_cells[dated])
        self.assertEqual(rollup_cells[-1], "analytics_rate_dates(gemini_rates_verified_on)")

    def test_one_run_reads_its_own_cells(self) -> None:
        # A run's cells are the events-table cells left unsummed: counted only
        # as an `agent_exit`, an underived row's `cost_usd` under the `unknown`
        # basis, and its own sorted dates rather than a union over others.
        run_cells = _top_level_cells(cost_cohorts.EVENT_RUN_COST_SQL)
        event_cells = _top_level_cells(cost_cohorts.EVENT_COST_COHORT_SQL)
        summed = [f"SUM({cell})" for cell in run_cells[:9]]
        self.assertEqual(summed, event_cells[:9])
        self.assertEqual(
            run_cells[9:],
            ["anthropic_rates_verified_on", "openai_rates_verified_on", "gemini_rates_verified_on"],
        )

    def test_the_stated_amount_adds_every_basis(self) -> None:
        # The measure a ranking orders on adds the five amounts a run's cells
        # carry, NULL only where none of them is stated.
        amounts = _top_level_cells(cost_cohorts.EVENT_RUN_COST_SQL)[4:9]
        listed = ", ".join(amounts)
        terms = " + ".join(f"COALESCE({amount}, 0)" for amount in amounts)
        self.assertEqual(
            cost_cohorts.EVENT_STATED_USD_SQL,
            f"CASE WHEN num_nonnulls({listed}) > 0 THEN {terms} END",
        )

    def test_token_fragments_pair_known_unknown(self) -> None:
        for fragment, unknown in (
            (token_totals.RUN_TOKEN_TOTAL_SQL, "WHEN total_tokens IS NULL THEN 1"),
            (token_totals.EVENT_TOKEN_TOTAL_SQL, "WHEN event = 'agent_exit' AND total_tokens IS NULL THEN 1"),
            (token_totals.ROLLUP_TOKEN_TOTAL_SQL, "SUM(total_tokens_unknown_runs)"),
        ):
            with self.subTest(fragment=fragment):
                known_cell, unknown_cell = _top_level_cells(fragment)
                self.assertEqual(known_cell, "COALESCE(SUM(total_tokens), 0)")
                self.assertIn(unknown, unknown_cell)


if __name__ == "__main__":
    unittest.main()
