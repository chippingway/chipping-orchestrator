# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one ordered sequence a run renders as, and how it is titled and hidden.

The timeline is what makes every run readable the same way. A run whose steps
are only tool calls and their results and one that interleaves assistant and
user turns among them are both read back as the prompt, then the steps in the
order they were streamed, then the final output. Each bracket is dropped when its field is empty, so a run that
was never answered is its prompt alone rather than a trailing blank.

The fixture tells are what an inherited file's synthetic records carry -- the
sentinel prompt the suite writes, the session id its doubles mint, and a run
whose only tool work is loading skills. A stepless record is judged on the
first two alone: "every step is a Skill call" is vacuously true of no steps,
and a real run that recorded none would otherwise be hidden by a toggle an
operator set to drop test data.

The two labels are one string split where a picker needs it: the detail is the
cohort a run is chosen within -- stage, role, backend, review round, timestamp
-- and the label is that detail behind the repository and issue it belongs to,
so the two can never disagree about how a run is named.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from orchestrator.observability.trajectory_viewer import constants
from orchestrator.observability.trajectory_viewer.models import (
    TimelineEntry,
    TurnUsageView,
)

if TYPE_CHECKING:
    from orchestrator.observability.trajectory_viewer.runs import TrajectoryRun


def timeline(run: TrajectoryRun) -> tuple[TimelineEntry, ...]:
    entries: list[TimelineEntry] = []
    if run.user_input:
        entries.append(
            TimelineEntry(
                kind=constants.TIMELINE_PROMPT,
                content=run.user_input,
            )
        )
    for step in run.steps:
        entries.append(
            TimelineEntry(
                kind=step.kind,
                content=step.content,
                name=step.name,
                tool_id=step.tool_id,
                turn=step.turn,
            )
        )
    if run.output:
        entries.append(
            TimelineEntry(
                kind=constants.TIMELINE_OUTPUT,
                content=run.output,
            )
        )
    return tuple(entries)


def is_fixture(run: TrajectoryRun) -> bool:
    if run.user_input.strip().lower() == constants.FIXTURE_PROMPT:
        return True
    if run.session_id.startswith(constants.FIXTURE_SESSION_PREFIX):
        return True
    skill_only = all(
        step.is_call and step.name == constants.FIXTURE_SKILL_TOOL
        for step in run.steps
    )
    return bool(run.steps and skill_only)


def detail_label(run: TrajectoryRun) -> str:
    stage = run.stage or "—"
    role = run.agent_role or "—"
    backend = run.backend or "—"
    round_suffix = "" if run.review_round is None else f" · round {run.review_round}"
    return f"{stage}/{role} · {backend}{round_suffix} · {run.ts}"


def label(run: TrajectoryRun) -> str:
    return f"#{run.issue} {run.repo} · {run.detail_label()}"


def turn_map(run: TrajectoryRun) -> dict[int, TurnUsageView]:
    return {turn_usage.turn: turn_usage for turn_usage in run.turns if turn_usage.turn is not None}
