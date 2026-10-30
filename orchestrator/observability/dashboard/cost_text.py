# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a cost reads as: its amount, its basis, and how complete it is.

Both pages spell money through here: on the trajectory viewer the total-cost
tile, a row of the recorded-runs table, a run's usage row, and an assistant
turn's strip, and on the analytics dashboard a row of the recent-runs listing
and of an issue's trace, and -- through ``spend_text``, which words a cohort of
runs on top of this -- the overview's totals and each issue on the cost
ranking. So does the receipt the workflow posts on an issue it finishes
(``workflow.engine.issue_usage``), for the cost the issue's pinned totals
state. A basis is therefore worded one way on every surface. An amount is
never shown without its basis beside it, because the bases are different
things: a CLI-reported amount is what the agent CLI printed, never a verified
bill, and an estimate is a token-only Standard API list-price equivalent on its
provider's basis. A Gemini estimate, the basis Antigravity usage is priced on,
reads as a Gemini API token estimate and never as an Antigravity charge. A cost
spanning several bases reads as ``blended``, with each basis's own amount
beside it.

Nothing here prices or re-adds anything: the evidence is the record's, read
through ``usage.cost_evidence.recorded_cost`` and folded by ``reduce_costs``.
What this owner adds is that an amount short of all the usage never reads as
complete spend: an ``incomplete`` amount is worded a subtotal, one whose
completeness nothing states says so, and a cost with no amount at all reads as
unpriced, unknown, or no usage rather than as a zero.

Money is exact to the cents a caller asks for. The shared compact formatters
trade digits for a suffix at a fixed threshold, so a total tile would read
``$12`` where the recorded figure is ``$12.50``; a turn asks for four decimals,
since a per-turn estimate is routinely sub-cent and two decimals would floor a
real charge to ``$0.00``.
"""

from __future__ import annotations

from types import MappingProxyType

from orchestrator.observability.usage import cost_evidence as usage_cost

_BASIS_LABELS = MappingProxyType({
    usage_cost.CLI_REPORTED: "CLI-reported",
    usage_cost.ANTHROPIC_API_ESTIMATE: "Anthropic API token estimate",
    usage_cost.OPENAI_API_ESTIMATE: "OpenAI API token estimate",
    usage_cost.GEMINI_API_ESTIMATE: "Gemini API token estimate",
    usage_cost.UNKNOWN_BASIS: "basis unknown",
})

# What a cost stating no amount reads as, by its completeness.
_NO_AMOUNT_ANSWERS = MappingProxyType({
    usage_cost.NO_USAGE: "no usage",
    usage_cost.INCOMPLETE: "unpriced",
})

_UNKNOWN_COST = "cost unknown"

# The words an amount that is not complete spend is qualified by.
_COMPLETENESS_QUALIFIERS = MappingProxyType({
    usage_cost.INCOMPLETE: "incomplete subtotal",
    usage_cost.UNKNOWN: "completeness unknown",
})


def fmt_cost_usd(amount: float, *, decimals: int = 2) -> str:
    """Render an exact dollar figure with the requested precision."""
    number_format = f",.{decimals}f"
    return f"${format(amount, number_format)}"


def basis_text(cost: usage_cost.CostEvidence, *, decimals: int = 2) -> str:
    """Name a cost's basis, listing each part of a blended one by its amount."""
    if cost.basis == usage_cost.BLENDED:
        components = " + ".join(
            _component_text(part, decimals) for part in cost.contributions
        )
        return f"{usage_cost.BLENDED}: {components}"
    if cost.basis is None:
        return ""
    return _BASIS_LABELS.get(cost.basis, cost.basis)


def completeness_text(cost: usage_cost.CostEvidence) -> str:
    """Say why an amount is not complete spend; empty where nothing to say."""
    if cost.total_usd is None:
        return ""
    return _COMPLETENESS_QUALIFIERS.get(cost.completeness, "")


def cost_figure(cost: usage_cost.CostEvidence, *, decimals: int = 2) -> str:
    """Render the amount a cost states, or what stands where it states none."""
    if cost.total_usd is None:
        return _NO_AMOUNT_ANSWERS.get(cost.completeness, _UNKNOWN_COST)
    return fmt_cost_usd(cost.total_usd, decimals=decimals)


def cost_text(cost: usage_cost.CostEvidence, *, decimals: int = 2) -> str:
    """Render a cost on one line, its basis and qualifier in parentheses."""
    qualifiers = [
        qualifier
        for qualifier in (
            basis_text(cost, decimals=decimals),
            completeness_text(cost),
        )
        if qualifier
    ]
    figure = cost_figure(cost, decimals=decimals)
    if not qualifiers:
        return figure
    qualified = ", ".join(qualifiers)
    return f"{figure} ({qualified})"


def rates_text(cost: usage_cost.CostEvidence) -> str:
    """Date the rates any estimate in a cost was priced at; empty for none."""
    verified_on = sorted({
        verified
        for part in cost.contributions
        for verified in part.rates_verified_on
    })
    if not verified_on:
        return ""
    dates = ", ".join(day.isoformat() for day in verified_on)
    return f"rates verified {dates}"


def _component_text(part: usage_cost.CostContribution, decimals: int) -> str:
    label = _BASIS_LABELS.get(part.basis, part.basis)
    return f"{label} {fmt_cost_usd(part.amount_usd, decimals=decimals)}"
