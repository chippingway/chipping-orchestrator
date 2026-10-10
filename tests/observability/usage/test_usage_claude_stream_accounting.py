# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where a captured Claude stream-json run keeps each token count."""

import unittest

from orchestrator.observability.usage import event_stream
from tests.observability.usage import (
    usage_claude_stream_capture as _capture,
    usage_test_values as _usage_cases,
)

_ASSISTANT = "assistant"
_MESSAGE_START = "message_start"
_MESSAGE_DELTA = "message_delta"
_MESSAGE = "message"
_API_MESSAGE_ID = "api_message_id"
_TOOL_USE_RESULT = "tool_use_result"

FrameCounts = dict[str, set[_capture.TokenCounts]]


def _counts(usage: dict) -> _capture.TokenCounts:
    return _capture.TokenCounts(
        usage[_usage_cases.INPUT_TOKENS_FIELD],
        usage["cache_read_input_tokens"],
        usage["cache_creation_input_tokens"],
        usage[_usage_cases.OUTPUT_TOKENS_FIELD],
    )


def _located_counts(event: dict) -> tuple[str, str, _capture.TokenCounts] | None:
    """The message a frame belongs to, the kind of frame it is, and the counts it carries."""
    frame_type = event.get(_usage_cases.TYPE_FIELD)
    if frame_type == _ASSISTANT:
        message = event[_MESSAGE]
        return message[_usage_cases.IDENTIFIER_FIELD], _ASSISTANT, _counts(message[_usage_cases.USAGE_FIELD])
    stream_event = event.get("event") if frame_type == "stream_event" else None
    event_type = stream_event.get(_usage_cases.TYPE_FIELD) if stream_event else None
    if event_type == _MESSAGE_START:
        return event[_API_MESSAGE_ID], _MESSAGE_START, _counts(stream_event[_MESSAGE][_usage_cases.USAGE_FIELD])
    if event_type == _MESSAGE_DELTA:
        return event[_API_MESSAGE_ID], _MESSAGE_DELTA, _counts(stream_event[_usage_cases.USAGE_FIELD])
    return None


def _counts_by_message(stdout: str) -> dict[str, FrameCounts]:
    """Each message's distinct counts, keyed by the kind of frame that carried them."""
    by_message: dict[str, FrameCounts] = {}
    for event in event_stream.iter_events(stdout):
        located = _located_counts(event)
        if located is not None:
            frame_counts = by_message.setdefault(located[0], {})
            frame_counts.setdefault(located[1], set()).add(located[2])
    return by_message


def _result_figures(stdout: str) -> tuple[object, ...]:
    """The `result` frame's thread usage, model usage, reported cost, model cost, and turn count."""
    terminal = next(
        event
        for event in event_stream.iter_events(stdout)
        if event.get(_usage_cases.TYPE_FIELD) == "result"
    )
    model_usage = terminal["modelUsage"][_capture.MODEL]
    return (
        _counts(terminal[_usage_cases.USAGE_FIELD]),
        _capture.TokenCounts(
            model_usage["inputTokens"],
            model_usage["cacheReadInputTokens"],
            model_usage["cacheCreationInputTokens"],
            model_usage["outputTokens"],
        ),
        terminal["total_cost_usd"],
        model_usage["costUSD"],
        terminal["num_turns"],
    )


def _handback_counts(stdout: str) -> list[_capture.TokenCounts]:
    """The usage each subagent hand-back carries on the lead thread's `tool_result` frame."""
    return [
        _counts(event[_TOOL_USE_RESULT][_usage_cases.USAGE_FIELD])
        for event in event_stream.iter_events(stdout)
        if _TOOL_USE_RESULT in event
    ]


class ClaudeStreamAccountingTest(unittest.TestCase):
    """The counts `usage_claude_stream_capture` documents are the ones its raw lines carry.

    A message's `message_start` event and every `assistant` frame it prints hold its counts at the start; only
    its `message_delta`, joined through the wrapper's `api_message_id`, holds its final output count. The
    `result` frame's `usage` sums the lead thread's final counts, while `modelUsage` and the reported cost
    take the subagent in as well.
    """

    def test_message_delta_holds_each_final_count(self) -> None:
        # A subagent's message prints no stream events, so the start counts on its `assistant` frame are all
        # the stream holds of it.
        runs = (
            (_capture.MAIN_RUN_STDOUT, _capture.MAIN_RUN_MESSAGES, ()),
            (
                _capture.SUBAGENT_RUN_STDOUT,
                _capture.SUBAGENT_RUN_LEAD_MESSAGES,
                _capture.SUBAGENT_RUN_SUBAGENT_MESSAGES,
            ),
        )
        for stdout, lead_messages, subagent_messages in runs:
            expected = {
                message.message_id: {
                    _MESSAGE_START: {message.start},
                    _ASSISTANT: {message.start},
                    _MESSAGE_DELTA: {message.final},
                }
                for message in lead_messages
            }
            expected.update({message.message_id: {_ASSISTANT: {message.start}} for message in subagent_messages})
            self.assertEqual(_counts_by_message(stdout), expected)

    def test_result_totals_sum_the_final_counts(self) -> None:
        # The subagent's first message has no final output count in any frame, so the documented one is what
        # `modelUsage` leaves after the lead thread and the hand-back; its input and cache counts, read from
        # its `assistant` frame, have to close the same sum.
        self.assertEqual(
            _result_figures(_capture.MAIN_RUN_STDOUT),
            (
                _capture.MAIN_RUN_TOTALS,
                _capture.MAIN_RUN_TOTALS,
                _capture.MAIN_RUN_COST_USD,
                _capture.MAIN_RUN_COST_USD,
                _capture.MAIN_RUN_NUM_TURNS,
            ),
        )
        self.assertEqual(
            _result_figures(_capture.SUBAGENT_RUN_STDOUT),
            (
                _capture.SUBAGENT_RUN_LEAD_TOTALS,
                _capture.SUBAGENT_RUN_MODEL_TOTALS,
                _capture.SUBAGENT_RUN_COST_USD,
                _capture.SUBAGENT_RUN_COST_USD,
                _capture.SUBAGENT_RUN_NUM_TURNS,
            ),
        )
        self.assertEqual(_handback_counts(_capture.SUBAGENT_RUN_STDOUT), [_capture.SUBAGENT_RUN_HANDBACK])
        self.assertEqual(
            _capture.summed(message.final for message in _capture.MAIN_RUN_MESSAGES),
            _capture.MAIN_RUN_TOTALS,
        )
        lead_finals = [message.final for message in _capture.SUBAGENT_RUN_LEAD_MESSAGES]
        self.assertEqual(_capture.summed(lead_finals), _capture.SUBAGENT_RUN_LEAD_TOTALS)
        subagent_finals = [message.final for message in _capture.SUBAGENT_RUN_SUBAGENT_MESSAGES]
        self.assertEqual(
            _capture.summed([*lead_finals, *subagent_finals, _capture.SUBAGENT_RUN_HANDBACK]),
            _capture.SUBAGENT_RUN_MODEL_TOTALS,
        )
