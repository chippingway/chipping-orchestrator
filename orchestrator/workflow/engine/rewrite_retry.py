# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The retry of a replay an interrupted tick made and never published, from its candidate to its finish.

The recovery (`rewrite_recovery`) reaches this with a checkout the pull
request is not standing on and every refusal ahead of a retry already asked,
and this is the workflow's road from there to the issue's next stage. The git
owner reads the candidate the attempt left (`git/base_sync/recovery_push.py`):
the replay in the checkout, the anchor its lease is pinned to, the publication
and stage the attempt recorded, and the remote head the recovery verified.
Every decision about it is made here, in the order the recovery has always
kept:

- A checkout git names uncommitted paths in is reset, cleaned, and parked:
  those paths would ride the push.
- An ordinary replay is measured before it is published, like every other
  push onto a pull request the remote already carries. A replay of a commit
  an adjudication accepted is the one candidate that may be published without
  a reading, and only on the transfer permit: a permission the interrupted
  grant left, or the evidence re-derived for a grant the crash came before
  (`git/base_sync/transfer_evidence.py`). Where the attempt record names no
  head, the transfer is the only voucher there is, and evidence that will not
  assemble parks rather than falling through to the cumulative reading --
  measuring a commit says how big it is, never whose it is.
- Where there is such a transfer, the permit is the whole of what may let the
  push out. It is asked before the gate (`git/base_sync/transfer_permits.py`)
  and the gate is told the same, so a refusal on either side of that seam is
  a reset and a park rather than the cumulative reading, which on this road
  would force-push a replay nothing vouched for and finish the route with the
  verdict still on the commit a human ruled on.
- The push the gate licenses is the git owner's publication of exactly that
  candidate under the anchor's lease, through the transport the ordinary
  publication pushes with (`rewrite_publication.CandidatePush`). The receipt,
  the debt it settles, the exemption it rotates, and the proof of the checkout
  behind it stay the gate's own (`stages/implementing/late_push.py`).
- A publication that sent nothing or did not land resets the checkout onto
  the anchor and parks. One that landed with the verdict left behind -- a
  permit that stopped holding inside the gate -- parks with HEAD and the
  anchor where they stand. Every other landing is handed to the one finish
  every landing gets (`rewrite_finish.finishes_the_recovery`), on its
  recovery road and with the human reply that brought the attempt back,
  which it spends -- the same hand a push the recovery finds already landed
  is finished through (`rewrite_landed`).

Run under the issue writer claim the base refresh (`base_refresh`) takes
before the issue is read and holds through the route.
"""
from __future__ import annotations

from orchestrator.git.base_sync import (
    outcomes as _outcomes,
    recovery_push as _recovery_push,
    replay_transfer_parks as _replay_transfer_parks,
    transfer_evidence as _transfer_evidence,
    transfer_permits as _transfer_permits,
    transfers as _transfers,
)
from orchestrator.git.base_sync.models import (
    _AutoRebaseRecoveryContext,
    _AutoRebaseRecoverySnapshot,
)
from orchestrator.git.base_sync.rewrite_handoffs import _RewriteCandidate
from orchestrator.git.base_sync.transfer_values import _Handoff
from orchestrator.workflow.engine import (
    rewrite_finish as _finish,
    rewrite_publication as _rewrite_publication,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_push as _late_push,
    late_records as _late_records,
)


def retries(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
    carried: _Handoff = _Handoff.NOTHING,
    *,
    permit_alone: bool = False,
) -> bool:
    """Publish the replay `completed` verified and finish what landed; whether the recovery owns the tick.

    `carried` says how far the interrupted tick got with the transfer it was
    making, and `permit_alone` says the attempt record names no head -- the
    process died between `git rebase` and the write after it -- so the
    transfer is the only thing that can vouch for this checkout. A permission
    this route's own grant already persisted is that evidence rather than the
    absence of it, so it licenses the road exactly as the re-derived rewrite
    does. False only where the finish left the landed head behind a base that
    has advanced again, and this tick's rebase goes on from it.
    """
    candidate = _recovery_push._recovered_candidate(context, completed)
    dirty = candidate.checkout.status.paths
    if dirty:
        return _outcomes._park_dirty_recovery(context, completed, list(dirty))
    rewrite = _transfer_evidence._reconstructed(context, completed.head, carried)
    licensed = rewrite is not None or carried == _Handoff.OUTSTANDING
    if permit_alone and not licensed:
        return _replay_transfer_parks._park_unproven_replay_recovery(context, completed)
    if licensed and not _transfer_permits._permits_the_publication(context, completed.head, rewrite):
        return _replay_transfer_parks._park_refused_permit_recovery(context, completed)
    entered = _late_gate_models._Entered(
        head=context.pending_pre_rebase_sha,
        reconciling=True,
        # The head this recovery verified against the remote, and the one the
        # finish records as published. The gate proves the checkout again, and
        # a commit that landed between the two readings would be the one
        # pushed while the notice and the event named this one -- so it is
        # bound, and a moved checkout refuses instead.
        candidate=completed.head,
        rewrite=rewrite,
        permit_only=licensed,
    )
    return _publishes(context, completed, candidate, entered)


def _publishes(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
    candidate: _RewriteCandidate,
    entered: _late_gate_models._Entered,
) -> bool:
    """Reissue the interrupted push through the gate, and answer for what it came to.

    A gate that held the candidate -- parked it, or handed it to an
    adjudication -- owns the issue from there, so nothing is announced or
    routed; its park's flags are written as the gate left them.
    """
    push = _rewrite_publication.CandidatePush(candidate)
    published = _late_push._publishes(
        _late_records._gate(context.gh, context.spec, context.issue, context.state, context.worktree),
        completed.branch,
        entered,
        transport=push,
    )
    if published.refused:
        return _replay_transfer_parks._park_refused_permit_recovery(context, completed)
    if published.held:
        context.gh.write_pinned_state(context.issue, context.state)
        return True
    landing = push.landing
    if landing is None or not published.landed:
        return _outcomes._park_failed_recovery_push(context, completed)
    if entered.permit_only and not _transfers._rotated_onto(context.state, completed.head):
        return _replay_transfer_parks._park_unfinished_recovery(
            context, completed, _recovery_push._UNROTATED.format(published=completed.head),
        )
    return _finish.finishes_the_recovery(context, landing)
