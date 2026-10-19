# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The evidence a landed rewrite's finish captured or settled, retired wherever its recovery reads the landing moved.

A finish that recorded the landed head's evidence transaction and stopped
short of its route leaves it pending beside the attempt
(`rewrite_finish_captured`), and one that settled it and then died in the
tail of its route -- before the announcement, the relabel, or the retirement
-- leaves it current beside the attempt (`rewrite_landing_records.settled`).
Only the recovery of the push already landed -- over a remote and a checkout
both still on that head -- may take the route either carries
(`rewrite_landed`). Every other road the recovery is sent down
reads the landing somewhere else and clears, resets, or parks the attempt
without that route: an unmoved checkout back on the anchor, a remote that is
not on the checkout -- rolled back, or moved out of band -- and a remote and
checkout that agree on another head. These are the helpers that abandon the
transaction, and invalidate the settled evidence into history whole
(`rewrite_finish_readiness.invalidates`), before any such road is taken, so
movement under a decision leaves none a later route, or a reader once the
attempt is cleared, may take. The recovery's coordinator (`rewrite_recovery`)
asks them of every snapshot before the road it chooses, and the landed road
(`rewrite_landed`) of a checkout or remote it reads leaving the head.

`abandons_off_the_landing` answers whether a road may go on: True where the
snapshot reads no head off the head a finish captured or settled evidence
for, or where nothing for that head stands once its retirement was asked
(`abandons`), and False where evidence still stands that no write could
retire, for the coordinator to hold the tick with nothing reset, cleared, or
parked. A head the snapshot could
not read -- a checkout whose head would not prove, or a remote not yet read --
establishes no movement, so the evidence is kept: the road such a snapshot
takes resets the checkout, and that reset, once it lands, is the movement the
retirement answers (`rewrite_landing_retirement.retires_over_the_reset`),
while one that fails keeps both. `abandons` hands what the tick holds to the
recovery's proof (`rewrite_landing_retirement.retires_unproved`) with the
landing's move as movement already read under each receipt it holds
(`rewrite_evidence_proof.LEFT_THE_LANDING`), however soon the heads are back:
the transaction abandoned unrun, settled evidence invalidated whole and
retired again if put back, a successor proved on its own readings.
"""
from __future__ import annotations

import logging

from orchestrator.git.base_sync import attempt_records as _attempt_records
from orchestrator.git.base_sync.models import _AutoRebaseRecoveryContext, _AutoRebaseRecoverySnapshot
from orchestrator.workflow.engine import (
    rewrite_landing_records as _landing_records,
    rewrite_landing_retirement as _retirement,
    rewrite_recovery_parks as _recovery_parks,
)
from orchestrator.workflow.engine.rewrite_evidence_proof import LEFT_THE_LANDING

log = logging.getLogger("orchestrator.workflow")


def abandons_off_the_landing(context: _AutoRebaseRecoveryContext, snapshot: _AutoRebaseRecoverySnapshot) -> bool:
    """Retire what a finish captured or settled for the landed head where `snapshot` reads a head off it; may it go on.

    Asked by the recovery's coordinator of every snapshot it reads, before
    the road the snapshot chooses is taken; a remote and a checkout both on
    the head the evidence answers for are the landed road's to finish. A head
    read as "" establishes no movement, so the evidence is kept for a reset
    that lands to retire (`rewrite_landing_retirement.retires_over_the_reset`).
    Heads both on the landing beside an attempt recording no base tip prove no
    base the head was replayed onto, so the proof is asked first, reading that
    blank as movement (`abandons`, `read` False), and the landed road finishes
    over nothing it retired, whichever policy that
    finish selects. False only where evidence still stands that the
    abandonment or invalidation could not retire, logged: the coordinator
    holds the tick then rather than take a road that would leave it behind.
    """
    recorded = (_landing_records.captured(context.state), _landing_records.settled(context.state))
    heads = [record.binding.target.target_head for record in recorded if record is not None]
    read = {snapshot.local_head, snapshot.remote_head}
    moved = any(read - {"", head} for head in heads)
    unbased = bool(heads) and not _attempt_records._recorded_onto(context.state)
    if not (moved or unbased) or abandons(context, read=moved):
        return True
    log.warning(
        "issue=#%d holding the recovery of %.8s: the verification evidence captured or settled for it could not "
        "be retired yet, so nothing is reset, cleared, or parked until a later tick retires it",
        context.issue.number, heads[0],
    )
    return False


def abandons(context: _AutoRebaseRecoveryContext, *, read: bool = True) -> bool:
    """Retire what an earlier finish recorded or settled for the head the landing was read leaving; whether none stands.

    The recovery's proof (`rewrite_landing_retirement.retires_unproved`),
    handed the landing's move as movement already read under every receipt
    the tick holds (`LEFT_THE_LANDING`), so the heads back on the landing keep
    nothing: a captured transaction abandoned unrun, or refused for good with
    no room, settled evidence invalidated whole and retired again if put back.
    A successor under its own receipt is proved on its own readings. False
    where either still stands, or a successor's proof holds. `read` False
    hands the proof no landing movement, for a caller that read none. A
    checkout gone from disk takes the proof before a park instead
    (`rewrite_recovery_parks.proves_before_a_park`), the reset recorded first.
    """
    held = _retirement.receipts(context.state)
    if held and not context.worktree.is_dir():
        return _recovery_parks.proves_before_a_park(context, lost=(context.worktree,))
    return _retirement.retires_unproved(context, dict.fromkeys(held, LEFT_THE_LANDING) if read else None)
