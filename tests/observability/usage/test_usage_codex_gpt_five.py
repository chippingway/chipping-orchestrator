# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Focused provider usage parsing tests."""

import unittest

from orchestrator.observability.usage import metrics as _metrics
from tests.observability.usage import (
    usage_codex_events as _codex,
    usage_jsonl_helpers as _jsonl,
    usage_test_values as _usage_cases,
)


class CodexGptFiveFivePricingTest(unittest.TestCase):
    """Synthetic ``codex exec --json`` runs.

    Codex emits cumulative usage on each event; the parser takes the
    final non-zero record as the authoritative total rather than summing
    deltas.
    """

    def test_gpt_five_five_estimates_cost(self) -> None:
        # gpt-5.5 has an active catalogue row; usage that names it
        # explicitly must produce an `estimated` cost rather than
        # falling through to `unknown-price`. Pricing-coverage guard:
        # if the row gets accidentally dropped from `OPENAI_PRICES`
        # the test fails loudly and the dashboard's
        # `cost_source='unknown-price'` cohort gains a regression
        # before any operator notices.
        stdout = _jsonl.jsonl(
            _codex.turn_complete(
                model=_usage_cases.GPT_FIVE_FIVE,
                input=1000,
                cached=_usage_cases.TOKEN_COUNT_TWO_HUNDRED,
                output=_usage_cases.TOKEN_COUNT_FOUR_HUNDRED,
            ),
        )
        metrics = _metrics.parse_codex_usage(stdout)
        self.assertEqual(metrics.cost_source, _usage_cases.ESTIMATED_COST_SOURCE)
        self.assertEqual(metrics.models, (_usage_cases.GPT_FIVE_FIVE,))
        # gpt-5.5 rates: input=5, cached=0.50, output=30 (per 1M)
        uncached = 1000 - _usage_cases.TOKEN_COUNT_TWO_HUNDRED
        expected = (
            uncached * 5
            + _usage_cases.TOKEN_COUNT_TWO_HUNDRED * 0.5
            + _usage_cases.TOKEN_COUNT_FOUR_HUNDRED * _usage_cases.PRICE_RATE_THIRTY
        ) / _usage_cases.TOKENS_PER_MILLION
        assert metrics.cost_usd is not None
        self.assertAlmostEqual(metrics.cost_usd, expected, places=9)

    def test_gpt_five_five_prefers_reported_cost(self) -> None:
        # Even when usage matches the priced gpt-5.5 family, a CLI-
        # reported `total_cost_usd` on the terminal frame is the
        # authoritative figure (it already accounts for any pricing
        # nuance our table may have missed). Precedence guard so a
        # future change to the priced-model path does not start
        # overriding reported values.
        stdout = _jsonl.jsonl(
            _codex.turn_complete(
                model=_usage_cases.GPT_FIVE_FIVE, input=1000, cached=0, output=_usage_cases.TOKEN_COUNT_TWO_HUNDRED
            ),
            _codex.task_complete(total_cost_usd=_usage_cases.REPORTED_PRICING_COST_USD, num_turns=1),
        )
        metrics = _metrics.parse_codex_usage(stdout)
        self.assertEqual(metrics.cost_source, "reported")
        self.assertEqual(metrics.cost_usd, _usage_cases.REPORTED_PRICING_COST_USD)
