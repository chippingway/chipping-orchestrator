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
implement is the word "continue". Nothing is lost by dropping it, because the
resume tail advances the watermarks past all of the fresh feedback rather than
past what it replayed.

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


def _reconstruct_pending_fix_batch(gh, issue, pr, state) -> list:
    """Rebuild the exact feedback batch that drove the `in_review` -> `fixing`
    route from the pinned `pending_fix_*` metadata.

    The per-tick rescan in `_handle_fixing` reads from the in_review
    watermarks, which advance past the triggering feedback the moment a dev
    resume consumes it -- so once a fix has been attempted the batch can no
    longer be recovered by rescanning. This helper reconstructs it from the
    persisted ids instead, returned in the same order the route built them --
    issue-space (issue-thread + PR-conversation) then inline review comments
    then review summaries, each sorted by id. Filtering by the recorded id set
    inherently drops the orchestrator's own comments (their ids were never in
    the batch) and survives watermark advancement because the fetch is
    unbounded. A batch item deleted on GitHub since the route simply drops out.

    The validating -> fixing route preserves no `pending_fix_*_ids`; its lone
    replay anchor is the reviewer-feedback PR comment recorded in
    `pending_fix_reviewer_comment_id`. `_reviewer_anchor_comment` re-fetches it
    and it is prepended to the batch OUTSIDE `filter_trusted` (it is the
    orchestrator's own trusted reviewer output, which the author allowlist
    would otherwise drop). Consulted ONLY on the validating route
    (`pending_fix_at` unset): a stale anchor left behind by an earlier
    validating park must not be prepended to an in_review-route batch. The two
    routes are mutually exclusive in practice, so the anchor is de-duplicated
    against the id-set batch defensively.

    Re-apply the author allowlist at reconstruction time, not only at route
    time: an issue parked before the trust gate shipped can carry untrusted ids
    in `pending_fix_*_ids`, and `ALLOWED_ISSUE_AUTHORS` may change between the
    route and the `/orchestrator continue` replay. Existing parked issues that
    carry only `pending_fix_*_max_id` (no id lists) get the conservative
    single-item reconstruction from `_pending_fix_id_set`.
    """
    trusted_batch = filter_trusted(
        _bookmarks._reconstruct_issue_space(gh, issue, pr, state)
        + _bookmarks._reconstruct_review_comments(gh, pr, state)
        + _bookmarks._reconstruct_review_summaries(gh, pr, state)
    )
    if state.get(_state._PENDING_FIX_AT) is None:
        anchor = _bookmarks._reviewer_anchor_comment(gh, pr, state)
        if anchor is not None and all(
            feedback_item.id != anchor.id for feedback_item in trusted_batch
        ):
            return [anchor] + trusted_batch
    return trusted_batch


def _carried_fresh_feedback(feedback: _models._FixingFeedback) -> list:
    """Return the fresh comments a replay may show the dev, minus the command.

    A bare `/orchestrator continue` is a control signal addressed to the
    orchestrator, and the replay renders whatever it is handed as PR feedback
    to act on -- so carrying it through would ask the dev to implement the
    command itself, on top of the batch it was meant to retry. Anything the
    operator wrote BESIDE the command line survives verbatim, command line
    included: mixed comments are guidance, and mangling their body is not this
    owner's call.

    Dropping the bare command costs nothing downstream. The resume tail
    advances the watermarks past ALL of `feedback` rather than past what it
    replayed, so the command is still consumed and does not re-fire next tick.
    """
    return [
        comment
        for comment in feedback.all_items
        if not _messages._is_bare_orchestrator_continue(comment)
    ]


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
        clears the park, as side effects; `batch` is the preserved PR-feedback
        batch (`_reconstruct_pending_fix_batch`) followed by the fresh feedback
        that carries something (`_carried_fresh_feedback`) -- any guidance
        posted with or beside the command, verbatim, but never the bare
        command itself. Pinned state is NOT written here (the caller's resume
        tail writes it).
      * ``("refuse", None)`` -- a content-free continue (every fresh comment is
        a bare command) on a park it cannot retry: an unsafe park that still
        needs real human guidance, or an eligible park with no reconstructable
        batch (a validating-route park whose reviewer anchor was never recorded
        or has since been deleted). Consumes the command comment (so the
        refusal does not re-fire) and posts the reason; the caller writes state
        and the issue stays parked.
      * ``("passthrough", None)`` -- the command arrived alongside genuine
        guidance on a park with no replayable batch. No side effect; the caller
        runs the normal resume so that guidance (not a bare continue) drives
        the dev.
    """
    park_reason = ctx.state.get(_state._PARK_REASON)
    batch = (
        _reconstruct_pending_fix_batch(ctx.gh, ctx.issue, ctx.pr, ctx.state)
        if park_reason in _messages._CONTINUE_PARK_REASONS else []
    )
    if batch:
        _dev_session._drop_poisoned_dev_session(ctx.state)
        ctx.state.set(_state._AWAITING_HUMAN, False)
        ctx.state.set(_state._PARK_REASON, None)
        log.info(
            "issue=#%s /orchestrator continue: replaying %d preserved feedback "
            "item(s) on a fresh dev session (park_reason=%s)",
            ctx.issue.number, len(batch), park_reason,
        )
        return "replay", batch + _carried_fresh_feedback(feedback)

    if all(
        _messages._is_bare_orchestrator_continue(comment)
        for comment in feedback.all_items
    ):
        # Content-free continue with nothing else to act on. Consume only the
        # command comment(s) (`feedback.all_items` is all bare commands here,
        # so `continue_cmds` covers them) so the refusal is not re-posted every
        # tick, then stay parked with a reason.
        continue_cmds = _messages._parse_orchestrator_continue(feedback.issue_space)
        command_feedback = _models._FixingFeedback(
            issue_space=continue_cmds,
            review_comments=[],
            review_summaries=[],
            all_items=continue_cmds,
        )
        _feedback._advance_consumed_watermarks(ctx.state, command_feedback)
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
