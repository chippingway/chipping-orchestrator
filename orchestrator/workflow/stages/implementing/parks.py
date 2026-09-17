# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Classify an agent result that produced no publishable commit and park it.

Session limits, transient provider failures, and silent exits retain their
retryable reason and streak. Real questions clear that reason and streak.
Each park emits its event and leaves the state write to the caller. Its
reply watermark stops before any unclaimed human comment from the run.

The classification is what the emitted reason says, and the two deliberately
disagree with the durable `park_reason` beside them: a quota stop and a
provider refusal report themselves by name while pinning the retryable
`agent_silent` the continue command keys off, and a real question reports
`agent_question` against a `park_reason` left null, because null there is what
tells a later tick this park needs a human's actual guidance. The correlation
the record carries beside the reason comes from `park_correlation`, which is
also where the road that produced the run is named.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.agents import provider_failures as _provider_failures
from orchestrator.agents.models import AgentResult
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    agent_diagnostics as _agent_diagnostics,
    comments as _comments,
    guards as _guards,
)
from orchestrator.workflow.stages.implementing import (
    park_correlation as _park_correlation,
    park_watermarks as _park_watermarks,
    session_read as _session_read,
    state as _state,
)
from orchestrator.workflow.state import stage_name

log = logging.getLogger("orchestrator.workflow")


def _mark_agent_silent_park(state: PinnedState) -> None:
    """Flag a retryable `agent_silent` park and advance the silent-park streak.

    Shared by the session-limit and empty-output parks: both are retryable
    `agent_silent` failures, not real questions. `_resume_dev_with_text` reads
    the streak (via `_dev_session_retirement_reason`) to rotate a poisoned
    session to a fresh spawn once it reaches `_SILENT_PARKS_BEFORE_FRESH_SESSION`.
    """
    count = int(state.get(_state._SILENT_PARK_COUNT) or 0)
    state.set(_state._AWAITING_HUMAN, True)
    state.set(_state._PARK_REASON, "agent_silent")
    state.set(_state._SILENT_PARK_COUNT, count + 1)


def _park_session_limit(
    gh: GitHubClient, issue: Issue, state: PinnedState, raw: str
) -> str:
    """Park a session/usage-quota notice as a RETRYABLE session failure.

    A known quota notice ("You've hit your session limit ...") is non-empty but
    is NOT a real agent question: the session is healthy, the account quota is
    exhausted, and the only recovery is to wait for the reset and retry.
    Parking it as `agent_silent` (the same reason a silent poisoned resume
    uses) lets an operator's `/orchestrator continue` after the reset drop the
    session and re-ground a fresh one; classifying it as a real question
    (`park_reason=None`) would refuse that continue as "needs your actual
    guidance". The silent-park streak is incremented so a session that keeps
    returning the quota notice is eventually rotated, mirroring the
    empty-message branch. Returns the distinct EVENT reason
    (`agent_session_limit`) for observability -- the pinned `park_reason` stays
    `agent_silent` (the control field `/orchestrator continue` keys off).
    """
    quoted = _session_read._as_blockquote(raw)
    _comments._post_issue_comment(
        gh, issue, state,
        f"{config.HITL_MENTIONS} agent hit a session/usage limit and "
        "stopped; retry with `/orchestrator continue` once it "
        f"resets:\n\n{quoted}",
    )
    _mark_agent_silent_park(state)
    return "agent_session_limit"


def _park_provider_unavailable(
    gh: GitHubClient, issue: Issue, state: PinnedState, raw: str
) -> str:
    """Park a transient provider refusal as a RETRYABLE session failure.

    An `API Error: 529 Overloaded` reaches this stage as an ordinary non-empty
    final message, so without this branch it would be posted as "agent needs
    your input" -- a question the operator cannot answer, whose reply then
    RESUMES the same session and gets the same refusal back. The park is the
    one a quota stop takes: `agent_silent`, so `/orchestrator continue` drops
    the failed session, re-grounds a fresh one on the preserved fixing batch,
    and skips the feedback debounce. The bookmarks that batch is rebuilt from
    (`pending_fix_*`, `pending_fix_reviewer_comment_id`) are untouched here --
    only a pushed fix retires them.

    The comment names the command verbatim because a retry is the whole
    recovery and any other reply would be read as implementation guidance.
    Returns the distinct EVENT reason for observability; the pinned
    `park_reason` stays `agent_silent`.
    """
    quoted = _session_read._as_blockquote(raw)
    _comments._post_issue_comment(
        gh, issue, state,
        f"{config.HITL_MENTIONS} the model provider is temporarily "
        "unavailable, so the agent stopped before doing any work. Nothing "
        "here needs your judgment: reply with exactly `/orchestrator "
        "continue` to retry this on a fresh session.\n\n"
        f"{quoted}",
    )
    _mark_agent_silent_park(state)
    return "agent_provider_unavailable"


def _park_real_question(
    gh: GitHubClient, issue: Issue, state: PinnedState, raw: str
) -> str:
    """Park a genuine agent clarification question awaiting a human reply."""
    quoted = _session_read._as_blockquote(raw)
    _comments._post_issue_comment(
        gh, issue, state,
        f"{config.HITL_MENTIONS} agent needs your input to proceed:\n\n{quoted}",
    )
    state.set(_state._AWAITING_HUMAN, True)
    # Real question parks are not transient: they need a human reply before the
    # in_review ready-ping gates should run again. Clear any stale
    # `park_reason` left behind by a prior in_review unmergeable park, and reset
    # the silent-park streak.
    state.set(_state._PARK_REASON, None)
    state.set(_state._SILENT_PARK_COUNT, 0)
    return "agent_question"


def _park_silent_failure(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    agent_result: AgentResult,
) -> str:
    """Park a run that produced no commit AND no message as a silent failure.

    Callers only invoke `_on_question` when the worktree has no new commits, so
    an empty `last_message` is a silent failure, not a content question -- most
    often a poisoned resume of a session killed mid-stream (e.g. by a Claude
    rate limit). Tag the park `agent_silent` so `_resume_dev_with_text` can
    drop the dev session id after enough consecutive silent parks, and surface
    the situation accurately instead of impersonating a real question park.
    """
    diag = _agent_diagnostics._format_stderr_diagnostics(agent_result, "Agent")
    _comments._post_issue_comment(
        gh, issue, state,
        f"{config.HITL_MENTIONS} agent produced no output (likely a "
        f"session-resume failure); manual intervention needed.{diag}",
    )
    log.warning(
        "issue=#%s agent produced no output; exit_code=%d "
        "timed_out=%s stderr_tail=%r",
        issue.number, agent_result.exit_code, agent_result.timed_out,
        _agent_diagnostics._stderr_log_tail(agent_result),
    )
    _mark_agent_silent_park(state)
    return "agent_silent"


def _on_question(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    parked: _guards._ParkedRun,
) -> None:
    """Classify what a run with no publishable commit left, park it, report it.

    The final message is what picks the branch: the two classifiers match
    known quota and provider-refusal phrasings as a PREFIX of it, and an empty
    one is a silent exit. What the reported reason names is the branch that
    ran, though, so the emitted vocabulary stays the closed set above however
    the agent phrased itself.

    The correlation beside it is the part built from no prose at all. The road
    comes off `parked`, since the stage the event reads from the label is held
    by several of them, and every other field is a structured identifier the
    caller already had -- never the last message, the prompt, the captured
    streams, or anything else an operator would have to redact to read a sink.
    """
    # Taken before anything is posted, because what separates this park's own
    # notice from a human's comment afterwards is which of them this ledger
    # gained.
    said_before = _comments._orchestrator_ids(state)
    agent_result = parked.agent_result
    raw = agent_result.last_message.strip()
    if raw and _session_read._is_session_limit_message(agent_result):
        park_reason = _park_session_limit(gh, issue, state, raw)
    elif raw and _provider_failures.is_transient_provider_failure(agent_result):
        park_reason = _park_provider_unavailable(gh, issue, state, raw)
    elif raw:
        park_reason = _park_real_question(gh, issue, state, raw)
    else:
        park_reason = _park_silent_failure(gh, issue, state, agent_result)
    read_to = _park_watermarks._read_this_far(gh, issue, state, said_before)
    if read_to is not None:
        state.set(_state._LAST_ACTION_COMMENT_ID, read_to)
    gh.emit_event(
        "park_awaiting_human",
        issue_number=issue.number,
        stage=stage_name(gh.workflow_label(issue)),
        reason=park_reason,
        **_park_correlation._correlated_fields(state, parked),
    )
