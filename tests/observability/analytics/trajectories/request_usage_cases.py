# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Antigravity runs a trajectory record is written for, and what a budget cut between two entries keeps.

The retention tests cut the budget between every two entries, so they need each entry's size exactly as the record
charges it: the serialized entry, redacted first, beside the always-kept headline charged before any of them. The
privacy case is a run whose conversation id is a secret and whose text, tool call, and tool output are all agent
content, none of which the request usage field may carry.
"""

import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from types import MappingProxyType
from typing import Any
from unittest.mock import patch

from orchestrator.agents.models import AgentResult
from orchestrator.observability.analytics.recording.models import AgentExitContext
from orchestrator.observability.analytics.trajectories import models, serialize
from orchestrator.observability.usage import metrics, protocol, request_agy, trajectory_models
from tests.support import agy_stream as stream

ARRAYS = ("turns", "source_items", "markers", "samples", "steps")
# The keys a sample may carry: identities, positions, attribution, status, and counters with their evidence.
SAMPLE_KEYS = frozenset((
    "id", "id_kind", "conversation_id", "session_id", "turn_id", "message_id", "request_id", "step_index",
    "parent_conversation_id", "parent_step_index", "parent_tool_use_id", "agent_id", "subagent_type",
    "trajectory_turn", "position", "branch_order", "source_kind", "source_timestamp", "source_duration_s", "model",
    "model_source", "context_capacity", "source_version", "scope", "status", "settlement", "raw",
    "context_input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "cache_write_lifetimes",
    "reasoning_tokens", "total_tokens", "source_total_tokens", "overlap", "evidence",
))
SECRET = "sk-ant-DEADBEEF-conversation-0123456789"
SPOKEN = "the-words-the-agent-said"
TOOL_TEXT = "the-command-the-tool-ran"
TOOL_OUTPUT = "what-the-tool-printed"
USAGE = MappingProxyType({protocol.INPUT_TOKENS: 10, protocol.OUTPUT_TOKENS: 2, protocol.CACHE_READ_TOKENS: 0})
_CONVERSATION = "conversation_id"
_MODEL = "model"
_EARLIER_INIT = json.dumps({
    "event": "init",
    _CONVERSATION: stream.SESSION_ID,
    "init": {_MODEL: "gemini-3.6-flash-high"},
})
# A model change between two requests: one marker and two samples.
_STDOUT = "\n".join((
    _EARLIER_INIT,
    stream.step(1, usage=dict(USAGE)),
    stream.init_event(),
    stream.step(2, usage=dict(USAGE)),
    stream.terminal(),
))
_TOOL = MappingProxyType({"name": stream.TOOL_NAME, "parameters": {"CommandLine": TOOL_TEXT}, "output": TOOL_OUTPUT})
_STEPS = (
    trajectory_models.TrajectoryStep("assistant_message", content="first answer"),
    trajectory_models.TrajectoryStep("tool_call", name=stream.TOOL_NAME, tool_id="2", content={"CommandLine": "ls"}),
)
_SOURCE_ITEMS = (
    trajectory_models.SourceItem("item_0", "command_execution", "stored"),
    trajectory_models.SourceItem("item_1", "reasoning", "excluded"),
)
_TURNS = (
    trajectory_models.TurnUsage(0, _MODEL, 1, 1),
    trajectory_models.TurnUsage(1, _MODEL, 2, 2),
)
_CONTEXT = AgentExitContext(
    repo="owner/repo",
    issue=1,
    stage="implementing",
    agent_role="developer",
    backend=protocol.AGY,
    agent_spec=protocol.AGY,
    resume_session_id=None,
    agent_result=AgentResult(None, "", 0, False, _STDOUT, ""),
    duration_s=float(0),
    review_round=None,
    retry_count=None,
    fallback_model=None,
    prompt=None,
    cwd=Path("/workspace"),
)


def private_stdout() -> str:
    """A run whose conversation id is a secret and whose text, tool call, and tool output are agent content."""
    secret = {_CONVERSATION: SECRET}
    response = {"step_type": "agent_response", "state": "DONE", "text_delta": SPOKEN, "usage": dict(USAGE)}
    tool = {"step_type": "tool", "state": "DONE", "tool_info": dict(_TOOL)}
    return "\n".join((
        stream.event("init", init={_MODEL: stream.MODEL}, **secret),
        stream.event("step_update", step_index=1, **response, **secret),
        stream.event("step_update", step_index=2, **tool, **secret),
        stream.terminal(response=SPOKEN),
    ))


def every_array_trajectory() -> trajectory_models.AgentTrajectory:
    """Two entries in each array a record budget draws from, beside one request usage marker."""
    return trajectory_models.AgentTrajectory(
        backend=protocol.AGY,
        steps=_STEPS,
        source_items=_SOURCE_ITEMS,
        turns=_TURNS,
        request_usage=request_agy.collect(_STDOUT),
    )


def built(
    trajectory: trajectory_models.AgentTrajectory,
    entries: list[tuple[str, int]],
    cut: int,
) -> dict[str, Any]:
    """The record `trajectory` is written as within a budget holding exactly the first `cut` charged `entries`."""
    usage = metrics.UsageMetrics(backend=protocol.AGY)
    budget = sum(size for _, size in entries[:cut])
    with patch.object(models, "TRAJECTORY_RECORD_BUDGET", budget):
        return serialize.build_trajectory_record(_CONTEXT, trajectory, usage, str)


def _sized(array: str, entries: Iterable[Any]) -> list[tuple[str, int]]:
    serialized = [entry if isinstance(entry, dict) else entry.to_dict() for entry in entries]
    return [(array, len(json.dumps(entry, default=str))) for entry in serialized]


def charged_entries(trajectory: trajectory_models.AgentTrajectory) -> list[tuple[str, int]]:
    """Every entry in the order the record draws it, named by its array, with the size it is charged.

    The first entry is the always-kept headline, charged before any array.
    """
    limits = models.current_limits()
    request_usage = trajectory.request_usage
    headline = serialize.trajectory_headline(
        _CONTEXT, trajectory, metrics.UsageMetrics(backend=protocol.AGY), str, limits,
    )
    steps = [serialize.trajectory_step(step, str, limits) for step in trajectory.steps]
    return [
        ("headline", headline.serialized_size),
        *_sized(ARRAYS[0], trajectory.turns),
        *_sized(ARRAYS[1], trajectory.source_items),
        *_sized(ARRAYS[2], request_usage.markers),
        *_sized(ARRAYS[3], request_usage.observations),
        *_sized(ARRAYS[4], steps),
    ]


def kept_counts(record: dict[str, Any]) -> dict[str, int]:
    """How many entries of each array a written record kept, and how many a budget cut there would draw."""
    request_usage = record.get("request_usage", {})
    kept = {array: len(record.get(array) or ()) for array in ARRAYS}
    for array in ARRAYS[2:4]:
        kept[array] = len(request_usage.get(array, ()))
    return kept


ChargedEntries = list[tuple[str, int]]


def drawn_counts(entries: ChargedEntries, cut: int) -> dict[str, int]:
    """How many entries of each array a budget holding exactly the first `cut` charged entries keeps."""
    arrays = [array for array, _ in entries[1:cut]]
    drawn = Counter(arrays)
    return {array: drawn[array] for array in ARRAYS}
