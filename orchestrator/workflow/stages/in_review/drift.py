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

The move to `validating` this edit owes is staged with the refreshed
requirements hash, before the resume that answers it: the hash is what stops a
later tick re-detecting the edit, and no write may make one durable without
the other. Every road out of the disposition writes durably before the relabel
is reached -- the report ahead of the size gate, the receipt a push leaves, a
park's own state -- and a process dying past one of those with the move
unrecorded would leave this label standing on an approval the edit has made
stale, with nothing left to re-detect and a ready ping one tick away.

A resume that ends PARKED -- a question, a timeout, a tree nobody could
publish -- answers the edit with nothing, so it leaves the same move owed: the
approval is stale either way, and only `validating` reads the reply as the
rest of that drift resume. The comment a human wrote while that resume was out
is still unread when it parks, and the watermark carry behind it stops below
that comment rather than at the thread's tip, so the reply the move hands on
is the one they wrote.

The session's report is handled as the validating drift handles it -- recorded
before the push, stamped with the revision the read its own prompt was built
from fingerprints to -- and bound only once the relabel is behind it. The fresh round the stale approval earns,
and the marker saying this issue owes that move at all, are persisted BEFORE
the relabel: a label that moves and a write that is then lost cannot hand the
reviewer the budget the old approval was under, and a relabel that does not
land is remade on the next tick even where the outcome recorded no report. A
pushed head has already outrun the approval, so the issue goes back to
`validating` without waiting for the report, and it is there that the reviewer
is held until the report is confirmed. A report this stage still finds owed on a later tick -- a failed
push, a held candidate an adjudication published, a process that died in
between -- sends the issue back there too, ahead of everything else here.

What the resume quotes and what the issue may mark answered come off ONE
frozen read of two surfaces, and the record of it is settled once the run is
back. The prompt carries the bounded issue excerpt and, below it, the pull
request's unread conversation -- read here rather than left to the ratchet,
because the two share an id space and a mark taken over the thread alone would
sit above a PR comment nobody has answered. What the excerpt bound cut is
recorded as delivered to nobody, so the scan that owns the surface still hands
it over, and the inline-review and review-summary watermarks are left where
they are, since nothing here reads those.

The record settles the issue thread's own cursor and the requirements
revision, and no more. The cursor the two IssueComment surfaces SHARE is the
carry's, because the record covers them at two different moments: the pull
request is read before the notice this road posts on it, the thread after --
so a comment landing on the pull request in between is in neither half, while
an issue reply above it is in one. Settled from the pair, the shared cursor
would step over that comment and no later poll could go back for it. The carry
re-reads both surfaces at one moment instead, crosses exactly what the record
names, and stops at the first id it does not.

The ratchet over what that record names is taken twice: once before the
disposition, so the first durable write the disposition makes carries it, and
once after, for the notices the disposition itself posts. A carry taken only
at the end is one a process dying mid-disposition loses, leaving a report and
a push durable over feedback still marked unread -- and that comment buys a
`fixing` round the next time the issue reaches review, for words the developer
answered in the prompt that quoted them.

All three refusals sit between the finished run and the disposition rather
than before the run, because the run itself is what makes them decidable: a
launch the run circuit turned away, a shutdown-interrupted result, and a live
pause each bail WITHOUT writing pinned state, so the refreshed hash, the
marker staged beside it, the cleared park, and every comment the prompt
carried are all left unrecorded and the next process re-detects the same edit.
Nothing read that prompt on any of the three, so nothing durable may act as
though something had -- a park taken in the name of a run that never started
included.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from orchestrator.git.verification import probes as _verification_probes
from orchestrator.git.worktrees import creation as _worktree_creation, naming as _naming, paths as _worktree_paths
from orchestrator.workflow.engine import (
    comments as _comments,
    drift as _engine_drift,
    drift_delivery as _drift_delivery,
    guards as _guards,
    prompt_delivery as _delivery,
    report_delivery as _report_delivery,
    report_records as _records,
    usage as _usage,
)
from orchestrator.workflow.stages.implementing import (
    resume as _dev_resume,
    resume_batch as _resume_batch,
)
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


def _drift_unread_pr_conv(ctx: _models._InReviewContext) -> list:
    """Capture unread PR-conversation comments BEFORE the drift notice and the
    later watermark bump.

    The issue thread and PR conversation share the IssueComment id space, and
    the resume settles the thread it quoted -- so a PR-conversation comment
    numbered below what it recorded would be under that settlement without any
    prompt having carried it. Capturing those comments here, quoting them into
    the same frozen prompt, and recording them on the surface they were written
    on is what stops one from being silently dropped. The read is the surface's
    own (`_unread_pr_conversation`), so the issue-thread cursor cannot bound
    it; orchestrator id / marker filtering mirrors the regular in_review
    comment scan.

    Taken BEFORE the notice this road posts on the same surface, so the record
    cannot name our own announcement as somebody's feedback.
    """
    orchestrator_ids = _comments._orchestrator_ids(ctx.state)
    return _feedback._drop_orchestrator_comments(
        _surfaces._unread_pr_conversation(ctx.gh, ctx.pr, ctx.state),
        orchestrator_ids,
    )


def _resume_dev_for_drift(
    ctx: _models._InReviewContext, unread_pr_conv: list,
) -> _models._DriftResume:
    """Notify the pull request, resolve the worktree, and resume the locked dev
    session with the updated body, the issue thread, and the pull request's
    unread conversation quoted from ONE frozen read.

    Captures the pre-resume HEAD so the disposition can tell a pushed fix from
    a no-commit ack, and carries the record of what that prompt quoted, which
    is what the disposition settles. The record travels with the run rather
    than being re-derived after it: the agent is out for minutes, and a mark
    taken off the thread it comes back to crosses replies nobody delivered.

    Untrusted authors reach neither half of it -- the prompt does not quote
    them and the record names them refused, which is how the carry behind it
    still crosses an outsider comment nobody is owed.
    """
    _comments._post_pr_comment(
        ctx.gh, int(ctx.pr_number), ctx.state,
        ":pencil2: issue body changed; resuming dev session.",
    )
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
    answered = _drift_delivery._pr_drift_resume_prompt(
        ctx.gh, ctx.issue, ctx.state, unread_pr_conv,
    )
    wt, dev_result, paused = _dev_resume._resume_dev_with_text(
        ctx.gh, ctx.spec, ctx.issue, ctx.state, answered.text,
        pause_guard=True,
        # The frozen conversation a rotated, retired or poisoned session's
        # respawn is re-grounded with, handed over rather than read again:
        # taken there it would be a second reading, newer than the record this
        # tick settles, carrying a comment the settlement would leave unread.
        thread_text=answered.delivery.rendered_text,
    )
    ctx.state.set("last_agent_action_at", _usage._now_iso())
    return _models._DriftResume(
        worktree=wt, dev_result=dev_result, paused=paused, before_sha=before_sha,
        delivery=answered.delivery,
    )


def _dispose_drift_result(
    ctx: _models._InReviewContext,
    resume: _models._DriftResume,
) -> None:
    """Post the dev result (a no-commit reply is an ack, not a park), record
    what the resume's prompt delivered, and on a pushed fix, an ack, or a
    report with no commit bounce DIRECTLY back to `validating` with
    `review_round` reset.

    The drift invalidated the prior validation either way: the reviewer approved
    against the OLD requirements, so `review_round` must reset before the issue
    can earn a fresh approval. Docs do not run here; the single docs pass is
    deferred to the final-docs handoff after reviewer approval.

    The frozen record is settled only where the run counts the prompt as
    delivered, and a run that read nothing hands the carry below no ids
    either: a shutdown kill, a live pause and a launch the circuit turned away
    all leave the edit and every comment under it exactly as unanswered as
    they were.
    """
    consumed = _settles_what_it_delivered(ctx, resume)
    # Carried TWICE, because the disposition below writes durably -- the
    # report ahead of the size gate, the receipt the push leaves, a park's own
    # state -- and a process that died past one of those writes with the carry
    # still to come would leave the pull request holding work whose feedback
    # is marked unread. The next time this issue reached review, that comment
    # would buy a `fixing` round for words the developer has already answered.
    # This pass crosses what the prompt delivered; the one below crosses the
    # notices the disposition posts, which do not exist yet. Both stop at the
    # first comment nothing vouches for, so the early one can only ever cross
    # less.
    _watermarks._bump_in_review_watermarks(ctx, delivered=consumed)
    outcome = _drift_outcomes._post_user_content_change_result(
        ctx.gh, ctx.spec, ctx.issue, ctx.state,
        resume.worktree, resume.dev_result, resume.before_sha,
        handed=_records.HandedRun(
            WorkflowLabel.IN_REVIEW, resume.requirements_revision,
        ),
    )
    _watermarks._bump_in_review_watermarks(ctx, delivered=consumed)
    if outcome in _BACK_TO_REVIEW:
        _relabels_for_review(ctx)
    else:
        # The edit is unanswered and the approval is stale whatever stopped
        # this resume, so the move to `validating` is owed from here. The
        # marker saying so went down with the hash; this is the write that
        # makes it durable where nothing the disposition did already has.
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
    # Bound only once the relabel and its write are behind it, so no tick
    # ever finds a settled report beside a label still claiming the approval
    # it made stale: a process dying before this line leaves the report owed,
    # which the next tick answers on `validating` either way.
    if outcome in _validating_state._REPORTING_OUTCOMES:
        _report_settlement._settles_the_report(
            ctx.gh, ctx.spec, ctx.issue, ctx.state, WorkflowLabel.VALIDATING,
        )


def _settles_what_it_delivered(
    ctx: _models._InReviewContext, resume: _models._DriftResume,
) -> _delivery.PromptDeliverySnapshot | None:
    """Record the frozen prompt as read, and say whether it may be.

    The issue thread's own delivery cursor and the requirements revision are
    what this road writes; the inline-review and review-summary watermarks are
    untouched because nothing here read them. What the excerpt bound cut holds
    the thread's cursor below it, so the scan that owns that surface still
    delivers it.

    Only the issue thread's half of the record is written from, because
    `pr_last_comment_id` spans BOTH IssueComment surfaces and this record
    covers them at two different moments -- the pull request's conversation is
    read before the resume's notice, the issue thread after it. A comment
    landing on the pull request in between is in neither half, and an issue
    reply numbered above it IS: settled together, the shared cursor would step
    over a comment nobody has read and no later poll could go back for it. So
    that cursor is left to `watermarks._bump_in_review_watermarks`, which
    re-reads both surfaces at one moment, crosses exactly what this record
    names, and stops at the first id it does not. Nothing is lost by the
    split: the pull-request comments this prompt delivered are named in the
    record that walk is handed, so it carries the cursor over them as readily
    as a settlement would.

    None is a run that never read the prompt through, and it is what the carry
    behind this is handed too: a walk crossing ids a delivery nobody received
    named would skip them for good. The caller returns ahead of every such
    outcome, so what the predicate states here is the contract rather than the
    last line of defence -- the record is settled by what the RUN came to, not
    by which guards a road happens to ask first.
    """
    if not _resume_batch._counts_as_delivered(resume.dev_result, resume.paused):
        return None
    replace(
        resume.delivery,
        entries=resume.delivery.surface_provenance(
            _delivery.SURFACE_ISSUE_THREAD,
        ),
    ).settle(ctx.state)
    return resume.delivery


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

    A publication this issue still OWES when the move is made is recorded as
    belonging to the budget this reset just gave it -- a report it has not
    settled, or an edit its resume never answered at all. That publication
    answers the same edit the reset is for, so the road that finally lands it
    on `validating` -- where a fix reaching the pull request spends a round --
    must not spend from the budget the edit earned: the delayed road would
    otherwise leave the next reviewer one round short of what the road where
    the same push landed at once leaves it. It is dropped by the settlement
    that ends the debt, or by the outcome that answers the edit with nothing
    left to settle.
    """
    _state.stages_the_handoff(ctx.state, owed_publication=(
        _report_delivery.owes_a_report(ctx.state)
        or bool(ctx.state.get(_validating_state._OPEN_DRIFT))
    ))
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)
    ctx.gh.set_workflow_label(ctx.issue, WorkflowLabel.VALIDATING)
    ctx.state.set(_state._HANDOFF_PENDING, None)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)


def _hands_a_stale_approval_back(ctx: _models._InReviewContext) -> bool:
    """Send an issue whose approval no longer covers its work back to review.

    True where it did, and the caller must return. Three things say so, and
    each is what the others cannot say.

    A developer report still OWED is one: the resume that recorded it was
    answering an edit, so the approval is stale whatever became of the report
    -- a push that failed, a candidate the size gate held and an adjudication
    later published, or a process that died between the record and the
    relabel. Left here the report is never bound, since the hold that binds it
    is `validating`'s.

    A handoff MARKER is the other, and it covers every outcome that records no
    report at all. An `ACK:` reply whose relabel did not land leaves no debt,
    no drift to re-detect, and nothing else on the comment to say the label
    still owes a move. A resume that PARKED leaves the same silence and an
    edit nobody has answered besides: its reply belongs to `validating`, where
    the drift road reads it and the report it writes is published, so the
    marker goes down with the park and the move is made ahead of the feedback
    scan that would otherwise route that reply to `fixing`.

    An approval recorded against another developer report than the one the
    issue now records as current is the third. The head can be the very one
    that approval, its docs pass, and its ready ping were about, so nothing
    keyed on the commit notices -- and a report nobody reviewed would be
    advertised as ready to merge.

    Either way nothing else this stage does runs first: `validating` recovers
    a failed push, binds and settles what a publication carried, and holds the
    reviewer until the pull request carries the report. A park standing beside
    the debt moves with it, and is answered there.
    """
    if not _state.owes_validating_a_move(ctx.state):
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
    # Staged beside the hash, because the two may never become durable apart.
    # Every write the disposition below makes persists the whole comment, the
    # refreshed hash included, and from the moment that hash lands no later
    # tick re-detects this edit -- so the issue has to already carry something
    # saying the move is owed. A report a run recorded, or the debt of work it
    # withheld, says it on the roads that leave one; an `ACK:` and a park with
    # no report at all leave none, and the marker is what says it for them.
    # Written together, a process dying anywhere past the first durable write
    # leaves an issue that knows it owes `validating` a move; dying before it
    # leaves an issue that simply re-detects the edit. The settlement below
    # refines the hash to the revision the prompt actually fingerprinted,
    # which is a reply newer at most -- never older.
    ctx.state.set(_state._HANDOFF_PENDING, True)
    resume = _resume_dev_for_drift(ctx, _drift_unread_pr_conv(ctx))
    # Refused (the run circuit turned the launch away), interrupted (shutdown
    # sweep) or live-paused (operator added `paused` / `backlog` mid-run)
    # resume: bail WITHOUT writing pinned state so everything staged above --
    # refreshed `user_content_hash`, the handoff marker, `last_agent_action_at`,
    # the `awaiting_human` clear inside `_resume_dev_with_text` -- is discarded
    # and the next process re-detects the body change and leaves any committed
    # work on the branch. The hash and the marker are staged TOGETHER for
    # exactly this reason: neither becomes durable here, so the pair stays
    # consistent and the edit is re-detectable rather than absorbed by a
    # prompt nothing read. All three must precede `_dispose_drift_result` so it
    # neither parses a reply no process wrote nor parks in the name of a run
    # that never started -- the refusal the circuit recorded where it was
    # decided is the whole of what this tick says.
    if _guards._ignore_if_never_invoked(ctx.issue, resume.dev_result):
        return True
    if _guards._ignore_if_interrupted(ctx.issue, resume.dev_result):
        return True
    if resume.paused:
        return True
    _dispose_drift_result(ctx, resume)
    return True
