# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The order a park's claimants are asked, and the resume none of them wanted.

The auto-rebase reasons are checked first and answered with silence, because
the comment on such a park is a "retry the rebase" signal addressed to the
per-tick refresh loop. Resuming the dev or re-spawning the reviewer here would
consume that comment as input neither has any context for, and the retry
intent would vanish without a trace.

After that the three park-reason decisions are asked in order and the first
one that claims the reply wins. Only when none does is this a plain
awaiting-human resume, and a bare `/orchestrator continue` against a park that
needs real words is refused there rather than spent on the dev.

The resume itself is implementing's mechanic with one difference: a clean
pushed fix bumps the round and emits no relabel, so the issue stays on
`validating` and the reviewer re-reads the new head next tick. Docs wait for
the final-docs hop after approval. It always answers `"return"` -- every path
through it has fully handled the tick -- while the decisions above may answer
`"spawn_reviewer"` and send the caller on to the round-cap check.

Everything on this road reads the context's one frozen batch, and the reply is
recorded as consumed by the run that read it rather than ahead of it, so a live
pause or an interruption leaves the thread exactly as it found it.

A park standing over an unanswered requirements edit is the one claim that
changes what the resume's answer MEANS: a report this issue owes, or a drift
resume that ended in a question or a failure without answering the edit at
all. Either way the reply is read the way a drift resume's is -- a report with
no commit publishes onto the head the pull request carries instead of parking
as a question, and a commit is held to the report contract before the gate
sees it -- and it is stamped with the revision the batch delivered. A
publication it lands spends the next review round, exactly as any other fix
reaching the pull request does.

The claim is read BEFORE the run, because the resume clears the park it was
written beside: read afterwards, the road would lose exactly the parks it is
for.
"""
from __future__ import annotations

from orchestrator.git.base_sync import state as _base_sync_state
from orchestrator.workflow.engine import (
    messages as _messages,
    report_delivery as _report_delivery,
    report_records as _records,
    usage as _usage,
)
from orchestrator.workflow.stages.validating import (
    awaiting as _awaiting,
    dev_fix as _dev_fix,
    drift_outcomes as _outcomes,
    models as _models,
    report_settlement as _report_settlement,
    rounds as _rounds,
    state as _state,
)
from orchestrator.workflow.state import WorkflowLabel


def _resume_validating_awaiting_dev(context: _models._AwaitingValidation) -> str:
    continue_action = (
        _messages._continue_command_action(context.comments, context.park_reason)
        if context.comments else "passthrough"
    )
    if continue_action == "refuse":
        _messages._refuse_parked_continue(
            context.gh, context.issue, context.state, context.comments,
        )
        context.gh.write_pinned_state(context.issue, context.state)
        return _state._OUTCOME_RETURN
    drifting = bool(context.state.get(_state._OPEN_DRIFT))
    attempt = _awaiting._run_awaiting_dev(context, continue_action)
    if _stops_after_the_run(context, attempt):
        return _state._OUTCOME_RETURN
    if drifting or _report_delivery.owes_a_report(context.state):
        return _answers_the_drift_park(
            context, attempt, _rounds._spends_next_round(context.state),
        )
    # Frozen before the push: the gate closes it beside its own receipt, and
    # the line below re-applies the same pair rather than re-reading a counter
    # that write may already have moved.
    owed = _rounds._spends_next_round(context.state)
    pushed = _dev_fix._handle_dev_fix_result(
        context.gh,
        context.spec,
        context.issue,
        context.state,
        attempt.run.worktree,
        attempt.run.agent_result,
        attempt.run.before_sha,
        spends=owed,
    )
    if not pushed:
        if not attempt.run.agent_result.interrupted:
            context.gh.write_pinned_state(context.issue, context.state)
        return _state._OUTCOME_RETURN
    _rounds._bump_review_round(context.state, owed)
    context.gh.write_pinned_state(context.issue, context.state)
    return _state._OUTCOME_RETURN


def _stops_after_the_run(
    context: _models._AwaitingValidation,
    attempt: _models._AwaitingDevAttempt | None,
) -> bool:
    """Whether the tick is over before the run's result may be read at all.

    A resume nothing ran, and one a live pause stopped before it persisted
    the session id: the caller returns without posting, pushing, or writing.
    """
    if attempt is None:
        return True
    context.state.set("last_agent_action_at", _usage._now_iso())
    return attempt.paused


def _answers_the_drift_park(
    context: _models._AwaitingValidation,
    attempt: _models._AwaitingDevAttempt,
    owed,
) -> str:
    """Read a resume answering a park over an edit nothing has answered yet.

    Two parks reach it. One this stage took over a report it owes, which
    asked for a report in so many words. And one a drift resume ended on
    without answering the edit -- a question, a timeout, a tree nobody could
    publish -- where what is owed is the whole outcome, report included.

    Either way the reply is read the way the drift resume's is rather than as
    a plain fix: a report with no commit is an answer and publishes onto the
    head the pull request already carries, while a commit is held to the
    report contract before the gate sees it. `ACK:` and a question keep their
    own roads, and the park they leave holds the review again.

    The revision the run was handed is the one this batch delivers, which its
    own settlement records as the baseline -- so the report is stamped with
    the content that produced it rather than with a hash the reply has already
    moved past.

    A publication this reply lands is a head no reviewer has read, so it
    spends the next round like any other fix that reaches the pull request.
    """
    outcome = _outcomes._post_user_content_change_result(
        context.gh,
        context.spec,
        context.issue,
        context.state,
        attempt.run.worktree,
        attempt.run.agent_result,
        attempt.run.before_sha,
        spends=owed,
        handed=_records.HandedRun(
            WorkflowLabel.VALIDATING,
            context.batch.delivery.requirements_revision,
        ),
    )
    if attempt.run.agent_result.interrupted:
        return _state._OUTCOME_RETURN
    if outcome == _state._OUTCOME_PUSHED:
        _rounds._bump_review_round(context.state, owed)
    context.gh.write_pinned_state(context.issue, context.state)
    if outcome in _state._REPORTING_OUTCOMES:
        _report_settlement._settles_the_report(
            context.gh, context.spec, context.issue, context.state,
            WorkflowLabel.VALIDATING,
        )
    return _state._OUTCOME_RETURN


def _handle_validating_awaiting_human(context: _models._AwaitingValidation) -> str:
    """Route an awaiting-human `validating` tick after a park.

    A human replied (or a transient condition self-resolved) while the issue
    was parked. Resume the developer with their feedback -- identical mechanic
    to implementing's resume, but on a clean pushed fix we bump the round while
    staying on `validating` (no relabel emitted) so the reviewer re-evaluates
    the new head next tick. Docs are deferred to the final-docs handoff after
    reviewer approval.

    Returns ``"return"`` when the tick is fully handled (caller must return) or
    ``"spawn_reviewer"`` when the park cleared into a reviewer re-run (review-cap
    reset, reviewer timeout / silent crash) and the caller should fall through
    to the round-cap check and reviewer spawn.

    `context` is the handler's, built before its drift check, so the check and
    every road here read the same frozen reply batch.
    """

    # Transient-park recovery: when the original park reason is something
    # that can resolve without a human comment (a push race that the
    # next --force-with-lease push will land, or an agent timeout that
    # the next tick can simply rerun past), re-attempt silently. This
    # mirrors the in_review recovery branch -- without it, the issue
    # would sit forever, because `_resume_developer_on_human_reply`
    # only fires on new issue-thread comments and the human action
    # that unstuck the underlying condition typically does not include
    # one.
    # The refresh-time `_AUTO_REBASE_PARK_REASONS` parks belong to
    # the `_sync_pr_worktree_to_base` retry loop -- the operator's
    # new comment is the "retry the rebase" signal, NOT a dev /
    # reviewer trigger for this stage. Stay silent so the refresh
    # keeps ownership of the comment; resuming the dev or
    # respawning the reviewer here would consume the comment as
    # input it has no context for and silently drop the retry
    # intent.
    if context.park_reason in _base_sync_state._AUTO_REBASE_PARK_REASONS:
        return _state._OUTCOME_RETURN
    # `/orchestrator add-review-rounds N` operator command. Only honored
    # on a `review_cap` park: the cap has consumed every review round and
    # plain resuming the dev would re-park on the same cap next tick (the
    # original bug -- the round bump in the resume branch just trips
    # `round_n >= MAX_REVIEW_ROUNDS` again). On other parks the human's
    # reply IS the input the dev / reviewer needs, so we don't intercept
    # it. On a non-command reply while parked on the cap we stay parked
    # silently rather than waking the dev on a do-nothing prompt.
    for decision_helper in (
        _awaiting._review_cap_awaiting_action,
        _awaiting._transient_awaiting_action,
        _awaiting._reviewer_retry_awaiting_action,
    ):
        action = decision_helper(context)
        if action is not None:
            return action
    return _resume_validating_awaiting_dev(context)
