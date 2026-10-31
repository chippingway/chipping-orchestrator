# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Claude usage-frame decoding: the usage block each frame carries, and the message it belongs to.

Every `assistant` frame repeats the usage its message's `message_start` event opened with, so its output count is the
one at the start of the message. Two other frames carry final counts: the `message_delta` stream event that closes a
lead-thread message, naming it through its wrapper's `api_message_id`, and a subagent's hand-back, the lead thread's
`tool_result` whose `tool_use_result.usage` is the usage of the message that closed the subagent. Which count a
message keeps is settled on `claude_settlement`; the lifetime each cache write counts under, and the scope of each row,
are defined on `claude_requests`.
"""

from __future__ import annotations

from typing import Any

from orchestrator.observability.usage import (
    claude_requests,
    model_names,
    protocol,
    token_evidence,
)

_STREAM_EVENT = "stream_event"
_MESSAGE_DELTA = "message_delta"
_TOOL_USE_RESULT = "tool_use_result"
_MESSAGE_CONTENT: protocol.ModelPath = (protocol.MESSAGE, "content")


def claude_usage_row(
    ordinal: int,
    model: str,
    usage: dict[str, Any],
    scope: str = claude_requests.MESSAGE,
) -> claude_requests.ClaudeUsageRow:
    """One usage block as a row: the counts it reports by token class -- a class it reports no count for has no key.

    Its cache writes count under the lifetimes `claude_requests.cache_writes` reads, and a split contradicting the
    aggregate marks the row. A missing class sums as zero and costs nothing, while its absence is what tells it apart
    from a reported zero and, for an input or cache class, leaves the request's prompt size unestablished.
    """
    writes, conflicting = claude_requests.cache_writes(usage)
    counts = token_evidence.reported_counts({
        protocol.INPUT: token_evidence.first_count(usage.get(protocol.INPUT_TOKENS), usage.get("prompt_tokens")),
        **writes,
        protocol.CACHE_READ: token_evidence.first_count(
            usage.get("cache_read_input_tokens"), usage.get("cached_input_tokens"), usage.get("cache_read_tokens"),
        ),
        protocol.OUTPUT: token_evidence.first_count(usage.get(protocol.OUTPUT_TOKENS), usage.get("completion_tokens")),
    })
    return claude_requests.ClaudeUsageRow(ordinal, model, counts, scope, conflicting)


def claude_assistant_usage_row(
    index: int,
    event: dict[str, Any],
) -> tuple[str, claude_requests.ClaudeUsageRow] | None:
    if event.get(protocol.TYPE) != protocol.ASSISTANT:
        return None
    message = event.get(protocol.MESSAGE)
    if not isinstance(message, dict):
        return None
    usage = message.get(protocol.USAGE)
    if not isinstance(usage, dict):
        return None
    message_id = message.get(protocol.ID) or event.get("request_id")
    if not message_id:
        message_id = str(index)
    return (
        str(message_id),
        claude_usage_row(index, model_names.claude_model_name(event), usage),
    )


def claude_result_usage_row(
    index: int,
    event: dict[str, Any],
) -> claude_requests.ClaudeUsageRow | None:
    """The `result` frame's usage, a total over the lead thread's requests that establishes none of their sizes."""
    if event.get(protocol.TYPE) != protocol.RESULT_KEY:
        return None
    usage = event.get(protocol.USAGE)
    if not isinstance(usage, dict):
        return None
    return claude_usage_row(index, model_names.claude_model_name(event), usage, claude_requests.RESULT_TOTAL)


def claude_message_delta_output(event: dict[str, Any]) -> tuple[str, int] | None:
    """The id of the message a `message_delta` stream event closes, and the final output count it closes it with."""
    if event.get(protocol.TYPE) != _STREAM_EVENT:
        return None
    stream_event = event.get("event")
    if not isinstance(stream_event, dict) or stream_event.get(protocol.TYPE) != _MESSAGE_DELTA:
        return None
    usage = stream_event.get(protocol.USAGE)
    reported_output = usage.get(protocol.OUTPUT_TOKENS) if isinstance(usage, dict) else None
    final_output = token_evidence.reported_count(reported_output)
    message_id = event.get("api_message_id")
    if final_output is None or not message_id:
        return None
    return str(message_id), final_output


def claude_handback_usage_row(
    index: int,
    event: dict[str, Any],
) -> tuple[str, claude_requests.ClaudeUsageRow] | None:
    """The invocation a subagent hand-back answers, and the usage of the message that closed the subagent.

    A resumed subagent returns under the agent id it had before, so a hand-back is told apart by the call it
    answers; a frame naming no call stands on its own.
    """
    if event.get(protocol.TYPE) != "user":
        return None
    handback = event.get(_TOOL_USE_RESULT)
    if not isinstance(handback, dict):
        return None
    usage = handback.get(protocol.USAGE)
    agent_id = handback.get("agentId")
    if not isinstance(usage, dict) or not agent_id:
        return None
    model = model_names.nonempty_string(handback.get("resolvedModel")) or protocol.UNKNOWN
    invocation = claude_tool_result_id(event) or str(index)
    return invocation, claude_usage_row(index, model, usage)


def claude_tool_result_id(event: dict[str, Any]) -> str | None:
    """The `tool_use_id` of a frame's lone `tool_result` block: the invocation it returns from."""
    message_blocks = model_names.nested_value(event, _MESSAGE_CONTENT)
    if not isinstance(message_blocks, list):
        return None
    result_ids = [
        block.get("tool_use_id")
        for block in message_blocks
        if isinstance(block, dict) and block.get(protocol.TYPE) == "tool_result"
    ]
    if len(result_ids) != 1:
        return None
    return model_names.nonempty_string(result_ids[0])


def claude_result_usage_records(
    events: list[dict[str, Any]],
) -> list[claude_requests.ClaudeUsageRow]:
    usage_rows: list[claude_requests.ClaudeUsageRow] = []
    for index, event in enumerate(events):
        usage_row = claude_result_usage_row(index, event)
        if usage_row is not None:
            usage_rows.append(usage_row)
    return usage_rows
