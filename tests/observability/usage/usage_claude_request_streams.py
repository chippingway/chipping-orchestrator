# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Claude stream-json message lines in the shapes Claude Code 2.1.295 prints, for the request collection tests.

Each builder returns one stdout line. The frames carry only what the request collector reads -- the wrapper's
`api_message_id` and `parent_tool_use_id`, a message's id, model, and usage -- beside a short text block, so a test
reads which frames a request is folded from rather than how the CLI words them. `message` prints a whole lead-thread
message the way the capture does: its `message_start`, one `assistant` frame per block repeating the usage it started
with, and the `message_delta` closing it. Subagent frames and process reports are built on
`usage_claude_request_branches`.
"""

import json
from typing import Any

SESSION = "sess-claude-0"
MODEL = "claude-opus-5-5"
OTHER_MODEL = "claude-sonnet-5-5"
VERSION = "2.1.295"
INPUT = "input_tokens"
OUTPUT = "output_tokens"
CACHE_READ = "cache_read_input_tokens"
CACHE_WRITE = "cache_creation_input_tokens"
SPLIT = "cache_creation"
FIVE_MINUTE = "ephemeral_5m_input_tokens"
ONE_HOUR = "ephemeral_1h_input_tokens"
DETAILS = "output_tokens_details"
THINKING = "thinking_tokens"
TYPE = "type"
PARENT = "parent_tool_use_id"
USAGE = "usage"
MESSAGE = "message"
MODEL_KEY = "model"
# Input, cache reads, cache writes, and the output a message starts with.
START_COUNTS = (2, 100, 10, 1)
Counts = tuple[int, int, int, int]
_STREAM_EVENT = "stream_event"
_API_MESSAGE_ID = "api_message_id"


def line(frame: dict[str, Any]) -> str:
    return json.dumps(frame)


def usage(counts: Counts = START_COUNTS, **fields: Any) -> dict[str, Any]:
    """A usage block of `(input, cache read, cache write, output)` counts, its writes all one-hour ones."""
    input_tokens, cache_read, cache_write, output = counts
    block = {INPUT: input_tokens, CACHE_READ: cache_read, CACHE_WRITE: cache_write, OUTPUT: output}
    block[SPLIT] = {FIVE_MINUTE: 0, ONE_HOUR: cache_write}
    block.update(fields)
    return block


def init(**fields: Any) -> str:
    frame = {TYPE: "system", "subtype": "init", "session_id": SESSION, MODEL_KEY: MODEL}
    frame["claude_code_version"] = VERSION
    frame.update(fields)
    return line(frame)


def start(message_id: str, block: dict[str, Any], *, model: str = MODEL) -> str:
    """The `message_start` stream event opening a message, under its wrapper's `api_message_id`."""
    event = {TYPE: "message_start", MESSAGE: {"id": message_id, MODEL_KEY: model, USAGE: block}}
    return line({TYPE: _STREAM_EVENT, "event": event, PARENT: None, _API_MESSAGE_ID: message_id})


def assistant(
    message_id: str | None,
    block: dict[str, Any] | None,
    *,
    model: str | None = MODEL,
    **wrapper: Any,
) -> str:
    """One `assistant` frame of a message: one content block, beside the usage the message started with."""
    message: dict[str, Any] = {"content": [{TYPE: "text", "text": "a block"}]}
    for name, named_value in (("id", message_id), (MODEL_KEY, model), (USAGE, block)):
        if named_value is not None:
            message[name] = named_value
    wrapper.setdefault(PARENT, None)
    return line({TYPE: "assistant", MESSAGE: message, **wrapper})


def delta(message_id: str | None, output: Any, *, thinking: Any = None, **fields: Any) -> str:
    """The `message_delta` closing a message with its final output, thinking broken out where `thinking` is given."""
    block = {OUTPUT: output, **fields}
    if thinking is not None:
        block[DETAILS] = {THINKING: thinking}
    wrapper: dict[str, Any] = {PARENT: None}
    if message_id is not None:
        wrapper[_API_MESSAGE_ID] = message_id
    return line({TYPE: _STREAM_EVENT, "event": {TYPE: "message_delta", USAGE: block}, **wrapper})


def message(
    message_id: str,
    final_output: int,
    *,
    thinking: int = 0,
    blocks: int = 2,
    model: str = MODEL,
) -> tuple[str, ...]:
    """A whole lead-thread message: its start, `blocks` assistant frames, and the delta closing it."""
    block = usage()
    frame = assistant(message_id, block, model=model, request_id=f"req_{message_id}")
    closing = delta(message_id, final_output, thinking=thinking)
    return (start(message_id, block, model=model), *(frame,) * blocks, closing)
