# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one group of a spend breakdown reads as on a bar, and what a panel of them notes beneath it.

A stage, a repository, a review round's role, and a backend each spend a cohort
of runs, so the full wording of one is ``spend_text``'s, the same a window's
total and an issue's cost are worded by, and a bar's hover carries it whole:
the figure, the basis -- each part of a blended amount by its own amount -- and
why the amount falls short of complete spend. A bar and the line under its
label have less room, so this owner says what fits there and stays true. The
figure drawn past a bar is the amount its runs state, compact the way every
dollar label on the page is, or the word that stands where they state none --
unpriced, no usage, cost unknown, or an em dash for a group with no run at all
-- never a zero for any of them. The line under the label names the basis the
amount is stated on -- a sole basis by its full name, so an Antigravity group
reads as a Gemini API token estimate, and several as ``blended`` -- and says a
subtotal or an amount of unknown completeness is one.

Beneath a panel, the note restates what all of its bars add up to the way the
overview words a window, its blended parts with their amounts, so the monetary
components behind a panel are read beside it rather than only on hover. A panel
splitting each bar by token share notes that too: the split is an allocation of
the stated amount by the cache tokens' share of the runs' declared totals, never
a measured cache charge, and the amount of a run whose total is unknown is left
unsplit.
"""
from __future__ import annotations

from collections.abc import Iterable
from types import MappingProxyType

from orchestrator.observability.analytics.query.cost_cohorts import CostCohort, fold_cohorts
from orchestrator.observability.dashboard import cost_text, spend_text
from orchestrator.observability.dashboard.formatting import fmt_money
from orchestrator.observability.usage import cost_evidence as usage_cost

TOKEN_SHARE_NOTE = (
    "Cache and non-cache segments split each stated amount by its runs' token share: an allocation, not a measured"
    " cache charge. The amount of runs whose token total is unknown stays unsplit."
)

_LINE_SEPARATOR = " · "

# What a bar's sub-line calls an amount short of complete spend.
_SHORTFALLS = MappingProxyType({
    usage_cost.INCOMPLETE: "subtotal",
    usage_cost.UNKNOWN: "completeness unknown",
})


def bar_figure(cohort: CostCohort) -> str:
    """The amount drawn past a group's bar, or what stands there where its runs state none."""
    stated = cohort.evidence.total_usd
    if cohort.is_empty or stated is None:
        return spend_text.spend_figure(cohort)
    return fmt_money(stated)


def basis_label(cohort: CostCohort) -> str:
    """The basis a group's amount is stated on, several named `blended`; empty where it states none."""
    evidence = cohort.evidence
    if cohort.is_empty or evidence.basis is None:
        return ""
    if evidence.basis == usage_cost.BLENDED:
        return usage_cost.BLENDED
    return cost_text.basis_text(evidence)


def sub_line(counted: str, cohort: CostCohort) -> str:
    """The line under a group's label: its run count, then its amount's basis and any shortfall."""
    shortfall = ""
    if cohort.evidence.total_usd is not None:
        shortfall = _SHORTFALLS.get(cohort.evidence.completeness, "")
    parts = (counted, basis_label(cohort), shortfall)
    return _LINE_SEPARATOR.join(part for part in parts if part)


def breakdown_note(cohorts: Iterable[CostCohort]) -> str:
    """What every bar of a panel adds up to, worded as a window's total is; empty for a panel with no bar."""
    groups = tuple(cohorts)
    if not groups:
        return ""
    return f"Bars total {spend_text.spend_line(fold_cohorts(groups))}"
