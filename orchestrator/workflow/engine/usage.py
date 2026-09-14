# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Invoke an agent only after its lifetime run charge is durable.

Requests identify the logical round; the run circuit reserves and starts its
charge before any process is invoked. Spawn and exit records bracket the real
runner call, and its result is returned intact for the stage to settle. Request
construction, exit reporting, and issue-wide usage totals have sibling owners."""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

from orchestrator.agents import runner as _agent_runner
from orchestrator.agents.models import AgentResult
from orchestrator.github.client import GitHubClient
from orchestrator.workflow.engine import (
    run_charge_state as _run_charge_state,
    run_circuit as _run_circuit,
    run_reporting as _run_reporting,
    run_requests as _run_requests,
)

log = logging.getLogger("orchestrator.workflow")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _run_agent_tracked(
    gh: GitHubClient,
    budget: _run_charge_state.AgentRunBudget,
    request: _run_requests._AgentRunRequest | None = None,
    **request_fields: Any,
) -> AgentResult:
    """Run an agent, bookending the spawn with `agent_spawn` / `agent_exit`
    audit events and appending a per-invocation analytics record on exit.

    The `budget` names the issue a charge is written on and the pinned state
    the caller will write at the end of the run, and it is required rather
    than optional: the lifetime agent-run ledger is charged immediately around
    the spawn by `workflow/engine/run_circuit.py`, and a spawn road that could
    omit the context would be a road that spends runs nothing counts. It is
    also where the issue number every audit and analytics field below is
    stamped with comes from, so the charge and the record cannot name
    different issues.

    That is the one place a charge covers every role at once: this is the sole
    low-level `run_agent` call in the repository, so a gate here is a gate no
    road walks around. A launch the circuit refuses returns an interrupted
    result WITHOUT emitting `agent_spawn`, invoking a process, or recording an
    exit -- there is no run to bookend. What it leaves instead is on the
    circuit's own budget stream, which is where the charge an ordinary launch
    pays is recorded too. The charge goes to freshly read
    durable state and only the fields it wrote come back onto the caller's
    object, so a reviewer spec, a moved watermark, or a session id staged
    before the spawn is still the handler's own write to make.

    Thin wrapper around `run_agent` otherwise -- the spawn behaviour is
    unchanged. Optional context (`review_round`, `retry_count`, resume session
    id) is forwarded so downstream consumers can correlate spawns with retry
    budgets and reviewer rounds. The exit record carries
    `exit_code`/`timed_out`/`duration_s` from the AgentResult so an
    operator tailing the JSONL sink sees timeouts and crashes without
    needing the orchestrator log too. An exception out of `run_agent`
    propagates -- the audit log will show a spawn without a matching
    exit, which is intentional (the per-issue `tick()` catch above logs
    the traceback).

    After the audit `agent_exit` is emitted, an analytics record is
    appended to `ANALYTICS_LOG_PATH` via the recording owner's
    `append_record` (a no-op when the sink is disabled). The record carries
    the same contextual fields (`repo`, `issue`, `stage`, `agent_role`, `backend`,
    `agent_spec`, `resume_session_id` / `session_id`, `review_round`,
    `retry_count`, `duration_s`, `exit_code`, `timed_out`) plus parsed
    token counts, model list, `cost_usd`, and `cost_source` extracted
    from `result.stdout` by `observability/usage/metrics.py`'s
    `parse_agent_usage`. The configured model is pulled out of
    `extra_args` (via `_configured_model`) and passed as the parser's
    `fallback_model` so a codex run whose stdout omits the model name
    still records the configured model and an estimated cost when the
    SKU is in the price table. Prompts, raw stdout/stderr, secrets, and
    worktree contents are intentionally NOT stored in this `agent_exit`
    record -- the analytics sink is a foundation for usage / cost
    aggregation, not a debugging mirror, and `result.stdout` may contain
    user-issue text. A parser failure or a sink IO error is swallowed so
    an analytics misconfiguration cannot stop the per-issue tick.

    The returned `AgentResult` additionally carries the parsed run usage on its
    `usage` field -- `record_agent_exit` attaches the `UsageMetrics` it parsed
    from the same stdout, independent of whether the sink is enabled -- so
    callers can read token / cost metrics off the result without re-parsing.
    It is `None` when the usage parse failed (fail-open); this is best-effort
    observability plumbing and does not touch the pinned state.

    The `prompt` is forwarded to `record_agent_exit` so it can land as the
    redacted `user_input` of the separate, opt-in trajectory record -- and
    ONLY when `TRAJECTORY_LOG_PATH` is enabled. With the trajectory sink off
    (the default) the prompt is never stored and the `agent_exit` record
    shape is unchanged. That trajectory parse / redact / write rides its own
    fail-open guard inside `record_agent_exit`, so it never disturbs the
    baseline record or the `skill_triggered` events below.

    The worktree `cwd` is also forwarded so `record_agent_exit` can discover
    a codex run's offered skills out-of-band from the filesystem -- codex's
    stream carries no offered-skills catalog the way claude's `system`/`init`
    frame does, so this backfills `skills_available` for codex records.

    When `TRACK_SKILL_TRIGGERS` is on, `record_agent_exit` returns the
    distinct skills the run triggered and one `skill_triggered` audit event
    is emitted per skill (carrying `agent`, `agent_role`, `review_round`,
    `retry_count`, and `skill`), reusing that parsed list rather than
    re-reading stdout. The switch off (the default) yields no list and thus
    no events, so the gating is inherited from the analytics layer; the
    emission is wrapped in its own fail-open guard so an opt-in bug can never
    cost a run whose baseline `agent_spawn` / `agent_exit` events already
    fired.
    """
    if request is not None and request_fields:
        raise TypeError("pass either request or keyword request fields, not both")
    run_request = request or _run_requests._AgentRunRequest(**request_fields)
    if not _run_circuit._charge_launch(gh, budget, run_request.launch):
        return _run_circuit._refused_run()
    start = time.monotonic()
    gh.emit_event(
        "agent_spawn",
        issue_number=budget.issue.number,
        stage=run_request.stage,
        agent=run_request.backend,
        agent_role=run_request.agent_role,
        session_id=run_request.resume_session_id,
        review_round=run_request.review_round,
        retry_count=run_request.retry_count,
    )
    # Forward only the kwargs the original call sites set so the
    # wrapper's run_agent invocation matches the pre-tracking signature
    # call-for-call (test fakes assert on `call.kwargs`).
    agent_result = _agent_runner.run_agent(
        run_request.backend,
        run_request.prompt,
        run_request.cwd,
        **_run_requests._agent_run_kwargs(run_request),
    )
    duration_s = round(time.monotonic() - start, 3)
    triggered_skills = _run_reporting._record_tracked_agent_exit(
        gh, budget.issue.number, run_request, agent_result, duration_s,
    )
    # One `skill_triggered` audit event per distinct triggered skill, reusing
    # the list `record_agent_exit` already parsed (no second pass over stdout).
    # Empty unless `TRACK_SKILL_TRIGGERS` is on, so the gating is inherited
    # from the analytics layer. This is opt-in observability, so it rides its
    # own fail-open guard exactly like the skill parse does -- a bug here must
    # never break a run whose baseline audit events have already fired.
    _run_reporting._emit_triggered_skills(
        gh, budget.issue.number, run_request, triggered_skills,
    )
    return agent_result
