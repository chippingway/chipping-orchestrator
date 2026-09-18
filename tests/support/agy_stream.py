# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Antigravity headless stream fixtures using its documented event envelopes."""

import json
from typing import Any

BACKEND = "agy"
MODEL = "gemini-3.8-flash-high"
ARGS = ("--dangerously-skip-permissions", "--model", MODEL, "--effort", "high")
SPEC = " ".join((BACKEND, *ARGS))
SESSION_ID = "3b2d8bbc-af8e-491b-b7e0-1993f622b3d5"
ANSWER = "AGY_OK\n"
SUCCESS = "SUCCESS"
FAILURE = "ERROR"
TOOL_NAME = "run_command"
TOOL_TASK = "manage_task"
INPUT_TOKENS = 13579
OUTPUT_TOKENS = 85
CACHE_READ_TOKENS = 200
_ACTIVE = "ACTIVE"
_DONE = "DONE"
_CMD_PARAM = "CommandLine"


def event(name: str, **payload) -> str:
    return json.dumps({"event": name, name: payload})


def init_event() -> str:
    return json.dumps({
        "event": "init",
        "conversation_id": SESSION_ID,
        "init": {"model": MODEL, "tools": [TOOL_NAME], "permission_mode": "always-proceed"},
    })


def step(index: int, kind: str = "agent_response", state: str = _DONE, **fields) -> str:
    return event(
        "step_update", conversation_id=SESSION_ID,
        step_index=index, step_type=kind, state=state, **fields,
    )


def terminal(status: str = SUCCESS, response: str = ANSWER, **fields) -> str:
    return event("result", conversation_id=SESSION_ID, status=status, response=response, **fields)


def resumed_stream() -> str:
    return "\n".join((
        init_event(),
        step(2, kind="user_input"),
        step(4, state=_ACTIVE, text_delta="AGY_OK"),
        step(4, text_delta="\n", usage={
            "input_tokens": INPUT_TOKENS, "output_tokens": OUTPUT_TOKENS,
            "thinking_tokens": 81, "cache_read_tokens": CACHE_READ_TOKENS,
        }),
        terminal(num_turns=2, usage={"input_tokens": 26820, "output_tokens": 203, "cache_read_tokens": 400}),
    ))


class ToolStream:
    """Tool step fixtures for lifecycle reducer tests."""

    @classmethod
    def tool_step(
        cls,
        index: int,
        name: str = TOOL_NAME,
        state: str = _DONE,
        args: dict[str, Any] | None = None,
        out: Any = None,
    ) -> str:
        tool_payload: dict[str, Any] = {"name": name}
        if args is not None:
            tool_payload["parameters"] = args
        if out is not None:
            tool_payload["output"] = out
        return step(index, kind="tool", state=state, tool_info=tool_payload)

    @classmethod
    def active_command(cls, name: str = TOOL_NAME, cmd: str = "pytest") -> str:
        return "\n".join((
            init_event(),
            cls.tool_step(1, name=name, state=_ACTIVE, args={_CMD_PARAM: cmd}),
            terminal(status=SUCCESS),
        ))

    @classmethod
    def active_with_checks(cls, cmd: str = "pytest", task_id: str = "task-1") -> str:
        status_msg = "Task task-1 is RUNNING"
        check_args = {"Action": "status", "TaskId": task_id}
        return "\n".join((
            init_event(),
            cls.tool_step(1, name=TOOL_NAME, state=_ACTIVE, args={_CMD_PARAM: cmd}),
            cls.tool_step(2, name=TOOL_TASK, state=_DONE, args=check_args, out=status_msg),
            cls.tool_step(3, name=TOOL_TASK, state=_DONE, args=check_args, out=status_msg),
            terminal(status=SUCCESS, response="Command is running in background."),
        ))

    @classmethod
    def repeated_updates(cls, index: int = 1, name: str = TOOL_NAME) -> str:
        return "\n".join((
            init_event(),
            cls.tool_step(index, name=name, state=_ACTIVE, args={_CMD_PARAM: "sleep 10"}),
            event("step_update", conversation_id=SESSION_ID, step_index=index, state=_ACTIVE),
            event(
                "step_update", conversation_id=SESSION_ID, step_index=index,
                tool_info={"output": "still running..."},
            ),
            terminal(status=SUCCESS),
        ))

    @classmethod
    def completed_command(cls, cmd: str = "pytest", task_id: str = "task-1") -> str:
        status_msg = "Task task-1 is RUNNING"
        check_args = {"Action": "status", "TaskId": task_id}
        return "\n".join((
            init_event(),
            cls.tool_step(1, name=TOOL_NAME, state=_ACTIVE, args={_CMD_PARAM: cmd}),
            cls.tool_step(2, name=TOOL_TASK, state=_DONE, args=check_args, out=status_msg),
            cls.tool_step(1, name=TOOL_NAME, state=_DONE, out="5 passed in 0.10s"),
            terminal(status=SUCCESS, response="Tests completed successfully."),
        ))
