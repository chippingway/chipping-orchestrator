# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one decoded JSONL object is read back as, and what it is not.

This is where a line stops being untyped JSON and becomes the record the page
renders. Two decisions are made once here: an object is only a run when it
carries this viewer's event, so an audit line sharing the file is dismissed
rather than rendered as an empty run; and the line's position in the file is
what the record is stamped with, because the file is append-only and that
position is the only thing two same-second records are ordered by.

Everything else is narrowing. Each field goes through ``coercion`` rather than
being trusted, and a step or a turn that cannot be read is dropped instead of
raising, so a hand-edited entry costs its own row rather than the whole run. A
usage summary that is missing or not an object reads as none, which is the one
reading of a damaged line that still lets the rest of its run render.
"""

from __future__ import annotations

from typing import Any

from orchestrator.observability.trajectory_viewer import coercion, constants
from orchestrator.observability.trajectory_viewer.models import (
    RunUsageView,
    TrajectoryStepView,
    TurnUsageView,
)
from orchestrator.observability.trajectory_viewer.runs import TrajectoryRun


def parse_step(raw_step: Any) -> TrajectoryStepView | None:
    if not isinstance(raw_step, dict):
        return None
    kind = coercion.coerce_str(raw_step.get("kind"))
    if not kind:
        return None
    return TrajectoryStepView(
        kind=kind,
        name=coercion.coerce_str(raw_step.get("name")),
        tool_id=coercion.coerce_str(raw_step.get("tool_id")),
        content=coercion.coerce_str(raw_step.get("content")),
        turn=coercion.coerce_int(raw_step.get("turn")),
    )


def parse_run_usage(raw_usage: Any) -> RunUsageView | None:
    if not isinstance(raw_usage, dict):
        return None
    return RunUsageView(
        models=coercion.coerce_str_tuple(raw_usage.get("models")),
        turns=coercion.coerce_int(raw_usage.get("turns")),
        input_tokens=coercion.coerce_int(raw_usage.get("input_tokens")) or 0,
        output_tokens=coercion.coerce_int(raw_usage.get("output_tokens")) or 0,
        cached_tokens=coercion.coerce_int(raw_usage.get("cached_tokens")) or 0,
        cache_read_tokens=coercion.coerce_int(raw_usage.get("cache_read_tokens")) or 0,
        cache_write_tokens=coercion.coerce_int(raw_usage.get("cache_write_tokens")) or 0,
        cost_usd=coercion.coerce_float(raw_usage.get("cost_usd")),
        cost_source=coercion.coerce_str(raw_usage.get("cost_source")),
    )


def parse_turn(raw_turn: Any) -> TurnUsageView | None:
    if not isinstance(raw_turn, dict):
        return None
    return TurnUsageView(
        turn=coercion.coerce_int(raw_turn.get("turn")),
        model=coercion.coerce_str(raw_turn.get("model")),
        input_tokens=coercion.coerce_int(raw_turn.get("input_tokens")) or 0,
        output_tokens=coercion.coerce_int(raw_turn.get("output_tokens")) or 0,
        cache_read_tokens=coercion.coerce_int(raw_turn.get("cache_read_tokens")) or 0,
        cache_write_tokens=coercion.coerce_int(raw_turn.get("cache_write_tokens")) or 0,
        cost_usd=coercion.coerce_float(raw_turn.get("cost_usd")),
        cost_source=coercion.coerce_str(raw_turn.get("cost_source")),
    )


def parse_record(record_object: Any, *, sequence: int) -> TrajectoryRun | None:
    if not isinstance(record_object, dict):
        return None
    if record_object.get("event") != constants.TRAJECTORY_EVENT:
        return None
    raw_steps = coercion.as_list(record_object.get("steps"))
    raw_turns = coercion.as_list(record_object.get("turns"))
    steps = tuple(step for step in map(parse_step, raw_steps) if step is not None)
    turns = tuple(turn for turn in map(parse_turn, raw_turns) if turn is not None)
    return TrajectoryRun(
        seq=sequence,
        ts=coercion.coerce_str(record_object.get("ts")),
        repo=coercion.coerce_str(record_object.get("repo")),
        issue=coercion.coerce_int(record_object.get("issue")) or 0,
        stage=coercion.coerce_str(record_object.get("stage")),
        agent_role=coercion.coerce_str(record_object.get("agent_role")),
        backend=coercion.coerce_str(record_object.get("backend")),
        session_id=coercion.coerce_str(record_object.get("session_id")),
        review_round=coercion.coerce_int(record_object.get("review_round")),
        retry_count=coercion.coerce_int(record_object.get("retry_count")),
        user_input=coercion.coerce_str(record_object.get("user_input")),
        system_prompt=coercion.coerce_str(record_object.get("system_prompt")),
        output=coercion.coerce_str(record_object.get("output")),
        tools=coercion.coerce_str_tuple(record_object.get("tools")),
        skills_triggered=coercion.coerce_str_tuple(record_object.get("skills_triggered")),
        skills_available=coercion.coerce_str_tuple(record_object.get("skills_available")),
        steps=steps,
        run_usage=parse_run_usage(record_object.get("run_usage")),
        turns=turns,
        truncated=bool(record_object.get("truncated")),
    )
