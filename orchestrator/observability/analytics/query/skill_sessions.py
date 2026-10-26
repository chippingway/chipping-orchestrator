# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One logical session's identity, and the evidence gathered under it.

Adoption is a per-session question, not a per-run one: an agent that resumes
four times has adopted a skill once, not four times. A row's session is
therefore its `resume_session_id` when it has one -- a continuation belongs to
the session it continued -- its own `session_id` otherwise, and its primary key
when it carries neither, so a run whose CLI yielded no id stays its own session
rather than merging into one anonymous bucket. The primary key is stable across
both scans below, so a shared ID-less row keys the same in each.

Two scans here feed one aggregate, and they are scoped differently on purpose.
The window scan is the reporting window as the caller selected it, and it
decides *which* sessions are counted at all. The history scan then reads every
finished run of those sessions before the window ends -- dropping the start
bound and the stage filter, keeping the end bound -- because a skill loaded in
an earlier stage or before the window still means the session adopted it, while
a load after the window ends has not happened yet from this page's point of
view. History rows for sessions the window never saw are dropped: their
evidence belongs to a window nobody asked about.

What a session accumulates is set-based on both sides, so folding a row twice
-- a window row is also returned by the history scan -- never double counts.
Every skill it accumulates is a name/level pair read off the row that reported
it, so an offer and a load are matched by provenance as well as by name.
Availability is only ever what a row's `skills_available` array listed. The
recorder drops that key wherever the run reported no offered set -- tracking
off, or a stream that named none -- so a session none of whose rows carried it
has unknown availability, and a load is never read as the offer it would have
needed: such a session contributes no denominator, while its loads stay
visible in the window diagnostics.

A level the row left blank is filled from the repository's catalog before the
pair is accumulated, and the caller hands that lookup in already scanned so
both these scans read it the same. Every category takes the step -- a window
load, an incidental reference, and a history row's offered set and loads alike
-- because filling one and not another is what would leave a session offered a
`develop` at one level and credited with loading it at another, which reads as
an offer nobody took up next to a load nobody was offered.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from orchestrator.observability.analytics.query.conditions import (
    AGENT_EXIT_CONDITION,
    append_where_condition,
)
from orchestrator.observability.analytics.query.execution import ReadQuery
from orchestrator.observability.analytics.query.filters import WindowFilters
from orchestrator.observability.analytics.query.predicates import build_window_where
from orchestrator.observability.analytics.query.skill_provenance import SkillProvenance
from orchestrator.observability.analytics.query.skill_values import (
    SkillCohort,
    SkillLevelPair,
    label_or_unknown,
    skill_cohort,
)

# Where the identity columns sit in both scans' SELECT lists, which share their
# leading six columns so one session key is read the same way off either row.
SESSION_RESUME_INDEX = 3
SESSION_ID_INDEX = 4
SESSION_ROW_INDEX = 5


def skill_session_key(row: Sequence[Any]) -> str:
    """Identify a row's logical session: resume id, then session id, then row.

    A resumed run continues the session it resumed *from*, so the
    `resume_session_id` groups a continuation with its origin; a fresh run
    keys on its own `session_id`. A row carrying neither (a CLI run that
    yielded no id) falls back to its primary key so every ID-less row stays
    its own session -- never silently merged into a single anonymous bucket.
    The primary key is stable across the window and history scans, so a
    shared ID-less row keys the same in both.
    """
    resume = row[SESSION_RESUME_INDEX]
    if isinstance(resume, str) and resume:
        return resume
    session = row[SESSION_ID_INDEX]
    if isinstance(session, str) and session:
        return session
    return f"row:{row[SESSION_ROW_INDEX]}"


@dataclass
class SessionEvidence:
    """One logical session's availability + load evidence before window end.

    `available` unions every `skills_available` set the session reported,
    and `adopted` the skills it loaded across its rows. Both hold name/level
    pairs, so a load is credited to the offer of the same provenance rather
    than to a same-named skill from another level, and both are set-based,
    so folding the same row twice (a window row is also returned by the
    history scan) never double-counts. Nothing moves a load into
    `available`: a session that reported no offered set has none.
    """

    available: set[SkillLevelPair] = field(default_factory=set)
    adopted: set[SkillLevelPair] = field(default_factory=set)

    def observe(
        self,
        *,
        available: Iterable[SkillLevelPair],
        triggered: Iterable[SkillLevelPair],
    ) -> None:
        self.available.update(available)
        self.adopted.update(triggered)

    def observe_history(
        self,
        row: Sequence[Any],
        provenance: SkillProvenance,
    ) -> None:
        """Fold one history scan row's offered set and loads into this session.

        Both are resolved against the row's own repository, so a session
        offered a name its record left unclassified is credited with loading
        that same definition rather than an `unknown` one beside it.
        """
        repo = label_or_unknown(row[0])
        levels = row[8]
        self.observe(
            available=provenance.resolve_row(repo, row[6], levels),
            triggered=provenance.resolve_row(repo, row[7], levels),
        )


@dataclass(frozen=True)
class SkillWindowRun:
    """One reporting-window `agent_exit` row's session + skill fields."""

    session_key: str
    cohort: SkillCohort
    triggered: frozenset[SkillLevelPair]
    incidental: frozenset[SkillLevelPair]


def skill_window_run(
    row: Sequence[Any],
    provenance: SkillProvenance,
) -> SkillWindowRun:
    """Project one window scan row onto its session, cohort, and skills.

    Both the loads and the incidental references are resolved against the
    row's own repository, so a claude run's unclassified names reach the
    same cell whichever of the two categories reported them.
    """
    cohort = skill_cohort(row)
    levels = row[8]
    return SkillWindowRun(
        session_key=skill_session_key(row),
        cohort=cohort,
        triggered=provenance.resolve_row(cohort[0], row[6], levels),
        incidental=provenance.resolve_row(cohort[0], row[7], levels),
    )


def skill_window_rows(
    query: ReadQuery,
    filters: WindowFilters,
    provenance: SkillProvenance,
) -> list[SkillWindowRun]:
    """Scan the finished runs the caller's window selected."""
    window_where, window_bindings = build_window_where(filters.without_events())
    clause = append_where_condition(window_where, AGENT_EXIT_CONDITION)
    rows = query.select(
        "SELECT repo, "
        "COALESCE(agent_role, 'unknown') AS role_label, "
        "COALESCE(backend, 'unknown') AS backend_label, "
        "resume_session_id, session_id, id, "
        "extras -> 'skills_triggered' AS skills_triggered, "
        "extras -> 'skills_incidental' AS skills_incidental, "
        "extras -> 'skill_levels' AS skill_levels "
        f"FROM analytics_events{clause}",
        window_bindings,
    )
    return [skill_window_run(row, provenance) for row in rows]


def skill_history_rows(
    query: ReadQuery,
    filters: WindowFilters,
) -> list[tuple]:
    """Scan every finished run before the window ends, at any stage."""
    history_where, history_bindings = build_window_where(
        filters.historical_scope(),
    )
    clause = append_where_condition(history_where, AGENT_EXIT_CONDITION)
    return query.select(
        "SELECT repo, "
        "COALESCE(agent_role, 'unknown') AS role_label, "
        "COALESCE(backend, 'unknown') AS backend_label, "
        "resume_session_id, session_id, id, "
        "extras -> 'skills_available' AS skills_available, "
        "extras -> 'skills_triggered' AS skills_triggered, "
        "extras -> 'skill_levels' AS skill_levels "
        f"FROM analytics_events{clause}",
        history_bindings,
    )


def skill_session_evidence(
    query: ReadQuery,
    filters: WindowFilters,
    window_runs: Sequence[SkillWindowRun],
    provenance: SkillProvenance,
) -> dict[str, SessionEvidence]:
    """Gather each active session's before-window-end availability + loads.

    Seeds one `SessionEvidence` per window session (a window row is itself
    evidence observed before the end) so only sessions active in the window
    are tracked, then folds in the history scan -- every `agent_exit` row
    for those sessions before the window end, ignoring the window start and
    stage filter -- so a load from a prior stage or from before the window
    stays visible. History rows for sessions not seen in the window are
    dropped: their evidence must not leak into the aggregate.
    """
    evidence: dict[str, SessionEvidence] = {}
    for run in window_runs:
        evidence.setdefault(run.session_key, SessionEvidence()).observe(
            available=(),
            triggered=run.triggered,
        )
    for row in skill_history_rows(query, filters):
        session = evidence.get(skill_session_key(row))
        if session is not None:
            session.observe_history(row, provenance)
    return evidence
