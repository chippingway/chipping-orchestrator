# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Why an estimate leaves usage unpriced: the reasons an estimator records, each beside the model it concerns.

An estimator that establishes no amount for a run's usage says why, evaluating every check that applies rather than
stopping at the first: a Codex record past its request tier that also reports no cache-write count names both. A
reason concerns one model -- the one the usage was priced as, `unknown` where the run named none -- so a run spanning
several models states each model's own. The vocabulary is closed:

- `missing-model-price`: no active price-catalogue row answers to the model -- an unknown or unnamed model, one whose
  row is dormant, or an Antigravity CLI slug no Gemini API model is established for.
- `indeterminate-request-tier`: the row charges a request by its prompt size, and the usage establishes no request's
  size -- a Codex record whose summed input passes the tier's threshold, or a Claude row that is no one message's
  whole prompt.
- `missing-cache-write-count`: the row charges cache writes by lifetime, and the usage does not establish how many
  there were, such as the zero or the missing count the Codex CLI prints.
- `missing-cache-write-lifetime`: cache writes the usage reports no lifetime for, on a row charging each lifetime at
  its own rate.
- `unrated-token-class`: tokens of a class the row publishes no rate for, such as cached input on a model whose page
  lists no cached rate.
- `invalid-token-counts`: a negative count, or counts that cannot all be right -- cache reads and writes past the
  input, or a lifetime split claiming more writes than its aggregate.
- `missing-token-count`: an Antigravity step whose usage reports no count.
- `indeterminate-rate-period`: no one dated Gemini row is in effect throughout the run's usage span -- a run with no
  span, or one reaching both sides of a scheduled rate change.
- `subagent-usage`: the run spawned an Antigravity subagent, whose model and usage the stream does not establish.
- `several-models`: an Antigravity run names more than one model, so none is the one its steps are priced as.

A run keeps its reasons only where its selected cost is unpriced (`incomplete`): a CLI-reported amount, an explicit
zero included, and a complete estimate leave none, and a run with no usage has nothing to price. A usage record
serializes them as `unpriced_reasons`, one `{"model": ..., "reason": ...}` object per pair, each pair once and in
order, and only on a run they explain, so a record whose cost is not unpriced carries no such field. An unpriced
record without one -- every record an earlier build wrote -- has its reason unavailable, and nothing re-estimates it
to fill one in. A reader takes only the entries this vocabulary writes.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from orchestrator.observability.usage import cost_evidence, protocol

UNPRICED_REASONS = "unpriced_reasons"
MODEL = "model"
REASON = "reason"

MISSING_MODEL_PRICE = "missing-model-price"
INDETERMINATE_REQUEST_TIER = "indeterminate-request-tier"
MISSING_CACHE_WRITE_COUNT = "missing-cache-write-count"
MISSING_CACHE_WRITE_LIFETIME = "missing-cache-write-lifetime"
UNRATED_TOKEN_CLASS = "unrated-token-class"
INVALID_TOKEN_COUNTS = "invalid-token-counts"
MISSING_TOKEN_COUNT = "missing-token-count"
INDETERMINATE_RATE_PERIOD = "indeterminate-rate-period"
SUBAGENT_USAGE = "subagent-usage"
SEVERAL_MODELS = "several-models"

# Tuples, so that testing an unhashable serialized value for membership answers no rather than raising.
REASONS = (
    MISSING_MODEL_PRICE,
    INDETERMINATE_REQUEST_TIER,
    MISSING_CACHE_WRITE_COUNT,
    MISSING_CACHE_WRITE_LIFETIME,
    UNRATED_TOKEN_CLASS,
    INVALID_TOKEN_COUNTS,
    MISSING_TOKEN_COUNT,
    INDETERMINATE_RATE_PERIOD,
    SUBAGENT_USAGE,
    SEVERAL_MODELS,
)

# A class with no rate of its own whose tokens say more than that no rate was found.
_CLASS_REASONS = MappingProxyType({protocol.CACHE_WRITE_UNKNOWN_LIFETIME: MISSING_CACHE_WRITE_LIFETIME})


@dataclass(frozen=True, order=True)
class UnpricedReason:
    """One reason some of a run's usage of `model` has no estimate."""

    model: str
    reason: str

    @classmethod
    def from_dict(cls, raw: Any) -> UnpricedReason | None:
        """Read one serialized reason, or None when it is not one this vocabulary writes."""
        if not isinstance(raw, dict) or raw.get(REASON) not in REASONS:
            return None
        model = raw.get(MODEL)
        if not isinstance(model, str) or not model:
            return None
        return cls(model, raw[REASON])

    def to_dict(self) -> dict[str, str]:
        return {MODEL: self.model, REASON: self.reason}


@dataclass(frozen=True)
class Pricing:
    """What an estimator answers for some usage: its estimate, or every reason it has none.

    A priced answer carries no reason, and an unpriced answer over some usage at least one; an answer over no usage at
    all carries neither, which the cost selection reads as no usage.
    """

    estimate: cost_evidence.CostContribution | None = None
    unpriced: tuple[UnpricedReason, ...] = ()

    @classmethod
    def refused(cls, models: Iterable[str], reasons: Iterable[str]) -> Pricing:
        """The usage of each of `models` unpriced for each of `reasons`, every pair once and in order."""
        pairs = itertools.product(models, reasons)
        return cls(None, _ordered(itertools.starmap(UnpricedReason, pairs)))


def summed(pricings: Iterable[Pricing]) -> Pricing:
    """Several answers added: their estimates summed where every one is priced, else every reason any of them states.

    An estimate is never partial, so one unpriced answer leaves the sum unpriced, and the sum of none is no usage.
    """
    total: cost_evidence.CostContribution | None = None
    reasons: list[UnpricedReason] = []
    for pricing in pricings:
        reasons.extend(pricing.unpriced)
        if pricing.estimate is not None:
            total = pricing.estimate if total is None else total.plus(pricing.estimate)
    if reasons:
        return Pricing(None, _ordered(reasons))
    return Pricing(total)


def unrated(rates: protocol.RateMap, bucket: protocol.TokenBucket) -> tuple[str, ...]:
    """Why `bucket` has no amount at `rates`: a reason for each class it charges that they publish no rate for.

    A class the bucket reports no tokens of costs nothing, so it needs no rate.
    """
    charged = {token_class for token_class, count in bucket.items() if count}
    missing = charged - rates.keys()
    named = {_CLASS_REASONS.get(token_class, UNRATED_TOKEN_CLASS) for token_class in missing}
    return tuple(sorted(named))


def recorded_reasons(record: Mapping[str, Any]) -> tuple[UnpricedReason, ...]:
    """The reasons one serialized usage record states, each once and in order; none where it states none."""
    return stated_reasons(record.get(UNPRICED_REASONS))


def stated_reasons(raw: Any) -> tuple[UnpricedReason, ...]:
    """The reasons a serialized `unpriced_reasons` value states, each once and in order.

    An entry this vocabulary does not write is no reason, and a value that is no list states none.
    """
    if not isinstance(raw, list):
        return ()
    read = (UnpricedReason.from_dict(entry) for entry in raw)
    return _ordered(reason for reason in read if reason is not None)


def _ordered(reasons: Iterable[UnpricedReason]) -> tuple[UnpricedReason, ...]:
    return tuple(sorted(set(reasons)))
