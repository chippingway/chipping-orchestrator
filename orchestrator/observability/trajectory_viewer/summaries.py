# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The headline counts a filtered run set is read back as.

Every tile the page's KPI strip carries is totalled here, and off the runs that
survived filtering rather than off the file, so what an operator reads is the
window they narrowed to. Two of the counts are distinct rather than summed: an
issue is one issue however many runs it took, and a repository is counted only
where a run named one, because a record written without one is not a repository
of its own. The money is the same care in the other direction: each run's cost
is folded by the usage owner's ``reduce_costs``, which sums every basis on its
own and keeps the weakest completeness any run states. A run whose usage was
left unpriced therefore makes the total an incomplete subtotal, and a run whose
cost states no evidence -- an earlier build's record, or a damaged line with no
usage summary at all -- leaves its completeness unknown, rather than either
adding a zero that would read as free work. The runs that did each are
counted beside the total, so the tile can say what a subtotal is missing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from orchestrator.observability.trajectory_viewer.runs import TrajectoryRun
from orchestrator.observability.usage import cost_evidence as usage_cost

# What an empty fold reads as: nothing ran, so nothing was used.
_NO_RUNS_COST = usage_cost.reduce_costs(())


@dataclass(frozen=True)
class TrajectorySummary:
    """Headline counts for the filtered run set."""

    total_runs: int = 0
    distinct_issues: int = 0
    distinct_repos: int = 0
    total_tool_calls: int = 0
    truncated_runs: int = 0
    total_cost: usage_cost.CostEvidence = _NO_RUNS_COST
    incomplete_cost_runs: int = 0
    unknown_cost_runs: int = 0


def summarize(runs: Sequence[TrajectoryRun]) -> TrajectorySummary:
    """Build headline counts for a filtered run set."""
    costs = tuple(run.cost_evidence for run in runs)
    completeness = [cost.completeness for cost in costs]
    return TrajectorySummary(
        total_runs=len(runs),
        distinct_issues=len({(run.repo, run.issue) for run in runs}),
        distinct_repos=len({run.repo for run in runs if run.repo}),
        total_tool_calls=sum(run.tool_calls for run in runs),
        truncated_runs=sum(1 for run in runs if run.truncated),
        total_cost=usage_cost.reduce_costs(costs),
        incomplete_cost_runs=completeness.count(usage_cost.INCOMPLETE),
        unknown_cost_runs=completeness.count(usage_cost.UNKNOWN),
    )
