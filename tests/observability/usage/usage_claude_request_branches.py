# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Claude stream-json lines for subagent branches and process reports, in the shapes Claude Code 2.1.295 prints.

A subagent prints its `assistant` frames under the call that launched it and the subagent's `agent_id`, but no stream
events; the lead thread's hand-back for that call carries, under `tool_use_result`, the subagent's `agentId`, the model
that ran it, and the usage of the message that closed it. A `task_started` frame names the call and the subagent's
type, and the `result` frame closes the process with its totals.
"""

from typing import Any

from tests.observability.usage import usage_claude_request_streams as stream

CALL = "toolu_call_a"
AGENT = "agent_a"
SUBAGENT_TYPE = "general-purpose"
CONTEXT_WINDOW = 1_000_000
# The input, cache reads, and cache writes a hand-back's usage block reports beside its output.
HANDBACK_PROMPT = (2, 50, 5)


def subagent(
    message_id: str,
    *,
    call: str = CALL,
    model: str | None = stream.MODEL,
    agent: str = AGENT,
) -> str:
    """A subagent's `assistant` frame, printed under the call that launched it; it prints no stream events."""
    return stream.assistant(message_id, stream.usage(), model=model, parent_tool_use_id=call, agent_id=agent)


def handback(
    call: str | None,
    output: Any,
    *,
    thinking: Any = None,
    agent: str | None = AGENT,
) -> str:
    """The lead thread's return of a subagent call, carrying the usage of the message that closed the subagent.

    `agent` None prints the hand-back with no agent identity.
    """
    block = stream.usage((*HANDBACK_PROMPT, output))
    if thinking is not None:
        block[stream.DETAILS] = {stream.THINKING: thinking}
    returned = {"agentId": agent, "resolvedModel": stream.MODEL, stream.USAGE: block}
    blocks = [{stream.TYPE: "tool_result", "tool_use_id": call, "content": "the report"}] if call else []
    frame = {stream.TYPE: "user", stream.MESSAGE: {"content": blocks}, stream.PARENT: None}
    return stream.line({**frame, "tool_use_result": returned})


def task_started(call: str = CALL) -> str:
    frame = {stream.TYPE: "system", "subtype": "task_started", "tool_use_id": call}
    return stream.line({**frame, "subagent_type": SUBAGENT_TYPE})


def terminal(**fields: Any) -> str:
    """The `result` frame closing the process."""
    frame = {stream.TYPE: "result", "subtype": "success", "session_id": stream.SESSION, "num_turns": 1}
    frame.update(fields)
    return stream.line(frame)


def model_usage(totals: stream.Counts) -> dict[str, Any]:
    """`result.modelUsage` reporting one model's `(input, cache read, cache write, output)` totals and its window."""
    named = ("inputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "outputTokens")
    reported: dict[str, Any] = dict(zip(named, totals, strict=True))
    reported["contextWindow"] = CONTEXT_WINDOW
    return {stream.MODEL: reported}
