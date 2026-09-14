# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Synthetic Codex and Claude output frames for usage and skill-event tests."""
from __future__ import annotations

import json

_TYPE_KEY = "type"
_USAGE_KEY = "usage"
_INPUT_TOKENS_KEY = "input_tokens"
_OUTPUT_TOKENS_KEY = "output_tokens"
_MESSAGE_KEY = "message"
_ID_KEY = "id"
_RESULT_KEY = "result"
_CONTENT_KEY = "content"
_SKILL_KEY = "skill"
_CLAUDE_MODEL = "claude-sonnet-4-6"
_CLAUDE_INPUT_TOKENS = 1234
_CLAUDE_OUTPUT_TOKENS = 567
_CLAUDE_CACHE_WRITE_TOKENS = 80
_SKILL_OUTPUT_TOKENS = 500


def _codex_stdout_no_model(
    *,
    input_tokens: int = 2000,
    cached: int = 500,
    output_tokens: int = 800,
) -> str:
    """Build a codex --json stdout with usage frames but NO model field.

    Reproduces the case the reviewer flagged: codex sometimes emits a
    usage frame on resume / minimal completions whose `model` is
    missing. Without `fallback_model` the parser tags the run
    `unknown-price` with `models=[]`; with the fallback it should
    populate `models` with the configured model and -- when priced --
    produce an `estimated` cost.
    """
    return json.dumps({
        _TYPE_KEY: "turn_complete",
        _USAGE_KEY: {
            _INPUT_TOKENS_KEY: input_tokens,
            "cached_input_tokens": cached,
            _OUTPUT_TOKENS_KEY: output_tokens,
        },
    })


def _claude_stdout(
    *,
    msg_id: str = "msg-1",
    model: str = _CLAUDE_MODEL,
    total_cost_usd: float | None = None,
    num_turns: int = 2,
) -> str:
    """Build a minimal claude stream-json stdout the usage parser understands.

    Mirrors the shape `parse_claude_usage` reads: one assistant frame with
    `message.usage` and one terminal `result` frame carrying `num_turns`
    (and `total_cost_usd` when the agent self-reports it).
    """
    assistant = {
        _TYPE_KEY: "assistant",
        _MESSAGE_KEY: {
            _ID_KEY: msg_id,
            "model": model,
            _USAGE_KEY: {
                _INPUT_TOKENS_KEY: _CLAUDE_INPUT_TOKENS,
                _OUTPUT_TOKENS_KEY: _CLAUDE_OUTPUT_TOKENS,
                "cache_read_input_tokens": 100,
                "cache_creation_input_tokens": _CLAUDE_CACHE_WRITE_TOKENS,
            },
        },
    }
    result_frame = {_TYPE_KEY: _RESULT_KEY, "num_turns": num_turns}
    if total_cost_usd is not None:
        result_frame["total_cost_usd"] = total_cost_usd
    return "\n".join([json.dumps(assistant), json.dumps(result_frame)])


def _claude_stdout_with_skills(
    *,
    skills: tuple[str, ...],
    args_marker: str = "skill-args-must-never-be-stored",
) -> str:
    """A claude stream-json stdout that reports usage AND triggers `Skill`
    blocks -- each name in `skills` becomes one `tool_use` block named
    `"Skill"`. The `args` string is asserted never to reach an emitted event
    (Privacy: only the skill name is read).
    """
    content_blocks = [
        {
            _TYPE_KEY: "tool_use",
            "name": "Skill",
            "input": {_SKILL_KEY: name, "args": args_marker},
        }
        for name in skills
    ]
    assistant = {
        _TYPE_KEY: "assistant",
        _MESSAGE_KEY: {
            _ID_KEY: "msg-skill",
            "model": _CLAUDE_MODEL,
            _CONTENT_KEY: content_blocks,
            _USAGE_KEY: {
                _INPUT_TOKENS_KEY: 1000,
                _OUTPUT_TOKENS_KEY: _SKILL_OUTPUT_TOKENS,
            },
        },
    }
    result_frame = {_TYPE_KEY: _RESULT_KEY, "num_turns": 1}
    return "\n".join([json.dumps(assistant), json.dumps(result_frame)])
