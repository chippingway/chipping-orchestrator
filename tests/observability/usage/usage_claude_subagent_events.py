# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Claude stream-json builders for runs that launch a subagent: its frames, its hand-back, and `modelUsage`."""

from tests.observability.usage import (
    usage_claude_events as _claude,
    usage_jsonl_helpers as _jsonl,
    usage_test_values as _usage_cases,
)

LEAD_INPUT_TOKENS = 10
SUBAGENT_INPUT_TOKENS = 2


def lead_assistant(model: str) -> dict:
    """The lead thread's message, opening with one output token; a `message_delta` may close it."""
    return _claude.assistant(
        id=_usage_cases.CLAUDE_TURN_ID,
        model=model,
        content_blocks=[_jsonl.text(_usage_cases.GREETING_TEXT)],
        usage=_claude.usage(input=LEAD_INPUT_TOKENS, output=1),
    )


def subagent_assistant(message_id: str, model: str) -> dict:
    """A subagent's message, opening with one output token, under the call that launched the subagent."""
    frame = _claude.assistant(
        id=message_id,
        model=model,
        content_blocks=[_jsonl.text(message_id)],
        usage=_claude.usage(input=SUBAGENT_INPUT_TOKENS, output=1),
    )
    frame["parent_tool_use_id"] = _usage_cases.TOOL_USE_A_ID
    return frame


def tool_result_frame(tool_use_result: dict, tool_use_id: str | None = None) -> dict:
    """A lead-thread `user` frame carrying `tool_use_result`, as the result of `tool_use_id` when one is named."""
    frame = {_usage_cases.TYPE_FIELD: "user", "tool_use_result": tool_use_result}
    if tool_use_id is not None:
        frame["message"] = {"content": [_jsonl.tool_result(tool_use_id, _usage_cases.FINAL_OUTPUT)]}
    return frame


def handback(tool_use_id: str, model: str, *, output: int) -> dict:
    """The return of the subagent call `tool_use_id`, carrying the usage of the message that closed the subagent."""
    return tool_result_frame(
        {
            "agentId": "agent_a",
            "resolvedModel": model,
            _usage_cases.USAGE_FIELD: _claude.usage(input=SUBAGENT_INPUT_TOKENS, output=output),
        },
        tool_use_id,
    )


def model_totals(*, input_tokens: int, output_tokens: int) -> dict:
    """One model's `modelUsage` entry, for a run with no cache traffic."""
    return {
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "cacheReadInputTokens": 0,
        "cacheCreationInputTokens": 0,
    }
