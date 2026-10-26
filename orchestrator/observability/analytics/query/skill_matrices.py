# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which of a repository's offered skills each cohort actually triggered.

Two scans, because the answer needs a universe as well as observations. The
runs scan here says what fired; the catalog scan under `skill_provenance` says
what was on offer, and without it a skill nobody triggered has no row at all --
which reads as "not applicable here" when the point is that it was available
and went unused. Padding the observed cells with the catalog is what turns
absence into an explicit zero.

Only the runs scan takes the caller's selection, and it takes all of it minus
the event filter, which the finished-run condition replaces. The catalog scan
beside it is narrowed further, for reasons that belong to the record rather
than to this aggregate and are documented on the owner that runs it.

Padding is per cohort, not per repository: every cohort that ran gets the
repository's catalog skills, so a decomposer or question cohort that triggers
nothing still reports its zeros against its own run count. A skill that fired
but is not in the catalog keeps its observed cell -- what ran is not discarded
for disagreeing with what was offered -- it simply gets no zeros elsewhere.
Ordering puts the most-triggered cells first, then the busiest cohort, then the
name tiebreak, so the cap keeps the rows a reader would have looked at first.

A cell is keyed by the source level a skill was defined at as well as by its
name, so a repository's own `develop` and a same-named global one are padded
and counted apart. A run that named no level for a skill it loaded is filed at
the level the repository's catalog offers that name at, where it offers exactly
one -- which is what lands a claude run's loads inside the padded cell for that
definition instead of beside it as a second `unknown` row.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from orchestrator.observability.analytics.query.conditions import (
    AGENT_EXIT_CONDITION,
    append_where_condition,
)
from orchestrator.observability.analytics.query.execution import ReadQuery
from orchestrator.observability.analytics.query.filters import WindowFilters
from orchestrator.observability.analytics.query.predicates import build_window_where
from orchestrator.observability.analytics.query.skill_models import SkillTriggerMatrixRow
from orchestrator.observability.analytics.query.skill_provenance import (
    SkillProvenance,
    repo_skill_provenance,
)
from orchestrator.observability.analytics.query.skill_values import (
    SkillCell,
    SkillCohort,
    skill_cohort,
)

SKILL_MATRIX_ROW_LIMIT = 100


def skill_run_rows(
    query: ReadQuery,
    filters: WindowFilters,
) -> list[tuple]:
    """Scan the window's finished runs and the skills each one triggered."""
    run_where, run_bindings = build_window_where(filters.without_events())
    clause = append_where_condition(run_where, AGENT_EXIT_CONDITION)
    return query.select(
        "SELECT repo, "
        "COALESCE(agent_role, 'unknown') AS role_label, "
        "COALESCE(backend, 'unknown') AS backend_label, "
        "extras -> 'skills_triggered' AS skills_triggered, "
        "extras -> 'skill_levels' AS skill_levels "
        f"FROM analytics_events{clause}",
        run_bindings,
    )


@dataclass
class SkillMatrixCounts:
    """Run and trigger counts used to assemble the skill matrix."""

    cohort_runs: dict[SkillCohort, int] = field(default_factory=dict)
    skill_runs: dict[SkillCell, int] = field(default_factory=dict)

    @classmethod
    def from_rows(
        cls,
        rows: Sequence[tuple],
        provenance: SkillProvenance,
    ) -> SkillMatrixCounts:
        counts = cls()
        for row in rows:
            counts._observe(row, provenance)
        return counts

    def matrix_keys(self, provenance: SkillProvenance) -> set[SkillCell]:
        keys = set(self.skill_runs)
        for cohort in self.cohort_runs:
            for offered in provenance.offers(cohort[0]):
                keys.add(SkillCell(*cohort, *offered))
        return keys

    def order_key(self, key: SkillCell) -> list:
        # Most-triggered cells first, then the busiest cohort, then the cell's
        # own naming columns as the stable tiebreak.
        return [
            -self.skill_runs.get(key, 0),
            -self.cohort_runs.get(key.cohort, 0),
            *key,
        ]

    def as_row(self, key: SkillCell) -> SkillTriggerMatrixRow:
        return SkillTriggerMatrixRow(
            repo=key.repo,
            skill=key.skill,
            agent_role=key.agent_role,
            backend=key.backend,
            level=key.level,
            runs=self.cohort_runs.get(key.cohort, 0),
            skill_runs=self.skill_runs.get(key, 0),
        )

    def _observe(
        self,
        row: Sequence[Any],
        provenance: SkillProvenance,
    ) -> None:
        cohort = skill_cohort(row)
        self.cohort_runs[cohort] = self.cohort_runs.get(cohort, 0) + 1
        for loaded in provenance.resolve_row(cohort[0], row[3], row[4]):
            key = SkillCell(*cohort, *loaded)
            self.skill_runs[key] = self.skill_runs.get(key, 0) + 1


def skill_trigger_matrix_rows(
    query: ReadQuery,
    filters: WindowFilters,
    limit: int,
) -> list[SkillTriggerMatrixRow]:
    """Return the observed and catalog-padded cells, ranked and capped."""
    provenance = repo_skill_provenance(query, filters)
    counts = SkillMatrixCounts.from_rows(skill_run_rows(query, filters), provenance)
    keys = sorted(counts.matrix_keys(provenance), key=counts.order_key)
    if limit > 0:
        keys = keys[:limit]
    return [counts.as_row(key) for key in keys]
