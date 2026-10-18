# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Evidence settled for a landed head, invalidated wherever a later tick reads what it rests on moving.

The real-git finish case (`rewrite_verification_recovery_support`), the run
settled and the finish killed at a final handoff boundary. The landing read
moving -- the checkout committed past the head, or the remote rolled back --
invalidates the run whole on whichever road that reading takes; so do the
requirements read moving with the comment unreadable for that write, or ahead
of a debt park. With no room for the run's history entry, the movement is
recorded by blanking its base tip instead, so putting the requirements or the
configuration back before room is made revives nothing. The run is never made
again, and no developer is launched.
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
from tests.workflow.interleaving import _RacesPastTheCall

_EDITED_BODY = "Also cover a base that moved twice."

# Room for the evidence's history entry and the park, not the debt's write.
_SHORT_OF_THE_DEBT = 250

# Room for a debt already recorded, and not the evidence's history entry.
_SHORT_OF_THE_HISTORY = 20

_FILLER = "room_filler"

_DEBT_PARK = "auto_base_rebase_unrecorded_debt"

_ANOTHER_COMMAND = "echo another"

# Whether the comment is filled ahead of the recovery, or while it proves the run.
_FILLED_WHILE_PROVED = (False, True)

# The proof's reading of the pinned comment: the refresh read it first.
_THE_PROOFS_READING = 2

# The finishes that die once their checkpoint, announcing the landing, landed.
_CHECKPOINTED = handoff.BOUNDARIES[4:]

# The finishes that die before their checkpoint lands, the debt still owed.
_UNCHECKPOINTED = handoff.BOUNDARIES[:4]


def _commits_past(case: support.CapturedRunCase, _head: str) -> None:
    """Commit past `_head` in `case`'s checkout, as another hand would."""
    case._git(*support.STRAY_COMMIT, cwd=case._wt)


def _puts_the_checkout_on(case: support.CapturedRunCase, head: str) -> None:
    """Reset `case`'s checkout onto `head`."""
    case._git("reset", "--quiet", "--hard", head, cwd=case._wt)


def _fills_short_of(case: support.CapturedRunCase, left: int) -> None:
    """Fill the pinned comment to `left` characters short of its limit, as another road's records would."""
    filled = case.gh.read_pinned_state(case.issue)
    filled.set(_FILLER, "")
    room = MAX_PINNED_BODY - len(pinned_state_body(filled.data))
    filled.set(_FILLER, "x" * (room - left))
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
        # The issue is edited under the run, and the comment will not read
        # again: the invalidation lands over the tick's own reading.
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
        # No room for the debt, and the issue edited under the run: the run is
        # invalidated before the debt's park, so nothing current is routed.
        for boundary in _UNCHECKPOINTED:
            with self.subTest(boundary=boundary.name):
                self.setUp()
                head, settled = self._settles_then_dies(boundary)
                written = self.issue.body
                self.issue.body = _EDITED_BODY
                _fills_short_of(self, _SHORT_OF_THE_DEBT)

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


class FullCommentMoveTest(support.CapturedRunCase, unittest.TestCase):
    """Movement under a settled run the comment has no room to invalidate is recorded, so nothing put back revives."""

    def test_moved_requirements_are_recorded(self) -> None:
        # The issue is edited under the run on a full comment: the movement is
        # recorded by blanking the base tip, so putting the requirements back
        # before room is made still leaves the run invalidated whole.
        for during, boundary in product(_FILLED_WHILE_PROVED, handoff.BOUNDARIES):
            with self.subTest(filled_while_proved=during, boundary=boundary.name):
                self.setUp()
                head, settled = self._settles_then_dies(boundary)
                written = self.issue.body
                self.issue.body = _EDITED_BODY
                self._recovers_filling(during=during)

                self._assert_recorded(settled)
                self._puts_it_right(head, settled, partial(setattr, self.issue, "body", written))

    def test_a_moved_configuration_is_recorded(self) -> None:
        # Another command is configured on a full comment once the landing is
        # announced: the movement is recorded, so putting it back revives nothing.
        for boundary in _CHECKPOINTED:
            with self.subTest(boundary=boundary.name):
                self.setUp()
                head, settled = self._settles_then_dies(boundary)
                self.configures(_ANOTHER_COMMAND)
                _fills_short_of(self, _SHORT_OF_THE_HISTORY)
                self.recovers()

                self._assert_recorded(settled)
                self._puts_it_right(head, settled, partial(self.configures, support.CONFIGURED))

    def _settles_then_dies(self, boundary: handoff.Boundary) -> tuple:
        """Land a reviewed rebase, settle its run, and kill the finish at `boundary`; the head, and the settled run."""
        head = self.lands_a_reviewed_rebase()
        handoff.dies_at(self.gh, boundary, partial(self.finishes, head))
        return head, readings.pinned_records(self)[1]

    def _recovers_filling(self, *, during: bool) -> None:
        """Recover with the comment filled to its limit: ahead of the recovery, or `during` its proof of the run."""
        fills = partial(finish_moves.fills_the_comment, self)
        if not during:
            fills()
            self.recovers()
            return
        racing = _RacesPastTheCall(self.gh.read_pinned_state, _THE_PROOFS_READING, fills)
        with patch.object(self.gh, "read_pinned_state", racing):
            self.recovers()

    def _assert_recorded(self, settled) -> None:
        """`settled` held current beside the standing attempt, the movement recorded by its blank base tip."""
        pinned = readings.pinned(self)
        self.assertEqual(readings.pinned_records(self)[1], settled)
        self.assertEqual(pinned[readings.KEY_PENDING_PUSH], self.anchor)
        self.assertIsNone(pinned[readings.KEY_REWRITE_BASE])

    def _puts_it_right(self, head: str, settled, puts_back) -> None:
        """Do `puts_back`, make room, and recover: `settled` invalidated whole, `head` routed once, run once."""
        puts_back()
        finish_moves.makes_room(self)
        self.recovers()

        retired = (*git_support.invalidated(self), (settled.receipt, readings.INVALIDATED))
        self.assertEqual(readings.pinned_records(self), (None, None, retired))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual((entry.revision, entry.binding), (settled.revision, settled.binding))
        self.assertEqual(support.announced(self), [head])
        self.assertEqual(readings.relabels(self), readings.ROUTED)
        self.assertEqual((self.runs(), self.developer.call_count), (1, 0))


if __name__ == "__main__":
    unittest.main()
