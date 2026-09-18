# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One issue's event trace, oldest first.

The `(repo, issue)` pair the drill-down is keyed by is this read's own
condition, so it is spliced ahead of the generated predicate and its two
operands bind before the window's. Ordering ties break on `id`, which is the
insertion order, so two events recorded in the same instant still read back in
the order they happened.

A trace row is the whole of what one event can be asked about, not only what
the page tabulates, because a human-wait record carries its answer in two
places. The ingest promotes the fields the table has a column for -- the run
and session a park correlates to, its review round and retry count, whether the
run timed out -- and routes everything else into `extras`: the park's `reason`
and `route`, its pull request and commit, and any field a newer writer adds
before the table knows it. So the read selects those columns and the blob
beside them, and a park read back here says why it waited without a join, a
migration, or a second query. The columns it reads are the fields of the named
trace row, which is what keeps the SELECT list and the projection from
disagreeing about where any one of them sits.

A row older than any of that still reads: a NULL column stays `None`, and a
NULL, damaged, or non-object blob reads as an empty mapping rather than
raising, so one legacy row never takes an issue's whole trace down with it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from orchestrator.observability.analytics.query.conditions import prepend_where_condition
from orchestrator.observability.analytics.query.execution import ReadQuery
from orchestrator.observability.analytics.query.filters import WindowFilters
from orchestrator.observability.analytics.query.predicates import build_window_where
from orchestrator.observability.analytics.query.query_rows import IssueEventQueryRow, issue_event_row
from orchestrator.observability.analytics.query.raw_values import (
    bool_or_none,
    float_or_none,
    int_or_none,
    json_object,
)
from orchestrator.observability.analytics.query.run_models import IssueEventRow

_SELECTED_COLUMNS = ", ".join(IssueEventQueryRow._fields)


def issue_event_from_row(row: Sequence[Any]) -> IssueEventRow:
    """Project one traced-event row onto its result model."""
    query_row = issue_event_row(row)
    return IssueEventRow(
        ts=query_row.ts,
        event=query_row.event,
        stage=query_row.stage,
        duration_s=float_or_none(query_row.duration_s),
        event_result=query_row.result,
        agent_role=query_row.agent_role,
        backend=query_row.backend,
        exit_code=int_or_none(query_row.exit_code),
        cost_usd=float_or_none(query_row.cost_usd),
        agent_spec=query_row.agent_spec,
        session_id=query_row.session_id,
        resume_session_id=query_row.resume_session_id,
        review_round=int_or_none(query_row.review_round),
        retry_count=int_or_none(query_row.retry_count),
        timed_out=bool_or_none(query_row.timed_out),
        extras=json_object(query_row.extras),
    )


def issue_event_rows(
    query: ReadQuery,
    filters: WindowFilters,
    repo: str,
    issue: int,
) -> list[IssueEventRow]:
    """Return every selected event for one issue, oldest first."""
    where, bindings = build_window_where(filters)
    where = prepend_where_condition(where, "repo = %s AND issue = %s")
    rows = query.select(
        f"SELECT {_SELECTED_COLUMNS} "
        f"FROM analytics_events{where} "
        "ORDER BY ts ASC, id ASC",
        [repo, int(issue), *bindings],
    )
    return [issue_event_from_row(row) for row in rows]
