# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which runs one filter request keeps, out of the ones a read came back with.

A request arrives as the keyword fields a page names, every one optional. It is
narrowed once, and every run is then walked against that one normalized form.

Filtering only ever narrows what the read already handed over, so the order it
was handed in -- newest first, the file's own line order as the tiebreak -- is
the order it hands back. Every filter is conjunctive, and the questions are
asked cheapest first: the fixture drop is not a filter over a field at all but a
toggle over what an inherited file left behind, the scalar and multi-value
fields are single comparisons, and the free-text search comes last because it is
the one predicate that walks a run's whole text.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Unpack

from orchestrator.observability.trajectory_viewer import filter_models, filter_values
from orchestrator.observability.trajectory_viewer.runs import TrajectoryRun


def normalize_run_filters(
    options: filter_models.RunFilterOptions,
) -> filter_models.RunFilters:
    return filter_models.RunFilters(
        repo=options.repo,
        backends=filter_values.normalize_filter_values(options.backends),
        agent_roles=filter_values.normalize_filter_values(options.agent_roles),
        stages=filter_values.normalize_filter_values(options.stages),
        issue=options.issue,
        query=filter_values.normalize_filter_query(options.query),
        exclude_fixtures=options.exclude_fixtures,
    )


def matches_scalar_filters(
    run: TrajectoryRun,
    run_filters: filter_models.RunFilters,
) -> bool:
    return (run_filters.repo is None or run.repo == run_filters.repo) and (
        run_filters.issue is None or run.issue == run_filters.issue
    )


def matches_dimension_filters(
    run: TrajectoryRun,
    run_filters: filter_models.RunFilters,
) -> bool:
    return (
        (run_filters.backends is None or run.backend in run_filters.backends)
        and (run_filters.agent_roles is None or run.agent_role in run_filters.agent_roles)
        and (run_filters.stages is None or run.stage in run_filters.stages)
    )


def matches_run_filters(
    run: TrajectoryRun,
    run_filters: filter_models.RunFilters,
) -> bool:
    if run_filters.exclude_fixtures and run.is_fixture:
        return False
    if not matches_scalar_filters(run, run_filters):
        return False
    if not matches_dimension_filters(run, run_filters):
        return False
    return run_filters.query is None or filter_values.matches_query(run, run_filters.query)


def filter_runs(
    runs: Sequence[TrajectoryRun],
    **option_fields: Unpack[filter_models.RunFilterOptionFields],
) -> list[TrajectoryRun]:
    """Return runs matching every supplied filter while preserving order."""
    run_filters = normalize_run_filters(
        filter_models.RunFilterOptions(**option_fields),
    )
    return [run for run in runs if matches_run_filters(run, run_filters)]
