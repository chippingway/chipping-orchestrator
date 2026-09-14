# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Receipt a landed rewrite whose transfer permission is still outstanding.

The window between a push that landed and the write that receipts it, reached
through the dormant `landed_recovery` route. The permit is asked before the
gate and the gate is told it is the only licence, so a refusal is never
measured. Standing on the commit already, the push is the leased no-op the push
tail makes anyway, and the receipt, the paid debt, the rotation, and its proof
ride that tail's one write. The rotation is read back afterwards, since a permit
that stopped holding inside the gate leaves the verdict where it was. Nothing
here resets: the remote carries the checkout's head, so every refusal keeps
HEAD and the anchor for a human.
"""
from __future__ import annotations

from orchestrator.git.base_sync import (
    outcomes,
    publication,
    recovery_push as _recovery_push,
    replay_transfer_parks as _replay_transfer_parks,
    transfer_permits as _transfer_permits,
    transfers,
)
from orchestrator.git.base_sync.models import (
    _AutoRebaseRecoveryContext,
    _AutoRebaseRecoverySnapshot,
)

# Why the receipt could not be taken, in the operator's own terms.
_REFUSED_PERMIT = (
    "the permit that would license the settlement refused this tick -- the "
    "pull request, the stage, the checkout, the lease, or the two "
    "contributions no longer agree with the permission on the comment, and "
    "the orchestrator log names which"
)

_REFUSED_NO_OP = (
    "the `--force-with-lease` no-op that would have receipted it, leased "
    "against that same commit, did not land -- the remote branch moved after "
    "this tick read it"
)


def _settle_published_recovery(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Receipt a landed rewrite through the leased no-op that proves it.

    Entered on the anchor and named against the rewritten commit, exactly as
    the interrupted tick entered it: the anchor is the head the permit was
    granted against, and a pull request standing on the rewrite instead is
    this issue's own push having landed, which the debt the grant recorded is
    what lets the entry freeze.

    There is nothing to measure on this road. A count under the ceiling would
    report the settlement landed with the permission still outstanding, and a
    count over it would route an adjudicated change into a second adjudication
    with the pull request already carrying the work -- so the gate is held to
    the permit, and the permit decides whether the permission may be spent.
    """
    landed = completed.head
    if not _transfer_permits._permits_the_publication(context, landed):
        return _replay_transfer_parks._park_unfinished_recovery(
            context, completed, _REFUSED_PERMIT,
        )
    records = publication._gate_records()
    # Gate values stay deferred with the workflow call to preserve layering.
    from orchestrator.workflow.stages.implementing.late_gate_models import _Entered
    published = publication._gated_publication()._publishes(
        records._gate(
            context.gh, context.spec, context.issue, context.state,
            context.worktree,
        ),
        completed.branch,
        _Entered(
            head=context.pending_pre_rebase_sha or "", reconciling=True,
            candidate=landed, permit_only=True,
        ),
    )
    unsettled = _unsettled_no_op(context, completed, published)
    if unsettled is not None:
        return unsettled
    return outcomes._finalize_already_published_recovery(context, completed)


def _unsettled_no_op(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
    published,
) -> bool | None:
    """What a leased no-op that settled nothing owes, or None where it settled.

    A permit the gate refused publishes nothing, and measuring is the one thing
    this road may not fall back on. A hold is a tick the gate finished for
    itself, and only the flags it left in memory are owed a write. A push that
    did not land is a remote that moved between this tick's fetch and the
    request. And a push that landed with the verdict still where it was is a
    permit that stopped holding inside the gate.
    """
    if published.refused:
        return _replay_transfer_parks._park_unfinished_recovery(
            context, completed, _REFUSED_PERMIT,
        )
    if published.held:
        context.gh.write_pinned_state(context.issue, context.state)
        return True
    if not published.landed:
        return _replay_transfer_parks._park_unfinished_recovery(
            context, completed, _REFUSED_NO_OP,
        )
    if transfers._rotated_onto(context.state, completed.head):
        return None
    return _replay_transfer_parks._park_unfinished_recovery(
        context, completed,
        _recovery_push._UNROTATED.format(published=completed.head),
    )
