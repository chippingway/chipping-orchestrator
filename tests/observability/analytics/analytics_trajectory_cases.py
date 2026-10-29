# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Trajectory stream payload builders for analytics recording tests."""

import json
from dataclasses import dataclass

_COMMAND_KEY = 'command'
_BASH_TOOL_NAME = 'Bash'
_TYPE_KEY = 'type'
_CONTENT_KEY = 'content'
_ID_KEY = 'id'
_MESSAGE_KEY = 'message'
_ITEM_KEY = 'item'
_RESULT_KEY = 'result'
_USAGE_KEY = 'usage'


CLAUDE_TRAJECTORY_INPUT_TOKENS = 100


CLAUDE_TRAJECTORY_OUTPUT_TOKENS = 50


CODEX_TRAJECTORY_INPUT_TOKENS = 200


CODEX_TRAJECTORY_OUTPUT_TOKENS = 80


_CLAUDE_MODEL = "claude-sonnet-4-6"


_INPUT_TOKENS = "input_tokens"


_OUTPUT_TOKENS = "output_tokens"


@dataclass(frozen=True)
class ClaudeTrajectoryCase:
    """One configurable Claude trajectory stream fixture."""

    tool_name: str = _BASH_TOOL_NAME
    tool_input: dict | None = None
    tool_result: object = "tool result text"
    final_output: str | None = "final answer"
    offered_tools: tuple[str, ...] = ("Read", _BASH_TOOL_NAME)
    input_tokens: int = CLAUDE_TRAJECTORY_INPUT_TOKENS
    output_tokens: int = CLAUDE_TRAJECTORY_OUTPUT_TOKENS

    def render(self) -> str:
        """Render the case as Claude stream-JSON stdout."""
        frames: list[dict] = [
            {
                _TYPE_KEY: "system",
                "subtype": "init",
                "tools": list(self.offered_tools),
            },
            {
                _TYPE_KEY: "assistant",
                _MESSAGE_KEY: {
                    _ID_KEY: "m1",
                    "model": _CLAUDE_MODEL,
                    _CONTENT_KEY: [
                        {
                            _TYPE_KEY: "tool_use",
                            "name": self.tool_name,
                            _ID_KEY: "tu1",
                            "input": self.tool_input or {_COMMAND_KEY: "ls"},
                        }
                    ],
                    _USAGE_KEY: {
                        _INPUT_TOKENS: self.input_tokens,
                        _OUTPUT_TOKENS: self.output_tokens,
                    },
                },
            },
            {
                _TYPE_KEY: "user",
                _MESSAGE_KEY: {
                    _CONTENT_KEY: [
                        {
                            _TYPE_KEY: "tool_result",
                            "tool_use_id": "tu1",
                            _CONTENT_KEY: self.tool_result,
                        }
                    ]
                },
            },
        ]
        result_frame: dict = {_TYPE_KEY: _RESULT_KEY, "num_turns": 1}
        if self.final_output is not None:
            result_frame[_RESULT_KEY] = self.final_output
        frames.append(result_frame)
        return "\n".join(json.dumps(frame) for frame in frames)


def claude_trajectory_stdout(**overrides) -> str:
    """Render one typed Claude trajectory fixture."""
    return ClaudeTrajectoryCase(**overrides).render()


def claude_multistep_stdout(*, n_steps: int, result_text: str, total_cost_usd: float | None = None) -> str:
    """A claude stream with `n_steps` tool_use / tool_result pairs (so
    `2 * n_steps` trajectory steps), each result carrying `result_text`, and
    the run's `total_cost_usd` when the CLI reports one. Used to drive the
    total-record-budget truncation and the per-turn usage evidence."""
    frames: list[dict] = [
        {_TYPE_KEY: "system", "subtype": "init", "tools": [_BASH_TOOL_NAME]},
    ]
    for index in range(n_steps):
        frames.append(
            {
                _TYPE_KEY: "assistant",
                _MESSAGE_KEY: {
                    _ID_KEY: f"m{index}",
                    "model": _CLAUDE_MODEL,
                    _CONTENT_KEY: [
                        {
                            _TYPE_KEY: "tool_use",
                            "name": _BASH_TOOL_NAME,
                            _ID_KEY: f"tu{index}",
                            "input": {_COMMAND_KEY: "x"},
                        }
                    ],
                    _USAGE_KEY: {_INPUT_TOKENS: 1, _OUTPUT_TOKENS: 1},
                },
            }
        )
        frames.append(
            {
                _TYPE_KEY: "user",
                _MESSAGE_KEY: {
                    _CONTENT_KEY: [
                        {
                            _TYPE_KEY: "tool_result",
                            "tool_use_id": f"tu{index}",
                            _CONTENT_KEY: result_text,
                        }
                    ]
                },
            }
        )
    result_frame: dict = {_TYPE_KEY: _RESULT_KEY, "num_turns": n_steps}
    if total_cost_usd is not None:
        result_frame["total_cost_usd"] = total_cost_usd
    frames.append(result_frame)
    return "\n".join(json.dumps(frame) for frame in frames)


def codex_trajectory_stdout(
    *,
    command: str = "ls -la",
    output: str = "command output",
    final: str | None = "codex done",
    input_tokens: int = CODEX_TRAJECTORY_INPUT_TOKENS,
    output_tokens: int = CODEX_TRAJECTORY_OUTPUT_TOKENS,
) -> str:
    """A codex --json stdout with one command_execution call + result and a
    final agent_message -- the surface `parse_codex_trajectory` reads."""
    frames: list[dict] = [
        {
            _TYPE_KEY: "item.started",
            _ITEM_KEY: {
                _ID_KEY: "c1",
                _TYPE_KEY: "command_execution",
                _COMMAND_KEY: command,
            },
        },
        {
            _TYPE_KEY: "item.completed",
            _ITEM_KEY: {
                _ID_KEY: "c1",
                _TYPE_KEY: "command_execution",
                _COMMAND_KEY: command,
                "aggregated_output": output,
            },
        },
    ]
    if final is not None:
        frames.append(
            {
                _TYPE_KEY: "item.completed",
                _ITEM_KEY: {
                    _ID_KEY: "a1",
                    _TYPE_KEY: "agent_message",
                    "text": final,
                },
            }
        )
    frames.append(
        {
            _TYPE_KEY: "turn_complete",
            _USAGE_KEY: {
                _INPUT_TOKENS: input_tokens,
                _OUTPUT_TOKENS: output_tokens,
            },
        }
    )
    return "\n".join(json.dumps(frame) for frame in frames)


def codex_mcp_trajectory_stdout(
    *,
    arguments: dict,
    result_content: list,
) -> str:
    """A codex --json stdout whose one item is an MCP tool call.

    The arguments and the result are the nested JSON codex reports them as,
    which is the payload shape the trajectory writer has to redact leaf by
    leaf rather than as text."""
    call = {
        _ID_KEY: "m1",
        _TYPE_KEY: "mcp_tool_call",
        "server": "docsServer",
        "tool": "fetch_doc",
        "arguments": arguments,
        _RESULT_KEY: None,
        "error": None,
        "status": "in_progress",
    }
    completed = dict(call)
    completed[_RESULT_KEY] = {
        _CONTENT_KEY: result_content,
        "structured_content": None,
    }
    completed["status"] = "completed"
    frames = [
        {_TYPE_KEY: "item.started", _ITEM_KEY: call},
        {_TYPE_KEY: "item.completed", _ITEM_KEY: completed},
        {
            _TYPE_KEY: "turn_complete",
            _USAGE_KEY: {
                _INPUT_TOKENS: CODEX_TRAJECTORY_INPUT_TOKENS,
                _OUTPUT_TOKENS: CODEX_TRAJECTORY_OUTPUT_TOKENS,
            },
        },
    ]
    return "\n".join(json.dumps(frame) for frame in frames)
