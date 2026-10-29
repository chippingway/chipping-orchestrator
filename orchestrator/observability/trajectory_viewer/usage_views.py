# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a run's tallies and its money read as, projected off the record.

Every accessor here answers from the run summary the sink already wrote rather
than re-adding the per-turn rows, because that summary's cost is the run's own
amount on its own basis -- a CLI-reported figure stays CLI-reported -- and the
turns are a claude-only detail of estimates a codex record does not carry at
all. Nothing here reprices a run either: a record whose cost states no basis
stays unknown. The sink writes that summary on every record, so one without it
is a hand-edited or damaged line, and each projection names what that leaves
unknown for its own type -- no model, a cost the record states no evidence for,
a token total nothing settles -- rather than raising over it.

The per-turn lookup is the one that reads the turns: it goes through the run's
cached index so a page walking a timeline can ask for each entry's turn in
turn without rescanning the tuple per entry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from orchestrator.observability.trajectory_viewer.models import TurnUsageView
from orchestrator.observability.usage import cost_evidence as usage_cost

if TYPE_CHECKING:
    from orchestrator.observability.trajectory_viewer.runs import TrajectoryRun


def tool_calls(run: TrajectoryRun) -> int:
    return sum(1 for step in run.steps if step.is_call)


def step_count(run: TrajectoryRun) -> int:
    return len(run.steps)


def model(run: TrajectoryRun) -> str:
    if run.run_usage is None or not run.run_usage.models:
        return ""
    return run.run_usage.models[0]


def cost_evidence(run: TrajectoryRun) -> usage_cost.CostEvidence:
    if run.run_usage is None:
        return usage_cost.recorded_cost({})
    return run.run_usage.cost_evidence


def total_tokens(run: TrajectoryRun) -> int | None:
    if run.run_usage is None:
        return None
    return run.run_usage.total_tokens


def usage_for_turn(
    run: TrajectoryRun,
    turn: int | None,
) -> TurnUsageView | None:
    if turn is None:
        return None
    return run._turn_map.get(turn)
