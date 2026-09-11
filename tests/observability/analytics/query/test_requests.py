# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a keyword call binds into, and the projections a family reads back."""
from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import MappingProxyType

from orchestrator.observability.analytics.query import requests as _support
from orchestrator.observability.analytics.query.filters import WindowFilters
from orchestrator.observability.analytics.query.request_models import (
    ReadConnection,
    ReadFilters,
    ReadOptions,
)
from tests.observability.analytics.query.query_fake_driver import (
    FakeConnect,
    FakeConnection,
)
from tests.observability.analytics.query.query_test_support import DB_URL

_AGENT_EXIT = "agent_exit"

_STAGE_IMPLEMENTING = "implementing"

_REPO = "owner/r"

_ISSUE = 42

_YEAR = 2026

_WINDOW_END_DAY = 28

_WINDOW_START = datetime(_YEAR, 5, 1, tzinfo=UTC)

_WINDOW_END = datetime(_YEAR, 5, _WINDOW_END_DAY, tzinfo=UTC)

# The row cap the paged families default to, and the ordering the issue table
# falls back on.
_PAGE_LIMIT = 100

_SORT_BY_LAST_SEEN = "last_seen"

# One dashboard call, spelled the way every public read is called.
_FILTER_CALL = MappingProxyType({
    "start": _WINDOW_START,
    "end": _WINDOW_END,
    "repo": _REPO,
    "events": [_AGENT_EXIT],
    "stages": [_STAGE_IMPLEMENTING],
    "issue": _ISSUE,
})


class KeywordBindingTest(unittest.TestCase):
    """One flat keyword call, sorted into the parts a family asks for."""

    def test_a_call_is_sorted_into_the_three_parts(self) -> None:
        conn = FakeConnection()
        connect = FakeConnect()
        request = _support.bind_read_request(
            _support.RECENT_EXITS_SIGNATURE,
            (),
            {**_FILTER_CALL, "db_url": DB_URL, "connect": connect, "conn": conn},
        )
        self.assertEqual(
            request.filters,
            ReadFilters(
                start=_WINDOW_START,
                end=_WINDOW_END,
                repo=_REPO,
                events=[_AGENT_EXIT],
                stages=[_STAGE_IMPLEMENTING],
                issue=_ISSUE,
            ),
        )
        self.assertEqual(
            request.connection,
            ReadConnection(db_url=DB_URL, connect=connect, conn=conn),
        )
        self.assertEqual(request.options, ReadOptions(limit=_support.RECENT_EXIT_LIMIT))

    def test_each_family_applies_its_own_defaults(self) -> None:
        # The knob a caller omits is answered here rather than by the family,
        # so the recent-runs cap and the issue table's ordering cannot differ
        # between the reader and the signature its call is bound against.
        families = (
            (_support.SOURCE_READ_SIGNATURE, ReadOptions()),
            (_support.FILTERED_READ_SIGNATURE, ReadOptions()),
            (_support.HEATMAP_SIGNATURE, ReadOptions()),
            (_support.RECENT_EXITS_SIGNATURE, ReadOptions(limit=_support.RECENT_EXIT_LIMIT)),
            (_support.LIMITED_READ_SIGNATURE, ReadOptions(limit=_PAGE_LIMIT)),
            (
                _support.ISSUES_SIGNATURE,
                ReadOptions(limit=_PAGE_LIMIT, sort_by=_SORT_BY_LAST_SEEN),
            ),
        )
        for signature, options in families:
            with self.subTest(options=options):
                request = _support.bind_read_request(signature, (), {})
                self.assertEqual(request.options, options)
                self.assertEqual(request.connection, ReadConnection())

    def test_the_drilldown_demands_its_issue(self) -> None:
        # `get_issue_events` is per-issue by definition; a call missing either
        # half would otherwise read the whole window.
        with self.assertRaises(TypeError):
            _support.bind_read_request(_support.ISSUE_EVENTS_SIGNATURE, (), {})
        request = _support.bind_read_request(
            _support.ISSUE_EVENTS_SIGNATURE,
            (),
            {"repo": _REPO, "issue": _ISSUE},
        )
        self.assertEqual(request.filters.repo, _REPO)
        self.assertEqual(request.filters.issue, _ISSUE)

    def test_a_positional_argument_is_refused(self) -> None:
        # Every parameter is keyword-only, so a value passed positionally is
        # rejected rather than landing on whichever field comes first.
        with self.assertRaises(TypeError):
            _support.bind_read_request(_support.FILTERED_READ_SIGNATURE, (_WINDOW_START,), {})


class FilterProjectionTest(unittest.TestCase):
    """The SQL filter model a family builds its predicate from."""

    def test_the_bound_filters_reach_the_sql_model(self) -> None:
        request = _support.bind_read_request(_support.FILTERED_READ_SIGNATURE, (), _FILTER_CALL)
        self.assertEqual(
            _support.window_filters(request),
            WindowFilters(
                start=_WINDOW_START,
                end=_WINDOW_END,
                repo=_REPO,
                events=[_AGENT_EXIT],
                stages=[_STAGE_IMPLEMENTING],
                issue=_ISSUE,
            ),
        )

    def test_a_scoped_projection_drops_identity(self) -> None:
        # What a query grouped by repo asks for: the window and the selections
        # still narrow it, but the repo and issue it groups over must not.
        request = _support.bind_read_request(_support.FILTERED_READ_SIGNATURE, (), _FILTER_CALL)
        self.assertEqual(
            _support.window_filters(request, include_identity=False),
            WindowFilters(
                start=_WINDOW_START,
                end=_WINDOW_END,
                events=[_AGENT_EXIT],
                stages=[_STAGE_IMPLEMENTING],
            ),
        )


class ConnectionProjectionTest(unittest.TestCase):
    """The connection a family runs its SELECT on."""

    def test_the_connection_fields_reach_the_query(self) -> None:
        conn = FakeConnection()
        connect = FakeConnect()
        request = _support.bind_read_request(
            _support.SOURCE_READ_SIGNATURE,
            (),
            {"db_url": DB_URL, "connect": connect, "conn": conn},
        )
        query = _support.resolve_read_query(request)
        self.assertEqual(query.db_url, DB_URL)
        self.assertIs(query.connect_fn, connect)
        self.assertIs(query.conn, conn)


if __name__ == "__main__":
    unittest.main()
