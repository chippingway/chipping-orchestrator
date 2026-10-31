# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Dated API price rows and the bounded model lookup over them.

A row prices one model at its provider's Standard first-party API list rates, in USD per million tokens. It answers
to its canonical model ID and to the documented aliases and published snapshot IDs listed beside it, each compared
whole: no prefix, substring, or suffix of a listed ID resolves, so an unknown version or an arbitrary suffix stays
unpriced rather than inheriting a neighbour's rates. A rate the provider does not publish is absent from the map, so
tokens of that class leave the estimate unknown instead of borrowing another class's rate.

Every row records the date its rates were last checked against the provider's pricing page (`verified_on`). A
provider-scheduled change is two rows of one ID over consecutive inclusive `starting` / `through` intervals; a row
carrying either bound resolves only for a usage date inside it, never for a caller with no date. `review_after` marks
a published guarantee whose expiry calls for a recheck of the row; it changes no rate by itself.

A row is dormant unless it is `active`: the catalogue resolves it, so its identity and rates can be read and tested,
but the production estimates price only active rows. New rows stay dormant until the accounting that prices their
provider's usage correctly lands.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from orchestrator.observability.usage import protocol


@dataclass(frozen=True)
class RequestTier:
    """The rates one request pays for the whole of itself once its prompt exceeds `above` tokens.

    What counts toward a request's prompt is the provider's own rule, applied by the estimator pricing that provider.
    """

    above: int
    rates: protocol.RateMap


@dataclass(frozen=True)
class PriceRow:
    model: str
    rates: protocol.RateMap
    verified_on: date
    aliases: tuple[str, ...] = ()
    tier: RequestTier | None = None
    starting: date | None = None
    through: date | None = None
    review_after: date | None = None
    active: bool = False

    def answers_to(self, model: str) -> bool:
        return model == self.model or model in self.aliases

    def in_effect(self, on: date | None) -> bool:
        if self.starting is None and self.through is None:
            return True
        if on is None:
            return False
        started = self.starting is None or self.starting <= on
        return started and (self.through is None or on <= self.through)

    def rates_for_prompt(self, prompt_tokens: int) -> protocol.RateMap:
        if self.tier is not None and prompt_tokens > self.tier.above:
            return self.tier.rates
        return self.rates

    def rates_for_request(self, prompt_tokens: int | None) -> protocol.RateMap | None:
        """The rates one request pays, `prompt_tokens` being its prompt size or None where nothing establishes it.

        A row with no tier charges every request alike, so its rates price usage summed over many requests too; a
        tiered row's rates depend on the request, so usage with no established prompt size has none.
        """
        if self.tier is None:
            return self.rates
        return None if prompt_tokens is None else self.rates_for_prompt(prompt_tokens)

    def rates_for_requests_within(self, prompt_bound: int | None) -> protocol.RateMap | None:
        """The rates each of several requests pays when none has a prompt over `prompt_bound`, or None.

        Usage summed over requests says nothing of which of them passed a tier, so a tiered row prices it only where
        the bound keeps every one at or under the threshold; a bound of None establishes nothing.
        """
        if self.tier is None:
            return self.rates
        if prompt_bound is None or prompt_bound > self.tier.above:
            return None
        return self.rates


def resolve(
    rows: Iterable[PriceRow],
    model: str,
    on: date | None = None,
) -> PriceRow | None:
    """Return the row answering to exactly `model` on the usage date `on`, dormant or active."""
    for row in rows:
        if row.answers_to(model) and row.in_effect(on):
            return row
    return None


def active_row(
    rows: Iterable[PriceRow],
    model: str,
    on: date | None = None,
) -> PriceRow | None:
    """Return the row a production estimate may price `model` with, or None when it is unknown or dormant."""
    row = resolve(rows, model, on)
    if row is None or not row.active:
        return None
    return row
