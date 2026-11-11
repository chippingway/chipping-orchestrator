# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The `request_usage` field of a trajectory record: what it charges the record budget, and what it keeps.

The coverage summary and the aggregate checkpoints are bounded by the collector and always kept, so they are charged
with the record's other summaries, before any array. The markers and then the samples are drawn after the per-turn
usage and the source item accounting and before the steps, each entry charged its whole serialized size and kept as a
prefix in source order, so a run whose budget ran out keeps its earliest requests and says how many it lost: the
summary counts the observed and retained entries, and anything dropped is a `storage-budget` gap. The summary is
charged as written when nothing is dropped; one reporting dropped entries is kept whole at the few bytes more that
costs.

Every string a collector bounded -- identities, model names, step kinds -- is a counter's correlation metadata rather
than agent text, and is still passed through the secret redactor before it is charged, so the field never carries a
secret-shaped value another field would have masked.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from orchestrator.observability.analytics.trajectories import models, sanitize
from orchestrator.observability.usage.request_coverage import RequestUsage

COVERAGE = "coverage"
CHECKPOINTS = "checkpoints"
MARKERS = "markers"
SAMPLES = "samples"


def checkpoints(request_usage: RequestUsage, redact: sanitize.Redactor) -> list[dict[str, Any]]:
    """The collection's aggregate checkpoints, bounded by the collector and redacted like every other entry."""
    return sanitize.redact_tree([checkpoint.to_dict() for checkpoint in request_usage.checkpoints], redact)


def request_summary(
    request_usage: RequestUsage | None,
    redact: sanitize.Redactor,
) -> dict[str, Any]:
    """The always-kept part of the field -- its coverage and checkpoints -- as charged before any array."""
    if request_usage is None:
        return {}
    return {
        COVERAGE: request_usage.summary(len(request_usage.observations), len(request_usage.markers)),
        CHECKPOINTS: checkpoints(request_usage, redact),
    }


def drawn_entries(
    entries: Iterable[Any],
    budget: models.TrajectoryBudget,
    redact: sanitize.Redactor,
) -> list[dict[str, Any]]:
    """The prefix of `entries` the budget has room for, each redacted and then charged its serialized size."""
    kept: list[dict[str, Any]] = []
    for entry in entries:
        entry_dict = sanitize.redact_tree(entry.to_dict(), redact)
        if not budget.include(entry_dict):
            break
        kept.append(entry_dict)
    return kept


def bounded_request_usage(
    request_usage: RequestUsage | None,
    budget: models.TrajectoryBudget,
    redact: sanitize.Redactor,
) -> dict[str, Any] | None:
    """The field as one record keeps it: the summary whole, then the markers and samples the budget had room for.

    An empty part is left out, so a run that printed no marker or checkpoint carries no key for it; the coverage
    is always there.
    """
    if request_usage is None:
        return None
    markers = drawn_entries(request_usage.markers, budget, redact)
    samples = drawn_entries(request_usage.observations, budget, redact)
    kept = {
        COVERAGE: request_usage.summary(len(samples), len(markers)),
        CHECKPOINTS: checkpoints(request_usage, redact),
        MARKERS: markers,
        SAMPLES: samples,
    }
    return {name: part for name, part in kept.items() if part}
