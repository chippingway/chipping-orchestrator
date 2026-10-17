# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed rewrite finished again and again, saying and making all once.

Direct finishes through the coordinator every road hands its landing to
(`settled_route_support`): issue #7's run settled beside another road's
charged run ledger, its finish killed at each final handoff boundary -- the
relabel's own record among them -- nothing the run rests on moving. The next
finish routes the head; one after that finds no attempt -- retired, replaced,
or beside a successor whose handoff is missing or damaged -- and touches
nothing. The issue ends with one notice,
event, artifact, settlement, round reset, relabel, and stage-entry event, the
command run once, nothing pushed or launched, and the run ledger exactly as
charged.
"""
from __future__ import annotations

import unittest
from functools import partial

from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    settled_finish_support as settled,
    settled_route_support as route,
)

# The handoff's place on the pinned comment.
_HANDOFF = "verification_evidence_handoff"


class RepeatedFinishTest(route.SettledRouteCase, unittest.TestCase):
    """Direct finishes behind one killed at any boundary route the settled run once and repeat nothing."""

    def test_every_boundary_finishes_once(self) -> None:
        # The run stays current whole beside the evidence the rewrite moved
        # past, posted once, and a transaction another road records for the
        # head behind the route is left owed and unposted.
        for boundary in handoff.BOUNDARIES:
            with self.subTest(boundary=boundary.name):
                self.setUp()
                head, run = self._routes_behind(boundary)
                later = settled.records_a_newer_run(self)
                pinned = readings.pinned(self)

                self.assertEqual(self.finalizes(head), FinishOutcome.UNFINISHABLE)

                self.assertEqual(readings.pinned(self), pinned)
                self.assert_routed_once(head)
                self.assertEqual(pinned[readings.KEY_REVIEW_ROUND], 0)
                settled.assert_charged_as_left(self)
                self._assert_settled_once(run, later)

    def test_a_replaced_attempt_is_left_as_it_stands(self) -> None:
        # The landing is routed, and a later rebase pins an attempt of its
        # own, anchored on the landed head, beside a transaction another road
        # records for that head: the earlier landing handed over again finds
        # another attempt anchored and touches neither.
        head = self.lands_a_reviewed_rebase()
        settled.charges(self)
        self.assertEqual(self.finalizes(head, FinishRoad.PUBLICATION), FinishOutcome.ROUTED)
        state = self.gh.read_pinned_state(self.issue)
        state.set(readings.KEY_PENDING_PUSH, head)
        self.gh.write_pinned_state(self.issue, state)
        later = settled.records_a_newer_run(self)
        pinned = readings.pinned(self)

        self.assertEqual(self.finalizes(head), FinishOutcome.UNFINISHABLE)

        self.assertEqual(readings.pinned(self), pinned)
        self.assertEqual(readings.pinned_records(self)[0], later)
        settled.assert_charged_as_left(self)
        self.assert_made()

    def test_a_handoff_out_of_step_is_no_mark(self) -> None:
        # The landing is routed and another road settles a newer run for the
        # head under its own receipt, whose handoff then reads missing or
        # damaged. Nothing marked movement under that run, so the landing
        # handed over again finds no attempt and leaves the successor current.
        for damaged in (None, "unreadable"):
            with self.subTest(handoff=damaged):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                self.assertEqual(self.finalizes(head, FinishRoad.PUBLICATION), FinishOutcome.ROUTED)
                later = settled.records_a_newer_run(self, settles=True)
                state = self.gh.read_pinned_state(self.issue)
                state.set(_HANDOFF, damaged)
                self.gh.write_pinned_state(self.issue, state)

                self.assertEqual(self.finalizes(head), FinishOutcome.UNFINISHABLE)

                self.assertEqual(self.gh.read_pinned_state(self.issue).data, state.data)
                self.assertEqual(readings.pinned_records(self)[1].receipt, later.receipt)

    def _routes_behind(self, boundary: handoff.Boundary) -> tuple:
        """Settle the run beside a charged ledger, kill its finish at `boundary`, and route the next; head and run."""
        head = self.lands_a_reviewed_rebase()
        settled.charges(self)
        handoff.dies_at(self.gh, boundary, partial(self.finalizes, head, FinishRoad.PUBLICATION))
        run = readings.pinned_records(self)[1]
        self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)
        return head, run

    def _assert_settled_once(self, run, later) -> None:
        """`run` current whole beside the evidence the rewrite moved past, posted once, and `later` pending unposted."""
        pending, current, retired = readings.pinned_records(self)
        self.assertEqual((pending, retired), (later, git_support.invalidated(self)))
        whole = (current.receipt, current.revision, current.binding)
        self.assertEqual(whole, (run.receipt, run.revision, run.binding))
        self.assertEqual(len(self.posted(run)), 1)
        self.assertEqual(self.posted(later), [])


if __name__ == "__main__":
    unittest.main()
