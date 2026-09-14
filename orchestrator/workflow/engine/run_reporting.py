# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Agent-exit analytics and triggered-skill audit records for completed invocations.

The actual request supplies the model fallback and round identity. A failure to
record triggered skills cannot discard an agent result the workflow must settle."""
from __future__ import annotations

import logging

from orchestrator.agents.models import AgentResult
from orchestrator.github.client import GitHubClient
from orchestrator.observability.analytics.recording import agent_exit as _agent_exit_records
from orchestrator.workflow.engine import (
    run_requests as _run_requests,
)

log = logging.getLogger("orchestrator.workflow")



def _record_tracked_agent_exit(
    gh: GitHubClient,
    issue_number: int,
    request: _run_requests._AgentRunRequest,
    agent_result: AgentResult,
    duration_s: float,
):
    gh.emit_event(
        "agent_exit",
        issue_number=issue_number,
        stage=request.stage,
        agent=request.backend,
        agent_role=request.agent_role,
        session_id=agent_result.session_id,
        duration_s=duration_s,
        exit_code=agent_result.exit_code,
        timed_out=agent_result.timed_out,
        review_round=request.review_round,
        retry_count=request.retry_count,
    )
    return _agent_exit_records.record_agent_exit(
        repo=getattr(gh, "_repo_slug", None) or "",
        issue=issue_number,
        stage=request.stage,
        agent_role=request.agent_role,
        backend=request.backend,
        agent_spec=request.agent_spec,
        resume_session_id=request.resume_session_id,
        result=agent_result,
        duration_s=duration_s,
        review_round=request.review_round,
        retry_count=request.retry_count,
        fallback_model=_configured_model(request.backend, request.extra_args),
        prompt=request.prompt,
        cwd=request.cwd,
    )


def _emit_triggered_skills(
    gh: GitHubClient,
    issue_number: int,
    request: _run_requests._AgentRunRequest,
    triggered_skills,
) -> None:
    try:
        for skill in triggered_skills or ():
            gh.emit_event(
                "skill_triggered",
                issue_number=issue_number,
                stage=request.stage,
                agent=request.backend,
                agent_role=request.agent_role,
                review_round=request.review_round,
                retry_count=request.retry_count,
                skill=skill,
            )
    except Exception:
        log.exception(
            "issue=#%d: skill_triggered audit emission failed; continuing",
            issue_number,
        )


def _configured_model(
    backend: str, extra_args: tuple[str, ...]
) -> str | None:
    """Pull the configured model name out of a backend's `extra_args`.

    codex selects the model with `-m <model>` (or `-m=<model>`); claude
    uses `--model <model>` (or `--model=<model>`). Whichever is present
    is forwarded to `observability/usage/metrics.py`'s
    `parse_agent_usage` as `fallback_model` so a codex run whose stdout
    carries usage frames but omits the model (resume frames, minimal
    completions, schema drift) still produces a populated `models` list
    and -- when the model is in the price table -- an estimated
    `cost_usd`. Returns `None` when neither flag is set so the parser
    keeps its own "unknown" handling.

    The split-form (`-m gpt-5`) and `=`-form (`--model=gpt-5`) are both
    accepted because `shlex.split` produces either shape depending on
    the operator's quoting; only one needs to win.
    """
    flag = "-m" if backend == "codex" else "--model"
    eq_prefix = f"{flag}="
    for arg_index, arg in enumerate(extra_args):
        if arg == flag and arg_index + 1 < len(extra_args):
            model_name = extra_args[arg_index + 1].strip()
            return model_name or None
        if arg.startswith(eq_prefix):
            model_name = arg[len(eq_prefix):].strip()
            return model_name or None
    return None
