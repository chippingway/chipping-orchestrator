# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether the mark a settlement raised may still close the round in hand.

One reading, for every road that could reach a relabel with a mark standing. It
is spelled apart from `reporting`, which takes the relabel, so that it stays ONE
reading: a road that carried a copy of this question would come to answer it
differently, and the answer it would get wrong is a hand-back taken past
feedback nobody has read.

What the question IS: a settlement can apply a fixing round's bookkeeping and
cannot move a label, so it leaves a mark for the tick that can. That mark is a
CLAIM on the next relabel rather than a fact about it, and the claim has to be
placed before it is acted on -- the settlement may have happened under another
label entirely, or over a round that has since been replaced.

A comment carrying no mark at all is asked nothing. The no-feedback bounce
relabels on every tick that finds nothing to do, report or no report, and a
stage whose own road decided to hand the head back is not waiting on a
settlement's permission to do it.
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
    return not any(
        state.get(recorded) is not None
        for recorded in (_state._PENDING_FIX_AT, _REVIEWER_ANCHOR)
    )
