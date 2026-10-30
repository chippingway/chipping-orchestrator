# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The newest agent runs in a window, newest first and capped.

`event = 'agent_exit'` is this read's own condition, so it is spliced ahead of
whatever predicate the filter set generated and its operand binds first; the
limit binds last, after the generated ones. Two selections leave nothing to ask
for -- an event filter that excludes `agent_exit`, and a cleared stage
multiselect -- and both are answered before a connection is dialed.

The `events` selection is dropped from the generated predicate because this
read already pins the event itself; keeping it would add a redundant
`event IN (...)` beside the pinned equality.

A run's cost is read off the evidence the sync filed on its row
(`EVENT_RUN_COST_SQL`), never re-derived from its tokens or its `cost_source`
tag: a CLI-reported amount stays the amount its record ranked ahead of any
estimate, an estimate keeps the dates its rates were verified on, and a row
stored with no evidence reads `unknown`, its `cost_usd` under that basis. Its
tokens are the stored non-overlapping total, NULL where the evidence leaves it
unknown.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from orchestrator.observability.analytics.query.conditions import (
    agent_event_excluded,
    prepend_where_condition,
)
from orchestrator.observability.analytics.query.cost_cohorts import EVENT_RUN_COST_SQL, cost_cohort
from orchestrator.observability.analytics.query.execution import ReadQuery
from orchestrator.observability.analytics.query.filters import WindowFilters
from orchestrator.observability.analytics.query.predicates import build_window_where
from orchestrator.observability.analytics.query.query_rows import agent_exit_row
from orchestrator.observability.analytics.query.raw_values import (
    bool_or_none,
    empty_filter_selected,
    float_or_none,
    int_or_none,
)
from orchestrator.observability.analytics.query.run_models import AgentExitRow


def agent_exit_from_row(row: Sequence[Any]) -> AgentExitRow:
    """Project one recent-agent-exit row onto its result model."""
    query_row = agent_exit_row(row)
    return AgentExitRow(
        ts=query_row.ts,
        repo=query_row.repo,
        issue=int(query_row.issue),
        stage=query_row.stage,
        agent_role=query_row.agent_role,
        backend=query_row.backend,
        duration_s=float_or_none(query_row.duration_s),
        exit_code=int_or_none(query_row.exit_code),
        timed_out=bool_or_none(query_row.timed_out),
        review_round=int_or_none(query_row.review_round),
        retry_count=int_or_none(query_row.retry_count),
        input_tokens=int_or_none(query_row.input_tokens),
        output_tokens=int_or_none(query_row.output_tokens),
        total_tokens=int_or_none(query_row.total_tokens),
        cost=cost_cohort(query_row.cost).evidence,
    )


def recent_agent_exit_rows(
    query: ReadQuery,
    filters: WindowFilters,
    limit: int,
) -> list[AgentExitRow]:
    """Return the newest filtered agent-exit rows, up to `limit`."""
    if agent_event_excluded(filters.events):
        return []
    if empty_filter_selected(filters.stages):
        return []
    where, bindings = build_window_where(filters.without_events())
    where = prepend_where_condition(where, "event = %s")
    bindings.insert(0, "agent_exit")
    bindings.append(int(limit))
    rows = query.select(
        "SELECT ts, repo, issue, stage, agent_role, backend, "
        "duration_s, exit_code, timed_out, review_round, retry_count, "
        f"input_tokens, output_tokens, total_tokens, {EVENT_RUN_COST_SQL} "
        f"FROM analytics_events{where} "
        "ORDER BY ts DESC LIMIT %s",
        bindings,
    )
    return [agent_exit_from_row(row) for row in rows]
