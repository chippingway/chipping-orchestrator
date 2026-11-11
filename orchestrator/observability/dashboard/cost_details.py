# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one place the analytics page explains its money: the collapsed Cost details section under the filter bar.

Every amount elsewhere on the page is its figure and, where it needs one, a
short status of its own (``spend_text``). What those figures are made of is
said here, once, rather than beside each of them: what a CLI-reported amount
and a provider's API token estimate are -- neither of them a verified charge --
what a total mixing them is, what every status on the page means, and that a
token-share split of a bar is an allocation rather than a measured cache charge.

The section also states the selection itself, read off the same first-wave
summary the topbar and the tiles are, so it moves with every filter: the
selection's amount and status, each source's own part of it with the dates an
estimate's rates were verified on, the runs counted by how much of their usage
was priced, and the bar sizing the selection by the cost source each run
recorded. A selection whose runs left that much of it unpriced or only partly
priced -- `UNPRICED_WARNING_THRESHOLD` of its runs or more -- says so in the
section's own label, so the warning is read without opening it and is raised
nowhere else. The evidence does not record why a run went unpriced, so neither
the warning nor the explanation names a cause for any run.

The body is one HTML block handed to ``st.markdown(unsafe_allow_html=True)``:
Markdown would read a pair of dollar amounts as a formula, and a block opened
by a tag and holding no blank line is passed through untouched. Every caller
string reaching it is escaped. Streamlit and the theme are the caller's,
carried in the modules shape, so this owner imports neither.
"""
from __future__ import annotations

import html
from collections.abc import Sequence

from orchestrator.observability.analytics.query.cost_cohorts import CostCohort
from orchestrator.observability.analytics.query.cost_models import CostCoverageRow
from orchestrator.observability.dashboard import cost_text, coverage_card, page_models, spend_text
from orchestrator.observability.usage import cost_evidence as usage_cost

COST_DETAILS_LABEL = "Cost details"

UNPRICED_WARNING_THRESHOLD = 0.1

_SEPARATOR = " · "

# What each source an amount can come from is.
_SOURCES = (
    ("CLI-reported", (
        "The dollar amount the agent CLI printed for a run. Nothing checks it against an invoice, a subscription, or"
        " a credit balance. Where a run has one, it is used instead of an estimate."
    )),
    ("API token estimate", (
        "A run's token usage priced at its provider's Standard API list prices (Anthropic, OpenAI, or Gemini;"
        " Antigravity usage is priced as Gemini API usage) at rates verified on the dates listed above. It counts"
        " tokens only and is not what anyone was billed."
    )),
    ("Mixed sources", (
        "A value adding amounts from more than one source, such as CLI-reported amounts and estimates. Each source's"
        " part of this selection is listed above."
    )),
    ("Basis unknown", "An amount recorded without cost evidence, so nothing states which source it came from."),
)

# What each status a value can carry means.
_STATUSES = (
    ("No label", (
        "Every run behind the value has an amount covering all its usage. A $0.00 with no label is a genuine zero."
    )),
    (spend_text.SUBTOTAL, (
        "Some runs behind the value are unpriced or only partly priced, so the amount counts only what was priced."
    )),
    (spend_text.COMPLETENESS_UNKNOWN, (
        "Some runs behind the value recorded no cost evidence, so nothing says whether the amount covers all their"
        " usage."
    )),
    (spend_text.UNPRICED, "The runs used tokens, but none of that usage has an amount."),
    (spend_text.COST_UNKNOWN, "The runs recorded no cost evidence and no amount."),
    (spend_text.NO_USAGE, "The runs reported no usage to price."),
    (spend_text.NO_RUNS, "No agent run is behind the value."),
    (spend_text.SOURCES_DIFFER, (
        "Beside a change against the previous window: the two windows' amounts come from different sources, so the"
        " percentage compares different things."
    )),
)

_NOTES = (
    (
        "A status belongs to the value it sits beside: a row, bar, or card is labelled by its own runs, never by the"
        " selection's."
    ),
    (
        "A run is unpriced or partly priced when some of its usage has no amount, for example a model the price"
        " catalogue has no active row for, or usage counters an estimate cannot price. The recorded evidence does"
        " not say which applies to a given run."
    ),
    (
        "The cache and non-cache segments of the stage and review-round bars split each amount by its runs' token"
        " share: an allocation, not a measured cache charge. The amount of runs whose token total is unknown stays"
        " unsplit."
    ),
    (
        "Cost attribution coverage sizes the selection by the cost source each run recorded, by token share, or by"
        " run share once some run's token total is unknown."
    ),
)

_SOURCES_LEAD = "No amount on this page is a verified charge. Each comes from one of these sources:"

_STATUSES_LEAD = "Each value shows its amount and, where needed, one of these statuses:"

# One glossary entry: the term, then what it means.
_TERM_HTML = "<li><b>{0}</b>: {1}</li>"


def cost_details_label(cost: CostCohort) -> str:
    """The section's label: its name, then the runs left unpriced or partly priced where they reach the threshold."""
    if cost.is_empty or cost.incomplete_runs / cost.runs < UNPRICED_WARNING_THRESHOLD:
        return COST_DETAILS_LABEL
    return f"{COST_DETAILS_LABEL}{_SEPARATOR}{cost.incomplete_runs:,} of {cost.runs:,} runs unpriced or partly priced"


def selection_html(cost: CostCohort) -> str:
    """The selection's amount and status, each source's own part of it, and its runs counted by coverage."""
    spend = f"<p><b>This selection</b>: {html.escape(spend_text.spend_line(cost))}</p>"
    if cost.is_empty:
        return spend
    evidence = cost.evidence
    sources = "".join(_source_html(part, evidence.completeness) for part in evidence.contributions)
    listed = f"<p><b>By source</b></p><ul>{sources}</ul>" if sources else ""
    return f"{spend}{listed}<p><b>Runs</b>: {_run_counts(cost)}</p>"


def cost_details_html(cost: CostCohort, coverage_rows: Sequence[CostCoverageRow], *, theme) -> str:
    """The section's body: the selection, the bar sizing it by recorded cost source, and what the page's words mean."""
    coverage = coverage_card.cost_coverage_bar_html(coverage_rows, theme=theme) if coverage_rows else ""
    sources = _glossary_html(_SOURCES_LEAD, _SOURCES)
    statuses = _glossary_html(_STATUSES_LEAD, _STATUSES)
    notes = "".join(f"<p>{html.escape(note)}</p>" for note in _NOTES)
    return f'<div class="orch-cost-details">{selection_html(cost)}{coverage}{sources}{statuses}{notes}</div>'


def render_cost_details(
    modules: page_models.DashboardModules,
    cost: CostCohort,
    coverage_rows: Sequence[CostCoverageRow],
) -> None:
    """Draw the collapsed section for the selection the filters narrowed the page to."""
    with modules.st.expander(cost_details_label(cost), expanded=False):
        modules.st.markdown(
            cost_details_html(cost, coverage_rows, theme=modules.theme),
            unsafe_allow_html=True,
        )


def _glossary_html(lead: str, entries: Sequence[tuple[str, str]]) -> str:
    """A lead line and the terms it introduces, each beside what it means."""
    escaped = (map(html.escape, entry) for entry in entries)
    terms = "".join(_TERM_HTML.format(*entry) for entry in escaped)
    heading = html.escape(lead)
    return f"<p>{heading}</p><ul>{terms}</ul>"


def _run_counts(cost: CostCohort) -> str:
    """The selection's runs, then each completeness they state counted, a zero included."""
    return _SEPARATOR.join((
        f"{cost.runs:,} total",
        f"{cost.complete_runs:,} fully priced",
        f"{cost.incomplete_runs:,} unpriced or partly priced",
        f"{cost.no_usage_runs:,} no usage",
        f"{cost.unknown_runs:,} no cost evidence",
    ))


def _source_html(part: usage_cost.CostContribution, completeness: str) -> str:
    """One source's part of the selection, its amount exact, and the dates an estimate's rates were verified on."""
    alone = usage_cost.CostEvidence(completeness, (part,))
    worded = (
        cost_text.basis_text(alone),
        cost_text.fmt_cost_usd(part.amount_usd),
        cost_text.rates_text(alone),
    )
    return f"<li>{html.escape(_SEPARATOR.join(word for word in worded if word))}</li>"
