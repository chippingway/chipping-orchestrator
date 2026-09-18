# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Named query-boundary rows for wide analytics SELECT lists.

A fifteen-column unpack read by index is a contract nobody can check by eye, so
the four widest SELECT lists are read back by field name instead: the row
names line up with the SELECT list, and a column inserted in the wrong place
fails on a name rather than silently shifting every value after it. The trace
row goes one step further and is the SELECT list: its fields are the columns
the per-issue read names, so the two cannot drift apart at all.

The three padded constructors carry the other half of that: a fixture written
against an older, shorter SELECT list still builds a full row, with the columns
it never carried reading as NULL, so the projections above them keep their
zero- and `None`-defaulting behavior.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, NamedTuple

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
    ("cost_usd", Any),
    ("cost_source", Any),
))
IssueSummaryQueryRow = NamedTuple("IssueSummaryQueryRow", (
    ("repo", Any),
    ("issue", Any),
    ("event_count", Any),
    ("first_seen", Any),
    ("last_seen", Any),
    ("latest_stage", Any),
    ("agent_exits", Any),
    ("total_cost_usd", Any),
    ("total_input_tokens", Any),
    ("total_output_tokens", Any),
    ("max_review_round", Any),
    ("failed_agent_runs", Any),
    ("max_retry_count", Any),
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
    ("cost_usd", Any),
    ("agent_spec", Any),
    ("session_id", Any),
    ("resume_session_id", Any),
    ("review_round", Any),
    ("retry_count", Any),
    ("timed_out", Any),
    ("extras", Any),
))
ReviewRoundQueryRow = NamedTuple("ReviewRoundQueryRow", (
    ("bucket", Any),
    ("runs", Any),
    ("failed", Any),
    ("total_cost_usd", Any),
    ("developer_runs", Any),
    ("reviewer_runs", Any),
    ("developer_cost_usd", Any),
    ("reviewer_cost_usd", Any),
    ("developer_cache_cost_usd", Any),
    ("developer_no_cache_cost_usd", Any),
    ("reviewer_cache_cost_usd", Any),
    ("reviewer_no_cache_cost_usd", Any),
))


def agent_exit_row(row: Sequence[Any]) -> AgentExitQueryRow:
    """Name the columns of one recent-agent-exit row."""
    return AgentExitQueryRow(*row)


def issue_summary_row(row: Sequence[Any]) -> IssueSummaryQueryRow:
    """Name the columns of one issue-summary row, padding a short one."""
    missing = len(IssueSummaryQueryRow._fields) - len(row)
    padded_row = (*row, *((None,) * max(missing, 0)))
    return IssueSummaryQueryRow(*padded_row[:len(IssueSummaryQueryRow._fields)])


def issue_event_row(row: Sequence[Any]) -> IssueEventQueryRow:
    """Name the columns of one traced-event row, padding a short one."""
    missing = len(IssueEventQueryRow._fields) - len(row)
    padded_row = (*row, *((None,) * max(missing, 0)))
    return IssueEventQueryRow(*padded_row[:len(IssueEventQueryRow._fields)])


def review_round_row(row: Sequence[Any]) -> ReviewRoundQueryRow:
    """Name the columns of one review-round bucket row, padding a short one."""
    missing = len(ReviewRoundQueryRow._fields) - len(row)
    padded_row = (*row, *((None,) * max(missing, 0)))
    return ReviewRoundQueryRow(*padded_row[:len(ReviewRoundQueryRow._fields)])
