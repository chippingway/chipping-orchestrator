# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Evidence settled for a landed head, invalidated wherever a later tick reads what it rests on moving.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7's
rebased head reviewed, its run settled under the anchor, and the finish killed
at a final handoff boundary (`rewrite_handoff_test_support`) before it routed
the head. The next tick's recovery reads what the run rests on moving before
any finish takes it up again -- the checkout committed past the head, or the
remote rolled back onto the anchor -- and takes the road that reading chooses,
a reset or a park, without the route; the settled run is invalidated into
history whole on the way, its revision and binding kept, so putting the
landing back and replying revives nothing it decided. And a finish that reads
the requirements moving under the run invalidates it even where the pinned
comment will not read again for that write: the invalidation lands over the
tick's own reading instead, so putting the requirements back revives nothing
either. So does a finish the comment has no room to record the landing's
report debt on: the run is proved ready before the park that debt takes, and
the requirements edited under it invalidate it there, so making room, putting
the requirements back, and replying routes the head with nothing current. The
run is never made again, and no developer is launched.
"""
from __future__ import annotations

import unittest
from collections.abc import Callable
from functools import partial
from itertools import product
from typing import NamedTuple
from unittest.mock import patch

from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from orchestrator.workflow.engine import (
    verification_durable as _durable,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
)

_EDITED_BODY = "Also cover a base that moved twice."

# Room on the pinned comment for the evidence's history entry and the park
# behind it, and short of the report debt and the announcement it rides.
_SHORT_OF_THE_DEBT = 250

_FILLER = "room_filler"

_DEBT_PARK = "auto_base_rebase_unrecorded_debt"

# The finishes that die before their checkpoint lands, so the next one still
# owes the landing's report debt a write.
_UNCHECKPOINTED = handoff.BOUNDARIES[:4]


def _commits_past(case: support.CapturedRunCase, _head: str) -> None:
    """Commit past `_head` in `case`'s checkout, as another hand would."""
    case._git(*support.STRAY_COMMIT, cwd=case._wt)


def _puts_the_checkout_on(case: support.CapturedRunCase, head: str) -> None:
    """Reset `case`'s checkout onto `head`."""
    case._git("reset", "--quiet", "--hard", head, cwd=case._wt)


def _fills_short_of_the_debt(case: support.CapturedRunCase) -> None:
    """Fill the pinned comment to `_SHORT_OF_THE_DEBT` short of its limit, as another road's records would."""
    filled = case.gh.read_pinned_state(case.issue)
    filled.set(_FILLER, "")
    room = MAX_PINNED_BODY - len(pinned_state_body(filled.data))
    filled.set(_FILLER, "x" * (room - _SHORT_OF_THE_DEBT))
    case.gh.write_pinned_state(case.issue, filled)


def _puts_the_remote_on(case: support.CapturedRunCase, head: str) -> None:
    """Point `case`'s remote branch, and the pull request reading it, at `head`."""
    case._git("update-ref", f"refs/heads/{git_support.BRANCH}", head, cwd=case._remote)
    case.pull_request.head.sha = head


class _Move(NamedTuple):
    """What moves the landing under the settled run, and what puts it back, each handed the case and the head."""

    name: str
    moves: Callable
    restores: Callable


_MOVES = (
    _Move("the checkout committed past the head", _commits_past, _puts_the_checkout_on),
    _Move(
        "the remote rolled back onto the anchor",
        lambda case, _head: _puts_the_remote_on(case, case.anchor),
        _puts_the_remote_on,
    ),
)


class SettledRunMoveTest(support.CapturedRunCase, unittest.TestCase):
    """A run settled under the anchor goes into history wherever the recovery reads what it rests on moving."""

    def test_a_moved_landing_invalidates_the_run(self) -> None:
        # The recovery reads the landing off the head and resets or parks
        # without routing it: the run is invalidated first, and stays so once
        # the landing is put back and the issue's author replies.
        for move, boundary in product(_MOVES, handoff.BOUNDARIES):
            with self.subTest(move=move.name, boundary=boundary.name):
                self.setUp()
                head, settled = self._settles_then_dies(boundary)
                move.moves(self, head)

                self.recovers()
                self._assert_invalidated(settled)
                move.restores(self, head)
                self.continues()
                self.recovers()

                self._assert_invalidated(settled)

    def test_an_unread_comment_still_invalidates(self) -> None:
        # The issue is edited under the run, and the pinned comment will not
        # read again for the write invalidating it: that write lands over the
        # tick's own reading, the head is routed once, and putting the
        # requirements back finds nothing current to route.
        for boundary in handoff.BOUNDARIES:
            with self.subTest(boundary=boundary.name):
                self.setUp()
                head, settled = self._settles_then_dies(boundary)
                written = self.issue.body
                self.issue.body = _EDITED_BODY
                with patch.object(_durable, "durable_comment", return_value=(None, _durable._UNREAD)):
                    self.recovers()
                self.issue.body = written
                self.recovers()

                self._assert_invalidated(settled)
                routed = (support.announced(self), readings.relabels(self))
                self.assertEqual(routed, ([head], readings.ROUTED))
                self.assertEqual(readings.attempt(readings.pinned(self)), readings.RETIRED)

    def test_a_debt_park_invalidates_first(self) -> None:
        # The comment has no room for the landing's report debt, and the issue
        # was edited under the settled run: the run is invalidated before the
        # park the debt takes, so room made, the requirements put back, and a
        # reply route the head with nothing current, the run made once.
        for boundary in _UNCHECKPOINTED:
            with self.subTest(boundary=boundary.name):
                self.setUp()
                head, settled = self._settles_then_dies(boundary)
                written = self.issue.body
                self.issue.body = _EDITED_BODY
                _fills_short_of_the_debt(self)

                self.recovers()
                self.assertEqual(readings.pinned(self)["park_reason"], _DEBT_PARK)
                self._assert_invalidated(settled)
                self._puts_it_right(written)

                self._assert_invalidated(settled)
                routed = (support.announced(self), readings.relabels(self))
                self.assertEqual(routed, ([head], readings.ROUTED))

    def _puts_it_right(self, written: str) -> None:
        """Put the issue's body back as `written`, make room on the comment, reply, and recover once more."""
        self.issue.body = written
        finish_moves.makes_room(self)
        self.continues()
        self.recovers()

    def _settles_then_dies(self, boundary: handoff.Boundary) -> tuple:
        """Land a reviewed rebase, settle its run, and kill the finish at `boundary`; the head, and the settled run."""
        head = self.lands_a_reviewed_rebase()
        handoff.dies_at(self.gh, boundary, partial(self.finishes, head))
        settled = readings.pinned_records(self)[1]
        self.assertEqual(settled.binding.target.target_head, head)
        return head, settled

    def _assert_invalidated(self, settled) -> None:
        """`settled` invalidated whole behind the anchor's evidence, run once, nothing pushed or launched."""
        retired = (*git_support.invalidated(self), (settled.receipt, readings.INVALIDATED))
        self.assertEqual(readings.pinned_records(self), (None, None, retired))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual((entry.revision, entry.binding), (settled.revision, settled.binding))
        made = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(made, (1, 0, 0))


if __name__ == "__main__":
    unittest.main()
