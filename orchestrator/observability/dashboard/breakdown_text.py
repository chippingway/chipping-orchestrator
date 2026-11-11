# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one group of a spend breakdown reads as on a bar, and what a panel of them notes beneath it.

A stage, a repository, a review round's role, and a backend each spend a cohort
of runs, so a bar's hover reads the group's cost the way ``spend_text`` words
every amount on the page: the figure, and its own status where it has one. A
bar and the line under its label have less room, so this owner says what fits
there and stays true. The figure drawn past a bar is the amount its runs state,
compact the way every dollar label on the page is, or the status that stands
where they state none -- ``Unpriced``, ``No usage``, ``Cost unknown``, or
``No runs`` -- never a zero for any of them. The line under the label counts
the group's runs and adds the amount's status, so a subtotal or an amount of
unknown completeness is marked as one on its own bar. Where one label heads
several bars -- a review round's development and review -- each bar gets a line
of its own under it, since one status there would be read as every bar's.

Beneath a panel, the note restates what all of its bars add up to, worded on
one line the way a hover words a group. Which sources those amounts came from,
and what a token-share split of them is, are explained once in the page's Cost
details section rather than under every panel.
"""
from __future__ import annotations

from collections.abc import Iterable

from orchestrator.observability.analytics.query.cost_cohorts import CostCohort, fold_cohorts
from orchestrator.observability.dashboard import spend_text
from orchestrator.observability.dashboard.formatting import fmt_money

_LINE_SEPARATOR = " · "


def bar_figure(cohort: CostCohort) -> str:
    """The amount drawn past a group's bar, or what stands there where its runs state none."""
    stated = cohort.evidence.total_usd
    if cohort.is_empty or stated is None:
        return spend_text.spend_figure(cohort)
    return fmt_money(stated)


def sub_line(counted: str, cohort: CostCohort) -> str:
    """The line under a group's label: its run count, then its amount's status where it has one."""
    parts = (counted, spend_text.spend_status(cohort))
    return _LINE_SEPARATOR.join(part for part in parts if part)


def role_line(runs: int, role: str, cohort: CostCohort) -> str:
    """One role's line under a label heading several bars: its run count, then its own amount's status."""
    noun = "run" if runs == 1 else "runs"
    return sub_line(f"{runs:,} {role} {noun}", cohort)


def breakdown_note(cohorts: Iterable[CostCohort]) -> str:
    """What every bar of a panel adds up to, worded on one line; empty for a panel with no bar."""
    groups = tuple(cohorts)
    if not groups:
        return ""
    return f"Bars total {spend_text.spend_line(fold_cohorts(groups))}"
