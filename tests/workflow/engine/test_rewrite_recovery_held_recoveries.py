# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Settled evidence a whole recovery keeps the attempt over, proved ready before it holds, parks, or stops.

The held-run case (`held_run_support`): issue #7's run settled and its finish
killed before its announcement, then the next tick's whole recovery -- not a
direct finish -- reaches a road that keeps the attempt: the landed road over a
candidate head nobody could prove, the stranded park of an issue relabelled
out from under the attempt whose notice raised, and the finish's own debt
park for a report debt with no room, refused or raising over report 3 settled
while its notice was posted. Each proves the run first, so the movement
invalidates it whole -- or abandons a run only captured -- and putting what
moved back routes the head once with nothing current, the run made once.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from functools import partial
from unittest.mock import patch

from orchestrator.git.base_sync import rewrite_facts
from orchestrator.git.publication.probes import _BranchDivergence
from tests.support.fakes import FakeLabel
from tests.workflow.engine import (
    held_run_support as held,
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
)


def _unproved_first(original, calls: list, *args):
    """Answer `original`, its first reading proving no head, as a failed head proof reads."""
    reading = original(*args)
    calls.append(reading)
    if len(calls) > 1:
        return reading
    return replace(reading, head="", tree="", base=_BranchDivergence())


class RecoveryHoldProofTest(held.HoldCase, unittest.TestCase):
    """A whole recovery that keeps the attempt over the settled run proves it first, as a direct finish does."""

    def test_an_unproved_head_proves_first(self) -> None:
        # The landed road cannot prove the candidate's head, so it finishes
        # nothing, and the issue was edited: the run is invalidated before the
        # attempt is kept, and with the issue and the reading back the head is
        # routed with nothing current.
        head = self.settles_then_dies()
        written = self.issue.body
        self.issue.body = held.EDITED_BODY
        unproved = partial(_unproved_first, rewrite_facts._reads_the_checkout, [])
        with patch.object(rewrite_facts, "_reads_the_checkout", side_effect=unproved):
            self.recovers()

        self.assert_invalidated(standing=self.anchor)
        self.issue.body = written
        self.recovers()

        self.assert_invalidated(standing=None)
        self.assert_routed_once(head)

    def test_a_raised_stranded_notice_proves(self) -> None:
        # The issue is relabelled out from under the attempt, and while the
        # stranded park's notice is posted report 3 of the head is settled
        # and the post's answer lost: the run is invalidated before the error
        # goes on, so report 2 and the label put back route the head with
        # nothing current.
        head = self.settles_then_dies()
        self.issue.labels = [FakeLabel("workflow:resolving_conflict")]
        replaced = self.settles_under_the_notice(head, raises=True, recovered=True)

        self.assert_invalidated(standing=self.anchor)
        self.assertFalse(readings.pinned(self).get("awaiting_human"))
        self.puts_back_records(replaced)
        self.issue.labels = [FakeLabel(git_support.REVIEWING)]
        self.recovers()

        self.assert_invalidated(standing=None)
        self.assert_routed_once(head)

    def test_a_debt_park_notice_proves_the_run(self) -> None:
        # The finish's own debt park, reached by a whole recovery: report 3
        # settled while its notice is posted, refused or raising, invalidates
        # the run before the recovery stops, and the next one routes the head
        # with nothing current once room is made.
        for raises in (False, True):
            with self.subTest(raised=raises):
                self.setUp()
                head = self.settles_then_dies()
                finish_moves.fills_the_comment(self, held.SHORT_OF_THE_DEBT)
                replaced = self.settles_under_the_notice(head, raises=raises, recovered=True)

                self.assert_invalidated(standing=self.anchor)
                self.puts_back_records(replaced)
                finish_moves.makes_room(self)
                self.recovers()

                self.assert_invalidated(standing=None)
                self.assert_routed_once(head)

    def test_a_debt_park_abandons_a_captured_run(self) -> None:
        # The run only captured, the debt park's record refused over report 3
        # with report 2 put back right behind that refusal: a whole recovery
        # abandons the run, and the next one routes the head once room is made.
        head, captured = self.captures()
        finish_moves.fills_the_comment(self, held.SHORT_OF_THE_DEBT)
        self.puts_back_records(self.settles_under_the_notice(head, raises=False, restores=True, recovered=True))

        self.assert_abandoned(captured)
        finish_moves.makes_room(self)
        self.recovers()
        self.assert_abandoned(captured)
        self.assert_routed_once(head)


if __name__ == "__main__":
    unittest.main()
