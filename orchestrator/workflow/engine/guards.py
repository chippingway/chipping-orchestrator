# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a finished agent run is allowed to leave behind.

Three of these decline a run's outcome and one publishes it, but all four live
in the same window -- after the spawn returns, before the handler's
`gh.write_pinned_state` -- and they share one rule: the handler owns that
write. `_ignore_if_never_invoked`, `_ignore_if_interrupted`, and
`_paused_during_agent_run` say "not this
run" by returning True and letting the caller `return` without writing, so the
in-memory `PinnedState` mutations it already staged are dropped and the next
tick re-derives the run from the state the prior tick left. `_park_awaiting_human`
goes the other way -- it posts the HITL comment, sets `awaiting_human`, forwards
explicit bounded correlation fields to the emitted event and analytics sink, and
ratchets `last_action_comment_id` past it -- and still leaves the write to the
caller, so a park composes with whatever else that handler staged rather than
committing ahead of it.

The three refusals answer different questions and none covers the others.
A launch that never became a process is read off the result the agent-run
circuit hands back in place of one. Interruption is read off the result the
shutdown sweep produced. A mid-run
`paused` / `backlog` is visible only on a FRESHLY fetched issue: the dispatcher
screened the hard-skip labels once at tick start, and the handler has been
holding that snapshot for however long the agent ran.

The first two are asked in that order wherever a stage inspects the worktree
before it asks about interruption -- and several do, deliberately. What a
killed run left on disk is the operator's to see; what a launch that never
started left is nothing, so the tree it would be read on says nothing about it.
"""
from __future__ import annotations

import contextlib
import logging
import math
from typing import Any

from github.Issue import Issue

from orchestrator.agents.models import AgentResult
from orchestrator.github.client import GitHubClient
from orchestrator.github.labels import hard_skip_control_label
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.state import stage_name

log = logging.getLogger("orchestrator.workflow")


def _ignore_if_interrupted(issue: Issue, agent_result: AgentResult) -> bool:
    """True when `agent_result` came from a run the shutdown sweep killed
    mid-flight (SIGTERM/SIGKILL -- `AgentResult.interrupted`).

    Such a run carries no trustworthy outcome: `last_message` is empty or a
    partial transcript chunk and no commit / question / timeout signal can be
    read from it. Dev-resume stage handlers call this BEFORE their
    timeout/question/dirty/push branches and `return` WITHOUT writing pinned
    state on a True result, so durable GitHub state stays exactly as the prior
    tick left it and the next orchestrator process re-runs the resume from
    scratch. Returning quietly here is what keeps the interrupted path from
    posting an agent-question HITL comment, consuming an `awaiting_human`
    park, advancing an action/comment watermark, or interpreting partial
    `last_message` content -- all of which the in-memory `state` mutations the
    caller already made would persist on a normal `write_pinned_state`.

    Logs once at INFO so the interruption is visible without being mistaken
    for a real silence/timeout park.
    """
    if not agent_result.interrupted:
        return False
    log.info(
        "issue=#%d agent run interrupted by shutdown sweep; leaving durable "
        "state untouched for retry by the next process",
        issue.number,
    )
    return True


def _ignore_if_never_invoked(issue: Issue, agent_result: AgentResult) -> bool:
    """True when no process was ever invoked for `agent_result`.

    The answer a launch the agent-run circuit turned away carries
    (`workflow/engine/run_circuit.py`): the lifetime ledger was spent, the
    pinned comment could not be read, or the charge could not be written, and
    nothing was spawned.

    Asked BEFORE any inspection of what a run left behind, which is the one
    place it differs from `_ignore_if_interrupted` below it. Several stages
    read the worktree ahead of that guard on purpose -- a run the shutdown
    sweep killed can have written before it died, and a contaminated tree is
    an operator's to see whether or not the run counted. A launch that never
    started wrote nothing, so a tree dirty for some older reason is not its
    doing, and a park taken in its name would replace the durable one the
    circuit had already recorded with a reason about a process that never
    existed.

    Callers `return` without writing pinned state, exactly as they do for an
    interruption. Nothing is logged loudly here: the refusal was already
    recorded where it was decided, and this is that decision arriving.
    """
    if agent_result.invoked:
        return False
    log.debug(
        "issue=#%d agent launch was refused before any process started; "
        "leaving durable state to whatever refused it",
        issue.number,
    )
    return True


def _paused_during_agent_run(gh: GitHubClient, issue: Issue) -> bool:
    """True when a hard-skip control label (`paused` / `backlog`) was applied
    to `issue` while an agent run was in flight.

    The dispatcher and `_process_issue` read the issue's labels once, at tick
    start, and skip a hard-skipped issue before any handler runs. But a stage
    that spawns an agent holds that label snapshot for the whole run -- minutes,
    typically -- so an operator who applies `paused` mid-run would otherwise not
    take effect until the run's results were already published: PR opened, label
    flipped, HITL park posted, action watermark consumed, pinned state advanced.

    Stage handlers call this right after an agent run returns, BEFORE any of
    that disposition, and `return` WITHOUT writing pinned state on a True result
    -- mirroring `_ignore_if_interrupted`. Durable GitHub state is left exactly
    as the prior tick had it and the agent's committed work stays on the branch,
    so once the operator removes the label the next tick republishes it through
    the normal recovered-worktree path.

    The label is read from a FRESHLY fetched issue (`gh.get_issue`), never the
    stale handler `issue` whose labels were snapshotted before the run -- the
    whole point is to catch a label applied mid-run. A fetch failure returns
    False (publish as before): the guard is an additive safety net and must not
    itself strand a run that would otherwise have completed.
    """
    try:
        fresh = gh.get_issue(issue.number)
    except Exception:  # noqa: BLE001 - the guard is additive and must not strand a finished run
        log.debug(
            "issue=#%d not retrievable for post-agent pause check; proceeding",
            issue.number,
        )
        return False
    skip_label = hard_skip_control_label(fresh)
    if skip_label is None:
        return False
    log.info(
        "issue=#%d acquired %r during the agent run; leaving durable state "
        "untouched until the label is removed",
        issue.number, skip_label,
    )
    return True


ALLOWED_CORRELATION_FIELDS: frozenset[str] = frozenset((
    "route",
    "agent_role",
    "backend",
    "agent_spec",
    "session_id",
    "resume_session_id",
    "review_round",
    "retry_count",
    "pr_number",
    "conflict_round",
    "dirty_files",
    "exit_code",
    "timed_out",
    "sha",
    "reservation_id",
))


def _safe_int(candidate: object) -> int | None:
    """Strictly normalize candidate to an int fail-open, dropping non-integers."""
    if isinstance(candidate, bool) or candidate is None:
        return None
    if isinstance(candidate, int):
        return candidate
    if isinstance(candidate, float) and math.isfinite(candidate) and candidate.is_integer():
        return int(candidate)
    if isinstance(candidate, str):
        with contextlib.suppress(ValueError, OverflowError):
            return int(candidate)
    return None


def _park_awaiting_human(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    message: str,
    **correlation: Any,
) -> None:
    """Post `message` and mark the issue as awaiting a human reply.

    Caller is responsible for `gh.write_pinned_state` afterwards (mirrors the
    existing _on_question / _on_dirty_worktree contract). Clears any stale
    `park_reason` -- a transient park (e.g. in_review `unmergeable`)
    followed by a follow-up question/timeout park would otherwise leave
    the transient reason behind. Callers that re-park for a transient
    reason re-set `park_reason` immediately after this call.

    `reason` is recorded only in the emitted `park_awaiting_human` audit
    event; the durable `park_reason` field in pinned state is still cleared
    here (callers that need a transient reason re-set it themselves -- see
    above), so passing a reason does not change observable behavior.
    Explicit bounded correlation fields passed via keyword arguments
    (`correlation`) forward to the emitted event and fan out to the analytics
    sink, sharing the same correlation payload across audit and analytics.
    Unsupported correlation fields raise `TypeError` so unexpected fields
    are rejected before audit emission.

    The watermark is the id of the notice this call POSTED, not the id the
    thread happens to end on afterwards. The two differ in exactly one case
    and it is the one that matters: a human replying between the post and this
    write. Read off the thread, their reply becomes the watermark and is
    skipped for good -- on a park whose whole point is waiting for a reply,
    that is the answer being thrown away by the question. Read off the comment
    we wrote, their reply is still there for the next poll.

    A post whose id nothing could read falls back to the thread's tip, which
    is the lesser of the two failures left: a watermark that never moved
    leaves the park's own notice to be read back as somebody's fresh guidance
    on every dispatch after this one.
    """
    reason = correlation.pop("reason", None)
    unsupported = set(correlation) - ALLOWED_CORRELATION_FIELDS
    if unsupported:
        raise TypeError(
            f"_park_awaiting_human received unsupported correlation field(s): "
            f"{sorted(unsupported)}"
        )
    posted = _comments._post_issue_comment(gh, issue, state, message)
    state.set("awaiting_human", True)
    state.set("park_reason", None)
    said = getattr(posted, "id", None)
    latest = gh.latest_comment_id(issue) if said is None else said
    if latest is not None:
        state.set("last_action_comment_id", latest)
    # Read the label AFTER the comment post and state writes so the
    # captured stage reflects the handler that drove the park (the label
    # itself is unchanged by this call -- callers relabel only after the
    # `write_pinned_state` they do next).
    gh.emit_event(
        "park_awaiting_human",
        issue_number=issue.number,
        stage=stage_name(gh.workflow_label(issue)),
        reason=reason,
        **correlation,
    )
