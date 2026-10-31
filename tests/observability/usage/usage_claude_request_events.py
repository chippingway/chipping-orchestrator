# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Claude stream-json builders for runs priced message by message, and for runs whose rows establish no prompt."""

from tests.observability.usage import (
    usage_claude_events as _claude,
    usage_claude_subagent_events as _subagent,
    usage_jsonl_helpers as _jsonl,
    usage_test_values as _usage_cases,
)

# Input, five-minute writes, one-hour writes, cache reads, and output: Claude's page columns, in its order.
RequestCounts = tuple[int, int, int, int, int]

# The `usage` builder field each column of a request's counts fills.
_COLUMN_FIELDS = ("input", "cache_five_minute", "cache_one_hour", "cache_read", "output")

LEAD_COUNTS: RequestCounts = (10, 0, 0, 0, 1)
LEAD_OUTPUT_TOKENS = 50
HANDBACK_OUTPUT_TOKENS = 20
_PROMPT_INPUT_TOKENS = 1000
_OUTPUT_TOKENS = 100


def request(message_id: str, model: str, counts: RequestCounts) -> dict:
    """An `assistant` frame whose usage reports every class, its writes as an aggregate beside their lifetime split."""
    columns = dict(zip(_COLUMN_FIELDS, counts, strict=True))
    writes = columns["cache_five_minute"] + columns["cache_one_hour"]
    usage = _claude.usage(cache_write=writes, **columns)
    return _claude.assistant(id=message_id, model=model, usage=usage)


def handback_run(model: str) -> str:
    """A lead message its `message_delta` closes, then a subagent hand-back carrying its closing message's usage."""
    return _jsonl.jsonl(
        request(_usage_cases.CLAUDE_TURN_ID, model, LEAD_COUNTS),
        _claude.message_delta(_usage_cases.CLAUDE_TURN_ID, output_tokens=LEAD_OUTPUT_TOKENS),
        _subagent.handback(_usage_cases.TOOL_USE_A_ID, model, output=HANDBACK_OUTPUT_TOKENS),
    )


def unestablished_runs(model: str) -> tuple[tuple[str, str], ...]:
    """Runs on `model` holding a row that establishes no request's prompt, each named for what it lacks."""
    every_class = _claude.usage(
        input=_PROMPT_INPUT_TOKENS,
        output=_OUTPUT_TOKENS,
        cache_read=0,
        cache_write=0,
        cache_five_minute=0,
        cache_one_hour=0,
    )
    no_cache_read = _claude.usage(input=_PROMPT_INPUT_TOKENS, output=_OUTPUT_TOKENS, cache_write=0)
    one_lifetime = _claude.usage(
        input=_PROMPT_INPUT_TOKENS,
        output=_OUTPUT_TOKENS,
        cache_read=0,
        cache_five_minute=_OUTPUT_TOKENS,
    )
    return (
        ("a result total", _jsonl.jsonl(_claude.terminal_result(model=model, usage=every_class))),
        ("no cache-read count", _jsonl.jsonl(_claude.assistant(model=model, usage=no_cache_read))),
        ("one lifetime and no aggregate", _jsonl.jsonl(_claude.assistant(model=model, usage=one_lifetime))),
    )
