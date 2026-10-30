# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a window's spend and tokens read as on the overview, and what a comparison keeps.

The overview's money is a cohort of runs rather than one run, so on top of the
wording ``cost_text`` gives any cost this owner says the three things only a
cohort can: that a window held no run at all, which is neither a zero nor no
usage; how many of its runs left the amount short -- unpriced or partly priced,
or stating no cost evidence whatever amount they carry; and what a move
between two windows has to be read with.

An amount is never shown without its basis. A Gemini estimate, the basis
Antigravity usage is priced on, reads as a Gemini API token estimate; a window
spanning several bases reads as ``blended`` with each basis's own amount
beside it where the note sits next to the total, and with the bases alone where
the figure is a ratio of it, since a component amount beside a per-issue figure
would read as that issue's share. An incomplete subtotal and an amount whose
completeness nothing states are qualified as such, so neither passes for
complete spend.

A comparison keeps the same qualifications rather than reducing two windows to
a bare percentage: a move involving a subtotal, an unknown completeness, a
blended total, or two windows stated on different bases says so beside the
percentage. A token count is the runs' known non-overlapping totals, so where
any run's total is unknown the count, and any move of it, is labelled a
subtotal with those runs counted.
"""
from __future__ import annotations

from orchestrator.observability.analytics.query.cost_cohorts import CostCohort
from orchestrator.observability.dashboard import cost_text
from orchestrator.observability.usage import cost_evidence as usage_cost

# What a window with no agent run reads as, figure and note alike.
NO_RUNS_FIGURE = "—"

NO_RUNS_NOTE = "no agent runs"

_NOTE_SEPARATOR = " · "


def spend_figure(cohort: CostCohort) -> str:
    """The amount a window's runs state, or what stands where they state none."""
    if cohort.is_empty:
        return NO_RUNS_FIGURE
    return cost_text.cost_figure(cohort.evidence)


def spend_note(cohort: CostCohort, *, amounts: bool = True) -> str:
    """The basis a window's amount is stated on and why it falls short of complete spend; empty where nothing to say.

    `amounts` lists each part of a blended total by its amount; a figure derived from the total, rather than the total
    itself, names the bases alone.
    """
    if cohort.is_empty:
        return NO_RUNS_NOTE
    evidence = cohort.evidence
    basis = cost_text.basis_text(evidence) if amounts else _bases_text(evidence)
    notes = (basis, _coverage_text(cohort))
    return _NOTE_SEPARATOR.join(note for note in notes if note)


def spend_line(cohort: CostCohort) -> str:
    """A window's spend on one line, its note in parentheses: what a chart's hover reads."""
    note = spend_note(cohort)
    figure = spend_figure(cohort)
    return f"{figure} ({note})" if note else figure


def spend_comparison_note(current: CostCohort, previous: CostCohort) -> str:
    """What a move between two windows' spend has to be read with; empty where both are complete on one basis."""
    sides = (current.evidence, previous.evidence)
    notes = []
    if usage_cost.INCOMPLETE in {side.completeness for side in sides}:
        notes.append("subtotal")
    if usage_cost.UNKNOWN in {side.completeness for side in sides}:
        notes.append("completeness unknown")
    current_bases, previous_bases = (
        {part.basis for part in side.contributions} for side in sides
    )
    if current_bases != previous_bases:
        notes.append("bases differ")
    elif len(current_bases) > 1:
        notes.append(usage_cost.BLENDED)
    return ", ".join(notes)


def token_note(unknown_runs: int) -> str:
    """What a known token count adds where some run's total is unknown; empty where every total is known."""
    if not unknown_runs:
        return ""
    noun = "run" if unknown_runs == 1 else "runs"
    return f"subtotal: token total unknown for {unknown_runs:,} {noun}"


def _bases_text(evidence: usage_cost.CostEvidence) -> str:
    """A blended cost's bases without their amounts; any other cost's basis as `basis_text` names it."""
    if evidence.basis != usage_cost.BLENDED:
        return cost_text.basis_text(evidence)
    parts = " + ".join(
        cost_text.basis_text(usage_cost.CostEvidence(evidence.completeness, (part,)))
        for part in evidence.contributions
    )
    return f"{usage_cost.BLENDED}: {parts}"


def _coverage_text(cohort: CostCohort) -> str:
    """Why a cohort's amount is not complete spend, with the runs that make it so counted; empty where it is."""
    shortfalls = []
    if cohort.incomplete_runs:
        shortfalls.append(f"{cohort.incomplete_runs:,} of {cohort.runs:,} runs unpriced or partly priced")
    if cohort.unknown_runs:
        shortfalls.append(f"{cohort.unknown_runs:,} of {cohort.runs:,} runs state no cost evidence")
    qualifier = cost_text.completeness_text(cohort.evidence)
    if not shortfalls:
        return qualifier
    counted = ", ".join(shortfalls)
    return f"{qualifier}: {counted}" if qualifier else counted
