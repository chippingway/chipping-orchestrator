# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a cohort of runs cost, read back off the cells a cohort fragment reduces them to.

A fragment sums each basis on its own, bounds each estimate's verification dates, and counts the runs by the
completeness each states; `cost_cohort` turns those cells back into evidence. The cohort read off a cohort's cells is
held to what `usage.cost_evidence.reduce_costs` folds the same runs' costs to, so a display reading a cohort words it
the way it words one run -- and the four answers a single summed amount would merge stay apart.
"""
from __future__ import annotations

import math
import re
import unittest
from collections.abc import Sequence
from decimal import Decimal

from orchestrator.observability.analytics.query import cost_cohorts, token_totals
from orchestrator.observability.usage import cost_evidence as usage_cost
from tests.observability.analytics import analytics_usage_cases as cases

_COMPLETENESS_ORDER = (usage_cost.COMPLETE, usage_cost.INCOMPLETE, usage_cost.NO_USAGE, usage_cost.UNKNOWN)

_DATED_BASES = (
    usage_cost.ANTHROPIC_API_ESTIMATE,
    usage_cost.OPENAI_API_ESTIMATE,
    usage_cost.GEMINI_API_ESTIMATE,
)

_EMPTY_CELLS = (None,) * cost_cohorts.COST_COHORT_WIDTH

_LEGACY_COST = 0.07

# A record an earlier build wrote, read the way every surface reads one: `unknown`, its amount under that basis.
_ABSENT_BASIS = usage_cost.recorded_cost(cases.unevidenced_record(1, cost_usd=_LEGACY_COST))

_COHORTS = (
    ("reported", (cases.REPORTED, cases.COMPLETE_ZERO)),
    ("anthropic estimates", (cases.ANTHROPIC_ESTIMATE, cases.ANTHROPIC_ESTIMATE)),
    ("antigravity only", (cases.GEMINI_ESTIMATE, cases.LATER_GEMINI_ESTIMATE)),
    ("mixed providers", (cases.REPORTED, cases.OPENAI_ESTIMATE, cases.BLENDED)),
    ("incomplete", (cases.ANTHROPIC_ESTIMATE, cases.INCOMPLETE_SUBTOTAL, cases.UNPRICED)),
    ("absent basis", (cases.REPORTED, _ABSENT_BASIS)),
    ("complete zero", (cases.COMPLETE_ZERO,)),
    ("no usage", (cases.NO_USAGE, cases.NO_USAGE)),
    ("three verification dates", cases.THREE_DATED_ESTIMATES),
)


def _parts(costs: Sequence[usage_cost.CostEvidence], basis: str) -> list[usage_cost.CostContribution]:
    return [part for spent in costs for part in spent.contributions if part.basis == basis]


def _basis_amount(costs: Sequence[usage_cost.CostEvidence], basis: str) -> Decimal | None:
    """One basis's SQL sum: NULL where no run states an amount on it, a zero included."""
    amounts = [part.amount_usd for part in _parts(costs, basis)]
    return Decimal(str(math.fsum(amounts))) if amounts else None


def _basis_dates(costs: Sequence[usage_cost.CostEvidence], basis: str) -> list | None:
    """One estimate basis's distinct verification dates, sorted, as the date-union aggregate returns them: NULL where
    no run was priced at a dated row."""
    days = {day for part in _parts(costs, basis) for day in part.rates_verified_on}
    return sorted(days) or None


def _cohort_cells(costs: Sequence[usage_cost.CostEvidence]) -> tuple:
    """The cells a cohort fragment selects over runs stating `costs`, in the order it selects them."""
    counts = [sum(spent.completeness == state for spent in costs) for state in _COMPLETENESS_ORDER]
    amounts = [_basis_amount(costs, basis) for basis in usage_cost.BASES]
    dates = [_basis_dates(costs, basis) for basis in _DATED_BASES]
    return (*counts, *amounts, *dates)


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
                cohort = cost_cohorts.cost_cohort(_cohort_cells(costs))
                folded = usage_cost.reduce_costs(costs)
                self.assertEqual(cohort.runs, len(costs))
                self.assertEqual(self._rounded(cohort.evidence), self._rounded(folded))

    def test_the_four_answers_stay_apart(self) -> None:
        # No run at all, a complete zero, an incomplete subtotal, and an amount
        # nothing states the basis of: one summed amount would read the first
        # two as $0 and the last two as spend, each as complete.
        empty = cost_cohorts.cost_cohort(_EMPTY_CELLS)
        zero = cost_cohorts.cost_cohort(_cohort_cells((cases.COMPLETE_ZERO,)))
        subtotal = cost_cohorts.cost_cohort(_cohort_cells((cases.INCOMPLETE_SUBTOTAL,)))
        unattributed = cost_cohorts.cost_cohort(_cohort_cells((_ABSENT_BASIS,)))
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
                (False, usage_cost.UNKNOWN, _LEGACY_COST, usage_cost.UNKNOWN_BASIS),
            ],
        )
        self.assertIsNone(subtotal.evidence.complete_usd)

    def test_cells_read_from_offset_and_whole(self) -> None:
        cells = _cohort_cells((cases.REPORTED,))
        leading = ("day", "backend")
        self.assertEqual(
            cost_cohorts.cost_cohort((*leading, *cells), start=len(leading)),
            cost_cohorts.cost_cohort(cells),
        )
        # A row narrower than the fragment is a broken query, never a cohort
        # whose missing cells read as NULL.
        with self.assertRaises(ValueError):
            cost_cohorts.cost_cohort(cells[:-1])

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
        dated = slice(-len(_DATED_BASES), None)
        self.assertEqual(run_cells[dated], rollup_cells[dated])
        self.assertEqual(event_cells[dated], rollup_cells[dated])
        self.assertEqual(rollup_cells[-1], "analytics_rate_dates(gemini_rates_verified_on)")

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
