# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The rows the issue, recent-run, and trace reads hand back, built the way their SELECT lists fill them.

Each of the three ends its row in the cells a cost fragment selects, so a fake driver is handed those cells as the
fragment computes them over runs stating a set of costs (`analytics_cohorts.cohort_cells`): an issue's summed over its
runs, beside the amount the ranking orders it on, and a run's its own -- with an event that is no run stating none.
A row built here is therefore as wide as the SELECT list it stands in for, whatever cost it carries.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from orchestrator.observability.analytics.query.query_rows import IssueEventQueryRow
from orchestrator.observability.usage import cost_evidence as usage_cost
from tests.observability.analytics import analytics_cohorts as cohort_cases

# The columns a trace row is tabulated by, ahead of the run columns it is
# correlated by; and those run columns, all NULL in a row built here, which sit
# between them and the blob and cost closing the row.
TRACE_TABULATED_WIDTH = 8

_NULL_RUN_COLUMNS = (None,) * (len(IssueEventQueryRow._fields) - TRACE_TABULATED_WIDTH - 2)


def stated_usd(costs: Sequence[usage_cost.CostEvidence]) -> Decimal | None:
    """What the stated-amount fragment sums runs stating `costs` to: every amount on every basis, NULL where none."""
    amounts = [part.amount_usd for spent in costs for part in spent.contributions]
    return Decimal(str(math.fsum(amounts))) if amounts else None


def run_cost_cells(cost: usage_cost.CostEvidence | None) -> tuple:
    """One row's cost cells: a run stating `cost`, or, for `None`, an event that is no run."""
    return cohort_cases.cohort_cells(() if cost is None else (cost,))


def trace_row(
    tabulated: tuple,
    *,
    extras: Any = None,
    cost: usage_cost.CostEvidence | None = None,
) -> tuple:
    """One trace row: its tabulated columns, no run correlation, then its blob and cost."""
    return tabulated + _NULL_RUN_COLUMNS + (extras,) + run_cost_cells(cost)


@dataclass(frozen=True)
class IssueAggregate:
    """One issue's aggregate as the issues read selects it, its runs stating `costs`."""

    repo: str
    issue: int
    first_seen: datetime
    last_seen: datetime
    costs: tuple[usage_cost.CostEvidence, ...] = ()
    event_count: int = 1
    latest_stage: str | None = None
    total_tokens: int = 0
    unknown_token_runs: int = 0
    max_review_round: int | None = None
    failed_agent_runs: int = 0
    max_retry_count: int | None = None

    def cells(self) -> tuple:
        """The row in SELECT-list order: the issue's columns, then its cohort's cells."""
        named = (self.repo, self.issue, self.event_count, self.first_seen, self.last_seen)
        activity = (self.latest_stage, len(self.costs), stated_usd(self.costs))
        tokens = (self.total_tokens, self.unknown_token_runs)
        rounds = (self.max_review_round, self.failed_agent_runs, self.max_retry_count)
        return named + activity + tokens + rounds + cohort_cases.cohort_cells(self.costs)
