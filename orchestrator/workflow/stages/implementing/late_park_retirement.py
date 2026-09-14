# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Retire the measurement, authorization, settled-split, or superseded park being answered.

Each targeted retirement changes only the park whose condition has ended.
A settled split cannot clear an unrelated reason, while supersession
explicitly clears the current wait and its reason together.
"""
from __future__ import annotations

from orchestrator.github import (
    pinned_state as _pinned_state,
)
from orchestrator.workflow.late_split import (
    models as _late_models,
)
from orchestrator.workflow.stages.implementing import (
    late_command as _command,
    late_measurement_state as _late_measurement_state,
    state as _state,
)


def _retire_spent_park(state: _pinned_state.PinnedState) -> None:
    """Drop a measurement park this attempt is the answer to, latch and all.

    The reason is durable and so is the flag beside it, so without this a park
    a fresh reading has superseded travels on -- into the stage the
    publication hands the issue to, where it is state describing a step
    nothing is waiting on.

    Called by the two owners that ANSWER the question it was taken for -- the
    verdict a count settles, and the verdict a commit this workflow already
    decided about needs no count for -- rather than by the gate they sit
    behind. Entering the gate is not an answer: the reading can miss again,
    and a retirement taken on the way in is one a durable write in that window
    makes permanent, leaving an unparked issue whose reading still has not
    happened and whose next miss starts the bound over. Every other exit
    either takes a park of its own with the reason it fails for NOW or leaves
    this one standing because it is still true.

    The LATCH goes with the reason, and it is the half that decides whether
    the reading was worth taking. A reconciliation the dispatcher drives has
    no run behind it to clear the flag, so a pair that measured small would
    retire its record, record the commit as owed a push, and hand the tick to
    a source stage that reads `awaiting_human` and takes its parked road --
    waiting for a reply to a question this very tick answered, while the
    approved commit sits unpushed.

    ONE park is retired here, and every other is left exactly where it
    stands -- a question, a dirty tree, a timeout, and above all the park an
    adjudicated candidate takes when nobody has authorized it. That one is
    waiting on a PERSON rather than on a reading, so nothing a reading does
    answers it: a road that lost the base and is counting a quiet miss would
    unpark an issue whose operator has not replied, and the exemption nobody
    stands behind would publish on the next poll with no authorization
    recorded anywhere. It comes off where a publication under it actually
    happens, and nowhere else.
    """
    if state.get(_state._PARK_REASON) == _late_measurement_state.PARK_MEASUREMENT_FAILED:
        state.set(_state._PARK_REASON, None)
        state.set(_state._AWAITING_HUMAN, False)


def _retire_authorized_park(state: _pinned_state.PinnedState) -> None:
    """Drop the authorization park a publication under it is the answer to.

    The park an adjudicated candidate takes when nobody has authorized it,
    taken down by both of the answers that publish one from under it without
    asking anybody. One is the unmeasured road, where the record answers the
    park's own question -- an override that now covers the commit, or the
    bookkeeping owed for one its own pull request already stands on. The other
    is a fresh count the ceiling lets through, which answers something else
    entirely: nobody's permission was ever needed for a change this size, so
    the candidate is not this park's to hold. Neither reads the thread, so
    nothing else on either would take the flag off, and a published commit
    would leave an issue still saying a human is holding it, with the source
    stage's parked road stopping on every poll after.

    Retired where the publication is DECIDED rather than on the way into the
    gate, which is the whole of what keeps it apart from the measurement park
    beside it. What this park waits for is a person, and no reading answers a
    person: a tick that lost the base, or one a close ends, would otherwise
    unpark an issue whose operator has not replied, and the exemption nobody
    stands behind would publish on the next poll under nobody's authority at
    all.
    """
    if state.get(_state._PARK_REASON) == _command.PARK_UNAUTHORIZED_EXEMPTION:
        state.set(_state._PARK_REASON, None)
        state.set(_state._AWAITING_HUMAN, False)


def _retire_settled_park(
    state: _pinned_state.PinnedState, recorded: _late_models.LateGeneration,
) -> bool:
    """Drop a measurement park a settled split's own record provoked.

    True where one was standing, so the caller knows it owes the write. Left
    to the caller for the reason `_retire_spent_park` leaves it there: the
    tick that clears a park has its own write to ride out on, and this domain
    does not put two where one will do.

    The park is this domain's, and on a record whose candidate has already
    become children it is this domain's own false positive: the group the
    retirement keeps is there for the releases and the branch delete the
    umbrella still owes, not for a reading anybody is waiting on. Left
    standing it is an issue reading as parked for a human with nothing for a
    human to answer -- and the reason is durable, so the pre-tick base refresh
    goes on holding the branch it names for as long as the flag does.

    Only the measurement park is retired, for the reason every other
    retirement of it gives: a question, a rejected child, or a child somebody
    closed by hand is a park with an answer still owed, and this record says
    nothing about any of them.
    """
    if not recorded.split_has_settled:
        return False
    if state.get(_state._PARK_REASON) != _late_measurement_state.PARK_MEASUREMENT_FAILED:
        return False
    _retire_spent_park(state)
    return True


def _retire_superseded_park(state: _pinned_state.PinnedState) -> None:
    """Drop a park the adjudication is taking the issue out of.

    A hold hands every later tick to the late coordinator, and what the issue
    is waiting on from that moment is a verdict rather than whatever the park
    asked a human about. Left standing the flag reaches the coordinator as an
    issue already parked -- its own parked dispatch fires on a mention nobody
    made about the question now open -- and the reason beside it describes a
    step no one is retrying. Every road into a hold either had no park or has
    one this hold supersedes, so the clear is unconditional.
    """
    state.set(_state._AWAITING_HUMAN, False)
    state.set(_state._PARK_REASON, None)
