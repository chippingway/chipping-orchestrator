# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Codex `exec --json` streams for the terminal-turn reader and its verdicts."""

from __future__ import annotations

import json
from typing import Any

TYPE_FIELD = "type"
MESSAGE_FIELD = "message"
USAGE_LIMIT_CODE = "usage_limit_exceeded"

# The provider message the reviewer runs on #1793 ended on, from their rollouts,
# which also recorded it coded `usage_limit_exceeded`.
ROLLOUT_LIMIT_MESSAGE = (
    "You\u2019ve hit your usage limit. Visit https://chatgpt.com/codex/settings/usage "
    "to purchase more credits or try again at Sep 26th, 2026 12:09 PM."
)
ROLLOUT_RESET = "Sep 26th, 2026 12:09 PM"

# Captured from codex-cli 0.162.0 `exec --json` against a provider answering
# its first request with a 429 `usage_limit_reached`: the run exited 1 and left
# its `-o` file empty. The CLI prints the message on both the standalone
# `error` event and the closing `turn.failed`, and the code on neither.
CAPTURED_LIMIT_MESSAGE = (
    "You\u2019ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), "
    "visit https://chatgpt.com/settings/usage to purchase more credits or try again at "
    "Oct 17th, 2026 1:36 AM."
)
CAPTURED_RESET = "Oct 17th, 2026 1:36 AM"
_CAPTURED_LIMIT_LINES = (
    '{"type":"thread.started","thread_id":"01a12719-eef4-7330-b188-a4ccd5feef66"}',
    (
        '{"type":"item.completed","item":{"id":"item_0","type":"error","message":'
        '"Model metadata for `gpt-5` not found. Defaulting to fallback metadata; '
        'this can degrade performance and cause issues."}}'
    ),
    '{"type":"turn.started"}',
    f'{{"type":"error","message":"{CAPTURED_LIMIT_MESSAGE}"}}',
    f'{{"type":"turn.failed","error":{{"message":"{CAPTURED_LIMIT_MESSAGE}"}}}}',
)
CAPTURED_LIMIT_STDOUT = "\n".join(_CAPTURED_LIMIT_LINES)

# The captured stop followed by a later turn the stream never closes: left open,
# and closed by a line cut off mid-write.
_LATER_TURN_STARTED = '{"type":"turn.started"}'
LIMIT_THEN_UNFINISHED_TURN_STDOUTS = (
    "\n".join((*_CAPTURED_LIMIT_LINES, _LATER_TURN_STARTED)),
    "\n".join((*_CAPTURED_LIMIT_LINES, _LATER_TURN_STARTED, '{"type":"turn.completed"')),
)


def codex_jsonl(*events: Any) -> str:
    """One event per line, non-ASCII left as the CLI prints it."""
    return "\n".join(json.dumps(event, ensure_ascii=False) for event in events)


def turn_started() -> dict[str, Any]:
    return {TYPE_FIELD: "turn.started"}


def turn_completed() -> dict[str, Any]:
    """A closing `turn.completed`, the event a successful turn ends on."""
    return {
        TYPE_FIELD: "turn.completed",
        "usage": {"input_tokens": 1200, "cached_input_tokens": 0, "output_tokens": 40},
    }


def turn_failed(message: str, **error_fields: Any) -> dict[str, Any]:
    """A closing `turn.failed` whose error carries `message` and any extra fields."""
    return {TYPE_FIELD: "turn.failed", "error": {MESSAGE_FIELD: message, **error_fields}}


def stream_error(message: str, **error_fields: Any) -> dict[str, Any]:
    """A standalone mid-turn `error` event, flattened the way the CLI prints it."""
    return {TYPE_FIELD: "error", MESSAGE_FIELD: message, **error_fields}


def agent_message(text: str) -> dict[str, Any]:
    """A completed agent message item, the text a successful turn answers with."""
    return {
        TYPE_FIELD: "item.completed",
        "item": {"id": "item_1", TYPE_FIELD: "agent_message", "text": text},
    }
