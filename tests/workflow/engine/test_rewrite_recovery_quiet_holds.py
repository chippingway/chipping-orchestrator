# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An anchor the dispatcher holds with nothing parked or posted, proving the run it keeps first.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7's
rebased head reviewed, its run captured by a finish that died posting its
artifact, or settled under the anchor by one that died before its
announcement. The dispatcher then holds a handler back for the anchor, and its
answer posts nothing: under a label the refresh drives it leaves the anchor to
the refresh, and under one the refresh does not drive it finds its own
stranded park already standing. Either hold keeps the attempt, so the run is
proved first all the same (`git/base_sync/persistence._proves_before_the_park`):
the issue edited before the hold and put back right behind it has the run
abandoned or invalidated whole, nothing posted beside the one stranded park,
and the recovery that takes the anchor up next -- the label put back and a
reply given, where the park stands -- routes the head with nothing current.

A run another finish settles, the edit put back, while the stranded park's
proof abandons it is invalidated over that edit all the same -- or, the comment
full, has it recorded by its base tip blanked -- and a newer run settled over
it under its own receipt is left as it stands.
The run is made once, and nothing is pushed or launched.
"""
from __future__ import annotations

import unittest
from collections.abc import Callable
from functools import partial
from itertools import product
from typing import NamedTuple
from unittest.mock import patch

from orchestrator.workflow.engine import verification_durable as _durable
from tests.support.fakes import FakeLabel
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
)
from tests.workflow.interleaving import _RacesTheStep

_EDITED_BODY = "Also cover a base that moved twice."

# A label the refresh does not drive, under which the dispatcher's hold strands the attempt.
_UNDRIVEN = "workflow:resolving_conflict"


def _strands(case) -> None:
    """Relabel `case`'s issue out of the refresh's stages and have the dispatcher's hold take its stranded park."""
    case.issue.labels = [FakeLabel(_UNDRIVEN)]
    guarded.answers_a_held_anchor(case)
    case.assertTrue(case.pinned_fields(guarded.AWAITING)[0])


def _puts_the_label_back(case) -> None:
    """Put `case`'s issue back on the stage it was reviewed in and reply to the park."""
    case.issue.labels = [FakeLabel(git_support.REVIEWING)]
    case.continues()


class _Road(NamedTuple):
    """Where the dispatcher's quiet hold stands: what brings it there, and what releases the anchor after it."""

    name: str
    stands: Callable
    releases: Callable


_ROADS = (
    _Road("a label the refresh drives", lambda _case: None, lambda _case: None),
    _Road("a stranded park already standing", _strands, _puts_the_label_back),
)


class QuietHoldProofTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A hold that posts nothing proves the run it keeps, so restoring what moved revives nothing."""

    def test_a_quiet_hold_proves_the_run(self) -> None:
        # The run, captured or settled, is retired whole by the hold that
        # read the edit, with the attempt kept and nothing posted; the head
        # is then routed once with nothing current.
        for road, captures in product(_ROADS, (True, False)):
            with self.subTest(road=road.name, captured=captures):
                self.setUp()
                head, run = self.captures() if captures else self.settles_then_dies()
                self._holds_over_an_edit(road)

                self._assert_retired(run, captured=captures)
                road.releases(self)
                self.recovers()

                self.assert_routed(head)

    def _holds_over_an_edit(self, road: _Road) -> None:
        """Bring the hold to `road`, then have the dispatcher hold the anchor with the issue edited, put back behind.

        The hold posts nothing.
        """
        road.stands(self)
        noticed = len(self.gh.posted_comments)
        written = self.issue.body
        self.issue.body = _EDITED_BODY
        guarded.answers_a_held_anchor(self)
        self.issue.body = written
        self.assertEqual(len(self.gh.posted_comments), noticed)

    def _assert_retired(self, run, *, captured: bool) -> None:
        """`run` abandoned whole where it was only `captured`, else invalidated whole, the attempt on its anchor."""
        self.assertEqual(self.pinned_fields(readings.KEY_PENDING_PUSH)[0], self.anchor)
        if captured:
            self.assert_abandoned(run)
        else:
            self.assert_invalidated(run)


class SettledUnderTheProofTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A captured run another finish settles while the stranded park's proof abandons it over an edited issue."""

    def test_the_settled_run_is_invalidated(self) -> None:
        # The park is taken over the run invalidated whole, and continued,
        # routes the head with nothing current.
        head, captured = self._holds_over_a_settlement()
        self.assertTrue(self.pinned_fields(guarded.AWAITING)[0])
        self.assert_invalidated(captured)
        self.issue.labels = [FakeLabel(git_support.REVIEWING)]
        self.continues()
        self.recovers()
        self.assert_routed(head)

    def test_a_full_comment_records_the_movement(self) -> None:
        # Nothing parked and the tip blank, the run current; room made, the
        # next recovery invalidates it whole and routes the head.
        head, captured = self._holds_over_a_settlement(finish_moves.fills_the_comment)
        self.assertEqual(self.pinned_fields(guarded.AWAITING, readings.KEY_REWRITE_BASE), (None, None))
        self.assertEqual(readings.pinned_records(self)[1].receipt, captured.receipt)
        finish_moves.makes_room(self)
        self.issue.labels = [FakeLabel(git_support.REVIEWING)]
        self.recovers()
        retired = readings.pinned_records(self)[2]
        self.assertEqual(retired[-1], (captured.receipt, readings.INVALIDATED))
        self.assert_routed(head)

    def test_a_successor_settled_meanwhile_is_kept(self) -> None:
        # The newer run stays current, the captured one superseded as that
        # road left it, and nothing is parked.
        captured = self._holds_over_a_settlement(partial(guarded.records_a_newer_run, settles=True))[1]
        current, retired = readings.pinned_records(self)[1:]
        self.assertNotEqual(current.receipt, captured.receipt)
        self.assertEqual(retired[-1], (captured.receipt, "superseded"))
        self.assertIsNone(self.pinned_fields(guarded.AWAITING)[0])

    def _holds_over_a_settlement(self, then=None) -> tuple:
        """Capture a run, edit the issue, and strand the attempt while another finish settles it; head and run."""
        head, captured = self.captures()
        written = self.issue.body
        self.issue.body = _EDITED_BODY
        self.issue.labels = [FakeLabel(_UNDRIVEN)]
        raced: list = []
        elsewhere = partial(guarded.settles_elsewhere, self, head, written, raced, then)
        with patch.object(_durable, "durable_comment", _RacesTheStep(_durable.durable_comment, elsewhere)):
            guarded.answers_a_held_anchor(self)
        self.assertEqual(raced, [head])
        return head, captured


if __name__ == "__main__":
    unittest.main()
