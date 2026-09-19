# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A body edit that lands after the PR is already open.

The dev session is still the one that wrote the branch, so the edit resumes it
rather than re-deciding the work. What makes this route different from the
same edit during implementing is where it ends: a pushed fix, a no-commit
`ACK:`, and a report with no commit all hand the issue back to `validating`
with `review_round` reset, because the approval that carried it to `in_review`
was earned against requirements that no longer exist. Docs deliberately do not
run on the way out -- the single docs pass belongs to the final-docs handoff
after a fresh reviewer approval.

The session's report is handled as the validating drift handles it -- recorded
before the push, stamped with the hash the drift check took here -- and bound
only once the relabel is behind it. The fresh round the stale approval earns,
and the marker saying this issue owes that move at all, are persisted BEFORE
the relabel: a label that moves and a write that is then lost cannot hand the
reviewer the budget the old approval was under, and a relabel that does not
land is remade on the next tick even where the outcome recorded no report. A pushed head has already outrun the
approval, so the issue goes back to `validating` without waiting for the
report, and it is there that the reviewer is held until the report is
confirmed. A report this stage still finds owed on a later tick -- a failed
push, a held candidate an adjudication published, a process that died in
between -- sends the issue back there too, ahead of everything else here.

The PR conversation is read BEFORE the notice and the ratchet, and that
ordering is the whole reason `_drift_unread_pr_conv` exists: the resume quotes
the issue thread in full and marks it read to the tip, so a PR comment nobody
has answered would sit under the mark that hop leaves behind. Capturing those
comments up front, quoting them into the same prompt, and handing their ids to
the ratchet as delivered is what keeps one from vanishing unanswered.

Both refusals sit between the finished run and the disposition rather than
before the run, because the run itself is what makes them decidable: a
shutdown-interrupted result and a live pause both bail WITHOUT writing pinned
state, so the refreshed hash, the consumed comments, and the cleared park are
all discarded and the next process re-detects the same edit.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.git.verification import probes as _verification_probes
from orchestrator.git.worktrees import creation as _worktree_creation, naming as _naming, paths as _worktree_paths
from orchestrator.github.comments import filter_trusted
from orchestrator.workflow.engine import (
    comments as _comments,
    drift as _engine_drift,
    guards as _guards,
    prompt_context as _prompt_context,
    report_delivery as _report_delivery,
    report_records as _records,
    usage as _usage,
)
from orchestrator.workflow.stages.implementing import resume as _dev_resume
from orchestrator.workflow.stages.in_review import (
    feedback as _feedback,
    models as _models,
    state as _state,
    surfaces as _surfaces,
    watermarks as _watermarks,
)
from orchestrator.workflow.stages.validating import (
    drift_outcomes as _drift_outcomes,
    report_settlement as _report_settlement,
    state as _validating_state,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

# The outcomes that take the issue back to review: new work on the pull
# request, an acknowledgement that the existing work covers the edit, and a
# report of that same head written against the new requirements. Each leaves
# an approval earned against the old requirements, so each re-reviews.
_BACK_TO_REVIEW = frozenset((
    _validating_state._OUTCOME_PUSHED,
    "ack",
    _validating_state._OUTCOME_REPORTED,
))


def _build_drift_resume_prompt(issue: Issue, unread_pr_conv: list) -> str:
    """Assemble the dev-resume prompt for a user-content drift: the recent
    issue-thread conversation combined with any unread PR-conversation
    comments so the dev sees both surfaces before the watermark bump consumes
    them.
    """
    comments_text = _prompt_context._recent_comments_text(issue)
    if unread_pr_conv:
        pr_block = "\n\n".join(
            _prompt_context._quote_comment_line(comment, label=" (PR comment)")
            for comment in unread_pr_conv
        )
        prefix = f"{comments_text}\n\n" if comments_text else ""
        comments_text = (
            f"{prefix}Unread PR conversation comments:\n\n{pr_block}"
        )
    return _engine_drift._build_user_content_change_prompt(issue, comments_text)


def _drift_unread_pr_conv(ctx: _models._InReviewContext) -> list:
    """Capture unread PR-conversation comments BEFORE the drift notice and the
    later watermark bump.

    The issue thread and PR conversation share the IssueComment id space, and
    the drift resume marks the thread read to its tip -- so a PR-conversation
    comment numbered below that tip would be under the issue thread's delivery
    cursor without any prompt having carried it. Capturing those comments here,
    quoting them in the followup, and handing the same list to the ratchet as
    delivered is what stops one from being silently dropped. The read is the
    surface's own (`_unread_pr_conversation`), so the issue-thread cursor cannot
    bound it; orchestrator id / marker filtering mirrors the regular in_review
    comment scan.
    """
    orchestrator_ids = _comments._orchestrator_ids(ctx.state)
    return _feedback._drop_orchestrator_comments(
        _surfaces._unread_pr_conversation(ctx.gh, ctx.pr, ctx.state),
        orchestrator_ids,
    )


def _resume_dev_for_drift(
    ctx: _models._InReviewContext, unread_pr_conv: list, new_hash: str,
) -> _models._DriftResume:
    """Notify both surfaces, mark the issue-thread drift comments consumed,
    resolve the worktree, and resume the locked dev session with the updated
    body plus the unread PR conversation. Captures the pre-resume HEAD so the
    disposition can tell a pushed fix from a no-commit ack.

    The dev sees the full issue thread via `_recent_comments_text` in the resume
    prompt, so marking the issue-thread comments consumed here keeps both a
    later validating->in_review handoff and the in_review watermark check from
    replaying them as fresh feedback. Untrusted authors are filtered out of the
    quoted PR-conversation block; the watermark bump still consumes the raw
    `unread_pr_conv` so an outsider comment is not re-scanned next tick.
    """
    _comments._post_pr_comment(
        ctx.gh, int(ctx.pr_number), ctx.state,
        ":pencil2: issue body changed; resuming dev session.",
    )
    _engine_drift._mark_drift_comments_consumed(ctx.gh, ctx.issue, ctx.state)
    # The checkout this resume runs in, recreated on the resolved branch
    # where the path is gone.
    wt = _worktree_paths._worktree_path(ctx.spec, ctx.issue.number)
    if not wt.exists():
        wt = _worktree_creation._ensure_worktree(
            ctx.spec, ctx.issue.number,
            branch=_naming._resolve_branch_name(
                ctx.state, ctx.spec, ctx.issue.number,
            ),
        )
    before_sha = _verification_probes._head_sha(wt)
    wt, dev_result, paused = _dev_resume._resume_dev_with_text(
        ctx.gh, ctx.spec, ctx.issue, ctx.state,
        _build_drift_resume_prompt(ctx.issue, filter_trusted(unread_pr_conv)),
        pause_guard=True,
    )
    ctx.state.set("last_agent_action_at", _usage._now_iso())
    return _models._DriftResume(
        worktree=wt, dev_result=dev_result, paused=paused, before_sha=before_sha,
        requirements_revision=new_hash,
    )


def _dispose_drift_result(
    ctx: _models._InReviewContext,
    unread_pr_conv: list,
    resume: _models._DriftResume,
) -> None:
    """Post the dev result (a no-commit reply is an ack, not a park), ratchet
    the in_review issue-side watermark past everything consumed this tick, and
    on a pushed fix, an ack, or a report with no commit bounce DIRECTLY back to
    `validating` with `review_round` reset.

    The drift invalidated the prior validation either way: the reviewer approved
    against the OLD requirements, so `review_round` must reset before the issue
    can earn a fresh approval. Docs do not run here; the single docs pass is
    deferred to the final-docs handoff after reviewer approval. Passing
    `unread_pr_conv` to the bump is what lets its walk advance over those
    ids: they were quoted into this tick's prompt, and the walk crosses
    nothing it cannot account for, so without them it would stop at the
    first one and re-fire them as fresh feedback next tick.
    """
    outcome = _drift_outcomes._post_user_content_change_result(
        ctx.gh, ctx.spec, ctx.issue, ctx.state,
        resume.worktree, resume.dev_result, resume.before_sha,
        handed=_records.HandedRun(
            WorkflowLabel.IN_REVIEW, resume.requirements_revision,
        ),
    )
    _watermarks._bump_in_review_watermarks(ctx, issue_space_new=unread_pr_conv)
    if outcome in _BACK_TO_REVIEW:
        _relabels_for_review(ctx)
    else:
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
    # Bound only once the relabel and its write are behind it, so no tick
    # ever finds a settled report beside a label still claiming the approval
    # it made stale: a process dying before this line leaves the report owed,
    # which the next tick answers on `validating` either way.
    if outcome in _validating_state._REPORTING_OUTCOMES:
        _report_settlement._settles_the_report(
            ctx.gh, ctx.spec, ctx.issue, ctx.state, WorkflowLabel.VALIDATING,
        )


def _relabels_for_review(ctx: _models._InReviewContext) -> None:
    """Move the label to `validating`, around the writes that make it durable.

    The fresh round and the MOVE THIS ISSUE OWES both go down before the
    label is touched, because a label move and a pinned write cannot be made
    one operation and only this order is recoverable. Moved first, a write
    that then failed would leave the issue under a reviewer with the round
    count the stale approval was earned under -- one tick's budget for
    requirements nobody has reviewed at all, where the cap was nearly spent.

    Written first, nothing is lost whichever half fails. A write nobody made
    leaves the label where it was, so the same tick simply runs again. A
    relabel that does not land leaves the marker standing, and the hand-back
    below remakes the move on the next tick -- which is what an `ACK:` reply
    needs, since it records no report and there would otherwise be nothing to
    recognise the debt by: no drift left to re-detect, and a ready ping one
    tick away on an approval that is over.

    The marker comes off in a write of its own, behind the move it was about.
    Lost, it costs one spurious hand-back the next time this issue reaches
    `in_review` -- a re-review rather than a ping on a stale approval -- and
    that tick clears it.
    """
    ctx.state.set(_state._HANDOFF_PENDING, True)
    ctx.state.set("review_round", 0)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)
    ctx.gh.set_workflow_label(ctx.issue, WorkflowLabel.VALIDATING)
    ctx.state.set(_state._HANDOFF_PENDING, None)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)


def _hands_a_stale_approval_back(ctx: _models._InReviewContext) -> bool:
    """Send an issue whose approval a requirements edit made stale back to review.

    True where it did, and the caller must return. Two things say so, and
    each is what the other cannot say.

    A developer report still OWED is one: the resume that recorded it was
    answering an edit, so the approval is stale whatever became of the report
    -- a push that failed, a candidate the size gate held and an adjudication
    later published, or a process that died between the record and the
    relabel. Left here the report is never bound, since the hold that binds it
    is `validating`'s.

    A handoff MARKER is the other, and it covers the outcomes that record no
    report at all: an `ACK:` reply whose relabel did not land leaves no debt,
    no drift to re-detect, and nothing else on the comment to say the label
    still owes a move.

    Either way nothing else this stage does runs first: `validating` recovers
    a failed push, binds and settles what a publication carried, and holds the
    reviewer until the pull request carries the report. A park standing beside
    the debt moves with it, and is answered there.
    """
    if not (
        _report_delivery.owes_a_report(ctx.state)
        or ctx.state.get(_state._HANDOFF_PENDING)
    ):
        return False
    log.warning(
        "issue=#%s owes PR #%s a move to validating its approval no longer "
        "covers; handing it back rather than acting on a stale approval",
        ctx.issue.number, ctx.pr_number,
    )
    _relabels_for_review(ctx)
    return True


def _handle_user_content_drift(ctx: _models._InReviewContext) -> bool:
    """Resume the dev when a human edited the issue title / body after the PR
    opened (no fresh comment surface triggered the fixing route).

    Returns True when drift was detected and handled (the caller must return),
    False when there is no drift (the caller falls through to the mergeability
    gate).
    """
    new_hash = _engine_drift._detect_user_content_change(ctx.gh, ctx.issue, ctx.state)
    if new_hash is None:
        return False
    ctx.state.set("user_content_hash", new_hash)
    unread_pr_conv = _drift_unread_pr_conv(ctx)
    resume = _resume_dev_for_drift(ctx, unread_pr_conv, new_hash)
    # Interrupted (shutdown sweep) or live-paused (operator added `paused` /
    # `backlog` mid-run) resume: bail WITHOUT writing pinned state so everything
    # staged above -- refreshed `user_content_hash`, consumed drift comments,
    # `last_agent_action_at`, the `awaiting_human` clear inside
    # `_resume_dev_with_text` -- is discarded and the next process re-detects the
    # body change and leaves any committed work on the branch. Must precede
    # `_dispose_drift_result` so it neither parses a partial reply nor persists
    # the consumption.
    if _guards._ignore_if_interrupted(ctx.issue, resume.dev_result):
        return True
    if resume.paused:
        return True
    _dispose_drift_result(ctx, unread_pr_conv, resume)
    return True
