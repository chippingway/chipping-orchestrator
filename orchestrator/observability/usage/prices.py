# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Standard first-party API price catalogue and the usage-cost estimates priced from it.

One table of `price_catalogue.PriceRow` per provider, verified on 2026-10-29 against the provider pricing pages --
https://platform.claude.com/docs/en/about-claude/pricing, https://developers.openai.com/api/docs/pricing, and
https://ai.google.dev/gemini-api/docs/pricing -- with each model page for the aliases and snapshot IDs a row answers
to. Each rate tuple copies one row of its provider's page in that page's column order, a dash on the page being
`None`, so a recheck compares them cell by cell.

Every Claude row is active -- Opus 4 through 5.5, Sonnet 4 through 5.5, Fable 5 and 5.1, and Haiku 3.5, 4.5, and
5.5 -- since the Claude accounting (`claude_requests`) prices each API message on its own, at the lifetime each cache
write was reported under, as each request is billed. Every OpenAI row is active too -- GPT-5 through GPT-5.5 with
their Codex and shut-down chat models, and the GPT-5.6 and GPT-6 families -- since the Codex accounting
(`codex_requests`) charges a cache write only at a lifetime its usage record reports and a request tier only where the
record bounds every request it sums. Every Gemini row is dormant until Antigravity's accounting can price it. The
restricted Mythos and Daybreak (cyber) models carry no row: no captured stream shows a harness emitting their IDs, and
`gpt-5.6-cyber` is a moving alias for whichever cyber model is current, as is the bare `chat-latest`.

An estimate priced from a table is a token-only list-price equivalent on that provider's API basis, carrying the
`verified_on` date of every row it was priced at, as `cost_evidence` defines it -- never a subscription or credit
charge, nor a premium the rows do not list, such as a Claude request's fast-mode or data-residency multiplier.
"""

from __future__ import annotations

from datetime import date
from functools import partial

from orchestrator.observability.usage import cost_evidence, price_catalogue, protocol

_VERIFIED_ON = date.fromisoformat("2026-10-29")
# The page guarantees GPT-5.6 Sol's promotional rates at least through this
# date; past it the row needs a recheck, and its rates stand until one.
_GPT_FIVE_SIX_SOL_REVIEW = date.fromisoformat("2026-11-21")
_GEMINI_FOUR_ARGON_THROUGH = date.fromisoformat("2026-11-30")
_GEMINI_FOUR_ARGON_STARTING = date.fromisoformat("2026-12-01")
_GEMINI_FLASH_THROUGH = date.fromisoformat("2026-12-31")
_GEMINI_FLASH_STARTING = date.fromisoformat("2027-01-01")

_HAIKU_FIVE_FIVE_PROMPT_TIER = 100_000
_OPENAI_LONG_CONTEXT_TIER = 272_000
_GEMINI_PRO_PROMPT_TIER = 200_000

# Base input, 5m cache writes, 1h cache writes, cache hits and refreshes, output.
_CLAUDE_COLUMNS = (
    protocol.INPUT,
    protocol.CACHE_WRITE_FIVE_MIN,
    protocol.CACHE_WRITE_ONE_HOUR,
    protocol.CACHE_READ,
    protocol.OUTPUT,
)
# Input, output, cached input, 30m write, 12h write; the older models' table
# stops after cached input, since a model before GPT-5.6 charges no cache
# write of its own.
_OPENAI_COLUMNS = (
    protocol.INPUT,
    protocol.OUTPUT,
    protocol.CACHED,
    protocol.CACHE_WRITE_THIRTY_MIN,
    protocol.CACHE_WRITE_TWELVE_HOUR,
)
# Input, output including thinking tokens, context caching.
_GEMINI_COLUMNS = (protocol.INPUT, protocol.OUTPUT, protocol.CACHED)


def _page_rates(
    columns: tuple[str, ...],
    page_row: tuple[float | None, ...],
) -> protocol.RateMap:
    published = zip(columns, page_row, strict=False)
    return {column: rate for column, rate in published if rate is not None}


_claude = partial(_page_rates, _CLAUDE_COLUMNS)
_openai = partial(_page_rates, _OPENAI_COLUMNS)
_gemini = partial(_page_rates, _GEMINI_COLUMNS)

_OPUS_FOUR_FIVE_TO_FIVE = _claude((5, 6.25, 10, 0.5, 25))
_OPUS_FOUR_AND_FOUR_ONE = _claude((15, 18.75, 30, 1.5, 75))
_SONNET_FOUR_TO_FOUR_SIX = _claude((3, 3.75, 6, 0.3, 15))

CLAUDE_PRICES: tuple[price_catalogue.PriceRow, ...] = (
    price_catalogue.PriceRow(
        "claude-fable-5-1",
        _claude((10, 12.5, 20, 0.25, 50)),
        _VERIFIED_ON,
        active=True,
    ),
    price_catalogue.PriceRow(
        "claude-fable-5",
        _claude((10, 12.5, 20, 1, 50)),
        _VERIFIED_ON,
        active=True,
    ),
    price_catalogue.PriceRow(
        "claude-opus-5-5",
        _claude((4, 5, 8, 0.2, 20)),
        _VERIFIED_ON,
        active=True,
    ),
    price_catalogue.PriceRow("claude-opus-5", _OPUS_FOUR_FIVE_TO_FIVE, _VERIFIED_ON, active=True),
    price_catalogue.PriceRow("claude-opus-4-8", _OPUS_FOUR_FIVE_TO_FIVE, _VERIFIED_ON, active=True),
    price_catalogue.PriceRow("claude-opus-4-7", _OPUS_FOUR_FIVE_TO_FIVE, _VERIFIED_ON, active=True),
    price_catalogue.PriceRow("claude-opus-4-6", _OPUS_FOUR_FIVE_TO_FIVE, _VERIFIED_ON, active=True),
    price_catalogue.PriceRow(
        "claude-opus-4-5-20251101",
        _OPUS_FOUR_FIVE_TO_FIVE,
        _VERIFIED_ON,
        aliases=("claude-opus-4-5",),
        active=True,
    ),
    price_catalogue.PriceRow(
        "claude-opus-4-1-20250805",
        _OPUS_FOUR_AND_FOUR_ONE,
        _VERIFIED_ON,
        aliases=("claude-opus-4-1",),
        active=True,
    ),
    price_catalogue.PriceRow(
        "claude-opus-4-20250514",
        _OPUS_FOUR_AND_FOUR_ONE,
        _VERIFIED_ON,
        aliases=("claude-opus-4-0",),
        active=True,
    ),
    price_catalogue.PriceRow(
        "claude-sonnet-5-5",
        _claude((2, 2.5, 4, 0.1, 10)),
        _VERIFIED_ON,
        active=True,
    ),
    price_catalogue.PriceRow(
        "claude-sonnet-5",
        _claude((2, 2.5, 4, 0.2, 10)),
        _VERIFIED_ON,
        active=True,
    ),
    price_catalogue.PriceRow("claude-sonnet-4-6", _SONNET_FOUR_TO_FOUR_SIX, _VERIFIED_ON, active=True),
    price_catalogue.PriceRow(
        "claude-sonnet-4-5-20250929",
        _SONNET_FOUR_TO_FOUR_SIX,
        _VERIFIED_ON,
        aliases=("claude-sonnet-4-5",),
        active=True,
    ),
    price_catalogue.PriceRow(
        "claude-sonnet-4-20250514",
        _SONNET_FOUR_TO_FOUR_SIX,
        _VERIFIED_ON,
        aliases=("claude-sonnet-4-0",),
        active=True,
    ),
    price_catalogue.PriceRow(
        "claude-haiku-5-5",
        _claude((0.1, 0.125, 0.2, 0.01, 0.5)),
        _VERIFIED_ON,
        tier=price_catalogue.RequestTier(_HAIKU_FIVE_FIVE_PROMPT_TIER, _claude((0.5, 0.625, 1, 0.05, 2.5))),
        active=True,
    ),
    price_catalogue.PriceRow(
        "claude-haiku-4-5-20251001",
        _claude((1, 1.25, 2, 0.1, 5)),
        _VERIFIED_ON,
        aliases=("claude-haiku-4-5",),
        active=True,
    ),
    price_catalogue.PriceRow(
        "claude-3-5-haiku-20241022",
        _claude((0.8, 1, 1.6, 0.08, 4)),
        _VERIFIED_ON,
        aliases=("claude-3-5-haiku-latest",),
        active=True,
    ),
)

_GPT_FIVE_PRO_LONG_CONTEXT = price_catalogue.RequestTier(_OPENAI_LONG_CONTEXT_TIER, _openai((60, 270, None)))
_GPT_FIVE_ONE = _openai((1.25, 10, 0.125))
_GPT_FIVE_TWO = _openai((1.75, 14, 0.175))
_GPT_FIVE_MINI = _openai((0.25, 2, 0.025))

OPENAI_PRICES: tuple[price_catalogue.PriceRow, ...] = (
    price_catalogue.PriceRow(
        "gpt-6-astra",
        _openai((10, 50, 1, 12.5, 25)),
        _VERIFIED_ON,
        tier=price_catalogue.RequestTier(_OPENAI_LONG_CONTEXT_TIER, _openai((20, 75, 2, 25, 50))),
        active=True,
    ),
    price_catalogue.PriceRow(
        "gpt-6.1-sol",
        _openai((2, 10, 0.1, 2.5, 5)),
        _VERIFIED_ON,
        tier=price_catalogue.RequestTier(_OPENAI_LONG_CONTEXT_TIER, _openai((4, 15, 0.2, 5, 10))),
        active=True,
    ),
    price_catalogue.PriceRow(
        "gpt-6.1-terra",
        _openai((1, 5, 0.05, 1.25, 2.5)),
        _VERIFIED_ON,
        tier=price_catalogue.RequestTier(_OPENAI_LONG_CONTEXT_TIER, _openai((2, 7.5, 0.1, 2.5, 5))),
        active=True,
    ),
    price_catalogue.PriceRow(
        "gpt-6-luna",
        _openai((0.1, 0.5, 0.01, 0.125, 0.25)),
        _VERIFIED_ON,
        tier=price_catalogue.RequestTier(_OPENAI_LONG_CONTEXT_TIER, _openai((0.2, 0.75, 0.02, 0.25, 0.5))),
        active=True,
    ),
    price_catalogue.PriceRow(
        "gpt-6-sol",
        _openai((2, 10, 0.2, 2.5, 5)),
        _VERIFIED_ON,
        tier=price_catalogue.RequestTier(_OPENAI_LONG_CONTEXT_TIER, _openai((4, 15, 0.4, 5, 10))),
        active=True,
    ),
    price_catalogue.PriceRow(
        "gpt-5.6-sol",
        _openai((4, 20, 0.4, 5, 10)),
        _VERIFIED_ON,
        aliases=("gpt-5.6",),
        tier=price_catalogue.RequestTier(_OPENAI_LONG_CONTEXT_TIER, _openai((8, 30, 0.8, 10, 20))),
        review_after=_GPT_FIVE_SIX_SOL_REVIEW,
        active=True,
    ),
    price_catalogue.PriceRow(
        "gpt-5.6-terra",
        _openai((2, 12, 0.2, 2.5, 5)),
        _VERIFIED_ON,
        tier=price_catalogue.RequestTier(_OPENAI_LONG_CONTEXT_TIER, _openai((4, 18, 0.4, 5, 10))),
        active=True,
    ),
    price_catalogue.PriceRow(
        "gpt-5.6-luna",
        _openai((0.2, 1.2, 0.02, 0.25, 0.5)),
        _VERIFIED_ON,
        tier=price_catalogue.RequestTier(_OPENAI_LONG_CONTEXT_TIER, _openai((0.4, 1.8, 0.04, 0.5, 1))),
        active=True,
    ),
    price_catalogue.PriceRow(
        "gpt-5.5",
        _openai((5, 30, 0.5)),
        _VERIFIED_ON,
        aliases=("gpt-5.5-2026-04-23",),
        tier=price_catalogue.RequestTier(_OPENAI_LONG_CONTEXT_TIER, _openai((10, 45, 1))),
        active=True,
    ),
    price_catalogue.PriceRow(
        "gpt-5.5-pro",
        _openai((30, 180, None)),
        _VERIFIED_ON,
        aliases=("gpt-5.5-pro-2026-04-23",),
        tier=_GPT_FIVE_PRO_LONG_CONTEXT,
        active=True,
    ),
    price_catalogue.PriceRow(
        "gpt-5.4",
        _openai((2.5, 15, 0.25)),
        _VERIFIED_ON,
        aliases=("gpt-5.4-2026-03-05",),
        tier=price_catalogue.RequestTier(_OPENAI_LONG_CONTEXT_TIER, _openai((5, 22.5, 0.5))),
        active=True,
    ),
    price_catalogue.PriceRow(
        "gpt-5.4-pro",
        _openai((30, 180, None)),
        _VERIFIED_ON,
        aliases=("gpt-5.4-pro-2026-03-05",),
        tier=_GPT_FIVE_PRO_LONG_CONTEXT,
        active=True,
    ),
    price_catalogue.PriceRow(
        "gpt-5.4-mini",
        _openai((0.75, 4.5, 0.075)),
        _VERIFIED_ON,
        aliases=("gpt-5.4-mini-2026-03-17",),
        active=True,
    ),
    price_catalogue.PriceRow(
        "gpt-5.4-nano",
        _openai((0.2, 1.25, 0.02)),
        _VERIFIED_ON,
        aliases=("gpt-5.4-nano-2026-03-17",),
        active=True,
    ),
    price_catalogue.PriceRow("gpt-5.3-codex", _GPT_FIVE_TWO, _VERIFIED_ON, active=True),
    # The chat models are shut down, so each `-latest` ID names one fixed
    # model, and its model page keeps the rates it was billed at.
    price_catalogue.PriceRow("gpt-5.3-chat-latest", _GPT_FIVE_TWO, _VERIFIED_ON, active=True),
    price_catalogue.PriceRow("gpt-5.2", _GPT_FIVE_TWO, _VERIFIED_ON, aliases=("gpt-5.2-2025-12-11",), active=True),
    price_catalogue.PriceRow("gpt-5.2-codex", _GPT_FIVE_TWO, _VERIFIED_ON, active=True),
    price_catalogue.PriceRow("gpt-5.2-chat-latest", _GPT_FIVE_TWO, _VERIFIED_ON, active=True),
    price_catalogue.PriceRow(
        "gpt-5.2-pro",
        _openai((21, 168, None)),
        _VERIFIED_ON,
        aliases=("gpt-5.2-pro-2025-12-11",),
        active=True,
    ),
    price_catalogue.PriceRow("gpt-5.1", _GPT_FIVE_ONE, _VERIFIED_ON, aliases=("gpt-5.1-2025-11-13",), active=True),
    price_catalogue.PriceRow("gpt-5.1-codex", _GPT_FIVE_ONE, _VERIFIED_ON, active=True),
    price_catalogue.PriceRow("gpt-5.1-codex-max", _GPT_FIVE_ONE, _VERIFIED_ON, active=True),
    price_catalogue.PriceRow("gpt-5.1-codex-mini", _GPT_FIVE_MINI, _VERIFIED_ON, active=True),
    price_catalogue.PriceRow("gpt-5.1-chat-latest", _GPT_FIVE_ONE, _VERIFIED_ON, active=True),
    price_catalogue.PriceRow("gpt-5", _GPT_FIVE_ONE, _VERIFIED_ON, aliases=("gpt-5-2025-08-07",), active=True),
    price_catalogue.PriceRow("gpt-5-codex", _GPT_FIVE_ONE, _VERIFIED_ON, active=True),
    price_catalogue.PriceRow("gpt-5-chat-latest", _GPT_FIVE_ONE, _VERIFIED_ON, active=True),
    price_catalogue.PriceRow(
        "gpt-5-pro",
        _openai((15, 120, None)),
        _VERIFIED_ON,
        aliases=("gpt-5-pro-2025-10-06",),
        active=True,
    ),
    price_catalogue.PriceRow(
        "gpt-5-mini",
        _GPT_FIVE_MINI,
        _VERIFIED_ON,
        aliases=("gpt-5-mini-2025-08-07",),
        active=True,
    ),
    price_catalogue.PriceRow(
        "gpt-5-nano",
        _openai((0.05, 0.4, 0.005)),
        _VERIFIED_ON,
        aliases=("gpt-5-nano-2025-08-07",),
        active=True,
    ),
    price_catalogue.PriceRow("codex-mini-latest", _openai((1.5, 6, 0.375)), _VERIFIED_ON, active=True),
)

_GEMINI_FLASH_BEFORE_CHANGE = _gemini((0.75, 3.75, 0.075))
_GEMINI_FLASH_AFTER_CHANGE = _gemini((1.5, 7.5, 0.15))

GEMINI_PRICES: tuple[price_catalogue.PriceRow, ...] = (
    price_catalogue.PriceRow(
        "gemini-4-argon",
        _gemini((2, 10, 0.1)),
        _VERIFIED_ON,
        through=_GEMINI_FOUR_ARGON_THROUGH,
    ),
    price_catalogue.PriceRow(
        "gemini-4-argon",
        _gemini((4, 20, 0.2)),
        _VERIFIED_ON,
        starting=_GEMINI_FOUR_ARGON_STARTING,
    ),
    price_catalogue.PriceRow(
        "gemini-3.8-flash",
        _GEMINI_FLASH_BEFORE_CHANGE,
        _VERIFIED_ON,
        through=_GEMINI_FLASH_THROUGH,
    ),
    price_catalogue.PriceRow(
        "gemini-3.8-flash",
        _GEMINI_FLASH_AFTER_CHANGE,
        _VERIFIED_ON,
        starting=_GEMINI_FLASH_STARTING,
    ),
    price_catalogue.PriceRow(
        "gemini-3.6-flash",
        _GEMINI_FLASH_BEFORE_CHANGE,
        _VERIFIED_ON,
        through=_GEMINI_FLASH_THROUGH,
    ),
    price_catalogue.PriceRow(
        "gemini-3.6-flash",
        _GEMINI_FLASH_AFTER_CHANGE,
        _VERIFIED_ON,
        starting=_GEMINI_FLASH_STARTING,
    ),
    price_catalogue.PriceRow(
        "gemini-3.1-pro-preview",
        _gemini((2, 12, 0.2)),
        _VERIFIED_ON,
        tier=price_catalogue.RequestTier(_GEMINI_PRO_PROMPT_TIER, _gemini((4, 18, 0.4))),
    ),
)


def claude_row(model: str) -> price_catalogue.PriceRow | None:
    return price_catalogue.active_row(CLAUDE_PRICES, model)


def claude_rates(model: str) -> protocol.RateMap | None:
    row = claude_row(model)
    return None if row is None else row.rates


def claude_estimate(
    model: str,
    bucket: protocol.TokenBucket,
    prompt_tokens: int | None,
) -> cost_evidence.CostContribution | None:
    """The bucket priced at the model's Anthropic API list rates, or None when nothing establishes its price.

    `prompt_tokens` is the prompt size of the one request the bucket counts, or None where it counts no request
    whose size is known; a request-tiered model prices only a bucket with one, as `PriceRow.rates_for_request`
    reads. Each class the bucket counts tokens of pays its own rate, so tokens of a class the rates do not
    publish -- a cache write of unknown lifetime -- leave the estimate None rather than borrowing another class's
    rate, while a class the bucket does not report, or reports zero of, costs nothing.
    """
    row = claude_row(model)
    rates = None if row is None else row.rates_for_request(prompt_tokens)
    amount = None if rates is None else priced_amount(rates, bucket)
    if row is None or amount is None:
        return None
    return cost_evidence.CostContribution(cost_evidence.ANTHROPIC_API_ESTIMATE, amount, (row.verified_on,))


def priced_amount(rates: protocol.RateMap, bucket: protocol.TokenBucket) -> float | None:
    """The bucket's tokens at `rates`, in USD, or None where it holds tokens of a class the rates do not publish."""
    charged = {token_class: count for token_class, count in bucket.items() if count}
    if not charged.keys() <= rates.keys():
        return None
    priced = (rates[token_class] * count for token_class, count in charged.items())
    return sum(priced) / protocol.TOKENS_PER_MILLION


def codex_row(model: str) -> price_catalogue.PriceRow | None:
    return price_catalogue.active_row(OPENAI_PRICES, model)
