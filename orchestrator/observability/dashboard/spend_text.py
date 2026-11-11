# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a cost reads as on the analytics dashboard: its figure, and a short status where the figure needs one.

Every amount the page shows -- the topbar, a tile, a bar and its hover, a
backend card, an issue row, a listed or traced run -- is worded here, and says
two things only: the amount its own runs state, exact to the cent, and a short
status where that amount is not the whole story. Which sources an amount came
from, what each of them is, and how many of the selection's runs left it short
are said once, in the collapsed section ``cost_details`` draws under the filter
bar, so no value repeats them and the overall selection's status is never
copied onto a row.

A status is earned by the value's own runs. An amount covering all of their
usage carries none, a complete zero included, since ``$0.00`` there is spend of
zero; an amount some run left unpriced or only partly priced is a
``Subtotal``; and one some run recorded no cost evidence for has
``Completeness unknown``. A cost stating no amount reads as its status alone --
``Unpriced``, ``No usage``, or ``Cost unknown`` -- and a cohort holding no run
as ``No runs``, so a missing cost never reads as a zero. A run's evidence and a
cohort's are worded alike; only a cohort can be empty.

Nothing here prices or re-adds anything: the evidence is the record's, read
through ``usage.cost_evidence`` and folded by the cohort reader, and an amount
is never called a charge.

A move between two windows keeps what either side is qualified by -- a
subtotal or an unknown completeness on either side -- and says so where the two
windows' amounts come from different sources, since a percentage between them
compares different things. A token count is the runs' known non-overlapping
totals, so where any run's total is unknown the count is labelled a subtotal
with those runs counted.
"""
from __future__ import annotations

from types import MappingProxyType

from orchestrator.observability.analytics.query.cost_cohorts import CostCohort
from orchestrator.observability.dashboard import cost_text
from orchestrator.observability.usage import cost_evidence as usage_cost

SUBTOTAL = "Subtotal"

COMPLETENESS_UNKNOWN = "Completeness unknown"

UNPRICED = "Unpriced"

COST_UNKNOWN = "Cost unknown"

NO_USAGE = "No usage"

NO_RUNS = "No runs"

SOURCES_DIFFER = "Sources differ"

_SEPARATOR = " · "

# The status an amount short of all its runs' usage is qualified by.
_AMOUNT_STATUSES = MappingProxyType({
    usage_cost.INCOMPLETE: SUBTOTAL,
    usage_cost.UNKNOWN: COMPLETENESS_UNKNOWN,
})

# What stands where a cost states no amount, by its completeness; any other reads as `COST_UNKNOWN`.
_NO_AMOUNT_STATUSES = MappingProxyType({
    usage_cost.NO_USAGE: NO_USAGE,
    usage_cost.INCOMPLETE: UNPRICED,
})


def spend_figure(cost: CostCohort | usage_cost.CostEvidence) -> str:
    """The amount a cost states, or the status standing where it states none."""
    evidence = _evidence(cost)
    if evidence is None:
        return NO_RUNS
    if evidence.total_usd is None:
        return _NO_AMOUNT_STATUSES.get(evidence.completeness, COST_UNKNOWN)
    return cost_text.fmt_cost_usd(evidence.total_usd)


def spend_status(cost: CostCohort | usage_cost.CostEvidence) -> str:
    """What an amount short of its runs' usage is qualified by; empty for a complete one and for no amount at all."""
    evidence = _evidence(cost)
    if evidence is None or evidence.total_usd is None:
        return ""
    return _AMOUNT_STATUSES.get(evidence.completeness, "")


def spend_line(cost: CostCohort | usage_cost.CostEvidence) -> str:
    """A cost on one line, its status after its figure: what a hover, a listed run, and a panel's note read."""
    status = spend_status(cost)
    figure = spend_figure(cost)
    return f"{figure}{_SEPARATOR}{status}" if status else figure


def spend_comparison_note(current: CostCohort, previous: CostCohort) -> str:
    """What a move between two windows' spend has to be read with; empty where both are complete on one source set."""
    stated = {current.evidence.completeness, previous.evidence.completeness}
    notes = [status for completeness, status in _AMOUNT_STATUSES.items() if completeness in stated]
    if _bases(current) != _bases(previous):
        notes.append(SOURCES_DIFFER)
    return ", ".join(notes)


def token_note(unknown_runs: int) -> str:
    """What a known token count adds where some run's total is unknown; empty where every total is known."""
    if not unknown_runs:
        return ""
    noun = "run" if unknown_runs == 1 else "runs"
    return f"subtotal: token total unknown for {unknown_runs:,} {noun}"


def _evidence(cost: CostCohort | usage_cost.CostEvidence) -> usage_cost.CostEvidence | None:
    """The evidence a cost is worded from; None for a cohort holding no run."""
    if isinstance(cost, CostCohort):
        return None if cost.is_empty else cost.evidence
    return cost


def _bases(cohort: CostCohort) -> set[str]:
    """Every basis a cohort's runs stated an amount on, a zero included."""
    return {part.basis for part in cohort.evidence.contributions}
