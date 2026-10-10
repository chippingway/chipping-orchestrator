# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Build Claude per-turn usage aligned with trajectory steps.

A turn is one API message, keyed the way the trajectory steps it produced are. Its output count is settled by the
same `claude_settlement.ClaudeSettlement` the run aggregate reads, so the turns sum to the run.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from orchestrator.observability.usage import (
    claude_rows,
    claude_settlement,
    model_names,
    prices,
    protocol,
    trajectory_claude_stream,
)
from orchestrator.observability.usage.trajectory_models import TurnUsage

TurnUsageRow = tuple[int, str, protocol.TokenBucket]


@dataclass
class ClaudeTurnUsageBuilder:
    turn_index: dict[str, int] = field(default_factory=dict)
    by_key: dict[str, TurnUsageRow] = field(default_factory=dict)
    settlement: claude_settlement.ClaudeSettlement = field(default_factory=claude_settlement.ClaudeSettlement)

    def add_event(self, index: int, event: dict[str, Any]) -> None:
        self.settlement.add_event(index, event)
        if event.get(protocol.TYPE) != protocol.ASSISTANT:
            return
        message = event.get(protocol.MESSAGE)
        if not isinstance(message, dict):
            return
        key = trajectory_claude_stream.turn_key(index, event)
        turn = self.turn_index.setdefault(key, len(self.turn_index))
        usage = message.get(protocol.USAGE)
        if isinstance(usage, dict):
            self.by_key[key] = (
                turn,
                model_names.claude_model_name(event),
                claude_rows.claude_usage_record(usage),
            )

    def build(self) -> tuple[TurnUsage, ...]:
        ordered_rows = self.settlement.settled_rows(self.by_key)
        # The message closing a subagent printed no frame, so no step names it:
        # its turn is numbered after every turn the steps were stamped with.
        ordered_rows.extend(
            (len(self.turn_index) + position, model, record)
            for position, (_, model, record) in enumerate(self.settlement.handback_rows())
        )
        return tuple(turn_usage_from_row(row) for row in ordered_rows)


def turn_usage_from_row(usage_row: TurnUsageRow) -> TurnUsage:
    turn, model, record = usage_row
    estimated_cost = prices.claude_estimate_cost(model, record)
    return TurnUsage(
        turn=turn,
        model=model,
        input_tokens=record[protocol.INPUT],
        output_tokens=record[protocol.OUTPUT],
        cache_read_tokens=record[protocol.CACHE_READ],
        cache_write_tokens=(record[protocol.CACHE_WRITE_FIVE_MIN] + record[protocol.CACHE_WRITE_ONE_HOUR]),
        cost_usd=estimated_cost,
        cost_source="unknown-price" if estimated_cost is None else "estimated",
    )


def claude_turn_usage(
    events: Iterable[dict[str, Any]],
) -> tuple[TurnUsage, ...]:
    builder = ClaudeTurnUsageBuilder()
    for index, event in enumerate(events):
        builder.add_event(index, event)
    return builder.build()
