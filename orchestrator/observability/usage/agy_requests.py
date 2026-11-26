# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which Gemini API model one Antigravity run's completed steps are priced as, and the estimate they are priced at.

`agy --output-format stream-json` names the model on `init` alone, as the `--model` slug it was given and only when one
was, and a slug is an Antigravity deployment rather than an API ID: `API_MODELS` maps a slug only where Antigravity's
documentation or its CLI lists it for a model the Gemini API prices under one ID. The headless guide
(https://antigravity.google/docs/cli/headless/) lists `gemini-4-argon`, `gemini-3.8-flash`, and `gemini-3.6-flash` at
high and medium thinking, and the model listing of agy 1.4.10 adds `gemini-3.8-flash-low`; a thinking level is a setting
of the model, not another SKU. Gemini 3.7 Flash has no row, since the Developer API routes its deprecated ID to 3.8
Flash while Antigravity still serves a 3.7 deployment; Gemini 3.1 Pro's API SKU and the request sizes it would be tiered
on are not established; and the Claude and GPT-OSS models Antigravity also serves are no Gemini usage. Any of them, or
any other slug, stays unpriced.

A completed step's usage is one generation's, on agy 1.4.10: its conversation store keeps each usage-bearing step's
usage as one generation's, and every generation it records, a response's and each helper generation beside it, names the
model the conversation selected, so a `checkpoint` step's usage is priced as that model's like a response's.
`input_tokens` is that generation's ordinary input, apart from its `cache_read_tokens` -- a step's cache reads exceed
its input on nearly every step that reads any, which no input holding them could -- and `output_tokens` holds its
`thinking_tokens`, which the Gemini API bills as output. A step spawning a subagent hands work to another conversation,
whose model and usage the stream does not establish, so a run that spawned one has no estimate.

The estimate prices each class at its own rate -- ordinary input, cached input, and output with thinking -- on the
active row in effect throughout the run's usage span (`prices.gemini_row`). A run with no span, or one reaching both
sides of a scheduled rate change, finds no one row; a request-tiered row needs a request size no step is read for; and a
negative count is no count. Each of those leaves the run unpriced, and an unpriced run states every reason that applies
(`unpriced`) -- its subagent, its model, and its steps' counts each answered on its own -- against each model it names,
or `unknown` where it names none.
"""

from __future__ import annotations

from collections.abc import Sequence
from types import MappingProxyType
from typing import Any

from orchestrator.observability.usage import agy_events, cost_evidence, price_catalogue, prices, protocol, unpriced

API_MODELS = MappingProxyType({
    "gemini-4-argon-high": "gemini-4-argon",
    "gemini-4-argon-medium": "gemini-4-argon",
    "gemini-3.8-flash-high": "gemini-3.8-flash",
    "gemini-3.8-flash-medium": "gemini-3.8-flash",
    "gemini-3.8-flash-low": "gemini-3.8-flash",
    "gemini-3.6-flash-high": "gemini-3.6-flash",
    "gemini-3.6-flash-medium": "gemini-3.6-flash",
})

# The class the Gemini API bills each counter a step reports at.
_TOKEN_CLASSES = MappingProxyType({
    protocol.INPUT_TOKENS: protocol.INPUT,
    protocol.CACHE_READ_TOKENS: protocol.CACHED,
    protocol.OUTPUT_TOKENS: protocol.OUTPUT,
})


def delegates(events: list[dict[str, Any]]) -> bool:
    """Whether any step the run printed spawned a subagent."""
    steps = agy_events.payloads(events, agy_events.STEP_UPDATE)
    return any(step.get(agy_events.SUBAGENT_INFO) is not None for step in steps)


def billed_tokens(records: Sequence[dict[str, int]]) -> protocol.TokenBucket:
    """The steps' counts summed by the class each is billed at."""
    billed: protocol.TokenBucket = {}
    for record in records:
        for counter, count in record.items():
            token_class = _TOKEN_CLASSES[counter]
            billed[token_class] = billed.get(token_class, 0) + count
    return billed


def count_reasons(records: Sequence[dict[str, int]]) -> tuple[str, ...]:
    """Why the steps' counts establish no amount: a step whose usage reports no count, or a negative count."""
    missing = () if all(records) else (unpriced.MISSING_TOKEN_COUNT,)
    negative = any(count < 0 for record in records for count in record.values())
    return (*missing, *((unpriced.INVALID_TOKEN_COUNTS,) if negative else ()))


def api_model(models: tuple[str, ...]) -> str | None:
    """The Gemini API model a run attributed to `models` is priced as: its one model's, where that slug is mapped."""
    if len(models) != 1:
        return None
    return API_MODELS.get(models[0])


def model_reasons(
    models: tuple[str, ...],
    row: price_catalogue.PriceRow | None,
) -> tuple[str, ...]:
    """Why a run attributed to `models` has no Gemini API row; none where `row` is the one in effect for its span.

    A mapped model whose active rows put no one of them in effect throughout the span lacks a rate period, not a price.
    """
    if len(models) > 1:
        return (unpriced.SEVERAL_MODELS,)
    model = api_model(models)
    if model is None:
        return (unpriced.MISSING_MODEL_PRICE,)
    if row is not None:
        return ()
    catalogued = (candidate for candidate in prices.GEMINI_PRICES if candidate.answers_to(model))
    priced = any(candidate.active for candidate in catalogued)
    return (unpriced.INDETERMINATE_RATE_PERIOD if priced else unpriced.MISSING_MODEL_PRICE,)


def price(
    models: tuple[str, ...],
    records: list[dict[str, int]],
    span: price_catalogue.UsageSpan | None,
    *,
    delegated: bool,
) -> unpriced.Pricing:
    """The steps' usage priced as a Gemini API estimate, or every reason nothing establishes its price.

    `delegated` says the run spawned a subagent. A run with no step has no usage, so nothing to price.
    """
    if not records:
        return unpriced.Pricing()
    model = api_model(models)
    row = None if model is None else prices.gemini_row(model, span)
    reasons = (
        *((unpriced.SUBAGENT_USAGE,) if delegated else ()),
        *model_reasons(models, row),
        *count_reasons(records),
    )
    if row is None or reasons:
        return unpriced.Pricing.refused(models or (protocol.UNKNOWN,), reasons)
    return _priced_at(row, billed_tokens(records), models)


def _priced_at(
    row: price_catalogue.PriceRow,
    bucket: protocol.TokenBucket,
    models: tuple[str, ...],
) -> unpriced.Pricing:
    """The bucket priced at `row`, which no step's request size tiers, or why it has no amount there."""
    rates = row.rates_for_request(None)
    if rates is None:
        return unpriced.Pricing.refused(models, (unpriced.INDETERMINATE_REQUEST_TIER,))
    amount = prices.priced_amount(rates, bucket)
    if amount is None:
        return unpriced.Pricing.refused(models, unpriced.unrated(rates, bucket))
    return unpriced.Pricing(
        cost_evidence.CostContribution(cost_evidence.GEMINI_API_ESTIMATE, amount, (row.verified_on,)),
    )
