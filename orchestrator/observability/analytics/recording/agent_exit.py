# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The `agent_exit` flow: what one finished run is summarized into.

The order here is the contract. Usage is parsed first because a stream it
cannot read cancels the record entirely, the Codex catalog next because the
skill fields fall back to it, and the write last -- the allowlisted baseline
event, then the opt-in trajectory beside it under its own guard. The names
this composes are reached on the owners that define them; what this owner adds
is the sequence and the value the caller gets back, which is the list the
`skill_triggered` audit events are driven by rather than a second pass over
stdout.

The producer-facing recorder is here rather than beside its four siblings on
``events`` because this is the only family with a sequence to own. The
envelope and the append it ends with are the ``events`` owner's, imported at
module scope: this composition depends on that vocabulary, and nothing under
it depends back.
"""

from __future__ import annotations

from typing import Any

from orchestrator.observability.analytics.recording import events
from orchestrator.observability.analytics.recording.catalog import discover_codex_catalog
from orchestrator.observability.analytics.recording.models import (
    AGENT_EXIT_SIGNATURE,
    AgentExitContext,
    AgentExitSkillFields,
    CodexCatalog,
    bind_agent_exit,
)
from orchestrator.observability.analytics.recording.skills import parse_agent_exit_skills
from orchestrator.observability.analytics.recording.usage import parse_agent_exit_usage
from orchestrator.observability.analytics.trajectories import (
    persistence as trajectory_persistence,
)
from orchestrator.observability.usage import metrics as usage_metrics


def build_agent_exit_record(
    context: AgentExitContext,
    metrics: usage_metrics.UsageMetrics,
    skill_fields: AgentExitSkillFields,
) -> dict:
    """Build the allowlisted baseline event without raw run content."""
    return events.build_record(
        repo=context.repo,
        issue=context.issue,
        event="agent_exit",
        stage=context.stage,
        agent_role=context.agent_role,
        backend=context.backend,
        agent_spec=context.agent_spec,
        resume_session_id=context.resume_session_id,
        session_id=context.agent_result.session_id,
        review_round=context.review_round,
        retry_count=context.retry_count,
        duration_s=context.duration_s,
        exit_code=context.agent_result.exit_code,
        timed_out=context.agent_result.timed_out,
        input_tokens=metrics.input_tokens,
        output_tokens=metrics.output_tokens,
        cached_tokens=metrics.cached_tokens,
        cache_read_tokens=metrics.cache_read_tokens,
        cache_write_tokens=metrics.cache_write_tokens,
        models=list(metrics.models),
        turns=metrics.turns,
        cost_usd=metrics.cost_usd,
        cost_source=metrics.cost_source,
        skills_triggered=skill_fields.skills_triggered,
        skills_triggered_count=skill_fields.skills_triggered_count,
        skills_available=skill_fields.skills_available,
        skill_levels=skill_fields.skill_levels,
        skills_evidence=skill_fields.skills_evidence,
        skills_incidental=skill_fields.skills_incidental,
        skills_incidental_count=skill_fields.skills_incidental_count,
    )


def persist_agent_exit(
    context: AgentExitContext,
    metrics: usage_metrics.UsageMetrics,
    skill_fields: AgentExitSkillFields,
    codex_catalog: CodexCatalog,
) -> None:
    """Write the baseline event, then the independently guarded trajectory.

    The baseline append is dispatched on the `events` owner, which is what
    makes `patch.object(events, "append_record", ...)` intercept it. The
    trajectory owner is named directly rather than reached back through the
    sink, so one run's two records stay independent all the way down.
    """
    events.append_record(
        build_agent_exit_record(context, metrics, skill_fields),
    )
    trajectory_persistence.maybe_record_trajectory(
        context,
        metrics,
        codex_catalog,
    )


def record_agent_exit(*args: Any, **kwargs: Any) -> list[str] | None:
    """Parse, persist, and return triggered skills for one completed run."""
    context = bind_agent_exit(args, kwargs)
    metrics = parse_agent_exit_usage(context)
    if metrics is None:
        return None
    codex_catalog = discover_codex_catalog(context)
    skill_fields = parse_agent_exit_skills(context, codex_catalog)
    persist_agent_exit(context, metrics, skill_fields, codex_catalog)
    return skill_fields.skills_triggered


record_agent_exit.__signature__ = AGENT_EXIT_SIGNATURE
