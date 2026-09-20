# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""`/orchestrator continue` on a parked fix, and the batch it must not lose.

The command means "retry this fix", and the park it usually answers is a dev
session that went silent or timed out with the PR feedback still unaddressed.
Resuming on the command text alone is the failure this owner exists to prevent:
the session that failed is dropped, a fresh one is grounded on the preserved
batch, and anything the operator wrote beside the command rides along verbatim.
The command line itself does not: what a replay is handed is rendered to the
dev as PR feedback to act on, and the one thing this retry must not tell it to
implement is the word "continue". Nothing is lost by dropping it, because what
the resume settles is the replayed batch JOINED with the whole fresh rescan,
so the command is consumed like any other delivered comment.

The batch is rebuilt per surface for that settlement's sake. A replay reaches
a developer, so it is delivered, so each half of it answers to the reader that
owns it -- and a flattened batch could not say that its issue-thread half
moves `last_action_comment_id` while its PR-conversation half never may. A
pre-upgrade park is where that shows: the round before the settlement existed
left the issue-action boundary behind, the replay is the tick that quotes the
reply again, and a relabel out of `fixing` after it would otherwise pay a
second developer to deliver the very comment this retry just answered.

Not every park may be retried. A park still waiting on a real human answer (an
agent question, a worktree it could not finish) is refused rather than
resumed, and so is a retryable park with nothing left to replay. Both refusals
consume the command comment so the answer is posted once instead of every tick.
The third answer is no answer at all: a command that arrived WITH genuine
guidance on an unreplayable park falls through untouched, so that guidance
drives the dev instead of a generic continue.
"""
from __future__ import annotations

import logging

from orchestrator import config
from orchestrator.github.comments import filter_trusted
from orchestrator.workflow.engine import comments as _comments, messages as _messages
from orchestrator.workflow.stages.fixing import (
    bookmarks as _bookmarks,
    feedback as _feedback,
    models as _models,
    state as _state,
)
from orchestrator.workflow.stages.implementing import session as _dev_session

log = logging.getLogger("orchestrator.workflow")


def _reconstruct_pending_fix_batch(
    gh, issue, pr, state,
) -> _models._FixingFeedback:
    """Rebuild the exact feedback batch that drove the `in_review` -> `fixing`
    route from the pinned `pending_fix_*` metadata.

    The per-tick rescan in `_handle_fixing` reads from the in_review
    watermarks, which advance past the triggering feedback the moment a dev
    resume consumes it -- so once a fix has been attempted the batch can no
    longer be recovered by rescanning. This helper reconstructs it from the
    persisted ids instead, per SURFACE and each sorted by id, so the reading
    it hands back is the shape every other batch in this stage has. That
    matters past the prompt: a replay is delivered, so it is settled, and a
    batch flattened into one list could not say that its issue-thread half
    moves `last_action_comment_id` while its PR-conversation half never may.
    Filtering by the recorded id set inherently drops the orchestrator's own
    comments (their ids were never in the batch) and survives watermark
    advancement because the fetch is unbounded. A batch item deleted on GitHub
    since the route simply drops out.

    The validating -> fixing route preserves no `pending_fix_*_ids`; its lone
    replay anchor is the reviewer-feedback PR comment recorded in
    `pending_fix_reviewer_comment_id`. `_reviewer_anchor_comment` re-fetches it
    and it joins the PR CONVERSATION -- the surface it was posted on -- OUTSIDE
    `filter_trusted` (it is the orchestrator's own trusted reviewer output,
    which the author allowlist would otherwise drop). Consulted ONLY on the
    validating route (`pending_fix_at` unset): a stale anchor left behind by an
    earlier validating park must not be added to an in_review-route batch. The
    two routes are mutually exclusive in practice, so the anchor is
    de-duplicated against that surface's id-set batch defensively.

    Re-apply the author allowlist at reconstruction time, not only at route
    time: an issue parked before the trust gate shipped can carry untrusted ids
    in `pending_fix_*_ids`, and `ALLOWED_ISSUE_AUTHORS` may change between the
    route and the `/orchestrator continue` replay. Existing parked issues that
    carry only `pending_fix_*_max_id` (no id lists) get the conservative
    single-item reconstruction from `_pending_fix_id_set`.
    """
    thread, conversation = _bookmarks._reconstruct_issue_space(
        gh, issue, pr, state,
    )
    inline, summaries = _bookmarks._reconstruct_review_surfaces(gh, pr, state)
    return _models._FixingFeedback(
        issue_thread=filter_trusted(thread),
        pr_conversation=_anchored(
            gh, pr, state, filter_trusted(conversation),
        ),
        review_comments=filter_trusted(inline),
        review_summaries=filter_trusted(summaries),
    )


def _anchored(gh, pr, state, rebuilt: list) -> list:
    """The PR conversation this replay rebuilt, plus the validating anchor.

    The anchor is a PR-conversation comment, so it belongs on that surface
    rather than at the head of a merged list -- which is also what keeps the
    settlement behind the replay from recording it against the issue thread.
    """
    if state.get(_state._PENDING_FIX_AT) is not None:
        return rebuilt
    anchor = _bookmarks._reviewer_anchor_comment(gh, pr, state)
    if anchor is None or any(
        feedback_item.id == anchor.id for feedback_item in rebuilt
    ):
        return rebuilt
    return [anchor] + rebuilt


def _carried_fresh_feedback(
    feedback: _models._FixingFeedback,
) -> _models._FixingFeedback:
    """Return the fresh comments a replay may show the dev, minus the command.

    A bare `/orchestrator continue` is a control signal addressed to the
    orchestrator, and the replay renders whatever it is handed as PR feedback
    to act on -- so carrying it through would ask the dev to implement the
    command itself, on top of the batch it was meant to retry. Anything the
    operator wrote BESIDE the command line survives verbatim, command line
    included: mixed comments are guidance, and mangling their body is not this
    owner's call.

    Cut per surface, like every other reading this stage takes, so the batch
    the prompt quotes stays the batch a settlement can attribute.

    Dropping the bare command costs nothing downstream. What the resume
    SETTLES is this reading joined with the whole fresh rescan, so the command
    is consumed exactly as the refusal road consumes one and does not re-fire
    next tick.
    """
    return _models._FixingFeedback(
        issue_thread=_carrying(feedback.issue_thread),
        pr_conversation=_carrying(feedback.pr_conversation),
        review_comments=_carrying(feedback.review_comments),
        review_summaries=_carrying(feedback.review_summaries),
    )


def _carrying(read: list) -> list:
    """One surface's fresh items, minus the bare commands among them."""
    return [
        comment for comment in read
        if not _messages._is_bare_orchestrator_continue(comment)
    ]


def _commands_only(
    feedback: _models._FixingFeedback,
) -> _models._FixingFeedback:
    """The refused commands alone, each still on the surface it was posted on.

    What a refusal consumes is the command it answered and nothing else, so
    the batch is cut per surface rather than merged: a command typed into the
    pull request's conversation is not something the issue thread has
    delivered, and settling it there would record a reply nobody wrote as
    answered.
    """
    return _models._FixingFeedback(
        issue_thread=_messages._parse_orchestrator_continue(
            feedback.issue_thread,
        ),
        pr_conversation=_messages._parse_orchestrator_continue(
            feedback.pr_conversation,
        ),
        review_comments=[],
        review_summaries=[],
    )


def _handle_continue_command(
    ctx: _models._FixingContext,
    feedback: _models._FixingFeedback,
) -> tuple:
    """Dispatch a `/orchestrator continue` operator command on a parked
    `fixing` issue.

    `/orchestrator continue` is the operator's "retry this fix" signal for a
    session-limit / session-failure park: a dev session that went silent
    (`agent_silent`) or timed out (`agent_timeout`) and left the fix-loop
    parked. The naive un-park resumes the dev on the command text alone,
    dropping the PR review feedback the poisoned session never addressed --
    the geserdugarov/lance-open-source#23 shape.

    Returns `(action, items)`:

      * ``("replay", batch)`` -- an eligible park WITH a reconstructable batch
        (the in_review `pending_fix_*` bookmarks, or the validating-route
        `pending_fix_reviewer_comment_id` anchor). Drops the poisoned dev
        session (so the retry re-grounds a FRESH session on the committed
        branch rather than replaying the transcript that already failed) and
        clears the park, as side effects; `batch` is a `_FixingFeedback`
        joining the preserved PR-feedback batch
        (`_reconstruct_pending_fix_batch`) with the fresh feedback that
        carries something (`_carried_fresh_feedback`) -- any guidance posted
        with or beside the command, verbatim, but never the bare command
        itself -- each item on the surface it was posted on, so the resume
        settles the replay against the readers that own it. Pinned state is
        NOT written here (the caller's resume tail writes it).
      * ``("refuse", None)`` -- a content-free continue (every fresh comment is
        a bare command) on a park it cannot retry: an unsafe park that still
        needs real human guidance, or an eligible park with no reconstructable
        batch (a validating-route park whose reviewer anchor was never recorded
        or has since been deleted). Settles the command comment as consumed on
        the surface it was posted on (so the refusal does not re-fire, and a
        later route reads the answered command as answered) and posts the
        reason; the caller writes state and the issue stays parked.
      * ``("passthrough", None)`` -- the command arrived alongside genuine
        guidance on a park with no replayable batch. No side effect; the caller
        runs the normal resume so that guidance (not a bare continue) drives
        the dev.
    """
    park_reason = ctx.state.get(_state._PARK_REASON)
    batch = (
        _reconstruct_pending_fix_batch(ctx.gh, ctx.issue, ctx.pr, ctx.state)
        if park_reason in _messages._CONTINUE_PARK_REASONS
        else _models._no_fixing_feedback()
    )
    preserved = batch.all_items
    if preserved:
        _dev_session._drop_poisoned_dev_session(ctx.state)
        ctx.state.set(_state._AWAITING_HUMAN, False)
        ctx.state.set(_state._PARK_REASON, None)
        log.info(
            "issue=#%s /orchestrator continue: replaying %d preserved feedback "
            "item(s) on a fresh dev session (park_reason=%s)",
            ctx.issue.number, len(preserved), park_reason,
        )
        return "replay", batch.merged_with(_carried_fresh_feedback(feedback))

    if all(
        _messages._is_bare_orchestrator_continue(comment)
        for comment in feedback.all_items
    ):
        # Content-free continue with nothing else to act on. Consume only the
        # command comment(s) -- every item here is a bare command, so
        # `_commands_only` covers them -- so the refusal is not re-posted every
        # tick, then stay parked with a reason.
        _feedback._settle_consumed_feedback(
            ctx.state, _commands_only(feedback),
        )
        if park_reason in _messages._CONTINUE_PARK_REASONS:
            message = (
                f"{config.HITL_MENTIONS} `/orchestrator continue`: no "
                "preserved PR-feedback batch is on file to replay for this "
                "park. Reply with the change to make, or relabel the issue, "
                "to proceed."
            )
        else:
            message = (
                f"{config.HITL_MENTIONS} `/orchestrator continue` needs your "
                "actual guidance here: this park is waiting on a real answer "
                "(an agent question, or a worktree it could not finish), not "
                "a generic continue. Reply with the specific change to make, "
                "or relabel the issue, to proceed."
            )
        _comments._post_issue_comment(ctx.gh, ctx.issue, ctx.state, message)
        return "refuse", None

    # The command came WITH genuine guidance on a park with no replayable
    # batch; let the normal resume feed that guidance to the dev.
    return "passthrough", None
