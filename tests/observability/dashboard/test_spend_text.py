# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an amount reads as on the analytics page, and what a move between two windows keeps.

Every cohort is the one the cohort reader hands back for runs stating the shared usage cases, so the wording read here
is the wording a real window gets: a figure and the short status its own runs earn, never the sources behind it, and a
subtotal, an unknown completeness, an unpriced cost, no usage, or a window with no run never as complete spend or as a
zero. A run's own evidence is worded the same way.
"""
from __future__ import annotations

import unittest

from orchestrator.observability.dashboard import spend_text
from orchestrator.observability.usage import cost_evidence as usage_cost
from tests.observability.analytics import analytics_cohorts as cohort_cases, analytics_usage_cases as cases

_MIXED = cohort_cases.cohort(*cohort_cases.NAMED_COSTS["mixed providers"])

_REPORTED = cohort_cases.cohort(*cohort_cases.NAMED_COSTS["reported only"])

_AGY = cohort_cases.cohort(*cohort_cases.NAMED_COSTS["agy only"])

_INCOMPLETE = cohort_cases.cohort(*cohort_cases.NAMED_COSTS["incomplete"])

_ANTHROPIC = cohort_cases.cohort(cases.ANTHROPIC_ESTIMATE)

_MISSING_BASIS = cohort_cases.cohort(*cohort_cases.NAMED_COSTS["missing basis"])

# A record an earlier build wrote with no cost evidence and no amount at all.
_NO_EVIDENCE = usage_cost.recorded_cost(cases.unevidenced_record(1, cost_usd=None))

_MANY_RUNS = 1_200

# Each cohort a window can hold: the figure it reads as, and the status its own runs earn. No source is named on any
# of them, a mix of CLI-reported amounts and estimates included.
_READINGS = (
    ("reported only", _REPORTED, "$0.84", ""),
    ("agy only", _AGY, "$0.32", ""),
    ("mixed providers", _MIXED, "$0.69", ""),
    ("incomplete", _INCOMPLETE, "$0.50", spend_text.SUBTOTAL),
    ("missing basis", _MISSING_BASIS, "$0.49", spend_text.COMPLETENESS_UNKNOWN),
    ("basis absent alone", cohort_cases.cohort(cases.ABSENT_BASIS), "$0.07", spend_text.COMPLETENESS_UNKNOWN),
    ("unpriced only", cohort_cases.cohort(cases.UNPRICED), spend_text.UNPRICED, ""),
    ("no evidence and no amount", cohort_cases.cohort(_NO_EVIDENCE), spend_text.COST_UNKNOWN, ""),
    ("complete zero", cohort_cases.cohort(cases.COMPLETE_ZERO), "$0.00", ""),
    ("no usage", cohort_cases.cohort(cases.NO_USAGE), spend_text.NO_USAGE, ""),
    ("empty", cohort_cases.cohort(), spend_text.NO_RUNS, ""),
)

# One run's own evidence, as a listed or traced run reads it.
_RUN_LINES = (
    ("reported", cases.REPORTED, "$0.42"),
    ("blended", cases.BLENDED, "$0.15"),
    ("incomplete subtotal", cases.INCOMPLETE_SUBTOTAL, "$0.20 · Subtotal"),
    ("unpriced", cases.UNPRICED, "Unpriced"),
    ("complete zero", cases.COMPLETE_ZERO, "$0.00"),
    ("no usage", cases.NO_USAGE, "No usage"),
    ("absent basis", cases.ABSENT_BASIS, "$0.07 · Completeness unknown"),
    ("no evidence and no amount", _NO_EVIDENCE, "Cost unknown"),
)

# Pairs of windows and what a move between them is read with.
_COMPARISONS = (
    ("one basis, both complete", _REPORTED, _REPORTED, ""),
    ("agy against agy", _AGY, _AGY, ""),
    ("mixed on the same sources", _MIXED, _MIXED, ""),
    ("agy against reported", _AGY, _REPORTED, spend_text.SOURCES_DIFFER),
    ("a subtotal on one side", _INCOMPLETE, _ANTHROPIC, spend_text.SUBTOTAL),
    ("a subtotal on the other", _ANTHROPIC, _INCOMPLETE, spend_text.SUBTOTAL),
    (
        "a missing basis",
        _MISSING_BASIS,
        _REPORTED,
        f"{spend_text.COMPLETENESS_UNKNOWN}, {spend_text.SOURCES_DIFFER}",
    ),
)

# Words that belong to the Cost details section alone.
_SOURCE_WORDS = ("CLI-reported", "estimate", "blended", "basis", "runs unpriced")


class SpendWordingTest(unittest.TestCase):
    """The figure and status each cohort and each run reads as."""

    def test_each_cohort_reads_as_figure_and_status(self) -> None:
        for name, cohort, figure, status in _READINGS:
            with self.subTest(cohort=name):
                self.assertEqual(spend_text.spend_figure(cohort), figure)
                self.assertEqual(spend_text.spend_status(cohort), status)
                self.assertEqual(spend_text.spend_line(cohort), f"{figure} · {status}" if status else figure)
                self.assertFalse([word for word in _SOURCE_WORDS if word in spend_text.spend_line(cohort)])

    def test_a_run_reads_as_its_own_evidence(self) -> None:
        for name, evidence, line in _RUN_LINES:
            with self.subTest(run=name):
                self.assertEqual(spend_text.spend_line(evidence), line)


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
