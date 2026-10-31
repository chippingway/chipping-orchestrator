# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Usage parsing for one completed tracked agent run.

The token and cost half of an `agent_exit`: what the provider's stdout is
metered into, and the one boundary where a stream the parser cannot read
cancels the record instead of degrading it. The parsed metrics are also
attached back onto the result the caller still holds, which is what lets the
per-issue accounting count the same object the record was built from. The
record itself stays observational: the meter is the pinned comment's.
"""

from __future__ import annotations

from orchestrator.observability.analytics import sink
from orchestrator.observability.analytics.recording.models import AgentExitContext
from orchestrator.observability.usage import metrics as usage_metrics, price_catalogue


def parse_agent_exit_usage(
    context: AgentExitContext,
) -> usage_metrics.UsageMetrics | None:
    """Parse usage and attach it to the result, failing open on bad streams.

    The run has just exited, so its usage was spent over the `duration_s` seconds before now.
    """
    try:
        metrics = usage_metrics.parse_agent_usage(
            context.backend,
            context.agent_result.stdout,
            fallback_model=context.fallback_model,
            span=price_catalogue.UsageSpan.ending_now(context.duration_s),
        )
    except Exception:  # noqa: BLE001 - an unreadable stream cancels the record, not the tick
        sink.log.exception(
            "issue=#%d analytics: parse_agent_usage(%s) failed; skipping record",
            context.issue,
            context.backend,
        )
        return None
    context.agent_result.usage = metrics
    return metrics
