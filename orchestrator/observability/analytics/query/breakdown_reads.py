# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The five reads whose grouping key the day-bucketed rollup threw away.

Each one binds its keyword call against the signature its family is declared
with, resolves the connection behind it, and hands the filtered window to the
projection owner beside it. Every signature is a shared one re-annotated with
what the read returns, so the vocabulary a caller writes stays declared once
while the return type stays readable on the function it belongs to.

The column the rollup does not carry is what these five have in common. A
review round, a cost source, and one run's own token split are per-run facts
the day bucket aggregated away, so those three scan the agent-run view; an hour
of day is what that bucket rounded off, so the heatmap stays on the events
table beneath it; and why a run went unpriced rides in its `extras` blob, which
only the events table holds, so that count scans it too.

Two answers are decided here rather than in SQL. A database that is not
configured -- and no caller-owned connection to fall back on -- yields an empty
list rather than an error, because "not wired up yet" is a page state and not a
failure. And the agent-run view has no `event` column to push a selection into,
so the three reads on it return nothing without dialing when the selection
excludes `agent_exit`: the filter baked into the view could never match. The
heatmap scans the events table, where that selection becomes an ordinary
predicate, so no short circuit applies to it. The unpriced-reason count pins
`agent_exit` on that table itself, as the view does, so it short-circuits
alike.
"""

from __future__ import annotations

from typing import Any

from orchestrator.observability.analytics.query.activity_models import (
    BackendDailyTokensRow,
    HourlyHeatmapPoint,
)
from orchestrator.observability.analytics.query.backend_tokens import (
    backend_daily_token_rows,
)
from orchestrator.observability.analytics.query.conditions import agent_event_excluded
from orchestrator.observability.analytics.query.cost_coverage import cost_coverage_rows
from orchestrator.observability.analytics.query.cost_models import (
    CostCoverageRow,
    ReviewRoundBucketRow,
    UnpricedReasonRow,
)
from orchestrator.observability.analytics.query.hourly_heatmaps import (
    hourly_heatmap_rows,
)
from orchestrator.observability.analytics.query.requests import (
    FILTERED_READ_SIGNATURE,
    HEATMAP_SIGNATURE,
    bind_read_request,
    resolve_read_query,
    window_filters,
)
from orchestrator.observability.analytics.query.review_rounds import review_round_rows
from orchestrator.observability.analytics.query.unpriced_reasons import unpriced_reason_rows

_REVIEW_ROUND_SIGNATURE = FILTERED_READ_SIGNATURE.replace(
    return_annotation="list[ReviewRoundBucketRow]",
)
_COST_COVERAGE_SIGNATURE = FILTERED_READ_SIGNATURE.replace(
    return_annotation="list[CostCoverageRow]",
)
_UNPRICED_REASONS_SIGNATURE = FILTERED_READ_SIGNATURE.replace(
    return_annotation="list[UnpricedReasonRow]",
)
_BACKEND_DAILY_TOKENS_SIGNATURE = FILTERED_READ_SIGNATURE.replace(
    return_annotation="list[BackendDailyTokensRow]",
)
_HOURLY_HEATMAP_SIGNATURE = HEATMAP_SIGNATURE.replace(
    return_annotation="list[HourlyHeatmapPoint]",
)


def get_review_round_breakdown(
    *args: Any,
    **kwargs: Any,
) -> list[ReviewRoundBucketRow]:
    """Return per-review-round development and review cost buckets."""
    request = bind_read_request(_REVIEW_ROUND_SIGNATURE, args, kwargs)
    query = resolve_read_query(request)
    if not query.available:
        return []
    if agent_event_excluded(request.filters.events):
        return []
    return review_round_rows(query, window_filters(request))


get_review_round_breakdown.__signature__ = _REVIEW_ROUND_SIGNATURE


def get_cost_coverage(*args: Any, **kwargs: Any) -> list[CostCoverageRow]:
    """Return token-volume coverage grouped by cost source."""
    request = bind_read_request(_COST_COVERAGE_SIGNATURE, args, kwargs)
    query = resolve_read_query(request)
    if not query.available:
        return []
    if agent_event_excluded(request.filters.events):
        return []
    return cost_coverage_rows(query, window_filters(request))


get_cost_coverage.__signature__ = _COST_COVERAGE_SIGNATURE


def get_unpriced_reasons(*args: Any, **kwargs: Any) -> list[UnpricedReasonRow]:
    """Return the window's unpriced runs counted per model and reason, uncapped."""
    request = bind_read_request(_UNPRICED_REASONS_SIGNATURE, args, kwargs)
    query = resolve_read_query(request)
    if not query.available:
        return []
    if agent_event_excluded(request.filters.events):
        return []
    return unpriced_reason_rows(query, window_filters(request))


get_unpriced_reasons.__signature__ = _UNPRICED_REASONS_SIGNATURE


def get_backend_daily_tokens(
    *args: Any,
    **kwargs: Any,
) -> list[BackendDailyTokensRow]:
    """Return daily token totals grouped by backend."""
    request = bind_read_request(_BACKEND_DAILY_TOKENS_SIGNATURE, args, kwargs)
    query = resolve_read_query(request)
    if not query.available:
        return []
    if agent_event_excluded(request.filters.events):
        return []
    return backend_daily_token_rows(query, window_filters(request))


get_backend_daily_tokens.__signature__ = _BACKEND_DAILY_TOKENS_SIGNATURE


def get_hourly_heatmap(
    *args: Any,
    **kwargs: Any,
) -> list[HourlyHeatmapPoint]:
    """Return weekday-by-hour activity cells in the requested timezone."""
    request = bind_read_request(_HOURLY_HEATMAP_SIGNATURE, args, kwargs)
    query = resolve_read_query(request)
    if not query.available:
        return []
    return hourly_heatmap_rows(
        query,
        window_filters(request),
        request.options.tz_offset_hours,
    )


get_hourly_heatmap.__signature__ = _HOURLY_HEATMAP_SIGNATURE
