# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Resilient JSONL decoding and shared usage value helpers."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from orchestrator.observability.usage import cost_evidence, protocol, token_evidence


def iter_events(stdout: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            decoded = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            events.append(decoded)
    return events


def token_count(raw_count: Any) -> int:
    """The count a raw usage field reports, zero when it reports none."""
    return token_evidence.reported_count(raw_count) or 0


def walk_objects(node: Any) -> Iterable[dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for child in node.values():
            yield from walk_objects(child)
    elif isinstance(node, list):
        for child in node:
            yield from walk_objects(child)


def coerce_reported_cost(raw_cost: Any) -> float | None:
    if isinstance(raw_cost, (int, float)):
        return float(raw_cost)
    if not isinstance(raw_cost, str):
        return None
    try:
        return float(raw_cost)
    except ValueError:
        return None


def find_last_reported_cost(events: list[dict[str, Any]]) -> float | None:
    last_cost: float | None = None
    for event in events:
        for payload in walk_objects(event):
            reported_cost = coerce_reported_cost(payload.get("total_cost_usd"))
            if reported_cost is not None:
                last_cost = reported_cost
    return last_cost


def dedup_models(models: Iterable[str]) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for model in models:
        if model and model != protocol.UNKNOWN and model not in seen:
            seen[model] = None
    return tuple(seen)


def select_cost(
    reported: float | None,
    estimated: cost_evidence.CostContribution | None,
    has_usage: bool,
) -> cost_evidence.CostEvidence:
    """A CLI-reported amount, an explicit zero included, wins over any estimate; unpriced usage states no amount."""
    if reported is not None:
        return cost_evidence.CostEvidence(
            cost_evidence.COMPLETE,
            (cost_evidence.CostContribution(cost_evidence.CLI_REPORTED, reported),),
        )
    if estimated is not None:
        return cost_evidence.CostEvidence(cost_evidence.COMPLETE, (estimated,))
    if not has_usage:
        return cost_evidence.CostEvidence(cost_evidence.NO_USAGE)
    return cost_evidence.CostEvidence(cost_evidence.INCOMPLETE)
