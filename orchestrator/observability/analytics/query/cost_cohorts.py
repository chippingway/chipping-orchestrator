# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a cohort of agent runs cost, reduced in SQL and read back as cost evidence.

The sync files each `agent_exit` row's cost under the basis its evidence names -- an amount column per basis, the
verification dates of each estimate's rates, and the completeness the record states -- so a cohort is reduced in SQL
the way `usage.cost_evidence.reduce_costs` folds costs in Python: each basis summed on its own, every distinct date an
estimate's rates were verified on kept per basis (the schema's `analytics_rate_dates` aggregate), and the runs counted
by the completeness each states. Every one of those cells folds across groups the way it folds across runs, which is
what lets the daily rollup store them pre-reduced and a read off it agree with the same read off the runs beneath.

`cost_cohort` turns those cells back into a `CostCohort`: the counts beside a `CostEvidence` whose completeness is the
weakest any counted run states and whose contributions are the per-basis sums, so anything that words a run's
`CostEvidence` words a cohort's the same way. Four answers one summed amount would merge stay apart: an empty cohort
(no run at all), a complete zero (a `complete` cost whose amounts sum to zero), an incomplete subtotal (amounts beside
a run that stated none), and an amount whose basis nothing states (held under the `unknown` basis, its completeness
`unknown`).

The fragment is spelled once per scan target, because each names what it reads differently. The agent-run view already
reads a row with no derived evidence as `unknown` with its `cost_usd` under that basis; the events table needs that
reading spelled out, and its counts kept to the `agent_exit` rows the other events are not; and the rollup carries the
counts pre-summed. All three select `COST_COHORT_WIDTH` cells in the one order `cost_cohort` reads.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from operator import attrgetter
from types import MappingProxyType
from typing import Any

from orchestrator.observability.usage import cost_evidence as usage_cost

# The completeness each count cell counts, in cell order, and the rollup column holding each count pre-summed.
_COMPLETENESS_STATES = (usage_cost.COMPLETE, usage_cost.INCOMPLETE, usage_cost.NO_USAGE, usage_cost.UNKNOWN)

_ROLLUP_COUNT_COLUMNS = ("cost_complete_runs", "cost_incomplete_runs", "cost_no_usage_runs", "cost_unknown_runs")

# One amount column per basis, named alike on the events table, the agent-run view, and the rollup. The `unknown`
# basis comes last, being the one whose reading differs by target.
_STATED_AMOUNT_COLUMNS = MappingProxyType({
    usage_cost.CLI_REPORTED: "cost_cli_reported_usd",
    usage_cost.ANTHROPIC_API_ESTIMATE: "cost_anthropic_estimate_usd",
    usage_cost.OPENAI_API_ESTIMATE: "cost_openai_estimate_usd",
    usage_cost.GEMINI_API_ESTIMATE: "cost_gemini_estimate_usd",
})

_UNKNOWN_AMOUNT = "cost_unknown_basis_usd"

_AMOUNT_BASES = (*_STATED_AMOUNT_COLUMNS, usage_cost.UNKNOWN_BASIS)

# The bases priced at dated rates, and the column holding each one's sorted distinct verification dates -- a run's on
# the events table and the agent-run view, a group's on the rollup.
_RATE_DATE_COLUMNS = MappingProxyType({
    usage_cost.ANTHROPIC_API_ESTIMATE: "anthropic_rates_verified_on",
    usage_cost.OPENAI_API_ESTIMATE: "openai_rates_verified_on",
    usage_cost.GEMINI_API_ESTIMATE: "gemini_rates_verified_on",
})

_COUNT_CELLS = len(_COMPLETENESS_STATES)

_AMOUNT_CELLS = len(_AMOUNT_BASES)

COST_COHORT_WIDTH = _COUNT_CELLS + _AMOUNT_CELLS + len(_RATE_DATE_COLUMNS)

_AMOUNT_SUMS = tuple(f"SUM({column})" for column in _STATED_AMOUNT_COLUMNS.values())

# The dates fold the same way over every target, since each stores them as a sorted distinct array.
_RATE_DATE_UNIONS = tuple(f"analytics_rate_dates({column})" for column in _RATE_DATE_COLUMNS.values())


def _run_cohort_sql(completeness: str, unknown_amount: str) -> str:
    """The cohort cells over per-run rows, given how a row's completeness and unknown-basis amount read."""
    counts = (f"SUM(CASE WHEN {completeness} = '{state}' THEN 1 ELSE 0 END)" for state in _COMPLETENESS_STATES)
    return ", ".join((*counts, *_AMOUNT_SUMS, f"SUM({unknown_amount})", *_RATE_DATE_UNIONS))


RUN_COST_COHORT_SQL = _run_cohort_sql("cost_completeness", _UNKNOWN_AMOUNT)

EVENT_COST_COHORT_SQL = _run_cohort_sql(
    "(CASE WHEN event = 'agent_exit' THEN COALESCE(cost_completeness, 'unknown') END)",
    f"CASE WHEN cost_completeness IS NULL THEN cost_usd ELSE {_UNKNOWN_AMOUNT} END",
)

ROLLUP_COST_COHORT_SQL = ", ".join((
    *(f"SUM({column})" for column in _ROLLUP_COUNT_COLUMNS),
    *_AMOUNT_SUMS,
    f"SUM({_UNKNOWN_AMOUNT})",
    *_RATE_DATE_UNIONS,
))


@dataclass(frozen=True)
class CostCohort:
    """The runs one cohort holds, counted by the completeness each states, and their cost reduced by basis.

    `evidence` is what the runs' costs fold to: each basis's amounts summed, an estimate's rates dated by every
    distinct verification date any of its runs was priced at, and the weakest completeness any run states. A cohort
    with no run at all is empty rather than one whose runs printed no usage, though both state no amount.
    """

    complete_runs: int
    incomplete_runs: int
    no_usage_runs: int
    unknown_runs: int
    evidence: usage_cost.CostEvidence

    @property
    def runs(self) -> int:
        return self.complete_runs + self.incomplete_runs + self.no_usage_runs + self.unknown_runs

    @property
    def is_empty(self) -> bool:
        return not self.runs


def cost_cohort(row: Sequence[Any], start: int = 0) -> CostCohort:
    """Read the cells a cohort fragment selected, from `start` on; a row too narrow to hold them raises."""
    cells = tuple(row[start:start + COST_COHORT_WIDTH])
    if len(cells) != COST_COHORT_WIDTH:
        raise ValueError(f"a cost cohort is {COST_COHORT_WIDTH} cells; the row holds {len(cells)} from {start}")
    counts = [int(cell or 0) for cell in cells[:_COUNT_CELLS]]
    amounts = cells[_COUNT_CELLS:_COUNT_CELLS + _AMOUNT_CELLS]
    evidence = usage_cost.CostEvidence(
        _weakest_completeness(counts),
        _contributions(amounts, cells[_COUNT_CELLS + _AMOUNT_CELLS:]),
    )
    return CostCohort(*counts, evidence=evidence)


def _weakest_completeness(counts: Sequence[int]) -> str:
    """The weakest completeness any counted run states, ranked by the fold every usage surface shares.

    An empty cohort reduces as an empty fold does, to `no-usage`; `CostCohort.is_empty` is what tells it apart.
    """
    stated = (
        usage_cost.CostEvidence(state)
        for state, count in zip(_COMPLETENESS_STATES, counts, strict=True)
        if count
    )
    return usage_cost.reduce_costs(stated).completeness


def _contributions(amounts: Sequence[Any], dates: Sequence[Any]) -> tuple[usage_cost.CostContribution, ...]:
    """One contribution per basis some run stated an amount on, a zero included, in the order `reduce_costs` keeps."""
    dated = dict(zip(_RATE_DATE_COLUMNS, map(_verified_on, dates), strict=True))
    stated = (
        usage_cost.CostContribution(basis, float(amount), dated.get(basis, ()))
        for basis, amount in zip(_AMOUNT_BASES, amounts, strict=True)
        if amount is not None
    )
    return tuple(sorted(stated, key=attrgetter("basis")))


def _verified_on(days: Any) -> tuple[date, ...]:
    """Every distinct date one basis's rates were verified on, in order; none where no run was priced at a dated row."""
    verified = {day for day in days or () if isinstance(day, date)}
    return tuple(sorted(verified))
