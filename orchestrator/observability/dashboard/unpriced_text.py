# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Why an unpriced run has no amount, as the analytics page words it: on a listed run, and over a selection.

The usage estimators record the reasons an unpriced run has no amount, each beside the model it concerns
(``usage.unpriced``), and the sync keeps them on the run's row as recorded. A listed run reads its own reasons grouped
by model; the Cost details section lists the selection's unpriced runs counted under each model and reason, and
explains every reason once. An unpriced run whose record states no reason -- every one an earlier build recorded --
reads ``Reason unavailable``, never a reason guessed for it, and a run whose cost is not unpriced reads none at all:
a CLI-reported amount, a zero included, is the run's cost whatever the estimate could not price.

Every caller string reaching the markup here is escaped, since it is handed on inside the Cost details section's HTML
block.
"""
from __future__ import annotations

import html
import itertools
from collections.abc import Iterable, Sequence
from operator import attrgetter
from types import MappingProxyType

from orchestrator.observability.analytics.query.cost_models import UnpricedReasonRow
from orchestrator.observability.usage import cost_evidence as usage_cost, unpriced as usage_unpriced

REASON_UNAVAILABLE = "Reason unavailable"

UNPRICED_REASONS_HEADING = "Unpriced runs by model and reason"

REASON_LABELS = MappingProxyType({
    usage_unpriced.MISSING_MODEL_PRICE: "Missing model price",
    usage_unpriced.INDETERMINATE_REQUEST_TIER: "Indeterminate request tier",
    usage_unpriced.MISSING_CACHE_WRITE_COUNT: "Missing cache-write count",
    usage_unpriced.MISSING_CACHE_WRITE_LIFETIME: "Missing cache-write lifetime",
    usage_unpriced.UNRATED_TOKEN_CLASS: "Unrated token class",
    usage_unpriced.INVALID_TOKEN_COUNTS: "Invalid token counts",
    usage_unpriced.MISSING_TOKEN_COUNT: "Missing token count",
    usage_unpriced.INDETERMINATE_RATE_PERIOD: "Indeterminate rate period",
    usage_unpriced.SUBAGENT_USAGE: "Subagent usage",
    usage_unpriced.SEVERAL_MODELS: "Several models",
})

# What each reason means, in the order the Cost details section explains them, the run recorded with none last.
REASON_MEANINGS = (
    (REASON_LABELS[usage_unpriced.MISSING_MODEL_PRICE], (
        "No active price-catalogue row answers to the model: an unknown or unnamed model, one whose row is not active,"
        " or an Antigravity model no Gemini API model is established for."
    )),
    (REASON_LABELS[usage_unpriced.INDETERMINATE_REQUEST_TIER], (
        "The model's price depends on each request's prompt size, and the usage does not establish it, such as a Codex"
        " run whose cumulative input passes the tier's threshold."
    )),
    (REASON_LABELS[usage_unpriced.MISSING_CACHE_WRITE_COUNT], (
        "The model charges cache writes by lifetime, and the usage does not say how many there were, such as the zero"
        " or missing count the Codex CLI prints."
    )),
    (REASON_LABELS[usage_unpriced.MISSING_CACHE_WRITE_LIFETIME], (
        "The usage reports cache writes without the lifetime the model charges them by."
    )),
    (REASON_LABELS[usage_unpriced.UNRATED_TOKEN_CLASS], (
        "The usage holds tokens of a kind the model's price row lists no rate for."
    )),
    (REASON_LABELS[usage_unpriced.INVALID_TOKEN_COUNTS], (
        "A token count is negative, or the counts contradict each other."
    )),
    (REASON_LABELS[usage_unpriced.MISSING_TOKEN_COUNT], "An Antigravity step reported no token count."),
    (REASON_LABELS[usage_unpriced.INDETERMINATE_RATE_PERIOD], (
        "No one dated Gemini API price covers the run's usage: it reaches both sides of a scheduled rate change, or"
        " nothing dates it."
    )),
    (REASON_LABELS[usage_unpriced.SUBAGENT_USAGE], (
        "The run handed work to an Antigravity subagent whose model and usage the stream does not report."
    )),
    (REASON_LABELS[usage_unpriced.SEVERAL_MODELS], (
        "The Antigravity run names more than one model, so none is the one its usage is priced as."
    )),
    (REASON_UNAVAILABLE, (
        "The run was recorded without a reason, as runs recorded by earlier versions were; nothing re-estimates it."
    )),
)

_SEPARATOR = " · "


def reason_label(reason: str | None) -> str:
    """One reason as the page names it; a run recorded with none reads `Reason unavailable`."""
    if reason is None:
        return REASON_UNAVAILABLE
    return REASON_LABELS.get(reason, REASON_UNAVAILABLE)


def run_reasons_text(
    cost: usage_cost.CostEvidence,
    reasons: Sequence[usage_unpriced.UnpricedReason],
) -> str | None:
    """Why one listed run is unpriced: its reasons grouped by model, or None where its cost is not unpriced.

    The reasons come in the order the usage owner's reader keeps, by model first, so each model is named once.
    """
    if cost.completeness != usage_cost.INCOMPLETE:
        return None
    if not reasons:
        return REASON_UNAVAILABLE
    grouped = itertools.groupby(reasons, key=attrgetter(usage_unpriced.MODEL))
    return _SEPARATOR.join(_model_reasons(model, given) for model, given in grouped)


def unpriced_reasons_html(rows: Sequence[UnpricedReasonRow]) -> str:
    """The selection's unpriced runs counted under each model and reason; nothing where it has none."""
    if not rows:
        return ""
    listed = "".join(map(_count_item, rows))
    return f"<p><b>{UNPRICED_REASONS_HEADING}</b></p><ul>{listed}</ul>"


def _model_reasons(model: str, given: Iterable[usage_unpriced.UnpricedReason]) -> str:
    labels = ", ".join(reason_label(reason.reason) for reason in given)
    return f"{model}: {labels}"


def _count_item(row: UnpricedReasonRow) -> str:
    noun = "run" if row.runs == 1 else "runs"
    counted = f"{row.runs:,} {noun}"
    line = _SEPARATOR.join((row.model, reason_label(row.reason), counted))
    return f"<li>{html.escape(line)}</li>"
