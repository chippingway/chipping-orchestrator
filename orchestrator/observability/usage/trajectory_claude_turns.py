# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Build Claude per-turn usage aligned with trajectory steps.

A turn is one API message, keyed the way the trajectory steps it produced are. Its output count is settled by the
same `claude_settlement.ClaudeSettlement` the run aggregate reads, so the turns sum to the run. Each turn is priced on
its own as an Anthropic API estimate, through the same `claude_requests.ClaudeUsageRow.estimate` the run estimate sums
its rows with, so a priced run's turns sum to its estimate; and each observes the token classes its own row reported.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Any

from orchestrator.observability.usage import (
    claude_requests,
    claude_rows,
    claude_settlement,
    claude_summary,
    event_stream,
    model_names,
    protocol,
    trajectory_claude_stream,
)
from orchestrator.observability.usage.trajectory_models import TurnUsage


@dataclass
class ClaudeTurnUsageBuilder:
    turn_index: dict[str, int] = field(default_factory=dict)
    by_key: dict[str, claude_requests.ClaudeUsageRow] = field(default_factory=dict)
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
            self.by_key[key] = claude_rows.claude_usage_row(turn, model_names.claude_model_name(event), usage)

    def build(self) -> tuple[TurnUsage, ...]:
        ordered_rows = self.settlement.settled_rows(self.by_key)
        # The message closing a subagent printed no frame, so no step names it:
        # its turn is numbered after every turn the steps were stamped with.
        ordered_rows.extend(
            replace(handback, ordinal=len(self.turn_index) + position)
            for position, handback in enumerate(self.settlement.handback_rows())
        )
        return tuple(turn_usage_from_row(row) for row in ordered_rows)


def turn_usage_from_row(usage_row: claude_requests.ClaudeUsageRow) -> TurnUsage:
    """One turn's usage, priced on its own as an API estimate: a run-level reported cost never reaches a turn.

    Its token evidence observes the classes its own row reported, so a hand-back turn observes its output alone, and
    its estimate prices the row as its scope allows, so a hand-back turn on a request-tiered model has none.
    """
    counts = usage_row.counts
    cost = event_stream.select_cost(None, usage_row.estimate(), has_usage=True)
    return TurnUsage(
        turn=usage_row.ordinal,
        model=usage_row.model,
        input_tokens=counts.get(protocol.INPUT, 0),
        output_tokens=counts.get(protocol.OUTPUT, 0),
        cache_read_tokens=counts.get(protocol.CACHE_READ, 0),
        cache_write_tokens=claude_requests.cache_write_total(counts),
        cost_usd=cost.complete_usd,
        cost_source=cost.cost_source,
        cost_evidence=cost,
        token_evidence=claude_summary.token_evidence_of((counts,)),
    )


def claude_turn_usage(
    events: Iterable[dict[str, Any]],
) -> tuple[TurnUsage, ...]:
    builder = ClaudeTurnUsageBuilder()
    for index, event in enumerate(events):
        builder.add_event(index, event)
    return builder.build()
