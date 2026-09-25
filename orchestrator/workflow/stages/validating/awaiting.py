# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a park is waiting for, and who the reply belongs to.

An awaiting-human `validating` issue is not one state but several, and the
`park_reason` is what says which. Each decision here answers for exactly one
of them and returns None otherwise, so the caller can ask them in order and
fall through to the plain dev resume only when none of them claims the reply.

`review_cap` is the reason a plain resume cannot serve: every round is spent,
so waking the dev would bump the round straight back into the cap next tick.
Only `/orchestrator add-review-rounds N` gets past it, and a reply that is not
that command leaves the issue parked silently rather than spending an agent
run on a do-nothing prompt. The parse walks newest-first so a corrected
command supersedes a stale one in the same batch, and an invalid argument is
answered on the issue instead of guessed at.

The cap's command is recorded as READ when this road answers it, and only
where the comment IS the command and nothing else. Nothing else in the batch
is -- not the requirements those words arrived beside, and not the guidance
written beside them, which reached no agent either. A command written INSIDE
a comment of guidance is that guidance, so the whole comment stays unread and
the round the grant buys is what delivers and records it, under its own
excerpt.

That leaves the mark below words nobody carried, so the command outlives the
cap it answered and the batch a later cap freezes carries it again. What says
a grant was honored is the record written beside the round reset it bought,
which is durable exactly where that reset is: the notice goes out before the
reviewer runs, and a launch the run circuit refuses discards the reset and
keeps the sentence, leaving a command an agent-run grant still has to hand
back. The invalid-argument refusal is the other shape and answers to its own
post instead, since its write follows that post rather than a run.

A reviewer-side park's retry records nothing at all. Clearing that park is an
action on the words, not a delivery of them, and the round it buys is what
carries them -- bounded by its own excerpt, which is not this batch's. So the
round records what it read (`reviewer.py`), a reply its excerpt cut short
stays unread for the scan that owns the issue thread, and a round nothing ran
-- the circuit's refusal, the report hold -- leaves the reply exactly where it
found it.

What both roads DO write down is the round the reply bought, because the
clear can go out on a tick that runs no round: the reply has moved the
requirements by then, and a later tick reading the park alone would find a
plain edit and resume the developer ahead of the reviewer those words asked
for. The note says which reply is owed a round, so the round that finally
runs is the reviewer's and the settlement is that round's own.

The transient reasons are the opposite shape: they fire only when NO comment
arrived, because they exist for conditions that resolve on their own and the
retry has to stay silent while it is still failing. Succeeding is the one thing
worth saying: the park mentioned a human, so the clear posts a follow-up
retiring that mention rather than leaving it as the thread's last word. A
reviewer timeout or crash with a reply is the third: the failure left no review
output for the dev to act on, so the comment buys a fresh REVIEWER rather than
a dev resume. A transient retry that resolves also answers the publication a
requirements edit was owed, where one was: the fresh review budget an
`in_review` hand-back recorded is about exactly the publication this retry
lands -- or finds there was none to land -- so the record of it goes down with
the park rather than outliving it.

`_run_awaiting_dev` is the fall-through the router uses when none of those
match. It reads HEAD before the resume because that is the only watermark that
can tell a commit this run produced from one already on the branch, and it
splits `retry` from a plain reply -- a retry re-issues the orchestrator's own
continue prompt and consumes the comment outright, since what the operator
bought is the prompt rather than a delivery of their words, while a reply
hands the human's words to the dev and is consumed only once the run that read
them is back.

Both halves resume from the context's OWN frozen batch rather than reading the
thread again, since the decisions above were made from it -- and a retry whose
session is missing or retired is re-grounded off that batch's conversation less
the commands it consumes.
"""
from __future__ import annotations

from pathlib import Path

from orchestrator import config
from orchestrator.agents.models import AgentResult
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.git.worktrees import creation as _worktree_creation, naming as _naming, paths as _worktree_paths
from orchestrator.workflow.engine import (
    comments as _comments,
    messages as _messages,
    prompt_notes as _prompt_notes,
    report_delivery as _report_delivery,
)
from orchestrator.workflow.stages.implementing import resume as _dev_resume
from orchestrator.workflow.stages.validating import models as _models, recovery as _recovery, state as _state


def _cap_command_to_answer(
    context: _models._AwaitingValidation,
) -> _state._ReviewRoundsCommand | None:
    """The `/orchestrator add-review-rounds N` command this tick has to answer.

    Returns ``(comment, n, None)`` for a valid positive `N`; ``(comment, n,
    reason)`` when the latest match has an invalid argument (caller posts
    `reason` and stays parked); ``None`` when there is nothing here to act
    on. Walks newest-first so a corrected command supersedes a stale one
    posted earlier in the same batch, and an empty batch comes back None like
    any other batch carrying no command -- a park nobody answered and a reply
    that is not the command leave this road sitting exactly alike, since the
    round a plain reply would spend is the one the cap already refused.

    A grant already WRITTEN DOWN comes back None too. Its command may have
    been left uncrossed -- a bounded round records only what its own excerpt
    carried -- so the batch a LATER cap freezes reaches back below it and
    offers the same words again, and honored twice they reset that cap for
    free and go on doing it. The record staged beside the round reset is what
    says one was honored, and it went down or did not with that reset: a
    launch the run circuit refuses discards both, leaving the command an
    agent-run grant hands back to be honored for real. A command posted after
    the record carries an id of its own and is new.

    The comment itself comes back because the road records exactly the words
    it answers: which comment carried them is the whole of what a settlement
    may cross, and whether it carried anything ELSE is what says it may be
    crossed at all (`_is_bare_command`).
    """
    granted_on = context.state.get(_state._CAP_GRANTED_ON)
    for comment in reversed(context.comments):
        body = comment.body or ""
        command_match = _state._ADD_REVIEW_ROUNDS_RE.search(body)
        if not command_match:
            continue
        if comment.id == granted_on:
            return None
        additional_rounds = int(command_match.group(1))
        if additional_rounds <= 0:
            return (
                comment,
                additional_rounds,
                f"expected a positive integer (got `{additional_rounds}`)",
            )
        return (comment, additional_rounds, None)
    return None


def _is_bare_command(issue_comment) -> bool:
    """Whether this comment is the cap command and nothing else.

    Only a bare one may be recorded as read when this road answers it. The
    answer is posted the moment the command is parsed, so the command must
    not come back on every poll -- and a comment that IS the command has
    nothing else in it for the mark to cross.

    Written ALONGSIDE guidance it is guidance too, held to the test
    `/orchestrator continue` and `/orchestrator add-agent-runs` are held to
    for the same reason. Those words reached no agent: this park hands its
    batch to nobody, and the round a grant buys quotes the thread under its
    OWN excerpt, which may cut a long comment short. Crossing the whole
    comment here would spend a head no prompt has carried, and a refused
    launch would leave it spent with no reviewer having run at all. So the
    comment stays unread and the round that finally runs is what delivers
    and records it.
    """
    written = (getattr(issue_comment, "body", "") or "").strip()
    return _state._ADD_REVIEW_ROUNDS_RE.fullmatch(written) is not None


def _review_cap_awaiting_action(
    context: _models._AwaitingValidation,
) -> str | None:
    if context.park_reason != _state._REASON_REVIEW_CAP:
        return None
    command = _cap_command_to_answer(context)
    if command is None:
        return _state._OUTCOME_RETURN
    answered, additional_rounds, error = command
    if _is_bare_command(answered):
        context.consume_command(answered)
    if error is not None:
        # Said once. This road's own write follows the post, so the post is
        # the record: where guidance nobody delivered stands below the
        # command -- or inside the very comment carrying it -- the mark stays
        # below both and the batch comes back identical on every poll.
        if not context.already_answered(answered):
            _comments._post_issue_comment(
                context.gh,
                context.issue,
                context.state,
                f":warning: `/orchestrator add-review-rounds` ignored: {error}.",
            )
        context.gh.write_pinned_state(context.issue, context.state)
        return _state._OUTCOME_RETURN
    new_round = max(0, config.MAX_REVIEW_ROUNDS - additional_rounds)
    context.state.set(_state._REVIEW_ROUND, new_round)
    context.state.set(_state._CAP_GRANTED_ON, answered.id)
    # The grant is a control, and a batch carrying nothing else asks the
    # developer for nothing; any other words beside it are requirements.
    context.bought_a_round(carries_requirements=not (
        _is_bare_command(answered)
        and all(seen.id == answered.id for seen in context.comments)
    ))
    context.clear_park()
    _comments._post_issue_comment(
        context.gh,
        context.issue,
        context.state,
        f":arrows_counterclockwise: review-cap reset: granting "
        f"{additional_rounds} more round(s) "
        f"(`review_round`={new_round}/{config.MAX_REVIEW_ROUNDS}); "
        "rerunning reviewer.",
    )
    return "spawn_reviewer"


def _transient_awaiting_action(
    context: _models._AwaitingValidation,
) -> str | None:
    if (
        context.comments
        or context.park_reason not in _state._VALIDATING_TRANSIENT_PARK_REASONS
    ):
        return None
    recovery = _recovery._try_recover_validating_transient_park(
        context.gh, context.spec, context.issue, context.state,
    )
    # Every outcome that healed nothing owes the thread nothing: the size gate
    # took the candidate and has already parked the issue or moved it to the
    # adjudication, or the reading of the branch withheld the clear. Announced
    # here, a recovery that did not happen would be claimed, and the state the
    # gate just wrote stepped on.
    if recovery not in _state._RECOVERY_HOLDS_THE_PARK:
        followup = _recovery._recovery_followup_comment(
            context.gh,
            context.issue,
            context.state,
            context.park_reason,
            recovery,
        )
        if followup is not None:
            _comments._post_issue_comment(
                context.gh, context.issue, context.state, followup,
            )
        context.clear_park()
        # The retry answered the publication a hand-back reset the budget
        # for: it pushed it, or read the branch and found nothing to push.
        # Either way that budget is spent by the reviewer this clear releases,
        # and a record left standing would spend nothing for the next
        # unrelated publication this stage owes.
        if context.state.get(_report_delivery.OWED_ROUND_RESET):
            context.state.set(_report_delivery.OWED_ROUND_RESET, None)
        context.gh.write_pinned_state(context.issue, context.state)
    return _state._OUTCOME_RETURN


def _reviewer_retry_awaiting_action(
    context: _models._AwaitingValidation,
) -> str | None:
    if not context.comments or context.park_reason not in (
        _state._REASON_REVIEWER_TIMEOUT, _state._REASON_REVIEWER_FAILED,
    ):
        return None
    # A reviewer-side park retries itself with nobody replying, so a reply to
    # one says something -- short of a bare `/orchestrator continue`.
    context.bought_a_round(carries_requirements=not all(
        _messages._is_bare_orchestrator_continue(seen) for seen in context.comments
    ))
    context.clear_park()
    return "spawn_reviewer"


def _resume_awaiting_dev_agent(
    context: _models._AwaitingValidation, continue_action: str,
) -> tuple[Path, AgentResult, bool] | None:
    if continue_action != "retry":
        return _dev_resume._resume_developer_on_human_reply(
            context.gh,
            context.spec,
            context.issue,
            context.batch,
            pause_guard=True,
        )
    context.consume_comments()
    return _dev_resume._resume_dev_with_text(
        context.gh,
        context.spec,
        context.issue,
        context.state,
        _prompt_notes._DEVELOPER_CONTINUE_RETRY_PROMPT,
        pause_guard=True,
        thread_text=context.batch.retry_thread_text,
    )


def _run_awaiting_dev(
    context: _models._AwaitingValidation, continue_action: str,
) -> _models._AwaitingDevAttempt | None:
    worktree = _worktree_paths._worktree_path(context.spec, context.issue.number)
    if not worktree.exists():
        worktree = _worktree_creation._ensure_worktree(
            context.spec,
            context.issue.number,
            branch=_naming._resolve_branch_name(
                context.state, context.spec, context.issue.number,
            ),
        )
    before_sha = _verification_probes._head_sha(worktree)
    resumed = _resume_awaiting_dev_agent(context, continue_action)
    if resumed is None:
        return None
    return _models._AwaitingDevAttempt(
        _models._DevFixRun(resumed[0], resumed[1], before_sha), resumed[2],
    )
