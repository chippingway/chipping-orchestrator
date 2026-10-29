# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a usage cost means: the basis each amount is stated on, how complete it is, and the reduction over many.

A cost is a set of monetary contributions, at most one per basis, beside a completeness. A basis names what an amount
is, never what anybody was billed:

- `cli-reported` is the USD figure the agent CLI printed for the run. Its origin is the CLI; nothing verifies it
  against an invoice, a subscription, or a credit balance.
- `anthropic-api-estimate`, `openai-api-estimate`, and `gemini-api-estimate` are token-only list-price equivalents:
  the run's observable usage priced at that provider's Standard first-party API rates from active rows of the price
  catalogue, naming the dates those rows were verified on.
- `unknown` files an amount stated with no basis. No parser writes it: a reader assigns it to the amount of a record
  that states no cost evidence, and a reduction over such a record carries it on.

Completeness says how much of the observable usage the contributions cover: `complete` (all of it), `incomplete`
(some of it carries no amount, so the contributions are at most a subtotal), `no-usage` (the stream showed nothing to
price), and `unknown` (nothing states it: a record with no cost evidence, whatever amount it carries, or a reduction
over one). Missing basis information therefore stays apart from every state a parser writes, and nothing is inferred
in its place.

A reduction sums each basis's amounts on their own and keeps the weakest completeness any input states -- a known
incomplete one ahead of an unknown one -- so a total holding unpriced usage, or an amount with no basis, never reads
as complete spend. A zero is a contribution like any other: a complete zero is spend of zero, not an absence.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Any

COST_EVIDENCE = "cost_evidence"
COST_USD = "cost_usd"
COMPLETENESS = "completeness"
CONTRIBUTIONS = "contributions"
BASIS = "basis"
AMOUNT_USD = "amount_usd"
RATES_VERIFIED_ON = "rates_verified_on"

CLI_REPORTED = "cli-reported"
ANTHROPIC_API_ESTIMATE = "anthropic-api-estimate"
OPENAI_API_ESTIMATE = "openai-api-estimate"
GEMINI_API_ESTIMATE = "gemini-api-estimate"
UNKNOWN_BASIS = "unknown"
# What a total spanning more than one basis is labelled as; no contribution carries it.
BLENDED = "blended"

COMPLETE = "complete"
INCOMPLETE = "incomplete"
NO_USAGE = "no-usage"
UNKNOWN = "unknown"

# The run-level `cost_source` tags a producer records beside its evidence.
REPORTED_SOURCE = "reported"
ESTIMATED_SOURCE = "estimated"
UNKNOWN_PRICE_SOURCE = "unknown-price"
NO_USAGE_SOURCE = NO_USAGE

# Tuples, so that testing an unhashable serialized value for membership answers no rather than raising.
BASES = (CLI_REPORTED, ANTHROPIC_API_ESTIMATE, OPENAI_API_ESTIMATE, GEMINI_API_ESTIMATE, UNKNOWN_BASIS)

# From the strongest claim to the weakest: a reduction keeps the last of these any input states.
_COMPLETENESS_ORDER = (NO_USAGE, COMPLETE, UNKNOWN, INCOMPLETE)
_SOURCE_TAGS = MappingProxyType({INCOMPLETE: UNKNOWN_PRICE_SOURCE, NO_USAGE: NO_USAGE_SOURCE})


@dataclass(frozen=True)
class CostContribution:
    """One basis's share of a cost, in USD, and the verification dates of the rates an estimate was priced at."""

    basis: str
    amount_usd: float
    rates_verified_on: tuple[date, ...] = ()

    @classmethod
    def from_dict(cls, raw: Any) -> CostContribution | None:
        """Read one serialized contribution, or None when it is not one this representation serializes."""
        if not isinstance(raw, dict) or raw.get(BASIS) not in BASES:
            return None
        amount = _amount(raw.get(AMOUNT_USD))
        verified_on = _dates(raw.get(RATES_VERIFIED_ON))
        if amount is None or verified_on is None:
            return None
        return cls(raw[BASIS], amount, verified_on)

    def plus(self, other: CostContribution) -> CostContribution:
        verified_on = sorted({*self.rates_verified_on, *other.rates_verified_on})
        return CostContribution(self.basis, self.amount_usd + other.amount_usd, tuple(verified_on))

    def to_dict(self) -> dict[str, Any]:
        return {
            BASIS: self.basis,
            AMOUNT_USD: self.amount_usd,
            RATES_VERIFIED_ON: [verified.isoformat() for verified in self.rates_verified_on],
        }


@dataclass(frozen=True)
class CostEvidence:
    """A cost's contributions by basis, in basis order, and how much of the observable usage they cover."""

    completeness: str
    contributions: tuple[CostContribution, ...] = ()

    @classmethod
    def from_dict(cls, raw: Any) -> CostEvidence | None:
        """Read serialized evidence, or None when it is not evidence this representation serializes.

        Serialized evidence names each basis once, at least one for a complete cost, and none for a stream with no
        usage; anything else is no current evidence.
        """
        if not isinstance(raw, dict) or raw.get(COMPLETENESS) not in _COMPLETENESS_ORDER:
            return None
        raw_contributions = raw.get(CONTRIBUTIONS)
        if not isinstance(raw_contributions, list):
            return None
        contributions = [CostContribution.from_dict(raw_contribution) for raw_contribution in raw_contributions]
        stated = [contribution for contribution in contributions if contribution is not None]
        evidence = cls(raw[COMPLETENESS], _merged(stated))
        if len(evidence.contributions) != len(contributions) or not evidence.is_consistent:
            return None
        return evidence

    @property
    def is_consistent(self) -> bool:
        """Whether the two can stand together: a complete cost states every basis it is on, and no usage no amount."""
        bases = {contribution.basis for contribution in self.contributions}
        if self.completeness == COMPLETE:
            return bool(bases) and UNKNOWN_BASIS not in bases
        return self.completeness != NO_USAGE or not bases

    @property
    def total_usd(self) -> float | None:
        """Every contribution summed, complete or not; None when no amount was stated at all."""
        if not self.contributions:
            return None
        return math.fsum(contribution.amount_usd for contribution in self.contributions)

    @property
    def complete_usd(self) -> float | None:
        """The total only when it covers all the observable usage: an incomplete or unknown one is never complete."""
        return self.total_usd if self.completeness == COMPLETE else None

    @property
    def basis(self) -> str | None:
        """The basis the total is stated on: the sole contribution's, `blended` across several, None with none."""
        if len(self.contributions) > 1:
            return BLENDED
        return self.contributions[0].basis if self.contributions else None

    @property
    def cost_source(self) -> str:
        """The `cost_source` tag a run's own cost is recorded under beside its evidence."""
        if self.completeness != COMPLETE:
            return _SOURCE_TAGS.get(self.completeness, UNKNOWN)
        return REPORTED_SOURCE if self.basis == CLI_REPORTED else ESTIMATED_SOURCE

    def to_dict(self) -> dict[str, Any]:
        return {
            COMPLETENESS: self.completeness,
            CONTRIBUTIONS: [contribution.to_dict() for contribution in self.contributions],
        }


def reduce_costs(costs: Iterable[CostEvidence]) -> CostEvidence:
    """Fold many costs into one: amounts summed per basis, and the weakest completeness any of them states.

    An empty fold, like a fold of runs that all printed no usage, is `no-usage`.
    """
    folded = tuple(costs)
    completeness = max(
        (cost.completeness for cost in folded),
        key=_COMPLETENESS_ORDER.index,
        default=NO_USAGE,
    )
    return CostEvidence(
        completeness,
        _merged(contribution for cost in folded for contribution in cost.contributions),
    )


def recorded_cost(record: Mapping[str, Any]) -> CostEvidence:
    """The cost one serialized usage record states.

    A record whose `cost_evidence` is missing, or is not evidence this representation serializes, states no basis and
    no completeness: its cost is `unknown`, holding whatever `cost_usd` it carries under the `unknown` basis. Nothing
    is inferred from its `cost_source`, its backend, or its models.
    """
    evidence = CostEvidence.from_dict(record.get(COST_EVIDENCE))
    if evidence is not None:
        return evidence
    amount = _amount(record.get(COST_USD))
    unattributed = () if amount is None else (CostContribution(UNKNOWN_BASIS, amount),)
    return CostEvidence(UNKNOWN, unattributed)


def _merged(contributions: Iterable[CostContribution]) -> tuple[CostContribution, ...]:
    by_basis: dict[str, CostContribution] = {}
    for contribution in contributions:
        prior = by_basis.get(contribution.basis)
        by_basis[contribution.basis] = contribution if prior is None else prior.plus(contribution)
    return tuple(by_basis[basis] for basis in sorted(by_basis))


def _amount(raw: Any) -> float | None:
    """A USD amount a record states: a non-negative finite number a float holds, zero included; None otherwise."""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    try:
        amount = float(raw)
    except OverflowError:
        return None
    return amount if math.isfinite(amount) and amount >= 0 else None


def _dates(raw: Any) -> tuple[date, ...] | None:
    if not isinstance(raw, list):
        return None
    try:
        return tuple(date.fromisoformat(entry) for entry in raw)
    except (TypeError, ValueError):
        return None
