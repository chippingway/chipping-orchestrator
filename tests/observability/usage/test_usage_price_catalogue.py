# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Bounded model resolution, dated rate rows, and dormant rows in the API price catalogue."""

import itertools
import unittest
from datetime import date, timedelta
from functools import partial

from orchestrator.observability.usage import metrics as _metrics, price_catalogue, prices
from tests.observability.usage import (
    usage_catalogue_cases as _cases,
    usage_claude_events as _claude,
    usage_codex_events as _codex,
    usage_jsonl_helpers as _jsonl,
    usage_test_values as _usage_cases,
)

_UNDATED = ((prices.CLAUDE_PRICES, _cases.CLAUDE), (prices.OPENAI_PRICES, _cases.OPENAI))
_PROVIDERS = (*_UNDATED, (prices.GEMINI_PRICES, _cases.GEMINI))
_TABLES = tuple(table for table, _provider in _PROVIDERS)
_VERIFIED_ON = date.fromisoformat(_cases.VERIFIED_ON)
_PRODUCTION_LOOKUPS = ((prices.claude_rates, _cases.CLAUDE), (prices.codex_row, _cases.OPENAI))


def _claude_run(model: str) -> _metrics.UsageMetrics:
    usage = _claude.usage(input=1000, output=100, cache_read=_usage_cases.TOKEN_COUNT_TWO_HUNDRED)
    return _metrics.parse_claude_usage(_jsonl.jsonl(_claude.assistant(model=model, usage=usage)))


def _codex_run(model: str, cached: int = _usage_cases.TOKEN_COUNT_TWO_HUNDRED) -> _metrics.UsageMetrics:
    usage = _codex.turn_complete(model=model, input=1000, cached=cached, output=100)
    return _metrics.parse_codex_usage(_jsonl.jsonl(usage))


def _spellings(table: tuple[price_catalogue.PriceRow, ...]) -> list[str]:
    return sorted({name for row in table for name in (row.model, *row.aliases)})


# A dormant row, an arbitrary suffix on an active row's ID, an unknown version,
# and an invented SKU: each a model the run parsers leave unpriced.
_UNPRICED_RUNS = (
    (_claude_run, _cases.OPUS_FOUR_EIGHT),
    (_claude_run, "claude-opus-4-7[1m]"),
    (_claude_run, "claude-opus-4-9"),
    (_codex_run, _cases.GPT_FIVE_SIX),
    (_codex_run, "gpt-5.5-mini"),
    (_codex_run, "gpt-5.6-pro"),
)
# No cached input on the Codex side, so the pro models, which publish no
# cached-input rate, still estimate.
_UNCACHED_CODEX_RUN = partial(_codex_run, cached=0)
_ALIAS_RUNNERS = ((_claude_run, _cases.CLAUDE), (_UNCACHED_CODEX_RUN, _cases.OPENAI))

# A `_codex_run` on gpt-5.1-chat-latest: its 800 uncached input, 200 cached, and
# 100 output tokens at the model page's $1.25 / $0.125 / $10.
_CHAT_RUN_CHARGES = ((800, 1.25), (200, 0.125), (100, 10))


class CatalogueIdentityTest(unittest.TestCase):
    """Every row answers to exactly the IDs its provider documents, at the rates its page publishes."""

    def test_rows_carry_their_published_rates(self) -> None:
        for table, provider in _UNDATED:
            for case in provider.rows:
                with self.subTest(model=case[0]):
                    row = price_catalogue.resolve(table, case[0])
                    assert row is not None
                    observed = (row.model, row.rates, row.active)
                    self.assertEqual(observed, provider.expected_row(case))

    def test_catalogue_holds_only_the_listed_rows(self) -> None:
        for table, provider in _UNDATED:
            with self.subTest(columns=provider.columns):
                self.assertEqual(
                    sorted(row.model for row in table),
                    sorted(case[0] for case in provider.rows),
                )
        self.assertEqual(
            sorted({row.model for row in prices.GEMINI_PRICES}),
            sorted({case[0] for case in _cases.GEMINI_DATED}),
        )

    def test_aliases_are_the_documented_ones(self) -> None:
        for table, provider in _PROVIDERS:
            with self.subTest(columns=provider.columns):
                self.assertEqual(
                    {alias: row.model for row in table for alias in row.aliases},
                    dict(provider.aliases),
                )

    def test_every_spelling_resolves_to_its_row(self) -> None:
        for table, provider in _UNDATED:
            for spelling, model in provider.spellings().items():
                with self.subTest(spelling=spelling):
                    row = price_catalogue.resolve(table, spelling)
                    self.assertEqual(row.model if row else None, model)

    def test_lookalikes_resolve_nothing(self) -> None:
        for table, provider in _PROVIDERS:
            for lookalike in provider.lookalikes:
                with self.subTest(lookalike=lookalike):
                    self.assertIsNone(price_catalogue.resolve(table, lookalike))
                    self.assertIsNone(price_catalogue.resolve(table, lookalike, _VERIFIED_ON))

    def test_every_row_records_its_check(self) -> None:
        for table in _TABLES:
            for row in table:
                with self.subTest(model=row.model, starting=row.starting):
                    self.assertEqual(row.verified_on, _VERIFIED_ON)


class CatalogueTierTest(unittest.TestCase):
    """Request tiers carry the rates and thresholds their model's page publishes."""

    def test_tiers_carry_published_rates(self) -> None:
        for table, provider in _PROVIDERS:
            with self.subTest(columns=provider.columns):
                tiers = {row.model: row.tier for row in table if row.tier is not None}
                self.assertEqual(
                    {model: (tier.above, tier.rates) for model, tier in tiers.items()},
                    provider.expected_tiers(),
                )

    def test_tier_applies_only_above_threshold(self) -> None:
        for table, model in (
            (prices.CLAUDE_PRICES, "claude-haiku-5-5"),
            (prices.OPENAI_PRICES, _cases.GPT_FIVE_SIX_SOL),
            (prices.GEMINI_PRICES, _cases.GEMINI_PRO_PREVIEW),
        ):
            with self.subTest(model=model):
                row = price_catalogue.resolve(table, model)
                assert row is not None
                assert row.tier is not None
                above = row.tier.above
                self.assertIs(row.rates_for_prompt(above), row.rates)
                self.assertIs(row.rates_for_prompt(above + 1), row.tier.rates)


class CatalogueDateTest(unittest.TestCase):
    """Scheduled rate changes take effect on their published dates; a review trigger changes nothing."""

    def test_gemini_rates_follow_published_dates(self) -> None:
        for model, on, page_row in _cases.GEMINI_DATED:
            with self.subTest(model=model, on=on):
                row = price_catalogue.resolve(prices.GEMINI_PRICES, model, date.fromisoformat(on))
                self.assertEqual(
                    row.rates if row else None,
                    _cases.page_rates(_cases.GEMINI_COLUMNS, page_row),
                )

    def test_dated_rows_need_a_usage_date(self) -> None:
        self.assertIsNone(price_catalogue.resolve(prices.GEMINI_PRICES, _cases.GEMINI_FOUR_ARGON))
        self.assertIsNotNone(price_catalogue.resolve(prices.GEMINI_PRICES, _cases.GEMINI_PRO_PREVIEW))

    def test_spellings_never_overlap_in_time(self) -> None:
        for table in _TABLES:
            for spelling in _spellings(table):
                with self.subTest(spelling=spelling):
                    self._assert_consecutive([row for row in table if row.answers_to(spelling)])

    def test_review_trigger_changes_no_rate(self) -> None:
        reviewed = [row.model for table in _TABLES for row in table if row.review_after is not None]
        self.assertEqual(reviewed, [_cases.GPT_FIVE_SIX_SOL])
        sol = price_catalogue.resolve(prices.OPENAI_PRICES, _cases.GPT_FIVE_SIX_SOL)
        assert sol is not None
        self.assertEqual(sol.review_after, date.fromisoformat("2026-11-21"))
        for on in ("2026-11-21", "2026-11-22", "2027-06-01"):
            with self.subTest(on=on):
                self.assertIs(
                    price_catalogue.resolve(prices.OPENAI_PRICES, _cases.GPT_FIVE_SIX, date.fromisoformat(on)),
                    sol,
                )

    def _assert_consecutive(self, matching: list[price_catalogue.PriceRow]) -> None:
        # Rows sharing a spelling are one provider-scheduled change, listed in
        # date order: the first has no start, the last no end, and each ends
        # the day before the next begins.
        if len(matching) == 1:
            return
        self.assertIsNone(matching[0].starting)
        self.assertIsNone(matching[-1].through)
        for earlier, later in itertools.pairwise(matching):
            assert earlier.through is not None
            self.assertEqual(later.starting, earlier.through + timedelta(days=1))


class CatalogueEstimateTest(unittest.TestCase):
    """Production estimates price active rows alone, through every spelling those rows answer to."""

    def test_only_active_rows_price(self) -> None:
        for lookup, provider in _PRODUCTION_LOOKUPS:
            for spelling, model in provider.spellings().items():
                with self.subTest(spelling=spelling):
                    self.assertEqual(lookup(spelling) is not None, provider.is_active(model))

    def test_unknown_and_dormant_ids_run_unpriced(self) -> None:
        for run, model in _UNPRICED_RUNS:
            with self.subTest(model=model):
                metrics = run(model)
                self.assertEqual(metrics.models, (model,))
                self.assertEqual(
                    (metrics.cost_source, metrics.cost_usd),
                    (_usage_cases.UNKNOWN_COST_SOURCE, None),
                )

    def test_aliases_price_like_their_row(self) -> None:
        # Every documented alias and published snapshot prices a run exactly
        # as its canonical ID does: estimated on an active row, unpriced on a
        # dormant one.
        for run, provider in _ALIAS_RUNNERS:
            for alias, model in provider.aliases.items():
                with self.subTest(alias=alias):
                    by_alias = run(alias)
                    self.assertEqual(
                        by_alias.cost_source == _usage_cases.ESTIMATED_COST_SOURCE,
                        provider.is_active(model),
                    )
                    self.assertEqual(by_alias.cost_usd, run(model).cost_usd)

    def test_shut_down_chat_model_prices(self) -> None:
        charged = sum(tokens * rate for tokens, rate in _CHAT_RUN_CHARGES)
        expected = charged / _usage_cases.TOKENS_PER_MILLION
        metrics = _codex_run(_cases.GPT_FIVE_ONE_CHAT)
        self.assertEqual(metrics.cost_source, _usage_cases.ESTIMATED_COST_SOURCE)
        assert metrics.cost_usd is not None
        self.assertAlmostEqual(metrics.cost_usd, expected, places=_usage_cases.COST_ASSERT_PLACES)

    def test_active_claude_rows_are_flat(self) -> None:
        # The Claude run estimate prices each model's summed buckets at one
        # set of rates, so an active row has to publish all five and no tier.
        for row in prices.CLAUDE_PRICES:
            if row.active:
                with self.subTest(model=row.model):
                    self.assertIsNone(row.tier)
                    self.assertEqual(set(row.rates), set(_cases.CLAUDE_COLUMNS))
