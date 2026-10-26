# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a repository offers a skill at, and the blank level that fills from it.

A run reports the skills it loaded, but not always the level each was defined
at: a claude stream names the skills it pulled without naming a source
directory for any of them, so every one of its loads arrives unclassified.
Read against the name alone that load becomes a cell of its own -- a
`develop` at `unknown` sitting beside the `develop` at `project` a classifying
record put there -- and one definition's use is split across two rows that
neither add up nor read as the same skill.

`repo_skill_catalog` is what closes that gap, because it enumerates a
repository's own checked-in definitions and the level each was classified at. A
name that repository offers at exactly one level has one definition an
unclassified load could have come from, so the load is filed there. Anything
less certain is left where it is: a name the catalog never offered, or one it
offers at two levels, stays `unknown` rather than being guessed into a cell it
may not belong to. The lookup is per repository, so a level another repository
classified a same-named skill at never reaches this one's runs.

What a run did record is never overwritten. An explicit level is an observation
from the run itself and outranks the repository-wide inference, so a globally
installed `develop` a run named `user` keeps that level even where the
repository checks in a `develop` of its own.

Both per-skill reads resolve here, and each resolves every category of evidence
it gathers: the loads a trigger cell counts, and the window loads, the
incidental references, and the earlier offers and loads an adoption cell
reads a session across. Resolving one category and not another is what would
leave a session offered a `develop` it is never credited with loading, so the
rule has to reach all of them or none.

The scan behind all of this is filtered differently from the run scans beside
it. A catalog record is a repository-level fact -- no issue, no stage, and
written whenever the catalog was last scanned -- so pushing the window, issue,
or stage selection onto it would drop every catalog row and leave both the
padding and the resolution with nothing to read. Only a name the record
classified is on offer: the producer classifies every definition it enumerates,
so a name its level map leaves out names no definition -- it pads no cell and
settles no unclassified load, rather than being guessed into a level.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from orchestrator.observability.analytics.query.conditions import (
    append_where_condition,
)
from orchestrator.observability.analytics.query.execution import ReadQuery
from orchestrator.observability.analytics.query.filters import WindowFilters
from orchestrator.observability.analytics.query.predicates import build_window_where
from orchestrator.observability.analytics.query.skill_values import (
    UNKNOWN_LABEL,
    SkillLevelPair,
    leveled_skills,
)

# The levels one repository classified each name it offers at.
_CatalogLevels = dict[str, frozenset[str]]


def skill_catalog_rows(
    query: ReadQuery,
    filters: WindowFilters,
) -> list[tuple]:
    """Scan the repository-level catalog records provenance is read from."""
    catalog_where, catalog_bindings = build_window_where(filters.catalog_scope())
    clause = append_where_condition(
        catalog_where,
        "event = 'repo_skill_catalog'",
    )
    return query.select(
        "SELECT repo, "
        "extras -> 'skills_available' AS skills_available, "
        "extras -> 'skill_levels' AS skill_levels "
        f"FROM analytics_events{clause}",
        catalog_bindings,
    )


def skill_catalog(rows: Sequence[tuple]) -> dict[str, set[SkillLevelPair]]:
    """Union every name a repository's catalog records classified into one set."""
    catalog: dict[str, set[SkillLevelPair]] = {}
    for row in rows:
        offered = catalog.setdefault(str(row[0]), set())
        offered.update(
            pair for pair in leveled_skills(row[1], row[2])
            if pair[1] != UNKNOWN_LABEL
        )
    return catalog


def _levels_by_name(offered: Iterable[SkillLevelPair]) -> _CatalogLevels:
    """Group one repository's offered pairs by the name each classifies."""
    by_name: dict[str, set[str]] = {}
    for skill, level in offered:
        by_name.setdefault(skill, set()).add(level)
    return {name: frozenset(levels) for name, levels in by_name.items()}


@dataclass(frozen=True)
class SkillProvenance:
    """What each repository's catalog offers, indexed both ways it is asked.

    `offered` answers the padding question -- which definitions a repository
    puts on offer -- and `levels` the resolution one, narrowing a name to the
    levels that repository classified it at so a load carrying none can be
    filed under the single candidate when there is exactly one.
    """

    offered: dict[str, frozenset[SkillLevelPair]] = field(default_factory=dict)
    levels: dict[str, _CatalogLevels] = field(default_factory=dict)

    @classmethod
    def from_catalog(
        cls,
        catalog: Mapping[str, set[SkillLevelPair]],
    ) -> SkillProvenance:
        """Index one repository-to-offered-set catalog by name as well."""
        return cls(
            offered={
                repo: frozenset(pairs) for repo, pairs in catalog.items()
            },
            levels={
                repo: _levels_by_name(pairs) for repo, pairs in catalog.items()
            },
        )

    def offers(self, repo: str) -> frozenset[SkillLevelPair]:
        """The definitions a repository's catalog put on offer."""
        return self.offered.get(repo, frozenset())

    def resolve_level(self, repo: str, skill: str, level: str) -> str:
        """Fill one unclassified level from the repository's catalog.

        An explicit level is returned untouched, since what the run itself
        observed outranks a repository-wide inference. An unclassified one
        takes the catalog's level for that name only where the repository
        offers the name at exactly one -- a name it never offered, or one it
        offers at two levels, stays `unknown`, which is a cell an operator
        can still look up rather than a guess between two definitions.
        """
        if level != UNKNOWN_LABEL:
            return level
        candidates = self.levels.get(repo, {}).get(skill, frozenset())
        if len(candidates) != 1:
            return level
        return next(iter(candidates))

    def resolve(
        self,
        repo: str,
        loaded: Iterable[SkillLevelPair],
    ) -> frozenset[SkillLevelPair]:
        """Resolve every pair one row reported against the repository."""
        return frozenset(
            (skill, self.resolve_level(repo, skill, level))
            for skill, level in loaded
        )

    def resolve_row(
        self,
        repo: str,
        raw_names: Any,
        raw_levels: Any,
    ) -> frozenset[SkillLevelPair]:
        """Pair one row's names with their levels, resolving the blanks.

        The one step every reader takes over a name array and the level map
        beside it, so a load, an incidental reference, and a session's offered
        set are all read and resolved the same way rather than each pairing
        first and remembering separately to resolve after.
        """
        return self.resolve(repo, leveled_skills(raw_names, raw_levels))


def repo_skill_provenance(
    query: ReadQuery,
    filters: WindowFilters,
) -> SkillProvenance:
    """Scan the catalog records and index what each repository offers."""
    return SkillProvenance.from_catalog(
        skill_catalog(skill_catalog_rows(query, filters)),
    )
