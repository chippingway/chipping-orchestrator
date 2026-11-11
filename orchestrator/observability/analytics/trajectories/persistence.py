# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Trajectory parsing, request collection, Codex enrichment, and fail-open persistence.

One owner for the whole opt-in write: whether it happens at all, what the
stream is parsed into, the request usage collected beside it, what a Codex
run's missing capabilities are backfilled from, and the guard the entire block
rides. They sit together because they are one decision -- the sink being off
is what makes the parse and the request collection never run, and the parse
failing is what the guard exists to swallow. The request collection rides a
narrower guard of its own inside that one, so a collector that fails costs the
trajectory nothing.

The gate reads the opt-in knob off the `settings` holder inside the call, and
the append it ends with is the `api` owner's own -- the sink is never reached
back through the recorders that composed this write. The redactor is named
inside the call, so the append path costs the credential owner nothing until
the sink an operator turned on has something to write.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from orchestrator.observability.analytics import config as analytics_config, sink
from orchestrator.observability.analytics.trajectories import api
from orchestrator.observability.analytics.trajectories.serialize import (
    build_trajectory_record,
)
from orchestrator.observability.usage import (
    metrics as usage_metrics,
    request_coverage as usage_request_coverage,
    trajectory as usage_trajectory,
    trajectory_models as usage_trajectory_models,
)

if TYPE_CHECKING:
    from orchestrator.observability.analytics.recording.models import (
        AgentExitContext,
        CodexCatalog,
    )


def codex_trajectory_changes(
    trajectory: usage_trajectory_models.AgentTrajectory,
    catalog: CodexCatalog,
) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    if catalog.available_skills and not trajectory.skills.available:
        changes["skills"] = replace(
            trajectory.skills,
            available=tuple(catalog.available_skills),
        )
    if catalog.tools and not trajectory.tools:
        changes["tools"] = tuple(catalog.tools)
    return changes


def collected_request_usage(
    context: AgentExitContext,
) -> usage_request_coverage.RequestUsage | None:
    """Collect the run's request usage behind a failure boundary of its own.

    The collector reads the run's stdout whether or not the CLI returned a
    session id, a failed or interrupted run's included, since what it printed
    is attributable to this invocation either way. A collector that raises
    logs and leaves a collection stating it failed, so the trajectory beside
    it -- and the baseline `agent_exit` record and the workflow behind that --
    are written exactly as they would have been.
    """
    try:
        return usage_trajectory.parse_agent_request_usage(
            context.backend,
            context.agent_result.stdout,
            context.fallback_model,
        )
    except Exception:  # noqa: BLE001 - request usage is dropped, never the trajectory
        sink.log.exception(
            "issue=#%d analytics: request usage collection(%s) failed; trajectory record is unaffected",
            context.issue,
            context.backend,
        )
        return usage_request_coverage.RequestUsage.failed()


def agent_trajectory(
    context: AgentExitContext,
    catalog: CodexCatalog,
) -> usage_trajectory_models.AgentTrajectory:
    trajectory = usage_trajectory.parse_agent_trajectory(
        context.backend,
        context.agent_result.stdout,
    )
    changes: dict[str, Any] = {"request_usage": collected_request_usage(context)}
    if context.backend == "codex":
        changes.update(codex_trajectory_changes(trajectory, catalog))
    return replace(trajectory, **changes)


def persist_trajectory_record(
    context: AgentExitContext,
    metrics: usage_metrics.UsageMetrics,
    codex_catalog: CodexCatalog,
) -> None:
    """Build and append the denormalized trajectory record.

    The redactor is reached inside the write rather than bound at import: it
    is the one thing this owner needs from outside the observability tree, and
    naming it here keeps a producer that imports the recording path from
    paying for the credential owner behind a sink that is off by default.
    """
    from orchestrator.config import credentials

    trajectory = agent_trajectory(context, codex_catalog)
    api.append_trajectory_record(
        build_trajectory_record(
            context,
            trajectory,
            metrics,
            credentials.redact_secrets,
        ),
    )


def maybe_record_trajectory(
    context: AgentExitContext,
    metrics: usage_metrics.UsageMetrics,
    codex_catalog: CodexCatalog,
) -> None:
    """Parse, redact, truncate, and append one trajectory record -- gated on
    the opt-in `TRAJECTORY_LOG_PATH` and wrapped in its own fail-open guard.

    A no-op when the trajectory sink is disabled (the default), so the
    orchestrator-built prompt (`user_input`) -- and the parse/redact work
    itself -- happens ONLY when an operator turned the sink on. `metrics` is
    the `UsageMetrics` `record_agent_exit` already parsed for the baseline
    `agent_exit` record; it is threaded through (never re-parsed) so the
    trajectory record can carry a denormalized `run_usage` summary. The whole
    block rides a dedicated try/except: a parser bug, an unredactable
    payload, or a sink IO failure logs and is swallowed so it can never drop
    the baseline `agent_exit` usage / cost record or the `skill_triggered`
    audit events, all of which were already produced before this runs.

    `codex_catalog` carries the out-of-band offered-skills and offered-tools
    sets `record_agent_exit` discovered for a codex run (empty for claude,
    whose offered sets already ride its stream). When present they backfill
    the codex trajectory's otherwise-empty
    `skills.available` / `tools` so the trajectory viewer's "Skills available"
    and "Tools offered" chips match a claude run's; a non-empty stream-parsed
    set is never overridden.
    """
    if analytics_config.live_settings().trajectory_log_path is None:
        return
    try:
        persist_trajectory_record(context, metrics, codex_catalog)
    except Exception:  # noqa: BLE001 - the trajectory is dropped, never the baseline record
        sink.log.exception(
            "issue=#%d analytics: trajectory record(%s) failed; baseline agent_exit record is unaffected",
            context.issue,
            context.backend,
        )
