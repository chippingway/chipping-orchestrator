# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Claude output settlement: the final output count of every API message a run printed.

The output count on a message's `assistant` frames is the one it started with. A lead-thread message is settled by the
`message_delta` closing it. A subagent prints no stream events: the message that closes it prints no frame at all,
only the usage its hand-back carries, and the final count of any earlier subagent message is printed nowhere. What
the `result` frame's `modelUsage` reports for a model beyond every count the stream printed is what those earlier
messages produced together, so it settles one only when it is the model's sole open message, only when it reports
every one of its input, cache, and output totals, and only when those input and cache counts are exactly the ones the
stream printed -- the evidence that it covers these messages and no others. Several open messages share a total no
frame splits, so each keeps its start count.

A stream with no `message_delta` -- printed without partial messages -- settles nothing: every message keeps the count
its last frame carries, and neither hand-backs nor `modelUsage` are read.

Only output counts are settled. Input and cache counts stay the ones the `assistant` frames carry, and a hand-back's
row carries its output count alone, so a run's input and cache counts leave out the message closing a subagent: its
`handback-output` scope says that row establishes no request's prompt. The run aggregate and the per-turn builder
settle through the same `ClaudeSettlement`, so the turns sum to the run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from operator import attrgetter
from typing import Any

from orchestrator.observability.usage import (
    claude_requests,
    claude_rows,
    claude_summary,
    model_names,
    protocol,
    token_evidence,
)

# The token class each `modelUsage` field totals; it reports cache writes as one count, with no lifetime split.
_MODEL_USAGE_FIELDS = (
    (protocol.INPUT, "inputTokens"),
    (protocol.CACHE_WRITE_UNKNOWN_LIFETIME, "cacheCreationInputTokens"),
    (protocol.CACHE_READ, "cacheReadInputTokens"),
    (protocol.OUTPUT, "outputTokens"),
)
_MODEL_USAGE_CLASSES = frozenset(token_class for token_class, _ in _MODEL_USAGE_FIELDS)


def subagent_message_id(event: dict[str, Any]) -> str | None:
    """The id of a message a subagent printed: its `assistant` frames name the call that launched the subagent."""
    if event.get(protocol.TYPE) != protocol.ASSISTANT:
        return None
    message = event.get(protocol.MESSAGE)
    if not event.get("parent_tool_use_id") or not isinstance(message, dict):
        return None
    return model_names.nonempty_string(message.get(protocol.ID))


def model_usage_counts(event: dict[str, Any]) -> dict[str, protocol.TokenBucket]:
    """The per-model totals a `result` frame's `modelUsage` reports, as usage buckets of the classes it reports."""
    if event.get(protocol.TYPE) != protocol.RESULT_KEY:
        return {}
    model_usage = event.get("modelUsage")
    if not isinstance(model_usage, dict):
        return {}
    return {
        model: token_evidence.reported_counts({
            token_class: token_evidence.reported_count(totals.get(field_name))
            for token_class, field_name in _MODEL_USAGE_FIELDS
        })
        for model, totals in model_usage.items()
        if isinstance(totals, dict)
    }


def input_and_cache(bucket: protocol.TokenBucket) -> tuple[int, int, int]:
    """Input, cache-read, and cache-write counts, the writes of every lifetime summed as `modelUsage` reports them."""
    return bucket[protocol.INPUT], bucket[protocol.CACHE_READ], claude_requests.cache_write_total(bucket)


usage_row_index = attrgetter("ordinal")


@dataclass
class ClaudeSettlement:
    """What a stream shows of each message's final output count, gathered as its frames arrive."""

    final_outputs: dict[str, int] = field(default_factory=dict)
    subagent_messages: set[str] = field(default_factory=set)
    handbacks: dict[str, claude_requests.ClaudeUsageRow] = field(default_factory=dict)
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
        rows_by_id: dict[str, claude_requests.ClaudeUsageRow],
    ) -> list[claude_requests.ClaudeUsageRow]:
        """The message rows in order, each output count settled to the final one the stream shows."""
        settled = {
            message_id: self._closed(message_id, usage_row)
            for message_id, usage_row in rows_by_id.items()
        }
        models = dict.fromkeys(usage_row.model for usage_row in settled.values())
        for model in models:
            self._reconcile(model, settled)
        return sorted(settled.values(), key=usage_row_index)

    def handback_rows(self) -> list[claude_requests.ClaudeUsageRow]:
        """One row per subagent hand-back, holding the output count of the message that closed the subagent.

        A stream no `message_delta` closes a message in -- printed without partial messages -- keeps the counts its
        frames carry and nothing more, so it has none.
        """
        if not self.final_outputs:
            return []
        # A run's input and cache counts are its frames', so a hand-back's row
        # states none of them -- no class at all, rather than a zero -- and so
        # carries no cache-write evidence to conflict either.
        return [
            claude_requests.ClaudeUsageRow(
                handback.ordinal,
                handback.model,
                token_evidence.reported_counts({protocol.OUTPUT: handback.counts.get(protocol.OUTPUT)}),
                claude_requests.HANDBACK_OUTPUT,
            )
            for handback in self.handbacks.values()
        ]

    def _closed(self, message_id: str, usage_row: claude_requests.ClaudeUsageRow) -> claude_requests.ClaudeUsageRow:
        final_output = self.final_outputs.get(message_id)
        return usage_row if final_output is None else usage_row.with_output(final_output)

    def _reconcile(self, model: str, settled: dict[str, claude_requests.ClaudeUsageRow]) -> None:
        open_message = self._sole_open_message(model, settled)
        unprinted = None if open_message is None else self._unprinted_output(model, settled)
        if open_message is None or unprinted is None:
            return
        start = settled[open_message].counts.get(protocol.OUTPUT, 0)
        settled[open_message] = settled[open_message].with_output(start + unprinted)

    def _sole_open_message(self, model: str, settled: dict[str, claude_requests.ClaudeUsageRow]) -> str | None:
        # What `modelUsage` leaves over belongs to one subagent message only
        # while it is the model's one open message in a stream that closes
        # messages at all: an open lead-thread message, or a second open
        # message, would claim a share no frame attributes.
        open_messages = [
            message_id
            for message_id, usage_row in settled.items()
            if usage_row.model == model and message_id not in self.final_outputs
        ]
        if not self.final_outputs or len(open_messages) != 1:
            return None
        return open_messages[0] if open_messages[0] in self.subagent_messages else None

    def _unprinted_output(self, model: str, settled: dict[str, claude_requests.ClaudeUsageRow]) -> int | None:
        """What `modelUsage` reports beyond every printed output count, if it covers exactly what was printed.

        A `modelUsage` that also covers usage no frame of this stream printed shows it in its input and cache
        counts, and leaves nothing to attribute. One missing any of the totals the check reads attributes nothing
        either: an absent input or cache total establishes no coverage, and an absent output total no remainder, so
        the open message's output stays as its frames left it.
        """
        reported = self.model_usage.get(model)
        if reported is None or not _MODEL_USAGE_CLASSES <= reported.keys():
            return None
        printed_rows = [*settled.values(), *self.handbacks.values()]
        printed = claude_summary.aggregate_by_model(printed_rows).per_model[model]
        unprinted = reported[protocol.OUTPUT] - printed[protocol.OUTPUT]
        if unprinted < 0 or input_and_cache(reported) != input_and_cache(printed):
            return None
        return unprinted


def claude_usage_records(
    events: list[dict[str, Any]],
) -> list[claude_requests.ClaudeUsageRow]:
    by_id: dict[str, claude_requests.ClaudeUsageRow] = {}
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
