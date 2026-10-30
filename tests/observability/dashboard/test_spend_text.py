# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a window's spend reads as on the overview, and what a move between two windows keeps.

Every cohort is the one the cohort reader hands back for runs stating the shared usage cases, so the wording read here
is the wording a real window gets: an amount never without its basis, a Gemini estimate never as an Antigravity
charge, a blended total with each part beside it, and a subtotal, an unknown completeness, or a window with no run
never as complete spend.
"""
from __future__ import annotations

import unittest

from orchestrator.observability.dashboard import spend_text
from tests.observability.analytics import analytics_cohorts as cohort_cases, analytics_usage_cases as cases

_MIXED = cohort_cases.cohort(cases.REPORTED, cases.GEMINI_ESTIMATE, cases.BLENDED)

_REPORTED = cohort_cases.cohort(cases.REPORTED, cases.REPORTED)

_AGY = cohort_cases.cohort(cases.GEMINI_ESTIMATE, cases.LATER_GEMINI_ESTIMATE)

_INCOMPLETE = cohort_cases.cohort(cases.ANTHROPIC_ESTIMATE, cases.INCOMPLETE_SUBTOTAL, cases.UNPRICED)

_ANTHROPIC = cohort_cases.cohort(cases.ANTHROPIC_ESTIMATE)

_MISSING_BASIS = cohort_cases.cohort(cases.REPORTED, cases.ABSENT_BASIS)

_EMPTY = cohort_cases.cohort()

_SUBTOTAL = "subtotal"

_MANY_RUNS = 1_200

_BASES_DIFFER = "bases differ"

# Each cohort a window can hold: the figure it reads as, and the note set beside it.
_READINGS = (
    ("reported only", _REPORTED, "$0.84", "CLI-reported"),
    ("agy only", _AGY, "$0.32", "Gemini API token estimate"),
    (
        "mixed providers",
        _MIXED,
        "$0.69",
        "blended: CLI-reported $0.52 + Gemini API token estimate $0.12 + OpenAI API token estimate $0.05",
    ),
    (
        "incomplete",
        _INCOMPLETE,
        "$0.50",
        "Anthropic API token estimate · incomplete subtotal: 2 of 3 runs unpriced or partly priced",
    ),
    (
        "missing basis",
        _MISSING_BASIS,
        "$0.49",
        "blended: CLI-reported $0.42 + basis unknown $0.07 · completeness unknown: 1 of 2 runs state no cost evidence",
    ),
    (
        "basis absent alone",
        cohort_cases.cohort(cases.ABSENT_BASIS),
        "$0.07",
        "basis unknown · completeness unknown: 1 of 1 runs state no cost evidence",
    ),
    ("unpriced only", cohort_cases.cohort(cases.UNPRICED), "unpriced", "1 of 1 runs unpriced or partly priced"),
    ("complete zero", cohort_cases.cohort(cases.COMPLETE_ZERO), "$0.00", "CLI-reported"),
    ("no usage", cohort_cases.cohort(cases.NO_USAGE), "no usage", ""),
    ("empty", _EMPTY, spend_text.NO_RUNS_FIGURE, spend_text.NO_RUNS_NOTE),
)

# Pairs of windows and what a move between them is read with.
_COMPARISONS = (
    ("one basis, both complete", _REPORTED, _REPORTED, ""),
    ("agy against agy", _AGY, _AGY, ""),
    ("blended on the same bases", _MIXED, _MIXED, "blended"),
    ("agy against reported", _AGY, _REPORTED, _BASES_DIFFER),
    ("a subtotal on one side", _INCOMPLETE, _ANTHROPIC, _SUBTOTAL),
    ("a subtotal on the other", _ANTHROPIC, _INCOMPLETE, _SUBTOTAL),
    ("a missing basis", _MISSING_BASIS, _REPORTED, f"completeness unknown, {_BASES_DIFFER}"),
)


class SpendWordingTest(unittest.TestCase):
    """The figure and note each cohort reads as."""

    def test_each_cohort_names_basis_and_shortfall(self) -> None:
        for name, cohort, figure, note in _READINGS:
            with self.subTest(cohort=name):
                self.assertEqual(spend_text.spend_figure(cohort), figure)
                self.assertEqual(spend_text.spend_note(cohort), note)
                line = spend_text.spend_line(cohort)
                self.assertEqual(line, f"{figure} ({note})" if note else figure)

    def test_a_ratio_names_bases_without_amounts(self) -> None:
        # A component amount beside a per-issue figure would read as that
        # issue's share, so a figure divided from the total names bases alone.
        self.assertEqual(
            spend_text.spend_note(_MIXED, amounts=False),
            "blended: CLI-reported + Gemini API token estimate + OpenAI API token estimate",
        )
        self.assertEqual(spend_text.spend_note(_AGY, amounts=False), "Gemini API token estimate")
        self.assertEqual(
            spend_text.spend_note(_INCOMPLETE, amounts=False),
            "Anthropic API token estimate · incomplete subtotal: 2 of 3 runs unpriced or partly priced",
        )


class ComparisonNoteTest(unittest.TestCase):
    """A move between two windows keeps what either side is qualified by."""

    def test_each_pair_names_its_qualifier(self) -> None:
        for name, current, previous, note in _COMPARISONS:
            with self.subTest(pair=name):
                self.assertEqual(spend_text.spend_comparison_note(current, previous), note)


class TokenNoteTest(unittest.TestCase):
    """A known token count says it is a subtotal wherever a run's total is unknown."""

    def test_unknown_runs_are_counted(self) -> None:
        self.assertEqual(spend_text.token_note(0), "")
        self.assertEqual(spend_text.token_note(1), "subtotal: token total unknown for 1 run")
        self.assertEqual(spend_text.token_note(_MANY_RUNS), "subtotal: token total unknown for 1,200 runs")


if __name__ == "__main__":
    unittest.main()
