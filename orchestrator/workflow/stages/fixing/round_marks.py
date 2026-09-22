# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether the mark a settlement raised may still close the round in hand.

One reading, for the two owners that could reach a relabel with a mark standing:
`reporting`, which takes the relabel every settlement-driven hand-back goes
through, and `report_recovery`, which finds a round settled while nobody was
looking. It is spelled apart from both so that it stays ONE reading: a road that
carried a copy of this question would come to answer it differently, and the
answer it would get wrong is a hand-back taken past feedback nobody has read.

What the question IS: a settlement can apply a fixing round's bookkeeping and
cannot move a label, so it leaves a mark for the tick that can. That mark is a
CLAIM on the next relabel rather than a fact about it, and the claim has to be
placed before it is acted on -- the settlement may have happened under another
label entirely, or over a round that has since been replaced.

A comment carrying no mark at all is asked nothing. The no-feedback bounce
relabels on every tick that finds nothing to do, report or no report, and a
stage whose own road decided to hand the head back is not waiting on a
settlement's permission to do it.

The hand-back this reading licenses STAMPS the transaction it closed, here, in
the write that takes the mark down. The two records do not expire together: the
mark is cleared by that write and the handoff beside it is persistent -- nothing
clears one, and a settlement only replaces it -- so a mark somebody writes back
onto the comment afterwards would find that same handoff, recorded under
`workflow:fixing` with both route anchors already closed, and be correlated into
a second hand-back over whatever arrived in between. The stamp is what ties a
mark to ONE transaction instead of to any settlement whose handoff is still
lying there.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.stages.fixing import state as _state
from orchestrator.workflow.state import WorkflowLabel

# The validating route's own record of the round it opened. It and
# `pending_fix_at` are what a settlement CLEARS, so either one standing over a
# raised mark says a newer round opened after that settlement.
_REVIEWER_ANCHOR = "pending_fix_reviewer_comment_id"


def _places_the_round_in_hand(state: PinnedState) -> bool:
    """Whether a relabel may be taken on what this comment says.

    True for a comment carrying no raised mark, which is every road that
    reached a relabel on its own reasons: nothing has claimed this hand-back,
    so nothing can withhold it.

    Otherwise the claim is CORRELATED, and all four readings have to hold.

    The settling LABEL is the one no other state can stand in for. A settlement
    records which label the issue was carrying as it landed -- read afresh, so
    a human who moved the issue while a developer ran is visible in it -- and
    one that landed anywhere but `workflow:fixing` is a round this stage was
    not behind. Acting on it takes the issue off the label that human chose,
    in the same tick that recorded their move; left alone, that mark would
    instead be waiting for whichever fixing round came next, which is a round
    it says nothing about. It is also the only thing that catches an anchorless
    manual move back to `workflow:fixing`, since the settlement cleared both
    route anchors and dropped the transaction, leaving the comment looking
    exactly like a round that closed.

    A handoff this build cannot read answers the same way, and deliberately: a
    mark nothing can place is one nothing should act on. What it costs is a
    hand-back left for the road that can prove it; what acting on it would cost
    is a relabel past feedback nobody has read.

    A handoff this stage has already HANDED BACK on answers the same way
    again, and it is the one reading none of the others can stand in for. The
    mark comes down with that hand-back and the handoff does not, so a comment
    whose round closed legitimately goes on carrying a readable
    `workflow:fixing` handoff with both route anchors cleared and no report
    owed -- everything above agrees -- for as long as the issue lives. A mark
    written back onto it by hand would be correlated into a second hand-back,
    off a transaction whose round was closed and whose label moved, past
    whatever feedback arrived in between. What `_stamps_the_round_handed_back`
    leaves is the receipt of that transaction, so the claim is about ONE of
    them rather than about any settlement still lying on the comment.

    The two readings beside them are kept because they are free and
    independent. A settlement clears both route anchors and drops the
    transaction, so a mark found over either anchor belongs to a round that
    opened AFTER it was raised, and one found beside an owed report belongs to
    a publication that has not happened yet.
    """
    if not state.get(_state._SETTLED_ROUND):
        return True
    if _report_delivery.owes_a_report(state):
        return False
    handoff = _settlement.read_handoff(state)
    if handoff is None or handoff.settled_under is not WorkflowLabel.FIXING:
        return False
    if handoff.receipt == state.get(_state._HANDED_BACK_RECEIPT):
        return False
    return not any(
        state.get(recorded) is not None
        for recorded in (_state._PENDING_FIX_AT, _REVIEWER_ANCHOR)
    )


def _stamps_the_round_handed_back(state: PinnedState) -> None:
    """Record the transaction this hand-back is closing a round on.

    Staged by the hand-back into the write that takes the mark down, so the
    two are one fact and durable before the label moves: a tick dying between
    them leaves a round nothing can hand back twice, exactly as it leaves one
    nothing can mistake for one that just settled.

    A comment carrying no raised MARK stamps nothing, and that reading lives
    here rather than at the caller because it is the same reading the
    correlation above opens on. The relabel a hand-back takes is not evidence
    a transaction closed one: the reading above places every road that reached
    a relabel on its own reasons, the no-feedback bounce among them, and such
    a road passes over whatever handoff an earlier transaction happened to
    leave. Stamped from there, an unrelated transaction is recorded as handed
    back -- which then refuses the mark a replay of that very transaction
    raises, leaving a round nothing can close -- and the write costs a key the
    settling measurement reserved room for only where a record's own spends
    RAISE the mark.

    A handoff nothing can read stamps nothing, and needs to stamp nothing --
    the reading above refuses such a mark on its own account, so no later one
    correlates against it either.

    The ROOM for it is reserved when the transaction is accepted, and by this
    same call: the engine's settling measurement plays it onto the payload a
    settlement whose spends raise the mark would leave
    (`engine/report_record_state.settled_payload`). Unreserved, a transaction
    is accepted at the ceiling, settles, raises the mark, and then this write
    is the one GitHub refuses -- with the mark raised, the relabel never
    taken, and every later tick failing in exactly the same place.
    """
    if not state.get(_state._SETTLED_ROUND):
        return
    handoff = _settlement.read_handoff(state)
    if handoff is not None:
        state.set(_state._HANDED_BACK_RECEIPT, handoff.receipt)
