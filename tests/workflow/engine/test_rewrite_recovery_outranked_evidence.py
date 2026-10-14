# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A run settled for the landed head, outranked by a newer transaction the next recovery abandons, is invalidated.

The real-git finish case (`rewrite_verification_recovery_support`), every
finish -- handed over directly or reached by a refresh -- held to the dormant
settled-evidence policy (`settled_finish_support`): a finish recorded its run
for the landed head and died posting its artifact, and the recovery settled
that run under the anchor and died before announcing it. Another road then
recorded a newer transaction for the head beside the run, spending a revision
past it. The settled report both are bound to moves -- before the next
recovery proves the newer transaction, or while that recovery publishes it --
so the newer transaction is abandoned into history. The run it outranked is no
reader's current evidence any more, and it was bound to the report that moved,
so the recovery invalidates it whole, its revision and binding kept, and
routes the head to the fresh reviewer -- even where that recovery dies before
its relabel and a later one finishes it -- rather than routing the run as
current or holding every later poll over the revision spent past it. So does a
revision floor nobody can read beside that history: the revision the abandoned
transaction spent still reads on its own, so the run is invalidated rather
than held over the floor for good -- and so does a floor raised past the run
with nothing left recorded, the newer transaction dropped, behind a recovery
that settled and announced the run and died at its relabel. The run is never
made again, nothing is pushed, and no developer is launched.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.workflow.engine import (
    verification_carries as _carries,
    verification_record_state as _record_state,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
    settled_finish_support as settled,
    verification_report_fixture as _report,
)
from tests.workflow.interleaving import _RacesPastTheCall


def _settles_a_later_report(case: support.CapturedRunCase, head: str) -> None:
    """Settle report 3 of `head` and hand a reviewer it, over the comment as it stands."""
    case.state = case.gh.read_pinned_state(case.issue)
    _report.settles_report(case, 3, "Implemented the change and covered a base that moved twice.", head=head)
    case.gh.write_pinned_state(case.issue, case.state)


class OutrankedRunTest(settled.SettledRunCase, unittest.TestCase):
    """A run a newer, abandoned transaction outranks is invalidated and the head routed, never held for good."""

    def test_abandoned_before_its_proof(self) -> None:
        # The report moves before the next recovery proves the newer
        # transaction, which it abandons unposted; that recovery routes the
        # head, or dies at the relabel behind its announcement and the next
        # one finishes it -- the run invalidated either way.
        for boundary in (None, handoff.BEFORE_THE_RELABEL):
            with self.subTest(boundary=getattr(boundary, "name", "uninterrupted")):
                self.setUp()
                head, settled, newer = self._outranks()
                _settles_a_later_report(self, head)

                handoff.dies_at(self.gh, boundary, self.recovers)
                self.recovers()
                self.recovers()

                self._assert_routed_over(head, settled, newer)
                self.assertEqual(self.posted(newer), [])

    def test_abandoned_while_it_is_published(self) -> None:
        # The report moves just as the recovery posts the newer transaction's
        # artifact, so its settlement is refused and it is abandoned behind
        # that post: the run beside it is invalidated and the head routed,
        # where every later poll would otherwise hold over the revision spent.
        head, settled, newer = self._outranks()
        settles = partial(_settles_a_later_report, self, head)
        moves = _RacesPastTheCall(self.gh.publish_verification_artifact, 1, settles)
        with patch.object(self.gh, support.POST, moves):
            self.recovers()
        self.recovers()
        self.recovers()

        self._assert_routed_over(head, settled, newer)
        self.assertEqual(self.posted(newer), [newer.commands])

    def test_outranked_beside_an_unreadable_floor(self) -> None:
        # The newer transaction is abandoned into history and the revision
        # floor stops reading: the entry still outranks the run, which the
        # recovery invalidates before any hold over that floor, and the head
        # is routed rather than held poll after poll.
        head, settled, newer = self._outranks()
        state = self.gh.read_pinned_state(self.issue)
        self.assertTrue(_carries.abandons(state, newer))
        state.set(readings.KEY_REVISION_FLOOR, "unreadable")
        self.gh.write_pinned_state(self.issue, state)

        self.recovers()
        self.recovers()

        self._assert_routed_over(head, settled, newer)
        self.assertEqual(self.posted(newer), [])

    def test_a_floor_past_the_run_outranks_it(self) -> None:
        # The recovery settles the run and dies at its relabel, and a
        # revision past it is spent with nothing left recorded beside it --
        # a newer transaction dropped. That revision outranks the run for
        # good, so the next recovery invalidates it whole rather than route
        # it as the last word on the head or hold every later poll over it,
        # and routes the head, already announced, to the fresh reviewer.
        head, captured = self.captures()
        self.dies_at(support.RELABEL, self.recovers)
        state = self.gh.read_pinned_state(self.issue)
        state.set(readings.KEY_REVISION_FLOOR, captured.revision + 1)
        self.gh.write_pinned_state(self.issue, state)

        self.recovers()

        retired = (*git_support.invalidated(self), (captured.receipt, readings.INVALIDATED))
        self.assertEqual(readings.pinned_records(self), (None, None, retired))
        self.assert_recovered(head)

    def _outranks(self) -> tuple:
        """Settle a captured run under the anchor, unannounced, and record a newer one beside it; head and both.

        The newer transaction carries the run's own binding and transcript, as
        another road answering the same review would record it.
        """
        head, captured = self.captures()
        handoff.dies_at(self.gh, handoff.BEFORE_THE_ANNOUNCEMENT, self.recovers)
        settled = readings.pinned_records(self)[1]
        self.assertEqual(settled.receipt, captured.receipt)
        state = self.gh.read_pinned_state(self.issue)
        newer = _record_state.mint_pending_evidence(state, git_support.ISSUE, captured.binding, captured.commands)
        self.assertTrue(_record_state.record_pending_evidence(state, newer))
        self.gh.write_pinned_state(self.issue, state)
        return head, settled, newer

    def _assert_routed_over(self, head: str, settled, newer) -> None:
        """`settled` invalidated whole and `newer` abandoned, `head` announced and routed once, nothing made again."""
        retired = (
            *git_support.invalidated(self),
            (settled.receipt, readings.INVALIDATED),
            (newer.receipt, readings.ABANDONED),
        )
        self.assertEqual(readings.pinned_records(self), (None, None, retired))
        invalidated = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-2]
        self.assertEqual((invalidated.revision, invalidated.binding), (settled.revision, settled.binding))
        routed = (support.announced(self), readings.relabels(self))
        self.assertEqual(routed, ([head], readings.ROUTED))
        self.assertEqual(readings.attempt(readings.pinned(self)), readings.RETIRED)
        made = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(made, (1, 0, 0))


if __name__ == "__main__":
    unittest.main()
