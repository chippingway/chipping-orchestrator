# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Named query-boundary rows for wide analytics SELECT lists.

A fifteen-column unpack read by index is a contract nobody can check by eye, so
the four widest SELECT lists are read back by field name instead: the row
names line up with the SELECT list, and a column inserted in the wrong place
fails on a name rather than silently shifting every value after it. The trace
row goes one step further and is the SELECT list: its fields are the columns
the per-issue read names, so the two cannot drift apart at all.

The three run and issue rows end in the cells a cost-cohort fragment selects,
which `cost_cohorts.cost_cohort` reads as one unit, so their last field is
`cost`, holding every one of those cells, rather than a dozen names the reader
would only have to gather back up; the trace's SELECT list names that fragment
where its row names `cost`. A review round's row is read per role, and the
three cells `cache_shares` splits its stated amount into are gathered as
`token_share` ahead of its `cost` the same way.

Each constructor takes exactly the columns its SELECT list names, so a row of
any other width raises rather than reading a column it never carried as NULL.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, NamedTuple

from orchestrator.observability.analytics.query.cache_shares import TOKEN_SHARE_WIDTH
from orchestrator.observability.analytics.query.cost_cohorts import COST_COHORT_WIDTH

# The field every costed row ends in, holding the cells a cost-cohort fragment selects.
_COST_FIELD = "cost"

AgentExitQueryRow = NamedTuple("AgentExitQueryRow", (
    ("ts", Any),
    ("repo", Any),
    ("issue", Any),
    ("stage", Any),
    ("agent_role", Any),
    ("backend", Any),
    ("duration_s", Any),
    ("exit_code", Any),
    ("timed_out", Any),
    ("review_round", Any),
    ("retry_count", Any),
    ("input_tokens", Any),
    ("output_tokens", Any),
    ("total_tokens", Any),
    (_COST_FIELD, tuple),
))
IssueSummaryQueryRow = NamedTuple("IssueSummaryQueryRow", (
    ("repo", Any),
    ("issue", Any),
    ("event_count", Any),
    ("first_seen", Any),
    ("last_seen", Any),
    ("latest_stage", Any),
    ("agent_exits", Any),
    ("stated_cost_usd", Any),
    ("total_tokens", Any),
    ("unknown_token_runs", Any),
    ("max_review_round", Any),
    ("failed_agent_runs", Any),
    ("max_retry_count", Any),
    (_COST_FIELD, tuple),
))
IssueEventQueryRow = NamedTuple("IssueEventQueryRow", (
    ("ts", Any),
    ("event", Any),
    ("stage", Any),
    ("duration_s", Any),
    ("result", Any),
    ("agent_role", Any),
    ("backend", Any),
    ("exit_code", Any),
    ("agent_spec", Any),
    ("session_id", Any),
    ("resume_session_id", Any),
    ("review_round", Any),
    ("retry_count", Any),
    ("timed_out", Any),
    ("extras", Any),
    (_COST_FIELD, tuple),
))
ReviewRoundQueryRow = NamedTuple("ReviewRoundQueryRow", (
    ("bucket", Any),
    ("agent_role", Any),
    ("runs", Any),
    ("failed", Any),
    ("token_share", tuple),
    (_COST_FIELD, tuple),
))


def agent_exit_row(row: Sequence[Any]) -> AgentExitQueryRow:
    """Name the columns of one recent-agent-exit row."""
    return AgentExitQueryRow(*_costed_cells(row, AgentExitQueryRow._fields))


def issue_summary_row(row: Sequence[Any]) -> IssueSummaryQueryRow:
    """Name the columns of one issue-summary row."""
    return IssueSummaryQueryRow(*_costed_cells(row, IssueSummaryQueryRow._fields))


def issue_event_row(row: Sequence[Any]) -> IssueEventQueryRow:
    """Name the columns of one traced-event row."""
    return IssueEventQueryRow(*_costed_cells(row, IssueEventQueryRow._fields))


def review_round_row(row: Sequence[Any]) -> ReviewRoundQueryRow:
    """Name the columns of one `(round, role)` row, its token-share cells and its cost cells each gathered as one."""
    columns = len(ReviewRoundQueryRow._fields) - 2
    shared = columns + TOKEN_SHARE_WIDTH
    width = shared + COST_COHORT_WIDTH
    if len(row) != width:
        raise TypeError(f"a review-round row is {width} cells; it holds {len(row)}")
    token_share = tuple(row[columns:shared])
    cost = tuple(row[shared:])
    return ReviewRoundQueryRow(*row[:columns], token_share, cost)


def _costed_cells(row: Sequence[Any], fields: Sequence[str]) -> tuple:
    """The columns ahead of a row's cost cells, then those cells as one value; a row of any other width raises."""
    columns = len(fields) - 1
    width = columns + COST_COHORT_WIDTH
    if len(row) != width:
        raise TypeError(f"a row naming {fields} is {width} cells; it holds {len(row)}")
    return (*row[:columns], tuple(row[columns:]))
