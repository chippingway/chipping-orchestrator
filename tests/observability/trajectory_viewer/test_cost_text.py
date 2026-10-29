# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How a cost's amount, basis, and completeness read on every surface."""
from __future__ import annotations

import unittest

from orchestrator.observability.trajectory_viewer import cost_text
from orchestrator.observability.usage import cost_evidence as usage_cost
from tests.observability.trajectory_viewer.trajectory_viewer_test_support import (
    cost,
)

_REPORTED_AMOUNT = 0.83

_ESTIMATED_AMOUNT = 0.4

_TURN_AMOUNT = 0.0123

_GEMINI = "Gemini API token estimate"

_RATES = "rates verified 2026-10-29"

_THOUSANDS = 12345.5

_MIXED_UNKNOWN_LINE = (
    "$1.23 (blended: Anthropic API token estimate $0.40 + basis unknown "
    "$0.83, completeness unknown)"
)

# Each cost a producer or a reduction can state, and the one line it reads as.
_COST_LINES = (
    (
        "cli-reported",
        cost(usage_cost.COMPLETE, (usage_cost.CLI_REPORTED, _REPORTED_AMOUNT)),
        "$0.83 (CLI-reported)",
    ),
    (
        "cli-reported zero",
        cost(usage_cost.COMPLETE, (usage_cost.CLI_REPORTED, 0)),
        "$0.00 (CLI-reported)",
    ),
    (
        "anthropic estimate",
        cost(usage_cost.COMPLETE, (usage_cost.ANTHROPIC_API_ESTIMATE, _ESTIMATED_AMOUNT)),
        "$0.40 (Anthropic API token estimate)",
    ),
    (
        "openai estimate",
        cost(usage_cost.COMPLETE, (usage_cost.OPENAI_API_ESTIMATE, _ESTIMATED_AMOUNT)),
        "$0.40 (OpenAI API token estimate)",
    ),
    (
        "agy-only",
        cost(usage_cost.COMPLETE, (usage_cost.GEMINI_API_ESTIMATE, _ESTIMATED_AMOUNT)),
        f"$0.40 ({_GEMINI})",
    ),
    (
        "mixed",
        cost(
            usage_cost.COMPLETE,
            (usage_cost.CLI_REPORTED, _REPORTED_AMOUNT),
            (usage_cost.GEMINI_API_ESTIMATE, _ESTIMATED_AMOUNT),
        ),
        f"$1.23 (blended: CLI-reported $0.83 + {_GEMINI} $0.40)",
    ),
    (
        "incomplete subtotal",
        cost(usage_cost.INCOMPLETE, (usage_cost.ANTHROPIC_API_ESTIMATE, _ESTIMATED_AMOUNT)),
        "$0.40 (Anthropic API token estimate, incomplete subtotal)",
    ),
    (
        "absent basis",
        cost(usage_cost.UNKNOWN, (usage_cost.UNKNOWN_BASIS, _REPORTED_AMOUNT)),
        "$0.83 (basis unknown, completeness unknown)",
    ),
    (
        "mixed with absent basis",
        cost(
            usage_cost.UNKNOWN,
            (usage_cost.ANTHROPIC_API_ESTIMATE, _ESTIMATED_AMOUNT),
            (usage_cost.UNKNOWN_BASIS, _REPORTED_AMOUNT),
        ),
        _MIXED_UNKNOWN_LINE,
    ),
    ("unpriced", cost(usage_cost.INCOMPLETE), "unpriced"),
    ("absent basis and amount", cost(usage_cost.UNKNOWN), "cost unknown"),
    ("no usage", cost(usage_cost.NO_USAGE), "no usage"),
)


class CostTextTest(unittest.TestCase):
    """An amount never reads without its basis, nor as complete when short."""

    def test_each_cost_reads_as_one_line(self) -> None:
        for name, stated, expected in _COST_LINES:
            with self.subTest(name):
                self.assertEqual(cost_text.cost_text(stated), expected)

    def test_a_short_amount_is_qualified(self) -> None:
        # Only a cost stating an amount has a figure to qualify; one stating
        # none already reads as unpriced or unknown rather than as a zero.
        for name, stated, _line in _COST_LINES:
            with self.subTest(name):
                qualifier = cost_text.completeness_text(stated)
                covered = stated.completeness in {
                    usage_cost.COMPLETE, usage_cost.NO_USAGE,
                }
                self.assertEqual(
                    bool(qualifier), stated.total_usd is not None and not covered,
                )

    def test_a_turn_figure_keeps_its_sub_cent_digits(self) -> None:
        turn = cost(usage_cost.COMPLETE, (usage_cost.ANTHROPIC_API_ESTIMATE, _TURN_AMOUNT))
        self.assertEqual(cost_text.cost_figure(turn, decimals=4), "$0.0123")
        # Two decimals would floor a real sub-cent charge to nothing.
        self.assertEqual(cost_text.cost_figure(turn), "$0.01")
        # Thousands are separated and cents kept, where a compact formatter
        # would read `$12K`.
        self.assertEqual(cost_text.fmt_cost_usd(_THOUSANDS), "$12,345.50")


class RatesTextTest(unittest.TestCase):
    """An estimate names the date of the rates it was priced at."""

    def test_only_estimates_carry_rates(self) -> None:
        for name, stated, expected in (
            ("estimate", _COST_LINES[2][1], _RATES),
            ("blended", _COST_LINES[5][1], _RATES),
            ("cli-reported", _COST_LINES[0][1], ""),
            ("absent basis", _COST_LINES[7][1], ""),
            ("unpriced", cost(usage_cost.INCOMPLETE), ""),
        ):
            with self.subTest(name):
                self.assertEqual(cost_text.rates_text(stated), expected)


if __name__ == "__main__":
    unittest.main()
