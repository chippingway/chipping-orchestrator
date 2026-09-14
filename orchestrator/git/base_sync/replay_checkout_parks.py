# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Restore the anchor when a replay's checkout or remote contradicts its record.

The dormant replay recovery refuses unrecorded work and out-of-band rollback.
The reset must succeed before its abandoned bookkeeping can be cleared;
announced publications cannot be pushed and announced a second time.
"""
from __future__ import annotations

from orchestrator import config
from orchestrator.git.base_sync import persistence, recovery_notices as _recovery_notices
from orchestrator.git.base_sync.models import (
    _AutoRebaseRecoveryContext,
    _AutoRebaseRecoverySnapshot,
)
from orchestrator.git.base_sync.state import (
    _REASON_AUTO_BASE_REBASE_FAILED,
    _REASON_AUTO_BASE_REBASE_PUSH_FAILED,
    log,
)


def _park_rolled_back_recovery(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Restore the anchor when the remote was rolled back off this replay.

    The record says the pull request carried the commit on this checkout --
    a receipt naming it, or a transfer that settled on the write behind one --
    and the remote is not standing on it now. Somebody moved the branch back,
    and where they moved it to is very often the pre-rebase anchor itself,
    which is the head a reissued force-push would be leased against. That
    lease would be satisfied, the push would land, and the rollback would be
    gone -- the one outcome a lease exists to prevent, reached by a recovery
    mistaking somebody's undo for its own unfinished work.

    So it is treated as the externally moved remote it is: HEAD goes back onto
    the anchor so the checkout matches what the pull request has, the anchor
    is dropped with it, and the issue parks for a human to say which of the
    two heads the branch is supposed to be on.
    """
    local_short = _recovery_notices._short(recovery_snapshot.head)
    remote_short = _recovery_notices._short(recovery_snapshot.remote_head)
    log.warning(
        "issue=#%d auto-rebase recovery: the pinned comment records %s as "
        "published and PR #%d stands on %s; treating the branch as rolled "
        "back out of band rather than force-pushing over it",
        context.issue.number, local_short, context.pr_number, remote_short,
    )
    persistence._reset_clear_and_park(
        context,
        context.pending_pre_rebase_sha,
        message=(
            f"{config.HITL_MENTIONS} crash recovery for PR "
            f"#{context.pr_number}: this issue's pinned comment records "
            f"`{local_short}` as already pushed, and the pull request is "
            f"standing on `{remote_short}` instead -- the branch was rolled "
            "back or moved out of band while the orchestrator was down. "
            "Reissuing the interrupted push would be leased against the very "
            "head it was rolled back to and would overwrite it, so nothing "
            "was pushed and HEAD has been reset to the pre-rebase SHA. "
            "Investigate the remote branch and reply on this issue with "
            "anything once it is reconciled."
        ),
        reason=_REASON_AUTO_BASE_REBASE_PUSH_FAILED,
    )
    return True


def _park_unrecorded_recovery(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Restore the anchor when the attempt's own record is in pieces.

    The pinned comment claims a record of what this attempt produced and
    cannot show it whole -- a member missing, a pull request that is not an
    identity, a stage no publication is entered from -- or shows it whole and
    names some OTHER commit. Read as the absence it resembles, the recovery
    would fall through to the ahead/behind counts and a strictly-ahead
    checkout would be measured and force-pushed on the strength of a claim
    nothing could check.

    So the branch goes back onto the anchor, which is the head the remote
    still carries wherever this refusal is reachable, and the issue parks. The
    record itself is left where the reset's own rule leaves every damaged
    group: for a human to repair, not for this tick to guess at.
    """
    local_short = _recovery_notices._short(recovery_snapshot.head)
    pre_rebase_short = _recovery_notices._short(context.pending_pre_rebase_sha)
    log.warning(
        "issue=#%d auto-rebase recovery: the record of what this attempt "
        "produced does not vouch for the checkout; resetting %s onto the "
        "anchor rather than publishing a head nothing names",
        context.issue.number, local_short,
    )
    persistence._reset_clear_and_park(
        context,
        context.pending_pre_rebase_sha,
        message=(
            f"{config.HITL_MENTIONS} crash recovery for PR "
            f"#{context.pr_number}: the pinned comment claims a record of the "
            "rebase an earlier tick was interrupted in the middle of, and it "
            f"does not say that `{local_short}` on the branch is that "
            "attempt's own work -- the record is in pieces, or it names some "
            f"other commit. HEAD has been reset to the pre-rebase SHA "
            f"`{pre_rebase_short}` and nothing was pushed. Repair or clear "
            "the `pending_auto_base_rebase_*` fields on the pinned comment, "
            "then reply on this issue with anything to retry."
        ),
        reason=_REASON_AUTO_BASE_REBASE_FAILED,
    )
    return True


def _park_undone_recovery(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Finish the rollback that put the branch back, and park what undid it.

    HEAD is exactly the head the attempt anchored, and the comment says the
    attempt got further than that: a replay it recorded producing, a mark a
    finish left, or a permission it never spent. Something put the branch back
    -- a reset whose own park write was lost, or a hand at the checkout -- and
    what it left behind is the bookkeeping that reset owed.

    So the reset is re-run onto the commit the branch is already on. It moves
    nothing, and that is the point: it is the step the abandoned rollback's
    own bookkeeping rides, so the debt for a commit no branch has and the
    permission that will never be spent on it go with it, on the rollback's
    own terms. The exemption is untouched, since the grant never moved it. A
    reset git refuses drops none of it, which is the same rule every other
    park here is held to.

    The park is what the missing half of that rollback owes a human: nothing
    here can say why the branch went back, and guessing would either rebase
    over an operator mid-repair or leave a record nobody reconciles.
    """
    unmoved = _recovery_notices._short(recovery_snapshot.head)
    log.warning(
        "issue=#%d auto-rebase recovery: HEAD is back on the anchor %s and "
        "the comment still carries what the attempt did past it; finishing "
        "the rollback's bookkeeping and parking rather than starting over",
        context.issue.number, unmoved,
    )
    persistence._reset_clear_and_park(
        context,
        context.pending_pre_rebase_sha,
        message=(
            f"{config.HITL_MENTIONS} crash recovery for PR "
            f"#{context.pr_number}: the branch is back on the pre-rebase SHA "
            f"`{unmoved}` and this issue still records the rebase an earlier "
            "tick made past it -- the replay it produced, the announcement a "
            "finish left, or the permission granted for a push nobody made. "
            "Something undid that rebase without finishing its bookkeeping, "
            "so the records it abandoned have been dropped and nothing was "
            "rebased or pushed. Check the worktree and reply on this issue "
            "with anything once it is where you want it."
        ),
        reason=_REASON_AUTO_BASE_REBASE_FAILED,
    )
    return True


def _park_announced_recovery(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Restore the anchor when a finish announced what the remote has lost.

    The announcement mark is written between a finish's notice and its
    relabel, so a comment carrying one says the push had already landed, the
    pull request had already been told, and the audit stream had already
    recorded it. The remote is not standing on the checkout now, so whatever
    was announced is not what the pull request has: somebody rolled it back,
    or the checkpoint itself is one something took apart.

    Either way this is the one road a retry may not take. Force-pushing here
    overwrites the rollback under a lease the anchor satisfies, and the finish
    behind it announces a second time -- a second notice on the pull request
    and a second `base_rebased` on the stream for one publication that
    happened once, with nothing left able to say which of the two describes
    the head the branch ended on.

    So the branch goes back onto the anchor, which is the head the pull
    request carries wherever this refusal is reachable, and the issue parks.
    Read as an absence instead, the mark is exactly the record whose whole
    purpose is to stop the second announcement.
    """
    local_short = _recovery_notices._short(recovery_snapshot.head)
    remote_short = _recovery_notices._short(recovery_snapshot.remote_head)
    log.warning(
        "issue=#%d auto-rebase recovery: a finish on this attempt already "
        "announced a publication and PR #%d is standing on %s rather than on "
        "%s; resetting onto the anchor rather than pushing and announcing a "
        "second time",
        context.issue.number, context.pr_number, remote_short, local_short,
    )
    persistence._reset_clear_and_park(
        context,
        context.pending_pre_rebase_sha,
        message=(
            f"{config.HITL_MENTIONS} crash recovery for PR "
            f"#{context.pr_number}: this issue's pinned comment records that "
            "a finish had already announced this rebase -- the notice went "
            "onto the pull request and the audit event was filed -- and the "
            f"pull request is standing on `{remote_short}` rather than on the "
            f"`{local_short}` on this branch. The publication was rolled back "
            "out of band, or the checkpoint itself was damaged. Reissuing the "
            "push would overwrite that rollback and announce the same rebase "
            "twice, so nothing was pushed and HEAD has been reset to the "
            "pre-rebase SHA. Investigate the remote branch and the "
            "`pending_auto_base_rebase_announced_sha` field, then reply on "
            "this issue with anything to retry."
        ),
        reason=_REASON_AUTO_BASE_REBASE_PUSH_FAILED,
    )
    return True
