# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Keep an interrupted attempt whose publication or workflow label moved.

Neither a reset nor a clear can be justified against another publication.
The dormant recovery leaves the checkout and pinned evidence intact, and
records a stranded park once so repeated ticks do not consume human replies.
"""
from __future__ import annotations

from orchestrator import config
from orchestrator.git.base_sync import persistence
from orchestrator.git.base_sync.models import (
    _AutoRebaseRecoveryContext,
    _AutoRebaseRecoverySnapshot,
)
from orchestrator.git.base_sync.state import (
    _AWAITING_HUMAN,
    _PARK_REASON,
    _REASON_AUTO_BASE_REBASE_FAILED,
    log,
)


def _park_foreign_publication_recovery(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Park, without a reset, an attempt made for another publication.

    The interrupted tick recorded which pull request it rebased for and which
    stage it was entered from, and the issue no longer says either. Every road
    out of a recovery ends in the same tail -- a notice to the pull request
    this tick holds, an audit event filed under the stage this tick reads, and
    the anchor dropped -- so finishing here would attribute the dead tick's
    work to a publication it was never made for, and drop the one record that
    could ever say otherwise. The permit catches the same disagreement where
    there is a verdict to move; on an issue carrying none there is no permit,
    so this is the only reading that can.

    Nothing is reset. Which publication the branch belongs to is exactly what
    this tick cannot say, and putting the checkout back onto the anchor would
    throw the replay away to settle a question about the pull request rather
    than about the commit. The whole record stays pinned with it, so a human
    who repoints the issue back, or clears the record, hands the next tick
    something it can finish.
    """
    recorded = context.pending_rewrite
    log.warning(
        "issue=#%d auto-rebase recovery: the interrupted attempt recorded PR "
        "#%d from %r and this issue now records PR #%d on %r; parking rather "
        "than finishing a route for a publication it was not made for",
        context.issue.number, recorded.pr_number, str(recorded.stage),
        context.pr_number, str(context.label),
    )
    persistence._park_auto_rebase_failure(
        context.gh,
        context.issue,
        context.state,
        message=(
            f"{config.HITL_MENTIONS} crash recovery for this issue's auto "
            f"rebase: the interrupted attempt was made against pull request "
            f"#{recorded.pr_number} from `{recorded.stage}`, and this issue "
            f"now records pull request #{context.pr_number} on "
            f"`{context.label}`. Finishing it would post the notice, file the "
            "audit event, and route the reviewer against a publication that "
            "attempt was never made for, so nothing was pushed and HEAD has "
            "not been reset. Put the issue back on the publication the rebase "
            "was made for -- or clear the `pending_auto_base_rebase_*` fields "
            "on the pinned comment -- then reply on this issue with anything "
            "to retry."
        ),
        reason=_REASON_AUTO_BASE_REBASE_FAILED,
    )
    return True


def _already_stranded(state) -> bool:
    """Whether this route's own stranded park is already standing.

    Two fields, and the anchor beside them is what makes the pair this park's
    own rather than any other auto-rebase failure's: every other road that
    ends on this reason resets the branch and clears the attempt first, so a
    comment still carrying one is one only this park could have left. The
    caller is on that road by definition, since the record is what brought it
    here.
    """
    if not state.get(_AWAITING_HUMAN):
        return False
    return state.get(_PARK_REASON) == _REASON_AUTO_BASE_REBASE_FAILED


def _park_stranded_recovery(context: _AutoRebaseRecoveryContext) -> bool:
    """Hold an attempt whose issue was relabelled out from under it.

    The label is no longer one refresh drives, so this recovery has no road
    left: nothing here fetches, compares, or publishes for a stage the sync
    does not own. What the attempt left decides what that costs. An issue
    holding a rebase an earlier tick RECORDED, a permission granted for a push
    nobody made, or a branch git has already replayed is not an issue that
    loses nothing by dropping the anchor: the checkout may be standing on a
    rewrite the pull request has never seen, a human's verdict is licensed
    onto a commit no push carried, and the approval debt beside it says a
    publication is still owed.

    Dropped there, the three come apart from one another. The anchor is the
    only thing naming what the branch would go back to, so the replay stops
    being attributable to anything; the permission outlives the attempt it was
    granted for and the next grant trips over it; and a decomposition tick
    reading an issue with no attempt in flight is free to put another agent on
    a change a human already ruled on.

    So nothing is reset and nothing is cleared. The reset cannot run here for
    the same reason the classification cannot: this tick does not know whether
    the hand that moved the label also moved the checkout, and a hard reset
    onto the anchor would answer that by discarding it.

    Which is also why the park has to be taken ONCE. Keeping the record is
    what brings this route back, and this route is reached from the label
    check ahead of every gate -- so every poll under the wrong label arrives
    here again, over a comment nothing has changed. Said again each time, the
    thread fills with one sentence repeated and each park ratchets
    `last_action_comment_id` past whatever the operator wrote: the reply that
    would release the attempt ends up behind the orchestrator's own newest
    comment and the retry scan never sees it.
    """
    if _already_stranded(context.state):
        return True
    log.warning(
        "issue=#%d auto-rebase recovery: label %r is not one the refresh "
        "drives and the attempt left records a clear would strand; keeping "
        "them and parking awaiting human",
        context.issue.number, context.label,
    )
    persistence._park_auto_rebase_failure(
        context.gh,
        context.issue,
        context.state,
        message=(
            f"{config.HITL_MENTIONS} this issue was moved to "
            f"`{context.label}`, which the base refresh does not drive, while "
            "an auto rebase was still in flight for it -- the branch may be "
            "standing on a replay the pull request has never seen, and a "
            "permission granted for a push nobody made may still be "
            "outstanding. Nothing was reset and nothing was cleared, because "
            "this tick cannot say whether the checkout moved with the label. "
            "Put the issue back on the stage the rebase was made under to let "
            "the recovery finish it, or reconcile the "
            "`pending_auto_base_rebase_*` and `late_rewrite_*` fields on the "
            "pinned comment by hand."
        ),
        reason=_REASON_AUTO_BASE_REBASE_FAILED,
    )
    return True
