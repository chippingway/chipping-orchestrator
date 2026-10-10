# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Claude output settlement: the final output count of every API message a run printed.

The output count on a message's `assistant` frames is the one it started with. A lead-thread message is settled by the
`message_delta` closing it. A subagent prints no stream events: the message that closes it prints no frame at all,
only the usage its hand-back carries, and the final count of any earlier subagent message is printed nowhere. What
the `result` frame's `modelUsage` reports for a model beyond every count the stream printed is what those earlier
messages produced together, so it settles one only when it is the model's sole open message, and only when the
model's input and cache counts in `modelUsage` are exactly the ones the stream printed -- the evidence that it covers
these messages and no others. Several open messages share a total no frame splits, so each keeps its start count.

A stream with no `message_delta` -- printed without partial messages -- settles nothing: every message keeps the count
its last frame carries, and neither hand-backs nor `modelUsage` are read.

Only output counts are settled. Input and cache counts stay the ones the `assistant` frames carry, and a hand-back's
row carries its output count alone, so a run's input and cache counts leave out the message closing a subagent. The
run aggregate and the per-turn builder settle through the same `ClaudeSettlement`, so the turns sum to the run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from orchestrator.observability.usage import (
    claude_rows,
    claude_summary,
    event_stream,
    model_names,
    protocol,
)


def subagent_message_id(event: dict[str, Any]) -> str | None:
    """The id of a message a subagent printed: its `assistant` frames name the call that launched the subagent."""
    if event.get(protocol.TYPE) != protocol.ASSISTANT:
        return None
    message = event.get(protocol.MESSAGE)
    if not event.get("parent_tool_use_id") or not isinstance(message, dict):
        return None
    return model_names.nonempty_string(message.get(protocol.ID))


def model_usage_counts(event: dict[str, Any]) -> dict[str, protocol.TokenBucket]:
    """The per-model totals a `result` frame's `modelUsage` reports, as usage buckets."""
    if event.get(protocol.TYPE) != protocol.RESULT_KEY:
        return {}
    model_usage = event.get("modelUsage")
    if not isinstance(model_usage, dict):
        return {}
    return {
        model: {
            protocol.INPUT: event_stream.token_count(totals.get("inputTokens")),
            protocol.CACHE_WRITE_FIVE_MIN: event_stream.token_count(totals.get("cacheCreationInputTokens")),
            protocol.CACHE_WRITE_ONE_HOUR: 0,
            protocol.CACHE_READ: event_stream.token_count(totals.get("cacheReadInputTokens")),
            protocol.OUTPUT: event_stream.token_count(totals.get("outputTokens")),
        }
        for model, totals in model_usage.items()
        if isinstance(totals, dict)
    }


def input_and_cache(bucket: protocol.TokenBucket) -> tuple[int, int, int]:
    """Input, cache-read, and cache-write counts, the cache-write TTL buckets summed as `modelUsage` reports them."""
    return (
        bucket[protocol.INPUT],
        bucket[protocol.CACHE_READ],
        bucket[protocol.CACHE_WRITE_FIVE_MIN] + bucket[protocol.CACHE_WRITE_ONE_HOUR],
    )


def with_output(usage_row: claude_rows.ClaudeUsageRow, output: int) -> claude_rows.ClaudeUsageRow:
    ordinal, model, record = usage_row
    return ordinal, model, {**record, protocol.OUTPUT: output}


def usage_row_index(usage_row: claude_rows.ClaudeUsageRow) -> int:
    return usage_row[0]


@dataclass
class ClaudeSettlement:
    """What a stream shows of each message's final output count, gathered as its frames arrive."""

    final_outputs: dict[str, int] = field(default_factory=dict)
    subagent_messages: set[str] = field(default_factory=set)
    handbacks: dict[str, claude_rows.ClaudeUsageRow] = field(default_factory=dict)
    model_usage: dict[str, protocol.TokenBucket] = field(default_factory=dict)

    def add_event(self, index: int, event: dict[str, Any]) -> None:
        closed = claude_rows.claude_message_delta_output(event)
        if closed is not None:
            self.final_outputs[closed[0]] = closed[1]
        subagent_message = subagent_message_id(event)
        if subagent_message is not None:
            self.subagent_messages.add(subagent_message)
        handback = claude_rows.claude_handback_usage_row(index, event)
        if handback is not None:
            self.handbacks[handback[0]] = handback[1]
        self.model_usage = model_usage_counts(event) or self.model_usage

    def settled_rows(
        self,
        rows_by_id: dict[str, claude_rows.ClaudeUsageRow],
    ) -> list[claude_rows.ClaudeUsageRow]:
        """The message rows in order, each output count settled to the final one the stream shows."""
        settled = {
            message_id: self._closed(message_id, usage_row)
            for message_id, usage_row in rows_by_id.items()
        }
        models = dict.fromkeys(usage_row[1] for usage_row in settled.values())
        for model in models:
            self._reconcile(model, settled)
        return sorted(settled.values(), key=usage_row_index)

    def handback_rows(self) -> list[claude_rows.ClaudeUsageRow]:
        """One row per subagent hand-back, holding the output count of the message that closed the subagent.

        A stream no `message_delta` closes a message in -- printed without partial messages -- keeps the counts its
        frames carry and nothing more, so it has none.
        """
        if not self.final_outputs:
            return []
        usage_rows = []
        for ordinal, model, record in self.handbacks.values():
            output_only = dict.fromkeys(record, 0)
            output_only[protocol.OUTPUT] = record[protocol.OUTPUT]
            usage_rows.append((ordinal, model, output_only))
        return usage_rows

    def _closed(self, message_id: str, usage_row: claude_rows.ClaudeUsageRow) -> claude_rows.ClaudeUsageRow:
        final_output = self.final_outputs.get(message_id)
        return usage_row if final_output is None else with_output(usage_row, final_output)

    def _reconcile(self, model: str, settled: dict[str, claude_rows.ClaudeUsageRow]) -> None:
        open_message = self._sole_open_message(model, settled)
        unprinted = None if open_message is None else self._unprinted_output(model, settled)
        if open_message is None or unprinted is None:
            return
        start = settled[open_message][2][protocol.OUTPUT]
        settled[open_message] = with_output(settled[open_message], start + unprinted)

    def _sole_open_message(self, model: str, settled: dict[str, claude_rows.ClaudeUsageRow]) -> str | None:
        # What `modelUsage` leaves over belongs to one subagent message only
        # while it is the model's one open message in a stream that closes
        # messages at all: an open lead-thread message, or a second open
        # message, would claim a share no frame attributes.
        open_messages = [
            message_id
            for message_id, usage_row in settled.items()
            if usage_row[1] == model and message_id not in self.final_outputs
        ]
        if not self.final_outputs or len(open_messages) != 1:
            return None
        return open_messages[0] if open_messages[0] in self.subagent_messages else None

    def _unprinted_output(self, model: str, settled: dict[str, claude_rows.ClaudeUsageRow]) -> int | None:
        """What `modelUsage` reports beyond every printed output count, if it covers exactly what was printed.

        A `modelUsage` that also covers usage no frame of this stream printed shows it in its input and cache
        counts, and leaves nothing to attribute.
        """
        reported = self.model_usage.get(model)
        if reported is None:
            return None
        printed_rows = [*settled.values(), *self.handbacks.values()]
        printed = claude_summary.aggregate_by_model(printed_rows).per_model[model]
        unprinted = reported[protocol.OUTPUT] - printed[protocol.OUTPUT]
        if unprinted < 0 or input_and_cache(reported) != input_and_cache(printed):
            return None
        return unprinted


def claude_usage_records(
    events: list[dict[str, Any]],
) -> list[claude_rows.ClaudeUsageRow]:
    by_id: dict[str, claude_rows.ClaudeUsageRow] = {}
    settlement = ClaudeSettlement()
    for index, event in enumerate(events):
        settlement.add_event(index, event)
        identified = claude_rows.claude_assistant_usage_row(index, event)
        if identified is not None:
            by_id[identified[0]] = identified[1]
    if not by_id:
        return claude_rows.claude_result_usage_records(events)
    return sorted(
        [*settlement.settled_rows(by_id), *settlement.handback_rows()],
        key=usage_row_index,
    )
