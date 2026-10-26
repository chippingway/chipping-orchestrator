# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How often a role-and-backend cohort loaded any skill at all.

The coarsest of the three skill reads: one row per `(agent_role, backend)`, and
no skill name anywhere in it. What it answers is whether a cohort reaches for
skills, which is why the denominator is every finished run rather than the runs
that loaded something -- a cohort that never triggers is a real zero rate, not
an absent row, and dropping it would hide exactly the case the panel exists to
surface.

Two counters ride beside that denominator because they answer different
questions. `skill_runs` tests the `skills_triggered` key for presence, so it
counts the runs that loaded at least one skill -- the recorder drops the key
rather than writing an empty list; `total_triggers` sums the recorded count, so
a run that loaded three contributes three.

The scan stays on the events table: the `extras` blob these fields live in is
not carried by the day-bucketed rollup, and the caller's own event selection is
dropped from the window before the finished-run condition is spliced in, since
a selection naming other events would contradict the pin.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from orchestrator.observability.analytics.query.conditions import (
    AGENT_EXIT_CONDITION,
    append_where_condition,
)
from orchestrator.observability.analytics.query.execution import ReadQuery
from orchestrator.observability.analytics.query.filters import WindowFilters
from orchestrator.observability.analytics.query.predicates import build_window_where
from orchestrator.observability.analytics.query.skill_models import SkillTriggerRateRow
from orchestrator.observability.analytics.query.skill_values import label_or_unknown


def skill_trigger_rate_sql(clause: str) -> str:
    """Build the per-cohort run, loading-run, and trigger-count scan."""
    return (
        "SELECT "
        "COALESCE(agent_role, 'unknown') AS role_label, "
        "COALESCE(backend, 'unknown') AS backend_label, "
        "COUNT(*) AS runs, "
        "COUNT(*) FILTER "
        "  (WHERE extras -> 'skills_triggered' IS NOT NULL) AS skill_runs, "
        "COALESCE(SUM((extras ->> 'skills_triggered_count')::int), 0) "
        "  AS total_triggers "
        f"FROM analytics_events{clause} "
        "GROUP BY role_label, backend_label "
        "ORDER BY skill_runs DESC, runs DESC, role_label ASC, "
        "backend_label ASC"
    )


def skill_trigger_rate_from_row(row: Sequence[Any]) -> SkillTriggerRateRow:
    """Project one per-cohort trigger-rate row onto its result model."""
    return SkillTriggerRateRow(
        agent_role=label_or_unknown(row[0]),
        backend=label_or_unknown(row[1]),
        runs=int(row[2] or 0),
        skill_runs=int(row[3] or 0),
        total_triggers=int(row[4] or 0),
    )


def skill_trigger_rate_rows(
    query: ReadQuery,
    filters: WindowFilters,
) -> list[SkillTriggerRateRow]:
    """Return one trigger-rate row per role-and-backend cohort."""
    event_where, event_bindings = build_window_where(filters.without_events())
    clause = append_where_condition(event_where, AGENT_EXIT_CONDITION)
    rows = query.select(skill_trigger_rate_sql(clause), event_bindings)
    return [skill_trigger_rate_from_row(row) for row in rows]
