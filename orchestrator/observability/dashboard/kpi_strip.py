# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The four tiles a window opens with, assembled from what it was read as.

This is where a page's first-wave rows become the strip above every panel: the
window's own aggregate and the one before it, the day series, the throughput
days, and the review-round split arrive together and leave as four display
entries plus the resolved / rejected pair the reliability tiles are also
reported with. Everything a tile shows is decided here rather than inside a
Streamlit run, so what an operator reads is testable without one.

The reductions themselves belong to `kpis`, the lines under the tiles to
`kpi_series`, and the words a cohort's spend and a known token count are
qualified by to `spend_text`; what this owner adds is which of them each tile
reports and how that reading is spelled. A tile that reports money carries a
note naming its basis and why it falls short of complete spend, and a tile whose
token count leaves some run's total out says it is a subtotal, so neither a
blended amount, an incomplete subtotal, nor a known token subtotal passes for
the whole. Its move against the window before carries the same qualifications:
a percentage between two subtotals, two windows on different bases, or a window
whose amount states no completeness is annotated as such, and a window whose
runs stated no amount at all has no percentage to report.

Two spellings carry a decision. Cost per resolved issue is an em dash rather
than a zero or a division when nothing was resolved, because a window that
resolved nothing has no such cost and printing one would be a number an
operator could act on; where the window's runs stated no amount it reads as
their spend does -- unpriced, or cost unknown. The rework share is an em dash
the same way where the review rounds state no positive amount to take a share
of, so an unpriced or unreviewed window reports no share rather than a zero it
never measured, and a share taken of a subtotal or of a blended amount carries
the rounds' basis and shortfall in its note.

The strip is handed the theme rather than importing it, because the module a
page renders through is the one whose formatters and hues a tile has to match
-- the page hands its own theme in, and the tiles cannot end up set in a
second one.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from orchestrator.observability.analytics.query.cost_cohorts import CostCohort
from orchestrator.observability.analytics.query.overview_models import Summary
from orchestrator.observability.dashboard import cost_text, spend_text
from orchestrator.observability.dashboard.kpi_series import (
    DailyKpiSeries,
    daily_kpi_series,
    throughput_totals,
)
from orchestrator.observability.dashboard.kpis import kpi_delta, rework_totals

# The keys the strip's HTML builder reads each entry back by.
_LABEL_KEY = "label"
_VALUE_KEY = "value"
_NOTE_KEY = "note"
_DELTA_KEY = "delta"
_DELTA_NOTE_KEY = "delta_note"
_SUBTITLE_KEY = "sub"
_SPARK_KEY = "spark"
_SPARK_COLOR_KEY = "spark_color"
KpiStripData = tuple[list[dict[str, Any]], int, int]


@dataclass(frozen=True)
class KpiInputs:
    """Everything one strip is built from, as the first wave handed it back."""

    theme: Any
    summary: Summary
    prev_summary: Summary
    ts_points: Sequence[Any]
    throughput_rows: Sequence[Any]
    review_round_rows: Sequence[Any]
    days_in_window: int


@dataclass(frozen=True)
class KpiTotals:
    """The window and the one before it, with the counts the four tiles are read off."""

    current: Summary
    previous: Summary
    resolved: int
    rejected: int
    review_cost: CostCohort
    rework_cost: CostCohort

    @property
    def spend(self) -> float | None:
        """The amount the window's runs state, every basis added; None where they state none."""
        return self.current.cost.evidence.total_usd

    @property
    def spend_delta(self) -> float | None:
        """The move in stated spend against the window before; None where either side states no amount."""
        previous = self.previous.cost.evidence.total_usd
        if self.spend is None or previous is None:
            return None
        return kpi_delta(self.spend, previous)

    @property
    def token_delta_note(self) -> str:
        """What a move in known tokens has to be read with: a subtotal on either side says so."""
        if self.current.unknown_token_runs or self.previous.unknown_token_runs:
            return "subtotal"
        return ""

    @property
    def rework_share(self) -> float | None:
        """The share of the review rounds' stated spend a second pass took; None where they state no positive amount."""
        review = self.review_cost.evidence.total_usd
        if review is None or review <= 0:
            return None
        return (self.rework_cost.evidence.total_usd or 0) / review


def kpi_totals(inputs: KpiInputs) -> KpiTotals:
    """Pair a window with the one before it and the counts its tiles report."""
    throughput = throughput_totals(inputs.throughput_rows)
    review_costs = rework_totals(inputs.review_round_rows)
    return KpiTotals(
        current=inputs.summary,
        previous=inputs.prev_summary,
        resolved=throughput[0],
        rejected=throughput[1],
        review_cost=review_costs[0],
        rework_cost=review_costs[1],
    )


def cost_per_resolved(totals: KpiTotals) -> str:
    """What one resolved issue cost, or an em dash when none were."""
    if totals.resolved <= 0:
        return "—"
    if totals.spend is None:
        return spend_text.spend_figure(totals.current.cost)
    return cost_text.fmt_cost_usd(totals.spend / totals.resolved)


def rework_subtitle(rework: CostCohort) -> str:
    """What the rounds after the first stated, or that none of them ran."""
    if rework.is_empty:
        return "no runs in review rounds >= 1"
    return f"{spend_text.spend_figure(rework)} in review rounds >= 1"


def kpi_strip_entries(
    inputs: KpiInputs,
    totals: KpiTotals,
    daily: DailyKpiSeries,
) -> list[dict[str, Any]]:
    """The four entries the strip renders, in the order they are drawn."""
    cost = totals.current.cost
    daily_cost = (
        "" if totals.spend is None
        else inputs.theme.fmt_money(totals.spend / inputs.days_in_window)
    )
    daily_tokens = inputs.theme.fmt_tokens(totals.current.total_tokens / inputs.days_in_window)
    rework_share = totals.rework_share
    rework_value = "—" if rework_share is None else format(rework_share, ".0%")
    return [
        {
            _LABEL_KEY: "Total spend",
            _VALUE_KEY: spend_text.spend_figure(cost),
            _NOTE_KEY: spend_text.spend_note(cost),
            _DELTA_KEY: totals.spend_delta,
            _DELTA_NOTE_KEY: spend_text.spend_comparison_note(cost, totals.previous.cost),
            _SUBTITLE_KEY: f"{daily_cost}/day" if daily_cost else "",
            _SPARK_KEY: daily.cost,
            _SPARK_COLOR_KEY: inputs.theme.ACCENT,
        },
        {
            _LABEL_KEY: "Total tokens",
            _VALUE_KEY: inputs.theme.fmt_tokens(totals.current.total_tokens),
            _NOTE_KEY: spend_text.token_note(totals.current.unknown_token_runs),
            _DELTA_KEY: kpi_delta(totals.current.total_tokens, totals.previous.total_tokens),
            _DELTA_NOTE_KEY: totals.token_delta_note,
            _SUBTITLE_KEY: f"{daily_tokens}/day",
            _SPARK_KEY: daily.tokens,
            _SPARK_COLOR_KEY: inputs.theme.TOKEN_TYPE_COLORS["Input"],
        },
        {
            _LABEL_KEY: "Cost / resolved issue",
            _VALUE_KEY: cost_per_resolved(totals),
            _NOTE_KEY: spend_text.spend_note(cost, amounts=False),
            _DELTA_KEY: None,
            _SUBTITLE_KEY: (
                f"{totals.resolved} resolved · {totals.rejected} rejected"
            ),
            _SPARK_KEY: daily.done,
            _SPARK_COLOR_KEY: inputs.theme.TOKEN_TYPE_COLORS["Cache"],
        },
        {
            _LABEL_KEY: "Rework share",
            _VALUE_KEY: rework_value,
            _NOTE_KEY: spend_text.spend_note(totals.review_cost, amounts=False),
            _DELTA_KEY: None,
            _SUBTITLE_KEY: rework_subtitle(totals.rework_cost),
            _SPARK_KEY: None,
        },
    ]


def build_kpi_strip_data(inputs: KpiInputs) -> KpiStripData:
    """Build KPI dictionaries and throughput totals."""
    totals = kpi_totals(inputs)
    daily = daily_kpi_series(
        ts_points=inputs.ts_points,
        throughput_rows=inputs.throughput_rows,
    )
    kpis = kpi_strip_entries(inputs, totals, daily)
    return kpis, totals.resolved, totals.rejected
