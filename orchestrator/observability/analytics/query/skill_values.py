# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The cell a skill fact is filed under, and the payload it is read from.

A skill fact is not a column. It rides in the `extras` JSONB blob of an
`agent_exit` row, so every reader here starts from a value a driver may hand
back three ways -- an adapted Python object, the raw JSON text, or nothing at
all because the key was never written. A name array collapses to a list of
strings and a name-to-level map to a dict of them, with a malformed blob
collapsing to an empty one rather than raising, because one bad `extras`
payload must not take a whole window's aggregate down with it.

A skill is identified by its name *and* the source level that defined it, so
the `develop` a repository checked in and the `develop` an operator installed
globally stay two cells rather than one blended average. A level is read off
the same row that named the skill, and a name the row's level map does not
cover reads `unknown` -- a record written before levels existed, or a claude
run whose stream names no source directory for the skills it lists, lands
under one spelling an operator can look up instead of a scattering of blanks.

The cohort is the other half. Every skill read groups by the same
`(repo, agent_role, backend)` triple, with a missing role or backend reading as
`unknown` rather than being dropped -- a run that recorded neither is still a
run the cohort's denominator counts. One cell type carries that triple, the
skill inside it, and the skill's level, so the two aggregates and the orderings
over them read a named field rather than each remembering the position a bare
tuple put it at.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, NamedTuple

from orchestrator.observability.analytics.query.raw_values import decoded_json
from orchestrator.observability.analytics.query.row_cells import row_value

# The cohort a cell is counted against, and the name/level pair one row
# reported a skill as.
SkillCohort = tuple[str, str, str]
SkillLevelPair = tuple[str, str]

# What an unrecorded grouping label and an unclassified skill both read as.
# One spelling for both because a page groups and sorts them the same way.
UNKNOWN_LABEL = "unknown"


class SkillCell(NamedTuple):
    """One cohort, and the skill definition counted inside it.

    The matrix and the adoption aggregate file their counts under the same
    shape and differ only in what a count means -- triggered runs on one
    side, adopting sessions on the other -- so both accumulate under this
    one cell rather than each declaring a tuple of its own.
    """

    repo: str
    agent_role: str
    backend: str
    skill: str
    level: str

    @property
    def cohort(self) -> SkillCohort:
        """The triple whose run count this cell reads against."""
        return (self.repo, self.agent_role, self.backend)


def as_skill_names(raw: Any) -> list[str]:
    """Coerce a JSONB skill-name array column into a list of strings.

    psycopg adapts a `jsonb` array to a Python list, so the common path
    is a passthrough; a driver / fixture that hands back the raw JSON
    text is tolerated too. ``None`` (the absent-key result of
    ``extras -> 'skills_...'``), a non-list payload, or a non-string
    element collapses to an empty list / is skipped so a malformed
    `extras` blob never raises mid-read.
    """
    decoded = decoded_json(raw)
    if not isinstance(decoded, (list, tuple)):
        return []
    return [name for name in decoded if isinstance(name, str)]


def as_skill_levels(raw: Any) -> dict[str, str]:
    """Coerce a JSONB name-to-source-level object into a string mapping.

    The map half of the same blob `as_skill_names` reads the array half
    of, and tolerant the same way: an absent key, a payload that is not an
    object, or an entry either half of which is not a string yields
    nothing rather than raising. A non-string level is dropped rather than
    carried, since an ordering that compares it against the levels beside
    it is what would raise.
    """
    decoded = decoded_json(raw)
    if not isinstance(decoded, dict):
        return {}
    return {
        name: level
        for name, level in decoded.items()
        if isinstance(name, str) and isinstance(level, str)
    }


def leveled_skills(
    raw_names: Any,
    raw_levels: Any,
    *,
    default_level: str = UNKNOWN_LABEL,
) -> frozenset[SkillLevelPair]:
    """Pair every recorded skill name with the level that defined it.

    The names decide which pairs exist and the map only classifies them, so
    a level recorded for a name the row never listed contributes no cell. A
    name the map leaves out takes `default_level`, which is what keeps an
    unclassified record's cells findable rather than scattered.
    """
    levels = as_skill_levels(raw_levels)
    return frozenset(
        (name, levels.get(name, default_level))
        for name in as_skill_names(raw_names)
    )


def label_or_unknown(raw: Any) -> str:
    """Read one grouping label, bucketing an unrecorded one under `unknown`."""
    if raw is None:
        return UNKNOWN_LABEL
    return str(raw)


def skill_cohort(row: Sequence[Any]) -> SkillCohort:
    """Normalize one row's repository, role, and backend cohort.

    The role and the backend are read positionally against a default, so a
    narrower row that carries neither still reports the cohort both label
    under `unknown`.
    """
    return (
        label_or_unknown(row[0]),
        label_or_unknown(row_value(row, 1, None)),
        label_or_unknown(row_value(row, 2, None)),
    )
