# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The shapes one filter request is made of, and the values it is offered.

``RunFilterOptionFields`` is the keywords a request is called with, every one
optional, and ``RunFilterOptions`` the same fields with the default each omitted
one reads as. ``RunFilters`` is what that becomes once every multi-value
selection has been narrowed to a set and the free-text needle folded and
stripped, so a run is walked against values that were normalized once for the
whole read rather than once per run.

``FilterOptions`` is the other direction: the distinct values a page may offer,
collected off the runs it already read rather than declared, so a dropdown only
ever holds a value some run actually carries.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypedDict


class RunFilterOptionFields(TypedDict, total=False):
    repo: str | None
    backends: Sequence[str] | None
    agent_roles: Sequence[str] | None
    stages: Sequence[str] | None
    issue: int | None
    query: str | None
    exclude_fixtures: bool


@dataclass(frozen=True)
class RunFilters:
    repo: str | None
    backends: frozenset[str] | None
    agent_roles: frozenset[str] | None
    stages: frozenset[str] | None
    issue: int | None
    query: str | None
    exclude_fixtures: bool


@dataclass(frozen=True)
class FilterOptions:
    """Distinct filter values across a set of runs, each sorted."""

    repos: tuple[str, ...] = ()
    backends: tuple[str, ...] = ()
    agent_roles: tuple[str, ...] = ()
    stages: tuple[str, ...] = ()


@dataclass(frozen=True)
class RunFilterOptions:
    """The keyword fields :func:`filter_runs` was called with, defaulted."""

    repo: str | None = None
    backends: Sequence[str] | None = None
    agent_roles: Sequence[str] | None = None
    stages: Sequence[str] | None = None
    issue: int | None = None
    query: str | None = None
    exclude_fixtures: bool = False
