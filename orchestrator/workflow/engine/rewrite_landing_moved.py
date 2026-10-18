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
while one that fails keeps the attempt and the evidence both. `abandons` hands
what the tick holds to the recovery's proof, the one every park and hold
keeping the attempt asks (`rewrite_landing_retirement.retires_unproved`), with
the landing's move as movement already read under each receipt it holds
(`rewrite_evidence_proof.LEFT_THE_LANDING`) whatever the proof's readings say,
the heads perhaps back by then: the transaction is abandoned unrun through the
last word, or refused for good with no room, and settled evidence invalidated
into history whole, then read afresh and retired again if put back behind that
write. A write not landing over the fresh comment falls back to the tick's own
reading, the tick held only where neither lands. A successor another road
settled under its own receipt is proved on its own readings, every comment
those finishes read, a refused abandonment's strict edit among them, asked
for movement under it too, so a mark of movement read there retires it
however soon put back. The proof's primitives are `rewrite_landing_captured`'s.
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
    the head the evidence answers for are the landed road's to finish, which
    reads them again itself. A head the snapshot holds as "" is one nobody
    read, which establishes no movement, so the evidence is kept for a reset
    that lands to retire (`rewrite_landing_retirement.retires_over_the_reset`).
    Heads both on the landing say nothing of movement already recorded: an
    attempt recording no base tip beside that evidence -- the blank a reset
    recorded ahead of a park that never landed among it -- proves no base the
    head was replayed onto, so the recovery's proof is asked first, reading
    that blank as the movement it is (`abandons`, `read` False), and the
    landed road finishes over nothing it retired, whichever policy that
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
    handed the landing's move as the movement already read under every receipt
    the tick holds (`LEFT_THE_LANDING`), so nothing it reads next -- the heads
    back on the landing among it -- keeps that evidence: a captured
    transaction is abandoned unrun, or refused for good with no room, and
    settled evidence invalidated whole, read afresh behind its write and
    retired again if put back there. A successor another road settled under
    its own receipt is proved on its own readings, and invalidated only where
    they, or a comment the proof's writes read, record it moving. Nothing is
    routed either way, nor read or written where neither stands. False where
    either still stands once its retirement was asked, or a successor's proof
    holds. `read` False hands the proof no landing movement, for a caller that
    read none, so it reads what the comment and checkout record moving itself.

    A checkout gone from disk since the landing was read has nothing to prove
    over, so the proof a park asks first takes it
    (`rewrite_recovery_parks.proves_before_a_park`): the reset recorded by
    blanking the base tip, the retirement landed in a write of its own over
    the comment read afresh, however soon another road puts that tip back.
    """
    held = _retirement.receipts(context.state)
    if held and not context.worktree.is_dir():
        return _recovery_parks.proves_before_a_park(context)
    return _retirement.retires_unproved(context, dict.fromkeys(held, LEFT_THE_LANDING) if read else None)
