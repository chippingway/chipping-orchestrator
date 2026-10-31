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
negative count is no count. Each of those leaves the run unpriced.
"""

from __future__ import annotations

from collections.abc import Sequence
from types import MappingProxyType
from typing import Any

from orchestrator.observability.usage import agy_events, cost_evidence, price_catalogue, prices, protocol

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


def billed_tokens(records: Sequence[dict[str, int]]) -> protocol.TokenBucket | None:
    """The steps' counts summed by the class each is billed at, or None where they establish no amount.

    No step leaves nothing to price, and a step whose usage reports no count, or a negative one, establishes none.
    """
    if not records or not all(records):
        return None
    billed: protocol.TokenBucket = {}
    for record in records:
        for counter, count in record.items():
            if count < 0:
                return None
            token_class = _TOKEN_CLASSES[counter]
            billed[token_class] = billed.get(token_class, 0) + count
    return billed


def api_model(models: tuple[str, ...]) -> str | None:
    """The Gemini API model a run attributed to `models` is priced as: its one model's, where that slug is mapped."""
    if len(models) != 1:
        return None
    return API_MODELS.get(models[0])


def estimate(
    models: tuple[str, ...],
    records: list[dict[str, int]],
    span: price_catalogue.UsageSpan | None,
) -> cost_evidence.CostContribution | None:
    """The steps' usage priced as a Gemini API estimate, or None when nothing establishes its price."""
    model = api_model(models)
    row = None if model is None else prices.gemini_row(model, span)
    rates = None if row is None else row.rates_for_request(None)
    bucket = billed_tokens(records)
    if row is None or rates is None or bucket is None:
        return None
    amount = prices.priced_amount(rates, bucket)
    if amount is None:
        return None
    return cost_evidence.CostContribution(cost_evidence.GEMINI_API_ESTIMATE, amount, (row.verified_on,))
