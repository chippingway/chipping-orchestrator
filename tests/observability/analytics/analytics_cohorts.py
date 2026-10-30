# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The cells a cohort fragment selects over runs stating a set of costs, and the cohort the reader hands back for them.

A read test hands its fake driver the cells a real cohort fragment would select, and a display test the cohort the
reader turns those cells into, so both are measured against what a real query produces rather than a hand-built
cohort: each basis's amount summed as SQL sums it -- NULL where no run states one, a zero kept -- each estimate's
distinct verification dates sorted as the date-union aggregate returns them, and the runs counted by the completeness
each states.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import Decimal
from types import MappingProxyType

from orchestrator.observability.analytics.query import cost_cohorts
from orchestrator.observability.usage import cost_evidence as usage_cost
from tests.observability.analytics import analytics_usage_cases as cases

_COMPLETENESS_ORDER = (usage_cost.COMPLETE, usage_cost.INCOMPLETE, usage_cost.NO_USAGE, usage_cost.UNKNOWN)

DATED_BASES = (
    usage_cost.ANTHROPIC_API_ESTIMATE,
    usage_cost.OPENAI_API_ESTIMATE,
    usage_cost.GEMINI_API_ESTIMATE,
)

# The cohorts any reduced cost has to keep apart, each the costs its runs state: a CLI-reported amount alone, an
# Antigravity group's Gemini API token estimates, a blend across providers and bases, a subtotal beside an unpriced
# run, and an amount an earlier build stored with no basis.
NAMED_COSTS = MappingProxyType({
    "reported only": (cases.REPORTED, cases.REPORTED),
    "agy only": (cases.GEMINI_ESTIMATE, cases.LATER_GEMINI_ESTIMATE),
    "mixed providers": (cases.REPORTED, cases.GEMINI_ESTIMATE, cases.BLENDED),
    "incomplete": (cases.ANTHROPIC_ESTIMATE, cases.INCOMPLETE_SUBTOTAL, cases.UNPRICED),
    "missing basis": (cases.REPORTED, cases.ABSENT_BASIS),
})


def _parts(costs: Sequence[usage_cost.CostEvidence], basis: str) -> list[usage_cost.CostContribution]:
    return [part for spent in costs for part in spent.contributions if part.basis == basis]


def _basis_amount(costs: Sequence[usage_cost.CostEvidence], basis: str) -> Decimal | None:
    """One basis's SQL sum: NULL where no run states an amount on it, a zero included."""
    amounts = [part.amount_usd for part in _parts(costs, basis)]
    return Decimal(str(math.fsum(amounts))) if amounts else None


def _basis_dates(costs: Sequence[usage_cost.CostEvidence], basis: str) -> list | None:
    """One estimate basis's distinct verification dates, sorted, as the date-union aggregate returns them: NULL where
    no run was priced at a dated row."""
    days = {day for part in _parts(costs, basis) for day in part.rates_verified_on}
    return sorted(days) or None


def cohort_cells(costs: Sequence[usage_cost.CostEvidence]) -> tuple:
    """The cells a cohort fragment selects over runs stating `costs`, in the order it selects them."""
    counts = [sum(spent.completeness == state for spent in costs) for state in _COMPLETENESS_ORDER]
    amounts = [_basis_amount(costs, basis) for basis in usage_cost.BASES]
    dates = [_basis_dates(costs, basis) for basis in DATED_BASES]
    return (*counts, *amounts, *dates)


def cohort(*costs: usage_cost.CostEvidence) -> cost_cohorts.CostCohort:
    """The cohort the reader hands back for runs stating `costs`; none at all is the empty cohort."""
    return cost_cohorts.cost_cohort(cohort_cells(costs))
