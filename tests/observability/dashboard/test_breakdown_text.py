# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one group of a spend breakdown reads as on its bar, and what a panel of them notes beneath it.

A group's spend is a cohort, so the cases name the cohorts a bar has to keep
apart -- reported-only, AGY-only, mixed-provider, incomplete, missing-basis,
unpriced, no usage, and a group with no run at all -- and read back the figure
drawn past the bar, the status under its label, and the note a panel of such
bars closes on.
"""
from __future__ import annotations

import unittest

from orchestrator.observability.analytics.query import cost_cohorts
from orchestrator.observability.dashboard import breakdown_text, spend_text
from tests.observability.analytics import analytics_cohorts as cohort_cases, analytics_usage_cases as cases

_RUNS = "4 runs"

# Each named cohort's bar figure and the status its own runs earn on the sub-line; no source is named there.
_GROUPS = (
    ("reported only", "$0.84", _RUNS),
    ("agy only", "$0.32", _RUNS),
    ("mixed providers", "$0.69", _RUNS),
    ("incomplete", "$0.50", f"{_RUNS} · {spend_text.SUBTOTAL}"),
    ("missing basis", "$0.49", f"{_RUNS} · {spend_text.COMPLETENESS_UNKNOWN}"),
)

# Groups stating no amount, a complete zero beside them: the word or figure drawn past the bar.
_UNSTATED = (
    ("unpriced", cohort_cases.cohort(cases.UNPRICED), spend_text.UNPRICED),
    ("no usage", cohort_cases.cohort(cases.NO_USAGE), spend_text.NO_USAGE),
    ("no run", cost_cohorts.EMPTY_COST_COHORT, spend_text.NO_RUNS),
    ("complete zero", cohort_cases.cohort(cases.COMPLETE_ZERO), "$0.00"),
)


class GroupWordingTest(unittest.TestCase):
    """A bar's figure and the line under its label."""

    def test_each_cohort_is_figured_by_its_own_runs(self) -> None:
        for name, figure, worded in _GROUPS:
            cohort = cohort_cases.cohort(*cohort_cases.NAMED_COSTS[name])
            with self.subTest(cohort=name):
                self.assertEqual(breakdown_text.bar_figure(cohort), figure)
                self.assertEqual(breakdown_text.sub_line(_RUNS, cohort), worded)

    def test_a_role_line_marks_its_own_runs(self) -> None:
        # A label heading several bars gives each role a line, its noun agreeing
        # with the count and its status the role's own.
        short = cohort_cases.cohort(*cohort_cases.NAMED_COSTS["incomplete"])
        complete = cohort_cases.cohort(cases.REPORTED)
        self.assertEqual(breakdown_text.role_line(1, "dev", complete), "1 dev run")
        self.assertEqual(breakdown_text.role_line(3, "review", short), f"3 review runs · {spend_text.SUBTOTAL}")
        self.assertEqual(breakdown_text.role_line(0, "review", cost_cohorts.EMPTY_COST_COHORT), "0 review runs")

    def test_no_stated_amount_is_never_a_zero(self) -> None:
        for name, cohort, figure in _UNSTATED:
            with self.subTest(group=name):
                self.assertEqual(breakdown_text.bar_figure(cohort), figure)
                self.assertEqual(breakdown_text.sub_line(_RUNS, cohort), _RUNS)


class BreakdownNoteTest(unittest.TestCase):
    """What a panel's bars add up to, worded beneath it."""

    def test_the_bars_fold_into_one_compact_total(self) -> None:
        # A panel mixing sources and holding an unpriced run reads as the
        # subtotal it is, its sources left to the Cost details section.
        groups = (
            cohort_cases.cohort(cases.REPORTED),
            cohort_cases.cohort(cases.GEMINI_ESTIMATE, cases.UNPRICED),
        )
        self.assertEqual(breakdown_text.breakdown_note(groups), "Bars total $0.54 · Subtotal")

    def test_a_panel_with_no_bar_notes_nothing(self) -> None:
        self.assertEqual(breakdown_text.breakdown_note(()), "")


if __name__ == "__main__":
    unittest.main()
