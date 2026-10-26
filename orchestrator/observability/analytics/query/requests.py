# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The keyword call a caller writes, bound into the request a family reads.

Every public read is called by keyword -- `start=`, `events=`, `conn=` -- and
each family accepts a slightly different list. The signatures here are that
vocabulary, declared once and composed from the same parameter groups, so the
defaults a caller relies on (an omitted `limit`, `sort_by="last_seen"`, a zero
hour offset) are stated in one place rather than per family.

`bind_read_request` is what turns one such call into the typed request: it
binds against the family's signature, applies those defaults, and sorts the
arguments into the filters, the connection, and the options. A family then asks
this module for the two projections it needs -- the resolved connection to run
on, and the SQL filter model to build a predicate from -- rather than reading
the caller's keywords a second time.
"""

from __future__ import annotations

import inspect
from typing import Any

from orchestrator.observability.analytics.query.execution import ReadQuery
from orchestrator.observability.analytics.query.filters import WindowFilters
from orchestrator.observability.analytics.query.request_models import (
    ReadConnection,
    ReadFilters,
    ReadOptions,
    ReadRequest,
)

LIMIT_FIELD = "limit"
RECENT_EXIT_LIMIT = 50


def _keyword(name: str, default: Any = None) -> inspect.Parameter:
    return inspect.Parameter(
        name,
        inspect.Parameter.KEYWORD_ONLY,
        default=default,
    )


_SOURCE_PARAMETERS = (
    _keyword("db_url"),
    _keyword("connect"),
    _keyword("conn"),
)
_FILTER_PARAMETERS = (
    _keyword("start"),
    _keyword("end"),
    _keyword("repo"),
    _keyword("events"),
    _keyword("stages"),
    _keyword("issue"),
)
SOURCE_READ_SIGNATURE = inspect.Signature(_SOURCE_PARAMETERS)
FILTERED_READ_SIGNATURE = inspect.Signature((*_FILTER_PARAMETERS, *_SOURCE_PARAMETERS))
RECENT_EXITS_SIGNATURE = inspect.Signature(
    (
        _keyword(LIMIT_FIELD, RECENT_EXIT_LIMIT),
        *_FILTER_PARAMETERS,
        *_SOURCE_PARAMETERS,
    )
)
ISSUES_SIGNATURE = inspect.Signature(
    (
        *_FILTER_PARAMETERS,
        _keyword(LIMIT_FIELD, 100),
        _keyword("sort_by", "last_seen"),
        *_SOURCE_PARAMETERS,
    )
)
ISSUE_EVENTS_SIGNATURE = inspect.Signature(
    (
        _keyword("repo", inspect.Parameter.empty),
        _keyword("issue", inspect.Parameter.empty),
        _keyword("start"),
        _keyword("end"),
        _keyword("events"),
        _keyword("stages"),
        *_SOURCE_PARAMETERS,
    )
)
LIMITED_READ_SIGNATURE = inspect.Signature(
    (
        *_FILTER_PARAMETERS,
        _keyword(LIMIT_FIELD, 100),
        *_SOURCE_PARAMETERS,
    )
)
HEATMAP_SIGNATURE = inspect.Signature(
    (
        *_FILTER_PARAMETERS,
        _keyword("tz_offset_hours", 0),
        *_SOURCE_PARAMETERS,
    )
)


def bind_read_request(
    signature: inspect.Signature,
    positional_fields: tuple[Any, ...],
    keyword_fields: dict[str, Any],
) -> ReadRequest:
    """Bind one public read's keyword call into the typed request model."""
    bound_fields = signature.bind(*positional_fields, **keyword_fields)
    bound_fields.apply_defaults()
    bound_values = bound_fields.arguments
    return ReadRequest(
        filters=ReadFilters(
            **{name: bound_values.get(name) for name in _FILTER_PARAMETERS_BY_NAME},
        ),
        connection=ReadConnection(
            **{name: bound_values.get(name) for name in _SOURCE_PARAMETERS_BY_NAME},
        ),
        options=ReadOptions(
            limit=bound_values.get(LIMIT_FIELD),
            sort_by=bound_values.get("sort_by"),
            tz_offset_hours=bound_values.get("tz_offset_hours", 0),
        ),
    )


def resolve_read_query(request: ReadRequest) -> ReadQuery:
    """Resolve one request's configured or caller-owned connection."""
    source = request.connection
    return ReadQuery.resolve(source.db_url, source.connect, source.conn)


def window_filters(
    request: ReadRequest,
    *,
    include_identity: bool = True,
) -> WindowFilters:
    """Project a typed request onto the shared SQL filter model."""
    filters = request.filters
    return WindowFilters(
        start=filters.start,
        end=filters.end,
        repo=filters.repo if include_identity else None,
        events=filters.events,
        stages=filters.stages,
        issue=filters.issue if include_identity else None,
    )


_FILTER_PARAMETERS_BY_NAME = tuple(parameter.name for parameter in _FILTER_PARAMETERS)
_SOURCE_PARAMETERS_BY_NAME = tuple(parameter.name for parameter in _SOURCE_PARAMETERS)
