# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Publish the verified recovery head and account for its exact outcome.

The running recovery uses the measured gate. The dormant replay route may
supply transfer evidence and require a permit-only push, rechecking the permit
inside the gate and the verdict's rotation after publication. A refusal never
falls through to measurement, and a held tick does not finalize twice.
"""
from __future__ import annotations

from orchestrator.git.base_sync import (
    outcomes,
    persistence,
    publication,
    recovery_notices as _recovery_notices,
    replay_transfer_parks as _replay_transfer_parks,
    transfer_evidence as _transfer_evidence,
    transfer_permits as _transfer_permits,
    transfers,
)
from orchestrator.git.base_sync.models import (
    _AutoRebaseRecoveryContext,
    _AutoRebaseRecoverySnapshot,
)
from orchestrator.git.base_sync.transfer_values import _Handoff
from orchestrator.git.verification import status as _worktree_status

# Why a push that landed could not be finished, in the operator's own terms.
# Spelled at the seam that answers for it rather than beside the park, which
# takes whatever reason its caller established.
_UNROTATED = (
    "the push went out and the verdict did not move with it, so the "
    "permission granted for `{published}` is still outstanding"
)


def _retry_recovery_push(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
    carried: _Handoff = _Handoff.NOTHING,
    *,
    permit_alone: bool = False,
) -> bool:
    """Publish a verified ahead-only recovery head and finalize its state.

    Measured before it is published, like every other push onto a pull request
    the remote already carries: the head this recovery found is one an earlier
    tick rebased and never pushed, so nothing on this branch has been read
    against the base it now sits on.

    Unless the branch is standing on a rewrite of a commit an adjudication
    accepted, which is the one candidate that may be published without a
    reading. `carried` says how far the interrupted tick got with that
    transfer, and what this call owes it is the evidence: a permission the
    grant already recorded is what `late_transfer` re-asks the permit over,
    and a rewrite that never reached one is re-derived here so the replay is
    not measured past the same ceiling and adjudicated a second time with a
    pull request open over the work.

    Where there IS such a transfer, the permit is the whole of what may let
    this push out. It is asked before the gate and the gate is told the same,
    so a refusal is a refusal on both sides of that seam rather than a
    fall-through to the cumulative reading -- which on this road would
    force-push a replay nothing vouched for and clear the recovery with the
    verdict still on the commit a human ruled on. The rotation is read back
    afterwards for the same reason, since a permit that stopped holding
    between the two asks leaves the push landed and the verdict where it was.

    `permit_alone` says the ATTEMPT record names no head -- the process died
    inside the window between `git rebase` and the write after it -- so the
    transfer is the only thing that can vouch for this checkout. Evidence that
    will not assemble parks there rather than falling through, because the
    fall-through is the ordinary cumulative reading and measuring a commit is
    not a way of establishing whose it is. A permission this route's own grant
    already persisted is that evidence rather than the absence of it, so it
    licenses the road exactly as the re-derived rewrite does.

    Both are the dormant route's to pass. The running route hands in neither,
    and with neither the transfer is `NOTHING`, nothing is re-derived, and the
    push is the measured one described first.
    """
    dirty_files = _worktree_status._worktree_dirty_files(context.worktree)
    if dirty_files:
        return outcomes._park_dirty_recovery(
            context, recovery_snapshot, dirty_files,
        )
    rewrite = _transfer_evidence._reconstructed(
        context, recovery_snapshot.head, carried,
    )
    licensed = rewrite is not None or carried == _Handoff.OUTSTANDING
    if permit_alone and not licensed:
        return _replay_transfer_parks._park_unproven_replay_recovery(
            context, recovery_snapshot,
        )
    if licensed and not _transfer_permits._permits_the_publication(
        context, recovery_snapshot.head, rewrite,
    ):
        return _replay_transfer_parks._park_refused_permit_recovery(
            context, recovery_snapshot,
        )
    return _pushes_the_recovered_head(
        context, recovery_snapshot, rewrite, licensed,
    )


def _pushes_the_recovered_head(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
    rewrite,
    licensed: bool,
) -> bool:
    """Reissue the interrupted push and finalize what it earns.

    `licensed` says a transfer this recovery already knows about is the whole
    of what may let the push out, and it is passed to the gate as well as
    asked ahead of it: a permit that stops holding between the two asks is
    refused there rather than measured, and one that stops holding after the
    push leaves the verdict where it was, which the rotation read below
    catches.
    """
    landed = recovery_snapshot.head
    records = publication._gate_records()
    # Gate values stay deferred with the workflow call to preserve layering.
    from orchestrator.workflow.stages.implementing.late_gate_models import _Entered
    published = publication._gated_publication()._publishes(
        records._gate(
            context.gh, context.spec, context.issue, context.state,
            context.worktree,
        ),
        recovery_snapshot.branch,
        _Entered(
            head=context.pending_pre_rebase_sha or "", reconciling=True,
            # The head this recovery verified against the remote and the one
            # the finalize below records as published. The gate proves the
            # checkout again, and a commit that landed between the two
            # readings would be the one pushed while the notice and the event
            # named this one -- so the candidate is bound and a moved checkout
            # refuses instead.
            candidate=landed,
            rewrite=rewrite,
            permit_only=licensed,
        ),
    )
    unfinished = _unfinished_recovery_push(
        context, recovery_snapshot, published, licensed,
    )
    if unfinished is not None:
        return unfinished
    return persistence._finalize_recovered_rebase(
        context,
        local_head=landed,
        method="crash_recovery_pushed",
        notice=_recovery_notices._pushed_recovery_notice(context, landed),
    )


def _unfinished_recovery_push(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
    published,
    licensed: bool,
) -> bool | None:
    """What a reissued push that did not finish owes, or None where it did.

    Four answers before the finalize, and each is a different tick. A permit
    the gate refused publishes nothing and parks here, since measuring is the
    one thing this road may not fall back on. A hold is a tick the gate
    finished for itself -- parked, or handed to the adjudication -- and only
    the flags it left in memory are owed a write. A push that went out and
    failed is the caller's own park. And a push that landed without the
    verdict moving with it is a permit that stopped holding inside the gate.
    """
    if published.refused:
        return _replay_transfer_parks._park_refused_permit_recovery(
            context, recovery_snapshot,
        )
    if published.held:
        # The gate took the candidate this recovery was finishing, so the
        # finalize behind this -- the notice, the event, the `validating`
        # route -- is not this tick's. The park it left is written here, since
        # nothing else would.
        context.gh.write_pinned_state(context.issue, context.state)
        return True
    if not published.landed:
        return outcomes._park_failed_recovery_push(context, recovery_snapshot)
    landed = recovery_snapshot.head
    if licensed and not transfers._rotated_onto(context.state, landed):
        return _replay_transfer_parks._park_unfinished_recovery(
            context, recovery_snapshot, _UNROTATED.format(published=landed),
        )
    return None
