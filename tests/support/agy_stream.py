# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Antigravity headless stream fixtures using its documented event envelopes."""

import json

BACKEND = "agy"
MODEL = "gemini-3.8-flash-high"
ARGS = ("--dangerously-skip-permissions", "--model", MODEL, "--effort", "high")
SPEC = " ".join((BACKEND, *ARGS))
SESSION_ID = "3b2d8bbc-af8e-491b-b7e0-1993f622b3d5"
ANSWER = "AGY_OK\n"
SUCCESS = "SUCCESS"
FAILURE = "ERROR"
TOOL_NAME = "run_command"
INPUT_TOKENS = 13579
OUTPUT_TOKENS = 85
CACHE_READ_TOKENS = 200


def event(name: str, **payload) -> str:
    return json.dumps({"event": name, name: payload})


def init_event() -> str:
    return json.dumps({
        "event": "init",
        "conversation_id": SESSION_ID,
        "init": {"model": MODEL, "tools": [TOOL_NAME], "permission_mode": "always-proceed"},
    })


def step(index: int, kind: str = "agent_response", state: str = "DONE", **fields) -> str:
    return event(
        "step_update", conversation_id=SESSION_ID,
        step_index=index, step_type=kind, state=state, **fields,
    )


def terminal(status: str = SUCCESS, **fields) -> str:
    return event("result", conversation_id=SESSION_ID, status=status, response=ANSWER, **fields)


def resumed_stream() -> str:
    return "\n".join((
        init_event(),
        step(2, kind="user_input"),
        step(4, state="ACTIVE", text_delta="AGY_OK"),
        step(4, text_delta="\n", usage={
            "input_tokens": INPUT_TOKENS, "output_tokens": OUTPUT_TOKENS,
            "thinking_tokens": 81, "cache_read_tokens": CACHE_READ_TOKENS,
        }),
        terminal(num_turns=2, usage={"input_tokens": 26820, "output_tokens": 203, "cache_read_tokens": 400}),
    ))
