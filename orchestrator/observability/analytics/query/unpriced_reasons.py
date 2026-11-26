# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Why a window's unpriced runs have no amount, counted by model and reason over the whole filtered selection.

A run's reasons are the `unpriced_reasons` its `agent_exit` record carried into the `extras` blob, which neither the
agent-run view nor the rollup holds, so this read scans the events table and pins `event = 'agent_exit'` itself, as
the recent-run read does -- but uncapped, so a count covers every unpriced run the filters select rather than the
newest few the run listing shows. A run is unpriced where the sync filed its completeness as `incomplete`; a run with
no cost evidence is no unpriced run, so it is counted nowhere here.

Each `{"model", "reason"}` entry counts its run once under that pair, so a run giving two reasons is counted under
both, and the rows overlap rather than add up to the unpriced runs. Only what the current producer writes is a reason:
an entry that is no object, names no model, or gives a reason outside the usage owner's vocabulary (`usage.unpriced`)
is none. An unpriced run whose record states no reason that way -- every one an earlier build recorded -- is counted
with no reason under each model its `models` names, `unknown` where it names none, and nothing re-estimates it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from orchestrator.observability.analytics.query.conditions import AGENT_EXIT_CONDITION, prepend_where_condition
from orchestrator.observability.analytics.query.cost_models import UnpricedReasonRow
from orchestrator.observability.analytics.query.execution import ReadQuery
from orchestrator.observability.analytics.query.filters import WindowFilters
from orchestrator.observability.analytics.query.predicates import build_window_where
from orchestrator.observability.usage import cost_evidence as usage_cost, protocol, unpriced as usage_unpriced

# The serialized reasons of a run as a JSON array, an empty one where its record carries none or no array.
_STATED = (
    f"CASE WHEN jsonb_typeof(extras->'{usage_unpriced.UNPRICED_REASONS}') = 'array' "
    f"THEN extras->'{usage_unpriced.UNPRICED_REASONS}' ELSE '[]'::jsonb END"
)

# The models a run names, or the one `unknown` model where it names none. The branches are separate, since only a CASE
# fixes the order Postgres evaluates them in, and an array's length is asked of nothing else.
_NO_MODEL = f"'[\"{protocol.UNKNOWN}\"]'::jsonb"
_NAMED_MODELS = (
    f"CASE WHEN jsonb_typeof(models) IS DISTINCT FROM 'array' THEN {_NO_MODEL} "
    f"WHEN jsonb_array_length(models) = 0 THEN {_NO_MODEL} ELSE models END"
)

_REASON_LIST = ", ".join("%s" for _ in usage_unpriced.REASONS)

# An entry the current vocabulary writes: an object naming a model and one of its reasons.
_CURRENT_ENTRY = (
    f"jsonb_typeof(entry->'{usage_unpriced.MODEL}') = 'string' "
    f"AND entry->>'{usage_unpriced.MODEL}' <> '' "
    f"AND entry->>'{usage_unpriced.REASON}' IN ({_REASON_LIST})"
)


def unpriced_reason_from_row(row: Sequence[Any]) -> UnpricedReasonRow:
    """Project one per-model-and-reason row onto its result model."""
    return UnpricedReasonRow(
        model=str(row[0]),
        reason=None if row[1] is None else str(row[1]),
        runs=int(row[2] or 0),
    )


def unpriced_reason_rows(
    query: ReadQuery,
    filters: WindowFilters,
) -> list[UnpricedReasonRow]:
    """Return the window's unpriced runs counted per model and reason, the most affected first."""
    where, bindings = build_window_where(filters.without_events())
    where = prepend_where_condition(where, f"{AGENT_EXIT_CONDITION} AND cost_completeness = %s")
    bindings.insert(0, usage_cost.INCOMPLETE)
    rows = query.select(
        f"WITH unpriced_runs AS (SELECT id, models, {_STATED} AS stated FROM analytics_events{where}), "
        "stated_reasons AS ("
        f"SELECT unpriced_runs.id, entry->>'{usage_unpriced.MODEL}' AS model, "
        f"entry->>'{usage_unpriced.REASON}' AS reason "
        "FROM unpriced_runs CROSS JOIN LATERAL jsonb_array_elements(unpriced_runs.stated) AS entry "
        f"WHERE {_CURRENT_ENTRY}) "
        "SELECT model, reason, COUNT(DISTINCT id) AS runs FROM ("
        "SELECT id, model, reason FROM stated_reasons "
        "UNION ALL "
        "SELECT unpriced_runs.id, named.model, NULL FROM unpriced_runs "
        f"CROSS JOIN LATERAL jsonb_array_elements_text({_NAMED_MODELS}) AS named(model) "
        "WHERE unpriced_runs.id NOT IN (SELECT id FROM stated_reasons)"
        ") AS affected "
        "GROUP BY model, reason "
        "ORDER BY runs DESC, model ASC, reason ASC NULLS LAST",
        [*bindings, *usage_unpriced.REASONS],
    )
    return [unpriced_reason_from_row(row) for row in rows]
