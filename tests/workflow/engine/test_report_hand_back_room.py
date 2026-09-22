# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The write a fixing round's mark earns is reserved with its settlement.

A settlement applies the bookkeeping a record froze and cannot move a label, so
the round a FIXING record closes is handed back by the tick behind it -- and
that write stamps the transaction it closed on, onto the comment the settlement
leaves. It is the same shape as the code-publication receipt and the comment-id
ledger entry: a write that lands between the measurement and the moment the
room is spent, and one the acceptance therefore has to carry.

Unreserved, a transaction is accepted at the ceiling, settles, raises the mark,
and then the hand-back is the write GitHub refuses. That failure has no bottom:
the mark stays raised, the relabel is never taken, and every later tick fails in
exactly the same place with the round unable to reach its reviewer at all.

The crowding each case works at is SEARCHED against the writer under test rather
than computed from a payload the case assembled, so a difference between two
searches is the room one build reserves and the other does not -- not an
arithmetic this module did.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import patch

from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState
from orchestrator.workflow.engine import (
    report_record_state as _record_state,
    report_records as _records,
)
from orchestrator.workflow.stages.fixing import round_marks as _round_marks
from tests.workflow.engine import report_record_test_support as support

# What a case crowds the rest of the comment with.
_FILLER = "filler"

_CROWDING = "y"

# The spends a fixing round's record freezes that no other route's does: the
# mark saying a fixing round's transaction is what settled.
_RAISES_THE_MARK = ((_records.SETTLED_ROUND, True),)

# The name of the write that stamps the transaction a hand-back closed on,
# patched on the owner that performs it to model a build reserving nothing.
_STAMPS_THE_HAND_BACK = "_stamps_the_round_handed_back"


def _largest_crowding(pending, *, reserved: bool) -> int:
    """The most crowding this record is still accepted under.

    `reserved=False` is the build that measured the settlement alone, with the
    write behind it stubbed out on the owner that performs it -- which is the
    only way to ask what that write costs without spelling it again here.
    """
    if reserved:
        return _searched(pending)
    with patch.object(_round_marks, _STAMPS_THE_HAND_BACK):
        return _searched(pending)


def _searched(pending) -> int:
    """The crowding this build, as it stands, accepts that record under."""
    low, high = 0, MAX_PINNED_BODY
    while low < high:
        tried = (low + high + 1) // 2
        crowded = PinnedState(state_data={_FILLER: _CROWDING * tried})
        if _record_state.record_pending_report(crowded, pending):
            low = tried
        else:
            high = tried - 1
    return low


class FixingHandBackRoomTest(unittest.TestCase):
    """What the acceptance of a fixing round's record has to leave room for."""

    def test_a_hand_back_with_no_room_is_refused(self) -> None:
        # The most a build reserving nothing accepts is exactly where a build
        # that reserves the hand-back has to refuse: the settlement fits and
        # the write behind it does not, which is the one failure nothing later
        # recovers from.
        marked = replace(support.PUBLISHED, spends=_RAISES_THE_MARK)
        crowded = PinnedState(state_data={
            _FILLER: _CROWDING * _largest_crowding(marked, reserved=False),
        })

        self.assertFalse(
            _record_state.record_pending_report(crowded, marked),
        )
        self.assertFalse(_record_state.carries_pending_report(crowded))

    def test_a_round_no_mark_closes_reserves_nothing(self) -> None:
        # Only a record whose spends RAISE the mark earns a hand-back, and a
        # road charged for a write it never makes is one refused for room
        # nothing was ever going to take.
        unmarked = replace(support.PUBLISHED, spends=())

        self.assertEqual(
            _largest_crowding(unmarked, reserved=True),
            _largest_crowding(unmarked, reserved=False),
        )


if __name__ == "__main__":
    unittest.main()
