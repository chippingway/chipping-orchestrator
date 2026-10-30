# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an `agent_exit` record's usage evidence fills on its row, beside the fields copied off it.

The raw `cost_evidence` and `token_evidence` objects ride verbatim in `extras`, where SQL can neither validate nor
fold them, so the sync reads each record through the readers every other usage surface reads it through --
`usage.cost_evidence.recorded_cost` and `usage.token_evidence.recorded_tokens` -- and files what they answer in
columns a view can sum. Reading here, rather than re-deriving in SQL, is what keeps one definition of a valid amount,
a basis, and a non-overlapping total: a record without evidence, or with evidence the current format does not
serialize, is read as those readers read it (an `unknown` cost holding its `cost_usd` under the `unknown` basis, and a
token total only where no cache counter is nonzero), and nothing is inferred from its `cost_source`, backend, or
models.

Only an `agent_exit` record states usage, so every other event fills none of these columns. Nothing reprices or
re-adds anything: an amount is filed under the basis its contribution names, and an estimate's verification dates
are the ones its contribution recorded, sorted and deduplicated. The record itself, and so its `content_hash`, is
left as it was.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from orchestrator.observability.analytics.sync.columns import (
    COL_EVENT,
    COST_AMOUNT_COLUMNS,
    COST_COMPLETENESS,
    RATE_DATE_COLUMNS,
    TOKEN_CACHE_OVERLAP,
    TOTAL_TOKENS,
)
from orchestrator.observability.usage import (
    cost_evidence as usage_cost,
    token_evidence as usage_tokens,
)

AGENT_EXIT_EVENT = "agent_exit"


def derived_columns(record: dict) -> dict[str, Any]:
    """The evidence columns one record fills; none for a record that states no usage."""
    if record.get(COL_EVENT) != AGENT_EXIT_EVENT:
        return {}
    cost = usage_cost.recorded_cost(record)
    tokens = usage_tokens.recorded_tokens(record)
    return {
        COST_COMPLETENESS: cost.completeness,
        **cost_amount_cells(cost),
        **rate_date_cells(cost),
        TOKEN_CACHE_OVERLAP: tokens.cache_overlap,
        TOTAL_TOKENS: tokens.total(record),
    }


def cost_amount_cells(cost: usage_cost.CostEvidence) -> dict[str, float]:
    """Each contribution's amount under its basis's column, a zero included."""
    return {
        COST_AMOUNT_COLUMNS[contribution.basis]: contribution.amount_usd
        for contribution in cost.contributions
    }


def rate_date_cells(cost: usage_cost.CostEvidence) -> dict[str, list[date]]:
    """Each estimate's verification dates under its basis's column; a basis priced at no dated row has none."""
    return {
        RATE_DATE_COLUMNS[contribution.basis]: sorted(set(contribution.rates_verified_on))
        for contribution in cost.contributions
        if contribution.basis in RATE_DATE_COLUMNS and contribution.rates_verified_on
    }
