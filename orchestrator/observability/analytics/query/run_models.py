# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one run, one issue, or one traced event is reported as.

These rows are positional unpacks of a SELECT list, so the field order here is
half of a contract whose other half is the query that fills it -- a column
added to one without the other silently shifts every field after it. The trace
row also carries the `result` name the page reads an event outcome by, which is
the column and the record field it was recorded under: the field is stored
under `event_result` because a bare `result` is a name the style guide rejects,
and the public name is installed as a property so the two can never hold
different values.

Money is carried as the evidence the sync filed rather than as one amount. A
run's cost is its own `CostEvidence` -- each basis's amount, an estimate's rate
dates, and the completeness its record stated -- and an issue's is the
`CostCohort` its runs fold to, so a reader can word a CLI-reported amount, a
provider's estimate, a blended total with its parts, an unpriced run, and an
amount with no basis apart, and never mistake a subtotal for the whole. Tokens
are the runs' non-overlapping totals, an unknown one left out of a sum and
counted beside it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from orchestrator.observability.analytics.query.cost_cohorts import EMPTY_COST_COHORT, CostCohort
from orchestrator.observability.usage.cost_evidence import CostEvidence

RESULT_FIELD = "result"


def public_event_result(event_row: IssueEventRow) -> str | None:
    """Return an event result through the `result` name the page reads."""
    return event_row.event_result


@dataclass(frozen=True)
class StageBreakdown:
    """Per-`stage` aggregate row for the stage breakdown table.

    `count` is `COUNT(*)` over every `analytics_events` row that
    carries the stage (so it includes `stage_enter` and
    `stage_evaluation` rows alongside `agent_exit`); `runs` narrows
    to the `event = 'agent_exit'` subset so the redesigned
    dashboard's "Cost by workflow stage" panel can label its
    sub-line as "runs" -- the standalone mock aggregates from
    per-agent-run records, not per-event rows.

    `avg_duration_s` is None when no row in the window had a
    non-null `duration_s` for that stage; the SQL `AVG(...)` returns
    NULL in that case rather than 0 so the dashboard can hide the
    column instead of showing a misleading zero. `total_cost_usd` /
    `total_input_tokens` / `total_output_tokens` roll up the cost /
    token figures across the stage so the breakdown table can plot
    "where the spend went". `cache_cost_usd` and `no_cache_cost_usd`
    split `total_cost_usd` into the portion attributable to cached /
    cache-read / cache-write tokens vs the portion attributable to
    input + output tokens. The split is prorated per rollup row by
    token share so cache + no-cache sums back to the stage's total
    cost, letting the dashboard chart stack cache vs no-cache spend
    per stage.
    """

    stage: str
    count: int
    avg_duration_s: float | None = None
    total_cost_usd: float = field(default_factory=float)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    runs: int = 0
    cache_cost_usd: float = field(default_factory=float)
    no_cache_cost_usd: float = field(default_factory=float)


@dataclass(frozen=True)
class EventBreakdown:
    """Per-`event` aggregate row for the event breakdown table."""

    event: str
    count: int


@dataclass(frozen=True)
class AgentExitRow:
    """One row of the recent-agent-exits overview table.

    Mirrors the columns the dashboard table renders -- intentionally a
    subset of the table, not every column. Adding a column should
    happen in lockstep with the SELECT list in `get_recent_agent_exits`
    so the positional unpack stays aligned.

    `total_tokens` is the run's non-overlapping total, `None` where its
    evidence leaves it unknown. `cost` is the run's evidence as stored: a
    CLI-reported amount stays the amount its record ranked first, an
    estimate keeps the dates its rates were verified on, and a row stored
    with no evidence reads `unknown` with its `cost_usd` under that basis.
    """

    ts: datetime
    repo: str
    issue: int
    stage: str | None
    agent_role: str | None
    backend: str | None
    duration_s: float | None
    exit_code: int | None
    timed_out: bool | None
    review_round: int | None
    retry_count: int | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cost: CostEvidence


@dataclass(frozen=True)
class IssueSummaryRow:
    """One row of the date/repo-bounded issues overview table.

    The dashboard's "issues" view shows one row per `(repo, issue)`
    pair seen in the window with light aggregates: how many events
    fired, when the issue was first / last touched, the most recent
    non-null `stage` (useful as a "current status" column even though
    pinned GitHub state remains authoritative), how many `agent_exit`
    events were recorded, the rolled-up cost / token totals, the
    highest review round any agent run for the issue reached, how
    many of those runs exited non-zero so the table can surface
    issues that needed multiple attempts, and the highest
    `retry_count` any agent run for the issue reached so the
    redesigned "Most expensive issues" table can carry a "Retries"
    column matching the standalone mock. Stable column order across
    the SELECT list, the dataclass, and the positional unpack in
    `get_issues` keeps the schema obvious when a future column is
    added.

    `cost` is the cohort the issue's runs fold to -- an empty one where
    it has none. `stated_cost_usd` is the measure the cost ranking orders
    on, read back as SQL ranked it: every amount the runs state, added
    across bases whatever their completeness, `None` where they state
    none. It equals `cost.evidence.total_usd` and is never shown without
    that cohort's wording. `total_tokens` sums the runs' known
    non-overlapping totals and `unknown_token_runs` counts the runs
    whose total is unknown.
    """

    repo: str
    issue: int
    event_count: int
    first_seen: datetime
    last_seen: datetime
    latest_stage: str | None
    agent_exits: int
    cost: CostCohort = EMPTY_COST_COHORT
    stated_cost_usd: float | None = None
    total_tokens: int = 0
    unknown_token_runs: int = 0
    max_review_round: int | None = None
    failed_agent_runs: int = 0
    max_retry_count: int | None = None


@dataclass(frozen=True)
class IssueEventRow:
    """One row of the per-issue event trace.

    The first nine fields are what the drill-down tabulates. `cost` is an
    `agent_exit` row's stored evidence, read as `AgentExitRow.cost` is,
    and `None` on every other event, which states no usage. The rest are
    what a `park_awaiting_human` record is correlated by: the promoted run
    columns it may carry (`agent_spec`, `session_id`, `resume_session_id`,
    `review_round`, `retry_count`, `timed_out`) and `extras`, the decoded
    blob the ingest routes every other field into -- a park's `reason`,
    `route`, `pr_number`, and `sha` among them. They default to unset
    because most events carry none of them: a `stage_enter` or a
    `stage_evaluation` reads back as having none rather than as a measured
    value, and an empty `extras` is a row with nothing outside the promoted
    set. The forensic provenance columns (`source_path`, `source_line`)
    stay off the trace.

    A park is a workflow-progress record, not an execution one: a handler
    that parked an issue still evaluated to `result="ok"`, and the
    `stage_evaluation` row beside a park says only that the handler returned
    without raising.
    """

    ts: datetime
    event: str
    stage: str | None
    duration_s: float | None
    event_result: str | None
    agent_role: str | None
    backend: str | None
    exit_code: int | None
    cost: CostEvidence | None
    agent_spec: str | None = None
    session_id: str | None = None
    resume_session_id: str | None = None
    review_round: int | None = None
    retry_count: int | None = None
    timed_out: bool | None = None
    extras: dict[str, Any] = field(default_factory=dict)


setattr(IssueEventRow, RESULT_FIELD, property(public_event_result))
