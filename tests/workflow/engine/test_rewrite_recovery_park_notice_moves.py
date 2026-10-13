# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A run settled for a landed head, under the debt park whose notice another road writes past.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7's
rebased head reviewed, its run settled under the anchor, and the finish killed
before its announcement. The next tick parks for want of room for the
landing's report debt rather than route the head, and while the park's notice
is posted another road settles and reviews report 3 of the head, the report
the run was bound to replaced. The park is decided on the report records and
refused over that move, which reads the run moving before the tick ends: it is
invalidated whole, so putting report 2 back revives nothing.

Room made, the head is then routed with nothing current, its notice said
once, the run never made again, and no developer launched. The recovery parks
that keep the attempt -- behind a fetch and a reset that both failed, or over
a checkout gone from disk under a label the refresh does not drive -- are
journeys of their own (`test_rewrite_recovery_kept_park_moves`,
`test_rewrite_recovery_missing_checkout`).
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from orchestrator.workflow.engine import verification_settlement_state as _settlement
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
    verification_report_fixture as _report,
)
from tests.workflow.interleaving import _RacesPastTheCall

_AWAITING = "awaiting_human"

# The report and review records report 3's settlement moves, as the pinned comment spells them.
_MOVED_RECORDS = (
    "developer_report_current",
    "developer_report_handoff",
    "review_subject",
    "review_returned_subject",
)

# Room on the pinned comment for the run's history entry and the park behind
# it, and short of the landing's report debt and the announcement it rides.
_SHORT_OF_THE_DEBT = 250



def _settles_a_later_report(case: support.CapturedRunCase, head: str, replaced: list) -> None:
    """Settle and review report 3 of `head` as another road would, keeping in `replaced` the records it moves."""
    pinned = readings.pinned(case)
    replaced.append({key: pinned.get(key) for key in _MOVED_RECORDS})
    case.state = case.gh.read_pinned_state(case.issue)
    _report.settles_report(case, 3, "Implemented the change and covered a base that moved twice.", head=head)
    case.gh.write_pinned_state(case.issue, case.state)


def _puts_back(case: support.CapturedRunCase, replaced: list) -> None:
    """Write the report and review records back as they stood before report 3 moved them, as `replaced` kept them."""
    state = case.gh.read_pinned_state(case.issue)
    for key, recorded in replaced[-1].items():
        state.set(key, recorded)
    case.gh.write_pinned_state(case.issue, state)


def _fills_short_of_the_debt(case: support.CapturedRunCase) -> None:
    """Fill the pinned comment to `_SHORT_OF_THE_DEBT` short of its limit, as another road's records would."""
    filled = case.gh.read_pinned_state(case.issue)
    filled.set("room_filler", "")
    room = MAX_PINNED_BODY - len(pinned_state_body(filled.data))
    filled.set("room_filler", "x" * (room - _SHORT_OF_THE_DEBT))
    case.gh.write_pinned_state(case.issue, filled)


class ParkNoticeMoveTest(support.CapturedRunCase, unittest.TestCase):
    """A debt park refused over a moved report leaves no run for the next poll to take up as current."""

    def test_a_debt_park_refused_over_a_moved_report(self) -> None:
        # The debt park, decided on the report records, is refused over
        # report 3, and that refusal invalidates the run; report 2 put back
        # and room made, the head is routed with nothing current.
        head, settled = self._settles_then_dies()
        _fills_short_of_the_debt(self)
        replaced = self._posting_moves_the_report(head)

        self.assertFalse(readings.pinned(self).get(_AWAITING))
        self._assert_retired(settled)
        _puts_back(self, replaced)
        finish_moves.makes_room(self)
        self.recovers()

        self._assert_retired(settled)
        self._assert_routed(head)

    def _settles_then_dies(self) -> tuple:
        """Land a reviewed rebase, settle its run, and kill its finish before the announcement; the head and the run."""
        head = self.lands_a_reviewed_rebase()
        handoff.dies_at(self.gh, handoff.BEFORE_THE_ANNOUNCEMENT, partial(self.finishes, head))
        return head, readings.pinned_records(self)[1]

    def _posting_moves_the_report(self, head: str) -> list:
        """Recover with report 3 of `head` settled behind the first issue-thread post; the records it moved."""
        replaced: list = []
        races = _RacesPastTheCall(self.gh.comment, 1, partial(_settles_a_later_report, self, head, replaced))
        with patch.object(self.gh, "comment", races):
            self.recovers()
        return replaced

    def _assert_retired(self, run) -> None:
        """`run` invalidated whole, its revision and binding kept, behind the anchor's own evidence; run once."""
        retired = (*git_support.invalidated(self), (run.receipt, readings.INVALIDATED))
        self.assertEqual(readings.pinned_records(self), (None, None, retired))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual((entry.revision, entry.binding), (run.revision, run.binding))
        self.assertEqual((self.runs(), self.developer.call_count), (1, 0))

    def _assert_routed(self, head: str) -> None:
        """`head` announced, relabelled, and its attempt retired once, nothing pending or current, nothing pushed."""
        self.assertEqual(readings.pinned_records(self)[:2], (None, None))
        self.assertEqual(support.announced(self), [head])
        self.assertEqual(readings.relabels(self), readings.ROUTED)
        self.assertEqual(readings.attempt(readings.pinned(self)), readings.RETIRED)
        self.assertEqual(self.pushes.call_count, 0)


if __name__ == "__main__":
    unittest.main()
