# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How many sessions that could have used a skill actually did.

The denominator is what separates this read from the matrix beside it. A
matrix cell counts runs against the runs of its cohort; an adoption cell counts
*sessions that were offered a skill* against the ones that loaded it, so a
skill offered to two sessions and used by one reads 50% no matter how many
times either session ran. Both are needed because a busy session repeating one
skill and many sessions each reaching for it once look identical by run count.

A cell carries its window diagnostics beside that ratio rather than folding
them in. `invocations` is the cohort's whole run count, `load_rows` the window
runs that loaded the skill, and `incidental` the ones that only referenced it
in passing -- a path mentioned, not a skill read. None of the three moves the
adoption ratio; they exist so a cell showing one adopting session out of forty
can be read as either a quiet skill or a busy one nobody keeps using.

A cell is keyed by the skill's source level as well as its name, so a session
offered a repository's own `develop` and one offered a global skill of that
name are two cells rather than one blended ratio. A record that named no level
-- a claude run, whose stream names no source directory -- is filed at the
level the repository's catalog offers that name at, where it offers exactly
one; the catalog scan behind that lookup is a third read beside the two session
scans, narrowed as the repository-level record it reads requires and documented
on the owner that runs it. The fill reaches every kind of evidence a cell is
built from, because resolving the loads and leaving the offers alone would move
a session out of the denominator it belongs in.

Which cells exist is the union of three observations, not just the availability
set: a purely incidental reference and a load whose session reported a
different availability set, or none at all, each get a row too, so an
observation is never dropped for disagreeing with the denominator it would have
been filed under. Such a row carries no session it could count against, which
is what leaves its rate undefined rather than claiming an offer nobody reported.
Ordering puts the widest reach first -- sessions offered, then sessions
adopting, then the busiest cohort -- so the cap keeps the cells a reader would
have looked at first.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from orchestrator.observability.analytics.query.execution import ReadQuery
from orchestrator.observability.analytics.query.filters import WindowFilters
from orchestrator.observability.analytics.query.skill_models import SkillAdoptionRow
from orchestrator.observability.analytics.query.skill_provenance import (
    repo_skill_provenance,
)
from orchestrator.observability.analytics.query.skill_sessions import (
    SessionEvidence,
    SkillWindowRun,
    skill_session_evidence,
    skill_window_rows,
)
from orchestrator.observability.analytics.query.skill_values import (
    SkillCell,
    SkillCohort,
)

SKILL_ADOPTION_ROW_LIMIT = 100


@dataclass
class SkillAdoption:
    """Per-`(repo, role, backend, skill, level)` counts and diagnostics.

    `cohort_runs` is the window `agent_exit` invocation count per
    `(repo, role, backend)` cohort -- every run, whether or not it loaded a
    skill -- so each skill's adoption reads against the cohort's run volume.
    `load_rows` / `incidental` count the window runs that loaded /
    incidentally referenced a given skill.
    """

    cohort_runs: dict[SkillCohort, int] = field(default_factory=dict)
    sessions: dict[SkillCell, int] = field(default_factory=dict)
    adopted: dict[SkillCell, int] = field(default_factory=dict)
    load_rows: dict[SkillCell, int] = field(default_factory=dict)
    incidental: dict[SkillCell, int] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        window_runs: Sequence[SkillWindowRun],
        evidence: dict[str, SessionEvidence],
    ) -> SkillAdoption:
        counts = cls()
        session_cohorts: dict[str, set[SkillCohort]] = {}
        for run in window_runs:
            counts._observe_window(run)
            session_cohorts.setdefault(run.session_key, set()).add(run.cohort)
        counts._count_sessions(session_cohorts, evidence)
        return counts

    def keys(self) -> set[SkillCell]:
        # Every available cell plus any cell that only shows in the window
        # diagnostics (a purely incidental reference, or a load whose session
        # reported a different availability set or none) so no observation is
        # dropped.
        keys = set(self.sessions)
        keys.update(self.load_rows)
        keys.update(self.incidental)
        return keys

    def order_key(self, key: SkillCell) -> list:
        # Widest reach first -- sessions offered, then sessions adopting, then
        # the busiest cohort -- with the cell's naming columns as the tiebreak.
        return [
            -self.sessions.get(key, 0),
            -self.adopted.get(key, 0),
            -self.cohort_runs.get(key.cohort, 0),
            *key,
        ]

    def as_row(self, key: SkillCell) -> SkillAdoptionRow:
        return SkillAdoptionRow(
            repo=key.repo,
            skill=key.skill,
            agent_role=key.agent_role,
            backend=key.backend,
            level=key.level,
            sessions=self.sessions.get(key, 0),
            adopted=self.adopted.get(key, 0),
            invocations=self.cohort_runs.get(key.cohort, 0),
            load_rows=self.load_rows.get(key, 0),
            incidental=self.incidental.get(key, 0),
        )

    def _observe_window(self, run: SkillWindowRun) -> None:
        cohort = run.cohort
        self.cohort_runs[cohort] = self.cohort_runs.get(cohort, 0) + 1
        for loaded in run.triggered:
            key = SkillCell(*cohort, *loaded)
            self.load_rows[key] = self.load_rows.get(key, 0) + 1
        for referenced in run.incidental:
            key = SkillCell(*cohort, *referenced)
            self.incidental[key] = self.incidental.get(key, 0) + 1

    def _count_sessions(
        self,
        session_cohorts: dict[str, set[SkillCohort]],
        evidence: dict[str, SessionEvidence],
    ) -> None:
        for session_key, cohorts in session_cohorts.items():
            session = evidence.get(session_key)
            if session is None:
                continue
            self._count_session(cohorts, session)

    def _count_session(
        self,
        cohorts: set[SkillCohort],
        session: SessionEvidence,
    ) -> None:
        for cohort in cohorts:
            for offered in session.available:
                key = SkillCell(*cohort, *offered)
                self.sessions[key] = self.sessions.get(key, 0) + 1
                if offered in session.adopted:
                    self.adopted[key] = self.adopted.get(key, 0) + 1


def skill_adoption_rows(
    query: ReadQuery,
    filters: WindowFilters,
    limit: int,
) -> list[SkillAdoptionRow]:
    """Return the per-session adoption cells, ranked and capped."""
    provenance = repo_skill_provenance(query, filters)
    window_runs = skill_window_rows(query, filters, provenance)
    evidence = skill_session_evidence(query, filters, window_runs, provenance)
    counts = SkillAdoption.build(window_runs, evidence)
    keys = sorted(counts.keys(), key=counts.order_key)
    if limit > 0:
        keys = keys[:limit]
    return [counts.as_row(key) for key in keys]
