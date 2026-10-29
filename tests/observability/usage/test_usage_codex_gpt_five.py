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

    def test_gpt_five_five_tiers_long_context(self) -> None:
        # GPT-5.5 prompts whose total input token count exceeds 272K
        # are billed across the whole session at 2x the input rate
        # and 1.5x the output rate (per OpenAI's published long-
        # context pricing). A no-reported-cost Codex run at 300K
        # input must record the elevated estimate, not the flat-rate
        # one. Pinning the threshold here means a future table edit
        # that drops the tier silently regresses the dashboard cost
        # column for long-context sessions before any operator
        # notices the under-reporting.
        stdout = _jsonl.jsonl(
            _codex.turn_complete(
                model=_usage_cases.GPT_FIVE_FIVE,
                input=_usage_cases.LONG_CONTEXT_INPUT_TOKENS,
                cached=0,
                output=_usage_cases.CODEX_PRICING_OUTPUT_TOKENS,
            ),
        )
        metrics = _metrics.parse_codex_usage(stdout)
        self.assertEqual(metrics.cost_source, _usage_cases.ESTIMATED_COST_SOURCE)
        # Long-context tier: input * 5 * 2 + output * 30 * 1.5, /1M.
        expected = (
            _usage_cases.LONG_CONTEXT_INPUT_TOKENS * 5 * _usage_cases.LONG_CONTEXT_INPUT_MULTIPLIER
            + _usage_cases.CODEX_PRICING_OUTPUT_TOKENS
            * _usage_cases.PRICE_RATE_THIRTY
            * _usage_cases.LONG_CONTEXT_OUTPUT_MULTIPLIER
        ) / _usage_cases.TOKENS_PER_MILLION
        assert metrics.cost_usd is not None
        self.assertAlmostEqual(metrics.cost_usd, expected, places=9)

    def test_gpt_five_five_threshold_is_flat(self) -> None:
        # The tier applies strictly when input > threshold; at or
        # under 272K the standard flat rates apply unchanged. This
        # guards the long-context tier boundary.
        stdout = _jsonl.jsonl(
            _codex.turn_complete(
                model=_usage_cases.GPT_FIVE_FIVE,
                input=_usage_cases.LONG_CONTEXT_THRESHOLD_TOKENS,
                cached=0,
                output=_usage_cases.CODEX_PRICING_OUTPUT_TOKENS,
            ),
        )
        metrics = _metrics.parse_codex_usage(stdout)
        self.assertEqual(metrics.cost_source, _usage_cases.ESTIMATED_COST_SOURCE)
        # Flat rate: input * 5 + output * 30, /1M (no multipliers).
        expected = (
            _usage_cases.LONG_CONTEXT_THRESHOLD_TOKENS * 5
            + _usage_cases.CODEX_PRICING_OUTPUT_TOKENS * _usage_cases.PRICE_RATE_THIRTY
        ) / _usage_cases.TOKENS_PER_MILLION
        assert metrics.cost_usd is not None
        self.assertAlmostEqual(metrics.cost_usd, expected, places=9)

    def test_gpt_five_five_cached_tokens_tier_up(self) -> None:
        # Cached input tokens are still input billing -- the long-
        # context multiplier must apply to them too. Otherwise a
        # cache-heavy session over the threshold would silently
        # under-report against OpenAI's actual bill.
        stdout = _jsonl.jsonl(
            _codex.turn_complete(
                model=_usage_cases.GPT_FIVE_FIVE,
                input=_usage_cases.LONG_CONTEXT_INPUT_TOKENS,
                cached=_usage_cases.LONG_CONTEXT_CACHED_INPUT_TOKENS,
                output=_usage_cases.CODEX_PRICING_OUTPUT_TOKENS,
            ),
        )
        metrics = _metrics.parse_codex_usage(stdout)
        self.assertEqual(metrics.cost_source, _usage_cases.ESTIMATED_COST_SOURCE)
        uncached = _usage_cases.LONG_CONTEXT_INPUT_TOKENS - _usage_cases.LONG_CONTEXT_CACHED_INPUT_TOKENS
        expected = (
            uncached * 5 * _usage_cases.LONG_CONTEXT_INPUT_MULTIPLIER
            + _usage_cases.LONG_CONTEXT_CACHED_INPUT_TOKENS * 0.5 * _usage_cases.LONG_CONTEXT_INPUT_MULTIPLIER
            + _usage_cases.CODEX_PRICING_OUTPUT_TOKENS
            * _usage_cases.PRICE_RATE_THIRTY
            * _usage_cases.LONG_CONTEXT_OUTPUT_MULTIPLIER
        ) / _usage_cases.TOKENS_PER_MILLION
        assert metrics.cost_usd is not None
        self.assertAlmostEqual(metrics.cost_usd, expected, places=9)
