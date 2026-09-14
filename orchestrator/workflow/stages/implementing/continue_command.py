# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""`/orchestrator continue` on a parked issue, and why it is not a comment.

A bare `/orchestrator continue` is an operator retrying a stopped session, not
new requirements, and it is recognized here before any drift or resume
processing for exactly that reason: read as an ordinary comment it would shift
the user-content hash and resume the dev as though the issue had been edited.

Which parks it answers is the point. `agent_silent` and `agent_timeout` are
session failures an operator can retry once the quota resets or the timeout is
understood; a real question park is not, so a continue that carries no guidance
is refused rather than replayed into a session that asked for words. The
refresh-time auto-rebase parks own their own retry comment, so this declines
them outright, and a continue that arrives ALONGSIDE genuine guidance is left
to the normal resume path, which feeds that guidance to the dev.

The spent spawn budget is the park asked ahead of all of that, and the one
where the command is the ONLY thing on a thread that means anything: what
stopped the issue is a budget rather than a missing answer, so words beside
the command are guidance for a developer nothing here can pay to run -- taken
with it rather than read instead of it -- and the classifier below would
refuse the one command that can lift the park as carrying no guidance. It is
also the one park that holds the tick with no command on the thread at all --
falling through, an ordinary reply would reach the resume, which takes the
flag down as a side effect and starts a session no budget was charged for.

The retry itself does not hand the command text to the agent: the poisoned
session already carries the issue context in its transcript, or the resume
rotates it to a re-grounded fresh spawn. The command comments are marked
consumed up front so the retry cannot re-fire next tick -- safe only because
every fresh comment being a bare continue is the retry's own precondition, so
nothing with content is dropped. `user_content_hash` is deliberately left alone:
masking it here would swallow a real body edit that landed in the same window.
"""
from __future__ import annotations

from dataclasses import dataclass

from github.Issue import Issue

from orchestrator import config
from orchestrator.git.base_sync import state as _base_sync_state
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.git.worktrees import (
    creation as _worktree_creation,
    naming as _naming,
    paths as _worktree_paths,
)
from orchestrator.github.client import GitHubClient
from orchestrator.github.comments import filter_trusted
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    guards as _guards,
    messages as _messages,
    prompts as _prompts,
    usage as _usage,
)
from orchestrator.workflow.stages.implementing import (
    disposition as _disposition,
    late_parks as _late_parks,
    models as _models,
    resume as _resume,
    retry_cap as _retry_cap,
    state as _state,
)


def _retry_parked_dev_session(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: PinnedState,
    new_comments: list,
) -> None:
    """Resume the locked dev session as an intentional `/orchestrator continue`
    retry of a session-failure park (`agent_silent` / `agent_timeout`), then
    dispose the result exactly like the awaiting-human resume path.

    Unlike the generic human-reply resume this does NOT feed the bare command
    text to the dev (`_prompts._CONTINUE_RETRY_PROMPT` instead): the poisoned
    session already carries the issue context in its transcript, or
    `_resume_dev_with_text` rotates it to a re-grounded fresh spawn. The
    command comment(s) are marked consumed up front so the retry does not
    re-fire next tick -- every fresh comment is a bare continue here (the
    classifier's retry precondition), so this drops no guidance.
    `user_content_hash` is deliberately NOT refreshed: a bare continue never
    shifts it, and masking it here would swallow a real body edit that landed
    in the same window before the dev could see it.
    """
    state.set(
        _state._LAST_ACTION_COMMENT_ID,
        max(comment.id for comment in new_comments),
    )
    wt = _worktree_paths._worktree_path(spec, issue.number)
    if not wt.exists():
        wt = _worktree_creation._ensure_worktree(
            spec, issue.number,
            branch=_naming._resolve_branch_name(state, spec, issue.number),
        )
    before_sha = _verification_probes._head_sha(wt)
    followup = f"{_prompts._CONTINUE_RETRY_PROMPT}\n\n{_prompts._FOREGROUND_ONLY_NOTE}"
    wt, agent_result, paused = _resume._resume_dev_with_text(
        gh, spec, issue, state, followup, pause_guard=True,
    )
    state.set("last_agent_action_at", _usage._now_iso())
    state.set(
        _state._BRANCH,
        _naming._resolve_branch_name(state, spec, issue.number),
    )
    # A shutdown-killed or live-paused resume leaves durable state untouched so
    # the next process re-detects and re-runs the retry (mirrors the drift and
    # fresh-spawn dispositions).
    if _guards._ignore_if_interrupted(issue, agent_result):
        return
    if paused:
        return
    _disposition._dispose_agent_result(
        gh, spec, issue, state,
        _models._PreparedDevRun(agent_result, before_sha, False, wt),
    )


def _handle_parked_continue_command(
    gh: GitHubClient, spec: config.RepoSpec, issue: Issue, state: PinnedState,
) -> bool:
    """Handle an operator `/orchestrator continue` on a parked `implementing`
    issue BEFORE generic user-content-drift / resume processing.

    `/orchestrator continue` is the recovery signal for a dev session that hit
    a session/usage limit, a transient provider refusal, or a silent failure
    (`_park_session_limit` / `_park_provider_unavailable` /
    `_park_silent_failure` tag all three `agent_silent`; an implementer timeout
    tags `agent_timeout`). Counting the bare command as an ordinary comment routed
    it through "issue body/content changed" drift handling and resumed the dev
    for the wrong reason (issue #729); a bare continue no longer shifts
    `user_content_hash`, and this handler routes it deliberately instead.

    Returns True when the command was fully handled this tick (an intentional
    retry ran, or a refusal was posted) and the caller must return. Returns
    False to fall through to the normal flow: the issue is not parked, the park
    belongs to the refresh-time rebase loop, there is no new comment, no
    continue command is present, or the command arrived alongside genuine
    guidance (which the normal resume / drift path feeds to the dev).

    The spent-budget park is asked first and answers for its own command, so
    the classifier below never sees one: it would read a continue there as a
    nudge at a park waiting for guidance and refuse it, which is the wrong
    thing to tell an operator whose command is the only reply that park can
    act on. That question also holds the tick whenever the park stands
    unanswered, so False past it is an issue this budget is not stopping.
    """
    if _retry_cap._park_owns_the_tick(gh, issue, state):
        return True
    decision = _parked_continue_decision(gh, issue, state)
    if decision is None:
        return False
    if decision.action == "refuse":
        _messages._refuse_parked_continue(gh, issue, state)
        gh.write_pinned_state(issue, state)
    else:
        _retry_parked_dev_session(
            gh, spec, issue, state, decision.comments,
        )
    return True


@dataclass(frozen=True)
class _ParkedContinueDecision:
    action: str
    comments: list


def _parked_continue_decision(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> _ParkedContinueDecision | None:
    if not state.get(_state._AWAITING_HUMAN):
        return None
    park_reason = state.get(_state._PARK_REASON)
    # Refresh-time auto-rebase parks own their operator retry comment.
    if park_reason in _base_sync_state._AUTO_REBASE_PARK_REASONS:
        return None
    comments = filter_trusted(
        gh.comments_after(issue, state.get(_state._LAST_ACTION_COMMENT_ID))
    )
    # Nothing to decide, and a batch that is not this road's to decide about.
    # The measurement park's own road would re-measure on one of these, and
    # this read comes after it handed the tick back -- so a command landing
    # between the two is in this batch and in nobody else's. Classified here
    # it is a continue on a park needing real guidance: refused, and consumed
    # past the refusal, so the operator's retry is gone and the reading they
    # asked for is one nothing will ever take.
    if not comments or _late_parks._reserved_for_the_measurement_park(
        comments, state,
    ):
        return None
    action = _messages._continue_command_action(comments, park_reason)
    if action == "passthrough":
        return None
    return _ParkedContinueDecision(action, comments)
