# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one group of a spend breakdown reads as on its bar, and what a panel of them notes beneath it.

A group's spend is a cohort, so the cases name the cohorts a bar has to keep
apart -- reported-only, AGY-only, mixed-provider, incomplete, missing-basis,
unpriced, no usage, and a group with no run at all -- and read back the figure
drawn past the bar, the basis and shortfall under its label, and the note a
panel of such bars closes on.
"""
from __future__ import annotations

import unittest

from orchestrator.observability.analytics.query import cost_cohorts
from orchestrator.observability.dashboard import breakdown_text, spend_text
from tests.observability.analytics import analytics_cohorts as cohort_cases, analytics_usage_cases as cases

_RUNS = "4 runs"

# Each named cohort's bar figure and the basis and shortfall its sub-line adds.
_GROUPS = (
    ("reported only", "$0.84", "CLI-reported"),
    ("agy only", "$0.32", "Gemini API token estimate"),
    ("mixed providers", "$0.69", "blended"),
    ("incomplete", "$0.50", "Anthropic API token estimate · subtotal"),
    ("missing basis", "$0.49", "blended · completeness unknown"),
)

# Groups stating no amount: the word drawn where a figure would be, and no
# basis to name.
_UNSTATED = (
    ("unpriced", cohort_cases.cohort(cases.UNPRICED), "unpriced"),
    ("no usage", cohort_cases.cohort(cases.NO_USAGE), "no usage"),
    ("no run", cost_cohorts.EMPTY_COST_COHORT, spend_text.NO_RUNS_FIGURE),
)


class GroupWordingTest(unittest.TestCase):
    """A bar's figure and the line under its label."""

    def test_each_cohort_is_figured_and_based(self) -> None:
        # An AGY-only group reads as a Gemini API token estimate, a mixed one
        # as blended, and a subtotal or an amount of unknown completeness says
        # so -- the parts of a blend are the hover's, with their amounts.
        for name, figure, worded in _GROUPS:
            cohort = cohort_cases.cohort(*cohort_cases.NAMED_COSTS[name])
            with self.subTest(cohort=name):
                self.assertEqual(breakdown_text.bar_figure(cohort), figure)
                self.assertEqual(breakdown_text.sub_line(_RUNS, cohort), f"{_RUNS} · {worded}")

    def test_no_stated_amount_is_never_a_zero(self) -> None:
        for name, cohort, figure in _UNSTATED:
            with self.subTest(group=name):
                self.assertEqual(breakdown_text.bar_figure(cohort), figure)
                self.assertEqual(breakdown_text.basis_label(cohort), "")
                self.assertEqual(breakdown_text.sub_line(_RUNS, cohort), _RUNS)

    def test_a_complete_zero_is_a_figure(self) -> None:
        zero = cohort_cases.cohort(cases.COMPLETE_ZERO)
        self.assertEqual(breakdown_text.bar_figure(zero), "$0.00")
        self.assertEqual(breakdown_text.basis_label(zero), "CLI-reported")


class BreakdownNoteTest(unittest.TestCase):
    """What a panel's bars add up to, worded beneath it."""

    def test_the_bars_fold_into_one_worded_total(self) -> None:
        # A panel blending bases lists each basis's own amount beside the
        # total, and the runs leaving it short of complete spend are counted.
        groups = (
            cohort_cases.cohort(cases.REPORTED),
            cohort_cases.cohort(cases.GEMINI_ESTIMATE, cases.UNPRICED),
        )
        self.assertEqual(
            breakdown_text.breakdown_note(groups),
            "Bars total $0.54 (blended: CLI-reported $0.42 + Gemini API token estimate $0.12"
            " · incomplete subtotal: 1 of 3 runs unpriced or partly priced)",
        )

    def test_a_panel_with_no_bar_notes_nothing(self) -> None:
        self.assertEqual(breakdown_text.breakdown_note(()), "")

    def test_the_split_note_names_an_allocation(self) -> None:
        self.assertIn("token share", breakdown_text.TOKEN_SHARE_NOTE)
        self.assertIn("not a measured cache charge", breakdown_text.TOKEN_SHARE_NOTE)


if __name__ == "__main__":
    unittest.main()
