# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Trajectory usage, turn, item-accounting, step, and record serialization.

One owner for the shape an `agent_trajectory` record has: which run metadata
rides along, which free-text fields are sanitized on the way in, and the order
the variable arrays are charged to the record budget in. The budget order is
part of the shape -- the per-turn array and the source item accounting are
drawn down before the steps, so a run with thousands of turns and no steps is
bounded the same way a run with thousands of steps is, and the accounting a
truncated timeline is audited against outlives the steps it accounts for.

The caps are snapshotted from the `models` owner once per record, so a value
patched between two writes bounds the second one, and the envelope is the
shared `sink` owner's -- the shape a trajectory record has in common with
every other analytics record is decided in one place.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

from orchestrator.observability.analytics import sink
from orchestrator.observability.analytics.trajectories import models, sanitize
from orchestrator.observability.usage import (
    metrics as usage_metrics,
    trajectory_models as usage_trajectory_models,
)

if TYPE_CHECKING:
    from orchestrator.observability.analytics.recording.models import AgentExitContext

# The dispositions a parser assigns, spelled in a fixed order so one run's
# counts are comparable to another's. They are exhaustive by construction --
# exactly one per identified item -- which is what makes the totals below an
# accounting rather than a sample.
ITEM_DISPOSITIONS = (
    usage_trajectory_models.ITEM_STORED,
    usage_trajectory_models.ITEM_UNSUPPORTED,
    usage_trajectory_models.ITEM_EXCLUDED,
    usage_trajectory_models.ITEM_EMPTY,
)

IDENTIFIED_ITEMS = "identified"


def trajectory_usage(metrics: usage_metrics.UsageMetrics) -> dict[str, Any]:
    run_usage = metrics.to_dict()
    run_usage.pop("backend", None)
    return run_usage


def item_counts(
    source_items: tuple[usage_trajectory_models.SourceItem, ...],
) -> dict[str, int]:
    """Total one run's identified items by the disposition each got.

    Fixed-shape and fixed-size: how many items the stream identified, then one
    count per disposition whether or not the run produced any of it. That is
    what a reader audits `item_N` coverage against when the budget left room
    for only a prefix of the ids -- or for none of them -- so it is charged as
    part of the headline and kept whole. A run whose stream identified nothing
    (every claude run, and a codex run that never got that far) is counted as
    nothing rather than as four zeros, so the record simply leaves the field
    off.
    """
    if not source_items:
        return {}
    counted = Counter(source_item.disposition for source_item in source_items)
    counts = {IDENTIFIED_ITEMS: len(source_items)}
    for disposition in ITEM_DISPOSITIONS:
        counts[disposition] = counted[disposition]
    return counts


def trajectory_headline(
    context: AgentExitContext,
    trajectory: usage_trajectory_models.AgentTrajectory,
    metrics: usage_metrics.UsageMetrics,
    redact: sanitize.Redactor,
    limits: models.TrajectoryLimits,
) -> models.TrajectoryHeadline:
    return models.TrajectoryHeadline(
        user_input=sanitize.redact_and_truncate(context.prompt, redact, limits),
        system_prompt=sanitize.redact_and_truncate(
            trajectory.system_prompt, redact, limits,
        ),
        output=sanitize.redact_and_truncate(
            trajectory.final_output, redact, limits,
        ),
        run_usage=trajectory_usage(metrics),
        source_item_counts=item_counts(trajectory.source_items),
    )


def trajectory_step(
    step: usage_trajectory_models.TrajectoryStep,
    redact: sanitize.Redactor,
    limits: models.TrajectoryLimits,
) -> dict[str, Any]:
    step_dict: dict[str, Any] = {
        "kind": step.kind,
        "name": step.name or None,
        "tool_id": step.tool_id or None,
        "content": sanitize.redact_and_truncate(step.content, redact, limits),
    }
    if step.turn is not None:
        step_dict["turn"] = step.turn
    return step_dict


def bounded_trajectory_steps(
    trajectory: usage_trajectory_models.AgentTrajectory,
    budget: models.TrajectoryBudget,
    redact: sanitize.Redactor,
    limits: models.TrajectoryLimits,
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    if budget.truncated:
        return steps
    for step in trajectory.steps:
        step_dict = trajectory_step(step, redact, limits)
        if not budget.include(step_dict):
            break
        steps.append(step_dict)
    return steps


def bounded_arrays(
    trajectory: usage_trajectory_models.AgentTrajectory,
    budget: models.TrajectoryBudget,
    redact: sanitize.Redactor,
    limits: models.TrajectoryLimits,
) -> models.TrajectoryArrays:
    """Draw one record's variable arrays in the order they are charged.

    The order is the contract. The per-turn usage and the source item
    accounting are small, fixed-shape rows a reader needs whole runs of, so
    they are drawn first; the steps -- the one array whose entries carry
    redacted free text and can be arbitrarily large -- are drawn from what is
    left. That is what keeps an id-by-id audit of a codex run possible on the
    very runs that overran the budget, where the timeline the ids account for
    is exactly what got cut.
    """
    turns = budget.bounded(trajectory.turns)
    source_items = budget.bounded(trajectory.source_items)
    steps = bounded_trajectory_steps(trajectory, budget, redact, limits)
    return models.TrajectoryArrays(
        turns=turns,
        source_items=source_items,
        steps=steps,
        source_items_truncated=len(source_items) < len(trajectory.source_items),
    )


def build_trajectory_record(
    context: AgentExitContext,
    trajectory: usage_trajectory_models.AgentTrajectory,
    metrics: usage_metrics.UsageMetrics,
    redact: sanitize.Redactor,
) -> dict:
    """Assemble one redacted, truncated `agent_trajectory` record.

    `prompt` becomes the redacted `user_input`; `system_prompt`, each
    step's content, and the final `output` are redacted the same way.
    `metrics` (the same `UsageMetrics` the baseline `agent_exit` record
    already carries) is denormalized into a `run_usage` summary so the
    file-only viewer needs no re-parse; it is `UsageMetrics.to_dict()` minus
    `backend` (already a record field), so its cost and token evidence are the
    objects the baseline record carries. Its token counts / cost / evidence /
    model name are not secret-shaped, so they skip redaction. The claude per-turn
    breakdown rides along as `turns` (empty on codex, whose usage frames are
    cumulative -- `build_record` then drops the key).

    The parser's per-item accounting rides along as `source_items` (codex-only
    today), one `{item_id, item_type, disposition}` row per item the stream
    identified, in first-seen order. It carries provider-assigned ids and item
    type names rather than agent-sourced content, so like `tools` and a step's
    `name` it skips redaction; everything an item actually said is in the step
    it contributed, and is redacted there.

    Each step is charged its full *serialized* size -- the JSON metadata
    (`kind` / `name` / `tool_id` / `turn`) plus its truncated content, not
    merely `len(content)` -- so steps with empty or tiny content still consume
    the budget. The per-turn `turns` array and the `source_items` accounting
    are charged and truncated the same way (a run with thousands of turns and
    no steps would otherwise write the whole array in full and blow the
    budget); both are drawn down before the steps, so once the running total
    crosses the record budget the remaining turns -- then accounting rows,
    then steps -- are dropped and `truncated` is set. Only the two small fixed
    summaries are always kept whole: `run_usage`, and the
    `source_item_counts` that state how many items were identified and how
    they were disposed of however few of their ids survived. A dropped
    accounting row also sets `source_items_truncated`, so a prefix of the ids
    is never readable as the whole set. `build_record` drops every
    `None`-valued field, so an absent prompt, empty system prompt, no-trigger
    skill set, codex's empty per-turn array, or a claude run's absent item
    accounting leaves its key off rather than storing a null.
    """
    limits = models.current_limits()
    headline = trajectory_headline(context, trajectory, metrics, redact, limits)
    budget = models.TrajectoryBudget(
        headline.serialized_size,
        limits.record_budget,
    )
    arrays = bounded_arrays(trajectory, budget, redact, limits)
    return sink.build_record(
        repo=context.repo,
        issue=context.issue,
        event="agent_trajectory",
        stage=context.stage,
        agent_role=context.agent_role,
        backend=context.backend,
        session_id=context.agent_result.session_id,
        review_round=context.review_round,
        retry_count=context.retry_count,
        user_input=headline.user_input,
        system_prompt=headline.system_prompt,
        tools=list(trajectory.tools) or None,
        skills_triggered=list(trajectory.skills.triggered) or None,
        skills_available=list(trajectory.skills.available) or None,
        run_usage=headline.run_usage,
        source_item_counts=headline.source_item_counts or None,
        turns=arrays.turns or None,
        source_items=arrays.source_items or None,
        source_items_truncated=arrays.source_items_truncated or None,
        steps=arrays.steps,
        output=headline.output,
        truncated=budget.truncated or None,
    )
